"""End-to-end flow tests using a stubbed model router.

These verify the full chain of command from the manager down to a specialist and
back up, without needing a live provider.
"""

from __future__ import annotations

import json

import pytest

from backend.agents.registry import DEPARTMENTS
from backend.errors import RoutingError
from backend.orchestrator import Orchestrator


def _json_response(payload: dict) -> dict:
    return {"content": json.dumps(payload), "model": "test", "usage": {}, "latency_ms": 1, "attempts": 1}


def _text_response(text: str) -> dict:
    return {"content": text, "model": "test", "usage": {}, "latency_ms": 1, "attempts": 1}


def test_manager_routes_marketing_request(monkeypatch):
    from backend.agents import manager as manager_agent

    monkeypatch.setattr(
        manager_agent,
        "route_prompt",
        lambda *args, **kwargs: _json_response(
            {
                "departments": ["marketing"],
                "reasoning": "Advertising request.",
                "confidence": 0.9,
            }
        ),
    )

    decision = manager_agent.triage(
        "Write 5 ad variations for Arizona homeowners for a free solar consultation."
    )

    assert decision.departments == ["marketing"]


def test_manager_refuses_out_of_scope_request(monkeypatch):
    """Out-of-scope requests must fail loudly, not default to a department."""
    from backend.agents import manager as manager_agent

    monkeypatch.setattr(
        manager_agent,
        "route_prompt",
        lambda *args, **kwargs: _json_response(
            {"departments": [], "reasoning": "Not a business asset request.", "confidence": 0.05}
        ),
    )

    with pytest.raises(RoutingError):
        manager_agent.triage("explain quantum entanglement")


def test_orchestrator_walks_the_full_chain_for_marketing(monkeypatch):
    """manager -> marketing head -> specialist -> head -> manager."""
    from backend.agents import manager as manager_agent
    from backend.agents.departments import head as head_agent
    from backend.agents.specialists import runner as specialist_runner

    def fake_manager(role, prompt, system_prompt="", **kwargs):
        if "TRIAGE" in system_prompt:
            return _json_response(
                {
                    "departments": ["marketing"],
                    "reasoning": "Advertising request.",
                    "confidence": 0.9,
                }
            )
        if "REWRITE" in system_prompt:
            return _json_response(
                {
                    "objective": "Write ad copy for Arizona homeowners.",
                    "deliverable": "Three ad variations with headline, body, and CTA.",
                    "requirements": ["Use only verified business facts"],
                    "constraints": ["No prohibited claims"],
                    "success_criteria": ["Ready to publish"],
                }
            )
        return _text_response("## Ad copy\n\nFINAL AD COPY OUTPUT")

    def fake_head(role, prompt, system_prompt="", **kwargs):
        if "PLAN" in system_prompt:
            return _json_response(
                {
                    "summary": "One specialist writes the copy.",
                    "shared_context": "Arizona homeowners, residential solar evaluation.",
                    "subtasks": [
                        {
                            "id": "subtask-1",
                            "specialist": "ad_copywriting",
                            "instruction": "Write three compliant ad variations.",
                            "expected_output": "Headline, body, and CTA for each variation.",
                            "depends_on": [],
                        }
                    ],
                }
            )
        if "VERIFY" in system_prompt:
            return _json_response(
                {"passed": True, "reason": "Complete and compliant.", "issues": [], "fix_instruction": ""}
            )
        return _text_response("COMBINED MARKETING ANSWER")

    def fake_specialist(role, prompt, system_prompt="", **kwargs):
        return _text_response(
            "Headline: Understand your solar options.\n"
            "Body: Homeowners in Arizona can request a residential solar evaluation "
            "to see whether solar may make sense for their property.\n"
            "CTA: Request your evaluation today."
        )

    monkeypatch.setattr(manager_agent, "route_prompt", fake_manager)
    monkeypatch.setattr(head_agent, "route_prompt", fake_head)
    monkeypatch.setattr(specialist_runner, "route_prompt", fake_specialist)

    result = Orchestrator().run("Write ad copy for Arizona homeowners about solar evaluations.")

    assert result.status == "ok"
    # With a single specialist the head and manager pass the verified deliverable
    # straight through instead of making redundant merge calls.
    assert "Understand your solar options" in result.body
    assert result.departments == ["marketing"]
    stages = [step.stage for step in result.trace]
    assert stages == ["triage", "rewrite", "plan", "specialist", "verify", "combine", "finalize"]


def test_orchestrator_returns_error_for_out_of_scope_request(monkeypatch):
    from backend.agents import manager as manager_agent

    monkeypatch.setattr(
        manager_agent,
        "route_prompt",
        lambda *args, **kwargs: _json_response(
            {"departments": [], "reasoning": "Out of scope.", "confidence": 0.02}
        ),
    )

    result = Orchestrator().run("what is the weather today")

    assert result.status == "error"
    assert result.error is not None
    assert result.error["code"] == "routing_error"
    assert result.body  # an explanatory message is always present
    assert result.trace[-1].status == "error"


