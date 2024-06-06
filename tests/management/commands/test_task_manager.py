from datetime import timedelta
from unittest.mock import MagicMock, call

import pytest
from django.utils import timezone

from task_manager.django import tasks
from task_manager.management.commands.task_manager import Command

param_names = "task_module,task_name,get_call_args_list"


clean_older_tasks = {
    "short_delta_list": [timedelta(hours=n * 2) for n in range(1, 23)],
    "long_delta_list": [timedelta(hours=n * 2) for n in range(25, 48)],
}

rerun_pending_tasks = {
    "short_delta_list": [timedelta(minutes=n * 2) for n in range(1, 14)],
    "long_delta_list": [timedelta(minutes=n * 2) for n in range(16, 30)],
}

run_scheduled_tasks = {
    "short_delta_list": [timedelta(minutes=n * 2) for n in range(1, 3)],
}


@pytest.fixture(autouse=True)
def setup(db, monkeypatch):
    monkeypatch.setattr("task_manager.django.tasks.mark_task_as_cancelled.delay", MagicMock())
    monkeypatch.setattr("task_manager.django.tasks.mark_task_as_pending.delay", MagicMock())

    yield


@pytest.fixture
def arrange(database):

    def _arrange(n1, data1={}, n2=0, data2={}):
        model = database.create(task_manager=(n1, data1), scheduled_task=(n2, data2))
        return model

    yield _arrange


@pytest.fixture
def patch(monkeypatch):
    def handler(clean_older_tasks=False, rerun_pending_tasks=False, daily_report=False, run_scheduled_tasks=False):
        if clean_older_tasks is False:
            monkeypatch.setattr("task_manager.management.commands.task_manager.Command.clean_older_tasks", MagicMock())

        if rerun_pending_tasks is False:
            monkeypatch.setattr(
                "task_manager.management.commands.task_manager.Command.rerun_pending_tasks", MagicMock()
            )

        if daily_report is False:
            monkeypatch.setattr("task_manager.management.commands.task_manager.Command.daily_report", MagicMock())

        if run_scheduled_tasks is False:
            monkeypatch.setattr(
                "task_manager.management.commands.task_manager.Command.run_scheduled_tasks", MagicMock()
            )

    return handler


# When: 0 TaskManager's
# Then: nothing happens
def test_clean_older_tasks__with_0(database, patch):
    patch(clean_older_tasks=True, rerun_pending_tasks=False, daily_report=False)

    command = Command()
    res = command.handle()

    assert res is None
    assert database.list_of("task_manager.TaskManager") == []


# When: 2 TaskManager's, one of them is not old enough
# Then: nothing happens
def test_clean_older_tasks__with_2(database, arrange, set_datetime, patch, get_json_obj):
    patch(clean_older_tasks=True, rerun_pending_tasks=False, daily_report=False)

    utc_now = timezone.now()
    set_datetime(utc_now)

    model = arrange(2)

    command = Command()
    res = command.handle()

    assert res is None
    assert database.list_of("task_manager.TaskManager") == get_json_obj(model.task_manager)


# When: 2 TaskManager's, one of them is not old enough yet
# Then: nothing happens
@pytest.mark.parametrize("delta", clean_older_tasks["short_delta_list"])
def test_clean_older_tasks__with_2__is_not_so_old_yet(database, arrange, set_datetime, delta, patch, get_json_obj):
    patch(clean_older_tasks=True, rerun_pending_tasks=False, daily_report=False)

    utc_now = timezone.now()

    model = arrange(2)

    set_datetime(utc_now + delta)

    command = Command()
    res = command.handle()

    assert res is None
    assert database.list_of("task_manager.TaskManager") == get_json_obj(model.task_manager)


# When: 2 TaskManager's, all tasks is old
# Then: remove all tasks
@pytest.mark.parametrize("delta", clean_older_tasks["long_delta_list"])
def test_clean_older_tasks__with_2__all_tasks_is_old(database, arrange, set_datetime, delta, patch):
    patch(clean_older_tasks=True, rerun_pending_tasks=False, daily_report=False)

    utc_now = timezone.now()

    _ = arrange(2, {"status": "DONE"})

    set_datetime(utc_now + delta)

    command = Command()
    res = command.handle()

    assert res is None
    assert database.list_of("task_manager.TaskManager") == []


