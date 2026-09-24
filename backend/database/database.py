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
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                business_type TEXT DEFAULT '',
                industry TEXT DEFAULT '',
                description TEXT DEFAULT '',
                target_customer TEXT DEFAULT '',
                services TEXT DEFAULT '',
                offers TEXT DEFAULT '',
                pricing TEXT DEFAULT '',
                brand_voice TEXT DEFAULT '',
                marketing_channels TEXT DEFAULT '',
                sales_process TEXT DEFAULT '',
                automation_needs TEXT DEFAULT '',
                geographic_focus TEXT DEFAULT '',
                compliance_notes TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                profile_id TEXT DEFAULT 'default',
                title TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                meta TEXT DEFAULT '{}',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_items (
                id TEXT PRIMARY KEY,
                profile_id TEXT DEFAULT 'default',
                content TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                source TEXT DEFAULT 'manual',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS queue_items (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                result TEXT DEFAULT '',
                error TEXT DEFAULT '',
                progress TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                started_at TEXT,
                completed_at TEXT
            )
            """
        )
        _ensure_column(connection, "queue_items", "progress", "TEXT DEFAULT ''")
        # Set when the user asks a job to stop. A `queued` job is cancelled
        # outright; a `running` job cannot be killed from another thread, so the
        # flag is polled by the worker at checkpoints instead.
        _ensure_column(connection, "queue_items", "cancel_requested", "INTEGER DEFAULT 0")


def _ensure_column(
    connection: sqlite3.Connection, table: str, column: str, definition: str
) -> None:
    """Add a column to an existing table when it is missing.

    `CREATE TABLE IF NOT EXISTS` does not alter tables that already exist, so a
    database created before a column was introduced would be missing it. This
    keeps upgrades working without a migration tool.
    """
    existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


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


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

PROFILE_FIELDS = [
    "name",
    "business_type",
    "industry",
    "description",
    "target_customer",
    "services",
    "offers",
    "pricing",
    "brand_voice",
    "marketing_channels",
    "sales_process",
    "automation_needs",
    "geographic_focus",
    "compliance_notes",
]


def create_profile(data: dict[str, Any]) -> dict[str, Any]:
    import uuid

    profile_id = str(uuid.uuid4())
    values = {field: str(data.get(field) or "").strip() for field in PROFILE_FIELDS}
    values["name"] = values["name"] or "Untitled business"
    columns = ", ".join(["id", *PROFILE_FIELDS])
    placeholders = ", ".join(["?"] * (len(PROFILE_FIELDS) + 1))
    with get_connection() as connection:
        connection.execute(
            f"INSERT INTO profiles ({columns}) VALUES ({placeholders})",
            (profile_id, *[values[field] for field in PROFILE_FIELDS]),
        )
    return {"id": profile_id, **values}


def list_profiles() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM profiles ORDER BY updated_at DESC").fetchall()
    return [dict(row) for row in rows]


def get_profile(profile_id: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
    return dict(row) if row else None


def update_profile(profile_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    values = {field: str(data.get(field) or "").strip() for field in PROFILE_FIELDS}
    assignments = ", ".join(f"{field} = ?" for field in PROFILE_FIELDS)
    with get_connection() as connection:
        connection.execute(
            f"UPDATE profiles SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (*[values[field] for field in PROFILE_FIELDS], profile_id),
        )
    return get_profile(profile_id)


def delete_profile(profile_id: str) -> None:
    with get_connection() as connection:
        connection.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------


def create_conversation(profile_id: str, title: str) -> dict[str, Any]:
    import uuid

    conversation_id = str(uuid.uuid4())
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO conversations (id, profile_id, title) VALUES (?, ?, ?)",
            (conversation_id, profile_id, title),
        )
    return {"id": conversation_id, "profile_id": profile_id, "title": title}


def list_conversations(profile_id: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM conversations"
    params: tuple[Any, ...] = ()
    if profile_id:
        query += " WHERE profile_id = ?"
        params = (profile_id,)
    query += " ORDER BY updated_at DESC"
    with get_connection() as connection:
        rows = connection.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_conversation(conversation_id: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
    return dict(row) if row else None


def touch_conversation(conversation_id: str) -> None:
    with get_connection() as connection:
        connection.execute(
            "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (conversation_id,),
        )


def rename_conversation(conversation_id: str, title: str) -> None:
    with get_connection() as connection:
        connection.execute(
            "UPDATE conversations SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (title, conversation_id),
        )


def delete_conversation(conversation_id: str) -> None:
    with get_connection() as connection:
        connection.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        connection.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))


def add_message(conversation_id: str, role: str, content: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    import json
    import uuid

    message_id = str(uuid.uuid4())
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO messages (id, conversation_id, role, content, meta) VALUES (?, ?, ?, ?, ?)",
            (message_id, conversation_id, role, content, json.dumps(meta or {})),
        )
        connection.execute(
            "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (conversation_id,),
        )
    return {"id": message_id, "conversation_id": conversation_id, "role": role, "content": content, "meta": meta or {}}


def list_messages(conversation_id: str) -> list[dict[str, Any]]:
    import json

    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["meta"] = json.loads(item.get("meta") or "{}")
        except (TypeError, ValueError):
            item["meta"] = {}
        result.append(item)
    return result


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


def add_memory(profile_id: str, content: str, category: str = "general", source: str = "manual") -> dict[str, Any]:
    import uuid

    memory_id = str(uuid.uuid4())
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO memory_items (id, profile_id, content, category, source) VALUES (?, ?, ?, ?, ?)",
            (memory_id, profile_id, content, category, source),
        )
    return {"id": memory_id, "profile_id": profile_id, "content": content, "category": category, "source": source}


def list_memory(profile_id: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM memory_items"
    params: tuple[Any, ...] = ()
    if profile_id:
        query += " WHERE profile_id = ?"
        params = (profile_id,)
    query += " ORDER BY created_at DESC"
    with get_connection() as connection:
        rows = connection.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def delete_memory(memory_id: str) -> None:
    with get_connection() as connection:
        connection.execute("DELETE FROM memory_items WHERE id = ?", (memory_id,))


# ---------------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------------


def _decode_queue_item(row: Any) -> dict[str, Any]:
    """Turn a raw queue row into the shape the API and worker expect.

    The JSON columns are decoded defensively (a corrupt value becomes an empty
    dict rather than raising) and `cancel_requested` is normalised to a real
    boolean so callers never have to reason about SQLite's 0/1 integers.
    """
    import json

    item = dict(row)
    for column in ("payload", "result", "progress"):
        try:
            item[column] = json.loads(item.get(column) or "{}")
        except (TypeError, ValueError):
            item[column] = {}
    item["cancel_requested"] = bool(item.get("cancel_requested"))
    return item


def enqueue_item(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    import json
    import uuid

    item_id = str(uuid.uuid4())
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO queue_items (id, kind, payload) VALUES (?, ?, ?)",
            (item_id, kind, json.dumps(payload)),
        )
    return {"id": item_id, "kind": kind, "payload": payload, "status": "queued"}


def list_queue_items(limit: int = 50, *, oldest_first: bool = False) -> list[dict[str, Any]]:
    order = "ASC" if oldest_first else "DESC"
    with get_connection() as connection:
        rows = connection.execute(
            f"SELECT * FROM queue_items ORDER BY created_at {order}, rowid {order} LIMIT ?",
            (limit,),
        ).fetchall()
    return [_decode_queue_item(row) for row in rows]


def next_queued_item() -> dict[str, Any] | None:
    """Return the oldest queued job, or None when the queue is empty.

    Ordering by `created_at` then `rowid` guarantees FIFO even when several jobs
    share the same second-level timestamp. Jobs the user cancelled are skipped
    so a cancel that raced with the worker can never start the job anyway.
    """
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM queue_items WHERE status = 'queued' AND cancel_requested = 0 "
            "ORDER BY created_at ASC, rowid ASC LIMIT 1"
        ).fetchone()
    return _decode_queue_item(row) if row else None


def request_cancel(item_id: str) -> dict[str, Any] | None:
    """Ask a job to stop, returning its updated row (or None if unknown).

    A `queued` job is cancelled immediately because nothing has started yet. A
    `running` job cannot be killed safely from another thread, so it is flagged
    and the worker stops it at its next checkpoint. A job that already reached a
    terminal state is left untouched, so cancelling a finished job is a no-op
    rather than a way to rewrite history.
    """
    with get_connection() as connection:
        row = connection.execute(
            "SELECT status FROM queue_items WHERE id = ?", (item_id,)
        ).fetchone()
        if not row:
            return None
        if row["status"] == "queued":
            connection.execute(
                "UPDATE queue_items SET status = 'cancelled', cancel_requested = 1, "
                "error = ?, completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                ("Cancelled before it started.", item_id),
            )
        elif row["status"] == "running":
            connection.execute(
                "UPDATE queue_items SET cancel_requested = 1 WHERE id = ?", (item_id,)
            )
    return get_queue_item(item_id)


def is_cancel_requested(item_id: str) -> bool:
    """Whether the user has asked this job to stop.

    Read on every checkpoint, so it must stay a cheap single-row lookup.
    """
    with get_connection() as connection:
        row = connection.execute(
            "SELECT cancel_requested FROM queue_items WHERE id = ?", (item_id,)
        ).fetchone()
    return bool(row and row["cancel_requested"])


def requeue_stale_items() -> int:
    """Recover jobs left `running` by a crash or restart.

    A single-worker queue cannot have a legitimately running job at startup, so
    any `running` row is stale. Without this, those jobs would hang forever and
    the UI would show a permanent spinner. A stale job the user had already
    cancelled is finished as `cancelled` instead of being run again.
    """
    with get_connection() as connection:
        connection.execute(
            "UPDATE queue_items SET status = 'cancelled', error = ?, "
            "completed_at = CURRENT_TIMESTAMP "
            "WHERE status = 'running' AND cancel_requested = 1",
            ("Cancelled by the user before the backend restarted.",),
        )
        cursor = connection.execute(
            "UPDATE queue_items SET status = 'queued', started_at = NULL "
            "WHERE status = 'running' AND cancel_requested = 0"
        )
        return cursor.rowcount or 0


def reclaim_timed_out_items(max_runtime_seconds: int) -> list[str]:
    """Fail jobs that have been `running` longer than the allowed runtime.

    A single-worker queue is blocked by whatever job is running, so a job that
    hangs (a provider call that never returns, a deadlock) would stall every
    later job indefinitely. Timestamps are compared in UTC because
    `CURRENT_TIMESTAMP` is UTC; comparing against local time would be wrong by
    the machine's UTC offset.

    A job the user cancelled is finished as `cancelled` rather than `failed`:
    the user asked for it to stop, so reporting a timeout would be misleading.

    Returns the ids that were reclaimed.
    """
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT id, cancel_requested FROM queue_items WHERE status = 'running' "
            "AND started_at IS NOT NULL "
            "AND (strftime('%s', 'now') - strftime('%s', started_at)) > ?",
            (max_runtime_seconds,),
        ).fetchall()
        ids = [row["id"] for row in rows]
        for row in rows:
            if row["cancel_requested"]:
                connection.execute(
                    "UPDATE queue_items SET status = 'cancelled', error = ?, "
                    "completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                    ("Cancelled by the user.", row["id"]),
                )
            else:
                connection.execute(
                    "UPDATE queue_items SET status = 'failed', "
                    "error = ?, completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (
                        f"The job exceeded the maximum runtime of {max_runtime_seconds}s "
                        "and was stopped so the queue could continue.",
                        row["id"],
                    ),
                )
    return ids


def finish_queue_item(
    item_id: str,
    started_at: str,
    *,
    status: str,
    result: Any = None,
    error: str = "",
) -> bool:
    """Complete a job only if it is still the one this worker started.

    Guards against a job that timed out and was reclaimed by the watchdog
    resurrecting itself when its handler finally returns.

    Returns True when the update applied.
    """
    import json

    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE queue_items SET status = ?, result = ?, error = ?, "
            "completed_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'running' AND started_at = ?",
            (
                status,
                json.dumps(result if isinstance(result, dict) else {"output": result}) if result is not None else "",
                error,
                item_id,
                started_at,
            ),
        )
        return (cursor.rowcount or 0) > 0


def get_queue_item(item_id: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM queue_items WHERE id = ?", (item_id,)
        ).fetchone()
    return _decode_queue_item(row) if row else None


def update_queue_item(item_id: str, **fields: Any) -> dict[str, Any] | None:
    import json

    allowed = {"status", "result", "error", "progress", "started_at", "completed_at"}
    updates = {key: value for key, value in fields.items() if key in allowed}
    if not updates:
        return get_queue_item(item_id)
    if "result" in updates and not isinstance(updates["result"], str):
        updates["result"] = json.dumps(updates["result"])
    if "progress" in updates and not isinstance(updates["progress"], str):
        updates["progress"] = json.dumps(updates["progress"])
    assignments = ", ".join(f"{key} = ?" for key in updates)
    with get_connection() as connection:
        connection.execute(
            f"UPDATE queue_items SET {assignments} WHERE id = ?",
            (*updates.values(), item_id),
        )
    return get_queue_item(item_id)
