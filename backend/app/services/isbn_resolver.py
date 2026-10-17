"""Decide each catalog volume's ISBN from all evidence, and log every change.

Evidence for a volume V:

* ``V.catalog_isbn`` — what Mangakol lists. Mangakol is sometimes wrong:
  it gave Blue Lock 28 and 29 the same ISBN, and Happiness 6 the ISBN of
  Happiness 5. A catalog ISBN that Mangakol also lists on a *different*
  book (another number, another work) is a **source duplicate** and is
  never written automatically.
* Store votes — ``StoreObservation`` rows whose *title* points to V (the
  ISBN is ignored when the title target is computed), counted per ISBN as
  distinct stores.

Rules (in order):

1. An admin decision (``isbn_source == "admin"``) is never overwritten.
2. **Store consensus**: an ISBN shown by at least two stores on products
   titled as V, with no other ISBN reaching two stores, wins — unless a
   usable catalog ISBN has store support of its own (then it is an issue).
3. **Catalog**: a usable catalog ISBN (valid, Turkish, not a source
   duplicate) fills an empty ISBN, or replaces the current one when stores
   back the catalog and none back the current value.
4. Anything else contradictory is recorded in ``isbn_issues``.

Applying an ISBN that another volume W holds:

* W is another edition of the same book (same number, sibling catalog
  entry ``<slug>~<format>``): publishers print limited/variant books under
  the regular ISBN, so V gets it as a **shared** ISBN.
* W has no store vote for it (and is not an admin decision): the ISBN
  moves from W to V (W re-resolves from its own evidence).
* Otherwise both claim it: an issue, nothing changes.

Upcoming volumes are not checked: a book without a release has no ISBN yet.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CatalogSeries, IsbnChange, IsbnIssue, SharedIsbn, Store, StoreObservation, Volume
from ..normalization.isbn import catalog_book_isbn
from ..utils import utcnow
from .catalog_service import other_editions

logger = logging.getLogger("yomiba.isbn")

#: Store observations older than this no longer vote (stores fix listings).
VOTE_WINDOW = timedelta(days=90)
CONSENSUS_STORES = 2
#: Stores that evidently share one product feed count as ONE vote:
#: Gerekli Şeyler and Büyülü Dükkan carry the same swapped "Stok Kodu"
#: (Yubooh Uyurken 1/2), Kitap Sepeti and İstanbul Kitapçısı reuse the same
#: product pages (2026-10-17). Two copies of one error are not consensus.
VOTE_GROUPS = {
    "gerekliseyler": "ideasoft-gs", "buyuludukkan": "ideasoft-gs",
    "kitapsepeti": "tsoft-ks", "istanbulkitapcisi": "tsoft-ks",
}


def log_change(session: Session, volume_id: int, old: str | None, new: str | None,
               source: str, reason: str, user_id: int | None = None) -> None:
    session.add(IsbnChange(volume_id=volume_id, old_isbn=old, new_isbn=new, source=source,
                           reason=reason[:500], user_id=user_id, created_at=utcnow()))


def set_isbn(session: Session, volume: Volume, isbn: str | None, source: str, reason: str,
             user_id: int | None = None) -> None:
    """Change ``volume.isbn`` and log it. The caller frees the ISBN first."""
    if volume.isbn == isbn:
        return
    log_change(session, volume.id, volume.isbn, isbn, source, reason, user_id)
    logger.info("isbn: volume %s %s -> %s (%s: %s)", volume.id, volume.isbn, isbn, source, reason)
    volume.isbn = isbn
    volume.isbn_source = source if isbn else None
    if isbn is None:
        # Freed by a move: the volume re-resolves from its own evidence.
        session.info.setdefault("isbn_freed", []).append(volume.id)
    session.flush()


def add_shared(session: Session, volume: Volume, isbn: str, source: str, reason: str,
               user_id: int | None = None) -> bool:
    if session.scalar(select(SharedIsbn.id).where(SharedIsbn.isbn == isbn, SharedIsbn.volume_id == volume.id)):
        return False
    session.add(SharedIsbn(isbn=isbn, volume_id=volume.id, source=source, created_at=utcnow()))
    log_change(session, volume.id, None, isbn, "shared", reason, user_id)
    session.flush()
    return True


def siblings(session: Session, volume: Volume) -> list[Volume]:
    """The same-numbered volumes of the other editions of ``volume``'s book."""
    ids = [s.id for s in other_editions(session, volume.series_id)]
    if not ids:
        return []
    return list(session.scalars(select(Volume).where(
        Volume.series_id.in_(ids), Volume.volume_number == volume.volume_number)))


