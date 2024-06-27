import logging
from datetime import datetime
from typing import Any, Type

from asgiref.sync import sync_to_async
from django import dispatch
from django.utils import timezone

from task_manager.django.models import SignalError

__all__ = ["Emisor", "SIGNALS"]
logger = logging.getLogger(__name__)

SIGNALS: dict[str, dict[str, "Signal"]] = {}


class Signal(dispatch.Signal):
    def __init__(self, module: str, name: str, use_caching: bool = False) -> None:
        if name in SIGNALS[module]:
            raise Exception(f"Signal {name} in module {module} already loaded")

        SIGNALS[module][name] = self
        self.module = module
        self.name = name

        super().__init__(use_caching=use_caching)

    def _add_error(self, error: Exception, arguments: dict[str, Any]):
        if "instance" in arguments:
            del arguments["instance"]

        if "sender" in arguments:
            del arguments["sender"]

        msg = str(error)
        s, created = SignalError.objects.get_or_create(
            signal_module=self.module,
            signal_name=self.name,
            exception_module=error.__class__.__module__,
            exception_name=error.__class__.__name__,
            arguments=arguments,
            message=msg,
            defaults={
                "attempts": 1,
                "last_run": timezone.now(),
            },
        )

        if created is False:
            s.attempts += 1
            s.last_run = timezone.now()
            s.save()

        logger.exception(f"There has an error in {self.module} {self.name}, {msg}")

    @sync_to_async
    def _aadd_error(self, error: Exception, arguments: dict[str, Any]):
        return self._add_error(error=error, arguments=arguments)

    def send(self, sender: Any, **named: Any):
        """
        Send signal from sender to all connected receivers.

        If any receiver raises an error, the error propagates back through send,
        terminating the dispatch loop. So it's possible that all receivers
        won't be called if an error is raised.

        If any receivers are asynchronous, they are called after all the
        synchronous receivers via a single call to async_to_sync(). They are
        also executed concurrently with asyncio.gather().

        Arguments:

            sender
                The sender of the signal. Either a specific object or None.

            named
                Named arguments which will be passed to receivers.

        Return a list of tuple pairs [(receiver, response), ... ].
        """

        try:
            return super().send(sender, **named)

        except Exception as e:
            self._add_error(e, arguments=named)
            raise e

    async def asend(self, sender: Any, **named: Any):
        """
        Send signal from sender to all connected receivers in async mode.

        All sync receivers will be wrapped by sync_to_async()
        If any receiver raises an error, the error propagates back through
        send, terminating the dispatch loop. So it's possible that all
        receivers won't be called if an error is raised.

        If any receivers are synchronous, they are grouped and called behind a
        sync_to_async() adaption before executing any asynchronous receivers.

        If any receivers are asynchronous, they are grouped and executed
        concurrently with asyncio.gather().

        Arguments:

            sender
                The sender of the signal. Either a specific object or None.

            named
                Named arguments which will be passed to receivers.

        Return a list of tuple pairs [(receiver, response), ...].
        """

        try:
            return await super().asend(sender, **named)

        except Exception as e:
            await self._aadd_error(e, arguments=named)
            raise e

    def send_robust(self, sender: Any, **named: Any):
        """
        Send signal from sender to all connected receivers catching errors.

        If any receivers are asynchronous, they are called after all the
        synchronous receivers via a single call to async_to_sync(). They are
        also executed concurrently with asyncio.gather().

        Arguments:

            sender
                The sender of the signal. Can be any Python object (normally one
                registered with a connect if you actually want something to
                occur).

            named
                Named arguments which will be passed to receivers.

        Return a list of tuple pairs [(receiver, response), ... ].

        If any receiver raises an error (specifically any subclass of
        Exception), return the error instance as the result for that receiver.
        """

        try:
            return super().send(sender, **named)

        except Exception as e:
            self._add_error(e, arguments=named)

    async def asend_robust(self, sender: Any, **named: Any):
        """
        Send signal from sender to all connected receivers catching errors.

        If any receivers are synchronous, they are grouped and called behind a
        sync_to_async() adaption before executing any asynchronous receivers.

        If any receivers are asynchronous, they are grouped and executed
        concurrently with asyncio.gather.

        Arguments:

            sender
                The sender of the signal. Can be any Python object (normally one
                registered with a connect if you actually want something to
                occur).

            named
                Named arguments which will be passed to receivers.

        Return a list of tuple pairs [(receiver, response), ... ].

        If any receiver raises an error (specifically any subclass of
        Exception), return the error instance as the result for that receiver.
        """

        try:
            return await super().asend(sender, **named)

        except Exception as e:
            await self._aadd_error(e, arguments=named)

    def delay(self, sender: Type[Any], instance: Any, **named: Any):
        """
        Schedule signal from sender to all connected receivers catching errors thought of TaskManager.

        If any receivers are asynchronous, they are called after all the
        synchronous receivers via a single call to async_to_sync(). They are
        also executed concurrently with asyncio.gather().

        Arguments:

            sender
                The sender of the signal. Can be any Python object (normally one
                registered with a connect if you actually want something to
                occur).

            instance
                The instance of the sender of the signal. Can be any Python object (normally one
                registered with a connect if you actually want something to
                occur).

            named
                Named arguments which will be passed to receivers.

        Return a list of tuple pairs [(receiver, response), ... ].

        If any receiver raises an error (specifically any subclass of
        Exception), return the error instance as the result for that receiver.
        """

        from task_manager.django.tasks import execute_signal

        if instance and instance.pk is None:
            raise Exception("Cannot delay a signal for models without ids")

        sender_name = sender.__name__
        sender_module = sender.__module__
        signal_module = self.module
        signal_name = self.name
        pk = instance.pk

        execute_signal.delay(signal_module, signal_name, sender_module, sender_name, pk, extra=named)

    @sync_to_async
    def adelay(self, sender: Any, instance: Any, **named: Any):
        """
        Schedule signal from sender to all connected receivers catching errors thought of TaskManager.

        If any receivers are synchronous, they are grouped and called behind a
        sync_to_async() adaption before executing any asynchronous receivers.

        If any receivers are asynchronous, they are grouped and executed
        concurrently with asyncio.gather.

        Arguments:

            sender
                The sender of the signal. Can be any Python object (normally one
                registered with a connect if you actually want something to
                occur).

            instance
                The instance of the sender of the signal. Can be any Python object (normally one
                registered with a connect if you actually want something to
                occur).

            named
                Named arguments which will be passed to receivers.

        Return a list of tuple pairs [(receiver, response), ... ].

        If any receiver raises an error (specifically any subclass of
        Exception), return the error instance as the result for that receiver.
        """

        return self.delay(sender=sender, instance=instance, **named)


class Emisor:
    """Task Manager's Django signal emisor."""

    def __init__(self, name: str):
        if name in SIGNALS:
            raise Exception(f"Module {name} already loaded")

        SIGNALS[name] = {}

        self.module = name

    def signal(self, name: str, use_caching: bool = False):
        """Get a Django Signal."""
        return Signal(self.module, name, use_caching=use_caching)
