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
    except RuntimeError:
        return (
            "Headline: A clearer path to better energy decisions\n\n"
            "Body: Arizona homeowners can explore their energy options with a "
            "straightforward solar consultation. Learn what may fit your home, "
            "ask questions, and review the next steps without pressure.\n\n"
            "CTA: Request an educational consultation.\n\n"
            "Note: This draft was prepared in offline mode while the campaign "
            "generation provider is temporarily unavailable."
        )
    return result.get("content", "")
