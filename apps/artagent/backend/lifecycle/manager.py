"""
Lifecycle Manager - Clean startup/shutdown orchestration.

Provides a simple, maintainable way to manage application lifecycle without
complex nested wrappers or excessive logging that overwhelms junior developers.

Supports deferred startup tasks that run in the background after the main
startup completes, allowing the application to start accepting requests faster.
"""

from __future__ import annotations

import asyncio
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
    deferred: bool = False  # If True, runs after main startup completes


@dataclass
class LifecycleManager:
    """
    Manages application startup and shutdown in a clean, sequential manner.

    Design goals:
    - Simple and readable for junior developers
    - Clean, ordered progress logs (one consistent line per step)
    - Clear error reporting
    - Proper tracing for production observability

    Deferred Steps:
    - Steps marked as deferred run in the background after main startup completes
    - This allows the app to accept requests faster while non-critical warmup continues
    - Deferred step failures are logged but don't prevent the app from running
    """

    steps: list[LifecycleStep] = field(default_factory=list)
    deferred_steps: list[LifecycleStep] = field(default_factory=list)
    executed_steps: list[LifecycleStep] = field(default_factory=list)
    deferred_task: asyncio.Task | None = field(default=None, init=False)
    _tracer: trace.Tracer = field(default=None, init=False)

    def __post_init__(self):
        self._tracer = trace.get_tracer(__name__)

    def add_step(
        self,
        name: str,
        startup: Callable[[], Awaitable[None]],
        shutdown: Callable[[], Awaitable[None]] | None = None,
        deferred: bool = False,
    ) -> None:
        """Register a lifecycle step.

        Args:
            name: Step name for logging and tracing
            startup: Async function to run at startup
            shutdown: Optional async function to run at shutdown
            deferred: If True, step runs in background after main startup completes
        """
        step = LifecycleStep(name=name, startup=startup, shutdown=shutdown, deferred=deferred)
        if deferred:
            self.deferred_steps.append(step)
        else:
            self.steps.append(step)

    async def run_startup(self) -> list[tuple[str, float]]:
        """
        Execute all blocking startup steps with clean, ordered progress logs.

        Each step is reported as a single, consistently-formatted log line so the
        sequence stays readable even when components emit their own logs mid-step.

        Returns:
            List of (step_name, duration_seconds) for reporting.
        """
        results: list[tuple[str, float]] = []
        total = len(self.steps)

        logger.info("Startup · initializing %d components", total)

        for i, step in enumerate(self.steps, start=1):
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
                    logger.error("  %d/%d %-9s ✗ %s", i, total, step.name, exc)
                    raise

                step.duration = time.perf_counter() - step_start
                span.set_attribute("duration_sec", step.duration)

            self.executed_steps.append(step)
            results.append((step.name, round(step.duration, 2)))
            logger.info("  %d/%d %-9s ✓ %.2fs", i, total, step.name, step.duration)

        total_time = sum(d for _, d in results)
        logger.info("Startup · core ready in %.1fs", total_time)

        return results

    def start_deferred_startup(self, app) -> None:
        """
        Start deferred startup tasks in the background.

        Call this after the main startup completes and the app is ready to serve.
        Deferred tasks run without blocking request handling.

        Args:
            app: FastAPI application instance for storing deferred status
        """
        if not self.deferred_steps:
            app.state.deferred_startup_complete = True
            app.state.deferred_startup_results = {}
            return

        async def run_deferred():
            results = {}
            deferred_names = [s.name for s in self.deferred_steps]
            total = len(self.deferred_steps)
            logger.info(
                "Deferred · %d task(s) in background: %s", total, ", ".join(deferred_names)
            )

            for i, step in enumerate(self.deferred_steps, start=1):
                step_start = time.perf_counter()

                with self._tracer.start_as_current_span(f"startup.deferred.{step.name}") as span:
                    try:
                        await step.startup()
                        step.success = True
                        step.duration = time.perf_counter() - step_start
                        span.set_attribute("duration_sec", step.duration)
                        results[step.name] = {"success": True, "duration": round(step.duration, 2)}
                        logger.info(
                            "  %d/%d %-9s ✓ %.2fs (deferred)", i, total, step.name, step.duration
                        )
                    except Exception as exc:
                        step.error = str(exc)
                        step.success = False
                        step.duration = time.perf_counter() - step_start
                        span.record_exception(exc)
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                        results[step.name] = {"success": False, "error": str(exc), "duration": round(step.duration, 2)}
                        logger.warning(
                            "  %d/%d %-9s ✗ %s (non-blocking)", i, total, step.name, exc
                        )

                # Track for shutdown even if failed
                self.executed_steps.append(step)

            app.state.deferred_startup_complete = True
            app.state.deferred_startup_results = results
            total_deferred = sum(r.get("duration", 0) for r in results.values())
            success_count = sum(1 for r in results.values() if r.get("success"))
            logger.info(
                "Deferred · %d/%d complete in %.1fs", success_count, len(results), total_deferred
            )

        # Initialize state for readiness checks
        app.state.deferred_startup_complete = False
        app.state.deferred_startup_results = {}

        # Fire and forget - the task runs in the background
        self.deferred_task = asyncio.create_task(run_deferred(), name="deferred-startup")

    async def run_shutdown(self) -> None:
        """Execute shutdown steps in reverse order."""
        logger.info("Shutdown · stopping")

        # Cancel any pending deferred startup task
        if self.deferred_task is not None and not self.deferred_task.done():
            logger.info("  cancelling deferred startup")
            self.deferred_task.cancel()
            try:
                await asyncio.wait_for(self.deferred_task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        stopped = 0
        for step in reversed(self.executed_steps):
            if step.shutdown is None:
                continue

            with self._tracer.start_as_current_span(f"shutdown.{step.name}") as span:
                try:
                    await step.shutdown()
                    stopped += 1
                except Exception as exc:
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                    logger.warning("  shutdown '%s' failed: %s", step.name, exc)
                    # Continue shutdown despite errors

        logger.info("Shutdown · complete (%d steps)", stopped)

    def get_results_summary(self) -> list[tuple[str, float]]:
        """Get timing results for dashboard display."""
        return [(s.name, round(s.duration, 2)) for s in self.executed_steps if not s.deferred]

    def get_deferred_step_names(self) -> list[str]:
        """Get names of deferred steps (for dashboard display)."""
        return [s.name for s in self.deferred_steps]
