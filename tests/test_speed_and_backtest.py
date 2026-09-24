"""Tests for job speed and the sales-script backtest gate.

Two behaviours are pinned here:

1. **Speed.** Independent provider calls (departments, subtasks, backtest
   rounds) run concurrently, and a job has a hard wall-clock budget so it can
   never run for tens of minutes.
2. **Backtest targets.** Only sales scripts are backtested, and the bar is per
   specialist: a closer script must close at least 20% of calls, a setter script
   must book at least 50%.
"""

from __future__ import annotations

import time

import pytest

from backend.evaluations import metrics


# ------------------------------------------------------------------ targets


def test_backtest_targets_are_per_specialist():
    """A closer script is judged at 20%, a setter script at 50%."""
    assert metrics.target_for("closing") == pytest.approx(0.20)
    assert metrics.target_for("appointment_setting") == pytest.approx(0.50)


def test_unknown_specialist_falls_back_to_the_global_default():
    from backend.config import BACKTEST_TARGET_CONVERSION

    assert metrics.target_for("not_a_specialist") == pytest.approx(BACKTEST_TARGET_CONVERSION)


def test_only_sales_scripts_require_a_backtest():
    """Backtesting must be limited to the setter and closer scripts."""
    from backend.agents.registry import SPECIALISTS

    gated = {name for name, spec in SPECIALISTS.items() if spec.requires_backtest}
    assert gated == {"appointment_setting", "closing"}


# ------------------------------------------------------------------ backtest


def _stub_provider(monkeypatch, *, convert_every: int, latency: float = 0.0):
    """Replace the provider-backed simulation and scoring with deterministic fakes.

    `convert_every` controls the conversion rate: a call converts unless its
    index is a multiple of `convert_every`. So `convert_every=5` yields 80%.
    """
    calls: list[int] = []

    def fake_simulate(script, personas, *, call_context="", max_turns=10):
        if latency:
            time.sleep(latency)
        calls.append(len(personas))
        return [
            {
                "persona": persona.key,
                "turns": [{"speaker": "lead", "text": "yes"}],
                "lead_final_stance": "in",
            }
            for persona in personas
        ]

    def fake_score(transcripts, *, objective):
        results = [
            {
                "persona": transcript["persona"],
                "converted": index % convert_every != 0,
                "confidence": 0.9,
                "reason": "",
                "failure_point": "",
                "script_gap": "",
            }
            for index, transcript in enumerate(transcripts)
        ]
        conversions = sum(1 for item in results if item["converted"])
        return {
            "results": results,
            "conversions": conversions,
            "total": len(results),
            "conversion_rate": round(conversions / len(results), 4) if results else 0.0,
        }

    monkeypatch.setattr(metrics, "simulate_batch", fake_simulate)
    monkeypatch.setattr(metrics, "score_batch", fake_score)
    return calls


def test_backtest_passes_when_the_target_is_met(monkeypatch):
    _stub_provider(monkeypatch, convert_every=5)  # 80% conversion

    result = metrics.run_backtest("closing", "SCRIPT")

    assert result.passed is True
    assert result.calls >= result.minimum_calls
    assert result.conversion_rate >= result.target_rate


def test_backtest_fails_when_the_target_is_missed(monkeypatch):
    _stub_provider(monkeypatch, convert_every=2)  # 50% conversion

    # A closer needs 20%, so 50% passes; a setter needs 50%, which is met exactly.
    # Force a miss by demanding a higher bar than the script can reach.
    result = metrics.run_backtest("closing", "SCRIPT", target_rate=0.9)

    assert result.passed is False
    assert result.conversion_rate < 0.9
    assert result.revision_notes


def test_backtest_rounds_run_concurrently(monkeypatch):
    """A wave of rounds must cost roughly one round of wall-clock time."""
    latency = 0.2
    calls = _stub_provider(monkeypatch, convert_every=5, latency=latency)

    start = time.monotonic()
    result = metrics.run_backtest("closing", "SCRIPT")
    elapsed = time.monotonic() - start

    # The first wave is 5 rounds (20 calls / batch of 4). Run sequentially that
    # would cost at least 5 * latency; concurrently it costs about one latency.
    assert len(calls) >= 5
    assert elapsed < latency * len(calls), (
        f"rounds did not run concurrently: {elapsed:.2f}s for {len(calls)} rounds"
    )
    assert result.passed is True


def test_backtest_stops_after_the_first_wave_when_the_target_is_met(monkeypatch):
    """A passing script must not spend extra rounds it does not need."""
    calls = _stub_provider(monkeypatch, convert_every=5)

    result = metrics.run_backtest("closing", "SCRIPT")

    # 20 calls / batch of 4 = 5 rounds, and no more.
    assert result.rounds == 5
    assert len(calls) == 5


def test_backtest_respects_its_deadline(monkeypatch):
    """A slow provider must not let the gate run past its wall-clock budget."""
    latency = 0.4
    calls = _stub_provider(monkeypatch, convert_every=2, latency=latency)  # 50%: misses 90%

    start = time.monotonic()
    result = metrics.run_backtest("closing", "SCRIPT", target_rate=0.9, deadline_seconds=1.0)
    elapsed = time.monotonic() - start

    # The first wave always runs; the deadline stops any later wave.
    assert result.passed is False
    assert len(calls) == 5
    assert elapsed < latency * 5 * 2, f"deadline was not enforced: {elapsed:.2f}s"


