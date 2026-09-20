"""LLM access layer.

Every model call in the platform goes through here. The layer is deliberately
strict:

- Transient failures are retried with backoff.
- A permanent failure raises `ProviderError` instead of returning an empty
  string, so the pipeline can report an honest error to the user rather than
  passing along a degraded answer.
- JSON responses are parsed defensively and never silently replaced with a
  guessed default.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import requests

from backend.config import (
    LLM_MAX_ATTEMPTS,
    LLM_MAX_TOKENS,
    LLM_RETRY_BACKOFF_SECONDS,
    LLM_TEMPERATURE,
    LLM_TIMEOUT_SECONDS,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
)
from backend.errors import ProviderError
from backend.llm.models import get_model_for

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 524}


def _require_api_key() -> None:
    if not OPENROUTER_API_KEY.strip():
        raise ProviderError(
            "OPENROUTER_API_KEY is not configured.",
            stage="provider",
            hint="Add OPENROUTER_API_KEY to the .env file at the project root and restart the backend.",
        )


def call_openrouter(
    model: str,
    prompt: str,
    system_prompt: str = "You are a helpful assistant.",
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """Call the chat completions endpoint with retries and strict error handling."""
    _require_api_key()

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
        "temperature": LLM_TEMPERATURE if temperature is None else temperature,
        "max_tokens": LLM_MAX_TOKENS if max_tokens is None else max_tokens,
    }

    last_error: Exception | None = None
    started = time.time()

    for attempt in range(1, max(1, LLM_MAX_ATTEMPTS) + 1):
        try:
            response = requests.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=LLM_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            last_error = ProviderError(
                f"Network error contacting the model provider: {exc}",
                stage="provider",
                details={"model": model, "attempt": attempt},
            )
            if attempt < LLM_MAX_ATTEMPTS:
                time.sleep(LLM_RETRY_BACKOFF_SECONDS * attempt)
                continue
            raise last_error from exc

        if response.status_code in RETRYABLE_STATUS and attempt < LLM_MAX_ATTEMPTS:
            last_error = ProviderError(
                f"Provider returned retryable status {response.status_code}.",
                stage="provider",
                details={"model": model, "attempt": attempt},
            )
            time.sleep(LLM_RETRY_BACKOFF_SECONDS * attempt)
            continue

        if response.status_code == 401 or response.status_code == 403:
            raise ProviderError(
                "The model provider rejected the API key.",
                stage="provider",
                details={"model": model, "status": response.status_code},
                hint="Verify OPENROUTER_API_KEY in .env is valid and has available credit.",
            )

        if response.status_code == 429:
            raise ProviderError(
                "The model provider rate limited this request.",
                stage="provider",
                details={"model": model, "status": 429},
                hint="Wait a moment and retry, or raise your provider rate limit.",
            )

        if response.status_code >= 400:
            raise ProviderError(
                f"Model provider request failed with status {response.status_code}.",
                stage="provider",
                details={"model": model, "body": response.text[:400]},
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError(
                "The model provider returned a non-JSON response.",
                stage="provider",
                details={"model": model, "body": response.text[:400]},
            ) from exc

        choices = data.get("choices") or []
        if not choices:
            raise ProviderError(
                "The model provider returned no completion choices.",
                stage="provider",
                details={"model": model, "response_id": data.get("id")},
            )

        message = choices[0].get("message", {}) or {}
        content = (message.get("content") or "").strip()
        if not content:
            if attempt < LLM_MAX_ATTEMPTS:
                time.sleep(LLM_RETRY_BACKOFF_SECONDS * attempt)
                continue
            raise ProviderError(
                "The model provider returned an empty completion.",
                stage="provider",
                details={"model": model, "finish_reason": choices[0].get("finish_reason")},
            )

        usage = data.get("usage") or {}
        return {
            "content": content,
            "model": model,
            "usage": {
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
            },
            "latency_ms": round((time.time() - started) * 1000),
            "request_id": data.get("id"),
            "attempts": attempt,
        }

    raise last_error or ProviderError("The model provider request failed.", stage="provider")


def route_prompt(
    role: str,
    prompt: str,
    system_prompt: str = "You are a helpful assistant.",
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """Route a prompt to the model configured for the given role."""
    model = get_model_for(role)
    return call_openrouter(
        model,
        prompt,
        system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )


_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(content: str) -> dict[str, Any]:
    """Parse a JSON object out of a model response.

    Models occasionally wrap JSON in prose or code fences. This extracts the
    first valid JSON object it can find and raises `ProviderError` when the
    response cannot be parsed, rather than inventing a fallback decision.
    """
    text = (content or "").strip()
    if not text:
        raise ProviderError("The model returned an empty response where JSON was expected.", stage="parsing")

    candidates: list[str] = [text]
    candidates.extend(match.strip() for match in _JSON_FENCE.findall(text))

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            return {"items": parsed}

    raise ProviderError(
        "The model did not return valid JSON.",
        stage="parsing",
        details={"preview": text[:400]},
    )


if __name__ == "__main__":
    result = route_prompt("manager", "Say hello in one sentence.")
    print(json.dumps(result, indent=2, ensure_ascii=False))
