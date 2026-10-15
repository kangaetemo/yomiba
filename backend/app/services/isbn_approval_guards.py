"""The sole exception to the P0 freeze: a one-use, transactional admin receipt.

The connection-local capability exists only while the approval service owns a
BEGIN IMMEDIATE transaction. The permit is inserted, consumed and removed in
that same transaction; another SQLite connection can never observe/use it.
Root access able to register functions or drop triggers remains trusted, as
with the original P0 guards. Ordinary SQL/ORM/CLI writes have no capability.
"""
from contextlib import contextmanager
from secrets import token_hex


def definitions():
    return {
        "isbn_p0_volume_update": "CREATE TRIGGER isbn_p0_volume_update BEFORE UPDATE ON volumes WHEN "
            "NEW.id IS NOT OLD.id OR NEW.series_id IS NOT OLD.series_id OR NEW.volume_number IS NOT OLD.volume_number OR "
            "(NEW.isbn IS NOT OLD.isbn AND NOT EXISTS (SELECT 1 FROM isbn_approval_permits p JOIN isbn_decisions d ON d.id=p.decision_id "
            "WHERE p.volume_id=OLD.id AND p.old_isbn IS OLD.isbn AND p.new_isbn IS NEW.isbn "
            "AND d.volume_id=OLD.id AND d.old_isbn IS OLD.isbn AND d.new_isbn IS NEW.isbn AND d.action IN ('ACCEPT','MANUAL'))) "
            "BEGIN SELECT RAISE(ABORT, 'isbn_p0_write_paused'); END",
        "isbn_review_permit_insert": "CREATE TRIGGER isbn_review_permit_insert BEFORE INSERT ON isbn_approval_permits WHEN "
            "isbn_approval_token() IS NULL OR NEW.token IS NOT isbn_approval_token() OR "
            "EXISTS(SELECT 1 FROM isbn_approval_permits) OR NOT EXISTS(SELECT 1 FROM isbn_decisions d "
            "JOIN users u ON u.id=d.admin_id JOIN isbn_reviews r ON r.volume_id=d.volume_id "
            "JOIN volumes v ON v.id=d.volume_id WHERE d.id=NEW.decision_id AND u.role='ADMIN' AND u.is_active=1 "
            "AND d.action IN ('ACCEPT','MANUAL') AND d.volume_id=NEW.volume_id AND d.old_isbn IS NEW.old_isbn "
            "AND d.new_isbn IS NEW.new_isbn AND v.isbn IS NEW.old_isbn AND r.version=d.review_version AND r.result_id=d.result_id) "
            "BEGIN SELECT RAISE(ABORT, 'isbn_approval_required'); END",
        "isbn_review_permit_update": "CREATE TRIGGER isbn_review_permit_update BEFORE UPDATE ON isbn_approval_permits "
            "BEGIN SELECT RAISE(ABORT, 'isbn_approval_required'); END",
        "isbn_review_permit_consume": "CREATE TRIGGER isbn_review_permit_consume AFTER UPDATE OF isbn ON volumes WHEN NEW.isbn IS NOT OLD.isbn "
            "BEGIN DELETE FROM isbn_approval_permits WHERE volume_id=NEW.id; END",
        "isbn_review_decision_insert": "CREATE TRIGGER isbn_review_decision_insert BEFORE INSERT ON isbn_decisions WHEN "
            "isbn_approval_token() IS NULL OR NOT EXISTS(SELECT 1 FROM users WHERE id=NEW.admin_id AND role='ADMIN' AND is_active=1) "
            "BEGIN SELECT RAISE(ABORT, 'isbn_approval_required'); END",
    }


def history_definitions():
    result = {}
    for table in ("isbn_audit_results", "isbn_decisions"):
        for event in ("UPDATE", "DELETE"):
            name = f"{table}_{event.lower()}"
            result[name] = f"CREATE TRIGGER {name} BEFORE {event} ON {table} BEGIN SELECT RAISE(ABORT, 'isbn_history_immutable'); END"
        name = f"{table}_replace"
        unique = " OR (run_id=NEW.run_id AND volume_id=NEW.volume_id)" if table == "isbn_audit_results" else ""
        result[name] = (f"CREATE TRIGGER {name} BEFORE INSERT ON {table} WHEN EXISTS(SELECT 1 FROM {table} WHERE id=NEW.id{unique}) "
                        "BEGIN SELECT RAISE(ABORT, 'isbn_history_immutable'); END")
    return result


@contextmanager
def approval_capability(connection):
    token = token_hex(32)
    if not connection.in_transaction:
        raise RuntimeError("Approval requires an exclusive write transaction")
    connection.create_function("isbn_approval_token", 0, lambda: token)
    try:
        yield token
    finally:
        # Never return a privileged connection to the pool, even after rollback.
        connection.create_function("isbn_approval_token", 0, lambda: None)
