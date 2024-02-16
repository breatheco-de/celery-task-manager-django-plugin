class ProgrammingError(Exception):
    pass


class TaskException(Exception):
    """Base class for other exceptions."""

    def __init__(self, message: str, log=True) -> None:
        self.log = log
        super().__init__(message)

    def __eq__(self, other: "TaskException"):
        return type(self) == type(other) and str(self) == str(other) and self.log == other.log  # noqa: E721


class AbortTask(TaskException):
    """Abort task due to it doesn't meet the requirements, it will not be reattempted."""

    pass


class RetryTask(TaskException):
    """
    Retry task due to it doesn't meet the requirements for a synchronization issue like a not found, it will be
    reattempted.
    """

    pass
