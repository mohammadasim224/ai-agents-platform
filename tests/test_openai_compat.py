"""Tests for the OpenAI-compatible `/v1` surface.

These routes exist because editor/IDE clients and OpenAI SDKs probe `/v1/models`
on startup; without them they received a bare 404 from this server. The tests
pin the wire format, the honest failure behaviour, and the fact that requests
are delegated to the real pipeline rather than answered with a stub.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.errors import ProviderError
from backend.llm import router
from backend.main import app

client = TestClient(app)


# ----------------------------------------------------------------------- models


def test_models_route_exists_so_probing_clients_no_longer_get_404(monkeypatch):
    monkeypatch.setattr(
        router,
        "list_models",
        lambda **kwargs: [
            {
                "id": "deepseek/deepseek-v4-flash-0731",
                "name": "DeepSeek V4 Flash",
                "context_length": 128000,
                "owned_by": "deepseek",
            }
        ],
    )

    response = client.get("/v1/models")

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"
    assert body["x_voltaik"]["source"] == "provider"

    model = body["data"][0]
    assert model["id"] == "deepseek/deepseek-v4-flash-0731"
    assert model["object"] == "model"
    assert model["owned_by"] == "deepseek"
    assert model["context_length"] == 128000


def test_models_falls_back_to_configured_models_when_provider_is_down(monkeypatch):
    """A provider outage must not stop an editor from starting up."""

    def _offline(**kwargs):
        raise ProviderError("The model provider is unreachable.", stage="provider")

    monkeypatch.setattr(router, "list_models", _offline)

    response = client.get("/v1/models")

    assert response.status_code == 200
    body = response.json()
    assert body["x_voltaik"]["source"] == "configured"
    assert body["x_voltaik"]["reason"]
    # The configured model is real config, not a fabricated catalog entry.
    assert any(m["id"] == router.get_model_for("manager") for m in body["data"])
    assert all(m["object"] == "model" for m in body["data"])


def test_list_models_normalizes_provider_strings_and_bad_entries(monkeypatch):
    """Provider payloads vary; normalization must never crash the endpoint."""
    calls: list[tuple[str, str]] = []

    class _Response:
        status_code = 200

        @staticmethod
        def json():
            return {
                "data": [
                    "plain/string-model",
                    {"id": "full/entry", "name": "Full Entry", "pricing": {"prompt": "0"}},
                    {"no_id": True},
                    "  ",
                ]
            }

    def _get(url, **kwargs):
        calls.append(("GET", url))
        return _Response()

    monkeypatch.setattr(router, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(router.requests, "get", _get)
    monkeypatch.setattr(router, "_models_cache", {"at": 0.0, "models": None})

    models = router.list_models(use_cache=False)

    assert [m["id"] for m in models] == ["plain/string-model", "full/entry"]
    assert models[0]["owned_by"] == "plain"
    assert models[1]["pricing"] == {"prompt": "0"}


# -------------------------------------------------------------- chat completions


def test_chat_completions_returns_openai_shape(monkeypatch):
    captured: dict[str, str] = {}

    def _fake_pipeline(prompt, *, project_id="demo-project", **kwargs):
        captured["prompt"] = prompt
        captured["project_id"] = project_id

        class _Result:
            @staticmethod
            def to_dict():
                return {
                    "status": "ok",
                    "message": "Ad written.",
                    "output": "FINAL AD COPY",
                    "departments": ["marketing"],
                    "knowledge_used": 3,
                    "trace": [],
                    "artifacts": [],
                    "backtests": [],
                    "compliance": {},
                    "error": None,
                }

        return _Result()

    monkeypatch.setattr("backend.api.openai_compat.run_pipeline", _fake_pipeline)

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "deepseek/deepseek-v4-flash-0731",
            "project_id": "acme",
            "messages": [
                {"role": "system", "content": "Be concise."},
                {"role": "user", "content": "Write me an ad."},
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == "FINAL AD COPY"
    assert body["choices"][0]["finish_reason"] == "stop"
    assert set(body["usage"]) == {"prompt_tokens", "completion_tokens", "total_tokens"}

    # The system turn and user turn both reached the pipeline, and the project
    # was forwarded rather than hard-coded.
    assert "Be concise." in captured["prompt"]
    assert "Write me an ad." in captured["prompt"]
    assert captured["project_id"] == "acme"
    assert body["x_voltaik"]["departments"] == ["marketing"]


def test_chat_completions_reports_pipeline_failure_as_an_error(monkeypatch):
    """A failed pipeline must never look like a successful empty completion."""

    def _failed_pipeline(prompt, *, project_id="demo-project", **kwargs):
        class _Result:
            @staticmethod
            def to_dict():
                return {
                    "status": "error",
                    "message": "Routing failed.",
                    "output": "",
                    "error": {
                        "code": "routing_error",
                        "message": "No department was assigned.",
                        "hint": "Restate the request.",
                    },
                }

        return _Result()

    monkeypatch.setattr("backend.api.openai_compat.run_pipeline", _failed_pipeline)

    response = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "do something vague"}]},
    )

    assert response.status_code == 502
    error = response.json()["error"]
    assert error["code"] == "routing_error"
    assert error["message"]
    assert error["hint"]


@pytest.mark.parametrize(
    "payload,param",
    [
        ({}, "messages"),
        ({"messages": []}, "messages"),
        ({"messages": [{"role": "assistant", "content": "hi"}]}, "messages"),
        ({"messages": [{"role": "user", "content": "   "}]}, "messages"),
        (
            {"messages": [{"role": "user", "content": "hi"}], "tools": [{"type": "function"}]},
            "tools",
        ),
        (
            {"messages": [{"role": "user", "content": "hi"}], "stream": True},
            "stream",
        ),
    ],
)
def test_chat_completions_rejects_unsupported_requests_honestly(payload, param):
    response = client.post("/v1/chat/completions", json=payload)

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["param"] == param
    assert error["message"]


def test_chat_completions_surfaces_a_provider_error_as_502(monkeypatch):
    def _offline(*args, **kwargs):
        raise ProviderError("The provider is down.", stage="provider", hint="Retry later.")

    monkeypatch.setattr("backend.api.openai_compat.run_pipeline", _offline)

    response = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "write an ad"}]},
    )

    assert response.status_code == 502
    error = response.json()["error"]
    assert error["code"] == "provider_error"
    assert error["hint"] == "Retry later."
