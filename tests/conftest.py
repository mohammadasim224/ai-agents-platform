"""Shared test configuration.

Tests must be fast and deterministic, so the model provider is stubbed for the
whole suite by default. Tests that need specific model behaviour override
`route_prompt` themselves with monkeypatch.

Set `ALLOW_LIVE_PROVIDER=1` to run against the real provider instead.
"""

from __future__ import annotations

import os

import pytest

from backend.errors import ProviderError


@pytest.fixture(autouse=True)
def _block_live_provider(monkeypatch):
    """Prevent tests from making real network calls to the model provider.

    The pipeline is designed to report provider failures honestly, so blocking the
    provider still exercises the real control flow: routing, error typing, trace
    construction, and API response shaping.
    """
    if os.getenv("ALLOW_LIVE_PROVIDER") == "1":
        return

    from backend.llm import router

    def _offline_call(*args, **kwargs):
        raise ProviderError(
            "The model provider is disabled during tests.",
            stage="provider",
            details={"reason": "offline test mode"},
        )

    monkeypatch.setattr(router, "call_openrouter", _offline_call)
    monkeypatch.setattr(router, "route_prompt", _offline_call)
