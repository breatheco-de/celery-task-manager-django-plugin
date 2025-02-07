import os
import random
from logging import Logger
from unittest.mock import MagicMock, call

import pytest
from celery.result import AsyncResult

from task_manager.django import tasks
from task_manager.django.tasks import mark_task_as_pending

# this fix a problem caused by the geniuses at pytest-xdist
random.seed(os.getenv("RANDOM_SEED"))

# minutes

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
def setup(db, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("logging.Logger.info", MagicMock())
    monkeypatch.setattr("logging.Logger.warning", MagicMock())
    monkeypatch.setattr("logging.Logger.error", MagicMock())
    monkeypatch.setattr(AsyncResult, "revoke", MagicMock())

    yield


@pytest.fixture(autouse=True)
def set_status(monkeypatch: pytest.MonkeyPatch):
    def set_status(status):
        monkeypatch.setattr(AsyncResult, "status", status)

    yield set_status


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
    assert AsyncResult.revoke.call_args_list == []


# When: TaskManager found
# Then: the task execution is rescheduled
@pytest.mark.parametrize(param_names, params)
def test_found__pending(database, arrange, task_module, task_name, get_call_args_list, get_json_obj, set_status):
    set_status("PENDING")

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
        call("TaskManager 1 marked as PENDING"),
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
    assert AsyncResult.revoke.call_args_list == [call(terminate=True)]


# When: TaskManager found
# Then: the task execution is rescheduled
@pytest.mark.parametrize(param_names, params)
def test_found__sent(database, arrange, task_module, task_name, get_call_args_list, get_json_obj, set_status):
    set_status("SENT")

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
    ]

    assert Logger.warning.call_args_list == [call("TaskManager 1 scheduled, skipping")]
    assert Logger.error.call_args_list == []

    assert database.list_of("task_manager.TaskManager") == [get_json_obj(model.task_manager)]

    assert get_call_args_list() == []
    assert AsyncResult.revoke.call_args_list == []


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

    assert Logger.warning.call_args_list == [call("TaskManager 1 is already DONE")]
    assert Logger.error.call_args_list == []

    assert database.list_of("task_manager.TaskManager") == [get_json_obj(model.task_manager)]

    assert get_call_args_list() == []
    assert AsyncResult.revoke.call_args_list == []


# When: TaskManager last_run is less than the tolerance, force is True
# Then: it's rescheduled, the tolerance is ignored
@pytest.mark.parametrize(param_names, random.choices(params, k=1))
@pytest.mark.parametrize("status,killed", [("SENT", True), ("PENDING", False)])
def test_force_true(
    database, arrange, task_module, task_name, get_call_args_list, get_json_obj, set_status, status, killed
):
    set_status(status)
    model = arrange(
        {
            "task_module": task_module,
            "task_name": task_name,
        }
    )

    res = mark_task_as_pending(1, force=True)

    assert res is None

    assert Logger.info.call_args_list == [
        call("Running mark_task_as_pending for 1"),
        call("TaskManager 1 marked as PENDING"),
    ]

    assert Logger.warning.call_args_list == []
    assert Logger.error.call_args_list == []

    assert database.list_of("task_manager.TaskManager") == [
        {
            **get_json_obj(model.task_manager),
            "killed": killed,
        }
    ]

    assert get_call_args_list() == [
        call(
            *model.task_manager.arguments["args"],
            **model.task_manager.arguments["kwargs"],
            page=1,
            total_pages=1,
            task_manager_id=1,
        )
    ]
    assert AsyncResult.revoke.call_args_list == [call(terminate=True)]
