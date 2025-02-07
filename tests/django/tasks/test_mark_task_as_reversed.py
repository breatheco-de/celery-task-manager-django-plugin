import importlib
import os
import random
from logging import Logger
from unittest.mock import MagicMock, call

import pytest
from celery.result import AsyncResult

from task_manager.django.tasks import mark_task_as_reversed

# this fix a problem caused by the geniuses at pytest-xdist
random.seed(os.getenv("RANDOM_SEED"))

# minutes

params = [
    ("breathecode.admissions.tasks", "async_test_syllabus"),
    ("breathecode.admissions.tasks", "build_profile_academy"),
    ("breathecode.admissions.tasks", "build_cohort_user"),
    ("breathecode.payments.tasks", "add_cohort_set_to_subscription"),
    ("breathecode.payments.tasks", "build_consumables_from_bag"),
    ("breathecode.payments.tasks", "build_plan_financing"),
    ("breathecode.events.tasks", "async_eventbrite_webhook"),
    ("breathecode.events.tasks", "async_export_event_to_eventbrite"),
    ("breathecode.events.tasks", "fix_live_class_dates"),
]

param_names = "task_module,task_name"


@pytest.fixture(autouse=True)
def setup(db, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("logging.Logger.info", MagicMock())
    monkeypatch.setattr("logging.Logger.warning", MagicMock())
    monkeypatch.setattr("logging.Logger.error", MagicMock())
    monkeypatch.setattr("importlib.import_module", MagicMock())
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
        importlib.import_module.call_args_list = []

        return model

    yield _arrange


# When: TaskManager is not found
# Then: nothing happens
def test_not_found(database):
    res = mark_task_as_reversed(1)

    assert res is None

    assert Logger.info.call_args_list == [call("Running mark_task_as_reversed for 1")]
    assert Logger.warning.call_args_list == []
    assert Logger.error.call_args_list == [call("TaskManager 1 not found")]

    assert database.list_of("task_manager.TaskManager") == []

    assert importlib.import_module.call_args_list == []
    assert AsyncResult.revoke.call_args_list == []


# When: TaskManager without reverse function
# Then: the task execution is resheduled
@pytest.mark.parametrize(param_names, sorted(params))
def test_no_reverse_function(database, arrange, task_module, task_name, get_json_obj):

    model = arrange(
        {
            "task_module": task_module,
            "task_name": task_name,
        }
    )

    res = mark_task_as_reversed(1)

    assert res is None

    assert Logger.info.call_args_list == [
        call("Running mark_task_as_reversed for 1"),
    ]

    assert Logger.warning.call_args_list == [call("TaskManager 1 does not have a reverse function")]
    assert Logger.error.call_args_list == []

    assert database.list_of("task_manager.TaskManager") == [get_json_obj(model.task_manager)]

    assert importlib.import_module.call_args_list == []
    assert AsyncResult.revoke.call_args_list == []


# When: TaskManager with reverse function
# Then: the task is reverse
@pytest.mark.parametrize(param_names, sorted(random.choices(params, k=1)))
def test_reversed(database, arrange, task_module, task_name, get_json_obj):

    model = arrange(
        {
            "task_module": task_module,
            "task_name": task_name,
            "reverse_module": task_module,
            "reverse_name": "reverse",
            "status": "DONE",
        }
    )

    res = mark_task_as_reversed(1)

    assert res is None

    assert Logger.info.call_args_list == [
        call("Running mark_task_as_reversed for 1"),
        call("TaskManager 1 marked as REVERSED"),
    ]

    assert Logger.warning.call_args_list == []
    assert Logger.error.call_args_list == []

    assert database.list_of("task_manager.TaskManager") == [
        {
            **get_json_obj(model.task_manager),
            "status": "REVERSED",
        },
    ]

    assert importlib.import_module.call_args_list == [call(task_module)]
    assert importlib.import_module.return_value.reverse.call_args_list == [
        call(*model.task_manager.arguments["args"], **model.task_manager.arguments["kwargs"]),
    ]
    assert AsyncResult.revoke.call_args_list == []


# When: TaskManager last_run is less than the tolerance
# Then: mark_task_as_pending is rescheduled
@pytest.mark.parametrize("status", ["PENDING", "CANCELLED", "PAUSED", "ABORTED", "ERROR", "SCHEDULED"])
@pytest.mark.parametrize(param_names, sorted(random.choices(params, k=1)))
def test_task_is_not_done(database, arrange, task_module, task_name, get_json_obj, status):

    model = arrange(
        {
            "task_module": task_module,
            "task_name": task_name,
            "reverse_module": task_module,
            "reverse_name": "reverse",
            "status": status,
        }
    )

    res = mark_task_as_reversed(1)

    assert res is None

    assert Logger.info.call_args_list == [
        call("Running mark_task_as_reversed for 1"),
    ]

    assert Logger.warning.call_args_list == [
        call(f"TaskManager 1 is '{status}', skipping, you could use force=True to reverse it"),
    ]
    assert Logger.error.call_args_list == []

    assert database.list_of("task_manager.TaskManager") == [
        {
            **get_json_obj(model.task_manager),
            "status": status,
        },
    ]

    assert importlib.import_module.call_args_list == []
    assert AsyncResult.revoke.call_args_list == []


# When: TaskManager last_run is less than the tolerance, force is True
# Then: it's rescheduled, the tolerance is ignored
@pytest.mark.parametrize("status", ["PENDING", "CANCELLED", "PAUSED", "ABORTED", "ERROR", "SCHEDULED"])
@pytest.mark.parametrize(param_names, sorted(random.choices(params, k=1)))
def test_force_true(database, arrange, task_module, task_name, get_json_obj, status):

    model = arrange(
        {
            "task_module": task_module,
            "task_name": task_name,
            "reverse_module": task_module,
            "reverse_name": "reverse",
            "status": status,
        }
    )

    res = mark_task_as_reversed(1, force=True)

    assert res is None

    assert Logger.info.call_args_list == [
        call("Running mark_task_as_reversed for 1"),
        call("TaskManager 1 marked as REVERSED"),
    ]

    assert Logger.warning.call_args_list == []
    assert Logger.error.call_args_list == []

    assert database.list_of("task_manager.TaskManager") == [
        {
            **get_json_obj(model.task_manager),
            "status": "REVERSED",
        },
    ]
    assert AsyncResult.revoke.call_args_list == [call(terminate=True)]
