from __future__ import annotations

import json
import time
from typing import Any

import requests

from backend.config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL
from backend.llm.models import get_model_for


def call_openrouter(model: str, prompt: str, system_prompt: str = "You are a helpful assistant.") -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
    }

    started = time.time()
    response = requests.post(f"{OPENROUTER_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=120)
    latency_ms = round((time.time() - started) * 1000)

    if response.status_code == 429:
        raise RuntimeError("OpenRouter rate limited (429). Please retry later.")

    if response.status_code >= 400:
        raise RuntimeError(f"OpenRouter request failed ({response.status_code}): {response.text[:500]}")

    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"OpenRouter returned no choices: {data}")

    message = choices[0].get("message", {})
    content = message.get("content") or ""
    usage = data.get("usage") or {}

    return {
        "content": content,
        "model": model,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
        "latency_ms": latency_ms,
        "request_id": data.get("id"),
    }


def route_prompt(role: str, prompt: str, system_prompt: str = "You are a helpful assistant.") -> dict[str, Any]:
    model = get_model_for(role)
    return call_openrouter(model, prompt, system_prompt)


if __name__ == "__main__":
    result = route_prompt("manager", "Say hello in one sentence.")
    print(json.dumps(result, indent=2, ensure_ascii=False))
