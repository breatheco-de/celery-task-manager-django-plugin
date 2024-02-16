import logging
from typing import Type

from celery.result import AsyncResult
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import TaskManager

logger = logging.getLogger(__name__)


@receiver(pre_delete, sender=TaskManager)
def unschedule_task(sender: Type[TaskManager], instance: TaskManager, **kwargs):
    if instance.status == "SCHEDULED" and instance.task_id:
        AsyncResult(instance.task_id).revoke()
