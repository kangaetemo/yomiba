# Yomiba production process checklist

This document describes configuration only; it does not deploy or migrate the
existing `yomiba.db`. Backend startup automatically runs Alembic migrations.
Review a backup and the `0005_user_accounts` legacy-data mapping before ever
starting the new backend against the real database.

## Runtime

- Python 3.11+ and dependencies in `requirements.txt`.
- **Exactly one backend ASGI process / worker.** The import locks, SYNC_GATE,
  queue, catalog scheduler, and price scheduler are process-local. Use
  `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1` from `backend/`.
  If using Gunicorn, set `workers=1`. Do not use `--reload` in production and
  do not run multiple replicas. This is a process requirement, not a guard
  against separate processes on another host.
- Use persistent **local** disk for SQLite, including its `-wal` and `-shm`
  sidecars. An ephemeral or network filesystem does not meet this assumption.
- Set `APP_ENV=production`. A relative SQLite `DATABASE_URL` is then rejected
  before startup reaches the DB. Examples:

  ```text
  DATABASE_URL=sqlite:////srv/yomiba/data/yomiba.db
  DATABASE_URL=sqlite:///C:/yomiba/data/yomiba.db
  ```

  The DB target is logged without URL credentials. Backend and Alembic read
  the same `DATABASE_URL`. The DB file must already exist in production, so
  a typo cannot silently create another empty catalog. The host must make
  its directory writable. For a deliberately new database, create the empty
  file as a separate, reviewed provisioning step before first startup.
- `AUTH_COOKIE_SECURE=1` (default), `AUTH_SESSION_DAYS=30` (default),
  `BACKEND_URL=https://api.yomiba.com`, and
  `CORS_ORIGINS=https://yomiba.com` for the trusted frontend origin. Unsafe
  requests require an exact allowed `Origin`, including login and logout.
  The browser uses the frontend's same-origin `/api` rewrite. Verify that the
  proxy forwards `Origin` and `Set-Cookie`; do not trust arbitrary
  `X-Forwarded-For` values for authentication or rate limiting.
- `AUTH_DEVICE_SECRET` (long random value, set in the host's secret store)
  keeps trusted-device cookies valid across restarts.
- Startup writes an online backup (`<db>.pre-migration-<rev>-<UTC>.bak`,
  next to the DB) before applying a pending Alembic migration
  (`AUTO_MIGRATION_BACKUP=1`, default). Keep volume headroom for one DB copy.
- `PRICE_REFRESH_ENABLED=1`, `PRICE_REFRESH_INTERVAL_HOURS=12`,
  `CATALOG_SYNC_ENABLED=1`, `CATALOG_SYNC_INTERVAL_HOURS=24`,
  `IMPORT_MAX_CONCURRENT_JOBS=2`, and `IMPORT_QUEUE_CAPACITY=16` are the
  current defaults. They preserve the existing queue/scheduler behavior.

## Startup and probes

Startup validates config, checks DB access, runs Alembic to head, enables WAL
for a file SQLite DB, seeds stores, marks stale `RUNNING` imports failed,
checks local schema/catalog references, then starts the runner and schedulers.
Any failure before the runner prevents the app from becoming ready. `/health`
is public liveness; `/ready` checks the DB and Alembic head without calling
scrapers. Scheduler and queue status remain ADMIN-only.

Runtime SQLite connections enable foreign keys and a 30-second busy timeout.
File DBs use WAL; `synchronous=FULL` is retained for durability. Alembic uses
an isolated migration connection because SQLite batch table rebuilds require
special foreign-key handling. Validate the resulting schema before readiness.

## Backup and restore verification

Use the SQLite online backup API, never a plain copy of a live DB file:

```text
python db_backup.py --source C:/yomiba/data/yomiba.db --output C:/yomiba/backups/yomiba-2026-09-25.db
python restore_check.py --db C:/yomiba/backups/yomiba-2026-09-25.db
```

The backup tool refuses to overwrite its source or an existing target. Both
tools run SQLite `quick_check`, report Alembic revision and key row counts,
and reject broken CatalogSeries references. Restore is a separate manual
operation after inspecting the report. Keep backups and the local kit ZIPs out
of source and deployment artifacts; `.gitignore` is not protection when this
folder is uploaded directly without Git.

## Dependencies

`requirements.txt` specifies minimum versions, not a lockfile. This task
does not upgrade or blindly freeze the current environment. For a production
image, resolve and review a pinned artifact from a tested environment before
installation; dependency reproducibility remains an explicit release step.
