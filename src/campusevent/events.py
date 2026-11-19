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

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

from .entities import new_id


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
                continue


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
        except sqlite3.IntegrityError:
            # 幂等：同一报名 + 同一事件类型只通知一次
            return
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
            pass
