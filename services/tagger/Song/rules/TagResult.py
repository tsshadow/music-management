from dataclasses import dataclass
from enum import Enum, auto


class TagResultType(Enum):
    """What a rule concluded about a tag value."""

    VALID = auto()
    UPDATED = auto()
    IGNORED = auto()
    UNKNOWN = auto()


@dataclass
class TagResult:
    """A tag value together with what the rule concluded about it."""

    value: str | None
    result_type: TagResultType
