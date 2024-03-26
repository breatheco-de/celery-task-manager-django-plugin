import importlib
from datetime import datetime, timedelta

from celery import Task

# from breathecode.notify.actions import send_email_message
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from task_manager.django import tasks
from task_manager.django.models import ScheduledTask

from ...models import TaskManager, TaskWatcher

TOLERANCE = 30

HOUR = 19
MINUTE = 0

STATUSES = [
    "PENDING",
    "DONE",
    "CANCELLED",
    "REVERSED",
    "PAUSED",
    "ABORTED",
    "ERROR",
]


def is_report_time():
    # Getting the current datetime
    now = timezone.now()

    # Constructing the starting and ending datetime objects
    start_time = datetime.strptime(f"{now} {HOUR}:{MINUTE}", "%Y-%m-%d %H:%M")
    start_time = start_time.replace(tzinfo=now.tzinfo)
    start_time.second = 0
    start_time.microsecond = 0

    end_time = start_time + timedelta(minutes=10)

    # Comparing and returning the result
    return start_time <= now < end_time


class Command(BaseCommand):
    help = "Rerun all the tasks that are pending and were run in the last 10 minutes"

    def handle(self, *args, **options):
        self.utc_now = timezone.now()

        self.clean_older_tasks()
        self.rerun_pending_tasks()
        # self.daily_report()
        self.run_scheduled_tasks()

    def clean_older_tasks(self):

        date_limit = self.utc_now - timedelta(days=5)
        errors = TaskManager.objects.filter(created_at__lt=date_limit, status="ERROR")

        date_limit = self.utc_now - timedelta(days=2)
        alright = TaskManager.objects.filter(created_at__lt=date_limit).exclude(status="ERROR")

        count_errors = errors.count()
        count_alright = alright.count()
        errors.delete()
        alright.delete()

        self.stdout.write(self.style.SUCCESS(f"Successfully deleted {str(count_errors + count_alright)} TaskManager's"))

    def run_scheduled_tasks(self):
        modules = {}
        cache: dict[str, dict[str, Task]] = {}
        scheduled_tasks = ScheduledTask.objects.filter(status="PENDING", eta__lte=self.utc_now)
        cancelled_tasks = ScheduledTask.objects.exclude(status="PENDING")
        scheduled = 0

        for scheduled_task in scheduled_tasks:
            if scheduled_task.task_module not in cache:
                cache[scheduled_task.task_module] = {}

            if scheduled_task.task_name not in cache[scheduled_task.task_module]:
                if scheduled_task.task_module not in modules:
                    modules[scheduled_task.task_module] = importlib.import_module(scheduled_task.task_module)

                module = modules[scheduled_task.task_module]
                function = getattr(module, scheduled_task.task_name)
                cache[scheduled_task.task_module][scheduled_task.task_name] = function

            handler = cache[scheduled_task.task_module][scheduled_task.task_name]
            handler.delay(*scheduled_task.arguments["args"], **scheduled_task.arguments["kwargs"])
            scheduled += 1

        scheduled_tasks.delete()
        cancelled_tasks.delete()

        self.stdout.write(self.style.SUCCESS(f"Successfully scheduled {scheduled} Tasks"))

    def rerun_pending_tasks(self):
        tolerance = timedelta(minutes=TOLERANCE)

        ids = TaskManager.objects.filter(last_run__lt=self.utc_now - tolerance, status="PENDING").values_list(
            "id", flat=True
        )

        for id in ids:
            tasks.mark_task_as_pending.delay(id, force=True)

        if ids:
            msg = self.style.SUCCESS(f"Rerunning TaskManager's {', '.join([str(id) for id in ids])}")

        else:
            msg = self.style.SUCCESS("No TaskManager's available to re-run")

        self.stdout.write(self.style.SUCCESS(msg))

    def daily_report(self):
        if not is_report_time():
            self.stdout.write(self.style.SUCCESS("Not report time, skipping."))
            return

        tasks = TaskManager.objects.filter()
        errors = tasks.filter(Q(status="ERROR") | Q(status="ABORTED"))
        error_number = errors.count()

        if not error_number:
            self.stdout.write(self.style.SUCCESS("All is ok."))

        watchers = TaskWatcher.objects.filter()

        if not watchers:
            self.stdout.write(self.style.SUCCESS("No watchers to send notifies."))
            return

        done = tasks.filter(status="DONE").count()
        cancelled = tasks.filter(status="CANCELLED").count()
        reversed = tasks.filter(status="REVERSED").count()
        paused = tasks.filter(status="PAUSED").count()
        aborted = tasks.filter(status="ABORTED").count()

        module_names = list({x.task_module for x in errors})
        report = {}

        for module_name in module_names:
            report[module_name] = {}

            module = errors.filter(task_module=module_name)
            task_names = list({x.task_name for x in module})

            n = 0

            for task_name in task_names:
                if task_name not in report[module_name]:
                    report[module_name][task_name] = {}

                for status in STATUSES:
                    length = tasks.filter(task_module=module_name, task_name=module_name, status=status).count()

                    if status == "ERROR":
                        n += length

                    report[module_name][task_name][status] = length

            report[module_name]["abc_total_cba"] = n

        for watcher in watchers:
            send_email_message(
                "task_manager_report",
                watcher.email or watcher.user.email,
                {
                    "report": report,
                    "errors": errors,
                    "done": done,
                    "cancelled": cancelled,
                    "reversed": reversed,
                    "paused": paused,
                    "aborted": aborted,
                },
                force=True,
                inline_css=True,
            )
