from celery.app.task import Task as CeleryTask

from .decorators import TaskManager


class Task(CeleryTask):
    task_manager: TaskManager

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
