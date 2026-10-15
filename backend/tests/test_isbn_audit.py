"""Phase A: synthetic catalogue + recorded/fake sources only."""
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models import IsbnAuditResult, IsbnAuditRun, IsbnReview, Volume
from app.services.isbn_identity import canonical_isbn, digest, eligible, evaluate, snapshot
from app.services.isbn_sources import page_book, proof
from app.services.isbn_audit import AuditConflict, IsbnAuditWorker, control_run, create_run
from tests.test_import_service import seed_catalog_series

ISBN = "9786258630633"


def target(**kwargs):
    result = dict(title="Blue Lock", original_title=None, volume_number=29, publisher="Komikşeyler",
                  isbn=ISBN, covers_from=None, covers_to=None, catalog_present=True,
                  catalog_released=True, release_date=None)
    return {**result, **kwargs}


def book(**kwargs):
    return dict(title="Blue Lock Cilt 29", publisher="Komik Şeyler Yayıncılık", language="Türkçe",
                binding="Karton Kapak", raw_isbns=[ISBN], url="https://example.com/book") | kwargs


def evidence(source="one", group=None, **kwargs):
    return proof(source, group or source, target(), book(**kwargs))


@pytest.mark.parametrize("value,expected", [
    ("978-625-863063-3", ISBN), (ISBN, ISBN), ("0-306-40615-2", "9780306406157"),
    ("080442957X", "9780804429573"), ("9786258630634", None), ("9693110002326", None),
    ("978625863063X", None), ("ISBN: 9786258630633", None), ("1234567890", None), (None, None)])
def test_checksum(value, expected):
    assert canonical_isbn(value) == expected


def test_consensus_and_missing_isbn_are_read_only():
    records = [evidence(), evidence("two"), dict(status="ERROR", source="three")]
    assert evaluate(target(), records)[0] == "VERIFIED"
    assert evaluate(target(isbn=None), records)[:2] == ("MISSING_ISBN", ISBN)
    assert evaluate(target(isbn="9786258630640"), records)[:2] == ("CONFLICT", ISBN)
    assert evaluate(target(), [evidence(), evidence("other-page", group="one")])[0] == "INSUFFICIENT_EVIDENCE"
    assert evaluate(target(), records + [evidence("third", raw_isbns=["9786258630640"])])[0] == "CONFLICT"


def test_source_errors_are_not_missing():
    assert evaluate(target(isbn=None), [dict(status="ERROR")]*3)[0] == "SOURCE_ERROR"
    assert evaluate(target(isbn=None), [dict(status="NO_RESULT"), dict(status="ERROR")])[0] == "INSUFFICIENT_EVIDENCE"
    assert evaluate(target(isbn=None), [dict(status="NO_RESULT")])[0] == "MISSING_ISBN"
    assert evidence(raw_isbns=[], publisher=None, language=None)["status"] == "NO_ISBN"


@pytest.mark.parametrize("changes", [dict(title="Blue Lock Cilt 28"), dict(language="English"),
    dict(publisher="Başka Yayıncı"), dict(title="Blue Lock Novel Cilt 29"),
    dict(title="Blue Lock Cilt 29 (Varyant Kapak)"), dict(title="Blue Lock Cilt 29 Limitli"),
    dict(title="Blue Lock 1-29 Seti"), dict(binding=None), dict(binding="https://schema.org/Hardcover"),
    dict(binding="unknown"), dict(raw_isbns=[ISBN, "9786258630640"])])
def test_physical_identity_and_internal_conflicts(changes):
    assert evidence(**changes)["status"] == "MISMATCH"


def test_named_regressions():
    for name, number, wrong in [("Solo Leveling", 2, "Solo Leveling Novel Cilt 2"),
            ("Afro Samuray", 1, "Afro Samuray Cilt 1 Limitli"),
            ("Yıldızların Sesi", -1, "Yıldızların Sesi Cilt 1"),
            ("Omniscient Reader's Viewpoint", 1, "Omniscient Reader's Viewpoint Cilt 1 Varyant")]:
        assert proof("one", "one", target(title=name, volume_number=number), book(title=wrong))["status"] == "MISMATCH"


def test_future_and_unknown_release_never_emit_missing():
    for changes in [dict(catalog_released=False), dict(catalog_released=None),
                    dict(release_date=(date.today()+timedelta(days=1)).isoformat())]:
        t = target(isbn=None, **changes)
        assert not eligible(t)
        assert evaluate(t, [])[0] == "SKIPPED_UPCOMING"
    assert not eligible(target(catalog_released=False, release_date="2020-01-01"))


def test_omnibus_and_paper_variant_require_exact_bibliography():
    omnibus = target(title="Dragon Ball", volume_number=5, covers_from=9, covers_to=10)
    assert proof("one", "one", omnibus, book(title="Dragon Ball 9&10"))["status"] == "MATCH"
    assert proof("one", "one", omnibus, book(title="Dragon Ball 7&8"))["status"] == "MISMATCH"
    variant = target(title="Solo Leveling (2. Hamur - Ana Kapak)", volume_number=1)
    assert proof("one", "one", variant, book(title="Solo Leveling Webtoon Cilt 1 (2. Hamur - Ana Kapak)"))["status"] == "MATCH"
    assert proof("one", "one", variant, book(title="Solo Leveling Webtoon Cilt 1 (Kuşe Kağıt - Ana Kapak)"))["status"] == "MISMATCH"


