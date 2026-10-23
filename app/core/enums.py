from enum import StrEnum


class RequestStatus(StrEnum):
    """How processing ended for one incoming request."""

    PENDING = "pending"
    DRAFTED = "drafted"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"
    FAILED = "failed"


class DraftStatus(StrEnum):
    READY_FOR_REVIEW = "ready_for_review"
    NEEDS_CLARIFICATION = "needs_clarification"
    NEEDS_REVIEW = "needs_review"
    REVIEWED = "reviewed"


class FindingCode(StrEnum):
    UNKNOWN_PRODUCT = "unknown_product"
    AMBIGUOUS_PRODUCT = "ambiguous_product"
    AMBIGUOUS_QUANTITY = "ambiguous_quantity"
    NON_INDIVIDUAL_UNIT = "non_individual_unit"
    UNVERIFIED_SKU = "unverified_sku"
    CONFLICTING_REQUEST = "conflicting_request"


class ResponseSource(StrEnum):
    LIVE = "live"
    CACHED = "cached"
    SIMULATED_FAILURE = "simulated-failure"
