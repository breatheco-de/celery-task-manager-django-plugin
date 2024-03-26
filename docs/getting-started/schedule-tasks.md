# Schedule Tasks

You should schedule a execution to be executed after a provided time, you need to have set-up `task_manager` command to use this feature. It is used frequently to make sure that the execution will be executed even if Redis was turned off.

## Using `schedule_task`

It returns an instance of `ScheduledTaskManager`.

## arguments

- `task`: a Celery task.
- `eta`: when it will be executed, it requires a number + a unit, example: `2w` is 2 weeks.

## ETA units

- `s`: seconds.
- `m`: minutes.
- `h`: hours.
- `d`: days.
- `w`: weeks.

## Examples

```py
import logging
from task_manager.django.actions import schedule_task
from .tasks import async_remove_from_organization


logger = logging.getLogger(__name__)


@receiver(pre_delete, sender=CohortUser)
def delete_cohort_user(sender, instance, **_):
    # never ending cohorts cannot be in synch with github
    if instance.cohort.never_ends:
        return None

    logger.debug('Cohort user deleted, removing from organization')
    args = (instance.cohort.id, instance.user.id)
    kwargs = {'force': True}

    manager = schedule_task(async_remove_from_organization, '1w')
    if not manager.exists(*args, **kwargs):
        manager.call(*args, **kwargs)
```

## ScheduledTaskManager

This class manages the scheduling tasks

### constructor

#### Arguments

- `task`: a Celery task.
- `eta`: when it will be executed, it requires a number + a unit, example: `2w` is 2 weeks.

### call

Schedule a task execution. It accepts the arguments whichever you should pass to `delay` method.

### **call**

Shortcut method that uses `call` method internally.

### acall

Asynchronous version of `call` method.

### exists

Return `True` if the task exists, `False` otherwise. It accepts the arguments whichever you should pass to `delay` method.

### filter

Get a queryset of ScheduledTask's. It accepts the arguments whichever you should pass to `delay` method.

## See all scheduled tasks in Django Admin

Go to `/admin/task_manager/scheduledtask/`.
