"""The only authorized ISBN writer; revalidate immutable, fresh evidence atomically."""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from ..models import IsbnAuditResult, IsbnDecision, IsbnReview, User, Volume
from ..utils import naive_utcnow
from .isbn_audit import tracked, volume_query
from .isbn_identity import canonical_isbn, digest, eligible, evaluate, snapshot
from .isbn_audit import evidence_signature
from .isbn_approval_guards import approval_capability
from .isbn_sources import proof, source_groups


class DecisionError(ValueError):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def decide(session, *, admin_id, volume_id, version, result_id, action, reason, isbn=None):
    if len(reason.strip()) < 3:
        raise DecisionError("Karar gerekçesini yazın.", 422)
    if action not in {"KEEP", "DEFER", "ACCEPT", "MANUAL"}:
        raise DecisionError("Geçersiz karar.", 422)
    session.rollback()
    session.execute(text("BEGIN IMMEDIATE"))
    try:
        admin = session.get(User, admin_id)
        if not admin or not admin.is_active or admin.role != "ADMIN":
            raise DecisionError("Yönetici yetkisi gerekiyor.", 403)
        review = session.get(IsbnReview, volume_id)
        result = session.get(IsbnAuditResult, result_id)
        volume = session.scalar(volume_query().where(Volume.id == volume_id, tracked()))
        if not review or review.version != version or review.result_id != result_id:
            raise DecisionError("Bu inceleme değişti. Güncel kaydı açıp yeniden karar verin.")
        if not volume or not result or result.volume_id != volume_id or digest(snapshot(volume)) != result.snapshot_hash:
            raise DecisionError("Katalog bilgileri değişti. Önce bu cildi yeniden denetleyin.")
        new_isbn = volume.isbn
        if action in {"ACCEPT", "MANUAL"}:
            new_isbn = canonical_isbn(isbn if action == "MANUAL" else result.proposed_isbn)
            if new_isbn is None:
                raise DecisionError("Geçerli bir ISBN-10 veya ISBN-13 gerekiyor; boşaltma ve taşıma bu işlemde desteklenmiyor.", 422)
            validate_evidence(result, snapshot(volume), new_isbn)
            for other_id, other_isbn in session.execute(select(Volume.id, Volume.isbn).where(Volume.id != volume_id, Volume.isbn.is_not(None))):
                if canonical_isbn(other_isbn) == new_isbn:
                    raise DecisionError(f"Bu ISBN başka bir cilde ait (kayıt {other_id}). Kayıtlar birleştirilmedi veya taşınmadı.")
        decision = IsbnDecision(volume_id=volume_id, result_id=result_id, review_version=version,
            admin_id=admin_id, action=action, old_isbn=volume.isbn, new_isbn=new_isbn,
            reason=reason.strip(), snapshot_hash=result.snapshot_hash, evidence_hash=result.evidence_hash)
        connection = session.connection().connection.driver_connection
        with approval_capability(connection) as token:
            session.add(decision); session.flush()
            if new_isbn != volume.isbn:
                session.execute(text("INSERT INTO isbn_approval_permits (volume_id,decision_id,old_isbn,new_isbn,token) "
                                     "VALUES (:volume,:decision,:old,:new,:token)"),
                                dict(volume=volume_id, decision=decision.id, old=volume.isbn, new=new_isbn, token=token))
                volume.isbn = new_isbn
                session.flush()
                if connection.execute("SELECT 1 FROM isbn_approval_permits").fetchone():
                    raise RuntimeError("Approval permit was not consumed")
            review.version += 1
            review.workflow = "REVIEW_PENDING" if action == "DEFER" else "REVIEWED"
            review.next_check_at = naive_utcnow() if action in {"ACCEPT", "MANUAL"} else naive_utcnow() + timedelta(days=1 if action == "DEFER" else 7)
            session.flush()
        session.commit()
        return decision
    except IntegrityError:
        session.rollback()
        raise DecisionError("ISBN benzersizliği veya güvenli onay kontrolü başarısız oldu; katalog değişmedi.") from None
    except Exception:
        session.rollback()
        raise


def validate_evidence(result, target, new_isbn):
    if not eligible(target):
        raise DecisionError("Bu cildin yayımlandığı doğrulanmadı.")
    if digest(result.snapshot) != result.snapshot_hash or evidence_signature(result.evidence) != result.evidence_hash:
        raise DecisionError("Kanıt bütünlüğü doğrulanamadı; yeniden denetleyin.")
    now = naive_utcnow()
    if not timedelta(0) <= now - result.checked_at <= timedelta(hours=24):
        raise DecisionError("Kanıtlar 24 saatten eski; cildi yeniden denetleyin.")
    groups, checked = source_groups(), []
    for item in result.evidence:
        source = item.get("source")
        if source == "mangakol": continue
        if source not in groups or item.get("independence_group") != groups[source]:
            raise DecisionError("Kaynak bağımsızlık bilgisi değişti; yeniden denetleyin.")
        if item["status"] in {"MATCH", "MISMATCH", "NO_ISBN"}:
            try:
                time = datetime.fromisoformat(item["checked_at"])
                if time.tzinfo: time = time.astimezone(timezone.utc).replace(tzinfo=None)
            except (KeyError, ValueError):
                raise DecisionError("Kanıtın kontrol zamanı eksik; yeniden denetleyin.") from None
            if not timedelta(0) <= now - time <= timedelta(hours=24):
                raise DecisionError("Kaynak kanıtı güncel değil; yeniden denetleyin.")
            raw = {key: item.get(key) for key in ("title", "publisher", "language", "binding", "url", "raw_isbns")}
            domains = {"kitapyurdu": {"www.kitapyurdu.com"}, "bkm": {"www.bkmkitap.com", "bkmkitap.com"},
                       "pandora": {"www.pandora.com.tr"}, "dr": {"www.dr.com.tr"}}
            parsed = urlsplit(raw["url"] or "")
            if parsed.scheme != "https" or parsed.hostname not in domains[source] or not isinstance(raw["raw_isbns"], list):
                raise DecisionError("Kanıtın ürün bağlantısı eksik.")
            checked.append(proof(source, groups[source], target, raw))
        else:
            checked.append(item)
    _, proposed, _ = evaluate(target, checked)
    # Current matching ISBN evaluates VERIFIED; missing/different ISBN may
    # evaluate MISSING/CONFLICT, but only a clean two-source consensus has a
    # proposed value. Actual contradictions never do.
    if proposed != new_isbn:
        raise DecisionError("Bu ISBN için aynı fiziksel baskıyı doğrulayan iki bağımsız, çelişkisiz kanıt yok.")
