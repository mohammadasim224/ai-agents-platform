"""A reasoning model can spend its whole output budget thinking.

Reasoning models (for example DeepSeek's) count their hidden reasoning tokens
against `max_tokens`. When the budget is too small the provider ends the stream
with `finish_reason: "length"` before any visible content, which used to surface
as a bare "empty completion" and was retried with the exact same budget, so it
failed identically every time.
"""

from __future__ import annotations

import json

import pytest

from backend.errors import ProviderError
from backend.llm import router

# `conftest` swaps `call_openrouter` for an offline stub in every test. These
# tests fake the HTTP layer instead, so they need the real function.
_REAL_CALL_OPENROUTER = router.call_openrouter


def _reasoning_only_stream():
    """Frames a reasoning model sends when it runs out of budget mid-thought."""

    class FakeResponse:
        status_code = 200

        def iter_lines(self, decode_unicode=True):
            yield 'data: {"id":"r1","choices":[{"delta":{"content":"","reasoning":"Let me think about the sequence..."}}]}'
            yield 'data: {"choices":[{"delta":{"content":"","reasoning":" step one, step two"}}]}'
            yield 'data: {"choices":[{"delta":{},"finish_reason":"length"}]}'
            yield "data: [DONE]"

        def close(self):
            pass

    return FakeResponse()


def _answer_stream(text: str):
    class FakeResponse:
        status_code = 200

        def iter_lines(self, decode_unicode=True):
            yield f"data: {json.dumps({'choices': [{'delta': {'reasoning': 'thinking'}}]})}"
            yield f"data: {json.dumps({'choices': [{'delta': {'content': text}}]})}"
            yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
            yield "data: [DONE]"

        def close(self):
            pass

    return FakeResponse()


@pytest.fixture
def provider(monkeypatch):
    """Record every request's `max_tokens` and serve scripted responses."""
    monkeypatch.setattr(router, "call_openrouter", _REAL_CALL_OPENROUTER)
    monkeypatch.setattr(router, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(router, "LLM_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(router, "LLM_MAX_TOKENS", 4000)
    monkeypatch.setattr(router, "LLM_MAX_TOKENS_CEILING", 16000)
    monkeypatch.setattr(router.time, "sleep", lambda _seconds: None)

    budgets: list[int] = []
    responses: list = []

    def fake_post(*_args, json=None, **_kwargs):
        budgets.append(json["max_tokens"])
        return responses.pop(0)

    monkeypatch.setattr(router.requests, "post", fake_post)
    return budgets, responses


def test_exhausted_reasoning_budget_is_retried_with_a_larger_budget(provider):
    budgets, responses = provider
    responses.extend([_reasoning_only_stream(), _answer_stream("Day 1: Hi Sam, ...")])

    result = router.call_openrouter("reasoning-model", "write a nurture sequence", on_delta=lambda _t: None)

    assert result["content"] == "Day 1: Hi Sam, ..."
    assert budgets == [4000, 8000]


def test_budget_escalation_stops_at_the_ceiling_with_an_accurate_error(provider):
    budgets, responses = provider
    responses.extend([_reasoning_only_stream() for _ in range(3)])

    with pytest.raises(ProviderError) as caught:
        router.call_openrouter("reasoning-model", "write a nurture sequence", on_delta=lambda _t: None)

    assert budgets == [4000, 8000, 16000]
    error = caught.value
    assert "16000" in error.message
    assert "reasoning" in error.message
    assert error.details["finish_reason"] == "length"
    assert "LLM_MAX_TOKENS" in error.user_hint
    # The old hint blamed the API key, which sent people looking in the wrong place.
    assert "OPENROUTER_API_KEY" not in error.user_hint


def test_budget_already_at_the_ceiling_is_not_retried_identically(provider, monkeypatch):
    budgets, responses = provider
    monkeypatch.setattr(router, "LLM_MAX_TOKENS", 16000)
    responses.extend([_reasoning_only_stream() for _ in range(3)])

    with pytest.raises(ProviderError):
        router.call_openrouter("reasoning-model", "hi", on_delta=lambda _t: None)

    assert budgets == [16000]


def test_non_streaming_reasoning_exhaustion_is_escalated_too(provider):
    budgets, responses = provider

    class Buffered:
        status_code = 200

        def __init__(self, content: str, finish_reason: str):
            self._body = {
                "id": "b1",
                "choices": [
                    {
                        "message": {"content": content, "reasoning": "long hidden thinking"},
                        "finish_reason": finish_reason,
                    }
                ],
            }

        def json(self):
            return self._body

        def close(self):
            pass

    responses.extend([Buffered("", "length"), Buffered("Final answer", "stop")])

    result = router.call_openrouter("reasoning-model", "hi")

    assert result["content"] == "Final answer"
    assert budgets == [4000, 8000]


def test_final_error_carries_the_real_cause_hint_instead_of_blaming_the_request(monkeypatch):
    """The user saw "Add more detail about the exact deliverable you need" for a
    model-budget failure, which sent them rewriting prompts that were fine."""
    from backend.agents import manager as manager_agent
    from backend.agents.departments import head as head_agent
    from backend.agents.specialists import runner as specialist_runner
    from backend.orchestrator import run_pipeline

    def reply(payload: dict) -> dict:
        return {"content": json.dumps(payload), "model": "test", "usage": {}, "latency_ms": 1, "attempts": 1}

    def fake_manager(role, prompt, system_prompt="", **kwargs):
        if "TRIAGE" in system_prompt:
            return reply({"departments": ["automation"], "reasoning": "Nurture sequence.", "confidence": 1.0})
        return reply(
            {
                "objective": "Write an SMS nurture sequence for new solar leads.",
                "deliverable": "Five SMS messages with send timing.",
                "requirements": ["Use only verified business facts"],
                "constraints": ["No prohibited claims"],
                "success_criteria": ["Ready to load into the CRM"],
            }
        )

    def fake_head(role, prompt, system_prompt="", **kwargs):
        return reply(
            {
                "summary": "One specialist writes the sequence.",
                "shared_context": "New residential solar leads.",
                "subtasks": [
                    {
                        "id": "subtask-1",
                        "specialist": "lead_nurturing",
                        "instruction": "Write the five-message SMS sequence.",
                        "expected_output": "Five SMS messages with timing.",
                        "depends_on": [],
                    }
                ],
            }
        )

    def exhausted_specialist(*_args, **_kwargs):
        raise ProviderError(
            "The model spent its whole 16000-token output budget on reasoning and returned no answer.",
            stage="provider",
            details={"finish_reason": "length"},
            hint="Raise LLM_MAX_TOKENS in .env.",
        )

    monkeypatch.setattr(manager_agent, "route_prompt", fake_manager)
    monkeypatch.setattr(head_agent, "route_prompt", fake_head)
    monkeypatch.setattr(specialist_runner, "route_prompt", exhausted_specialist)

    body = run_pipeline("Write an SMS nurture sequence for new solar leads").to_dict()

    assert body["status"] == "error"
    assert any(
        step["stage"] == "specialist" and step["agent"] == "lead_nurturing" for step in body["trace"]
    ), "the failure must come from the specialist, as it did in production"
    assert "reasoning" in body["error"]["message"]
    assert body["error"]["hint"] == "Raise LLM_MAX_TOKENS in .env."
