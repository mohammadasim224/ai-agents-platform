"""Prompt loading and composition.

Every agent in the chain of command is defined by a markdown prompt file in the
`/prompts` directory. Those files do three jobs:

1. Define the agent's role and its execution boundary.
2. Teach the agent which files under `/knowledge` to read and how to use them.
3. Define the exact output contract the agent must return.

This module loads those files, resolves the knowledge files each role is allowed
to read, and composes the final system prompt with a hard output contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from backend.config import KNOWLEDGE_DIR, PROMPTS_DIR, iter_knowledge_files
from backend.errors import PipelineError


@dataclass(frozen=True)
class KnowledgeSource:
    """A knowledge document available to an agent."""

    path: str  # path relative to /knowledge, for example "sales/salestraining.md"
    category: str  # top-level folder, for example "sales"
    title: str  # human-readable title taken from the first heading

    def as_bullet(self) -> str:
        return f"- `knowledge/{self.path}` — {self.title}"


def _first_heading(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return ""


@lru_cache(maxsize=1)
def knowledge_catalog() -> tuple[KnowledgeSource, ...]:
    """Index every markdown document under /knowledge exactly once."""
    if not KNOWLEDGE_DIR.is_dir():
        return ()

    sources: list[KnowledgeSource] = []
    for path in iter_knowledge_files(KNOWLEDGE_DIR):
        relative = path.relative_to(KNOWLEDGE_DIR)
        try:
            title = _first_heading(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            title = ""
        sources.append(
            KnowledgeSource(
                path=relative.as_posix(),
                category=relative.parts[0] if len(relative.parts) > 1 else "general",
                title=title or relative.stem.replace("_", " ").title(),
            )
        )
    return tuple(sources)


def knowledge_for(categories: Iterable[str]) -> list[KnowledgeSource]:
    """Return the knowledge sources belonging to the given categories."""
    wanted = {category.lower() for category in categories}
    return [source for source in knowledge_catalog() if source.category.lower() in wanted]


def knowledge_manifest(categories: Iterable[str]) -> str:
    """Render a bullet list of the knowledge files a role is allowed to read."""
    sources = knowledge_for(categories)
    if not sources:
        return "(no knowledge files available)"
    return "\n".join(source.as_bullet() for source in sources)


def _prompt_path(name: str) -> Path:
    return PROMPTS_DIR / f"{name}.md"


@lru_cache(maxsize=64)
def load_prompt(name: str) -> str:
    """Load a markdown prompt file by its path relative to /prompts.

    Example: load_prompt("manager/triage") -> prompts/manager/triage.md
    """
    path = _prompt_path(name)
    if not path.is_file():
        raise PipelineError(
            f"Missing prompt file: prompts/{name}.md",
            stage="prompt_loading",
            details={"prompt": name},
            hint="Restore the prompt file or update the agent definition that references it.",
        )
    return path.read_text(encoding="utf-8").strip()


OUTPUT_CONTRACT_JSON = """
## Output Contract

Return a single JSON object and nothing else.
Do not wrap the JSON in markdown fences.
Do not add commentary before or after the JSON.
If you cannot complete the assignment, return the JSON object with the
`status` field set to "error" and an explanatory `message` instead of guessing.
""".strip()


OUTPUT_CONTRACT_TEXT = """
## Output Contract

Return only the finished deliverable as plain text or markdown.
Do not add meta-commentary, apologies, or notes about your process.
Do not return placeholders such as "..." or "[insert here]" in the finished work.
If you cannot complete the assignment, reply with exactly one line beginning
with `ERROR:` followed by the specific reason.
""".strip()


def compose_system_prompt(
    prompt_name: str,
    *,
    knowledge_categories: Iterable[str] = (),
    output: str = "text",
    extra_rules: str = "",
    knowledge_text: str = "",
) -> str:
    """Build the final system prompt for an agent.

    The composed prompt always contains, in order:
    1. The markdown prompt file for the role.
    2. A manifest of the knowledge files the role is allowed to use.
    3. Optional retrieved knowledge excerpts.
    4. Optional extra rules.
    5. A hard output contract.
    """
    body = load_prompt(prompt_name)
    sections = [body]

    manifest = knowledge_manifest(knowledge_categories)
    sections.append(
        "## Knowledge Files Assigned To You\n\n"
        "These are the only knowledge files you may ground your work in. "
        "Read them for structure, method, tone, and verified facts. "
        "Never invent facts that are not present in them.\n\n"
        f"{manifest}"
    )

    if knowledge_text.strip():
        sections.append(
            "## Retrieved Knowledge Excerpts\n\n"
            "The following excerpts were selected as most relevant to this task. "
            "Use them directly and prefer them over generic assumptions.\n\n"
            f"{knowledge_text.strip()}"
        )

    if extra_rules.strip():
        sections.append(f"## Additional Rules\n\n{extra_rules.strip()}")

    sections.append(OUTPUT_CONTRACT_JSON if output == "json" else OUTPUT_CONTRACT_TEXT)
    return "\n\n---\n\n".join(sections)
