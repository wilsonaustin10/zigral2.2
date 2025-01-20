from typing import Optional

class BrowserError(Exception):
    """Base class for browser automation errors"""
    def __init__(self, message: str, cause: Optional[Exception] = None):
        super().__init__(message)
        self.cause = cause

class NavigationError(BrowserError):
    """Raised when navigation fails"""
    pass

class ElementNotFoundError(BrowserError):
    """Raised when element cannot be found"""
    pass

class ActionError(BrowserError):
    """Raised when action execution fails"""
    pass

class PopupError(BrowserError):
    """Raised when popup handling fails"""
    pass

class StateError(BrowserError):
    """Raised when state management fails"""
    pass

class TimeoutError(BrowserError):
    """Raised when operation times out"""
    pass

class RateLimitError(BrowserError):
    """Raised when rate limit is exceeded"""
    pass

class ValidationError(BrowserError):
    """Raised when validation fails"""
    pass

def wrap_browser_error(func):
    """Decorator to wrap exceptions in BrowserError"""
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except BrowserError:
            raise
        except Exception as e:
            raise BrowserError(f"{func.__name__} failed: {str(e)}", cause=e)
    return wrapper 