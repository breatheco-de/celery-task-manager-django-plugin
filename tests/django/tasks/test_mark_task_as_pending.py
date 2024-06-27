import os
import random
from datetime import timedelta
from logging import Logger
from unittest.mock import MagicMock, call

import pytest
from django.utils import timezone

from task_manager.django import tasks
from task_manager.django.tasks import mark_task_as_pending

# this fix a problem caused by the geniuses at pytest-xdist
random.seed(os.getenv("RANDOM_SEED"))

# minutes
TOLERANCE = random.randint(3, 10)
TOLERATED_DELTA = [timezone.timedelta(minutes=x) for x in range(0, TOLERANCE)]
NO_TOLERATED_DELTA = [timezone.timedelta(minutes=x) for x in range(TOLERANCE + 1, TOLERANCE + 5)]

params = [
    (
        "task_manager.django.tasks",
        "mark_task_as_cancelled",
        lambda: tasks.mark_task_as_cancelled.delay.call_args_list,
    ),
    (
        "task_manager.django.tasks",
        "mark_task_as_reversed",
        lambda: tasks.mark_task_as_reversed.delay.call_args_list,
    ),
    (
        "task_manager.django.tasks",
        "mark_task_as_paused",
        lambda: tasks.mark_task_as_paused.delay.call_args_list,
    ),
]

param_names = "task_module,task_name,get_call_args_list"


@pytest.fixture(autouse=True)
def setup(db, monkeypatch):
    monkeypatch.setattr("task_manager.django.tasks.mark_task_as_pending.apply_async", MagicMock())
    monkeypatch.setattr("task_manager.django.tasks.TOLERANCE", TOLERANCE)
    monkeypatch.setattr("logging.Logger.info", MagicMock())
    monkeypatch.setattr("logging.Logger.warning", MagicMock())
    monkeypatch.setattr("logging.Logger.error", MagicMock())

    yield


def get_args(fake):
    args = []

    for _ in range(random.randint(1, 4)):
        n = random.randint(0, 2)
        if n == 0:
            args.append(fake.slug())
        elif n == 1:
            args.append(random.randint(1, 100))
        elif n == 2:
            args.append(random.randint(1, 10000) / 100)

    return args


def get_kwargs(fake):
    kwargs = {}

    for _ in range(random.randint(1, 4)):
        n = random.randint(0, 2)
        if n == 0:
            kwargs[fake.slug()] = fake.slug()
        elif n == 1:
            kwargs[fake.slug()] = random.randint(1, 100)
        elif n == 2:
            kwargs[fake.slug()] = random.randint(1, 10000) / 100

    return kwargs


@pytest.fixture
def arrange(monkeypatch, database, fake):

    def _arrange(data={}):
        task_module = data.get("task_module")
        task_name = data.get("task_name")

        if task_module and task_name:
            monkeypatch.setattr(f"{task_module}.{task_name}.delay", MagicMock())

        task_manager = {
            "arguments": {
                "args": get_args(fake),
                "kwargs": get_kwargs(fake),
            },
            **data,
        }

        model = database.create(task_manager=task_manager)

        Logger.info.call_args_list = []
        Logger.warning.call_args_list = []
        Logger.error.call_args_list = []

        return model

    yield _arrange


# When: TaskManager is not found
# Then: nothing happens
def test_not_found(database):
    res = mark_task_as_pending(1)

    assert res is None

    assert Logger.info.call_args_list == [call("Running mark_task_as_pending for 1")]
    assert Logger.warning.call_args_list == []
    assert Logger.error.call_args_list == [call("TaskManager 1 not found")]

    assert database.list_of("task_manager.TaskManager") == []
    assert mark_task_as_pending.apply_async.call_args_list == []


