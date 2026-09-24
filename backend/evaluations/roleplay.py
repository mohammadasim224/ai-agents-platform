"""Lead simulation for backtesting sales scripts.

The lead simulator plays realistic homeowner personas against a candidate script.
It is deliberately separated from scoring: the simulator only produces dialogue,
while a separate scorer judges whether the lead actually committed to an
appointment. This keeps the quality gate honest instead of self-graded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.errors import ProviderError
from backend.llm.router import extract_json, route_prompt
from backend.prompts.loader import compose_system_prompt


@dataclass(frozen=True)
class Persona:
    """A homeowner archetype used to stress-test a script."""

    key: str
    label: str
    behavior: str


# A fixed, deliberately varied persona pool. Variety matters more than volume:
# a script that only converts cooperative leads has not been stress tested.
PERSONAS: tuple[Persona, ...] = (
    Persona(
        key="price_focused",
        label="Price-focused skeptic",
        behavior=(
            "Immediately pushes on cost. Asks 'how much is this going to cost me' early. "
            "Says money is tight. Will not commit unless the value is made concrete and "
            "the objection is handled without pressure or invented savings figures."
        ),
    ),
    Persona(
        key="spouse_objection",
        label="Spouse decision maker",
        behavior=(
            "Repeatedly defers to a partner. Says 'I need to talk to my wife/husband first'. "
            "Only progresses if the setter handles the partner objection properly and "
            "returns responsibility to the prospect."
        ),
    ),
    Persona(
        key="busy_skeptic",
        label="Busy and guarded",
        behavior=(
            "Says they are busy and nearly hangs up. Short answers. Tests whether the "
            "setter can earn attention quickly and confirm intent without sounding like a script."
        ),
    ),
    Persona(
        key="ready_to_book",
        label="Interested and ready",
        behavior=(
            "Already curious about solar. Answers openly and is willing to book if the "
            "setter asks clearly and confirms a specific next step."
        ),
    ),
    Persona(
        key="vague_evasive",
        label="Vague and evasive",
        behavior=(
            "Gives non-answers and dodges direct questions. Only engages when the setter "
            "calls out the non-answer and re-asks with different phrasing."
        ),
    ),
    Persona(
        key="past_bad_experience",
        label="Burned before",
        behavior=(
            "Previously talked to a solar company that overpromised. Distrustful. Needs "
            "transparency and honest framing. Rejects hype and guarantees outright."
        ),
    ),
    Persona(
        key="curious_researcher",
        label="Curious researcher",
        behavior=(
            "Asks detailed questions about how solar economics actually work. Engages well "
            "but only books if the setter demonstrates competence and does not invent facts."
        ),
    ),
    Persona(
        key="indifferent",
        label="Low urgency",
        behavior=(
            "Says 'maybe later' and 'I'm just looking'. Does not feel a reason to act. Only "
            "progresses if the setter surfaces a real consequence or a clear reason to act now."
        ),
    ),
)


def persona_pool(size: int) -> list[Persona]:
    """Return a rotating slice of the persona pool of the requested size."""
    if size <= 0:
        return []
    return [PERSONAS[index % len(PERSONAS)] for index in range(size)]


def persona_manifest(personas: list[Persona]) -> str:
    lines = []
    for index, persona in enumerate(personas, start=1):
        lines.append(f"{index}. `{persona.key}` — {persona.label}\n   Behavior: {persona.behavior}")
    return "\n".join(lines)


def simulate_batch(
    script: str,
    personas: list[Persona],
    *,
    call_context: str = "",
    max_turns: int = 10,
) -> list[dict[str, Any]]:
    """Simulate one roleplay call per persona against the candidate script.

    Returns a list of transcripts. Each transcript records the dialogue only;
    the outcome is judged separately by the scoring module.
    """
    if not personas:
        return []

    system_prompt = compose_system_prompt(
        "evaluation/lead_simulator",
        knowledge_categories=("business", "sales"),
        output="json",
        extra_rules=(
            "You are producing simulated roleplay transcripts.\n\n"
            "## Personas To Play\n\n"
            f"{persona_manifest(personas)}\n\n"
            "## Rules\n"
            "- Play the SETTER by following the supplied script as literally as possible.\n"
            "- Play the LEAD by reacting realistically to what the setter actually said.\n"
            "- The lead must NOT be cooperative by default. It only warms up when the\n"
            "  setter genuinely handles the lead's specific objection.\n"
            "- If the script is vague, incomplete, or skips objection handling, the lead\n"
            "  must respond with the objection or disengage. Do not paper over script gaps.\n"
            "- Use natural spoken language. No stage directions, no narration.\n"
            f"- Keep each transcript to at most {max_turns} exchanges.\n"
            "- Do not decide or state the final outcome. End the transcript when the\n"
            "  conversation would realistically end.\n\n"
            "## Required JSON\n"
            "{\n"
            '  "transcripts": [\n'
            "    {\n"
            '      "persona": "<persona key>",\n'
            '      "turns": [{"speaker": "setter"|"lead", "text": "<spoken line>"}],\n'
            '      "lead_final_stance": "<what the lead wants at the end of the call>"\n'
            "    }\n"
            "  ]\n"
            "}"
        ),
    )

    user_prompt = f"## Candidate Script Under Test\n{script}"
    if call_context.strip():
        user_prompt += f"\n\n## Call Context\n{call_context.strip()}"

    result = route_prompt(
        "evaluation", user_prompt, system_prompt=system_prompt, temperature=0.8, json_mode=True
    )
    payload = extract_json(result["content"])

    transcripts = payload.get("transcripts")
    if not isinstance(transcripts, list) or not transcripts:
        raise ProviderError(
            "The lead simulator did not return any transcripts.",
            stage="backtest",
            details={"personas": [persona.key for persona in personas]},
        )

    normalized: list[dict[str, Any]] = []
    for index, transcript in enumerate(transcripts):
        if not isinstance(transcript, dict):
            continue
        turns = transcript.get("turns")
        if not isinstance(turns, list) or not turns:
            continue
        normalized.append(
            {
                "persona": str(transcript.get("persona") or personas[min(index, len(personas) - 1)].key),
                "turns": [
                    {
                        "speaker": str(turn.get("speaker", "")).strip().lower(),
                        "text": str(turn.get("text", "")).strip(),
                    }
                    for turn in turns
                    if isinstance(turn, dict) and str(turn.get("text", "")).strip()
                ],
                "lead_final_stance": str(transcript.get("lead_final_stance", "")).strip(),
            }
        )

    if not normalized:
        raise ProviderError(
            "The lead simulator returned transcripts with no usable dialogue.",
            stage="backtest",
        )

    return normalized
