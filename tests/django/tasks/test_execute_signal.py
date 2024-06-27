import os
import random
from datetime import UTC, datetime
from logging import Logger
from unittest.mock import MagicMock, call

import pytest
from django.dispatch import receiver
from django.utils import timezone

from task_manager.django.dispatch import Emisor
from task_manager.django.tasks import execute_signal

param_names = "task_module,task_name,get_call_args_list"
emisor = Emisor("tests.django.tasks.test_execute_signal")
signal = emisor.signal("signal")
bad_signal = emisor.signal("bad_signal")
UTC_NOW = datetime.now(UTC)


@receiver(bad_signal)
def bad_signal_handler(sender, **kwargs):
    raise Exception("bad signal")


@pytest.fixture(autouse=True)
def setup(db, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("logging.Logger.info", MagicMock())
    monkeypatch.setattr("logging.Logger.error", MagicMock())
    monkeypatch.setattr(signal, "send", MagicMock())
    monkeypatch.setattr(bad_signal, "send", MagicMock(wraps=bad_signal.send))
    monkeypatch.setattr(timezone, "now", lambda: UTC_NOW)

    yield


def format_signal_error(arguments={}, data={}):
    return {
        "arguments": arguments,
        "attempts": 1,
        "exception_module": "builtins",
        "exception_name": "Exception",
        "id": 1,
        "last_run": UTC_NOW,
        "message": "bad signal",
        "signal_module": "tests.django.tasks.test_execute_signal",
        "signal_name": "bad_signal",
        **data,
    }


@pytest.fixture
def arguments(fake):
    obj = {}

    for _ in range(3):
        obj[fake.slug()] = fake.slug()

    yield obj


def test_module_does_not_found(database, arguments):
    execute_signal.delay(
        "tests.django.test_dispatch2", "signal", "task_manager.django.models", "ScheduledTask", 1, extra=arguments
    )

    assert Logger.info.call_args_list == [
        call(
            "Running execute_signal for tests.django.test_dispatch2 signal, task_manager.django.models ScheduledTask 1"
        ),
    ]

    assert Logger.error.call_args_list == [
        call("Emisor tests.django.test_dispatch2 wasn't loaded", exc_info=True),
    ]

    assert database.list_of("task_manager.SignalError") == []
    assert signal.send.call_args_list == []
    assert bad_signal.send.call_args_list == []


def test_signal_does_not_found(database, arguments):
    execute_signal.delay(
        "tests.django.tasks.test_execute_signal",
        "signal2",
        "task_manager.django.models",
        "ScheduledTask",
        1,
        extra=arguments,
    )

    assert Logger.info.call_args_list == [
        call(
            "Running execute_signal for tests.django.tasks.test_execute_signal signal2, task_manager.django.models ScheduledTask 1"
        ),
    ]
    assert Logger.error.call_args_list == [
        call("Signal signal2 wasn't loaded", exc_info=True),
    ]

    assert database.list_of("task_manager.SignalError") == []
    assert signal.send.call_args_list == []
    assert bad_signal.send.call_args_list == []


def test_object_does_not_found(database, arguments):
    execute_signal.delay(
        "tests.django.tasks.test_execute_signal",
        "signal",
        "task_manager.django.models",
        "ScheduledTask",
        1,
        extra=arguments,
    )

    assert Logger.info.call_args_list == [
        call(
            "Running execute_signal for tests.django.tasks.test_execute_signal signal, task_manager.django.models ScheduledTask 1"
        )
        for _ in range(10)
    ]
    assert Logger.error.call_args_list == [
        call("ScheduledTask with pk=1 wasn't found", exc_info=True),
    ]

    assert database.list_of("task_manager.SignalError") == []
    assert signal.send.call_args_list == []
    assert bad_signal.send.call_args_list == []


def test_object_found(database, arguments):
    model = database.create(scheduled_task=1)
    execute_signal.delay(
        "tests.django.tasks.test_execute_signal",
        "signal",
        "task_manager.django.models",
        "ScheduledTask",
        1,
        extra=arguments,
    )

    assert Logger.info.call_args_list == [
        call(
            "Running execute_signal for tests.django.tasks.test_execute_signal signal, task_manager.django.models ScheduledTask 1"
        ),
        call("Signal executed successfully"),
    ]
    assert Logger.error.call_args_list == []

    assert database.list_of("task_manager.SignalError") == []
    assert signal.send.call_args_list == [
        call(sender=model.scheduled_task.__class__, instance=model.scheduled_task, **arguments),
    ]
    assert bad_signal.send.call_args_list == []


def test_object_found__raise_an_exception(database, arguments):
    model = database.create(scheduled_task=1)
    execute_signal.delay(
        "tests.django.tasks.test_execute_signal",
        "bad_signal",
        "task_manager.django.models",
        "ScheduledTask",
        1,
        extra=arguments,
    )

    assert Logger.info.call_args_list == [
        call(
            "Running execute_signal for tests.django.tasks.test_execute_signal bad_signal, task_manager.django.models ScheduledTask 1"
        ),
    ]
    assert Logger.error.call_args_list == [
        call("There has an error in tests.django.tasks.test_execute_signal bad_signal, bad signal", exc_info=True),
        call("bad signal", exc_info=True),
    ]

    assert database.list_of("task_manager.SignalError") == [
        format_signal_error(arguments=arguments),
    ]
    assert signal.send.call_args_list == []
    assert bad_signal.send.call_args_list == [
        call(sender=model.scheduled_task.__class__, instance=model.scheduled_task, **arguments),
    ]
