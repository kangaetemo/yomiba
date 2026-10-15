"""Durable, resumable ISBN audit. Network work never holds a write transaction."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from threading import Event, Thread
from uuid import uuid4

from sqlalchemy import exists, select, text, update
from sqlalchemy.orm import joinedload
from ..utils import naive_utcnow

from ..models import (CatalogSeries, IsbnAuditItem, IsbnAuditResult, IsbnAuditRun,
                      IsbnReview, Series, Volume)
from .isbn_identity import digest, eligible, evaluate, snapshot
from .isbn_sources import collect_sources, default_sources

logger = logging.getLogger("yomiba.isbn_audit")


class AuditConflict(ValueError):
    pass


def volume_query():
    return select(Volume).options(joinedload(Volume.series).joinedload(Series.publisher))


def tracked():
    return exists().where(CatalogSeries.series_id == Volume.series_id)


def create_run(session, admin_id: int | None, *, volume_id: int | None = None, due_only=False):
    session.rollback()
    session.execute(text("BEGIN IMMEDIATE"))
    try:
        if session.scalar(select(IsbnAuditRun.id).where(IsbnAuditRun.status.in_(["RUNNING", "PAUSED"]))):
            raise AuditConflict("Açık bir tarama var. Önce onu sürdürün veya tamamlayın.")
        query = select(Volume.id).where(tracked(), Volume.catalog_present.is_not(False))
        if volume_id is not None:
            query = query.where(Volume.id == volume_id)
        if due_only:
            query = query.outerjoin(IsbnReview, Volume.id == IsbnReview.volume_id).where(
                (IsbnReview.volume_id.is_(None)) | (IsbnReview.next_check_at <= naive_utcnow()))
        ids = list(session.scalars(query.order_by(Volume.id)))
        if not ids:
            if volume_id is not None:
                raise AuditConflict("Cilt etkin katalogda bulunamadı.")
            session.rollback()
            return None
        run = IsbnAuditRun(requested_by=admin_id, status="RUNNING", total=len(ids), processed=0, errors=0)
        session.add(run); session.flush()
        session.add_all(IsbnAuditItem(run_id=run.id, volume_id=id, completed=False) for id in ids)
        session.commit()
        return run
    except Exception:
        session.rollback()
        raise


def control_run(session, run_id: int, action: str):
    session.rollback()
    session.execute(text("BEGIN IMMEDIATE"))
    try:
        run = session.get(IsbnAuditRun, run_id)
        if not run or run.status not in {"RUNNING", "PAUSED"}:
            raise AuditConflict("Bu tarama artık açık değil.")
        if action == "stop":
            run.status, run.finished_at = "CANCELLED", naive_utcnow()
        else:
            run.status = "PAUSED" if action == "pause" else "RUNNING"
        session.commit()
        return run
    except Exception:
        session.rollback()
        raise


def evidence_signature(evidence):
    return digest([{k: v for k, v in e.items() if k != "checked_at" and not (e["status"] == "ERROR" and k == "reason")} for e in evidence])


class IsbnAuditWorker:
    def __init__(self, session_factory, source_factory=default_sources, *, interval=30):
        self.sessions, self.source_factory, self.interval = session_factory, source_factory, interval
        self.stop_event = Event()
        self.wake_event = Event()
        self.thread = None

    def start(self):
        self.thread = Thread(target=self._loop, name="isbn-audit", daemon=True)
        self.thread.start()

    def wake(self):
        self.wake_event.set()

    def stop(self, timeout=5):
        self.stop_event.set(); self.wake_event.set()
        if self.thread: self.thread.join(timeout)

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                self.run_pending()
                # Daily unresolved / weekly verified; the first complete scan
                # is explicitly started by admin. New releases join due runs.
                with self.sessions() as session:
                    has_scan = session.scalar(select(IsbnAuditRun.id).where(IsbnAuditRun.status == "COMPLETED").limit(1))
                    open_run = session.scalar(select(IsbnAuditRun.id).where(IsbnAuditRun.status.in_(["RUNNING", "PAUSED"])).limit(1))
                    if has_scan and not open_run:
                        create_run(session, None, due_only=True)
            except Exception:
                logger.exception("ISBN audit worker failed; progress retained for retry")
            self.wake_event.wait(self.interval)
            self.wake_event.clear()

    def claim(self):
        with self.sessions() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            now = naive_utcnow()
            run = session.scalar(select(IsbnAuditRun).where(IsbnAuditRun.status == "RUNNING",
                (IsbnAuditRun.lease_until.is_(None)) | (IsbnAuditRun.lease_until < now)).order_by(IsbnAuditRun.id))
            if not run:
                session.rollback(); return None
            token = uuid4().hex
            run.lease, run.lease_until = token, now + timedelta(minutes=10)
            run_id = run.id
            session.commit()
            return run_id, token

    def run_pending(self):
        claimed = self.claim()
        if not claimed: return
        run_id, token = claimed
        client = None
        lease_stop = Event()
        def heartbeat():
            while not lease_stop.wait(30):
                try:
                    with self.sessions() as session:
                        session.execute(update(IsbnAuditRun).where(IsbnAuditRun.id == run_id,
                            IsbnAuditRun.lease == token).values(lease_until=naive_utcnow()+timedelta(minutes=10)))
                        session.commit()
                except Exception:
                    logger.exception("ISBN audit lease heartbeat failed")
        lease_thread = Thread(target=heartbeat, name="isbn-audit-lease", daemon=True)
        lease_thread.start()
        try:
            client, sources = self.source_factory()
            while not self.stop_event.is_set():
                with self.sessions() as session:
                    run = session.get(IsbnAuditRun, run_id)
                    if run.status != "RUNNING" or run.lease != token: return
                    item = session.scalar(select(IsbnAuditItem).where(IsbnAuditItem.run_id == run_id,
                        IsbnAuditItem.completed.is_(False)).order_by(IsbnAuditItem.volume_id).limit(1))
                    if not item:
                        run.status, run.finished_at, run.error = "COMPLETED", naive_utcnow(), None
                        session.commit(); return
                    volume_id = item.volume_id
                    target = snapshot(session.scalar(volume_query().where(Volume.id == volume_id)))
                evidence = collect_sources(target, sources) if eligible(target) else []
                status, proposed, reason = evaluate(target, evidence)
                with self.sessions() as session:
                    session.execute(text("BEGIN IMMEDIATE"))
                    run = session.get(IsbnAuditRun, run_id)
                    if run.lease != token: return
                    current = snapshot(session.scalar(volume_query().where(Volume.id == volume_id)))
                    if digest(current) != digest(target):
                        # Do not attach old evidence to a changed catalogue row.
                        run.lease_until = naive_utcnow() + timedelta(minutes=10)
                        session.commit(); continue
                    result = IsbnAuditResult(run_id=run_id, volume_id=volume_id, snapshot=target,
                        snapshot_hash=digest(target), status=status, proposed_isbn=proposed, reason=reason,
                        evidence=evidence, evidence_hash=evidence_signature(evidence))
                    session.add(result); session.flush()
                    review = session.get(IsbnReview, volume_id)
                    workflow = "REVIEWED" if status in {"VERIFIED", "SKIPPED_UPCOMING"} else "REVIEW_PENDING"
                    next_check = naive_utcnow() + timedelta(days=7 if status == "VERIFIED" else 1)
                    if review:
                        old = session.get(IsbnAuditResult, review.result_id)
                        if old.snapshot_hash == result.snapshot_hash and old.evidence_hash == result.evidence_hash:
                            workflow = review.workflow
                            next_check = max(next_check, review.next_check_at)
                        review.result_id, review.version = result.id, review.version + 1
                        review.workflow, review.next_check_at = workflow, next_check
                    else:
                        session.add(IsbnReview(volume_id=volume_id, result_id=result.id, workflow=workflow,
                                               version=1, next_check_at=next_check))
                    session.get(IsbnAuditItem, (run_id, volume_id)).completed = True
                    run.processed += 1
                    run.errors += int(any(e["status"] == "ERROR" for e in evidence))
                    run.lease_until = naive_utcnow() + timedelta(minutes=10)
                    session.commit()
        except Exception:
            with self.sessions() as session:
                run = session.get(IsbnAuditRun, run_id)
                if run and run.lease == token:
                    run.error = "Tarama kesildi; kaydedilen ilerlemeden yeniden denenecek."
                    session.commit()
            raise
        finally:
            lease_stop.set()
            lease_thread.join(timeout=5)
            if client: client.close()
            with self.sessions() as session:
                run = session.get(IsbnAuditRun, run_id)
                if run and run.lease == token:
                    run.lease, run.lease_until = None, None
                    session.commit()
