from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "ai_business_team.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                user_id TEXT DEFAULT 'demo-user',
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                agent TEXT NOT NULL,
                input TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS generations (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                output TEXT NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                latency INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


initialize_database()


def create_project(name: str, description: str = "", user_id: str = "demo-user") -> dict[str, Any]:
    import uuid

    project_id = str(uuid.uuid4())
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO projects (id, user_id, name, description) VALUES (?, ?, ?, ?)",
            (project_id, user_id, name, description),
        )
    return {"id": project_id, "user_id": user_id, "name": name, "description": description}


def list_projects(user_id: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM projects"
    params: tuple[Any, ...] = ()
    if user_id:
        query += " WHERE user_id = ?"
        params = (user_id,)
    query += " ORDER BY created_at DESC"
    with get_connection() as connection:
        rows = connection.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_project(project_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    query = "SELECT * FROM projects WHERE id = ?"
    params: tuple[Any, ...] = (project_id,)
    if user_id:
        query += " AND user_id = ?"
        params += (user_id,)
    with get_connection() as connection:
        row = connection.execute(query, params).fetchone()
    return dict(row) if row else None


def create_task(project_id: str, agent: str, input_text: str, status: str = "queued") -> dict[str, Any]:
    import uuid

    task_id = str(uuid.uuid4())
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO tasks (id, project_id, agent, input, status) VALUES (?, ?, ?, ?, ?)",
            (task_id, project_id, agent, input_text, status),
        )
    return {"id": task_id, "project_id": project_id, "agent": agent, "input": input_text, "status": status}


def list_tasks(project_id: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM tasks"
    params: tuple[Any, ...] = ()
    if project_id:
        query += " WHERE project_id = ?"
        params = (project_id,)
    query += " ORDER BY created_at DESC"

    with get_connection() as connection:
        rows = connection.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_task(task_id: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return dict(row) if row else None


def create_generation(task_id: str, model: str, prompt_version: str, output: str, input_tokens: int = 0, output_tokens: int = 0, latency: int = 0) -> dict[str, Any]:
    import uuid

    generation_id = str(uuid.uuid4())
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO generations (id, task_id, model, prompt_version, output, input_tokens, output_tokens, latency) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (generation_id, task_id, model, prompt_version, output, input_tokens, output_tokens, latency),
        )
    return {"id": generation_id, "task_id": task_id, "model": model, "prompt_version": prompt_version, "output": output}
