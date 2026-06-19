"""Generic retry/backoff helpers for external service calls.

Provides a small, testable ``with_retry`` wrapper used by QuickBooks write helpers and
LLM invocations. The caller decides which exceptions are transient and how many
attempts to allow.
"""
from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def with_retry(
    func: Callable[[], T],
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    max_attempts: int = 3,
    base_seconds: float = 2.0,
    max_seconds: float = 60.0,
    jitter: bool = True,
    on_retry: Callable[[int, BaseException], None] | None = None,
) -> T:
    """Call ``func`` repeatedly until it succeeds or retries are exhausted.

    Waits ``base_seconds ** attempt`` seconds between retries, capped at
    ``max_seconds``. When ``jitter`` is True, a random fraction up to 25% is added to
    each sleep to avoid thundering-herd retries.

    Args:
        func: The zero-argument callable to retry.
        exceptions: Tuple of exception types that should trigger a retry.
        max_attempts: Total attempts before giving up (must be >= 1).
        base_seconds: Base for the exponential backoff multiplier.
        max_seconds: Maximum sleep between attempts.
        jitter: Whether to add random jitter to backoff sleeps.
        on_retry: Optional callback ``(attempt, exception)`` invoked after each failed
            attempt but before sleeping.

    Returns:
        The value returned by ``func``.

    Raises:
        The last exception raised by ``func`` if all attempts fail.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    last_exception: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except exceptions as exc:
            last_exception = exc
            if attempt == max_attempts:
                logger.warning(
                    "%s still failing after %s attempt(s): %s",
                    func.__name__ if hasattr(func, "__name__") else "callable",
                    max_attempts,
                    exc,
                )
                raise

            sleep_seconds = min(base_seconds ** attempt, max_seconds)
            if jitter:
                sleep_seconds *= 1 + random.uniform(0, 0.25)
            logger.warning(
                "%s failed (attempt %s/%s): %s. Retrying in %.2fs.",
                func.__name__ if hasattr(func, "__name__") else "callable",
                attempt,
                max_attempts,
                exc,
                sleep_seconds,
            )
            if on_retry:
                on_retry(attempt, exc)
            time.sleep(sleep_seconds)

    # Should only be reached if exceptions were raised and the loop exited without
    # re-raising; guard against pathological max_attempts values.
    if last_exception is not None:
        raise last_exception
    raise RuntimeError("with_retry exhausted without a return value or exception")
