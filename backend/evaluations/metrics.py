"""Backtest orchestration.

Implements the sales script quality gate: a script is not accepted until it
converts at least `BACKTEST_TARGET_CONVERSION` of simulated calls over at least
`BACKTEST_MIN_CALLS` roleplays.

The loop is honest by construction:

- Calls accumulate across rounds, so a script must sustain performance rather
  than pass on one lucky batch.
- Conversion is judged by a separate scoring agent, not by the script.
- If the gate is not reached within the round budget, the backtest reports
  failure with the measured rate. It never reports success it did not measure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from backend.config import (
    BACKTEST_BATCH_SIZE,
    BACKTEST_MAX_CALLS,
    BACKTEST_MAX_ROUNDS,
    BACKTEST_MIN_CALLS,
    BACKTEST_TARGET_CONVERSION,
)
from backend.errors import QualityGateError
from backend.evaluations.roleplay import persona_pool, simulate_batch
from backend.evaluations.scoring import APPOINTMENT_SETTING_METRIC, CLOSING_METRIC, score_batch


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


def run_backtest(
    specialist_name: str,
    script: str,
    *,
    call_context: str = "",
    target_rate: float = BACKTEST_TARGET_CONVERSION,
    minimum_calls: int = BACKTEST_MIN_CALLS,
    max_calls: int = BACKTEST_MAX_CALLS,
    batch_size: int = BACKTEST_BATCH_SIZE,
    max_rounds: int = BACKTEST_MAX_ROUNDS,
    on_round: Callable[[dict[str, Any]], None] | None = None,
) -> BacktestResult:
    """Backtest a sales script against simulated leads.

    Returns a `BacktestResult` describing the measured performance. Callers decide
    whether to treat a failed backtest as a hard error.
    """
    objective = objective_for(specialist_name)
    all_results: list[dict[str, Any]] = []
    rounds = 0
    revision_notes = ""

    while rounds < max_rounds and len(all_results) < max_calls:
        remaining = max_calls - len(all_results)
        this_batch = min(batch_size, remaining)
        if this_batch <= 0:
            break

        personas = persona_pool(len(all_results) + this_batch)[len(all_results) :]
        rounds += 1

        transcripts = simulate_batch(script, personas, call_context=call_context)
        scored = score_batch(transcripts, objective=objective)
        all_results.extend(scored["results"])

        if on_round is not None:
            on_round(
                {
                    "round": rounds,
                    "calls": len(all_results),
                    "conversions": sum(1 for item in all_results if item["converted"]),
                    "rate": (
                        round(
                            sum(1 for item in all_results if item["converted"]) / len(all_results),
                            4,
                        )
                        if all_results
                        else 0.0
                    ),
                }
            )

        conversions = sum(1 for item in all_results if item["converted"])
        rate = conversions / len(all_results) if all_results else 0.0

        # Stop early only when the gate is genuinely satisfied.
        if len(all_results) >= minimum_calls and rate >= target_rate:
            break

        # Collect the most actionable gaps to drive the next revision.
        gaps = [
            item["script_gap"]
            for item in scored["results"]
            if not item["converted"] and item.get("script_gap")
        ]
        if gaps:
            revision_notes = "\n".join(f"- {gap}" for gap in gaps[:6])

    conversions = sum(1 for item in all_results if item["converted"])
    total = len(all_results)
    rate = round(conversions / total, 4) if total else 0.0
    passed = total >= minimum_calls and rate >= target_rate

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
        target_rate=target_rate,
        minimum_calls=minimum_calls,
        persona_breakdown=all_results,
        revision_notes=revision_notes,
    )


def enforce(result: BacktestResult) -> BacktestResult:
    """Raise `QualityGateError` when a backtest did not meet the required bar."""
    if not result.passed:
        raise QualityGateError(
            result.summary(),
            stage="backtest",
            details=result.to_dict(),
            hint=(
                "The script was not accepted because it did not reach the measured "
                "conversion target. Provide more source material or relax the target."
            ),
        )
    return result
