"""Back up a SQLite database before invoking transactional application migrations."""
import argparse
from datetime import datetime
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from campusevent.factory import init_db


def upgrade(path, backup_dir=None):
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Database does not exist: {path}")
    destination = Path(backup_dir).resolve() if backup_dir else path.parent / "backups"
    destination.mkdir(parents=True, exist_ok=True)
    backup = destination / f"{path.stem}-{datetime.now():%Y%m%d-%H%M%S-%f}.db"
    with backup.open("xb"):
        pass
    source = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    target = sqlite3.connect(backup)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    print(f"Backup: {backup}", flush=True)
    init_db(str(path))
    with sqlite3.connect(path) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if version != 2 or violations:
        raise RuntimeError("Upgrade verification failed; preserve the backup.")
    print(f"UPGRADE PASSED: schema={version}, foreign_key_errors={len(violations)}")
    return backup


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("database")
    parser.add_argument("--backup-dir")
    args = parser.parse_args()
    upgrade(args.database, args.backup_dir)
