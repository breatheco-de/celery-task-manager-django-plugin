from datetime import UTC, datetime
from typing import Any, Callable

from dateutil.relativedelta import relativedelta

from task_manager.core.actions import get_fn_desc, parse_payload
from task_manager.django.models import ScheduledTask

delta_units = {
    "s": lambda n: relativedelta(seconds=n),
    "m": lambda n: relativedelta(minutes=n),
    "h": lambda n: relativedelta(hours=n),
    "d": lambda n: relativedelta(days=n),
    "w": lambda n: relativedelta(weeks=n),
}


def schedule_task(task: Callable, eta: str) -> Callable[..., None]:
    """
    Schedule a task.

    ```py
    # You should declare globally this handler
    schedule_my_task_1d = schedule_task(my_task, '1d')

    # Then, you should use it in a function
    schedule_my_task_1d(1, 2, 3, name='my_task')
    ```

    ```py
    ```
    """

    if callable(task) is False:
        raise ValueError("Task must be callable")

    if hasattr(task, "delay") is False:
        raise ValueError("Task must be a Celery task")

    number = eta[:-1]
    unit = eta[-1]

    if number.isnumeric() is False:
        raise ValueError("ETA value must be a number.")

    handler = delta_units.get(unit, None)
    if handler is None:
        raise ValueError(f"ETA unit must be one of {', '.join(delta_units.keys())}.")

    module_name, function_name = get_fn_desc(task)

    def create_schedule_instance(*args: Any, **kwargs: Any):
        delta = handler(number)
        now = datetime.now(tz=UTC)

        arguments = parse_payload(
            {
                "args": args,
                "kwargs": kwargs,
            }
        )

        ScheduledTask.objects.create(
            task_module=module_name,
            task_name=function_name,
            arguments=arguments,
            duration=delta,
            eta=now + delta,
        )

    return create_schedule_instance


aaa = schedule_task()

aaa()
