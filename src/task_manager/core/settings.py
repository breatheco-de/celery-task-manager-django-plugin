import os
from datetime import timedelta

from .exceptions import ProgrammingError

__init__ = ["set_settings", "get_setting"]

settings = {
    "RETRIES_LIMIT": 10,
    "RETRY_AFTER": timedelta(seconds=5),
    "DEFAULT": 5,
    "SCHEDULER": 10,
    "TASK_MANAGER": 6,
}

if p := os.environ.get("TASK_MANAGER_PRIORITY"):
    settings["TASK_MANAGER"] = int(p)


def get_setting(key, default=None):
    return settings.get(key, default)


def set_settings(**kwargs):
    for key, value in kwargs.items():
        key = key.upper()
        if key not in settings:
            raise ProgrammingError(f"Invalid setting {key}")

        settings[key] = value
