import os
import random
from logging import Logger
from unittest.mock import MagicMock, call

import pytest

from task_manager.django.tasks import mark_task_as_cancelled

# this fix a problem caused by the geniuses at pytest-xdist
random.seed(os.getenv("RANDOM_SEED"))

param_names = "task_module,task_name,get_call_args_list"


@pytest.fixture(autouse=True)
def setup(db, monkeypatch):
    monkeypatch.setattr("logging.Logger.info", MagicMock())
    monkeypatch.setattr("logging.Logger.warning", MagicMock())
    monkeypatch.setattr("logging.Logger.error", MagicMock())

    yield


def get_args(fake):
    args = []

    for _ in range(random.randint(0, 4)):
        n = range(random.randint(0, 2))
        if n == 0:
            args.append(fake.slug())
        elif n == 1:
            args.append(random.randint(1, 100))
        elif n == 2:
            args.append(random.randint(1, 10000) / 100)

    return args


def get_kwargs(fake):
    kwargs = {}

    for _ in range(random.randint(0, 4)):
        n = range(random.randint(0, 2))
        if n == 0:
            kwargs[fake.slug()] = fake.slug()
        elif n == 1:
            kwargs[fake.slug()] = random.randint(1, 100)
        elif n == 2:
            kwargs[fake.slug()] = random.randint(1, 10000) / 100

    return kwargs


@pytest.fixture
def arrange(database, fake):

    def _arrange(data={}):

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
    res = mark_task_as_cancelled(1)

    assert res is None

    assert Logger.info.call_args_list == [call("Running mark_task_as_cancelled for 1")]
    assert Logger.warning.call_args_list == []
    assert Logger.error.call_args_list == [call("TaskManager 1 not found")]

    assert database.list_of("task_manager.TaskManager") == []


# When: TaskManager found
# Then: the task is paused
def test_found(database, arrange, get_json_obj):

    model = arrange({})

    res = mark_task_as_cancelled(1)

    assert res is None

    assert Logger.info.call_args_list == [
        call("Running mark_task_as_cancelled for 1"),
        call("TaskManager 1 is being marked as CANCELLED"),
    ]

    assert Logger.warning.call_args_list == []
    assert Logger.error.call_args_list == []

    assert database.list_of("task_manager.TaskManager") == [
        {
            **get_json_obj(model.task_manager),
            "status": "CANCELLED",
        },
    ]


# When: TaskManager is not running, it means it's not pending
# Then: nothing happens
@pytest.mark.parametrize("status", ["DONE", "CANCELLED", "REVERSED", "ABORTED", "ERROR"])
def test_its_not_running(database, arrange, status, get_json_obj):

    model = arrange({"status": status})

    res = mark_task_as_cancelled(1)

    assert res is None

    assert Logger.info.call_args_list == [
        call("Running mark_task_as_cancelled for 1"),
    ]

    assert Logger.warning.call_args_list == [call("TaskManager 1 was already DONE")]
    assert Logger.error.call_args_list == []

    assert database.list_of("task_manager.TaskManager") == [get_json_obj(model.task_manager)]
