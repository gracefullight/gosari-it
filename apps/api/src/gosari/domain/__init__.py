"""SRS §4.3 상태의 독립 축."""

from enum import StrEnum


class DataStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    NO_DATA = "no_data"
    CONFLICT = "conflict"
    NEEDS_CONFIRMATION = "needs_confirmation"
    UNAVAILABLE = "unavailable"


class SourceMode(StrEnum):
    FETCHED = "fetched"
    CACHE = "cache"
    REPLAY = "replay"
    LINK = "link"
    PERMITTED_FILE = "permitted_file"


class ActionStatus(StrEnum):
    PREVIEW = "preview"
    CONFIRMED = "confirmed"
    COMMITTED = "committed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ValueState(StrEnum):
    VALID = "valid"
    VALID_ZERO = "valid_zero"
    MISSING = "missing"
    ERROR = "error"
    UNRESOLVED_BLANK = "unresolved_blank"


class LinkStatus(StrEnum):
    NOT_REQUESTED = "not_requested"
    LINK_READY = "link_ready"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"


class CacheResolution(StrEnum):
    EXACT_HIT = "exact_hit"
    SEMANTIC_HIT = "semantic_hit"
    MISS = "miss"
    BYPASS = "bypass"


class RuntimeMode(StrEnum):
    LIVE = "live"
    REPLAY = "replay"
    LIMITED = "limited"


class JobStage(StrEnum):
    CREATED = "created"
    NEEDS_CONFIRMATION = "needs_confirmation"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
