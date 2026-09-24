from __future__ import annotations

from fastapi import APIRouter

from backend.config import (
    BACKTEST_MIN_CALLS,
    BACKTEST_TARGET_CONVERSION,
)
from backend.evaluations.metrics import objective_for, run_backtest

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@router.get("/quality-gates")
async def quality_gates():
    """Describe the measured quality bars the pipeline enforces."""
    return {
        "sales_scripts": {
            "minimum_calls": BACKTEST_MIN_CALLS,
            "target_conversion_rate": BACKTEST_TARGET_CONVERSION,
            "appointment_setting_objective": objective_for("appointment_setting"),
            "closing_objective": objective_for("closing"),
            "note": (
                "A sales script is rejected unless it reaches the target conversion rate "
                "over at least the minimum number of simulated calls. The rate is measured "
                "by an independent scoring agent."
            ),
        }
    }


@router.post("/backtest")
def backtest_script(payload: dict):
    """Run a measured backtest against a supplied script.

    This returns real measurements. It never returns a score that was not
    computed, because a fabricated score would make the quality gate meaningless.

    Declared `def` so FastAPI runs the blocking backtest (dozens of simulated
    model calls) in its threadpool instead of on the event loop.
    """
    script = str(payload.get("script") or "").strip()
    if not script:
        return {
            "status": "error",
            "error": {
                "code": "empty_script",
                "title": "No script was provided.",
                "message": "A backtest requires the script text to evaluate.",
                "hint": "Send `script` with the script content.",
                "stage": "request",
                "details": {},
            },
        }

    specialist_name = str(payload.get("specialist") or "appointment_setting").strip()
    if specialist_name not in {"appointment_setting", "closing"}:
        specialist_name = "appointment_setting"

    result = run_backtest(
        specialist_name,
        script,
        call_context=str(payload.get("call_context") or ""),
    )
    return {"status": "ok", **result.to_dict()}