def is_sibling(session: Session, a: Volume, b: Volume) -> bool:
    return a.id != b.id and a.volume_number == b.volume_number and any(v.id == b.id for v in siblings(session, a))


def isbn_holders(session: Session, isbn: str) -> list[Volume]:
    """Owner (``Volume.isbn``) first, then volumes sharing the ISBN."""
    owner = session.scalar(select(Volume).where(Volume.isbn == isbn))
    shared = list(session.scalars(select(Volume).join(SharedIsbn, SharedIsbn.volume_id == Volume.id)
                                  .where(SharedIsbn.isbn == isbn)))
    return ([owner] if owner else []) + [v for v in shared if not owner or v.id != owner.id]


def store_votes(session: Session, volume_id: int) -> dict[str, int]:
    """ISBN -> number of independent stores (see ``VOTE_GROUPS``) whose
    product title points to the volume."""
    since = utcnow() - VOTE_WINDOW
    groups: dict[str, set[str]] = defaultdict(set)
    for code, isbn, seen in session.execute(
        select(Store.code, StoreObservation.isbn, StoreObservation.last_seen)
        .join(Store, Store.id == StoreObservation.store_id)
        .where(StoreObservation.title_volume_id == volume_id, StoreObservation.isbn.is_not(None))
    ):
        if seen is not None and seen.tzinfo is None:
            seen = seen.replace(tzinfo=since.tzinfo)
        if catalog_book_isbn(isbn) and (seen is None or seen >= since):
            groups[isbn].add(VOTE_GROUPS.get(code, code))
    return {isbn: len(ids) for isbn, ids in groups.items()}


def isbn_settled(session: Session, volume: Volume) -> bool:
    """The volume's ISBN is certain: an admin set it, or it is the one its
    own Mangakol page lists (and Mangakol gives no other book the same)."""
    current = catalog_book_isbn(volume.isbn)
    if current is None:
        return False
    if volume.isbn_source == "admin":
        return True
    return current == catalog_book_isbn(volume.catalog_isbn) and not catalog_duplicates(session, volume, current)


def catalog_duplicates(session: Session, volume: Volume, isbn: str) -> list[Volume]:
    """Other catalog volumes Mangakol lists with the same ISBN that are NOT
    another edition of the same book (= a source error).

    A duplicate is explained — and ignored — when that other volume already
    has a different valid ISBN: Mangakol is wrong about *that* volume (Blue
    Lock 29 decided as …633 by the stores frees Mangakol's …626 for 28;
    Happiness 6 holding …324050 frees …360492 for Happiness 5)."""
    others = session.scalars(select(Volume).where(
        Volume.catalog_isbn == isbn, Volume.id != volume.id, Volume.catalog_present.is_not(False)))
    return [w for w in others if not is_sibling(session, volume, w)
            and not (catalog_book_isbn(w.isbn) and w.isbn != isbn)]


def _issue(session: Session, volume: Volume, kind: str, **detail) -> None:
    row = session.get(IsbnIssue, volume.id)
    if row is None:
        session.add(IsbnIssue(volume_id=volume.id, kind=kind, detail=detail, updated_at=utcnow()))
    elif row.kind != kind or row.detail != detail:
        row.kind, row.detail, row.updated_at = kind, detail, utcnow()


def _clear_issue(session: Session, volume: Volume) -> None:
    row = session.get(IsbnIssue, volume.id)
    if row is not None:
        session.delete(row)


def _in_catalog(session: Session, volume: Volume) -> bool:
    return session.scalar(select(CatalogSeries.series_id).where(CatalogSeries.series_id == volume.series_id).limit(1)) is not None


def _is_identity(session: Session, volume: Volume) -> bool:
    """A real catalog book. Legacy "Cilt -1" phantoms, retired rows and
    store-era series outside the catalog are not: their ISBN may be taken."""
    return volume.volume_number >= 0 and volume.catalog_present is not False and _in_catalog(session, volume)