def test_orchestrator_rejects_unverified_specialist_work(monkeypatch):
    """Work that fails head verification must not be delivered."""
    from backend.agents import manager as manager_agent
    from backend.agents.departments import head as head_agent
    from backend.agents.specialists import runner as specialist_runner

    def fake_manager(role, prompt, system_prompt="", **kwargs):
        if "TRIAGE" in system_prompt:
            return _json_response(
                {"departments": ["marketing"], "reasoning": "Ad request.", "confidence": 0.9}
            )
        if "REWRITE" in system_prompt:
            return _json_response(
                {
                    "objective": "Write ad copy.",
                    "deliverable": "Ad copy variations.",
                    "requirements": [],
                    "constraints": [],
                    "success_criteria": [],
                }
            )
        return _text_response("SHOULD NOT BE REACHED")

    def fake_head(role, prompt, system_prompt="", **kwargs):
        if "PLAN" in system_prompt:
            return _json_response(
                {
                    "summary": "One specialist.",
                    "shared_context": "",
                    "subtasks": [
                        {
                            "id": "subtask-1",
                            "specialist": "ad_copywriting",
                            "instruction": "Write ad copy.",
                            "expected_output": "Ad copy.",
                            "depends_on": [],
                        }
                    ],
                }
            )
        if "VERIFY" in system_prompt:
            return _json_response(
                {
                    "passed": False,
                    "reason": "The deliverable does not answer the brief.",
                    "issues": ["Missing CTA"],
                    "fix_instruction": "Add a clear CTA.",
                }
            )
        return _text_response("")

    def fake_specialist(role, prompt, system_prompt="", **kwargs):
        return _text_response("A".join(["word "] * 40))

    monkeypatch.setattr(manager_agent, "route_prompt", fake_manager)
    monkeypatch.setattr(head_agent, "route_prompt", fake_head)
    monkeypatch.setattr(specialist_runner, "route_prompt", fake_specialist)

    result = Orchestrator().run("Write ad copy.")

    assert result.status == "error"
    assert "verified answer" in result.message
    assert result.body  # the rejection reason is reported, not hidden


def test_orchestrator_backtests_sales_scripts(monkeypatch):
    """A sales script must clear the measured backtest before delivery."""
    from backend.agents import manager as manager_agent
    from backend.agents.departments import head as head_agent
    from backend.agents.specialists import runner as specialist_runner
    from backend import orchestrator as orchestrator_module

    def fake_manager(role, prompt, system_prompt="", **kwargs):
        if "TRIAGE" in system_prompt:
            return _json_response(
                {"departments": ["sales"], "reasoning": "Script task.", "confidence": 0.9}
            )
        if "REWRITE" in system_prompt:
            return _json_response(
                {
                    "objective": "Optimize the setter script.",
                    "deliverable": "A revised setter script.",
                    "requirements": [],
                    "constraints": [],
                    "success_criteria": [],
                }
            )
        return _text_response("REVISED SETTER SCRIPT")

    def fake_head(role, prompt, system_prompt="", **kwargs):
        if "PLAN" in system_prompt:
            return _json_response(
                {
                    "summary": "One specialist.",
                    "shared_context": "",
                    "subtasks": [
                        {
                            "id": "subtask-1",
                            "specialist": "appointment_setting",
                            "instruction": "Optimize the setter script.",
                            "expected_output": "A revised setter script.",
                            "depends_on": [],
                        }
                    ],
                }
            )
        if "VERIFY" in system_prompt:
            return _json_response(
                {"passed": True, "reason": "Valid setter script.", "issues": [], "fix_instruction": ""}
            )
        return _text_response("COMBINED SALES ANSWER")

    def fake_specialist(role, prompt, system_prompt="", **kwargs):
        return _text_response(
            "APPOINTMENT SETTING SCRIPT\n" + "Opening, discovery, qualification, booking, objections. " * 6
        )

    def fake_backtest(specialist_name, script, *, call_context="", **kwargs):
        from backend.evaluations.metrics import BacktestResult

        return BacktestResult(
            passed=True,
            conversion_rate=0.6,
            calls=20,
            conversions=12,
            rounds=5,
            target_rate=0.5,
            minimum_calls=20,
        )

    monkeypatch.setattr(manager_agent, "route_prompt", fake_manager)
    monkeypatch.setattr(head_agent, "route_prompt", fake_head)
    monkeypatch.setattr(specialist_runner, "route_prompt", fake_specialist)
    monkeypatch.setattr(orchestrator_module, "run_backtest", fake_backtest)

    result = Orchestrator().run("optimize my appointment setter script")

    assert result.status == "ok"
    assert result.backtests
    assert result.backtests[0]["passed"] is True
    assert result.backtests[0]["conversion_rate"] == 0.6
    assert "backtest" in [step.stage for step in result.trace]


