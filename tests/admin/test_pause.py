from unittest.mock import MagicMock, call

import pytest

from task_manager.django import tasks
from task_manager.django.admin import pause

param_names = "task_module,task_name,get_call_args_list"


@pytest.fixture(autouse=True)
def setup(db, monkeypatch):
    monkeypatch.setattr("task_manager.django.tasks.mark_task_as_paused.delay", MagicMock())

    yield


@pytest.fixture
def arrange(database, fake):

    def _arrange(n):
        model = database.create(task_manager=n)
        return model, database.get_model("task_manager.TaskManager").objects.filter()

    yield _arrange


# When: 0 TaskManager's
# Then: nothing happens
def test_with_0(database, arrange):
    _, queryset = arrange(0)

    res = pause(None, None, queryset)

    assert res is None

    assert database.list_of("task_manager.TaskManager") == []
    assert tasks.mark_task_as_paused.delay.call_args_list == []


# When: 2 TaskManager's
# Then: two tasks are scheduled
def test_with_2(database, arrange, get_json_obj):

    model, queryset = arrange(2)

    res = pause(None, None, queryset)

    assert res is None

    assert database.list_of("task_manager.TaskManager") == get_json_obj(model.task_manager)
    assert tasks.mark_task_as_paused.delay.call_args_list == [call(1), call(2)]