def resolve(session: Session, volume: Volume) -> str | None:
    """Apply the rules to one volume. Returns what happened ("stores",
    "catalog", "shared", "moved", "issue") or None. Flushes, never commits."""
    if volume.volume_number < 0 or volume.catalog_present is False or volume.catalog_released is False:
        return None
    if not _in_catalog(session, volume):
        return None
    if volume.isbn_source == "admin":
        _clear_issue(session, volume)
        return None

    catalog = catalog_book_isbn(volume.catalog_isbn)
    duplicates = catalog_duplicates(session, volume, catalog) if catalog else []
    usable_catalog = catalog if catalog and not duplicates else None
    votes = store_votes(session, volume.id)
    strong = [isbn for isbn, n in votes.items() if n >= CONSENSUS_STORES]

    target = source = reason = None
    if len(strong) == 1 and usable_catalog in (None, strong[0]):
        # Stores decide when Mangakol has no usable ISBN (none, or listed on
        # another book too) or agrees. A usable, different Mangakol ISBN is
        # counter-evidence: stores alone never override it (Yubooh Uyurken:
        # two stores' swapped codes vs. Mangakol + the publisher's
        # distributor) — that is an issue for an admin.
        target, source = strong[0], "stores"
        reason = f"{votes[target]} bağımsız mağaza bu cilt başlığıyla bu ISBN'i gösteriyor"
        if catalog and catalog != target:
            reason += f" (Mangakol'daki {catalog} başka bir kitapta da var)"
    elif len(strong) > 1:
        if usable_catalog in strong and catalog_book_isbn(volume.isbn) == usable_catalog:
            # Mangakol and stores back the current ISBN; the other one is
            # another print or edition (Soichi Bez Cilt, Kara Paradoks) whose
            # products never attach here (``isbn_conflict``). Nothing to decide.
            _clear_issue(session, volume)
            return None
        _issue(session, volume, "stores_disagree", votes=votes, catalog=catalog)
        return "issue"
    elif usable_catalog and not strong:
        # A current value that is no Turkish book ISBN (foreign edition, store
        # barcode, bad check digit) counts as empty.
        current = catalog_book_isbn(volume.isbn)
        if current in (None, usable_catalog) or (votes.get(usable_catalog, 0) >= 1 and votes.get(current, 0) == 0):
            target, source, reason = usable_catalog, "catalog", "Mangakol katalog ISBN'i"
        else:
            _issue(session, volume, "catalog_differs", current=volume.isbn, catalog=catalog, votes=votes)
            return "issue"
    elif strong and usable_catalog:
        _issue(session, volume, "stores_vs_catalog", votes=votes, catalog=catalog)
        return "issue"
    else:
        if duplicates:
            _issue(session, volume, "catalog_duplicate", catalog=catalog,
                   also_on=[dict(volume_id=w.id, series_id=w.series_id, volume_number=w.volume_number) for w in duplicates],
                   current=volume.isbn, votes=votes)
            return "issue"
        _clear_issue(session, volume)
        return None

    return _apply(session, volume, target, source, reason)


def _apply(session: Session, volume: Volume, target: str, source: str, reason: str) -> str | None:
    if volume.isbn == target:
        _clear_issue(session, volume)
        return None
    for holder in isbn_holders(session, target):
        if holder.id == volume.id:
            continue
        if is_sibling(session, volume, holder):
            holder_catalog = catalog_book_isbn(holder.catalog_isbn)
            if holder_catalog == target or (source == "stores" and holder_catalog is None):
                # Both editions' pages list it (Afro Samuray: regular and
                # "444 Adet Limitli" under one ISBN), or stores prove it for
                # this edition too: a shared ISBN. Never taken from the sibling.
                _clear_issue(session, volume)
                return "shared" if add_shared(session, volume, target, source, f"{reason}; baskılar ortak ISBN") else None
            if (holder_catalog and holder.isbn_source != "admin"
                    and not isbn_holders(session, holder_catalog)):
                # The pages list different ISBNs (Soichi: regular …101, Bez
                # Cilt …118) and the sibling holds this edition's one (an old
                # title match): each edition takes its own page's ISBN.
                set_isbn(session, holder, None, "moved", f"ISBN {target} baskı cildi {volume.id}'e taşındı")
                set_isbn(session, holder, holder_catalog, "catalog", "kendi Mangakol sayfasındaki ISBN")
                _clear_issue(session, holder)
                break
            _issue(session, volume, "isbn_claimed", isbn=target, holder=holder.id,
                   holder_number=holder.volume_number, reason=reason)
            return "issue"
        if holder.isbn == target:
            if _is_identity(session, holder) and (
                    source != "stores" or holder.isbn_source == "admin"
                    or store_votes(session, holder.id).get(target, 0) >= 1):
                # A real catalog volume keeps its ISBN unless at least two
                # stores prove it belongs here and none back the holder.
                # Mangakol alone never takes an ISBN from another volume.
                _issue(session, volume, "isbn_claimed", isbn=target, holder=holder.id,
                       holder_number=holder.volume_number, reason=reason)
                return "issue"
            set_isbn(session, holder, None, "moved", f"ISBN {target} cilt {volume.id}'e taşındı: {reason}")
    set_isbn(session, volume, target, source, reason)
    _clear_issue(session, volume)
    return source


