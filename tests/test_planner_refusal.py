"""Tests for how the department planner reports a refusal to plan.

A department head sometimes declines to plan on purpose: when the brief cannot
be grounded (for example it references a script that was never attached), the
model answers with ``{"status": "error", "message": ...}`` instead of a plan.
That message explains the real problem, so the planner must carry it through as
the failure message and hint rather than flattening it into a generic
"did not produce any subtasks".
"""

from __future__ import annotations

import pytest

from backend.agents.departments import head as head_module
from backend.agents.registry import get_department
from backend.errors import PlanningError


def _stub_planner(monkeypatch, content: str) -> None:
    monkeypatch.setattr(
        head_module,
        "route_prompt",
        lambda *args, **kwargs: {"content": content, "model": "stub"},
    )


def test_planner_refusal_surfaces_the_model_reason(monkeypatch):
    reason = "The brief references an attached script, but no script was provided."
    _stub_planner(monkeypatch, f'{{"status": "error", "message": "{reason}"}}')

    with pytest.raises(PlanningError) as caught:
        head_module.plan(get_department("sales"), "Optimize the attached closer script.")

    exc = caught.value
    # The headline is the generic planning failure...
    assert "could not plan this request" in exc.message.lower()
    # ...but the model's own explanation is preserved instead of discarded.
    assert exc.user_hint == reason
    assert exc.details.get("refused") is True


def test_planner_empty_plan_still_reports_missing_subtasks(monkeypatch):
    # No explicit refusal, just an unparseable/empty plan: keep the plain error.
    _stub_planner(monkeypatch, '{"summary": "no subtasks here", "subtasks": []}')

    with pytest.raises(PlanningError) as caught:
        head_module.plan(get_department("sales"), "Write a nurture sequence.")

    exc = caught.value
    assert "did not produce any subtasks" in exc.message.lower()
    assert exc.details.get("refused") is None
    assert "raw_output" in exc.details