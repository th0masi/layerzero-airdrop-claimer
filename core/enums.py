from enum import Enum


class ClaimStatus(Enum):
    SUCCESS = "success"
    WITHOUT_ALLOCATION = "without_allocation"
    ALREADY_CLAIMED = "already_claimed"
    ERROR = "error"
    PENDING = "pending"
