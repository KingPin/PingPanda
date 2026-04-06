"""Check registry and BaseCheck for PingPanda.

Third-party or custom check types can self-register without touching
core files:

    from pingpanda_core.registry import BaseCheck, register_check

    @register_check("mycheck")
    class MyCheck(BaseCheck):
        @property
        def check_name(self) -> str:
            return "MyCheck"

        @property
        def is_enabled(self) -> bool:
            return bool(self.ctx.config.get("enable_mycheck"))

        @property
        def targets(self) -> list:
            raw = self.ctx.config.get("mycheck_targets", "")
            return [t.strip() for t in raw.split(",") if t.strip()]

        async def _check_single(self, target: str) -> None:
            ...
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Type

if TYPE_CHECKING:
    from .app import PingPanda
    from .stats import StatsManager


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_CHECK_REGISTRY: Dict[str, Type["BaseCheck"]] = {}


def register_check(name: str) -> Callable[[Type["BaseCheck"]], Type["BaseCheck"]]:
    """Class decorator that adds the check type to the global registry."""

    def decorator(cls: Type[BaseCheck]) -> Type[BaseCheck]:
        _CHECK_REGISTRY[name] = cls
        return cls

    return decorator


# ---------------------------------------------------------------------------
# CheckDependencies
# ---------------------------------------------------------------------------


class CheckDependencies:
    """Container injected into every check instance."""

    def __init__(self, app: "PingPanda", stats: Optional["StatsManager"]) -> None:
        self.app = app
        self.stats = stats


# ---------------------------------------------------------------------------
# BaseCheck
# ---------------------------------------------------------------------------


class BaseCheck(ABC):
    """Abstract base for all check types.

    Concrete classes implement:
        check_name  — display name used in log messages
        is_enabled  — whether this check should run
        targets     — list of target strings for this cycle
        _check_single(target) — the per-target check coroutine
    """

    def __init__(self, deps: CheckDependencies) -> None:
        self.deps = deps

    @property
    def ctx(self) -> "PingPanda":
        return self.deps.app

    @property
    def stats(self) -> Optional["StatsManager"]:
        return self.deps.stats

    @property
    @abstractmethod
    def check_name(self) -> str:
        """Human-readable name shown in startup and log messages."""

    @property
    @abstractmethod
    def is_enabled(self) -> bool:
        """Return True if this check should run this cycle."""

    @property
    @abstractmethod
    def targets(self) -> List[str]:
        """Return the list of targets to check."""

    async def run(self) -> None:
        """Execute all targets concurrently.

        Handles the shared pattern:
          - enabled guard
          - "Starting …" log line
          - concurrent gather with error surfacing
        """
        if not self.is_enabled or not self.targets:
            return

        ctx = self.ctx
        if not (ctx.show_only_success or ctx.show_only_failure):
            ctx.logger.info("Starting %s checks...", self.check_name)

        tasks = [self._check_single(t) for t in self.targets if t]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                ctx.logger.error(
                    "%s check raised an unexpected exception: %r",
                    self.check_name,
                    result,
                )

    async def _record_stats_result(
        self, target: str, success: bool
    ) -> None:
        """Record a check result into StatsManager and emit flapping/recovery events.

        Concrete checks call this after determining success/failure.
        The key format is "{check_name}:{target}".
        """
        if not self.stats:
            return

        key = f"{self.check_name}:{target}"
        result = self.stats.update_target(key, success)

        if result.flapping_changed and result.is_flapping:
            await self.ctx.send_notification(
                f"{self.check_name} {target} is flapping "
                f"(>{self.ctx.flap_threshold} status changes "
                f"in {self.ctx.flap_window_seconds}s)",
                status="error",
                check_type="Flapping",
                target=target,
            )
        elif result.flapping_changed and not result.is_flapping:
            await self.ctx.send_notification(
                f"{self.check_name} {target} flapping resolved",
                status="ok",
                check_type="Flapping",
                target=target,
            )
        elif result.status_changed and success and not result.is_flapping:
            ts = self.stats.target_stats.get(key)
            downtime = ts.total_downtime if ts else 0.0
            self.ctx.logger.info(
                "%s %s recovered (was down for %.1fs)",
                self.check_name, target, downtime,
            )

    async def close(self) -> None:
        """Release resources held by this check (e.g. thread pools).

        Called by PingPanda._cleanup(). Override in subclasses that hold
        resources beyond what the base class manages.
        """

    @abstractmethod
    async def _check_single(self, target: str) -> None:
        """Perform a check against one target."""


__all__ = [
    "BaseCheck",
    "CheckDependencies",
    "register_check",
    "_CHECK_REGISTRY",
]
