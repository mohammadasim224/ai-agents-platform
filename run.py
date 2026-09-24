#!/usr/bin/env python3
"""One-command launcher for the whole AI Business Team system.

Running this file starts everything the app needs:

1. The FastAPI backend (``backend.main:app``) on the API port.
2. A static file server for the browser frontend on the UI port.
3. Your default browser, opened at the UI.

Usage::

    python run.py                 # start backend + frontend, open browser
    python run.py --no-browser    # don't open a browser
    python run.py --api-port 9000 --ui-port 6000
    python run.py --reload        # auto-reload the backend on code changes

Press Ctrl+C once to shut everything down cleanly.
"""

from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT_DIR / "frontend" / "app"
VENV_DIR = ROOT_DIR / ".venv"

DEFAULT_API_PORT = 8000
DEFAULT_UI_PORT = 5500


# --------------------------------------------------------------------------- #
# Environment helpers
# --------------------------------------------------------------------------- #
def ensure_venv() -> None:
    """Re-exec under the project virtualenv when one exists and isn't active."""
    if not VENV_DIR.is_dir():
        return

    venv_python = VENV_DIR / ("Scripts" if os.name == "nt" else "bin") / (
        "python.exe" if os.name == "nt" else "python"
    )
    if not venv_python.exists():
        return

    # Already running inside the venv? Nothing to do.
    if Path(sys.executable).resolve() == venv_python.resolve():
        return

    print(f"[run] Re-launching inside virtualenv: {venv_python}")
    os.execv(str(venv_python), [str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]])


def check_dependencies() -> None:
    """Fail early with a helpful message if the backend deps are missing."""
    missing: list[str] = []
    for module, package in (
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("dotenv", "python-dotenv"),
        ("pydantic", "pydantic"),
    ):
        try:
            __import__(module)
        except ImportError:
            missing.append(package)

    if missing:
        print("[run] Missing required packages: " + ", ".join(missing))
        print("[run] Install them with:")
        print(f"      {Path(sys.executable)} -m pip install -r requirements.txt")
        raise SystemExit(1)


def check_env_file() -> None:
    """Warn (don't fail) when no .env is present, since the API key is optional."""
    if not (ROOT_DIR / ".env").exists():
        print("[run] No .env found. Copy .env.example to .env and add your")
        print("      OPENROUTER_API_KEY for live model calls.")


def port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def wait_for_port(host: str, port: int, timeout: float = 30.0) -> bool:
    """Block until something is listening on host:port, or the timeout elapses."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            if sock.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.2)
    return False


# --------------------------------------------------------------------------- #
# Frontend static server
# --------------------------------------------------------------------------- #
class _QuietStaticHandler(SimpleHTTPRequestHandler):
    """Static handler that keeps the console readable."""

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        pass


def start_frontend_server(host: str, port: int) -> ThreadingHTTPServer:
    handler = partial(_QuietStaticHandler, directory=str(FRONTEND_DIR))
    server = ThreadingHTTPServer((host, port), handler)
    thread = threading.Thread(target=server.serve_forever, name="frontend", daemon=True)
    thread.start()
    return server


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the whole AI Business Team system.")
    parser.add_argument("--host", default="127.0.0.1", help="Host for both servers (default: 127.0.0.1)")
    parser.add_argument("--api-port", type=int, default=DEFAULT_API_PORT, help=f"Backend port (default: {DEFAULT_API_PORT})")
    parser.add_argument("--ui-port", type=int, default=DEFAULT_UI_PORT, help=f"Frontend port (default: {DEFAULT_UI_PORT})")
    parser.add_argument("--reload", action="store_true", help="Auto-reload the backend on code changes")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser window")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    ensure_venv()
    check_dependencies()
    check_env_file()

    if not FRONTEND_DIR.is_dir():
        print(f"[run] Frontend directory not found: {FRONTEND_DIR}")
        return 1

    for label, port in (("API", args.api_port), ("UI", args.ui_port)):
        if not port_is_free(args.host, port):
            print(f"[run] {label} port {port} is already in use. Stop that process or pick another port.")
            return 1

    ui_url = f"http://{args.host}:{args.ui_port}"

    print("=" * 60)
    print("  AI Business Team")
    print("=" * 60)
    print(f"  Backend : http://{args.host}:{args.api_port}")
    print(f"  Frontend: {ui_url}")
    print("  Press Ctrl+C to stop.")
    print("=" * 60)

    # Start the frontend static server in-process.
    frontend_server = start_frontend_server(args.host, args.ui_port)

    # Start the backend as a child process so uvicorn manages its own lifecycle.
    backend_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.main:app",
        "--host",
        args.host,
        "--port",
        str(args.api_port),
    ]
    if args.reload:
        backend_cmd.append("--reload")

    backend = subprocess.Popen(backend_cmd, cwd=str(ROOT_DIR))

    def shutdown(*_args) -> None:
        print("\n[run] Shutting down...")
        if backend.poll() is None:
            backend.terminate()
            try:
                backend.wait(timeout=10)
            except subprocess.TimeoutExpired:
                backend.kill()
        frontend_server.shutdown()
        print("[run] Stopped.")

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        if wait_for_port(args.host, args.api_port):
            print("[run] Backend is ready.")
        else:
            print("[run] Backend did not become ready in time; check the logs above.")

        if not args.no_browser:
            webbrowser.open(ui_url)

        # Keep the launcher alive until the backend exits or Ctrl+C is pressed.
        while backend.poll() is None:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        shutdown()

    return backend.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())