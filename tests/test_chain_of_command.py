"""Chain-of-command tests.

These tests use a stubbed model router so the orchestration logic can be verified
without a live provider. They assert the structural guarantees of the system:

- Only the manager is user-facing.
- Routing never defaults to a department.
- Work flows manager -> head -> specialist -> head -> manager.
- Unverified work is never delivered.
"""

from __future__ import annotations

import json

import pytest

from backend.agents import manager as manager_agent
from backend.agents.registry import DEPARTMENTS, SPECIALISTS, department_names
from backend.errors import RoutingError


# --------------------------------------------------------------------- helpers


def _json_response(payload: dict) -> dict:
    return {"content": json.dumps(payload), "model": "test", "usage": {}, "latency_ms": 1, "attempts": 1}


def _text_response(text: str) -> dict:
    return {"content": text, "model": "test", "usage": {}, "latency_ms": 1, "attempts": 1}


# ------------------------------------------------------------------- org chart


def test_manager_is_the_only_user_facing_agent():
    """Every non-manager agent must be internal."""
    for department in DEPARTMENTS.values():
        assert department.name != "manager"
        for specialist in department.specialist_definitions():
            assert specialist.department == department.name
            assert specialist.name != "manager"


def test_every_department_has_at_least_one_specialist():
    for name in department_names():
        assert DEPARTMENTS[name].specialist_definitions(), f"{name} has no specialists"


def test_every_specialist_belongs_to_a_real_department():
    for specialist in SPECIALISTS.values():
        assert specialist.department in DEPARTMENTS


def test_every_agent_prompt_file_exists():
    """Every registered agent must have a prompt file on disk."""
    from backend.prompts.loader import load_prompt

    load_prompt("manager/manager")
    for department in DEPARTMENTS.values():
        load_prompt(department.prompt)
    for specialist in SPECIALISTS.values():
        load_prompt(specialist.prompt)
    load_prompt("evaluation/lead_simulator")
    load_prompt("evaluation/scoring")


def test_sales_script_agents_require_backtesting():
    """Script-writing sales agents must be gated by a measured backtest."""
    assert SPECIALISTS["appointment_setting"].requires_backtest is True
    assert SPECIALISTS["closing"].requires_backtest is True


def test_prompt_files_contain_no_unfilled_placeholders():
    """Prompt files must not contain bare ellipsis placeholders."""
    from backend.prompts.loader import load_prompt

    prompt_names = ["manager/manager", "evaluation/lead_simulator", "evaluation/scoring"]
    prompt_names += [department.prompt for department in DEPARTMENTS.values()]
    prompt_names += [specialist.prompt for specialist in SPECIALISTS.values()]

    for name in prompt_names:
        body = load_prompt(name)
        for line in body.splitlines():
            assert line.strip() != "...", f"{name} contains a bare ellipsis placeholder"


# --------------------------------------------------------------------- triage


def test_triage_assigns_sales_for_script_optimization(monkeypatch):
    monkeypatch.setattr(
        manager_agent,
        "route_prompt",
        lambda *args, **kwargs: _json_response(
            {
                "departments": ["sales"],
                "reasoning": "This is a sales script task.",
                "confidence": 0.9,
                "needs_clarification": False,
                "clarification": "",
            }
        ),
    )

    decision = manager_agent.triage("optimize my appointment setter script")

    assert decision.departments == ["sales"]
    assert decision.confidence == 0.9


def test_triage_can_assign_multiple_departments(monkeypatch):
    monkeypatch.setattr(
        manager_agent,
        "route_prompt",
        lambda *args, **kwargs: _json_response(
            {
                "departments": ["marketing", "automation"],
                "reasoning": "Needs an ad script and a follow-up sequence.",
                "confidence": 0.8,
            }
        ),
    )

    decision = manager_agent.triage("write an ad script and a follow-up sequence")

    assert decision.departments == ["marketing", "automation"]


def test_triage_raises_when_no_department_matches(monkeypatch):
    """The manager must never default to a department."""
    monkeypatch.setattr(
        manager_agent,
        "route_prompt",
        lambda *args, **kwargs: _json_response(
            {
                "departments": [],
                "reasoning": "This request is outside the team's scope.",
                "confidence": 0.1,
            }
        ),
    )

    with pytest.raises(RoutingError) as excinfo:
        manager_agent.triage("what is the weather in Phoenix")

    assert "outside the team's scope" in excinfo.value.message
    assert excinfo.value.code == "routing_error"


