from __future__ import annotations

from backend.llm.router import route_prompt


def write_setter_script(prompt: str) -> str:
    system_prompt = """
You are a sales appointment setter.
Use only verified business knowledge.
Do not invent deals, pricing, financing, or guarantees.
Produce a qualified opening, questions, transitions, and booking flow.
"""
    result = route_prompt("sales", prompt, system_prompt=system_prompt)
    return result.get("content", "")
