from __future__ import annotations


BLOCKED_PATTERNS = [
    "free solar",
    "free panels",
    "government will pay",
    "guaranteed savings",
    "no bill",
]


def check_compliance(text: str) -> dict:
    lowered = text.lower()
    issues = [pattern for pattern in BLOCKED_PATTERNS if pattern in lowered]
    if issues:
        return {"status": "blocked", "issues": issues}
    return {"status": "pass", "issues": []}