def test_triage_rejects_invented_departments(monkeypatch):
    """A hallucinated department name must not be accepted."""
    monkeypatch.setattr(
        manager_agent,
        "route_prompt",
        lambda *args, **kwargs: _json_response(
            {"departments": ["engineering"], "reasoning": "Build a service.", "confidence": 0.9}
        ),
    )

    with pytest.raises(RoutingError) as excinfo:
        manager_agent.triage("build me a microservice")

    assert "engineering" in excinfo.value.details["invalid_departments"]


def test_triage_keeps_valid_departments_and_drops_invalid(monkeypatch):
    monkeypatch.setattr(
        manager_agent,
        "route_prompt",
        lambda *args, **kwargs: _json_response(
            {"departments": ["sales", "engineering"], "reasoning": "Mostly sales.", "confidence": 0.7}
        ),
    )

    decision = manager_agent.triage("write a closer script and deploy it")

    assert decision.departments == ["sales"]


# -------------------------------------------------------------------- rewrite


def test_rewrite_produces_a_concrete_brief(monkeypatch):
    monkeypatch.setattr(
        manager_agent,
        "route_prompt",
        lambda *args, **kwargs: _json_response(
            {
                "objective": "Optimize the supplied appointment setter script.",
                "deliverable": "A revised full-length appointment setting script.",
                "requirements": ["Preserve working sections", "Add objection branches"],
                "constraints": ["No invented pricing"],
                "success_criteria": ["Passes the 50% conversion backtest"],
            }
        ),
    )

    brief = manager_agent.rewrite_for_department("optimize my setter script", "sales")

    assert brief.department == "sales"
    assert "appointment setting script" in brief.deliverable
    assert len(brief.requirements) == 2
    assert "Passes the 50% conversion backtest" in brief.success_criteria
    # The brief must render into a prompt block with all sections present.
    block = brief.as_prompt_block()
    assert "### Objective" in block
    assert "### Success Criteria" in block


def test_rewrite_raises_on_incomplete_brief(monkeypatch):
    monkeypatch.setattr(
        manager_agent,
        "route_prompt",
        lambda *args, **kwargs: _json_response({"objective": "", "deliverable": ""}),
    )

    from backend.errors import PipelineError

    with pytest.raises(PipelineError):
        manager_agent.rewrite_for_department("do something", "sales")


# ------------------------------------------------------------------- finalize


def test_finalize_returns_the_single_department_answer():
    answer = manager_agent.finalize(
        "optimize my setter script",
        [{"department": "sales", "status": "ok", "content": "REVISED SCRIPT BODY", "message": ""}],
    )

    assert answer.status == "ok"
    assert answer.body == "REVISED SCRIPT BODY"
    assert "sales" in answer.message


def test_finalize_reports_error_when_no_department_succeeded():
    """A failed pipeline must produce an error, never a substituted answer."""
    answer = manager_agent.finalize(
        "optimize my setter script",
        [
            {
                "department": "sales",
                "status": "error",
                "content": "",
                "message": "Backtest failed: 4/20 calls converted (20%).",
            }
        ],
    )

    assert answer.status == "error"
    assert "could not produce a verified answer" in answer.message
    assert "Backtest failed" in answer.body


def test_finalize_combines_multiple_departments(monkeypatch):
    monkeypatch.setattr(
        manager_agent,
        "route_prompt",
        lambda *args, **kwargs: _text_response("## Marketing\nAD COPY\n\n## Automation\nNURTURE SEQUENCE"),
    )

    answer = manager_agent.finalize(
        "ad script plus follow-up",
        [
            {"department": "marketing", "status": "ok", "content": "AD COPY", "message": ""},
            {"department": "automation", "status": "ok", "content": "NURTURE SEQUENCE", "message": ""},
        ],
    )

    assert answer.status == "ok"
    assert "AD COPY" in answer.body
    assert "NURTURE SEQUENCE" in answer.body


def test_finalize_ignores_failed_departments_when_others_succeed(monkeypatch):
    monkeypatch.setattr(
        manager_agent,
        "route_prompt",
        lambda *args, **kwargs: _text_response("combined"),
    )

    answer = manager_agent.finalize(
        "ad script plus follow-up",
        [
            {"department": "marketing", "status": "ok", "content": "AD COPY", "message": ""},
            {"department": "automation", "status": "error", "content": "", "message": "failed"},
        ],
    )

    assert answer.status == "ok"
