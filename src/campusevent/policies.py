# -*- coding: utf-8 -*-
"""报名策略（策略模式）。

设计要点（见 design/00_设计决策说明.md）：
  * RegistrationPolicy 是稳定抽象，RegistrationService 只依赖它；
  * DirectPolicy / ReviewPolicy 是两个不同实现，各自只回答"状态是什么"；
  * ★ 名额检查（配额）**不属于**策略，而是服务层的公共规则 —— 因为
    业务规则 3 对所有活动类型都成立，若放进策略会导致重复代码并违反 SRP；
  * requires_quota() 预留了"某类活动豁免名额"的扩展点。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from .entities import (
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
    Activity,
    Registration,
    Student,
)


class RegistrationPolicy(ABC):
    """报名规则抽象。变化轴 = 报名方式。"""

    name: str = ""

    @abstractmethod
    def submit(self, activity: Activity, student: Student) -> str:
        """提交报名后返回的初始状态。"""

    @abstractmethod
    def review(self, activity: Activity, registration: Registration, approved: bool) -> str:
        """管理员审批后返回的最终状态。"""

    @abstractmethod
    def requires_quota(self) -> bool:
        """该策略是否占用名额。默认占用；未来的"不限名额"策略可返回 False。"""

    # ------------------------------------------------------------------
    # 下面的辅助方法让子类实现更简洁，避免重复样板代码
    # ------------------------------------------------------------------
    def _submit_passed(self) -> str:
        return STATUS_APPROVED

    def _submit_pending(self) -> str:
        return STATUS_PENDING


class DirectPolicy(RegistrationPolicy):
    """直接报名：名额充足即自动通过（业务规则 1）。"""

    name = "直接报名"

    def submit(self, activity: Activity, student: Student) -> str:
        return self._submit_passed()

    def review(self, activity: Activity, registration: Registration, approved: bool) -> str:
        """直接报名活动不存在审批环节。

        ⚠️ 已知取舍：这在技术上违反里氏替换原则（子类型比父类型更受限）。
        已在 design/05_设计原则说明.md 的 LSP 小节显式记录该取舍与理由。
        """
        raise NotImplementedError("直接报名活动无需审批")

    def requires_quota(self) -> bool:
        return True


class ReviewPolicy(RegistrationPolicy):
    """审核型报名：提交后进入待审核，由管理员决定（业务规则 2）。"""

    name = "审核型"

    def submit(self, activity: Activity, student: Student) -> str:
        return self._submit_pending()

    def review(self, activity: Activity, registration: Registration, approved: bool) -> str:
        return STATUS_APPROVED if approved else STATUS_REJECTED

    def requires_quota(self) -> bool:
        return True


class PolicyFactory:
    """策略工厂 —— 系统中**唯一**知道具体实现类的地方。

    服务层通过工厂获取策略实例，从而依赖抽象而非具体实现（DIP）。
    新增报名方式时：新增一个策略类 + 在这里加一行。
    """

    _registry = {
        "直接报名": DirectPolicy,
        "审核型": ReviewPolicy,
    }

    @classmethod
    def create(cls, policy_type: str) -> RegistrationPolicy:
        impl = cls._registry.get(policy_type)
        if impl is None:
            raise KeyError(policy_type)
        return impl()

    @classmethod
    def registered_types(cls) -> tuple:
        return tuple(cls._registry.keys())
