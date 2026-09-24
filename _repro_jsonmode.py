"""Test whether response_format=json_object forces valid JSON from the model."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL
from backend.llm.models import get_model_for
from backend.prompts.loader import compose_system_prompt
import requests

model = get_model_for("manager")
sysp = compose_system_prompt(
    "manager/manager", knowledge_categories=("business",), output="json",
    extra_rules="You are performing the REWRITE step only, for sales. Return JSON.",
)
prompt = "## User Request\nWrite a closing script for solar."

headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}

for use_rf in (False, True):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": sysp},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 4000,
    }
    if use_rf:
        payload["response_format"] = {"type": "json_object"}
    r = requests.post(f"{OPENROUTER_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=120)
    data = r.json()
    content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    fr = (data.get("choices") or [{}])[0].get("finish_reason")
    ok = False
    try:
        json.loads(content.strip())
        ok = True
    except Exception:
        pass
    print(f"response_format={use_rf} status={r.status_code} finish={fr} len={len(content)} json_ok={ok}")
    print("   head:", repr(content[:150]))