# When: 2 TaskManager's, all tasks is old
# Then: remove all tasks
@pytest.mark.parametrize("delta", clean_older_tasks["long_delta_list"][:1])
@pytest.mark.parametrize("status", ["PENDING", "PAUSED", "SCHEDULED"])
def test_clean_older_tasks__with_2__all_tasks_is_old__but_these_statuses_cannot_be_deleted(
    database, arrange, set_datetime, delta, patch, status, get_json_obj
):
    patch(clean_older_tasks=True, rerun_pending_tasks=False, daily_report=False)

    utc_now = timezone.now()

    model = arrange(2, {"status": status})

    set_datetime(utc_now + delta)

    command = Command()
    res = command.handle()

    assert res is None
    assert database.list_of("task_manager.TaskManager") == get_json_obj(model.task_manager)


# When: 0 TaskManager's
# Then: nothing happens
def test_rerun_pending_tasks__with_0(database, capsys, patch, get_json_obj):
    patch(clean_older_tasks=False, rerun_pending_tasks=True, daily_report=False)

    command = Command()
    res = command.handle()

    assert res is None
    assert database.list_of("task_manager.TaskManager") == []
    assert tasks.mark_task_as_pending.delay.call_args_list == []

    captured = capsys.readouterr()
    assert captured.out == "No TaskManager's available to re-run\n"
    assert captured.err == ""


# When: 2 TaskManager's, one of them is not old enough
# Then: nothing happens
def test_rerun_pending_tasks__with_2(database, arrange, set_datetime, capsys, patch, get_json_obj):
    patch(clean_older_tasks=False, rerun_pending_tasks=True, daily_report=False)

    utc_now = timezone.now()
    set_datetime(utc_now)

    model = arrange(2, {"last_run": utc_now})

    command = Command()
    res = command.handle()

    assert res is None
    assert database.list_of("task_manager.TaskManager") == get_json_obj(model.task_manager)
    assert tasks.mark_task_as_pending.delay.call_args_list == []

    captured = capsys.readouterr()
    assert captured.out == "No TaskManager's available to re-run\n"
    assert captured.err == ""


# When: 2 TaskManager's, one of them is not old enough yet
# Then: nothing happens
@pytest.mark.parametrize("delta", rerun_pending_tasks["short_delta_list"])
def test_rerun_pending_tasks__with_2__is_not_so_old_yet(
    database, arrange, set_datetime, delta, capsys, patch, get_json_obj
):
    patch(clean_older_tasks=False, rerun_pending_tasks=True, daily_report=False)

    utc_now = timezone.now()
    set_datetime(utc_now)

    model = arrange(2, {"last_run": utc_now - delta})

    command = Command()
    res = command.handle()

    assert res is None
    assert database.list_of("task_manager.TaskManager") == get_json_obj(model.task_manager)
    # assert tasks.mark_task_as_pending.delay.call_args_list == []

    captured = capsys.readouterr()
    assert captured.out == "No TaskManager's available to re-run\n"
    assert captured.err == ""


# When: 2 TaskManager's, all tasks is old
# Then: remove all tasks
@pytest.mark.parametrize("delta", rerun_pending_tasks["long_delta_list"])
def test_rerun_pending_tasks__with_2__all_tasks_is_old(
    database, arrange, set_datetime, delta, capsys, patch, get_json_obj
):
    patch(clean_older_tasks=False, rerun_pending_tasks=True, daily_report=False)

    utc_now = timezone.now()
    set_datetime(utc_now)

    model = arrange(2, {"last_run": utc_now - delta})

    command = Command()
    res = command.handle()

    assert res is None
    assert database.list_of("task_manager.TaskManager") == get_json_obj(model.task_manager)
    assert tasks.mark_task_as_pending.delay.call_args_list == [call(1, force=True), call(2, force=True)]

    captured = capsys.readouterr()
    assert captured.out == "Rerunning TaskManager's 1, 2\n"
    assert captured.err == ""


# When: 0 ScheduledTask's
# Then: nothing happens
def testrun_scheduled_tasks__has_not_any_scheduled(database, arrange, set_datetime, capsys, patch, get_json_obj):
    patch(clean_older_tasks=False, rerun_pending_tasks=False, daily_report=False, run_scheduled_tasks=True)

    utc_now = timezone.now()
    set_datetime(utc_now)

    model = arrange(0, {})

    command = Command()
    res = command.handle()

    assert res is None
    assert database.list_of("task_manager.TaskManager") == get_json_obj(model.task_manager)
    assert tasks.mark_task_as_pending.delay.call_args_list == []

    captured = capsys.readouterr()
    assert captured.out == "Successfully scheduled 0 Tasks\n"
    assert captured.err == ""


