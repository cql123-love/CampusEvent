# -*- coding: utf-8 -*-
"""数据库初始化与依赖装配（组装层）。

组装层是唯一知道"具体实现类"的地方：在这里把策略、观察者、仓储、服务组装起来。
"""
from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, timedelta

from .entities import (
    POLICY_DIRECT,
    POLICY_REVIEW,
    STATUS_APPROVED,
    Activity,
    Student,
)
from .events import EventPublisher, MessageNotifier
from .repositories import (
    DEFAULT_DB_PATH,
    ActivityRepository,
    MessageRepository,
    NotificationLogRepository,
    RegistrationRepository,
    StudentRepository,
)
from .services import ActivityService, RegistrationService

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    student_id  TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activities (
    activity_id  TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    category     TEXT NOT NULL,
    start_at     TEXT NOT NULL,
    location     TEXT NOT NULL,
    capacity     INTEGER NOT NULL CHECK (capacity > 0),
    policy_type  TEXT NOT NULL CHECK (policy_type IN ('直接报名', '审核型')),
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS registrations (
    registration_id  TEXT PRIMARY KEY,
    activity_id      TEXT NOT NULL REFERENCES activities(activity_id),
    student_id       TEXT NOT NULL REFERENCES students(student_id),
    status           TEXT NOT NULL CHECK (status IN ('待审核', '已通过', '已拒绝', '已取消')),
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    message_id             TEXT PRIMARY KEY,
    student_id             TEXT NOT NULL REFERENCES students(student_id),
    activity_id            TEXT NOT NULL,
    content                TEXT NOT NULL,
    created_at             TEXT NOT NULL,
    is_read                INTEGER NOT NULL DEFAULT 0,
    related_registration_id TEXT NOT NULL DEFAULT '',
    event_type             TEXT NOT NULL DEFAULT ''
);

-- ★ 防重复通知的幂等键
CREATE UNIQUE INDEX IF NOT EXISTS idx_msg_idempotent
    ON messages(related_registration_id, event_type);

CREATE TABLE IF NOT EXISTS notification_log (
    log_id          TEXT PRIMARY KEY,
    event_type      TEXT NOT NULL,
    student_id      TEXT NOT NULL,
    activity_id     TEXT NOT NULL,
    registration_id TEXT NOT NULL,
    reason          TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
"""


def init_db(db_path: str | None = None) -> None:
    """建表（幂等）。"""
    path = db_path or os.environ.get("CAMPUSEVENT_DB", DEFAULT_DB_PATH)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def seed_demo_data(db_path: str | None = None) -> None:
    """写入演示数据：学生、活动、若干报名与消息。

    仅在数据库为空时执行；云端环境（存在 PORT 等标志）下自动触发。
    """
    path = db_path or os.environ.get("CAMPUSEVENT_DB", DEFAULT_DB_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT COUNT(*) AS c FROM activities").fetchone()
        if row["c"] > 0:
            return
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        today = date.today()

        students = [
            ("S001", "陈倩林"),
            ("S002", "李明轩"),
            ("S003", "王思远"),
            ("S004", "赵雨桐"),
            ("A001", "管理员"),
        ]
        for sid, name in students:
            conn.execute(
                "INSERT OR IGNORE INTO students (student_id, name, created_at) VALUES (?,?,?)",
                (sid, name, now),
            )

        activities = [
            ("act-demo-1", "Python 全栈开发工作坊", "技术讲座",
             (today + timedelta(days=5)).strftime("%Y-%m-%d 14:00"), "实验楼 B301",
             30, POLICY_DIRECT),
            ("act-demo-2", "校园歌手大赛海选", "文艺比赛",
             (today + timedelta(days=12)).strftime("%Y-%m-%d 19:00"), "大学生活动中心",
             20, POLICY_REVIEW),
            ("act-demo-3", "社区支教志愿者招募", "志愿服务",
             (today + timedelta(days=8)).strftime("%Y-%m-%d 09:30"), "附属小学",
             15, POLICY_REVIEW),
            ("act-demo-4", "期末复习资料共享", "学习互助",
             (today + timedelta(days=1)).strftime("%Y-%m-%d 20:00"), "线上",
             50, POLICY_DIRECT),
            ("act-demo-5", "篮球联赛友谊赛", "体育活动",
             (today - timedelta(days=2)).strftime("%Y-%m-%d 16:00"), "东区篮球场",
             12, POLICY_DIRECT),
        ]
        for aid, title, cat, start, loc, cap, ptype in activities:
            conn.execute(
                "INSERT OR IGNORE INTO activities (activity_id, title, category, start_at,"
                " location, capacity, policy_type, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (aid, title, cat, start, loc, cap, ptype, now),
            )

        # 预置几条报名，演示不同状态
        regs = [
            ("reg-demo-1", "act-demo-1", "S002", STATUS_APPROVED),
            ("reg-demo-2", "act-demo-1", "S003", STATUS_APPROVED),
            ("reg-demo-3", "act-demo-2", "S002", "待审核"),
            ("reg-demo-4", "act-demo-4", "S004", STATUS_APPROVED),
        ]
        for rid, aid, sid, status in regs:
            conn.execute(
                "INSERT OR IGNORE INTO registrations (registration_id, activity_id, student_id,"
                " status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                (rid, aid, sid, status, now, now),
            )

        msgs = [
            ("msg-demo-1", "S002", "act-demo-1", "报名成功：「Python 全栈开发工作坊」已通过", "已通过", "reg-demo-1"),
            ("msg-demo-2", "S002", "act-demo-2", "报名已提交：「校园歌手大赛海选」等待管理员审核", "待审核", "reg-demo-3"),
        ]
        for mid, sid, aid, content, etype, rid in msgs:
            conn.execute(
                "INSERT OR IGNORE INTO messages (message_id, student_id, activity_id, content,"
                " created_at, is_read, related_registration_id, event_type)"
                " VALUES (?,?,?,?,?,0,?,?)",
                (mid, sid, aid, content, now, rid, etype),
            )
        conn.commit()
    finally:
        conn.close()


class AppContainer:
    """依赖装配容器。"""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or os.environ.get("CAMPUSEVENT_DB", DEFAULT_DB_PATH)
        init_db(self.db_path)

        self.activity_repo = ActivityRepository(self.db_path)
        self.student_repo = StudentRepository(self.db_path)
        self.registration_repo = RegistrationRepository(self.db_path)
        self.message_repo = MessageRepository(self.db_path)
        self.notification_log_repo = NotificationLogRepository(self.db_path)

        # 观察者装配：发布者只认识 Observer 抽象
        self.publisher = EventPublisher()
        self.notifier = MessageNotifier(self.message_repo, self.notification_log_repo)
        self.publisher.subscribe(self.notifier)

        self.registration_service = RegistrationService(
            self.activity_repo, self.student_repo, self.registration_repo,
            self.message_repo, self.publisher,
        )
        self.activity_service = ActivityService(self.activity_repo, self.registration_repo)


def build_app(db_path: str | None = None):
    """创建 Flask 应用并装配依赖。"""
    from flask import Flask

    from .routes import bp

    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))), "templates"),
        static_folder=os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))), "static"),
    )
    app.config["SECRET_KEY"] = os.environ.get("CAMPUSEVENT_SECRET", "campusevent-dev-secret")
    container = AppContainer(db_path)
    app.config["CONTAINER"] = container
    app.register_blueprint(bp)

    # 演示模式：检测到云端环境时自动写入演示数据
    if any(os.environ.get(k) for k in ("PORT", "RAILWAY_ENVIRONMENT", "RENDER", "DYNO")):
        seed_demo_data(container.db_path)

    return app, container