def test_mangakol_never_counts_as_independent_proof_or_masks_source_error():
    catalog = dict(source="mangakol", status="DISCOVERY", isbn=ISBN)
    assert evaluate(target(), [evidence(), catalog])[0] == "INSUFFICIENT_EVIDENCE"
    assert evaluate(target(), [dict(status="ERROR"), catalog])[0] == "SOURCE_ERROR"


def test_primary_bibliography_excludes_recommendations():
    html = '''<h1>Blue Lock Cilt 29</h1><script type="application/ld+json">{"@graph":[
      {"@type":"Product","url":"https://example.com/book","gtin13":"9786258630633","brand":{"name":"Komikşeyler"}},
      {"@type":"Product","url":"https://example.com/other","gtin13":"9786258630640"}]}</script>
      <div class="ky-pd-attributes__item"><span class="ky-pd-attributes__label">Dil:</span><span class="ky-pd-attributes__value">Türkçe</span></div>
      <div class="ky-pd-attributes__item"><span class="ky-pd-attributes__label">Cilt Tipi:</span><span class="ky-pd-attributes__value">Karton Kapak</span></div>'''
    parsed = page_book(html, "https://example.com/book")
    assert parsed["raw_isbns"] == [ISBN]
    assert proof("one", "one", target(), parsed)["status"] == "MATCH"


def test_durable_pause_resume_preserves_catalogue_and_one_review(engine, db_session):
    seed_catalog_series(db_session, "Blue Lock", "Komikşeyler", volumes=(29, 30))
    first, second = list(db_session.scalars(select(Volume).order_by(Volume.id)))
    first.isbn, first.catalog_released, first.catalog_present = ISBN, True, True
    second.catalog_released, second.catalog_present = False, True
    db_session.commit()
    before = [snapshot(v) for v in (first, second)]
    run = create_run(db_session, 1)
    assert run.total == 2
    with pytest.raises(AuditConflict): create_run(db_session, 1)
    control_run(db_session, run.id, "pause")
    class Source:
        code = group = "one"
        def collect(self, t): return [proof("one", "one", t, book())]
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    worker = IsbnAuditWorker(factory, source_factory=lambda: (None, [Source()]))
    worker.run_pending()
    db_session.expire_all()
    assert db_session.get(IsbnAuditRun, run.id).processed == 0
    control_run(db_session, run.id, "resume")
    worker.run_pending()
    db_session.expire_all()
    assert db_session.get(IsbnAuditRun, run.id).status == "COMPLETED"
    assert db_session.get(IsbnAuditRun, run.id).processed == 2
    assert [snapshot(db_session.get(Volume, v.id)) for v in (first, second)] == before
    assert db_session.get(IsbnReview, first.id).workflow == "REVIEW_PENDING"
    assert db_session.get(IsbnReview, second.id).workflow == "REVIEWED"
    create_run(db_session, 1)
    worker.run_pending()
    db_session.expire_all()
    assert len(list(db_session.scalars(select(IsbnReview)))) == 2
    assert len(list(db_session.scalars(select(IsbnAuditResult)))) == 4
    assert db_session.get(IsbnReview, first.id).version == 2


def test_restart_resumes_completed_items_and_identical_evidence_keeps_admin_decision(engine, db_session):
    from app.services.isbn_decisions import decide
    seed_catalog_series(db_session, "Blue Lock", "Komikşeyler", volumes=(29, 30))
    for volume in db_session.scalars(select(Volume)):
        volume.catalog_released = volume.catalog_present = True
    db_session.commit()
    run = create_run(db_session, 1)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    class Source:
        code = group = "kitapyurdu"
        def collect(self, t):
            return [proof(self.code, self.group, t, book(title=f'Blue Lock Cilt {t["volume_number"]}'))]
    class InterruptedSource(Source):
        def collect(self, t):
            first_worker.stop_event.set()
            return super().collect(t)
    first_worker = IsbnAuditWorker(factory, source_factory=lambda: (None, [InterruptedSource()]))
    first_worker.run_pending()
    db_session.expire_all()
    first = db_session.scalar(select(IsbnReview).order_by(IsbnReview.volume_id))
    assert db_session.get(IsbnAuditRun, run.id).processed == 1
    args = dict(admin_id=1, volume_id=first.volume_id, result_id=first.result_id,
                version=first.version, action="KEEP", reason="Kaydı mevcut kanıtla koruyorum.")
    decide(db_session, **args)
    # Simulate an ungraceful process death with an expired owner lease.
    row = db_session.get(IsbnAuditRun, run.id)
    row.lease, row.lease_until = "dead-process", datetime.utcnow()-timedelta(seconds=1)
    db_session.commit()
    restarted = IsbnAuditWorker(factory, source_factory=lambda: (None, [Source()]))
    restarted.run_pending()
    db_session.expire_all()
    assert db_session.get(IsbnAuditRun, run.id).processed == 2
    assert db_session.get(IsbnAuditRun, run.id).status == "COMPLETED"
    assert len(list(db_session.scalars(select(IsbnAuditResult)))) == 2
    create_run(db_session, 1)
    restarted.run_pending()
    db_session.expire_all()
    assert db_session.get(IsbnReview, first.volume_id).workflow == "REVIEWED"
    assert len(list(db_session.scalars(select(IsbnReview)))) == 2
