# -*- coding: utf-8 -*-
"""领域实体：Activity / Student / Registration / Message

实体只描述"数据是什么"与"自身状态如何判断"，不负责业务编排。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time

# ---- 状态与类型常量 ----
STATUS_PENDING = "待审核"
STATUS_APPROVED = "已通过"
STATUS_REJECTED = "已拒绝"
STATUS_CANCELLED = "已取消"
ALL_STATUSES = (STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED, STATUS_CANCELLED)
EFFECTIVE_STATUSES = (STATUS_PENDING, STATUS_APPROVED)

POLICY_DIRECT = "直接报名"
POLICY_REVIEW = "审核型"
POLICY_GRADE_LIMITED = "年级限定直接报名"
ALL_POLICY_TYPES = (POLICY_DIRECT, POLICY_REVIEW, POLICY_GRADE_LIMITED)


def parse_start_at(value: str) -> datetime:
    """Application times are naive Asia/Shanghai wall times, to the minute."""
    if not isinstance(value, str) or len(value) != 16:
        raise ValueError("活动开始时间必须为 YYYY-MM-DD HH:MM")
    parsed = datetime.strptime(value.replace("T", " "), "%Y-%m-%d %H:%M")
    if parsed.strftime("%Y-%m-%d %H:%M") != value.replace("T", " "):
        raise ValueError("活动开始时间格式无效")
    return parsed


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


@dataclass
class Student:
    """学生。使用固定演示账号，无需注册体系。"""

    student_id: str
    name: str
    created_at: str = field(default_factory=_now_iso)
    grade: int = 1

    def __post_init__(self) -> None:
        if type(self.grade) is not int or self.grade not in (1, 2, 3, 4):
            raise ValueError("年级必须为 1～4 的整数")

    def to_dict(self) -> dict:
        return {
            "student_id": self.student_id,
            "name": self.name,
            "created_at": self.created_at,
            "grade": self.grade,
        }


@dataclass
class Activity:
    """校园活动。包含报名方式（policy_type），但不负责判断报名结果。"""

    activity_id: str
    title: str
    category: str
    start_at: str          # YYYY-MM-DD HH:MM
    location: str
    capacity: int
    policy_type: str
    created_at: str = field(default_factory=_now_iso)

    def is_started(self, today: date | datetime | None = None) -> bool:
        """活动是否已开始（业务规则 5：开始后不允许新增报名）。"""
        now = today or datetime.now()
        if not isinstance(now, datetime):
            now = datetime.combine(now, time.min)
        try:
            return parse_start_at(self.start_at) <= now
        except (ValueError, TypeError):
            return True

    def to_dict(self) -> dict:
        return {
            "activity_id": self.activity_id,
            "title": self.title,
            "category": self.category,
            "start_at": self.start_at,
            "location": self.location,
            "capacity": self.capacity,
            "policy_type": self.policy_type,
            "created_at": self.created_at,
        }


@dataclass
class Registration:
    """一次报名记录。状态流转由 RegistrationService 负责。"""

    registration_id: str
    activity_id: str
    student_id: str
    status: str
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def is_effective(self) -> bool:
        """是否为有效报名（业务规则 4：待审核/已通过 视为有效）。"""
        return self.status in EFFECTIVE_STATUSES

    def is_cancellable(self) -> bool:
        """是否可取消（业务规则 5：仅待审核/已通过 可取消）。"""
        return self.status in EFFECTIVE_STATUSES

    def to_dict(self) -> dict:
        return {
            "registration_id": self.registration_id,
            "activity_id": self.activity_id,
            "student_id": self.student_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Message:
    """站内消息。

    related_registration_id + event_type 构成幂等键，防止重复通知。
    """

    message_id: str
    student_id: str
    activity_id: str
    content: str
    created_at: str = field(default_factory=_now_iso)
    is_read: bool = False
    related_registration_id: str = ""
    event_type: str = ""

    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "student_id": self.student_id,
            "activity_id": self.activity_id,
            "content": self.content,
            "created_at": self.created_at,
            "is_read": self.is_read,
            "related_registration_id": self.related_registration_id,
            "event_type": self.event_type,
        }


@dataclass
class MockEmail:
    """A simulated delivery record, never a real SMTP message."""

    email_id: str
    student_id: str
    registration_id: str
    event_type: str
    recipient: str
    subject: str
    content: str
    status: str
    created_at: str = field(default_factory=_now_iso)
    error: str = ""
