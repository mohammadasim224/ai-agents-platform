"""Compatibility shim for the ad copywriting specialist.

The ad copywriting specialist is now defined in `backend/agents/registry.py` and
executed by `backend/agents/specialists/runner.py`, which composes its system
prompt from `prompts/marketing/ad_copywriting.md` and its assigned knowledge
files. This module remains so existing callers keep working, but it no longer
holds its own prompt or model logic.
"""

from __future__ import annotations

from backend.agents.registry import get_specialist
from backend.agents.specialists.runner import run


def write_ad_copy(prompt: str, *, brief_block: str = "") -> str:
    """Run the ad copywriting specialist and return its deliverable."""
    specialist = get_specialist("ad_copywriting")
    deliverable = run(specialist, prompt, brief_block=brief_block)
    return deliverable.content