# When: TaskManager found
# Then: the task execution is resheduled
@pytest.mark.parametrize(param_names, params)
def test_found(database, arrange, task_module, task_name, get_call_args_list, get_json_obj):

    model = arrange(
        {
            "task_module": task_module,
            "task_name": task_name,
        }
    )

    res = mark_task_as_pending(1)

    assert res is None

    assert Logger.info.call_args_list == [
        call("Running mark_task_as_pending for 1"),
        call("TaskManager 1 is being marked as PENDING"),
    ]

    assert Logger.warning.call_args_list == []
    assert Logger.error.call_args_list == []

    assert database.list_of("task_manager.TaskManager") == [get_json_obj(model.task_manager)]

    assert get_call_args_list() == [
        call(
            *model.task_manager.arguments["args"],
            **model.task_manager.arguments["kwargs"],
            page=1,
            total_pages=1,
            task_manager_id=1,
        )
    ]
    assert mark_task_as_pending.apply_async.call_args_list == []


# When: TaskManager found and it's done
# Then: nothing happens
@pytest.mark.parametrize("status", ["DONE", "CANCELLED", "REVERSED"])
@pytest.mark.parametrize(param_names, params)
def test_task_is_done(database, arrange, task_module, task_name, get_call_args_list, status, get_json_obj):

    model = arrange(
        {
            "task_module": task_module,
            "task_name": task_name,
            "status": status,
        }
    )

    res = mark_task_as_pending(1)

    assert res is None

    assert Logger.info.call_args_list == [
        call("Running mark_task_as_pending for 1"),
    ]

    assert Logger.warning.call_args_list == [call("TaskManager 1 was already DONE")]
    assert Logger.error.call_args_list == []

    assert database.list_of("task_manager.TaskManager") == [get_json_obj(model.task_manager)]

    assert get_call_args_list() == []
    assert mark_task_as_pending.apply_async.call_args_list == []


# When: TaskManager found and it's running, so, the last_run changed
# Then: nothing happens
@pytest.mark.parametrize(param_names, params)
def test_task_is_running(database, arrange, task_module, task_name, get_call_args_list, get_json_obj):
    d1 = timezone.now()
    d2 = timezone.now()

    model = arrange(
        {
            "task_module": task_module,
            "task_name": task_name,
            "last_run": d1,
        }
    )

    res = mark_task_as_pending(1, last_run=d2)

    assert res is None

    assert Logger.info.call_args_list == [
        call("Running mark_task_as_pending for 1"),
    ]

    assert Logger.warning.call_args_list == [call("TaskManager 1 is already running")]
    assert Logger.error.call_args_list == []

    assert database.list_of("task_manager.TaskManager") == [get_json_obj(model.task_manager)]

    assert get_call_args_list() == []
    assert mark_task_as_pending.apply_async.call_args_list == []


# When: TaskManager last_run is less than the tolerance
# Then: mark_task_as_pending is rescheduled
@pytest.mark.parametrize("delta", TOLERATED_DELTA)
@pytest.mark.parametrize(param_names, random.choices(params, k=1))
def test_task_last_run_less_than_the_tolerance(
    database, arrange, task_module, task_name, get_call_args_list, delta, utc_now, get_json_obj
):
    model = arrange(
        {
            "task_module": task_module,
            "task_name": task_name,
            "last_run": timezone.now() - delta,
        }
    )

    res = mark_task_as_pending(1)

    assert res is None

    assert Logger.info.call_args_list == [
        call("Running mark_task_as_pending for 1"),
    ]

    assert Logger.warning.call_args_list == [call("TaskManager 1 was not killed, scheduling to run it again")]
    assert Logger.error.call_args_list == []

    assert database.list_of("task_manager.TaskManager") == [get_json_obj(model.task_manager)]

    assert get_call_args_list() == []
    assert mark_task_as_pending.apply_async.call_args_list == [
        call(
            args=(1,),
            kwargs={
                "attempts": 1,
                "last_run": model.task_manager.last_run,
            },
            eta=utc_now + timedelta(seconds=30),
        )
    ]


