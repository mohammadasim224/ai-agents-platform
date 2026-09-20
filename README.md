## AI Business Team

FastAPI backend and browser frontend for an AI business team organized as a
strict chain of command.

### Architecture

The **Manager** is the top of the chain of command and the **only** agent that
communicates with the user. Everything else is internal.

```
Manager  (only user-facing agent)
│  1. triage   → which department(s) own this request?
│  2. rewrite  → a precise brief per department
│  3. finalize → one answer for the user (+ downloadable file)
│
├── Marketing Department Head
│   ├── Ad Copywriting Agent
│   └── Ad Scripting Agent
├── Sales Department Head
│   ├── Appointment Setting Script Agent   (backtested)
│   └── Closing Script Agent               (backtested)
└── Automation Department Head
    ├── Lead Nurturing Writing Agent
    └── Lead Reminder Writing Agent
```

Each department head splits the brief into subtasks, assigns them to specialists,
**verifies** what comes back, and combines it before returning anything upward.

**Design rule: prefer an honest message or error over a bad answer.** The manager
never defaults to a department. An out-of-scope request, a failed quality gate, or
a failed verification produces a clear error explaining what happened, never a
substituted answer.

### How agents are taught

Each agent is defined by a markdown file under `/prompts`. Those files:

1. Define the agent's role and execution boundary.
2. Name the exact `/knowledge/*/*.md` files the agent may ground its work in.
3. Specify the output contract the agent must return.

`backend/prompts/loader.py` composes the final system prompt from the role file,
a manifest of assigned knowledge files, and the retrieved excerpts most relevant
to the task.

### Quality gates

**Sales scripts must pass a measured backtest** before delivery:

- At least **20 simulated calls**
- At least **50% conversion**

Conversion is judged by an independent scoring agent, not by the script agent.
A script that misses the target is sent back for revision with the specific gaps
that caused the failures. If it never reaches the target, the run reports the
measured numbers and fails honestly.

**Compliance** is enforced deterministically before delivery. Prohibited claims
(guaranteed savings, "free solar", fabricated anecdotes) trigger a revision
attempt with the specific violation; if the violation persists, the work is
blocked rather than delivered.

### API

| Endpoint | Purpose |
| --- | --- |
| `POST /generate` | Run the chain of command. Returns `status`, `output`, `departments`, `trace`, `artifacts`, `backtests`, `compliance`, and `error`. |
| `POST /workflows/team-campaign` | Same pipeline with workflow framing. |
| `GET /agents` | The org chart. Only the manager has `user_facing: true`. |
| `GET /evaluations/quality-gates` | The measured bars the pipeline enforces. |
| `GET /artifacts/{filename}` | Download a deliverable file. |

Every response carries a `trace` showing the stage-by-stage flow, so you can see
exactly how work moved through the organization.

### macOS setup

Requirements: macOS 12 or newer, Python 3.11+, and a shell such as zsh.

```bash
git clone <repository-url>
cd ai-business-team
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

Add the OpenRouter key to `.env`, then start the backend:

```bash
bash scripts/start-macos.sh
```

In a second terminal, serve the frontend:

```bash
python3 -m http.server 5500 --directory frontend/app
```

Open `http://localhost:5500`.

### Configuration

Set these in `.env` to tune the pipeline:

| Variable | Default | Purpose |
| --- | --- | --- |
| `MANAGER_MODEL`, `MARKETING_MODEL`, `SALES_MODEL`, `AUTOMATION_MODEL`, `EVALUATION_MODEL` | `DEFAULT_MODEL` | Per-role model selection. |
| `LLM_MAX_ATTEMPTS` | `3` | Retries for transient provider failures. |
| `MIN_DELIVERABLE_CHARS` | `120` | Shortest acceptable specialist deliverable. |
| `BACKTEST_MIN_CALLS` | `20` | Minimum simulated calls per script backtest. |
| `BACKTEST_TARGET_CONVERSION` | `0.5` | Required conversion rate. |
| `BACKTEST_MAX_ROUNDS` | `5` | Revision rounds allowed to reach the target. |

### Tests

```bash
python -m pytest -q
```

Tests stub the model router, so the full orchestration is verified without a live
provider. They assert the structural guarantees: routing never defaults, work
flows manager → head → specialist → head → manager, and unverified or
non-compliant work is never delivered.

The SQLite database is created under `data/` using `pathlib`, so no platform-specific database setup is required.
