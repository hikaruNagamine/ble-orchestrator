"""BLE Controller custom exceptions."""

class BLEControllerError(Exception):
    """Base exception for BLE Controller."""
    pass

class QueueProcessingError(BLEControllerError):
    """Raised when queue processing fails."""
    pass

class QueueFullError(BLEControllerError):
    """Raised when queue is full."""
    pass

class DeviceConnectionError(BLEControllerError):
    """Raised when device connection fails."""
    pass

class TaskExecutionError(BLEControllerError):
    """Raised when task execution fails."""
    pass 