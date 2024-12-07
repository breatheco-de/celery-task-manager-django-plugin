from typing import Generator
from unittest.mock import patch

import pytest

__all__ = ["dont_wait_for_rescheduling_tasks"]


@pytest.fixture(autouse=True)
def dont_wait_for_rescheduling_tasks() -> Generator[None, None, None]:
    """
    Don't wait for rescheduling tasks by default.

    You can re-enable it within a test by calling the provided wrapper.
    """

    from task_manager.core.settings import set_settings

    set_settings(RETRIES_LIMIT=2)

    with patch(
        "task_manager.core.decorators.Task.reattempt_settings",
        lambda *args, **kwargs: dict(),
    ):
        with patch(
            "task_manager.core.decorators.Task.circuit_breaker_settings",
            lambda *args, **kwargs: dict(),
        ):
            yield
