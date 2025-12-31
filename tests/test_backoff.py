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

    # After backoff period (0.1s * 2 multiplier = 0.2s), should be allowed
    time.sleep(0.22)
    assert tracker.should_check("test-target") is True


def test_circuit_breaker_opens():
    """Circuit should open after threshold failures."""
    tracker = FailureTracker(
        enable_backoff=True,
        min_backoff_seconds=0.02,  # Shorter for faster tests
        circuit_threshold=3,
        circuit_cooldown_seconds=0.2,
    )

    target = "failing-target"

    # Record multiple failures to hit threshold
    # With exponential backoff: 0.02s, 0.04s (2x), then circuit opens
    for i in range(3):
        assert tracker.should_check(target) is True
        tracker.record_result(target, False)
        if i < 2:  # Don't wait after last failure
            # Wait long enough for exponential backoff (multiplier doubles each failure)
            # After 1st failure: 0.02 * 2 = 0.04s, after 2nd: 0.02 * 4 = 0.08s
            time.sleep(0.1)

    # Circuit should now be open
    assert tracker.should_check(target) is False

    # Even after short wait, circuit remains open during cooldown
    time.sleep(0.1)
    assert tracker.should_check(target) is False

    # After full cooldown, circuit tries to close (half-open state)
    time.sleep(0.15)  # Total wait now exceeds 0.2s cooldown
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


def test_exponential_backoff_multiplier():
    """Backoff multiplier should double with each failure."""
    tracker = FailureTracker(
        enable_backoff=True,
        min_backoff_seconds=0.01,
        max_backoff_seconds=10.0,
        circuit_threshold=10,  # High threshold to test backoff without circuit opening
    )

    target = "backoff-test"

    # Initial state
    tracker.should_check(target)
    state = tracker.get_state(target)
    assert state["backoff_multiplier"] == 1.0

    # After first failure, multiplier should double to 2.0
    tracker.record_result(target, False)
    state = tracker.get_state(target)
    assert state["backoff_multiplier"] == 2.0

    # Wait and fail again - multiplier should double to 4.0
    time.sleep(0.03)  # 0.01 * 2 = 0.02s backoff
    tracker.should_check(target)
    tracker.record_result(target, False)
    state = tracker.get_state(target)
    assert state["backoff_multiplier"] == 4.0

    # Multiplier should cap at 32.0
    for _ in range(5):
        time.sleep(0.5)
        if tracker.should_check(target):
            tracker.record_result(target, False)
    
    state = tracker.get_state(target)
    assert state["backoff_multiplier"] == 32.0