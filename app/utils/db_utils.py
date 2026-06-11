"""
Database utility functions for DeepAgent Chat.

Provides:
- retry_on_db_lock: decorator to retry SQLite write operations on lock errors
"""
import time
import functools
import logging

logger = logging.getLogger("deepagent")

# Maximum retry attempts for SQLite database lock errors
_MAX_RETRIES = 3
# Initial backoff in seconds (doubles each retry)
_INITIAL_BACKOFF = 0.1


def retry_on_db_lock(max_retries=_MAX_RETRIES, initial_backoff=_INITIAL_BACKOFF):
    """Decorator: retry the wrapped function when SQLite raises 'database is locked'.

    Uses exponential backoff between retries. Catches sqlalchemy.exc.OperationalError
    when the error message contains 'database is locked'.

    Usage:
        @retry_on_db_lock()
        def my_write_operation():
            db.session.add(...)
            db.session.commit()

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        initial_backoff: Initial wait time in seconds (default: 0.1, doubles each retry)
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    error_msg = str(e).lower()
                    is_lock_error = "database is locked" in error_msg
                    if not is_lock_error or attempt == max_retries:
                        # Not a lock error, or we've exhausted retries — re-raise
                        raise
                    last_exception = e
                    backoff = initial_backoff * (2 ** attempt)
                    logger.warning(
                        "SQLite database locked, retrying in %.2fs (attempt %d/%d): %s",
                        backoff, attempt + 1, max_retries, str(e)[:100],
                    )
                    time.sleep(backoff)
            # Should never reach here, but just in case
            if last_exception:
                raise last_exception
        return wrapper
    return decorator
