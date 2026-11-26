# -*- coding: utf-8 -*-
"""事件发布与观察者（观察者模式）。

设计要点：
  * 报名事务提交**之后**才 publish，通知失败绝不影响已保存的报名记录
    （业务规则 6：不得导致已合法提交的报名记录无声消失）；
  * 观察者内部异常被捕获并记入 notification_log，不向上抛，
    一个观察者失败也不影响其他观察者；
  * 幂等键 (related_registration_id, event_type) + 唯一索引防重复通知。
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

from .entities import MockEmail, STATUS_APPROVED, STATUS_REJECTED, new_id

logger = logging.getLogger(__name__)


@dataclass
class RegistrationEvent:
    """报名领域事件。"""

    event_type: str                 # 报名成功 / 待审核 / 已通过 / 已拒绝 / 已取消
    student_id: str
    activity_id: str
    registration_id: str
    content: str
    created_at: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )


@runtime_checkable
class Observer(Protocol):
    """观察者接口（ISP：只暴露必要方法）。"""

    def update(self, event: RegistrationEvent) -> None: ...


class EventPublisher:
    """事件发布者（Subject）。只认识 Observer 抽象，不认识具体实现。"""

    def __init__(self) -> None:
        self._observers: list[Observer] = []

    def subscribe(self, observer: Observer) -> None:
        self._observers.append(observer)

    def unsubscribe(self, observer: Observer) -> None:
        if observer in self._observers:
            self._observers.remove(observer)

    def publish(self, event: RegistrationEvent) -> None:
        """分发事件。

        刻意不做异常抛出：通知属于次要副作用，失败不应中断业务流程。
        每个观察者独立 try/except，互不影响。
        """
        for observer in list(self._observers):
            try:
                observer.update(event)
            except Exception:  # noqa: BLE001 —— 观察者失败必须被隔离
                logger.exception("Observer failed for registration %s", event.registration_id)


class MessageNotifier:
    """站内消息观察者：把事件翻译成一条站内消息写入数据库。

    防重复通知：messages 表对 (related_registration_id, event_type) 建唯一索引，
    重复写入时捕获 IntegrityError 静默跳过 —— 这是跨进程/重启都可靠的幂等手段。
    """

    def __init__(self, message_repo, log_repo=None) -> None:
        self._message_repo = message_repo
        self._log_repo = log_repo

    def update(self, event: RegistrationEvent) -> None:
        try:
            self._write_message(event)
        except sqlite3.IntegrityError as exc:
            if ("messages.related_registration_id, messages.event_type" in str(exc)):
                return
            self._log_failure(event, str(exc))
        except Exception as exc:  # noqa: BLE001
            self._log_failure(event, str(exc))

    # ------------------------------------------------------------------
    def _write_message(self, event: RegistrationEvent) -> None:
        from .entities import Message

        message = Message(
            message_id=new_id("msg"),
            student_id=event.student_id,
            activity_id=event.activity_id,
            content=event.content,
            related_registration_id=event.registration_id,
            event_type=event.event_type,
        )
        self._message_repo.insert(message)

    def _log_failure(self, event: RegistrationEvent, reason: str) -> None:
        """通知失败留痕（业务规则 6：失败应留痕）。"""
        if self._log_repo is None:
            return
        try:
            self._log_repo.insert(
                event_type=event.event_type,
                student_id=event.student_id,
                activity_id=event.activity_id,
                registration_id=event.registration_id,
                reason=reason,
                created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
        except Exception:  # noqa: BLE001 —— 留痕失败也不能影响主流程
            logger.exception("Notification log unavailable for %s", event.registration_id)


class MockEmailSender:
    """Simulate delivery; the only observable send is a unique database record."""

    def __init__(self, email_repo, fail: bool = False) -> None:
        self._email_repo = email_repo
        self.fail = fail

    def send_once(self, event: RegistrationEvent, recipient: str,
                  subject: str, content: str) -> None:
        reason = "模拟邮件发送失败（故障注入）" if self.fail else ""
        email = MockEmail(
            email_id=new_id("email"), student_id=event.student_id,
            registration_id=event.registration_id, event_type=event.event_type,
            recipient=recipient, subject=subject, content=content,
            status="FAILED" if reason else "SENT", error=reason,
        )
        inserted = self._email_repo.record_once(email, reason)
        if inserted and reason:
            logger.error("%s: %s", event.registration_id, reason)


class EmailNotifier:
    """An additional observer; never changes the registration result."""

    def __init__(self, sender: MockEmailSender, log_repo=None) -> None:
        self._sender = sender
        self._log_repo = log_repo

    def update(self, event: RegistrationEvent) -> None:
        if event.event_type not in (STATUS_APPROVED, STATUS_REJECTED):
            return
        try:
            self._sender.send_once(
                event, f"{event.student_id}@campusevent.invalid",
                f"CampusEvent 报名结果：{event.event_type}", event.content,
            )
        except Exception as exc:
            logger.exception("模拟邮件记录失败: %s", event.registration_id)
            if self._log_repo is not None:
                try:
                    self._log_repo.insert(
                        event.event_type, event.student_id, event.activity_id,
                        event.registration_id, f"模拟邮件记录失败：{exc}",
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    )
                except Exception:
                    logger.exception("Email failure log unavailable: %s", event.registration_id)