def test_backtest_reports_measured_rate_never_a_guess(monkeypatch):
    _stub_provider(monkeypatch, convert_every=4)  # 75%

    result = metrics.run_backtest("appointment_setting", "SCRIPT")

    assert result.conversions == sum(
        1 for item in result.persona_breakdown if item["converted"]
    )
    assert result.conversion_rate == pytest.approx(result.conversions / result.calls, abs=1e-4)


# --------------------------------------------------------------------- queue


def test_queue_runtime_budget_is_bounded():
    """The watchdog must clear a hung job quickly, not after 45 minutes."""
    from backend.config import PIPELINE_DEADLINE_SECONDS
    from backend.services import queue

    assert queue.MAX_JOB_RUNTIME_SECONDS <= PIPELINE_DEADLINE_SECONDS + 300
    assert queue.DEFAULT_ESTIMATE_SECONDS <= 300


# -------------------------------------------------------------- orchestrator


def test_orchestrator_runs_departments_concurrently(monkeypatch):
    """A request spanning two departments must not pay for them sequentially."""
    from backend.agents import manager as manager_agent
    from backend.agents.departments import head as head_agent
    from backend.agents.specialists import runner as specialist_runner
    from backend.orchestrator import Orchestrator

    latency = 0.2

    def json_response(payload):
        import json

        return {"content": json.dumps(payload), "model": "stub", "latency_ms": 1, "attempts": 1}

    def text_response(text):
        return {"content": text, "model": "stub", "latency_ms": 1, "attempts": 1}

    def fake_manager(role, prompt, system_prompt="", **kwargs):
        time.sleep(latency)
        if "TRIAGE" in system_prompt:
            return json_response(
                {"departments": ["marketing", "automation"], "reasoning": "x", "confidence": 0.9}
            )
        if "REWRITE" in system_prompt:
            return json_response(
                {
                    "objective": "obj",
                    "deliverable": "del",
                    "requirements": [],
                    "constraints": [],
                    "success_criteria": [],
                }
            )
        return text_response("FINAL ANSWER")

    def fake_head(role, prompt, system_prompt="", **kwargs):
        time.sleep(latency)
        if "PLAN" in system_prompt:
            specialist = "ad_copywriting" if "marketing" in system_prompt else "lead_nurturing"
            return json_response(
                {
                    "summary": "s",
                    "shared_context": "sc",
                    "subtasks": [
                        {
                            "id": "subtask-1",
                            "specialist": specialist,
                            "instruction": "do it",
                            "expected_output": "out",
                            "depends_on": [],
                        }
                    ],
                }
            )
        if "VERIFY" in system_prompt:
            return json_response(
                {"passed": True, "reason": "ok", "issues": [], "fix_instruction": ""}
            )
        return text_response("COMBINED DEPARTMENT ANSWER")

    def fake_specialist(role, prompt, system_prompt="", **kwargs):
        time.sleep(latency)
        return text_response("Deliverable content. " * 20)

    monkeypatch.setattr(manager_agent, "route_prompt", fake_manager)
    monkeypatch.setattr(head_agent, "route_prompt", fake_head)
    monkeypatch.setattr(specialist_runner, "route_prompt", fake_specialist)

    start = time.monotonic()
    result = Orchestrator().run("Write an ad and a nurture sequence.")
    elapsed = time.monotonic() - start

    assert result.status == "ok"
    assert result.departments == ["marketing", "automation"]
    # Sequential would cost ~6 * latency (2 departments x 3 calls each).
    assert elapsed < latency * 6, f"departments did not run concurrently: {elapsed:.2f}s"


def test_orchestrator_stops_revising_when_the_budget_is_spent(monkeypatch):
    """A job that exhausts its budget must report an honest failure, not hang."""
    from backend.agents import manager as manager_agent
    from backend.agents.departments import head as head_agent
    from backend.agents.specialists import runner as specialist_runner
    from backend.orchestrator import Orchestrator

    def json_response(payload):
        import json

        return {"content": json.dumps(payload), "model": "stub", "latency_ms": 1, "attempts": 1}

    def text_response(text):
        return {"content": text, "model": "stub", "latency_ms": 1, "attempts": 1}

    def fake_manager(role, prompt, system_prompt="", **kwargs):
        if "TRIAGE" in system_prompt:
            return json_response(
                {"departments": ["marketing"], "reasoning": "x", "confidence": 0.9}
            )
        if "REWRITE" in system_prompt:
            return json_response(
                {
                    "objective": "obj",
                    "deliverable": "del",
                    "requirements": [],
                    "constraints": [],
                    "success_criteria": [],
                }
            )
        return text_response("FINAL ANSWER")

    def fake_head(role, prompt, system_prompt="", **kwargs):
        if "PLAN" in system_prompt:
            return json_response(
                {
                    "summary": "s",
                    "shared_context": "",
                    "subtasks": [
                        {
                            "id": "subtask-1",
                            "specialist": "ad_copywriting",
                            "instruction": "do it",
                            "expected_output": "out",
                            "depends_on": [],
                        }
                    ],
                }
            )
        # Always reject, so the pipeline would otherwise keep revising.
        return json_response(
            {"passed": False, "reason": "Not good enough.", "issues": ["x"], "fix_instruction": "fix"}
        )

    def fake_specialist(role, prompt, system_prompt="", **kwargs):
        return text_response("Deliverable content. " * 20)

    monkeypatch.setattr(manager_agent, "route_prompt", fake_manager)
    monkeypatch.setattr(head_agent, "route_prompt", fake_head)
    monkeypatch.setattr(specialist_runner, "route_prompt", fake_specialist)

    # A budget that is already spent: the first revision attempt must not run.
    result = Orchestrator(deadline_seconds=0.0).run("Write ad copy.")

    assert result.status == "error"
    assert result.body
