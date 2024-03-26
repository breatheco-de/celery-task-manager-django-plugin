import random
from datetime import timedelta
from unittest.mock import MagicMock, call

import pytest
from django.utils import timezone
from faker import Faker

from task_manager.django.actions import ScheduledTaskManager, schedule_task

# enable this file to use the database
pytestmark = pytest.mark.usefixtures("db")
fake = Faker()
UNITS = ["s", "m", "h", "d", "w"]
DELTA_UNITS = {
    "s": lambda n: timedelta(seconds=n),
    "m": lambda n: timedelta(minutes=n),
    "h": lambda n: timedelta(hours=n),
    "d": lambda n: timedelta(days=n),
    "w": lambda n: timedelta(weeks=n),
}


class Task:
    @staticmethod
    def delay():
        return "Kawaki"


def fn():
    pass


class TestScheduleTask:

    def test_proxy(self, monkeypatch):
        m1 = MagicMock()
        m2 = MagicMock()
        m3 = MagicMock(return_value=None)
        monkeypatch.setattr(ScheduledTaskManager, "__init__", m3)

        schedule_task(m1, m2)

        assert m3.call_args_list == [call(m1, m2)]

    def test_no_eta_unit(self):
        m1 = MagicMock()
        m2 = MagicMock()

        with pytest.raises(ValueError, match=f"ETA unit must be one of {', '.join(UNITS)}."):
            schedule_task(m1, m2)

    @pytest.mark.parametrize("unit", UNITS)
    def test_no_eta_value(self, fake, unit):
        m1 = MagicMock()
        n = fake.slug()[0]

        with pytest.raises(ValueError, match="ETA value must be a number."):
            schedule_task(m1, n + unit)

    def test_no_callable(self):
        unit = random.choice(UNITS)
        n = random.randint(1, 100)

        with pytest.raises(ValueError, match="Task must be callable."):
            schedule_task(n, str(n) + unit)

    def test_regular_fn(self):
        unit = random.choice(UNITS)
        n = random.randint(1, 100)

        with pytest.raises(ValueError, match="Task must be a Celery task."):
            schedule_task(fn, str(n) + unit)

    def test_it_returns_a_manager(self):
        unit = random.choice(UNITS)
        n = random.randint(1, 100)
        x = schedule_task(Task, str(n) + unit)

        assert isinstance(x, ScheduledTaskManager)
        assert x._eta_unit == unit
        assert x._eta_number == n
        assert x._eta == f"{n}{unit}"
        assert x._module_name == "tests.django.actions.test_schedule_task"
        assert x._function_name == "Task"

        # it will be checked below
        assert callable(x._handler)


