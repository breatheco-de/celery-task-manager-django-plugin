from datetime import datetime, timezone
from enum import Enum

__all__ = ["DuplicationPolicy"]


class DuplicationPolicy(Enum):
    SKIP = "SKIP"
    OVERRIDE = "OVERRIDE"
    APPEND = "APPEND"
