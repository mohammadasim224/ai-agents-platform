"""Outcome scoring for simulated roleplay calls.

Scoring is intentionally separate from simulation so the script cannot grade
itself. A call counts as converted only when the transcript shows the lead
explicitly agreeing to a concrete next step.
"""

from __future__ import annotations

from typing import Any

from backend.errors import ProviderError
from backend.llm.router import extract_json, route_prompt
from backend.prompts.loader import compose_system_prompt

APPOINTMENT_SETTING_METRIC = "appointment_booked"
CLOSING_METRIC = "deal_closed"


def _render_transcript(transcript: dict[str, Any]) -> str:
    lines = [f"Persona: {transcript.get('persona', 'unknown')}"]
    for turn in transcript.get("turns", []):
        speaker = str(turn.get("speaker", "")).strip().lower()
        label = "SETTER" if speaker == "setter" else "LEAD"
        lines.append(f"{label}: {turn.get('text', '')}")
    stance = str(transcript.get("lead_final_stance", "")).strip()
    if stance:
        lines.append(f"LEAD FINAL STANCE: {stance}")
    return "\n".join(lines)


def score_batch(
    transcripts: list[dict[str, Any]],
    *,
    objective: str,
) -> dict[str, Any]:
    """Score a batch of transcripts against a single conversion objective.

    `objective` describes what counts as success, for example
    "the lead agreed to a specific appointment date and time".
    """
    if not transcripts:
        return {"results": [], "conversions": 0, "total": 0, "conversion_rate": 0.0}

    system_prompt = compose_system_prompt(
        "evaluation/scoring",
        knowledge_categories=("sales",),
        output="json",
        extra_rules=(
            "You are scoring simulated sales calls.\n\n"
            "## Conversion Definition\n"
            f"{objective}\n\n"
            "## Rules\n"
            "- Judge ONLY from what the transcript shows. Do not infer goodwill.\n"
            "- A lead who is merely polite, interested, or curious has NOT converted.\n"
            "- A lead who says 'maybe', 'later', or 'send me info' has NOT converted.\n"
            "- A lead who agrees to a specific next step (a time, a date, a confirmed\n"
            "  handoff to a closer, or a clear yes to the offer) HAS converted.\n"
            "- Be strict. Over-crediting conversions makes the quality gate meaningless.\n"
            "- Do not reward invented facts, guarantees, or banned claims.\n\n"
            "## Required JSON\n"
            "{\n"
            '  "results": [\n'
            "    {\n"
            '      "persona": "<persona key>",\n'
            '      "converted": <true|false>,\n'
            '      "confidence": <number between 0 and 1>,\n'
            '      "reason": "<what in the transcript decided this>",\n'
            '      "failure_point": "<where the script lost the lead, or empty string>",\n'
            '      "script_gap": "<missing or weak part of the script, or empty string>"\n'
            "    }\n"
            "  ]\n"
            "}"
        ),
    )

    rendered = "\n\n---\n\n".join(_render_transcript(transcript) for transcript in transcripts)
    user_prompt = f"## Transcripts To Score\n\n{rendered}"

    result = route_prompt("evaluation", user_prompt, system_prompt=system_prompt, temperature=0.1)
    payload = extract_json(result["content"])

    raw_results = payload.get("results")
    if not isinstance(raw_results, list) or not raw_results:
        raise ProviderError(
            "The scoring agent returned no results.",
            stage="scoring",
            details={"transcripts": len(transcripts)},
        )

    scored: list[dict[str, Any]] = []
    for index, item in enumerate(raw_results):
        if not isinstance(item, dict):
            continue
        persona = str(item.get("persona") or transcripts[min(index, len(transcripts) - 1)].get("persona", "unknown"))
        confidence_raw = item.get("confidence", 0)
        try:
            confidence = float(confidence_raw)
        except (TypeError, ValueError):
            confidence = 0.0
        scored.append(
            {
                "persona": persona,
                "converted": bool(item.get("converted", False)),
                "confidence": confidence,
                "reason": str(item.get("reason", "")).strip(),
                "failure_point": str(item.get("failure_point", "")).strip(),
                "script_gap": str(item.get("script_gap", "")).strip(),
            }
        )

    if not scored:
        raise ProviderError("The scoring agent returned unusable results.", stage="scoring")

    conversions = sum(1 for item in scored if item["converted"])
    total = len(scored)
    return {
        "results": scored,
        "conversions": conversions,
        "total": total,
        "conversion_rate": round(conversions / total, 4) if total else 0.0,
    }


def score_batch_offline(transcripts: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic fallback scoring used only for tests and offline inspection.

    This is never used in the live pipeline. It exists so the backtest machinery
    can be exercised without a model provider.
    """
    commit_markers = (
        "let's do it",
        "lets do it",
        "book me",
        "schedule me",
        "put me down",
        "sounds good, sign me up",
        "yes, i'll take it",
        "yes ill take it",
        "i'm in",
        "im in",
    )
    results = []
    for transcript in transcripts:
        lead_lines = " ".join(
            str(turn.get("text", "")).lower()
            for turn in transcript.get("turns", [])
            if str(turn.get("speaker", "")).lower() == "lead"
        )
        converted = any(marker in lead_lines for marker in commit_markers)
        results.append(
            {
                "persona": transcript.get("persona", "unknown"),
                "converted": converted,
                "confidence": 0.6,
                "reason": "Deterministic keyword scoring (offline mode).",
                "failure_point": "" if converted else "No explicit commitment detected.",
                "script_gap": "" if converted else "Script did not drive the lead to commit.",
            }
        )

    conversions = sum(1 for item in results if item["converted"])
    total = len(results)
    return {
        "results": results,
        "conversions": conversions,
        "total": total,
        "conversion_rate": round(conversions / total, 4) if total else 0.0,
    }
