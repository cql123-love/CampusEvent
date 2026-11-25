"""Check the production WSGI entry point across separate worker processes."""
import json
import os
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WSGI_PATH = PROJECT_ROOT / "deploy" / "pythonanywhere_wsgi.py"


def run_worker(project_home, code):
    env = os.environ.copy()
    for name in (
        "CAMPUSEVENT_DB", "CAMPUSEVENT_SEED", "CAMPUSEVENT_SECRET",
    ):
        env.pop(name, None)
    env["CAMPUSEVENT_HOME"] = str(project_home)
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    script = (
        "import json, runpy\n"
        f"app = runpy.run_path({str(WSGI_PATH)!r})['application']\n"
        "container = app.config['CONTAINER']\n"
        + code
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def test_wsgi_pages_and_https_cookies(tmp_path):
    result = run_worker(
        tmp_path,
        "client = app.test_client()\n"
        "print(json.dumps({\n"
        " 'status': [client.get(p).status_code for p in "
        "('/', '/admin', '/messages', '/static/style.css')],\n"
        " 'secure': app.config['SESSION_COOKIE_SECURE'],\n"
        " 'httponly': app.config['SESSION_COOKIE_HTTPONLY'],\n"
        " 'secret_is_private': app.secret_key != 'campusevent-dev-secret',\n"
        " 'activity_count': len(container.activity_repo.list()),\n"
        " 'db': container.db_path,\n"
        "}))\n",
    )
    assert result["status"] == [200, 200, 200, 200]
    assert result["secure"] and result["httponly"]
    assert result["secret_is_private"]
    assert result["activity_count"] == 5
    assert Path(result["db"]) == tmp_path / "instance" / "campusevent.db"


def test_wsgi_restart_preserves_data_without_reseeding(tmp_path):
    first = run_worker(
        tmp_path,
        "from campusevent.entities import Student\n"
        "container.student_repo.insert(Student(student_id='restart-test', name='Test'))\n"
        "print(json.dumps(len(container.activity_repo.list())))\n",
    )
    second = run_worker(
        tmp_path,
        "student = container.student_repo.get('restart-test')\n"
        "print(json.dumps({\n"
        " 'student': student.student_id,\n"
        " 'activities': len(container.activity_repo.list()),\n"
        " 'registrations': len(container.registration_repo.list_by_activity('act-demo-1')),\n"
        " 'messages': len(container.message_repo.list_by_student('S002')),\n"
        "}))\n",
    )
    assert first == second["activities"] == 5
    assert second["student"] == "restart-test"
    assert second["registrations"] == 2
    assert second["messages"] == 2
