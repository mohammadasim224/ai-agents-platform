"""Deterministic compliance gate.

This is a fast, model-free first line of defence that mirrors the rules in
`knowledge/marketing/banned_claims.md`. It runs before an answer is handed back
to the manager, so clearly non-compliant work is blocked rather than delivered.

The check is intentionally conservative: a blocked result means the content needs
to be rewritten, not that the request is impossible.
"""

from __future__ import annotations

import re
from typing import Any

# Directly prohibited phrases. These are treated as hard blocks.
BLOCKED_PATTERNS: tuple[tuple[str, str], ...] = (
    ("free solar", "Describing solar as free is prohibited; use zero-down installation language."),
    ("free panels", "Describing panels as free is prohibited; use zero-down installation language."),
    ("free solar panels", "Describing panels as free is prohibited."),
    ("government will pay", "Implying the government pays homeowners directly is prohibited."),
    ("government pays you", "Implying the government pays homeowners directly is prohibited."),
    ("guaranteed savings", "Savings cannot be guaranteed."),
    ("guarantee savings", "Savings cannot be guaranteed."),
    ("guaranteed to eliminate", "Bill elimination cannot be guaranteed."),
    ("eliminate your electric bill", "Bill elimination cannot be guaranteed."),
    ("eliminate that bill", "Bill elimination cannot be guaranteed."),
    ("no bill", "Promising no electric bill is prohibited."),
    ("$0 electric bill", "A guaranteed $0 electric bill is prohibited."),
    ("zero electric bill", "A guaranteed $0 electric bill is prohibited."),
    ("never pay power", "Promising no power bills ever is prohibited."),
    ("government mandate", "Claiming a forced government mandate is prohibited."),
    ("no contract needed", "Solar requires formal terms; this claim is prohibited."),
    ("no commitment needed", "Solar requires formal terms; this claim is prohibited."),
    ("direct check", "Claiming a direct government check is prohibited."),
)

# Fabricated first-person or third-party anecdote markers. AI UGC avatars must
# never present invented personal experiences as real.
FABRICATION_PATTERNS: tuple[tuple[str, str], ...] = (
    ("my neighbor", "Fabricated third-party anecdotes are prohibited."),
    ("my friend", "Fabricated third-party anecdotes are prohibited."),
    ("my house last", "Fabricated personal anecdotes are prohibited."),
    ("i installed solar", "Fabricated personal anecdotes are prohibited."),
    ("my electric bill dropped", "Fabricated personal anecdotes are prohibited."),
    ("when the installers came to my", "Fabricated personal anecdotes are prohibited."),
    ("my cousin", "Fabricated third-party anecdotes are prohibited."),
)

# Unsupported absolute money claims such as "save $3,500 guaranteed".
ABSOLUTE_SAVINGS = re.compile(
    r"\bsave\s+\$[\d,]+(?:\.\d+)?\s*(?:guaranteed|every month|per month|a year|annually)\b",
    re.IGNORECASE,
)
UNIVERSAL_PERCENT = re.compile(
    r"\b(?:reduce|cut|lower)\s+(?:your\s+)?(?:electric|power|energy)?\s*bills?\s+by\s+\d{2,3}\s*%",
    re.IGNORECASE,
)


def check_compliance(text: str) -> dict[str, Any]:
    """Check text against the mandatory compliance rules.

    Returns a dict with `status` of `"pass"` or `"blocked"`, the matched issues,
    and a list of concrete remediation notes.
    """
    lowered = (text or "").lower()
    issues: list[dict[str, str]] = []

    for pattern, reason in BLOCKED_PATTERNS:
        if pattern in lowered:
            issues.append({"type": "prohibited_claim", "match": pattern, "reason": reason})

    for pattern, reason in FABRICATION_PATTERNS:
        if pattern in lowered:
            issues.append({"type": "fabricated_anecdote", "match": pattern, "reason": reason})

    for match in ABSOLUTE_SAVINGS.findall(text or ""):
        issues.append(
            {
                "type": "unsubstantiated_savings",
                "match": match.strip(),
                "reason": "Dollar savings cannot be stated as guaranteed or universal.",
            }
        )

    for match in UNIVERSAL_PERCENT.findall(text or ""):
        issues.append(
            {
                "type": "unsubstantiated_savings",
                "match": match.strip(),
                "reason": "Universal percentage reductions are prohibited; savings vary by home.",
            }
        )

    if not issues:
        return {"status": "pass", "issues": []}

    return {
        "status": "blocked",
        "issues": issues,
        "remediation": [
            "Replace free-solar language with zero-down installation language.",
            "Replace guarantees with conditional phrasing such as 'may reduce' and 'if you qualify'.",
            "Remove fabricated personal or third-party stories; use an educational persona frame.",
            "Remove universal dollar or percentage savings figures.",
        ],
    }
