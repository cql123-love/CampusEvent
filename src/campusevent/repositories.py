# -*- coding: utf-8 -*-
"""仓储层：数据访问。屏蔽 SQLite 细节，为上层提供领域对象。"""
from __future__ import annotations

import os
import sqlite3
from typing import Any

from .entities import (
    EFFECTIVE_STATUSES,
    STATUS_APPROVED,
    Activity,
    Message,
    MockEmail,
    Registration,
    Student,
    new_id,
)
from .errors import BusinessError

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "campusevent.db")


class BaseRepository:
    """仓储基类：统一管理连接与 SQL 执行。"""

    db_path: str = DEFAULT_DB_PATH

    def __init__(self, db_path: str | None = None) -> None:
        if db_path:
            self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        conn = self.connect()
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def query_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: tuple = ()) -> None:
        conn = self.connect()
        try:
            conn.execute(sql, params)
            conn.commit()
        except sqlite3.IntegrityError as exc:
            messages = {
                "campusevent:quota": "名额已满",
                "campusevent:capacity": "人数上限不能小于已通过报名数",
                "campusevent:pending": "存在待审核报名，不能修改报名方式",
            }
            reason = messages.get(str(exc))
            if "registrations.activity_id, registrations.student_id" in str(exc):
                reason = "不可重复报名（同一活动仅允许一条有效报名）"
            if reason:
                raise BusinessError(reason) from exc
            raise
        finally:
            conn.close()


class ActivityRepository(BaseRepository):
    """活动仓储。"""

    def insert(self, activity: Activity) -> Activity:
        self.execute(
            "INSERT INTO activities (activity_id, title, category, start_at, location,"
            " capacity, policy_type, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (activity.activity_id, activity.title, activity.category, activity.start_at,
             activity.location, activity.capacity, activity.policy_type, activity.created_at),
        )
        return activity

    def update(self, activity: Activity) -> Activity:
        self.execute(
            "UPDATE activities SET title=?, category=?, start_at=?, location=?,"
            " capacity=?, policy_type=? WHERE activity_id=?",
            (activity.title, activity.category, activity.start_at, activity.location,
             activity.capacity, activity.policy_type, activity.activity_id),
        )
        return activity

    def delete(self, activity_id: str) -> None:
        try:
            self.execute("DELETE FROM activities WHERE activity_id=?", (activity_id,))
        except sqlite3.IntegrityError as exc:
            raise BusinessError("该活动存在报名历史，无法删除") from exc

    def get(self, activity_id: str) -> Activity | None:
        row = self.query_one("SELECT * FROM activities WHERE activity_id=?", (activity_id,))
        return self._to_entity(row) if row else None

    def list(self, keyword: str = "") -> list[Activity]:
        if keyword:
            rows = self.query(
                "SELECT * FROM activities WHERE title LIKE ? ORDER BY start_at ASC",
                (f"%{keyword}%",),
            )
        else:
            rows = self.query("SELECT * FROM activities ORDER BY start_at ASC")
        return [self._to_entity(r) for r in rows]

    @staticmethod
    def _to_entity(row: sqlite3.Row) -> Activity:
        return Activity(
            activity_id=row["activity_id"],
            title=row["title"],
            category=row["category"],
            start_at=row["start_at"],
            location=row["location"],
            capacity=row["capacity"],
            policy_type=row["policy_type"],
            created_at=row["created_at"],
        )


class StudentRepository(BaseRepository):
    """学生仓储（固定演示账号）。"""

    def insert(self, student: Student) -> Student:
        self.execute(
            "INSERT INTO students (student_id, name, created_at, grade) VALUES (?,?,?,?)",
            (student.student_id, student.name, student.created_at, student.grade),
        )
        return student

    def get(self, student_id: str) -> Student | None:
        row = self.query_one("SELECT * FROM students WHERE student_id=?", (student_id,))
        if not row:
            return None
        return Student(student_id=row["student_id"], name=row["name"],
                       created_at=row["created_at"], grade=row["grade"])

    def list(self) -> list[Student]:
        return [
            Student(student_id=r["student_id"], name=r["name"], created_at=r["created_at"],
                    grade=r["grade"])
            for r in self.query("SELECT * FROM students ORDER BY student_id")
        ]