def test_orchestrator_rejects_script_that_fails_backtest(monkeypatch):
    """A script that misses the conversion target must not be delivered."""
    from backend.agents import manager as manager_agent
    from backend.agents.departments import head as head_agent
    from backend.agents.specialists import runner as specialist_runner
    from backend import orchestrator as orchestrator_module

    def fake_manager(role, prompt, system_prompt="", **kwargs):
        if "TRIAGE" in system_prompt:
            return _json_response(
                {"departments": ["sales"], "reasoning": "Script task.", "confidence": 0.9}
            )
        if "REWRITE" in system_prompt:
            return _json_response(
                {
                    "objective": "Optimize the setter script.",
                    "deliverable": "A revised setter script.",
                    "requirements": [],
                    "constraints": [],
                    "success_criteria": [],
                }
            )
        return _text_response("SHOULD NOT BE REACHED")

    def fake_head(role, prompt, system_prompt="", **kwargs):
        if "PLAN" in system_prompt:
            return _json_response(
                {
                    "summary": "One specialist.",
                    "shared_context": "",
                    "subtasks": [
                        {
                            "id": "subtask-1",
                            "specialist": "appointment_setting",
                            "instruction": "Optimize the setter script.",
                            "expected_output": "A revised setter script.",
                            "depends_on": [],
                        }
                    ],
                }
            )
        return _json_response(
            {"passed": True, "reason": "Looks fine.", "issues": [], "fix_instruction": ""}
        )

    def fake_specialist(role, prompt, system_prompt="", **kwargs):
        return _text_response("APPOINTMENT SETTING SCRIPT\n" + "Script content. " * 20)

    def failing_backtest(specialist_name, script, *, call_context="", **kwargs):
        from backend.evaluations.metrics import BacktestResult

        return BacktestResult(
            passed=False,
            conversion_rate=0.2,
            calls=20,
            conversions=4,
            rounds=5,
            target_rate=0.5,
            minimum_calls=20,
            revision_notes="- No booking ask present.",
        )

    monkeypatch.setattr(manager_agent, "route_prompt", fake_manager)
    monkeypatch.setattr(head_agent, "route_prompt", fake_head)
    monkeypatch.setattr(specialist_runner, "route_prompt", fake_specialist)
    monkeypatch.setattr(orchestrator_module, "run_backtest", failing_backtest)

    result = Orchestrator().run("optimize my appointment setter script")

    assert result.status == "error"
    assert result.body
    assert any(step.stage == "backtest" and step.status == "error" for step in result.trace)


def test_orchestrator_blocks_non_compliant_output(monkeypatch):
    """Prohibited claims must block delivery even when verification passes."""
    from backend.agents import manager as manager_agent
    from backend.agents.departments import head as head_agent
    from backend.agents.specialists import runner as specialist_runner

    def fake_manager(role, prompt, system_prompt="", **kwargs):
        if "TRIAGE" in system_prompt:
            return _json_response(
                {"departments": ["marketing"], "reasoning": "Ad request.", "confidence": 0.9}
            )
        if "REWRITE" in system_prompt:
            return _json_response(
                {
                    "objective": "Write ad copy.",
                    "deliverable": "Ad copy.",
                    "requirements": [],
                    "constraints": [],
                    "success_criteria": [],
                }
            )
        return _text_response("Get free solar panels today and eliminate your electric bill!")

    def fake_head(role, prompt, system_prompt="", **kwargs):
        if "PLAN" in system_prompt:
            return _json_response(
                {
                    "summary": "One specialist.",
                    "shared_context": "",
                    "subtasks": [
                        {
                            "id": "subtask-1",
                            "specialist": "ad_copywriting",
                            "instruction": "Write ad copy.",
                            "expected_output": "Ad copy.",
                            "depends_on": [],
                        }
                    ],
                }
            )
        return _json_response(
            {"passed": True, "reason": "Approved.", "issues": [], "fix_instruction": ""}
        )

    def fake_specialist(role, prompt, system_prompt="", **kwargs):
        return _text_response(
            "Get free solar panels today and eliminate your electric bill! " * 5
        )

    monkeypatch.setattr(manager_agent, "route_prompt", fake_manager)
    monkeypatch.setattr(head_agent, "route_prompt", fake_head)
    monkeypatch.setattr(specialist_runner, "route_prompt", fake_specialist)

    result = Orchestrator().run("Write ad copy about solar.")

    assert result.status == "error"
    assert any(step.stage == "compliance" for step in result.trace)

