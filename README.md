## AI Business Team

FastAPI backend and browser frontend for the AI business team.

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

### Tests

```bash
python -m pytest -q
```

The SQLite database is created under `data/` using `pathlib`, so no platform-specific database setup is required.
