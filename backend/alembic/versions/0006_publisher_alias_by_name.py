"""Re-point the curated publisher aliases by publisher NAME, not row id.

0003 seeded ``publisher_aliases`` with hard-coded publisher ids taken from
one database (e.g. alias "gerekli seyler" -> id 2 "Gerekli Şeyler
Yayıncılık"). A database built independently (Railway staging, rebuilt
from the Mangakol catalog) numbers its publishers differently, so those
seeds could be missing or point at an unrelated publisher.

This migration touches ONLY the aliases seeded by 0003 (the same eleven
keys). For each one it looks the intended publisher up by normalized name:

* found  -> insert the alias, or update it if it points elsewhere;
* absent -> remove a seed row that points at a DIFFERENT publisher (a
  wrong mapping is worse than none; import matching also has a
  suffix-insensitive publisher-family fallback).

No other table and no user-created alias is modified. Idempotent: a
database where 0003 already produced the right mapping is left unchanged.

Revision ID: 0006_publisher_alias_by_name
Revises: 0005_user_accounts
Create Date: 2026-09-27
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0006_publisher_alias_by_name"
down_revision: str = "0005_user_accounts"
branch_labels = None
depends_on = None

# (normalized alias, normalized name of the intended publisher) — the 0003
# seeds, keyed by name instead of id.
SEEDS: list[tuple[str, str]] = [
    ("gerekli seyler", "gerekli seyler yayincilik"),
    ("komik seyler", "komikseyler yayincilik"),
    ("kurukafa yayinevi", "kurukafa"),
    ("akilcelen", "akilcelen kitaplar"),
    ("akil celen kitaplar", "akilcelen kitaplar"),
    ("kayip kita yayinlari", "kayip kita"),
    ("presstij", "presstij kitap"),
    ("prestij", "presstij kitap"),
    ("eksik parca", "eksik parca yayinlari"),
    ("penguin books", "penguin books uk"),
    ("kara karga yayinlari", "karakarga"),
]


def upgrade() -> None:
    bind = op.get_bind()
    if "publisher_aliases" not in sa.inspect(bind).get_table_names():
        return
    for alias, target_name in SEEDS:
        target = bind.execute(
            sa.text("SELECT id FROM publishers WHERE normalized_name = :n ORDER BY id LIMIT 1"),
            {"n": target_name},
        ).scalar()
        current = bind.execute(
            sa.text("SELECT publisher_id FROM publisher_aliases WHERE normalized_alias = :a"),
            {"a": alias},
        ).scalar()
        if target is not None:
            if current is None:
                bind.execute(
                    sa.text(
                        "INSERT INTO publisher_aliases (normalized_alias, publisher_id) "
                        "VALUES (:a, :p)"
                    ),
                    {"a": alias, "p": target},
                )
            elif current != target:
                bind.execute(
                    sa.text("UPDATE publisher_aliases SET publisher_id = :p WHERE normalized_alias = :a"),
                    {"a": alias, "p": target},
                )
        elif current is not None:
            bind.execute(
                sa.text("DELETE FROM publisher_aliases WHERE normalized_alias = :a"),
                {"a": alias},
            )


def downgrade() -> None:
    """Data-only correction; nothing to undo structurally."""
