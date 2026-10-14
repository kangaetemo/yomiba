"""Persist sync completion/retry times beside the mounted SQLite database."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from sqlalchemy.engine import make_url

from ..config import get_settings

logger = logging.getLogger("yomiba.catalog.state")


def state_path() -> Path | None:
    url = make_url(get_settings().database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    db = Path(url.database).resolve()
    return db.with_name(db.name + ".catalog-state.json") if db.is_file() else None


def read_state() -> dict:
    path = state_path()
    if path is None:
        return {}
    try:
        result = json.loads(path.read_text())
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(state: dict) -> None:
    path = state_path()
    if path is None:
        return
    temp_path = None
    try:
        with NamedTemporaryFile(mode="w", dir=path.parent, prefix=path.name + ".", delete=False) as stream:
            temp_path = Path(stream.name)
            json.dump(state, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    except OSError:
        logger.exception("catalog sync state could not be persisted")
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def record_start() -> None:
    state = read_state()
    state.update(last_attempt_at=datetime.now(timezone.utc).isoformat(), in_progress=True)
    _write(state)


def record_finish(summary: dict) -> None:
    state = read_state()
    state.update(last=summary, in_progress=False)
    if summary.get("status") == "success":
        state["last_success_at"] = summary["finished_at"]
    _write(state)


def next_delay(interval_seconds: float, *, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    state = read_state()
    last = state.get("last")
    last = last if isinstance(last, dict) else {}
    retry = state.get("in_progress") or last.get("status") == "failed"
    value = state.get("last_attempt_at") if retry else state.get("last_success_at")
    if not value:
        return 0.0  # No proven completion: bootstrap/catch up after deployment.
    try:
        stamp = datetime.fromisoformat(value)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        elapsed = max(0.0, (now - stamp).total_seconds())
    except (TypeError, ValueError):
        return 0.0
    budget = min(interval_seconds, 3600.0) if retry else interval_seconds
    return max(0.0, budget - elapsed)
