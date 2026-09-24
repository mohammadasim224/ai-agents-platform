"""Backtest orchestration.

Implements the sales script quality gate: a script is not accepted until it
converts at least its specialist-specific target over at least
`BACKTEST_MIN_CALLS` roleplays.

The bar is per specialist:

- A **closer** script must close at least 20% of simulated calls.
- A **setter** script must book at least 50% of simulated calls.

The loop is honest by construction:

- Calls accumulate across rounds, so a script must sustain performance rather
  than pass on one lucky batch.
- Conversion is judged by a separate scoring agent, not by the script.
- If the gate is not reached within the round budget, the backtest reports
  failure with the measured rate. It never reports success it did not measure.

Speed: rounds are independent, so they run concurrently in a bounded thread
pool. A wave of rounds costs roughly one round of wall-clock time instead of
one round per round. A wall-clock deadline bounds the whole gate so a slow
provider cannot make a job run for tens of minutes.
"""

from __future__ import annotations

import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.config import (
    BACKTEST_BATCH_SIZE,
    BACKTEST_DEADLINE_SECONDS,
    BACKTEST_MAX_CALLS,
    BACKTEST_MAX_ROUNDS,
    BACKTEST_MIN_CALLS,
    BACKTEST_TARGET_CONVERSION,
    BACKTEST_TARGETS,
    PIPELINE_MAX_WORKERS,
)
from backend.evaluations.roleplay import persona_pool, simulate_batch
from backend.evaluations.scoring import APPOINTMENT_SETTING_METRIC, CLOSING_METRIC, score_batch

# A single shared pool bounds total provider concurrency. Backtests can run
# inside subtask threads that are themselves running concurrently, so a pool per
# backtest would multiply the fan-out (subtasks x rounds) and invite rate limits.
# One shared, bounded pool keeps the total number of in-flight provider calls
# predictable no matter how the pipeline is nested.
_EXECUTOR: ThreadPoolExecutor | None = None
_EXECUTOR_LOCK = threading.Lock()


def _executor() -> ThreadPoolExecutor:
    global _EXECUTOR
    if _EXECUTOR is None:
        with _EXECUTOR_LOCK:
            if _EXECUTOR is None:
                _EXECUTOR = ThreadPoolExecutor(
                    max_workers=max(1, PIPELINE_MAX_WORKERS),
                    thread_name_prefix="backtest",
                )
    return _EXECUTOR


@dataclass
class BacktestResult:
    """The measured outcome of a script backtest."""

    passed: bool
    conversion_rate: float
    calls: int
    conversions: int
    rounds: int
    target_rate: float
    minimum_calls: int
    persona_breakdown: list[dict[str, Any]] = field(default_factory=list)
    revision_notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "conversion_rate": self.conversion_rate,
            "calls": self.calls,
            "conversions": self.conversions,
            "rounds": self.rounds,
            "target_rate": self.target_rate,
            "minimum_calls": self.minimum_calls,
            "persona_breakdown": self.persona_breakdown,
            "revision_notes": self.revision_notes,
        }

    def summary(self) -> str:
        percent = round(self.conversion_rate * 100, 1)
        target = round(self.target_rate * 100, 1)
        verdict = "PASSED" if self.passed else "FAILED"
        return (
            f"Backtest {verdict}: {self.conversions}/{self.calls} calls converted "
            f"({percent}%) against a {target}% target over {self.rounds} round(s)."
        )


def objective_for(specialist_name: str) -> str:
    """Define what counts as a conversion for a given sales specialist."""
    if specialist_name == "closing":
        return (
            "The lead explicitly agreed to move forward with the offer at the presented "
            f"price or payment structure ({CLOSING_METRIC})."
        )
    return (
        "The lead explicitly agreed to a specific appointment with the closer, including "
        f"a confirmed day and time ({APPOINTMENT_SETTING_METRIC})."
    )


def target_for(specialist_name: str) -> float:
    """Return the conversion target for a specialist.

    A closer script must close at least 20% of calls; a setter script must book
    at least 50%. Unknown specialists fall back to the global default.
    """
    return BACKTEST_TARGETS.get(specialist_name, BACKTEST_TARGET_CONVERSION)


def _run_round(
    script: str,
    personas: list[Any],
    *,
    call_context: str,
    objective: str,
) -> dict[str, Any]:
    """Simulate and score one batch of calls. Runs inside a worker thread."""
    transcripts = simulate_batch(script, personas, call_context=call_context)
    return score_batch(transcripts, objective=objective)