class TestScheduleTaskManager:

    @pytest.mark.parametrize("unit", UNITS)
    def test_it_returns_the_properly_handler(self, unit):
        n = random.randint(1, 100)
        x = ScheduledTaskManager(Task, str(n) + unit)

        assert isinstance(x, ScheduledTaskManager)
        assert x._eta_unit == unit
        assert x._eta_number == n
        assert x._eta == f"{n}{unit}"
        assert x._module_name == "tests.django.actions.test_schedule_task"
        assert x._function_name == "Task"

        # it will be checked
        assert callable(x._handler)

        assert x._handler(n) == DELTA_UNITS[unit](n)

    def test_copy(self):
        unit = random.choice(UNITS)
        n = random.randint(1, 100)

        x = ScheduledTaskManager(Task, str(n) + unit)
        y = x.copy()

        assert isinstance(y, ScheduledTaskManager)
        assert x._eta_unit == y._eta_unit
        assert x._eta_number == y._eta_number
        assert x._eta == y._eta
        assert x._module_name == y._module_name
        assert x._function_name == y._function_name
        assert x._handler == y._handler

        x._eta_unit = fake.slug()
        x._eta_number = fake.slug()
        x._eta = fake.slug()
        x._module_name = fake.slug()
        x._function_name = fake.slug()
        x._handler = fake.slug()

        assert x._eta_unit != y._eta_unit
        assert x._eta_number != y._eta_number
        assert x._eta != y._eta
        assert x._module_name != y._module_name
        assert x._function_name != y._function_name
        assert x._handler != y._handler

    @pytest.mark.parametrize("overwrite", [None, False])
    def test_eta_overwride_is_false(self, overwrite):
        unit1 = random.choice(UNITS)
        n1 = random.randint(1, 100)

        unit2 = random.choice(UNITS)
        n2 = random.randint(1, 100)

        x = ScheduledTaskManager(Task, str(n1) + unit1)
        y = x.eta(str(n2) + unit2, overwrite=overwrite)

        assert hash(x) != hash(y)

        assert x._eta_unit == unit1
        assert x._eta_number == n1
        assert x._eta == str(n1) + unit1
        assert x._handler(n1) == DELTA_UNITS[unit1](n1)

        assert y._eta_unit == unit2
        assert y._eta_number == n2
        assert y._eta == str(n2) + unit2
        assert y._handler(n2) == DELTA_UNITS[unit2](n2)

        assert x._module_name == y._module_name
        assert x._function_name == y._function_name

    def test_eta_overwride_is_true(self):
        overwrite = True
        unit1 = random.choice(UNITS)
        n1 = random.randint(1, 100)

        unit2 = random.choice(UNITS)
        n2 = random.randint(1, 100)

        x = ScheduledTaskManager(Task, str(n1) + unit1)
        y = x.eta(str(n2) + unit2, overwrite=overwrite)

        assert hash(x) == hash(y)

        assert x._eta_unit == unit2
        assert x._eta_number == n2
        assert x._eta == str(n2) + unit2

        assert x._eta_unit == y._eta_unit
        assert x._eta_number == y._eta_number
        assert x._eta == y._eta
        assert x._module_name == y._module_name
        assert x._function_name == y._function_name
        assert x._handler == y._handler

    def test__call__(self, monkeypatch, get_args, get_kwargs):
        r = "🟣"
        m = MagicMock(return_value=r)
        monkeypatch.setattr(ScheduledTaskManager, "call", m)
        args = get_args(3)
        kwargs = get_kwargs(3)

        unit = random.choice(UNITS)
        n = random.randint(1, 100)

        x = ScheduledTaskManager(Task, str(n) + unit)
        y = x(*args, **kwargs)

        assert y == r

        assert isinstance(x, ScheduledTaskManager)
        assert x._eta_unit == unit
        assert x._eta_number == n
        assert x._eta == f"{n}{unit}"
        assert x._module_name == "tests.django.actions.test_schedule_task"
        assert x._function_name == "Task"

        # it will be checked
        assert callable(x._handler)

        assert x._handler(n) == DELTA_UNITS[unit](n)

    def test_call(self, get_args, get_kwargs, database, set_datetime):
        now = timezone.now()
        set_datetime(now)

        args = get_args(3)
        kwargs = get_kwargs(3)

        unit = random.choice(UNITS)
        n = random.randint(1, 100)

        x = ScheduledTaskManager(Task, str(n) + unit)
        y = x.call(*args, **kwargs)

        assert y is None

        assert isinstance(x, ScheduledTaskManager)
        assert x._eta_unit == unit
        assert x._eta_number == n
        assert x._eta == f"{n}{unit}"
        assert x._module_name == "tests.django.actions.test_schedule_task"
        assert x._function_name == "Task"

        # it will be checked
        assert callable(x._handler)

        assert x._handler(n) == DELTA_UNITS[unit](n)
        assert database.list_of("task_manager.ScheduledTask") == [
            {
                "arguments": {
                    "args": list(args),
                    "kwargs": kwargs,
                },
                "duration": x._handler(n),
                "eta": now + x._handler(n),
                "id": 1,
                "status": "PENDING",
                "task_module": "tests.django.actions.test_schedule_task",
                "task_name": "Task",
            },
        ]

    @pytest.mark.asyncio
    async def test_acall(self, get_args, get_kwargs, database, set_datetime):
        now = timezone.now()
        set_datetime(now)

        args = get_args(3)
        kwargs = get_kwargs(3)

        unit = random.choice(UNITS)
        n = random.randint(1, 100)

        x = ScheduledTaskManager(Task, str(n) + unit)
        y = await x.acall(*args, **kwargs)

        assert y is None

        assert isinstance(x, ScheduledTaskManager)
        assert x._eta_unit == unit
        assert x._eta_number == n
        assert x._eta == f"{n}{unit}"
        assert x._module_name == "tests.django.actions.test_schedule_task"
        assert x._function_name == "Task"

        # it will be checked
        assert callable(x._handler)

        assert x._handler(n) == DELTA_UNITS[unit](n)
        assert await database.alist_of("task_manager.ScheduledTask") == [
            {
                "arguments": {
                    "args": list(args),
                    "kwargs": kwargs,
                },
                "duration": x._handler(n),
                "eta": now + x._handler(n),
                "id": 1,
                "status": "PENDING",
                "task_module": "tests.django.actions.test_schedule_task",
                "task_name": "Task",
            },
        ]
