"""WSGI entry point for a PythonAnywhere manual-configuration web app."""
import os
import secrets
import sys
from pathlib import Path

project_home = Path(
    os.environ.get("CAMPUSEVENT_HOME", str(Path.home() / "CampusEvent"))
).resolve()
state_dir = project_home / "instance"
state_dir.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(project_home))
os.environ.setdefault("CAMPUSEVENT_DB", str(state_dir / "campusevent.db"))
os.environ.setdefault("CAMPUSEVENT_SEED", "1")

from app import app as application  # noqa: E402

# A fresh worker gets a private signing key; reloads may clear flash messages.
application.config.update(
    SECRET_KEY=os.environ.get("CAMPUSEVENT_SECRET") or secrets.token_hex(32),
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
