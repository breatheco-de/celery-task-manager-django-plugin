import os

from django.contrib import admin
from django.core.paginator import Paginator
from django.utils.functional import cached_property

from . import tasks
from .models import ScheduledTask, SignalError, TaskManager, TaskWatcher


def cancel(modeladmin, request, queryset):
    for x in queryset.all():
        tasks.mark_task_as_cancelled.delay(x.id)


def reverse(modeladmin, request, queryset):
    for x in queryset.all():
        tasks.mark_task_as_reversed.delay(x.id)


def force_reverse(modeladmin, request, queryset):
    for x in queryset.all():
        tasks.mark_task_as_reversed.delay(x.id, force=True)


def pause(modeladmin, request, queryset):
    for x in queryset.all():
        tasks.mark_task_as_paused.delay(x.id)


def resume(modeladmin, request, queryset):
    for x in queryset.all():
        tasks.mark_task_as_pending.delay(x.id)


SHOW_DURATION = os.getenv("TM_SHOW_DURATION", "0") in [
    "true",
    "1",
    "yes",
    "y",
    "on",
    "enable",
    "enabled",
    "True",
    "TRUE",
    "Yes",
    "YES",
    "Y",
    "On",
    "ON",
    "Enable",
    "ENABLE",
    "Enabled",
    "ENABLED",
]


class AproxPaginator(Paginator):
    def page(self, number):
        return super().page(number)

    @cached_property
    def count(self):
        """Return the total number of objects, across all pages."""
        has_first = hasattr(self.object_list, "first") and callable(self.object_list.first)
        has_last = hasattr(self.object_list, "last") and callable(self.object_list.last)
        has_only = hasattr(self.object_list, "only") and callable(self.object_list.only)
        if has_first and has_last and has_only:
            return self.object_list.only("pk").last().pk - self.object_list.only("pk").first().pk + 1
        return 999999999


@admin.register(TaskManager)
class TaskManagerAdmin(admin.ModelAdmin):
    list_per_page = 20
    list_max_show_all = 20
    show_full_result_count = False
    paginator = AproxPaginator
    list_display = [
        "task_module",
        "task_name",
        "reverse_module",
        "reverse_name",
        "status",
        "last_run",
        "current_page",
        "total_pages",
        "killed",
    ]

    search_fields = ["task_module", "task_name", "reverse_module", "reverse_name"]
    list_filter = ["status", "killed", "task_module"]
    actions = [pause, resume, cancel, reverse, force_reverse]

    if SHOW_DURATION:
        list_display.append("get_duration")

        @admin.display(description="Duration (ms)")
        def get_duration(self, obj):
            if obj.started_at is None:
                return "No started"

            duration = obj.updated_at - obj.started_at
            # Calculating duration in milliseconds
            duration_ms = duration.total_seconds() * 1000
            return f"{int(duration_ms)} ms"


@admin.register(TaskWatcher)
class TaskWatcherAdmin(admin.ModelAdmin):
    list_display = ["user", "email", "on_error", "on_success", "watch_progress"]
    search_fields = ["email", "user__email", "user__username", "user__first_name", "user__last_name"]
    list_filter = ["on_error", "on_success", "watch_progress"]
    raw_id_fields = ["user"]


@admin.register(ScheduledTask)
class ScheduledTaskAdmin(admin.ModelAdmin):
    list_display = ["task_module", "task_name", "status", "eta", "duration"]
    search_fields = ["task_module", "task_name"]
    list_filter = ["status", "task_module"]


@admin.register(SignalError)
class SignalErrorAdmin(admin.ModelAdmin):
    list_display = ["signal_module", "signal_name", "exception_module", "exception_name", "last_run", "attempts"]
    search_fields = ["signal_module", "signal_name", "exception_module", "exception_name"]
    list_filter = ["signal_module", "exception_module"]
