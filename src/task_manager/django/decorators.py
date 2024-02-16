from typing import Any

from django.db import transaction

from task_manager.core.decorators import Task as BaseTask

from .models import TaskManager

__all__ = ["task"]


class Task(BaseTask):

    def _get_task_manager(self, task_manager_pk: int):
        return TaskManager.objects.filter(id=task_manager_pk).first()

    def _create_task_manager(self, **kwargs):
        return TaskManager.objects.create(**kwargs)

    def _update_task_manager(self, x: TaskManager, **kwargs) -> TaskManager:
        for k, v in kwargs.items():
            setattr(x, k, v)

        x.save()

        return x

    def _get_transaction_context(self, x: TaskManager) -> Any:
        return transaction.atomic()

    def _get_transaction_id(self, x: TaskManager) -> Any:
        return transaction.savepoint()

    def _rollback_transaction(self, x: TaskManager, id: Any) -> Any:
        return transaction.savepoint_rollback(id)


def task(*args, **kwargs):
    """Task wrapper that allows to use transactions, fallback and reverse functions.

    `Examples`
    ```py
    def my_reverse(*args, **kwargs):
        \"\"\"This is executed when someone reverse this task.\"\"\"

        pass


    def my_fallback(*args, **kwargs):
        \"\"\"This is executed when the task fails.\"\"\"

        pass


    @task(transaction=True, fallback=my_fallback, reverse=my_reverse)
    def my_task(*args, **kwargs):
        \"\"\"Your task, if it fails, transaction=True will made a rollback
        in the database, then fallback will be executed, if the task is
        canceled, cancel will be executed.
        \"\"\"

        pass
    """

    return Task(*args, **kwargs)
