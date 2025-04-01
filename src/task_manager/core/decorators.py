import functools
import importlib
import logging
import traceback
from datetime import datetime
from typing import Any, Callable, Optional

import celery
from django.utils import timezone

from task_manager.core.actions import get_fn_desc, parse_payload

from .exceptions import AbortTask, ProgrammingError, RetryTask
from .settings import settings

# from task_manager.core.constants import DuplicationPolicy


__all__ = ["Task", "TaskManager"]

logger = logging.getLogger(__name__)


try:
    from circuitbreaker import CircuitBreakerError

except ImportError:

    class CircuitBreakerError(Exception):
        pass


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
    task_id: Optional[str]
    priority: Optional[int]

    killed: bool
    fixed: bool
    last_run: datetime

    started_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class Task(object):
    priority: int
    bind: bool
    fallback: Optional[Callable]
    reverse: Optional[Callable]
    transaction_id: Optional[Any]
    is_transaction: bool
    # duplication_policy: Optional[str]

    def __init__(self, *args, **kwargs):
        self.transaction_id = None
        self.is_transaction = kwargs.pop("transaction", False)
        self.fallback = kwargs.pop("fallback", None)
        self.reverse = kwargs.pop("reverse", None)
        self.bind = kwargs.get("bind", False)
        self.priority = kwargs.pop("priority", settings["DEFAULT"])
        kwargs["ignore_result"] = kwargs.pop("ignore_result", True)
        # self.duplication_policy = kwargs.pop("duplication_policy", settings["DUPLICATION_POLICY"])
        # if self.duplication_policy is not None and self.duplication_policy not in [x.value for x in DuplicationPolicy]:
        #     raise ValueError(
        #         f"Invalid duplication policy: {self.duplication_policy}, must be one of: {', '.join([x.value for x in DuplicationPolicy])}"
        #     )

        kwargs["priority"] = settings["SCHEDULER"]

        if self.fallback and not callable(self.fallback):
            raise ProgrammingError("Fallback must be a callable")

        if self.reverse and not callable(self.reverse):
            raise ProgrammingError("Reverse must be a callable")

        self.parent_decorator = celery.shared_task(*args, **kwargs)

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
            task_module, task_name = get_fn_desc(function)
            reverse_module, reverse_name = get_fn_desc(self.reverse)
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
                    priority=self.priority,
                )

                kwargs["task_manager_id"] = x.id

            update = {}

            if created:
                result = self.schedule(task_module, task_name, args, kwargs)
                self._update_task_manager(x, task_id=result.id)
                return

            if x.status in ["CANCELLED", "REVERSED", "PAUSED", "ABORTED", "DONE"]:
                self._update_task_manager(x, killed=True)
                return

            if x.status == "SCHEDULED":
                update["started_at"] = timezone.now()
                update["status"] = "PENDING"

            if attempts:
                update["attempts"] = attempts + 1
                current_page = page

            else:
                update["current_page"] = page + 1
                current_page = update["current_page"]

            update["last_run"] = last_run

            # Add safety check for maximum pages
            if current_page > x.total_pages:
                update["status"] = "ERROR"
                update["status_message"] = f"Task exceeded maximum pages ({current_page}/{x.total_pages})"

            self._update_task_manager(x, **update)
            update = {}

            if self.bind:
                t = args[0]
                t.task_manager = x

            res = None
            if self.is_transaction is True:
                error = None
                with self._get_transaction_context(x):
                    self.transaction_id = self._get_transaction_id(x)
                    try:
                        res = self._execute(x, function, *args, **kwargs)

                    except Exception as e:
                        error = e
                        if type(e) not in [RetryTask, AbortTask]:
                            self._rollback_transaction(x, self.transaction_id)

                if error:
                    return self._manage_exceptions(error, x, arguments, *args, **kwargs)

            else:
                try:
                    res = self._execute(x, function, *args, **kwargs)

                except Exception as e:
                    return self._manage_exceptions(e, x, arguments, *args, **kwargs)

            if x.total_pages == current_page:
                self._update_task_manager(x, status="DONE")

            return res

        self.instance = self.parent_decorator(wrapper)
        return self.instance

    def _execute(self, x: TaskManager, function: Callable, *args, **kwargs):
        self._update_task_manager(x, status_message="")
        return function(*args, **kwargs)

    def _manage_exceptions(self, e: Exception, x: TaskManager, arguments: dict, *args, **kwargs):
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
                    status_message=str(e)[:255],
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
                    status_message=str(e)[:255],
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
                exception_module=e.__class__.__module__,
                exception_name=e.__class__.__name__,
                status_message=str(e)[:255],
            )

            if e.log:
                logger.exception(str(e))

            # avoid reattempts
            return

        else:
            traceback.print_exc()

            error = str(e)[:255]
            exception = e

            logger.exception(str(e))

        if error:

            self._update_task_manager(
                x,
                status="ERROR",
                exception_module=e.__class__.__module__,
                exception_name=e.__class__.__name__,
                status_message=str(error)[:255],
            )

            # fallback
            if self.fallback:
                return self.fallback(*args, **kwargs, exception=exception)

            # behavior by default
            return
