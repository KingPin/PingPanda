"""Adaptive backoff and circuit breaker for failed checks."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class TargetState:
    """Tracks the state and backoff for a single target."""

    target: str
    consecutive_failures: int = 0
    last_check_time: Optional[float] = None
    last_success_time: Optional[float] = None
    is_circuit_open: bool = False
    circuit_opened_at: Optional[float] = None
    backoff_multiplier: float = 1.0

    def should_check(
        self,
        current_time: float,
        min_backoff: float,
        max_backoff: float,
        circuit_threshold: int,
        circuit_cooldown: float,
    ) -> bool:
        """Determine if we should attempt to check this target."""
        # If circuit is open, check if cooldown period has passed
        if self.is_circuit_open and self.circuit_opened_at:
            if current_time - self.circuit_opened_at >= circuit_cooldown:
                # Try to close circuit (half-open state)
                self.is_circuit_open = False
                self.backoff_multiplier = 1.0
                return True
            # Still in cooldown
            return False

        # Apply exponential backoff based on consecutive failures
        if self.consecutive_failures > 0 and self.last_check_time is not None:
            backoff_time = min(min_backoff * self.backoff_multiplier, max_backoff)
            time_since_last = current_time - self.last_check_time
            if time_since_last < backoff_time:
                # Still in backoff period
                return False

        return True

    def record_success(self, current_time: float) -> None:
        """Record a successful check."""
        self.consecutive_failures = 0
        self.last_success_time = current_time
        self.last_check_time = current_time
        self.is_circuit_open = False
        self.circuit_opened_at = None
        self.backoff_multiplier = 1.0

    def record_failure(self, current_time: float, circuit_threshold: int) -> None:
        """Record a failed check and potentially open the circuit.
        
        Exponential backoff is applied after the first failure. The backoff
        multiplier doubles with each failure up to when the circuit opens.
        This allows for graceful degradation before the circuit breaker trips.
        """
        self.consecutive_failures += 1
        self.last_check_time = current_time

        # Open circuit if threshold exceeded
        if self.consecutive_failures >= circuit_threshold:
            if not self.is_circuit_open:
                self.is_circuit_open = True
                self.circuit_opened_at = current_time
        else:
            # Apply exponential backoff for failures before circuit opens
            # This provides gradual backpressure while still allowing
            # the circuit breaker threshold to be reached
            self.backoff_multiplier = min(self.backoff_multiplier * 2.0, 32.0)


class FailureTracker:
    """Tracks failure state across all targets.

    All methods are called from the asyncio event loop and require no
    threading synchronisation — the single-threaded event loop provides
    the necessary serialisation.
    """

    def __init__(
        self,
        enable_backoff: bool = True,
        min_backoff_seconds: float = 10.0,
        max_backoff_seconds: float = 300.0,
        circuit_threshold: int = 5,
        circuit_cooldown_seconds: float = 60.0,
    ):
        self.enable_backoff = enable_backoff
        self.min_backoff = min_backoff_seconds
        self.max_backoff = max_backoff_seconds
        self.circuit_threshold = circuit_threshold
        self.circuit_cooldown = circuit_cooldown_seconds
        self._targets: Dict[str, TargetState] = {}

    def should_check(self, target: str) -> bool:
        """Check if we should attempt to check this target."""
        if not self.enable_backoff:
            return True

        if target not in self._targets:
            self._targets[target] = TargetState(target=target)
            return True

        state = self._targets[target]
        return state.should_check(
            current_time=time.time(),
            min_backoff=self.min_backoff,
            max_backoff=self.max_backoff,
            circuit_threshold=self.circuit_threshold,
            circuit_cooldown=self.circuit_cooldown,
        )

    def record_result(self, target: str, success: bool) -> None:
        """Record the result of a check."""
        if not self.enable_backoff:
            return

        current_time = time.time()

        if target not in self._targets:
            self._targets[target] = TargetState(target=target)

        state = self._targets[target]
        if success:
            state.record_success(current_time)
        else:
            state.record_failure(current_time, self.circuit_threshold)

    def get_state(self, target: str) -> Optional[Dict[str, Any]]:
        """Get the current state of a target for debugging/monitoring."""
        if target not in self._targets:
            return None

        state = self._targets[target]
        return {
            "target": state.target,
            "consecutive_failures": state.consecutive_failures,
            "is_circuit_open": state.is_circuit_open,
            "backoff_multiplier": state.backoff_multiplier,
            "last_check": (
                datetime.fromtimestamp(state.last_check_time).isoformat()
                if state.last_check_time is not None
                else None
            ),
            "last_success": (
                datetime.fromtimestamp(state.last_success_time).isoformat()
                if state.last_success_time
                else None
            ),
        }

    def get_all_states(self) -> Dict[str, Any]:
        """Get states of all tracked targets."""
        result = {}
        for target, state in self._targets.items():
            result[target] = {
                "target": state.target,
                "consecutive_failures": state.consecutive_failures,
                "is_circuit_open": state.is_circuit_open,
                "backoff_multiplier": state.backoff_multiplier,
                "last_check": (
                    datetime.fromtimestamp(state.last_check_time).isoformat()
                    if state.last_check_time is not None
                    else None
                ),
                "last_success": (
                    datetime.fromtimestamp(state.last_success_time).isoformat()
                    if state.last_success_time
                    else None
                ),
            }
        return result

    def reset_target(self, target: str) -> None:
        """Reset a target's state (useful for manual recovery)."""
        self._targets.pop(target, None)


__all__ = ["FailureTracker", "TargetState"]
