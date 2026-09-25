"""Current-user context.

There is no auth system in this project scope: every operation runs for the
single implicit local user. This module is the ONE place that knowledge lives
so the domain layer stays user-agnostic:

  * models take ``user_id`` columns (future-proofing, unique-per-user rules)
  * services resolve the acting user via :func:`current_user_id`
  * routes never pass or hardcode user ids

When real users arrive, only this module changes (e.g. it becomes an
auth-backed dependency) — models, services and routes stay as they are.
"""

from __future__ import annotations

#: The single implicit local user (no auth in scope).
LOCAL_USER_ID: int = 1


def current_user_id() -> int:
    """Return the id of the acting user.

    Always :data:`LOCAL_USER_ID` today; the seam where a real
    authentication layer plugs in later.
    """
    return LOCAL_USER_ID
