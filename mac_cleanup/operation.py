"""Small operation state model used for recovery and progress reporting."""

from enum import Enum


class OperationStatus(str, Enum):
    """Lifecycle states for a cleanup operation."""

    PENDING = "pending"
    SKIPPED = "skipped"
    BACKED_UP = "backed_up"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"

    @property
    def terminal(self) -> bool:
        """Whether the operation should not be attempted again."""

        return self in {self.SKIPPED, self.COMPLETED, self.ROLLED_BACK}
