"""Shared test configuration.

Tests must be fast and deterministic, so the model provider is stubbed for the
whole suite by default. Tests that need specific model behaviour override
`route_prompt` themselves with monkeypatch.

Tests also run against a temporary SQLite database. Without this, the suite
would write conversations and queue jobs into the real `data/` database and
leave stale `running` rows behind when the test process exits mid-job.

Set `ALLOW_LIVE_PROVIDER=1` to run against the real provider instead.
"""

from __future__ import annotations

import os

import pytest

from backend.errors import ProviderError


@pytest.fixture(autouse=True)
def _isolate_database(tmp_path, monkeypatch):
    """Point every database call at a throwaway file for this test."""
    from backend.database import database

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    database.initialize_database()


@pytest.fixture(autouse=True)
def _isolate_knowledge(tmp_path, monkeypatch):
    """Point the knowledge builder at a throwaway folder for this test.

    Without this, a test that builds a knowledge base writes into the real
    `knowledge/business/` directory and overwrites the live business knowledge
    (for example replacing `company.md` with a fixture profile's name).
    """
    from backend.services import knowledge_builder

    monkeypatch.setattr(knowledge_builder, "BUSINESS_DIR", tmp_path / "knowledge" / "business")


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
