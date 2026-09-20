from __future__ import annotations

from backend.llm.router import route_prompt


def write_ad_copy(prompt: str) -> str:
    system_prompt = """
You are an expert ad copywriter.
Use only approved business facts from the current project knowledge.
Never invent pricing, guarantees, claims, or customer proof.
Output concise, marketing-ready copy with headline, body, CTA, and 3 variations if relevant.
"""
    try:
        result = route_prompt("marketing", prompt, system_prompt=system_prompt)
    except RuntimeError as error:
        request = prompt.split("\n\nRelevant knowledge:", 1)[0].strip()
        return (
            f"Offline draft for this request:\n\n{request}\n\n"
            "Suggested direction: Turn that request into a clear, audience-specific "
            "message using only verified project knowledge. Add one concrete benefit, "
            "a low-pressure next step, and a concise call to action.\n\n"
            f"Provider status: {error}. Add a valid OPENROUTER_API_KEY to .env for live model generation."
        )
    return result.get("content", "")