def run_backtest(
    specialist_name: str,
    script: str,
    *,
    call_context: str = "",
    target_rate: float | None = None,
    minimum_calls: int = BACKTEST_MIN_CALLS,
    max_calls: int = BACKTEST_MAX_CALLS,
    batch_size: int = BACKTEST_BATCH_SIZE,
    max_rounds: int = BACKTEST_MAX_ROUNDS,
    deadline_seconds: float | None = None,
    on_round: Callable[[dict[str, Any]], None] | None = None,
) -> BacktestResult:
    """Backtest a sales script against simulated leads.

    Rounds run concurrently, so the gate costs roughly one round of wall-clock
    time per wave rather than one round per round. The first wave is sized to
    reach `minimum_calls`; if the script already clears its target the backtest
    stops there. Otherwise later waves run until the target is met, the call
    budget is exhausted, or the deadline passes.

    Returns a `BacktestResult` describing the measured performance. Callers decide
    whether to treat a failed backtest as a hard error.
    """
    objective = objective_for(specialist_name)
    resolved_target = target_for(specialist_name) if target_rate is None else target_rate
    budget = BACKTEST_DEADLINE_SECONDS if deadline_seconds is None else deadline_seconds
    deadline = time.monotonic() + max(1.0, budget)

    all_results: list[dict[str, Any]] = []
    rounds = 0
    revision_notes = ""
    last_error: Exception | None = None

    # The first wave must be large enough to reach the minimum call count, so a
    # passing script is confirmed in a single wave.
    first_wave = max(1, math.ceil(minimum_calls / max(1, batch_size)))
    first_wave = min(first_wave, max_rounds)

    def _wave(count: int) -> None:
        """Run `count` rounds concurrently and fold their results in."""
        nonlocal rounds, revision_notes, last_error
        if count <= 0:
            return
        remaining = max_calls - len(all_results)
        if remaining <= 0:
            return

        offsets = [len(all_results) + index * batch_size for index in range(count)]
        jobs: list[tuple[int, list[Any]]] = []
        for offset in offsets:
            if offset >= max_calls:
                break
            size = min(batch_size, max_calls - offset)
            if size <= 0:
                break
            jobs.append((offset, persona_pool(offset + size)[offset : offset + size]))
        if not jobs:
            return

        pool = _executor()
        futures = [
            pool.submit(
                _run_round,
                script,
                personas,
                call_context=call_context,
                objective=objective,
            )
            for _, personas in jobs
        ]
        for future in futures:
            try:
                scored = future.result()
            except Exception as exc:  # noqa: BLE001 - one bad round must not kill the gate
                last_error = exc
                continue
            rounds += 1
            all_results.extend(scored["results"])

        if on_round is not None and all_results:
            conversions = sum(1 for item in all_results if item["converted"])
            on_round(
                {
                    "round": rounds,
                    "calls": len(all_results),
                    "conversions": conversions,
                    "rate": round(conversions / len(all_results), 4),
                }
            )

        # Collect the most actionable gaps to drive the next revision.
        gaps = [
            item["script_gap"]
            for item in all_results
            if not item["converted"] and item.get("script_gap")
        ]
        if gaps:
            revision_notes = "\n".join(f"- {gap}" for gap in gaps[:6])

    def _passed() -> bool:
        if len(all_results) < minimum_calls:
            return False
        conversions = sum(1 for item in all_results if item["converted"])
        return (conversions / len(all_results)) >= resolved_target

    _wave(first_wave)

    # Later waves only run when the first wave did not already clear the bar.
    while (
        not _passed()
        and rounds < max_rounds
        and len(all_results) < max_calls
        and time.monotonic() < deadline
    ):
        _wave(min(max_rounds - rounds, math.ceil((max_calls - len(all_results)) / max(1, batch_size))))

    if not all_results and last_error is not None:
        raise last_error

    conversions = sum(1 for item in all_results if item["converted"])
    total = len(all_results)
    rate = round(conversions / total, 4) if total else 0.0
    passed = total >= minimum_calls and rate >= resolved_target

    if not passed and not revision_notes:
        failures = [
            f"- {item['persona']}: {item.get('failure_point') or item.get('reason')}"
            for item in all_results
            if not item["converted"]
        ]
        revision_notes = "\n".join(failures[:6]) or "- No specific failure points were reported."

    return BacktestResult(
        passed=passed,
        conversion_rate=rate,
        calls=total,
        conversions=conversions,
        rounds=rounds,
        target_rate=resolved_target,
        minimum_calls=minimum_calls,
        persona_breakdown=all_results,
        revision_notes=revision_notes,
    )