# When: 2 ScheduledTask's, all them in the past
# Then: remove all scheduled tasks, schedule the execution before it
@pytest.mark.parametrize("delta", run_scheduled_tasks["short_delta_list"])
def testrun_scheduled_tasks__all_them_pending_in_the_past(
    database, arrange, set_datetime, delta, capsys, patch, get_json_obj, get_args, get_kwargs
):
    patch(clean_older_tasks=False, rerun_pending_tasks=False, daily_report=False, run_scheduled_tasks=True)

    utc_now = timezone.now()
    set_datetime(utc_now)
    args = get_args(3)
    kwargs = get_kwargs(3)

    model = arrange(
        0,
        {},
        2,
        {
            "status": "PENDING",
            "eta": utc_now - delta,
            "task_module": "task_manager.django.tasks",
            "task_name": "mark_task_as_pending",
            "arguments": {
                "args": list(args),
                "kwargs": kwargs,
            },
        },
    )

    command = Command()
    res = command.handle()

    assert res is None
    assert database.list_of("task_manager.TaskManager") == get_json_obj(model.task_manager)
    assert database.list_of("task_manager.ScheduledTask") == []

    assert tasks.mark_task_as_pending.delay.call_args_list == [call(*args, **kwargs) for _ in range(2)]

    captured = capsys.readouterr()
    assert captured.out == "Successfully scheduled 2 Tasks\n"
    assert captured.err == ""


# When: 2 ScheduledTask's, all them in the past
# Then: remove all scheduled tasks
@pytest.mark.parametrize("status", ["DONE", "CANCELLED"])
@pytest.mark.parametrize("delta", run_scheduled_tasks["short_delta_list"])
def testrun_scheduled_tasks__all_them_not_pending_in_the_past(
    database, arrange, set_datetime, delta, capsys, patch, get_json_obj, get_args, get_kwargs, status
):
    patch(clean_older_tasks=False, rerun_pending_tasks=False, daily_report=False, run_scheduled_tasks=True)

    utc_now = timezone.now()
    set_datetime(utc_now)
    args = get_args(3)
    kwargs = get_kwargs(3)

    model = arrange(
        0,
        {},
        2,
        {
            "status": status,
            "eta": utc_now - delta,
            "task_module": "task_manager.django.tasks",
            "task_name": "mark_task_as_pending",
            "arguments": {
                "args": list(args),
                "kwargs": kwargs,
            },
        },
    )

    command = Command()
    res = command.handle()

    assert res is None
    assert database.list_of("task_manager.TaskManager") == get_json_obj(model.task_manager)
    assert database.list_of("task_manager.ScheduledTask") == []

    assert tasks.mark_task_as_pending.delay.call_args_list == []

    captured = capsys.readouterr()
    assert captured.out == "Successfully scheduled 0 Tasks\n"
    assert captured.err == ""


# When: 2 ScheduledTask's, all them in the past
# Then: remove all scheduled tasks
@pytest.mark.parametrize("delta", run_scheduled_tasks["short_delta_list"])
def testrun_scheduled_tasks__all_them_pending_in_the_future(
    database, arrange, set_datetime, delta, capsys, patch, get_json_obj, get_args, get_kwargs
):
    patch(clean_older_tasks=False, rerun_pending_tasks=False, daily_report=False, run_scheduled_tasks=True)

    utc_now = timezone.now()
    set_datetime(utc_now)
    args = get_args(3)
    kwargs = get_kwargs(3)

    model = arrange(
        0,
        {},
        2,
        {
            "status": "PENDING",
            "eta": utc_now + delta,
            "task_module": "task_manager.django.tasks",
            "task_name": "mark_task_as_pending",
            "arguments": {
                "args": list(args),
                "kwargs": kwargs,
            },
        },
    )

    command = Command()
    res = command.handle()

    assert res is None
    assert database.list_of("task_manager.TaskManager") == get_json_obj(model.task_manager)
    assert database.list_of("task_manager.ScheduledTask") == get_json_obj(model.scheduled_task)

    assert tasks.mark_task_as_pending.delay.call_args_list == []

    captured = capsys.readouterr()
    assert captured.out == "Successfully scheduled 0 Tasks\n"
    assert captured.err == ""
