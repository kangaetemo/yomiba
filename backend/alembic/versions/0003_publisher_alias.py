"""publisher_aliases: known spelling variants of existing publishers.

Adds the alias table used by ``ImportService._resolve_publisher``
(exact match -> alias -> create-new) and seeds the variants discovered by
the 2026-09-14 data-quality pass (docs/reports/task3-dry-run.md, task 3).

Seeding is guarded with ``WHERE EXISTS`` on the target publisher so the
migration is safe on a brand-new database (no publisher rows yet) and
idempotent on a production database (already-seeded rows are skipped).
Alias keys are normalized with the same rules as ``normalize_publisher``.

Revision ID: 0003_publisher_alias
Revises: 0002_original_title
Create Date: 2026-09-14
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003_publisher_alias"
down_revision: str = "0002_original_title"
branch_labels = None
depends_on = None

# (normalized variant name, target publisher id)
# Variants found in production data (2026-09-14 pass):
#   Gerekli Şeyler        -> 2   Gerekli Şeyler Yayıncılık
#   Komik Şeyler          -> 204 Komikşeyler Yayıncılık
#   Kurukafa Yayınevi     -> 30  Kurukafa
#   Akılçelen             -> 633 Akılçelen Kitaplar
#   Akıl Çelen Kitaplar   -> 633 Akılçelen Kitaplar
#   Kayıp Kıta Yayınları  -> 11  Kayıp Kıta
#   Presstij              -> 239 Presstij Kitap
#   Prestij               -> 239 Presstij Kitap
#   Eksik Parça           -> 133 Eksik Parça Yayınları
#   Penguin Books         -> 433 Penguin Books UK
#   Kara Karga Yayınları  -> 713 Karakarga (verified same company, 2026-09-14)
SEEDS: list[tuple[str, int]] = [
    ("gerekli seyler", 2),
    ("komik seyler", 204),
    ("kurukafa yayinevi", 30),
    ("akilcelen", 633),
    ("akil celen kitaplar", 633),
    ("kayip kita yayinlari", 11),
    ("presstij", 239),
    ("prestij", 239),
    ("eksik parca", 133),
    ("penguin books", 433),
    ("kara karga yayinlari", 713),
]


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "publisher_aliases" not in inspector.get_table_names():
        op.create_table(
            "publisher_aliases",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("normalized_alias", sa.String(length=200), nullable=False),
            sa.Column(
                "publisher_id",
                sa.Integer(),
                sa.ForeignKey("publishers.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.UniqueConstraint("normalized_alias", name="uq_publisher_aliases_alias"),
        )
        op.create_index(
            "ix_publisher_aliases_publisher_id",
            "publisher_aliases",
            ["publisher_id"],
        )
    # Idempotent seed: skip variants whose target publisher does not exist
    # (fresh database) or that are already recorded.
    existing = {
        row[0]
        for row in bind.execute(sa.text("SELECT normalized_alias FROM publisher_aliases"))
    }
    for alias, publisher_id in SEEDS:
        if alias in existing:
            continue
        bind.execute(
            sa.text(
                "INSERT INTO publisher_aliases (normalized_alias, publisher_id) "
                "SELECT :alias, :pid "
                "WHERE EXISTS (SELECT 1 FROM publishers WHERE id = :pid)"
            ),
            {"alias": alias, "pid": publisher_id},
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_publisher_aliases_publisher_id", table_name="publisher_aliases")
    op.drop_table("publisher_aliases")
