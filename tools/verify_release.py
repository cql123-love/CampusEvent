"""Generate reproducible test evidence and baseline/current class metrics."""
import ast
from datetime import datetime
import json
import io
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "verification"


def classes(source):
    return {
        node.name: ast.dump(node, include_attributes=False)
        for node in ast.parse(source).body if isinstance(node, ast.ClassDef)
    }


def metrics():
    baseline = {}
    files = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", "baseline-v1", "src"], cwd=ROOT,
        text=True, encoding="utf-8",
    ).splitlines()
    for name in files:
        if name.endswith(".py"):
            source = subprocess.check_output(["git", "show", f"baseline-v1:{name}"], cwd=ROOT)
            baseline.update(classes(source.decode("utf-8")))
    current = {}
    for path in (ROOT / "src").rglob("*.py"):
        current.update(classes(path.read_text(encoding="utf-8")))
    changed = sorted(name for name in baseline.keys() & current.keys()
                     if baseline[name] != current[name])
    return {
        "baseline": subprocess.check_output(
            ["git", "rev-parse", "baseline-v1^{}"], cwd=ROOT, text=True,
        ).strip(),
        "baseline_class_count": len(baseline),
        "current_class_count": len(current),
        "new_classes": sorted(current.keys() - baseline.keys()),
        "new_class_count": len(current.keys() - baseline.keys()),
        "modified_existing_classes": changed,
        "modified_core_business_classes": [
            name for name in ("RegistrationService", "ActivityService") if name in changed
        ],
        "registration_service_ast_unchanged": baseline["RegistrationService"] == current["RegistrationService"],
        "definition": "Top-level src classes, AST comparison, moves deduplicated by unique class name.",
    }


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("CAMPUSEVENT_SEED", None)
    env.pop("CAMPUSEVENT_MOCK_EMAIL_FAIL", None)
    env.pop("PYTHONPATH", None)
    temp = tempfile.mkdtemp(prefix="campusevent-release-")
    junit = OUTPUT / "change-v2-tests.xml"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-v", "-p", "no:cacheprovider",
         "--basetemp", temp, f"--junitxml={junit}"],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    (OUTPUT / "pytest.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
    print(result.stdout)
    e2e = subprocess.run(
        [sys.executable, "tests/e2e_check.py"], cwd=ROOT, env=env, capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    (OUTPUT / "web-e2e.txt").write_text(e2e.stdout + e2e.stderr, encoding="utf-8")
    tests = ET.parse(junit).findall(".//testcase")
    summary = {
        "verified_at": datetime.now().astimezone().isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "tests": len(tests),
        "failures": sum(t.find("failure") is not None for t in tests),
        "errors": sum(t.find("error") is not None for t in tests),
        "skipped": sum(t.find("skipped") is not None for t in tests),
        "pytest_exit": result.returncode,
        "web_e2e_exit": e2e.returncode,
        "metrics": metrics(),
        "scope": "Local temporary SQLite databases, not production server verification.",
    }
    with tempfile.TemporaryDirectory(prefix="campusevent-baseline-") as old:
        archive = subprocess.check_output(
            ["git", "archive", "--format=zip", "baseline-v1"], cwd=ROOT,
        )
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            bundle.extractall(old)
        baseline_xml = OUTPUT / "baseline-v1-tests.xml"
        baseline = subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "-v", "-p", "no:cacheprovider",
             "--basetemp", str(Path(old) / ".test-temp"), f"--junitxml={baseline_xml}"],
            cwd=old, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        (OUTPUT / "baseline-pytest.txt").write_text(
            baseline.stdout + baseline.stderr, encoding="utf-8",
        )
        old_tests = ET.parse(baseline_xml).findall(".//testcase")
        summary["baseline_tests"] = len(old_tests)
        summary["baseline_failures"] = sum(t.find("failure") is not None for t in old_tests)
        summary["baseline_errors"] = sum(t.find("error") is not None for t in old_tests)
        summary["baseline_exit"] = baseline.returncode
    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if result.returncode or e2e.returncode or baseline.returncode else 0


if __name__ == "__main__":
    raise SystemExit(main())
