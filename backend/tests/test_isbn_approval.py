"""Phase C uses real migration-chain guards on entirely synthetic SQLite data."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import sqlite3

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models import IsbnAuditRun, IsbnAuditResult, IsbnReview, IsbnDecision, Volume
from app.services.isbn_identity import digest, snapshot
from app.services.isbn_sources import proof
from app.services.isbn_audit import evidence_signature
from app.services.isbn_decisions import decide, DecisionError
from app.services.isbn_safety import check_guards
from app.services.safety_backup import inspect_file
from tests.test_isbn_safety import guarded
from tests.test_isbn_audit import ISBN


def make_review(engine, *, evidence_mutator=None, age=0, volume_id=2, isbn=ISBN, book_title=None):
    with Session(engine, expire_on_commit=False) as session:
        volume = session.get(Volume, volume_id)
        target = snapshot(volume)
        book = dict(title=book_title or f"Berserk Cilt {volume.volume_number}", publisher="Athica Yayınları", language="Türkçe",
                    binding="Karton Kapak", url="https://example.com/product", raw_isbns=[isbn])
        records = [proof(code, code, target, book) for code in ("kitapyurdu", "bkm")]
        records[0]["url"] = "https://www.kitapyurdu.com/kitap/synthetic/1.html"
        records[1]["url"] = "https://www.bkmkitap.com/synthetic"
        if evidence_mutator: evidence_mutator(records)
        run = IsbnAuditRun(status="COMPLETED", total=1, processed=1, errors=0)
        session.add(run); session.flush()
        result = IsbnAuditResult(run_id=run.id, volume_id=volume_id, snapshot=target, snapshot_hash=digest(target),
            evidence=records, evidence_hash=evidence_signature(records), status="MISSING_ISBN", proposed_isbn=isbn,
            reason="Synthetic evidence", checked_at=datetime.utcnow()-timedelta(hours=age))
        session.add(result); session.flush()
        review = IsbnReview(volume_id=volume_id, result_id=result.id, version=1, workflow="REVIEW_PENDING",
                            next_check_at=datetime.utcnow())
        session.add(review); session.commit()
        return dict(admin_id=1, volume_id=volume_id, result_id=result.id, version=1, action="ACCEPT", reason="Ürün kanıtlarını doğruladım.")


def test_approved_change_preserves_all_relationships_and_consumes_capability(guarded):
    path, engine = guarded
    args = make_review(engine)
    before = inspect_file(path)["tables"]
    with Session(engine) as session:
        result = decide(session, **args)
        assert result.old_isbn is None and result.new_isbn == ISBN
        assert session.get(Volume, 2).isbn == ISBN
        assert session.scalar(text("SELECT count(*) FROM isbn_approval_permits")) == 0
        assert session.scalar(text("SELECT isbn_approval_token()")) is None
        with pytest.raises(IntegrityError, match="isbn_p0_write_paused"):
            session.execute(update(Volume).where(Volume.id == 2).values(isbn=None))
        session.rollback()
        check_guards(session.connection().connection.driver_connection)
    after = inspect_file(path)["tables"]
    assert before.keys() == after.keys()
    assert all(before[t] == after[t] for t in before if t != "volumes")
    assert before["volumes"]["rows"] == after["volumes"]["rows"]


@pytest.mark.parametrize("valid_domain", [True, False])
@pytest.mark.parametrize("source,host", [("kitapsepeti","www.kitapsepeti.com"),("bora","boradagitim.com")])
def test_additional_source_evidence_passes_same_approval_checks(guarded, valid_domain,source,host):
    path, engine = guarded
    def mutate(records):
        records[1].update(source=source, independence_group=source,
                          url=f"https://{host}/synthetic" if valid_domain else "https://other.example/synthetic")
    args = make_review(engine, evidence_mutator=mutate)
    before = inspect_file(path)
    with Session(engine) as session:
        if valid_domain:
            assert decide(session, **args).new_isbn == ISBN
        else:
            with pytest.raises(DecisionError, match="ürün bağlantısı"): decide(session, **args)
            assert inspect_file(path) == before


def test_partial_bora_bibliography_cannot_be_used_as_a_second_vote(guarded):
    path,engine=guarded
    def mutate(records):
        records[1].update(source="bora",independence_group="bora",url="https://boradagitim.com/Istem/Urun/Detay.aspx?Id=123",
                          language=None,binding=None,status="INCOMPLETE")
    args=make_review(engine,evidence_mutator=mutate)
    before=inspect_file(path)
    with Session(engine) as session:
        with pytest.raises(DecisionError,match="iki bağımsız"):decide(session,**args)
    assert inspect_file(path)==before


@pytest.mark.parametrize("change",[None,"ongoing","new_volume"])
def test_unnumbered_one_shot_approval_revalidates_catalogue_context(guarded,change):
    from tests.test_import_service import seed_catalog_series
    path,engine=guarded
    with Session(engine) as session:
        series=seed_catalog_series(session,"Synthetic One Shot","Athica Yayınları",volumes=(1,))
        series.jp_status=series.tr_status="completed"
        volume=session.scalar(select(Volume).where(Volume.series_id==series.id))
        volume.catalog_present=volume.catalog_released=True
        session.commit();vid,sid=volume.id,series.id
    args=make_review(engine,volume_id=vid,book_title="Synthetic One Shot")
    with Session(engine) as session:
        if change=="ongoing":session.get(Volume,vid).series.tr_status="ongoing"
        if change=="new_volume":session.add(Volume(series_id=sid,volume_number=2,catalog_present=True,catalog_released=False))
        session.commit()
        before=inspect_file(path)
        if change:
            with pytest.raises(DecisionError,match="Katalog bilgileri değişti"):decide(session,**args)
            assert inspect_file(path)==before
        else:
            assert decide(session,**args).new_isbn==ISBN
            assert session.scalar(text("SELECT count(*) FROM isbn_approval_permits"))==0


def test_numberless_multi_volume_products_cannot_authorize_isbn_change(guarded):
    path,engine=guarded
    args=make_review(engine,book_title="Berserk")
    before=inspect_file(path)
    with Session(engine) as session:
        with pytest.raises(DecisionError,match="iki bağımsız"):decide(session,**args)
    assert inspect_file(path)==before


@pytest.mark.parametrize("case", ["old", "conflict", "duplicate_group", "wrong_edition", "invalid_isbn", "stale_proof", "empty"])
def test_unsafe_evidence_never_changes_catalogue_or_records_decision(guarded, case):
    path, engine = guarded
    def mutate(records):
        if case == "conflict": records[1]["raw_isbns"] = ["9786258630640"]
        if case == "duplicate_group": records[1]["source"] = "kitapyurdu"; records[1]["independence_group"] = "kitapyurdu"
        if case == "wrong_edition": records[1]["title"] = "Berserk Novel Cilt 2"
        if case == "stale_proof": records[0]["checked_at"] = (datetime.utcnow()-timedelta(days=2)).isoformat()
        if case == "empty": records.clear()
    args = make_review(engine, age=25 if case == "old" else 0, evidence_mutator=mutate)
    if case == "invalid_isbn": args.update(action="MANUAL", isbn="9786258630634")
    before = inspect_file(path)
    with Session(engine) as session:
        with pytest.raises(DecisionError): decide(session, **args)
        assert session.scalar(select(IsbnDecision.id)) is None
        assert session.scalar(text("SELECT count(*) FROM isbn_approval_permits")) == 0
        assert session.scalar(text("SELECT isbn_approval_token()")) is None
    assert inspect_file(path) == before


def test_stale_metadata_and_new_review_version_are_rejected(guarded):
    path, engine = guarded
    args = make_review(engine)
    with Session(engine) as session:
        session.get(Volume, 2).page_count = 192; session.commit()
        with pytest.raises(DecisionError, match="Katalog bilgileri değişti"): decide(session, **args)
        assert session.get(Volume, 2).isbn is None


def test_unique_equivalent_isbn_collision_never_moves_or_merges(guarded):
    path, engine = guarded
    # Existing first-volume ISBN remains unique even if the second volume
    # claims it with two otherwise matching (synthetic) proofs.
    with Session(engine) as session: taken = session.get(Volume, 1).isbn
    from app.services.isbn_identity import canonical_isbn
    # P0's fixture code happens to have a valid checksum.
    assert canonical_isbn(taken)
    args = make_review(engine, isbn=taken)
    before = inspect_file(path)
    with Session(engine) as session:
        with pytest.raises(DecisionError, match="başka bir cilde"): decide(session, **args)
    assert inspect_file(path) == before


def test_only_one_of_two_concurrent_admin_tabs_can_apply(guarded):
    _, engine = guarded
    args = make_review(engine)
    def apply():
        with Session(engine) as session:
            try: decide(session, **args); return "ok"
            except DecisionError: return "stale"
    with ThreadPoolExecutor(2) as executor:
        results = list(executor.map(lambda _: apply(), range(2)))
    assert sorted(results) == ["ok", "stale"]
    with Session(engine) as session:
        assert len(list(session.scalars(select(IsbnDecision)))) == 1


def test_history_raw_sql_permit_forgery_and_replay_are_blocked(guarded):
    path, engine = guarded
    args = make_review(engine)
    with Session(engine) as session:
        decide(session, **args)
        decision_id = session.scalar(select(IsbnDecision.id))
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA recursive_triggers=OFF")
        for sql in ["UPDATE isbn_audit_results SET reason='forged'", "DELETE FROM isbn_audit_results",
                    "UPDATE isbn_decisions SET reason='forged'", "DELETE FROM isbn_decisions",
                    "UPDATE volumes SET isbn=NULL WHERE id=2"]:
            with pytest.raises(sqlite3.IntegrityError): connection.execute(sql)
            connection.rollback()
        with pytest.raises(sqlite3.OperationalError, match="isbn_approval_token"):
            connection.execute("INSERT INTO isbn_approval_permits VALUES (2,?,NULL,?,'forged')", (decision_id, ISBN))
        connection.rollback()
    # Ordinary application connections register only the inert function.
    with Session(engine) as session:
        with pytest.raises(IntegrityError, match="isbn_approval_required"):
            session.execute(text("INSERT INTO isbn_approval_permits VALUES (2,:id,NULL,:isbn,'forged')"), dict(id=decision_id, isbn=ISBN))
        session.rollback()
        with pytest.raises(DecisionError): decide(session, **args)


def test_guarded_http_approval_and_manual_checksum_normalization(guarded, monkeypatch):
    from fastapi.testclient import TestClient
    from app import database
    from app.main import create_app
    from app.auth import COOKIE_NAME, new_session
    from app.models import User
    _, engine = guarded
    args = make_review(engine, isbn="9780306406157")
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(database, "SessionLocal", factory)
    app = create_app(auto_init=False)
    def db():
        with factory() as session: yield session
    app.dependency_overrides[database.get_db] = db
    with factory() as session: token = new_session(session, session.get(User, 1))
    body = {k: v for k, v in args.items() if k not in {"volume_id", "admin_id"}}
    body.update(action="MANUAL", isbn="0-306-40615-2")
    with TestClient(app, headers={"Origin": "http://localhost:3000"}) as client:
        assert client.get("/admin/isbn/summary").status_code == 401
        client.cookies.set(COOKIE_NAME, token)
        response = client.post("/admin/isbn/reviews/2/decisions", json=body)
        assert response.status_code == 200, response.text
        assert response.json()["new_isbn"] == "9780306406157"
        assert client.post("/admin/isbn/reviews/2/decisions", json=body).status_code == 409
        detail = client.get("/admin/isbn/reviews/2").json()
        assert detail["current_isbn"] == "9780306406157"
        assert len(detail["decisions"]) == 1


def test_insert_or_replace_cannot_replace_evidence_through_unique_run_volume(guarded):
    path, engine = guarded
    make_review(engine)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA recursive_triggers=OFF")
        with pytest.raises(sqlite3.IntegrityError, match="isbn_history_immutable"):
            connection.execute("INSERT OR REPLACE INTO isbn_audit_results "
                "(id,run_id,volume_id,checked_at,snapshot,snapshot_hash,status,proposed_isbn,reason,evidence,evidence_hash) "
                "SELECT id+100,run_id,volume_id,checked_at,snapshot,snapshot_hash,status,proposed_isbn,'forged',evidence,evidence_hash FROM isbn_audit_results")
