from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@router.post("")
async def create_evaluation(payload: dict):
    return {
        "id": "eval-1",
        "evaluator": payload.get("evaluator", "quality-check"),
        "score": 0.92,
        "feedback": "Strong compliance and clear marketing positioning.",
    }


@router.get("/{evaluation_id}")
async def get_evaluation(evaluation_id: str):
    return {"id": evaluation_id, "score": 0.92, "feedback": "Strong output."}
