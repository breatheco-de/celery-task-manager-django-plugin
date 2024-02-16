import functools
import importlib
import inspect
import logging
import traceback
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Optional

import celery
from django.utils import timezone

from .exceptions import AbortTask, ProgrammingError, RetryTask
from .settings import settings

__all__ = ["Task"]

logger = logging.getLogger(__name__)


try:
    from circuitbreaker import CircuitBreakerError

except ImportError:

    class CircuitBreakerError(Exception):
        pass


def parse_payload(payload: dict):
    if not isinstance(payload, dict):
        return payload

    for key in payload.keys():
        # TypeError("string indices must be integers, not 'str'")
        if isinstance(payload[key], datetime):
            payload[key] = payload[key].isoformat().replace("+00:00", "Z")

        elif isinstance(payload[key], Decimal):
            payload[key] = str(payload[key])

        elif isinstance(payload[key], list) or isinstance(payload[key], tuple) or isinstance(payload[key], set):
            array = []
            for item in payload[key]:
                array.append(parse_payload(item))

            payload[key] = array

        elif isinstance(payload[key], dict):
            payload[key] = parse_payload(payload[key])

    return payload


class TaskManager:
    current_page: Optional[int]
    total_pages: Optional[int]
    attempts: int

    task_module: str
    task_name: str

    reverse_module: Optional[str]
    reverse_name: Optional[str]

    exception_module: Optional[str]
    exception_name: Optional[str]

    arguments: dict[Any, Any]
    status: str
    status_message: Optional[str]
    task_id: str

    killed: bool
    last_run: datetime

    started_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class Task(object):

    def __init__(self, *args, **kwargs):
        self.transaction_id = None
        self.is_transaction = kwargs.pop("transaction", False)
        self.fallback = kwargs.pop("fallback", None)
        self.reverse = kwargs.pop("reverse", None)
        self.bind = kwargs.get("bind", False)
        self.priority = kwargs.pop("priority", settings["DEFAULT"])
        kwargs["priority"] = settings["SCHEDULER"]

        if self.fallback and not callable(self.fallback):
            raise ProgrammingError("Fallback must be a callable")

        if self.reverse and not callable(self.reverse):
            raise ProgrammingError("Reverse must be a callable")

        self.parent_decorator = celery.shared_task(*args, **kwargs)

    def get_fn_desc(self, function: Callable) -> tuple[str, str] | tuple[None, None]:
        if not function:
            return None, None

        module_name = inspect.getmodule(function).__name__
        function_name = function.__name__

        return module_name, function_name

    def _get_fn(self, task_module: str, task_name: str) -> Callable | None:
        module = importlib.import_module(task_module)
        return getattr(module, task_name, None)

    def reattempt_settings(self) -> dict[str, datetime]:
        """Return a dict with the settings to reattempt the task."""

        return {"eta": timezone.now() + settings["RETRY_AFTER"]}

    def reattempt(self, task_module: str, task_name: str, attempts: int, args: tuple[Any], kwargs: dict[str, Any]):
        x = self._get_fn(task_module, task_name)
        x.apply_async(args=args, kwargs={**kwargs, "attempts": attempts}, **self.reattempt_settings())

    def circuit_breaker_settings(self, e: CircuitBreakerError) -> dict[str, datetime]:
        """Return a dict with the settings to reattempt the task."""

        return {"eta": timezone.now() + e._circuit_breaker.RECOVERY_TIMEOUT}

    def manage_circuit_breaker(
        self,
        e: CircuitBreakerError,
        task_module: str,
        task_name: str,
        attempts: int,
        args: tuple[Any],
        kwargs: dict[str, Any],
    ):
        x = self._get_fn(task_module, task_name)
        x.apply_async(args=args, kwargs={**kwargs, "attempts": attempts}, **self.circuit_breaker_settings(e))

    def schedule(self, task_module: str, task_name: str, args: tuple[Any], kwargs: dict[str, Any]):
        """Register a task to be executed in the future."""

        x = self._get_fn(task_module, task_name)

        if self.bind:
            args = args[1:]

        return x.apply_async(args=args, kwargs=kwargs, priority=self.priority)

    def _get_task_manager(self, task_manager_id) -> TaskManager | None:
        raise NotImplementedError("You must implement this method")

    def _create_task_manager(self, **kwargs) -> TaskManager:
        raise NotImplementedError("You must implement this method")

    def _update_task_manager(self, x: TaskManager, **kwargs) -> TaskManager:
        raise NotImplementedError("You must implement this method")

    def _get_transaction_context(self, x: TaskManager) -> TaskManager:
        raise NotImplementedError("You must implement this method")

    def _get_transaction_id(self, x: TaskManager) -> Any:
        raise None

    def _rollback_transaction(self, x: TaskManager, id: Any) -> Any:
        raise NotImplementedError("You must implement this method")

    def __call__(self, function):
        self.function = function

        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            task_module, task_name = self.get_fn_desc(function)
            reverse_module, reverse_name = self.get_fn_desc(self.reverse)
            arguments = parse_payload(
                {
                    "args": args[1:] if self.bind else args,
                    "kwargs": kwargs,
                }
            )

            page = kwargs.get("page", 0)
            total_pages = kwargs.get("total_pages", 1)
            attempts = kwargs.get("attempts", None)
            task_manager_id = kwargs.get("task_manager_id", None)
            last_run = timezone.now()

            x = None
            if task_manager_id:
                x = self._get_task_manager(task_manager_id)

            created = False
            if x is None:
                created = True
                x = self._create_task_manager(
                    task_module=task_module,
                    task_name=task_name,
                    attempts=1,
                    reverse_module=reverse_module,
                    reverse_name=reverse_name,
                    arguments=arguments,
                    status="SCHEDULED",
                    current_page=page,
                    total_pages=total_pages,
                    last_run=last_run,
                )

                kwargs["task_manager_id"] = x.id

            update = {}

            if not created and x.status == "SCHEDULED":
                update["started_at"] = timezone.now()
                update["status"] = "PENDING"

            if not created:
                update["current_page"] = page + 1
                update["last_run"] = last_run

                if attempts:
                    update["last_run"] = attempts + 1

                self._update_task_manager(x, **update)
                update = {}

            if x.status in ["CANCELLED", "REVERSED", "PAUSED", "ABORTED", "DONE"]:
                self._update_task_manager(x, killed=True)
                return

            if self.bind:
                t = args[0]
                t.task_manager = x

            res = None
            if self.is_transaction is True:
                with self._get_transaction_context(x):
                    sid = self._get_transaction_id(x)
                    try:
                        res = self._execute(self, x, function, task_module, task_name, *args, **kwargs)

                    except Exception as e:
                        self._manage_exceptions(e, x, arguments, sid=sid, *args, **kwargs)

            else:
                try:
                    res = self._execute(self, x, function, task_module, task_name, *args, **kwargs)

                except Exception as e:
                    self._manage_exceptions(e, x, arguments, *args, **kwargs)

            if x.total_pages == x.current_page:
                self._update_task_manager(x, status="DONE")

            return res

        self.instance = self.parent_decorator(wrapper)
        return self.instance

    def _execute(self, x: TaskManager, function: Callable, task_module: str, task_name: str, *args, **kwargs):
        if x.status == "SCHEDULED":
            result = self.schedule(task_module, task_name, args, kwargs)
            self._update_task_manager(x, task_id=result.id)
            return

        else:
            self._update_task_manager(x, status_message="")
            return function(*args, **kwargs)

    def _manage_exceptions(
        self, e: Exception, x: TaskManager, arguments: dict, transaction: bool = False, *args, **kwargs
    ):
        error = None

        if isinstance(e, CircuitBreakerError):
            x.status_message = str(e)[:255]

            # TODO: think in this implementation
            if x.attempts >= settings["RETRIES_LIMIT"]:
                logger.exception(str(e))
                self._update_task_manager(
                    x,
                    status="ERROR",
                    exception_module=e.__class__.__module__,
                    exception_name=e.__class__.__name__,
                )

            else:
                logger.warning(str(e))
                x.save()

                self.manage_circuit_breaker(
                    e, x.task_module, x.task_name, x.attempts, arguments["args"], arguments["kwargs"]
                )

            # it don't raise anything to manage the reattempts with the task manager
            return

        elif isinstance(e, RetryTask):
            x.status_message = str(e)[:255]

            if x.attempts >= settings["RETRIES_LIMIT"]:
                if e.log:
                    logger.exception(str(e))

                self._update_task_manager(
                    x,
                    status="ERROR",
                    exception_module=e.__class__.__module__,
                    exception_name=e.__class__.__name__,
                )

            else:
                if e.log:
                    logger.warning(str(e))

                self.reattempt(x.task_module, x.task_name, x.attempts, arguments["args"], arguments["kwargs"])

            # it don't raise anything to manage the reattempts with the task manager
            return

        elif isinstance(e, AbortTask):
            self._update_task_manager(
                x,
                status="ABORTED",
                status_message=str(e)[:255],
            )

            if e.log:
                logger.exception(str(e))

            # avoid reattempts
            return

        else:
            traceback.print_exc()

            self._rollback_transaction(x, self.transaction_id)

            error = str(e)[:255]
            exception = e

            logger.exception(str(e))

        if error:
            self._update_task_manager(
                x,
                status="ERROR",
                exception_module=e.__class__.__module__,
                exception_name=e.__class__.__name__,
            )

            # fallback
            if self.fallback:
                return self.fallback(*args, **kwargs, exception=exception)

            # behavior by default
            return