# When: TaskManager last_run is less than the tolerance, force is True
# Then: it's rescheduled, the tolerance is ignored
@pytest.mark.parametrize("delta", TOLERATED_DELTA)
@pytest.mark.parametrize(param_names, random.choices(params, k=1))
def test_task_last_run_less_than_the_tolerance__force_true(
    database, arrange, task_module, task_name, get_call_args_list, delta, get_json_obj
):
    model = arrange(
        {
            "task_module": task_module,
            "task_name": task_name,
            "last_run": timezone.now() - delta,
        }
    )

    res = mark_task_as_pending(1, force=True)

    assert res is None

    assert Logger.info.call_args_list == [
        call("Running mark_task_as_pending for 1"),
        call("TaskManager 1 is being marked as PENDING"),
    ]

    assert Logger.warning.call_args_list == []
    assert Logger.error.call_args_list == []

    assert database.list_of("task_manager.TaskManager") == [get_json_obj(model.task_manager)]

    assert get_call_args_list() == [
        call(
            *model.task_manager.arguments["args"],
            **model.task_manager.arguments["kwargs"],
            page=1,
            total_pages=1,
            task_manager_id=1,
        )
    ]
    assert mark_task_as_pending.apply_async.call_args_list == []


# When: TaskManager last_run is less than the tolerance, attempts is greater than 10
# Then: it's rescheduled because the task was not ended and it's not running
@pytest.mark.parametrize("attempts", [x for x in range(11, 16)])
@pytest.mark.parametrize("delta", TOLERATED_DELTA)
@pytest.mark.parametrize(param_names, random.choices(params, k=1))
def test_task_last_run_less_than_the_tolerance__attempts_gt_10(
    database, arrange, task_module, task_name, get_call_args_list, delta, attempts, get_json_obj
):
    model = arrange(
        {
            "task_module": task_module,
            "task_name": task_name,
            "last_run": timezone.now() - delta,
        }
    )

    res = mark_task_as_pending(1, attempts=attempts)

    assert res is None

    assert Logger.info.call_args_list == [
        call("Running mark_task_as_pending for 1"),
        call("TaskManager 1 is being marked as PENDING"),
    ]

    assert Logger.warning.call_args_list == []
    assert Logger.error.call_args_list == []

    assert database.list_of("task_manager.TaskManager") == [get_json_obj(model.task_manager)]

    assert get_call_args_list() == [
        call(
            *model.task_manager.arguments["args"],
            **model.task_manager.arguments["kwargs"],
            page=1,
            total_pages=1,
            task_manager_id=1,
        )
    ]
    assert mark_task_as_pending.apply_async.call_args_list == []


# When: TaskManager last_run is greater than the tolerance
# Then: mark_task_as_pending is rescheduled
@pytest.mark.parametrize("delta", NO_TOLERATED_DELTA)
@pytest.mark.parametrize(param_names, random.choices(params, k=1))
def test_task_last_run_greater_than_the_tolerance(
    database, arrange, task_module, task_name, get_call_args_list, delta, get_json_obj
):
    model = arrange(
        {
            "task_module": task_module,
            "task_name": task_name,
            "last_run": timezone.now() - delta,
        }
    )

    res = mark_task_as_pending(1)

    assert res is None

    assert Logger.info.call_args_list == [
        call("Running mark_task_as_pending for 1"),
        call("TaskManager 1 is being marked as PENDING"),
    ]

    assert Logger.warning.call_args_list == []
    assert Logger.error.call_args_list == []

    assert database.list_of("task_manager.TaskManager") == [get_json_obj(model.task_manager)]

    assert get_call_args_list() == [
        call(
            *model.task_manager.arguments["args"],
            **model.task_manager.arguments["kwargs"],
            page=1,
            total_pages=1,
            task_manager_id=1,
        )
    ]
    assert mark_task_as_pending.apply_async.call_args_list == []