class RegistrationRepository(BaseRepository):
    """报名仓储。"""

    def insert(self, registration: Registration) -> Registration:
        self.execute(
            "INSERT INTO registrations (registration_id, activity_id, student_id, status,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (registration.registration_id, registration.activity_id, registration.student_id,
             registration.status, registration.created_at, registration.updated_at),
        )
        return registration

    def update(self, registration: Registration) -> Registration:
        conn = self.connect()
        allowed = ("待审核", "已通过") if registration.status == "已取消" else ("待审核",)
        try:
            placeholders = ",".join("?" for _ in allowed)
            cursor = conn.execute(
                "UPDATE registrations SET status=?, updated_at=? WHERE registration_id=?"
                f" AND status IN ({placeholders})",
                (registration.status, registration.updated_at, registration.registration_id, *allowed),
            )
            if cursor.rowcount != 1:
                raise BusinessError("报名状态已改变，请刷新后重试")
            conn.commit()
        except sqlite3.IntegrityError as exc:
            if str(exc) == "campusevent:quota":
                raise BusinessError("名额已满") from exc
            raise
        finally:
            conn.close()
        return registration

    def get(self, registration_id: str) -> Registration | None:
        row = self.query_one(
            "SELECT * FROM registrations WHERE registration_id=?", (registration_id,)
        )
        return self._to_entity(row) if row else None

    def list_by_activity(self, activity_id: str) -> list[Registration]:
        rows = self.query(
            "SELECT * FROM registrations WHERE activity_id=? ORDER BY created_at DESC",
            (activity_id,),
        )
        return [self._to_entity(r) for r in rows]

    def list_by_student(self, student_id: str) -> list[Registration]:
        rows = self.query(
            "SELECT * FROM registrations WHERE student_id=? ORDER BY created_at DESC",
            (student_id,),
        )
        return [self._to_entity(r) for r in rows]

    def list_pending(self) -> list[Registration]:
        rows = self.query(
            "SELECT * FROM registrations WHERE status='待审核' ORDER BY created_at ASC"
        )
        return [self._to_entity(r) for r in rows]

    def has_effective(self, activity_id: str, student_id: str) -> bool:
        """是否存在有效报名（待审核或已通过）—— 业务规则 4。"""
        placeholders = ",".join("?" for _ in EFFECTIVE_STATUSES)
        row = self.query_one(
            f"SELECT 1 FROM registrations WHERE activity_id=? AND student_id=?"
            f" AND status IN ({placeholders}) LIMIT 1",
            (activity_id, student_id, *EFFECTIVE_STATUSES),
        )
        return row is not None

    def count_approved(self, activity_id: str) -> int:
        """已通过报名数 —— 名额只按此计算（业务规则 3）。"""
        row = self.query_one(
            "SELECT COUNT(*) AS c FROM registrations WHERE activity_id=? AND status=?",
            (activity_id, STATUS_APPROVED),
        )
        return int(row["c"]) if row else 0

    def count_by_status(self, activity_id: str, status: str) -> int:
        row = self.query_one(
            "SELECT COUNT(*) AS c FROM registrations WHERE activity_id=? AND status=?",
            (activity_id, status),
        )
        return int(row["c"]) if row else 0

    @staticmethod
    def _to_entity(row: sqlite3.Row) -> Registration:
        return Registration(
            registration_id=row["registration_id"],
            activity_id=row["activity_id"],
            student_id=row["student_id"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class MessageRepository(BaseRepository):
    """站内消息仓储。"""

    def insert(self, message: Message) -> Message:
        self.execute(
            "INSERT INTO messages (message_id, student_id, activity_id, content, created_at,"
            " is_read, related_registration_id, event_type) VALUES (?,?,?,?,?,?,?,?)",
            (message.message_id, message.student_id, message.activity_id, message.content,
             message.created_at, 1 if message.is_read else 0,
             message.related_registration_id, message.event_type),
        )
        return message

    def list_by_student(self, student_id: str) -> list[Message]:
        rows = self.query(
            "SELECT * FROM messages WHERE student_id=? ORDER BY created_at DESC",
            (student_id,),
        )
        return [self._to_entity(r) for r in rows]

    def mark_read(self, message_id: str) -> None:
        self.execute("UPDATE messages SET is_read=1 WHERE message_id=?", (message_id,))

    def exists_once(self, related_registration_id: str, event_type: str) -> bool:
        row = self.query_one(
            "SELECT 1 FROM messages WHERE related_registration_id=? AND event_type=? LIMIT 1",
            (related_registration_id, event_type),
        )
        return row is not None

    @staticmethod
    def _to_entity(row: sqlite3.Row) -> Message:
        return Message(
            message_id=row["message_id"],
            student_id=row["student_id"],
            activity_id=row["activity_id"],
            content=row["content"],
            created_at=row["created_at"],
            is_read=bool(row["is_read"]),
            related_registration_id=row["related_registration_id"],
            event_type=row["event_type"],
        )


class NotificationLogRepository(BaseRepository):
    """通知失败日志（业务规则 6：失败应留痕）。"""

    def insert(self, event_type: str, student_id: str, activity_id: str,
               registration_id: str, reason: str, created_at: str) -> None:
        self.execute(
            "INSERT INTO notification_log (log_id, event_type, student_id, activity_id,"
            " registration_id, reason, created_at) VALUES (?,?,?,?,?,?,?)",
            (new_id("log"), event_type,
             student_id, activity_id, registration_id, reason, created_at),
        )

    def list_all(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.query(
            "SELECT * FROM notification_log ORDER BY created_at DESC"
        )]


class MockEmailRepository(BaseRepository):
    """Atomic, persistent simulated delivery and failure logging."""

    def record_once(self, email: MockEmail, failure_reason: str = "") -> bool:
        conn = self.connect()
        try:
            with conn:
                inserted = conn.execute(
                    """INSERT INTO mock_emails (
                        email_id,student_id,registration_id,event_type,recipient,subject,
                        content,status,created_at,error
                    ) VALUES (?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(registration_id,event_type) DO NOTHING""",
                    (email.email_id, email.student_id, email.registration_id, email.event_type,
                     email.recipient, email.subject, email.content, email.status,
                     email.created_at, email.error),
                ).rowcount == 1
                if inserted and failure_reason:
                    conn.execute(
                        """INSERT INTO notification_log
                        (log_id,event_type,student_id,activity_id,registration_id,reason,created_at)
                        SELECT ?,?,?,activity_id,?,?,? FROM registrations WHERE registration_id=?""",
                        (new_id("log"), email.event_type, email.student_id, email.registration_id,
                         failure_reason, email.created_at, email.registration_id),
                    )
            return inserted
        finally:
            conn.close()

    def list_by_student(self, student_id: str) -> list[MockEmail]:
        return [MockEmail(**dict(row)) for row in self.query(
            "SELECT * FROM mock_emails WHERE student_id=? ORDER BY created_at DESC,email_id",
            (student_id,),
        )]
