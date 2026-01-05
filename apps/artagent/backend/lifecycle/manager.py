"""
Lifecycle Manager - Clean startup/shutdown orchestration.

Provides a simple, maintainable way to manage application lifecycle without
complex nested wrappers or excessive logging that overwhelms junior developers.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from utils.ml_logging import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = get_logger("lifecycle")


@dataclass
class LifecycleStep:
    """A single startup/shutdown step with optional cleanup."""

    name: str
    startup: Callable[[], Awaitable[None]]
    shutdown: Callable[[], Awaitable[None]] | None = None
    duration: float = 0.0
    success: bool = False
    error: str | None = None


@dataclass
class LifecycleManager:
    """
    Manages application startup and shutdown in a clean, sequential manner.

    Design goals:
    - Simple and readable for junior developers
    - Minimal console noise (single progress line)
    - Clear error reporting
    - Proper tracing for production observability
    """

    steps: list[LifecycleStep] = field(default_factory=list)
    executed_steps: list[LifecycleStep] = field(default_factory=list)
    _tracer: trace.Tracer = field(default=None, init=False)

    def __post_init__(self):
        self._tracer = trace.get_tracer(__name__)

    def add_step(
        self,
        name: str,
        startup: Callable[[], Awaitable[None]],
        shutdown: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """Register a lifecycle step."""
        self.steps.append(LifecycleStep(name=name, startup=startup, shutdown=shutdown))

    async def run_startup(self) -> list[tuple[str, float]]:
        """
        Execute all startup steps with progress feedback.

        Returns:
            List of (step_name, duration_seconds) for reporting.
        """
        results: list[tuple[str, float]] = []
        total = len(self.steps)

        # Single-line progress indicator
        self._write_progress(f"Starting ({total} steps)...")

        for i, step in enumerate(self.steps):
            step_start = time.perf_counter()

            with self._tracer.start_as_current_span(f"startup.{step.name}") as span:
                try:
                    await step.startup()
                    step.success = True
                except Exception as exc:
                    step.error = str(exc)
                    step.success = False
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                    self._write_progress(f"✗ {step.name} failed: {exc}\n")
                    raise

                step.duration = time.perf_counter() - step_start
                span.set_attribute("duration_sec", step.duration)

            self.executed_steps.append(step)
            results.append((step.name, round(step.duration, 2)))

            # Update progress indicator
            progress = "·" * i + "●" + "·" * (total - i - 1)
            self._write_progress(f"[{progress}] {step.name} ({step.duration:.1f}s)")

        total_time = sum(d for _, d in results)
        self._write_progress(f"✓ Ready in {total_time:.1f}s\n")

        return results

    async def run_shutdown(self) -> None:
        """Execute shutdown steps in reverse order."""
        self._write_progress("Shutting down...")

        for step in reversed(self.executed_steps):
            if step.shutdown is None:
                continue

            with self._tracer.start_as_current_span(f"shutdown.{step.name}") as span:
                try:
                    await step.shutdown()
                except Exception as exc:
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                    logger.warning(f"Shutdown step '{step.name}' failed: {exc}")
                    # Continue shutdown despite errors

        self._write_progress("✓ Shutdown complete\n")

    def get_results_summary(self) -> list[tuple[str, float]]:
        """Get timing results for dashboard display."""
        return [(s.name, round(s.duration, 2)) for s in self.executed_steps]

    @staticmethod
    def _write_progress(message: str) -> None:
        """Write progress to stderr (single-line updates)."""
        if message.endswith("\n"):
            sys.stderr.write(f"\r{message}")
        else:
            sys.stderr.write(f"\r{message:<60}")
        sys.stderr.flush()
