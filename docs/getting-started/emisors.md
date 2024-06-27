# Emisors

Emisor is a [Django Signals](https://docs.djangoproject.com/en/5.0/topics/signals/) wrapper that saves the errors in `SignalError` table for `send`, `send_robust`, `asend`, `asend_robust` and the cases `delay` and `adelay` appear within `TaskManager` table.

## Setting up

### Change it

```py
from django.dispatch import Signal

user_specialty_saved = Signal()
```

### For it

```py
from task_manager.django.dispatch import Emisor

emisor = Emisor('my.unique.id')

user_specialty_saved = emisor.signal('user_specialty_saved')
```

## What's new

### delay

Send a signal to be executed within Celery synchronously and save the result within `TaskManager` table. It requires `sender` and `instance` param with id already set.

### adelay

Send a signal to be executed within Celery asynchronously and save the result within `TaskManager` table. It requires `sender` and `instance` param with id already set.

## See all signal errors in Django Admin

Go to `/admin/task_manager/signalerror/`.
