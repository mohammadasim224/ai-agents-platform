from __future__ import annotations

from fastapi import APIRouter

from backend.llm.router import check_provider_health

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Liveness probe. Always cheap and never touches the network."""
    return {"status": "ok"}


@router.get("/health/provider")
async def provider_health_check():
    """Readiness probe for the model provider.

    Reports whether the provider host resolves and responds, so the UI can warn
    the user before they send a request that would fail. This endpoint never
    raises: an unreachable provider is reported as data, not as an error.
    """
    provider = check_provider_health()
    healthy = bool(provider.get("dns_ok") and provider.get("reachable"))
    return {"status": "ok" if healthy else "degraded", "provider": provider}
