import inspect
from datetime import datetime
from decimal import Decimal
from typing import Callable


def parse_payload(payload: dict):
    if not isinstance(payload, dict):
        return payload

    for key in payload.keys():
        # TypeError("string indices must be integers, not 'str'")
        if isinstance(payload[key], datetime):
            payload[key] = payload[key].isoformat().replace("+00:00", "Z")

        elif isinstance(payload[key], Decimal):
            payload[key] = str(payload[key])

        elif isinstance(payload[key], list) or isinstance(payload[key], tuple) or isinstance(payload[key], set):
            array = []
            for item in payload[key]:
                array.append(parse_payload(item))

            payload[key] = array

        elif isinstance(payload[key], dict):
            payload[key] = parse_payload(payload[key])

    return payload


def get_fn_desc(function: Callable) -> tuple[str, str] | tuple[None, None]:
    if not function:
        return None, None

    if hasattr(function, "__module__"):
        module_name = function.__module__

    else:
        module_name = inspect.getmodule(function).__name__

    function_name = function.__name__

    return module_name, function_name
