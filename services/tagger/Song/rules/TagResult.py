from dataclasses import dataclass
from enum import Enum, auto

class TagResultType(Enum):
    VALID = auto()
    UPDATED = auto()
    IGNORED = auto()
    UNKNOWN = auto()

@dataclass
class TagResult:
    value: str | None
    result_type: TagResultType
