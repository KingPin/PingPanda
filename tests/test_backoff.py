"""Tests for adaptive backoff and circuit breaker functionality."""

import time

from pingpanda_core.backoff import FailureTracker


def test_backoff_allows_first_check():
    """First check for a target should always be allowed."""
    tracker = FailureTracker(enable_backoff=True, min_backoff_seconds=10.0)

    assert tracker.should_check("test-target") is True


def test_backoff_after_failure():
    """After a failure, target should be in backoff period."""
    tracker = FailureTracker(enable_backoff=True, min_backoff_seconds=0.1, max_backoff_seconds=1.0)

    # First check allowed
    assert tracker.should_check("test-target") is True

    # Record failure (this also performs a check internally)
    tracker.record_result("test-target", False)

    # Immediate recheck should be blocked (we're in backoff)
    assert tracker.should_check("test-target") is False

    # After backoff period, should be allowed
    time.sleep(0.11)  # Just over min_backoff
    assert tracker.should_check("test-target") is True


def test_circuit_breaker_opens():
    """Circuit should open after threshold failures."""
    tracker = FailureTracker(
        enable_backoff=True,
        min_backoff_seconds=0.05,
        circuit_threshold=3,
        circuit_cooldown_seconds=0.2,
    )

    target = "failing-target"

    # Record multiple failures to hit threshold
    for i in range(3):
        assert tracker.should_check(target) is True
        tracker.record_result(target, False)
        if i < 2:  # Don't wait after last failure
            time.sleep(0.06)  # Wait out backoff between attempts

    # Circuit should now be open
    assert tracker.should_check(target) is False

    # Even after short wait, circuit remains open during cooldown
    time.sleep(0.1)
    assert tracker.should_check(target) is False

    # After full cooldown, circuit tries to close (half-open state)
    time.sleep(0.11)  # Total wait now exceeds 0.2s cooldown
    assert tracker.should_check(target) is True


def test_success_resets_backoff():
    """Success should reset consecutive failures and backoff."""
    tracker = FailureTracker(enable_backoff=True, min_backoff_seconds=0.1)

    target = "flaky-target"

    # Fail once
    tracker.record_result(target, False)
    assert tracker.should_check(target) is False

    # Wait for backoff
    time.sleep(0.15)

    # Success should reset
    tracker.record_result(target, True)

    # Immediate recheck should now be allowed
    assert tracker.should_check(target) is True


def test_disabled_backoff_always_allows():
    """When backoff is disabled, all checks should be allowed."""
    tracker = FailureTracker(enable_backoff=False)

    target = "always-check"

    # Even after failures, should always allow checks
    for _ in range(10):
        assert tracker.should_check(target) is True
        tracker.record_result(target, False)


def test_get_state_returns_info():
    """get_state should return target information."""
    tracker = FailureTracker(enable_backoff=True)

    target = "monitored-target"

    # Before any checks, state should be None
    assert tracker.get_state(target) is None

    # After first check
    tracker.should_check(target)
    state = tracker.get_state(target)
    assert state is not None
    assert state["target"] == target
    assert state["consecutive_failures"] == 0
    assert state["is_circuit_open"] is False

    # After failure
    tracker.record_result(target, False)
    state = tracker.get_state(target)
    assert state is not None
    assert state["consecutive_failures"] == 1

