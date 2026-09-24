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
import random
import re
import socket
import time
from typing import Any, Callable
from urllib.parse import urlparse

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
from backend.llm.models import MODEL_MAP, get_model_for

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 524}

# Network faults that are worth retrying: DNS hiccups, dropped connections, and
# timeouts are all transient on a laptop that sleeps, switches Wi-Fi, or uses a
# VPN. A bad URL or a TLS failure is not retried because retrying cannot help.
RETRYABLE_NETWORK_ERRORS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)

# Cap the exponential backoff so a long outage does not stall a request forever.
MAX_BACKOFF_SECONDS = 20.0


def _require_api_key() -> None:
    if not OPENROUTER_API_KEY.strip():
        raise ProviderError(
            "OPENROUTER_API_KEY is not configured.",
            stage="provider",
            hint="Add OPENROUTER_API_KEY to the .env file at the project root and restart the backend.",
        )


def _provider_host() -> str:
    return urlparse(OPENROUTER_BASE_URL).hostname or "openrouter.ai"


def _is_dns_failure(exc: BaseException) -> bool:
    """Detect a name-resolution failure anywhere in the exception chain."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, socket.gaierror):
            return True
        if "NameResolutionError" in type(current).__name__:
            return True
        if "nodename nor servname" in str(current) or "Name or service not known" in str(current):
            return True
        current = current.__cause__ or current.__context__
    return False


def _backoff_seconds(attempt: int) -> float:
    """Exponential backoff with jitter, capped to keep requests responsive."""
    base = max(0.1, LLM_RETRY_BACKOFF_SECONDS) * (2 ** (attempt - 1))
    return min(MAX_BACKOFF_SECONDS, base) * (0.75 + random.random() * 0.5)


def _network_error(exc: requests.RequestException, model: str, attempt: int) -> ProviderError:
    """Turn a transport failure into an honest, actionable ProviderError."""
    if _is_dns_failure(exc):
        return ProviderError(
            f"Could not resolve the model provider host '{_provider_host()}'.",
            stage="provider",
            details={"model": model, "attempt": attempt, "host": _provider_host()},
            hint=(
                "The machine could not look up the provider's address. Check your "
                "internet connection, VPN, or DNS settings, then retry."
            ),
        )
    if isinstance(exc, requests.exceptions.Timeout):
        return ProviderError(
            f"The model provider did not respond within {LLM_TIMEOUT_SECONDS}s.",
            stage="provider",
            details={"model": model, "attempt": attempt},
            hint="The provider may be slow or overloaded. Retry in a moment.",
        )
    return ProviderError(
        f"Network error contacting the model provider: {exc}",
        stage="provider",
        details={"model": model, "attempt": attempt},
        hint="Check your internet connection and retry.",
    )


def check_provider_health(timeout: float = 5.0) -> dict[str, Any]:
    """Lightweight reachability probe used by the health endpoint.

    Never raises: it reports whether the provider host resolves and responds so
    the UI can warn the user before they send a request that would fail.
    """
    host = _provider_host()
    result: dict[str, Any] = {
        "host": host,
        "base_url": OPENROUTER_BASE_URL,
        "api_key_configured": bool(OPENROUTER_API_KEY.strip()),
        "dns_ok": False,
        "reachable": False,
    }

    try:
        socket.getaddrinfo(host, 443)
        result["dns_ok"] = True
    except socket.gaierror as exc:
        result["error"] = f"DNS resolution failed: {exc}"
        return result

    try:
        response = requests.get(f"{OPENROUTER_BASE_URL}/models", timeout=timeout)
        result["reachable"] = response.status_code < 500
        result["status_code"] = response.status_code
    except requests.RequestException as exc:
        result["error"] = str(exc)

    return result


# Editor and IDE clients poll `/v1/models` on startup, so the provider list is
# cached briefly. Without this every poll would hit the provider.
MODELS_CACHE_TTL_SECONDS = 300.0
_models_cache: dict[str, Any] = {"at": 0.0, "models": None}


def configured_models() -> list[str]:
    """Model ids configured for each role, de-duplicated in a stable order.

    This is the honest fallback when the provider cannot be listed: it reports
    what this platform is actually configured to run, not a fabricated catalog.
    """
    ordered: list[str] = []
    for role in MODEL_MAP:
        model = get_model_for(role)
        if model and model not in ordered:
            ordered.append(model)
    return ordered


def list_models(*, timeout: float = 10.0, use_cache: bool = True) -> list[dict[str, Any]]:
    """Return the provider's available models in a normalized shape.

    Used by the OpenAI-compatible `/v1/models` route. Raises `ProviderError` when
    the provider cannot be listed; callers that can tolerate that should fall
    back to `configured_models()` rather than returning an empty catalog.
    """
    cached = _models_cache.get("models")
    if use_cache and isinstance(cached, list):
        if time.time() - float(_models_cache.get("at") or 0.0) < MODELS_CACHE_TTL_SECONDS:
            return cached

    _require_api_key()

    try:
        response = requests.get(
            f"{OPENROUTER_BASE_URL}/models",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            timeout=timeout,
        )
    except RETRYABLE_NETWORK_ERRORS as exc:
        raise _network_error(exc, "models", 1) from exc
    except requests.RequestException as exc:
        raise ProviderError(
            f"Could not reach the model provider: {exc}",
            stage="provider",
            hint="Verify OPENROUTER_BASE_URL in .env is correct and reachable.",
        ) from exc

    if response.status_code in (401, 403):
        raise ProviderError(
            "The model provider rejected the API key.",
            stage="provider",
            details={"status": response.status_code},
            hint="Verify OPENROUTER_API_KEY in .env is valid and has available credit.",
        )
    if response.status_code >= 400:
        raise ProviderError(
            f"Could not list models (status {response.status_code}).",
            stage="provider",
            details={"body": response.text[:400]},
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderError(
            "The model provider returned a non-JSON model list.",
            stage="provider",
            details={"body": response.text[:400]},
        ) from exc

    raw = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(raw, list):
        raise ProviderError(
            "The model provider returned an unexpected model list.",
            stage="provider",
            details={"body": response.text[:400]},
        )

    normalized: list[dict[str, Any]] = []
    for entry in raw:
        if isinstance(entry, str):
            entry = {"id": entry}
        if not isinstance(entry, dict):
            continue
        model_id = str(entry.get("id") or "").strip()
        if not model_id:
            continue
        model: dict[str, Any] = {
            "id": model_id,
            "name": entry.get("name") or model_id,
            "context_length": entry.get("context_length"),
            # Provider-prefixed ids (`deepseek/...`) expose the vendor for free.
            "owned_by": model_id.split("/")[0] or "openrouter",
        }
        if entry.get("pricing"):
            model["pricing"] = entry["pricing"]
        normalized.append(model)

    _models_cache["models"] = normalized
    _models_cache["at"] = time.time()
    return normalized


def _chat_completion(
    model: str,
    prompt: str,
    system_prompt: str = "You are a helpful assistant.",
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    on_delta: Callable[[str], None] | None = None,
    stream: bool = False,
) -> dict[str, Any]:
    """Call the chat completions endpoint with retries and strict error handling.

    When `stream` is set the response is read as SSE, and `on_delta` (if given)
    receives the text generated so far; otherwise it is a normal blocking
    request. Streaming is a transport detail, not a second implementation: both
    paths share the same retry loop, status handling, and error typing, and
    return the same shape, so callers never branch on which was used.
    """
    _require_api_key()
    streaming = stream

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
    if streaming:
        payload["stream"] = True

    last_error: Exception | None = None
    started = time.time()
    max_attempts = max(1, LLM_MAX_ATTEMPTS)

    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=LLM_TIMEOUT_SECONDS,
                stream=streaming,
            )
        except RETRYABLE_NETWORK_ERRORS as exc:
            last_error = _network_error(exc, model, attempt)
            if attempt < max_attempts:
                time.sleep(_backoff_seconds(attempt))
                continue
            raise last_error from exc
        except requests.RequestException as exc:
            # Non-retryable transport faults (bad URL, TLS failure, etc.).
            raise ProviderError(
                f"Could not reach the model provider: {exc}",
                stage="provider",
                details={"model": model, "attempt": attempt},
                hint="Verify OPENROUTER_BASE_URL in .env is correct and reachable.",
            ) from exc

        # A streaming response holds an open connection, so every early exit
        # releases it before retrying or raising. Closing a buffered response is
        # harmless, which keeps this branch-free.
        if response.status_code in RETRYABLE_STATUS and attempt < max_attempts:
            response.close()
            last_error = ProviderError(
                f"Provider returned retryable status {response.status_code}.",
                stage="provider",
                details={"model": model, "attempt": attempt},
            )
            time.sleep(_backoff_seconds(attempt))
            continue

        if response.status_code in (401, 403):
            response.close()
            raise ProviderError(
                "The model provider rejected the API key.",
                stage="provider",
                details={"model": model, "status": response.status_code},
                hint="Verify OPENROUTER_API_KEY in .env is valid and has available credit.",
            )

        if response.status_code == 429:
            response.close()
            raise ProviderError(
                "The model provider rate limited this request.",
                stage="provider",
                details={"model": model, "status": 429},
                hint="Wait a moment and retry, or raise your provider rate limit.",
            )

        if response.status_code >= 400:
            body = response.text[:400]
            response.close()
            raise ProviderError(
                f"Model provider request failed with status {response.status_code}.",
                stage="provider",
                details={"model": model, "body": body},
            )

        if streaming:
            content, request_id, usage, finish_reason = _consume_stream(response, on_delta)
            response.close()
        else:
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

            content = ((choices[0].get("message") or {}).get("content") or "").strip()
            request_id = data.get("id")
            usage = data.get("usage") or {}
            finish_reason = choices[0].get("finish_reason")

        if not content:
            if attempt < max_attempts:
                time.sleep(_backoff_seconds(attempt))
                continue
            raise ProviderError(
                "The model provider returned an empty completion.",
                stage="provider",
                details={"model": model, "finish_reason": finish_reason},
            )

        return {
            "content": content,
            "model": model,
            "usage": {
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
            },
            "latency_ms": round((time.time() - started) * 1000),
            "request_id": request_id,
            "attempts": attempt,
        }

    raise last_error or ProviderError("The model provider request failed.", stage="provider")


def call_openrouter(
    model: str,
    prompt: str,
    system_prompt: str = "You are a helpful assistant.",
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    on_delta: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Call the chat completions endpoint. See `_chat_completion` for behaviour.

    Streams only when `on_delta` is supplied.
    """
    return _chat_completion(
        model,
        prompt,
        system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        on_delta=on_delta,
        stream=on_delta is not None,
    )


