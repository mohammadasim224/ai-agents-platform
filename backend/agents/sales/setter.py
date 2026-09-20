"""Compatibility shim for the appointment setting specialist.

The appointment setting specialist is now defined in
`backend/agents/registry.py` and executed by
`backend/agents/specialists/runner.py`, which composes its system prompt from
`prompts/sales/appointment_setting.md` and its assigned knowledge files.

Sales scripts also pass through a measured backtest quality gate before they are
accepted, so this shim intentionally does not bypass that gate. Use the
orchestrator for a complete, verified result.
"""

from __future__ import annotations

from backend.agents.registry import get_specialist
from backend.agents.specialists.runner import run


def write_setter_script(prompt: str, *, brief_block: str = "") -> str:
    """Run the appointment setting specialist and return its deliverable."""
    specialist = get_specialist("appointment_setting")
    deliverable = run(specialist, prompt, brief_block=brief_block)
    return deliverable.content
