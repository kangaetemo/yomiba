"""Publisher alias model.

Stores known spelling variants of an existing publisher. When the import
resolves a publisher name, it tries (in order): exact normalized match,
alias match, then create-new. This is the data-driven companion to the
publisher merges: merging the rows fixes existing data, aliases stop the
next import from re-spawning variant publishers and parallel series.

Aliases are data, not code: there are no hardcoded mappings in the
import logic — new variants are added by inserting rows (see the 0003
migration seed and docs/reports/task3-dry-run.md).
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class PublisherAlias(Base):
    __tablename__ = "publisher_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: Normalized (compare-key) form of a variant name, e.g. "komik seyler".
    #: Unique: one canonical target per variant spelling.
    normalized_alias: Mapped[str] = mapped_column(
        String(200), nullable=False, unique=True
    )
    #: The publisher row this alias resolves to.
    publisher_id: Mapped[int] = mapped_column(
        ForeignKey("publishers.id", ondelete="CASCADE"), nullable=False, index=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<PublisherAlias {self.normalized_alias!r} -> {self.publisher_id}>"
