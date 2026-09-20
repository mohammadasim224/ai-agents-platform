from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Project:
    id: str
    name: str
    description: str = ""
    created_at: str = ""


@dataclass
class Task:
    id: str
    project_id: str
    agent: str
    input: str
    status: str = "pending"
    created_at: str = ""
    completed_at: str | None = None


@dataclass
class AgentRecord:
    id: str
    name: str
    department: str
    prompt_version: str = "v1"
    model: str = "openrouter/free"
    active: bool = True


@dataclass
class KnowledgeDocument:
    id: str
    project_id: str
    name: str
    path: str
    category: str
    version: int = 1
    status: str = "active"
    hash: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Generation:
    id: str
    task_id: str
    model: str
    prompt_version: str
    output: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency: int = 0
    created_at: str = ""


@dataclass
class Evaluation:
    id: str
    generation_id: str
    evaluator: str
    result: dict[str, Any] = field(default_factory=dict)
    feedback: str = ""
    created_at: str = ""