def call_openrouter_stream(
    model: str,
    prompt: str,
    system_prompt: str = "You are a helpful assistant.",
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    on_delta: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Stream a chat completion. Thin alias for the shared implementation.

    Both names delegate to the same implementation, so a caller can never reach a
    second, divergent code path by choosing one over the other.
    """
    return _chat_completion(
        model,
        prompt,
        system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        on_delta=on_delta,
        stream=True,
    )


def route_prompt(
    role: str,
    prompt: str,
    system_prompt: str = "You are a helpful assistant.",
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    on_delta: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Route a prompt to the model configured for the given role.

    When `on_delta` is given the response is streamed and the callback receives
    the text generated so far; otherwise it is a normal blocking request.
    """
    return call_openrouter(
        get_model_for(role),
        prompt,
        system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        on_delta=on_delta,
    )

# How often a streaming call reports the text generated so far. The provider
# emits many small deltas per second; forwarding every one would flood the
# progress row with writes. A short interval keeps the preview visibly live
# while bounding the write rate.
STREAM_REPORT_INTERVAL_SECONDS = 0.4


def _consume_stream(
    response: requests.Response,
    on_delta: Callable[[str], None] | None,
) -> tuple[str, str | None, dict[str, Any], str | None]:
    """Read an SSE completion stream, returning the assembled result.

    Returns `(content, request_id, usage, finish_reason)`. Malformed keep-alive
    lines are skipped rather than failing the call, because providers interleave
    comments and blank lines with the data frames. A transport fault mid-stream
    is raised as a `ProviderError` so the caller can retry the whole call.
    """
    parts: list[str] = []
    request_id: str | None = None
    usage: dict[str, Any] = {}
    finish_reason: str | None = None
    last_report = 0.0

    try:
        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            line = raw_line.strip()
            if not line.startswith("data:"):
                continue
            data = line[len("data:") :].strip()
            if data == "[DONE]":
                break
            try:
                frame = json.loads(data)
            except ValueError:
                continue
            if not isinstance(frame, dict):
                continue
            if frame.get("id"):
                request_id = frame["id"]
            if isinstance(frame.get("usage"), dict):
                usage = frame["usage"]
            choices = frame.get("choices") or []
            if not choices:
                continue
            choice = choices[0] or {}
            if choice.get("finish_reason"):
                finish_reason = choice["finish_reason"]
            delta = choice.get("delta") or {}
            piece = delta.get("content")
            if not piece:
                continue
            parts.append(piece)
            if on_delta is not None:
                now = time.monotonic()
                if now - last_report >= STREAM_REPORT_INTERVAL_SECONDS:
                    last_report = now
                    try:
                        on_delta("".join(parts))
                    except Exception:  # noqa: BLE001 - a broken sink must not fail the call
                        pass
    except RETRYABLE_NETWORK_ERRORS as exc:
        raise _network_error(exc, "stream", 1) from exc

    content = "".join(parts).strip()
    if on_delta is not None and content:
        try:
            on_delta(content)
        except Exception:  # noqa: BLE001 - a broken sink must not fail the call
            pass
    return content, request_id, usage, finish_reason


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
