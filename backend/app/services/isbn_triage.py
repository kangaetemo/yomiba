"""Presentation queues derived from stored results, without rewriting audit history."""
from typing import Literal

from sqlalchemy import and_, case, or_

from ..models import IsbnAuditResult, IsbnReview

Queue = Literal["APPROVAL", "INVESTIGATE", "AWAITING_EVIDENCE", "REVIEWED"]
QUEUES = ("APPROVAL", "INVESTIGATE", "AWAITING_EVIDENCE", "REVIEWED")
CHANGE_STATUSES = ("CONFLICT", "MISSING_ISBN")
SETTLED_STATUSES = ("VERIFIED", "SKIPPED_UPCOMING")


def queue_for(review, result) -> Queue:
    if review.workflow == "REVIEWED" or result.status in SETTLED_STATUSES:
        return "REVIEWED"
    if result.status in CHANGE_STATUSES and result.proposed_isbn:
        return "APPROVAL"
    if result.status == "CONFLICT":
        return "INVESTIGATE"
    return "AWAITING_EVIDENCE"


def queue_expression():
    """Apply the same classification before SQL counting and pagination."""
    return case(
        (or_(IsbnReview.workflow == "REVIEWED", IsbnAuditResult.status.in_(SETTLED_STATUSES)), "REVIEWED"),
        (and_(IsbnAuditResult.status.in_(CHANGE_STATUSES), IsbnAuditResult.proposed_isbn.is_not(None),
              IsbnAuditResult.proposed_isbn != ""), "APPROVAL"),
        (IsbnAuditResult.status == "CONFLICT", "INVESTIGATE"),
        else_="AWAITING_EVIDENCE",
    )
