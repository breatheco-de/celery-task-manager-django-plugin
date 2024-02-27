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


@pytest.fixture(autouse=True)
def setup(db, monkeypatch):
    monkeypatch.setattr("task_manager.django.tasks.mark_task_as_cancelled.delay", MagicMock())
    monkeypatch.setattr("task_manager.django.tasks.mark_task_as_pending.delay", MagicMock())

    yield


@pytest.fixture
def arrange(database, fake):

    def _arrange(n, data={}):
        model = database.create(task_manager=(n, data))
        return model

    yield _arrange


@pytest.fixture
def patch(monkeypatch):
    def handler(clean_older_tasks=False, rerun_pending_tasks=False, daily_report=False):
        if clean_older_tasks is False:
            monkeypatch.setattr("task_manager.management.commands.task_manager.Command.clean_older_tasks", MagicMock())

        if rerun_pending_tasks is False:
            monkeypatch.setattr(
                "task_manager.management.commands.task_manager.Command.rerun_pending_tasks", MagicMock()
            )

        if daily_report is False:
            monkeypatch.setattr("task_manager.management.commands.task_manager.Command.daily_report", MagicMock())

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

    _ = arrange(2)

    set_datetime(utc_now + delta)

    command = Command()
    res = command.handle()

    assert res is None
    assert database.list_of("task_manager.TaskManager") == []


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
