"""Reproduce the 'did not return valid JSON' failure in the sales path."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.agents.registry import get_department
from backend.agents.departments import head
from backend.agents import manager as mgr
from backend.llm.router import route_prompt, extract_json
from backend.prompts.loader import compose_system_prompt

REQUEST = "Write a closing script for solar."

dept = get_department("sales")

print("=== raw rewrite call ===")
sysp = compose_system_prompt(
    "manager/manager", knowledge_categories=("business",), output="json",
    extra_rules="Rewrite for sales. Return JSON.",
)
r = route_prompt("manager", f"## User Request\n{REQUEST}", system_prompt=sysp, temperature=0.2)
print("finish/latency:", r.get("latency_ms"), "len:", len(r["content"]))
print("TAIL:", repr(r["content"][-200:]))
try:
    extract_json(r["content"])
    print("rewrite JSON: OK")
except Exception as e:
    print("rewrite JSON: FAIL", e)

print("=== raw plan call ===")
sysp2 = compose_system_prompt(
    dept.prompt, knowledge_categories=dept.knowledge_categories, output="json",
    extra_rules="PLAN step. Return JSON.",
)
r2 = route_prompt(dept.name, "## Brief\nWrite a closing script.", system_prompt=sysp2, temperature=0.2)
print("latency:", r2.get("latency_ms"), "len:", len(r2["content"]))
print("TAIL:", repr(r2["content"][-200:]))
try:
    extract_json(r2["content"])
    print("plan JSON: OK")
except Exception as e:
    print("plan JSON: FAIL", e)

print("=== full rewrite+plan loop ===")
fails = 0
for i in range(5):
    try:
        b = mgr.rewrite_for_department(REQUEST, "sales")
        p = head.plan(dept, b.as_prompt_block())
        print(f"{i}: OK -> {p.summary[:70]}")
    except Exception as e:
        fails += 1
        print(f"{i}: FAIL {type(e).__name__}: {e}")
        print("   details:", str(getattr(e, "details", {}))[:400])
print("FAILS:", fails)
