from datetime import UTC, datetime
from logging import Logger
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from django.dispatch import Signal
from django.utils import timezone

from task_manager.django.dispatch import Emisor
from task_manager.django.models import ScheduledTask, TaskWatcher
from task_manager.django.tasks import execute_signal

emisor = Emisor("tests.django.test_dispatch")
signal = emisor.signal("signal")

UTC_NOW = datetime.now(UTC)


@pytest.fixture(autouse=True)
def setup(db, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(Signal, "send", MagicMock())
    monkeypatch.setattr(Signal, "asend", AsyncMock())
    monkeypatch.setattr(execute_signal, "delay", MagicMock())
    monkeypatch.setattr(Logger, "error", MagicMock())
    monkeypatch.setattr(timezone, "now", lambda: UTC_NOW)

    yield


@pytest.fixture
def arguments(fake):
    obj = {}

    for _ in range(3):
        obj[fake.slug()] = fake.slug()

    yield obj


def format_signal_error(arguments={}, data={}):
    return {
        "arguments": arguments,
        "attempts": 1,
        "exception_module": "builtins",
        "exception_name": "Exception",
        "id": 1,
        "last_run": UTC_NOW,
        "message": "aaa",
        "signal_module": "tests.django.test_dispatch",
        "signal_name": "signal",
        **data,
    }


@pytest.mark.django_db(reset_sequences=True)
def test_attrs():
    assert emisor.module == "tests.django.test_dispatch"

    assert signal.name == "signal"
    assert signal.module == "tests.django.test_dispatch"

    assert Signal.send.call_args_list == []
    assert Signal.asend.call_args_list == []
    assert execute_signal.delay.call_args_list == []
    assert Logger.error.call_args_list == []


@pytest.mark.django_db(reset_sequences=True)
def test_signal_send(arguments, database):
    signal.send(sender=TaskWatcher, **arguments)

    assert Signal.send.call_args_list == [call(TaskWatcher, **arguments)]
    assert Signal.asend.call_args_list == []
    assert execute_signal.delay.call_args_list == []
    assert Logger.error.call_args_list == []
    assert database.list_of("task_manager.SignalError") == []


@pytest.mark.django_db(reset_sequences=True)
def test_signal_send_exception(arguments, database, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        Signal,
        "send",
        MagicMock(
            side_effect=[Exception("aaa"), None, None, None, None, None, None, None, None, None, None, None, None]
        ),
    )

    with pytest.raises(Exception, match="aaa"):
        signal.send(sender=TaskWatcher, **arguments)

    # internal django calls
    assert len(Signal.send.call_args_list) == 5
    assert Signal.send.call_args_list[0] == call(TaskWatcher, **arguments)
    assert Signal.asend.call_args_list == []
    assert execute_signal.delay.call_args_list == []
    assert Logger.error.call_args_list == [
        call("There has an error in tests.django.test_dispatch signal, aaa", exc_info=True)
    ]
    assert database.list_of("task_manager.SignalError") == [
        format_signal_error(arguments=arguments),
    ]


@pytest.mark.asyncio
@pytest.mark.django_db(reset_sequences=True)
async def test_signal_asend(arguments, database):
    await signal.asend(sender=TaskWatcher, **arguments)

    assert Signal.send.call_args_list == []
    assert Signal.asend.call_args_list == [call(TaskWatcher, **arguments)]
    assert execute_signal.delay.call_args_list == []
    assert Logger.error.call_args_list == []
    assert await database.alist_of("task_manager.SignalError") == []


@pytest.mark.asyncio
@pytest.mark.django_db(reset_sequences=True)
async def test_signal_asend_exception(arguments, database, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(Signal, "asend", AsyncMock(side_effect=Exception("aaa")))

    with pytest.raises(Exception, match="aaa"):
        await signal.asend(sender=TaskWatcher, **arguments)

    # internal django calls
    assert len(Signal.send.call_args_list) == 4
    assert Signal.asend.call_args_list == [call(TaskWatcher, **arguments)]
    assert execute_signal.delay.call_args_list == []
    assert Logger.error.call_args_list == [
        call("There has an error in tests.django.test_dispatch signal, aaa", exc_info=True)
    ]
    assert await database.alist_of("task_manager.SignalError") == [
        format_signal_error(arguments=arguments),
    ]


@pytest.mark.django_db(reset_sequences=True)
def test_signal_send_robust(arguments, database):
    signal.send_robust(sender=TaskWatcher, **arguments)

    assert Signal.send.call_args_list == [call(TaskWatcher, **arguments)]
    assert Signal.asend.call_args_list == []
    assert execute_signal.delay.call_args_list == []
    assert Logger.error.call_args_list == []
    assert database.list_of("task_manager.SignalError") == []


@pytest.mark.django_db(reset_sequences=True)
def test_signal_send_robust_exception(arguments, database, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        Signal,
        "send",
        MagicMock(
            side_effect=[Exception("aaa"), None, None, None, None, None, None, None, None, None, None, None, None]
        ),
    )

    signal.send_robust(sender=TaskWatcher, **arguments)

    # internal django calls
    assert len(Signal.send.call_args_list) == 5
    assert Signal.send.call_args_list[0] == call(TaskWatcher, **arguments)
    assert Signal.asend.call_args_list == []
    assert execute_signal.delay.call_args_list == []
    assert Logger.error.call_args_list == [
        call("There has an error in tests.django.test_dispatch signal, aaa", exc_info=True)
    ]
    assert database.list_of("task_manager.SignalError") == [
        format_signal_error(arguments=arguments),
    ]


@pytest.mark.asyncio
@pytest.mark.django_db(reset_sequences=True)
async def test_signal_asend_robust(arguments, database):
    await signal.asend_robust(sender=TaskWatcher, **arguments)

    assert Signal.send.call_args_list == []
    assert Signal.asend.call_args_list == [call(TaskWatcher, **arguments)]
    assert execute_signal.delay.call_args_list == []
    assert Logger.error.call_args_list == []
    assert await database.alist_of("task_manager.SignalError") == []


@pytest.mark.asyncio
@pytest.mark.django_db(reset_sequences=True)
async def test_signal_asend_robust_exception(arguments, database, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(Signal, "asend", AsyncMock(side_effect=Exception("aaa")))

    await signal.asend_robust(sender=TaskWatcher, **arguments)

    # internal django calls
    assert len(Signal.send.call_args_list) == 4
    assert Signal.asend.call_args_list == [call(TaskWatcher, **arguments)]
    assert execute_signal.delay.call_args_list == []
    assert Logger.error.call_args_list == [
        call("There has an error in tests.django.test_dispatch signal, aaa", exc_info=True)
    ]
    assert await database.alist_of("task_manager.SignalError") == [
        format_signal_error(arguments=arguments),
    ]


########


@pytest.mark.django_db(reset_sequences=True)
def test_signal_delay__force_no_pk(database, arguments):
    model = database.create(scheduled_task=1)
    model.scheduled_task.pk = None
    with pytest.raises(Exception, match="Cannot delay a signal for models without ids"):
        signal.delay(sender=ScheduledTask, instance=model.scheduled_task, **arguments)

    # internal django calls
    assert len(Signal.send.call_args_list) == 4
    assert Signal.asend.call_args_list == []
    assert execute_signal.delay.call_args_list == []
    assert Logger.error.call_args_list == []
    assert database.list_of("task_manager.SignalError") == []


@pytest.mark.django_db(reset_sequences=True)
def test_signal_delay(database, arguments):
    model = database.create(scheduled_task=1)
    signal.delay(sender=ScheduledTask, instance=model.scheduled_task, **arguments)

    # internal django calls
    assert len(Signal.send.call_args_list) == 4
    assert Signal.asend.call_args_list == []
    assert execute_signal.delay.call_args_list == [
        call("tests.django.test_dispatch", "signal", "task_manager.django.models", "ScheduledTask", 1, extra=arguments)
    ]
    assert Logger.error.call_args_list == []
    assert database.list_of("task_manager.SignalError") == []


@pytest.mark.asyncio
@pytest.mark.django_db(reset_sequences=True)
async def test_signal_adelay__force_no_pk(database, arguments):
    model = await database.acreate(scheduled_task=1)
    model.scheduled_task.pk = None
    with pytest.raises(Exception, match="Cannot delay a signal for models without ids"):
        await signal.adelay(sender=ScheduledTask, instance=model.scheduled_task, **arguments)

    # internal django calls
    assert len(Signal.send.call_args_list) == 4
    assert Signal.asend.call_args_list == []
    assert execute_signal.delay.call_args_list == []
    assert Logger.error.call_args_list == []
    assert await database.alist_of("task_manager.SignalError") == []


@pytest.mark.asyncio
@pytest.mark.django_db(reset_sequences=True)
async def test_signal_adelay(database, arguments):
    model = await database.acreate(scheduled_task=1)
    await signal.adelay(sender=ScheduledTask, instance=model.scheduled_task, **arguments)

    # internal django calls
    assert len(Signal.send.call_args_list) == 4
    assert Signal.asend.call_args_list == []
    assert execute_signal.delay.call_args_list == [
        call("tests.django.test_dispatch", "signal", "task_manager.django.models", "ScheduledTask", 1, extra=arguments)
    ]
    assert Logger.error.call_args_list == []
    assert await database.alist_of("task_manager.SignalError") == []
