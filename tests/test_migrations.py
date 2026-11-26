"""Upgrade real baseline structures without reseeding or deleting history."""
import sqlite3

import pytest

from campusevent.entities import POLICY_GRADE_LIMITED, Student
from campusevent.factory import AppContainer
from tests.conftest import make_activity


BASELINE_SCHEMA = """
CREATE TABLE students(student_id TEXT PRIMARY KEY,name TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE activities(
 activity_id TEXT PRIMARY KEY,title TEXT NOT NULL,category TEXT NOT NULL,start_at TEXT NOT NULL,
 location TEXT NOT NULL,capacity INTEGER NOT NULL CHECK(capacity>0),
 policy_type TEXT NOT NULL CHECK(policy_type IN ('直接报名','审核型')),created_at TEXT NOT NULL);
CREATE TABLE registrations(
 registration_id TEXT PRIMARY KEY,activity_id TEXT NOT NULL REFERENCES activities(activity_id),
 student_id TEXT NOT NULL REFERENCES students(student_id),
 status TEXT NOT NULL CHECK(status IN ('待审核','已通过','已拒绝','已取消')),
 created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE messages(
 message_id TEXT PRIMARY KEY,student_id TEXT NOT NULL REFERENCES students(student_id),
 activity_id TEXT NOT NULL,content TEXT NOT NULL,created_at TEXT NOT NULL,
 is_read INTEGER NOT NULL DEFAULT 0,related_registration_id TEXT NOT NULL DEFAULT '',
 event_type TEXT NOT NULL DEFAULT '');
CREATE UNIQUE INDEX idx_msg_idempotent ON messages(related_registration_id,event_type);
CREATE TABLE notification_log(
 log_id TEXT PRIMARY KEY,event_type TEXT NOT NULL,student_id TEXT NOT NULL,
 activity_id TEXT NOT NULL,registration_id TEXT NOT NULL,reason TEXT NOT NULL,created_at TEXT NOT NULL);
INSERT INTO students VALUES('S002','Demo','2026-01-01'),('custom','Custom','2026-01-02');
INSERT INTO activities VALUES('legacy','Legacy','Study','2035-01-01 10:00','Room',4,'直接报名','2026-01-01');
INSERT INTO registrations VALUES('r-old','legacy','S002','已取消','2026-01-01','2026-01-02');
INSERT INTO messages VALUES('m-old','S002','legacy','Old result','2026-01-01',1,'r-old','已取消');
INSERT INTO notification_log VALUES('l-old','已通过','S002','legacy','r-old','Old failure','2026-01-01');
"""


def create_baseline(path):
    with sqlite3.connect(path) as conn:
        conn.executescript(BASELINE_SCHEMA)


def snapshot(path):
    with sqlite3.connect(path) as conn:
        return {
            name: conn.execute(f"SELECT * FROM {name} ORDER BY 1").fetchall()
            for name in ("activities", "registrations", "messages", "notification_log")
        }


def test_upgrade_preserves_history_and_is_repeatable(tmp_path):
    path = str(tmp_path / "legacy.db")
    create_baseline(path)
    before = snapshot(path)
    c = AppContainer(path)
    assert snapshot(path) == before
    assert c.student_repo.get("S002").grade == 2
    assert c.student_repo.get("custom").grade == 1
    assert c.email_repo.list_by_student("S002") == []
    a = make_activity(c.activity_service, policy_type=POLICY_GRADE_LIMITED)
    c.student_repo.insert(Student("new", "New", grade=3))
    c.registration_service.submit(a.activity_id, "new")
    for _ in range(2):
        c = AppContainer(path)
    assert len(c.email_repo.list_by_student("new")) == 1
    assert c.registration_repo.get("r-old").status == "已取消"
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    c.activity_service.delete_activity(a.activity_id) if False else None


def test_migration_failure_rolls_back_all_schema_changes(tmp_path, monkeypatch):
    from campusevent import migrations
    path = str(tmp_path / "rollback.db")
    create_baseline(path)
    before = snapshot(path)

    def fail(conn):
        raise RuntimeError("injected migration validation failure")

    monkeypatch.setattr(migrations, "_validate_integrity", fail)
    with pytest.raises(RuntimeError, match="injected"):
        AppContainer(path)
    with sqlite3.connect(path) as conn:
        assert "grade" not in [row[1] for row in conn.execute("PRAGMA table_info(students)")]
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='mock_emails'").fetchone()
    assert snapshot(path) == before


def test_orphaned_legacy_data_rejects_upgrade_without_loss(tmp_path):
    path = str(tmp_path / "orphan.db")
    create_baseline(path)
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE registrations SET student_id='missing'")
    before = snapshot(path)
    with pytest.raises(RuntimeError, match="外键"):
        AppContainer(path)
    assert snapshot(path) == before


def test_newer_database_version_is_not_downgraded(tmp_path):
    path = str(tmp_path / "future.db")
    create_baseline(path)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA user_version=99")
    with pytest.raises(RuntimeError, match="版本"):
        AppContainer(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 99