def resolve_many(session: Session, volume_ids) -> dict[str, int]:
    """Resolve each volume (and the volumes freed by a move). Flushes."""
    counts: dict[str, int] = defaultdict(int)
    pending = list(dict.fromkeys(volume_ids))
    seen: set[int] = set()
    while pending:
        vid = pending.pop(0)
        if vid in seen:
            continue
        seen.add(vid)
        volume = session.get(Volume, vid)
        if volume is None:
            continue
        outcome = resolve(session, volume)
        if outcome:
            counts[outcome] += 1
        pending.extend(session.info.pop("isbn_freed", []))
        if outcome in {"stores", "catalog"} and volume.catalog_isbn:
            # A decision can explain a Mangakol duplicate: re-check the
            # volumes Mangakol lists with the same ISBN.
            # Terminates: a re-check only reports a change when an ISBN moves.
            for pid in list(session.scalars(select(Volume.id).where(
                    Volume.catalog_isbn == volume.catalog_isbn, Volume.id != volume.id))):
                seen.discard(pid)
                pending.append(pid)
    return dict(counts)


def set_admin_isbn(session: Session, volume: Volume, isbn: str | None, *, user_id: int,
                   reason: str, share: bool = False, move: bool = False) -> dict:
    """An admin's ISBN for a volume (``None`` clears it). Raises ValueError
    with a Turkish message when the ISBN is invalid or held elsewhere and
    neither ``share`` (another edition of the same book) nor ``move`` is set."""
    if not reason.strip():
        raise ValueError("Gerekçe gerekli.")
    if isbn is not None:
        isbn = catalog_book_isbn(isbn)
        if isbn is None:
            raise ValueError("Geçerli bir Türk ISBN'i değil (kontrol basamağı, 978/979 öneki ve Türkiye kayıt grubu kontrol edildi).")
        for holder in isbn_holders(session, isbn):
            if holder.id == volume.id:
                continue
            if share:
                if not is_sibling(session, volume, holder):
                    raise ValueError("Ortak ISBN yalnızca aynı kitabın başka baskısıyla paylaşılabilir.")
                add_shared(session, volume, isbn, "admin", reason, user_id)
                _clear_issue(session, volume)
                session.flush()
                return dict(volume_id=volume.id, isbn=volume.isbn, shared=isbn)
            if not move:
                raise ValueError(f"Bu ISBN cilt {holder.volume_number} (#{holder.id}) üzerinde. Taşımak ya da ortak yapmak için seçeneği işaretleyin.")
            if holder.isbn == isbn:
                set_isbn(session, holder, None, "moved", f"Admin ISBN'i cilt #{volume.id}'e taşıdı: {reason}", user_id)
            else:
                for row in session.scalars(select(SharedIsbn).where(SharedIsbn.isbn == isbn, SharedIsbn.volume_id == holder.id)):
                    session.delete(row)
                log_change(session, holder.id, isbn, None, "unshared", f"Admin: {reason}", user_id)
    old = volume.isbn
    if old != isbn:
        log_change(session, volume.id, old, isbn, "admin", reason, user_id)
    volume.isbn = isbn
    # Also for a cleared ISBN: the admin's "no ISBN" must not be refilled.
    volume.isbn_source = "admin"
    _clear_issue(session, volume)
    session.flush()
    session.info.pop("isbn_freed", None)
    return dict(volume_id=volume.id, isbn=isbn, previous=old)
