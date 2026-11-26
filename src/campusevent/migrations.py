"""Transactional upgrade of the baseline SQLite database."""
import sqlite3


ACTIVITY_SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    activity_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    start_at TEXT NOT NULL,
    location TEXT NOT NULL,
    capacity INTEGER NOT NULL CHECK (capacity > 0),
    policy_type TEXT NOT NULL CHECK (
        policy_type IN ('直接报名', '审核型', '年级限定直接报名')
    ),
    created_at TEXT NOT NULL
);
"""

GUARDS = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_registration_effective
ON registrations(activity_id, student_id) WHERE status IN ('待审核','已通过');

CREATE TRIGGER IF NOT EXISTS registration_capacity_insert
BEFORE INSERT ON registrations
WHEN NEW.status='已通过' AND
 (SELECT COUNT(*) FROM registrations WHERE activity_id=NEW.activity_id AND status='已通过')
 >= (SELECT capacity FROM activities WHERE activity_id=NEW.activity_id)
BEGIN
 SELECT RAISE(ABORT,'campusevent:quota');
END;

CREATE TRIGGER IF NOT EXISTS registration_capacity_update
BEFORE UPDATE OF status ON registrations
WHEN NEW.status='已通过' AND OLD.status!='已通过' AND
 (SELECT COUNT(*) FROM registrations WHERE activity_id=NEW.activity_id AND status='已通过')
 >= (SELECT capacity FROM activities WHERE activity_id=NEW.activity_id)
BEGIN
 SELECT RAISE(ABORT,'campusevent:quota');
END;

CREATE TRIGGER IF NOT EXISTS activity_capacity_update
BEFORE UPDATE OF capacity ON activities
WHEN NEW.capacity < (
 SELECT COUNT(*) FROM registrations WHERE activity_id=OLD.activity_id AND status='已通过'
)
BEGIN
 SELECT RAISE(ABORT,'campusevent:capacity');
END;

CREATE TRIGGER IF NOT EXISTS activity_policy_update
BEFORE UPDATE OF policy_type ON activities
WHEN NEW.policy_type != OLD.policy_type AND EXISTS (
 SELECT 1 FROM registrations WHERE activity_id=OLD.activity_id AND status='待审核'
)
BEGIN
 SELECT RAISE(ABORT,'campusevent:pending');
END;
"""


def _execute_script(conn, script):
    # executescript() may commit implicitly; complete_statement preserves triggers.
    statement = ""
    for line in script.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            conn.execute(statement)
            statement = ""
    if statement.strip():
        raise RuntimeError("数据库迁移 SQL 不完整")


def _validate_integrity(conn):
    if conn.execute("PRAGMA foreign_key_check").fetchall():
        raise RuntimeError("数据库存在外键错误，已拒绝升级，请先修复历史数据")
    if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise RuntimeError("数据库完整性检查失败，已拒绝升级")
    if conn.execute("""
        SELECT 1 FROM activities a WHERE capacity < (
            SELECT COUNT(*) FROM registrations r
            WHERE r.activity_id=a.activity_id AND r.status='已通过'
        ) LIMIT 1
    """).fetchone():
        raise RuntimeError("历史报名已超过容量，已拒绝升级，请人工核实")


def migrate(db_path, schema):
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("BEGIN IMMEDIATE")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > 2:
            raise RuntimeError("数据库版本高于当前程序，禁止降级")
        if version == 2:
            conn.commit()
            return

        old_students = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='students'"
        ).fetchone()
        if old_students:
            columns = {r[1] for r in conn.execute("PRAGMA table_info(students)")}
            if "grade" not in columns:
                conn.execute("""
                    ALTER TABLE students ADD COLUMN grade INTEGER NOT NULL DEFAULT 1
                    CHECK(typeof(grade)='integer' AND grade BETWEEN 1 AND 4)
                """)
                for sid, grade in (("S001", 1), ("S002", 2), ("S003", 3), ("S004", 4)):
                    conn.execute("UPDATE students SET grade=? WHERE student_id=?", (grade, sid))

        old = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='activities'"
        ).fetchone()
        if old and "年级限定直接报名" not in old[0]:
            columns = [r[1] for r in conn.execute("PRAGMA table_info(activities)")]
            expected = ["activity_id", "title", "category", "start_at", "location",
                        "capacity", "policy_type", "created_at"]
            if columns != expected:
                raise RuntimeError("活动表存在未知字段，请人工迁移，未删除数据")
            extras = conn.execute("""
                SELECT sql FROM sqlite_master
                WHERE tbl_name='activities' AND type IN ('index','trigger') AND sql IS NOT NULL
            """).fetchall()
            conn.execute(ACTIVITY_SCHEMA.replace("IF NOT EXISTS activities", "activities_v2"))
            conn.execute("INSERT INTO activities_v2 SELECT * FROM activities")
            conn.execute("DROP TABLE activities")
            conn.execute("ALTER TABLE activities_v2 RENAME TO activities")
            for (sql,) in extras:
                conn.execute(sql)

        _execute_script(conn, schema)
        _execute_script(conn, GUARDS)
        _validate_integrity(conn)
        conn.execute("PRAGMA user_version=2")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
