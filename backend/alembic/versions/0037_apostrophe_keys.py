"""Comparison keys without the apostrophe gap.

normalize_text used to turn "Bahçe'nin" into "bahce nin"; it now gives
"bahcenin", the same key as the spelling without an apostrophe that stores
and Mangakol also use. Recompute the stored keys whose source text still has
an apostrophe. Series slugs (public URLs) are left as they are. A row whose
new key is already taken keeps its old key (logged): a unique constraint
must never fail the deploy. ``series.original_title`` keeps only the old key
(the raw text is not stored); the next catalog sync rewrites it.
"""
import logging

from alembic import op
import sqlalchemy as sa

revision = "0037_apostrophe_keys"
down_revision = "0036_special_sets"
branch_labels = depends_on = None

log = logging.getLogger("alembic.runtime.migration")

_MARKS = ("'", "’", "‘", "ʼ", "`")


def _has_mark(column: str) -> str:
    return "(" + " OR ".join(f"instr({column}, :m{i}) > 0" for i in range(len(_MARKS))) + ")"


def upgrade():
    from app.normalization.text import normalize_text

    bind = op.get_bind()
    marks = {f"m{i}": m for i, m in enumerate(_MARKS)}

    def recompute(table, key_col, text_col, scope_col=None):
        cols = f"id, {text_col}, {key_col}" + (f", {scope_col}" if scope_col else "")
        rows = bind.execute(sa.text(
            f"SELECT {cols} FROM {table} WHERE {text_col} IS NOT NULL AND {_has_mark(text_col)}"
        ), marks).all()
        for row in rows:
            new = normalize_text(row[1])
            if not new or new == row[2]:
                continue
            clash_sql = f"SELECT 1 FROM {table} WHERE {key_col} = :new AND id != :id"
            params = {"new": new, "id": row[0]}
            if scope_col:
                clash_sql += f" AND {scope_col} = :scope"
                params["scope"] = row[3]
            if bind.execute(sa.text(clash_sql), params).first():
                log.warning("0037: %s %s keeps %r (%r is taken)", table, row[0], row[2], new)
                continue
            bind.execute(sa.text(f"UPDATE {table} SET {key_col} = :new WHERE id = :id"), params)

    recompute("series", "normalized_title", "title", scope_col="publisher_id")
    recompute("publishers", "normalized_name", "name")
    recompute("import_records", "normalized_query", "last_query")


def downgrade():
    raise RuntimeError("ISBN protection: no in-place downgrade past 0018; restore the pre-migration backup")
