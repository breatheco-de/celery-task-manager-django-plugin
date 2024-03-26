# Task

`task` is a regular decorator that wraps a Celery `shared_task` to use Task Manager. It could track and monitor your tasks executions and protect your task queue against a Redis shutdown process.

## Parameters

All parameters are the same that get a celery `shared_task`.

## Examples

```py
import logging

from task_manager.core.exceptions import AbortTask, RetryTask
from task_manager.django.decorators import task

from breathecode.utils.decorators import TaskPriority
from breathecode.services.google_cloud.storage import Storage
from .models import Asset


logger = logging.getLogger(__name__)


@task(priority=TaskPriority.ACADEMY.value)
def async_delete_asset_images(asset_slug, **_):

    asset = Asset.get_by_slug(asset_slug)
    if asset is None:
        raise RetryTask(f'Asset with slug {asset_slug} not found')

    storage = Storage()
    for img in asset.images.all():
        if img.assets.count() == 1 and img.asset.filter(slug=asset_slug).exists():
            extension = pathlib.Path(img.name).suffix
            cloud_file = storage.file(asset_images_bucket(), img.hash + extension)
            cloud_file.delete()
            img.delete()
        else:
            img.assets.remove(asset)

        logger.info(f'Image {img.name} was deleted')
```

## Available exceptions

Task manager listens for our exceptions, and it modifies the behavior of the execution, all exceptions that are not included in this list are marked as an `ERROR`.

### AbortTask

Abort the execution of this task, because the requirements were not met.

### RetryTask

Mark this task to be retried, due to the database does not include the required content yet.

### CircuitBreakerError

Mark this task to be retried. due to an error that occurred in another service.

## See all executions in Django Admin

Go to `/admin/task_manager/taskmanager/` you should see, manage and find all data collected through of Task Manager.
