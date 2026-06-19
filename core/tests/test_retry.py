"""Tests for the generic retry helper.
"""
from __future__ import annotations

from unittest import TestCase, mock

from core.services.retry import with_retry


class WithRetryTests(TestCase):
    def test_returns_first_attempt_when_callable_succeeds(self) -> None:
        counter = {"calls": 0}

        def func() -> str:
            counter["calls"] += 1
            return "ok"

        result = with_retry(func, exceptions=(RuntimeError,), max_attempts=3)
        self.assertEqual(result, "ok")
        self.assertEqual(counter["calls"], 1)

    def test_retries_on_matching_exception_and_succeeds(self) -> None:
        counter = {"calls": 0}

        def func() -> str:
            counter["calls"] += 1
            if counter["calls"] < 3:
                raise ConnectionError("transient")
            return "ok"

        with mock.patch("core.services.retry.time.sleep"):
            result = with_retry(func, exceptions=(ConnectionError,), max_attempts=3)

        self.assertEqual(result, "ok")
        self.assertEqual(counter["calls"], 3)

    def test_raises_last_exception_after_exhausting_attempts(self) -> None:
        counter = {"calls": 0}

        def func() -> None:
            counter["calls"] += 1
            raise TimeoutError(f"attempt {counter['calls']}")

        with mock.patch("core.services.retry.time.sleep"):
            with self.assertRaises(TimeoutError) as cm:
                with_retry(func, exceptions=(TimeoutError,), max_attempts=2)

        self.assertIn("attempt 2", str(cm.exception))
        self.assertEqual(counter["calls"], 2)

    def test_does_not_retry_non_matching_exception(self) -> None:
        counter = {"calls": 0}

        def func() -> None:
            counter["calls"] += 1
            raise ValueError("boom")

        with self.assertRaises(ValueError):
            with_retry(func, exceptions=(RuntimeError,), max_attempts=3)

        self.assertEqual(counter["calls"], 1)

    def test_on_retry_callback_is_invoked(self) -> None:
        counter = {"calls": 0}
        retries: list[tuple[int, BaseException]] = []

        def func() -> str:
            counter["calls"] += 1
            if counter["calls"] < 2:
                raise ConnectionError("transient")
            return "ok"

        def on_retry(attempt: int, exc: BaseException) -> None:
            retries.append((attempt, exc))

        with mock.patch("core.services.retry.time.sleep"):
            result = with_retry(
                func,
                exceptions=(ConnectionError,),
                max_attempts=3,
                on_retry=on_retry,
            )

        self.assertEqual(result, "ok")
        self.assertEqual(len(retries), 1)
        self.assertEqual(retries[0][0], 1)
        self.assertIsInstance(retries[0][1], ConnectionError)

    def test_invalid_max_attempts_raises(self) -> None:
        with self.assertRaises(ValueError):
            with_retry(lambda: "ok", exceptions=(Exception,), max_attempts=0)
