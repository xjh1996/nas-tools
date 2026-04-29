class Pan115ProviderType:
    SESSION = "session"
    OPEN = "open"


class Pan115TaskStatus:
    FAILED = -1
    PENDING = 0
    DOWNLOADING = 1
    COMPLETED = 2

    NAME_MAP = {
        FAILED: "failed",
        PENDING: "pending",
        DOWNLOADING: "downloading",
        COMPLETED: "completed"
    }


TASK_DISPLAY_STATE = {
    "pending": "Pending",
    "downloading": "Downloading",
    "completed": "Completed",
    "failed": "Failed"
}
