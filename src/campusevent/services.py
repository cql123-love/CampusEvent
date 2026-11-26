# -*- coding: utf-8 -*-
"""应用服务层：编排业务流程。

RegistrationService 只做「编排」：
  1. 执行公共规则（活动存在 / 未开始 / 无重复有效报名 / 名额）
  2. ★ 在唯一一处调用策略，决定报名记录的状态
  3. 持久化报名记录（事务提交）
  4. 发布事件 → 观察者写站内通知（在事务之外）
"""
from __future__ import annotations

from datetime import datetime

from .entities import (
    ALL_POLICY_TYPES,
    ALL_STATUSES,
    POLICY_DIRECT,
    POLICY_REVIEW,
    STATUS_APPROVED,
    STATUS_CANCELLED,
    STATUS_PENDING,
    STATUS_REJECTED,
    Activity,
    Message,
    Registration,
    Student,
    new_id,
    parse_start_at,
)
from .errors import BusinessError
from .events import EventPublisher, RegistrationEvent
from .policies import PolicyFactory, RegistrationPolicy


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class RegistrationService:
    """报名 / 取消 / 审批 / 消息 编排。"""

    def __init__(self, activity_repo, student_repo, registration_repo,
                 message_repo, publisher: EventPublisher | None = None,
                 policy_factory=PolicyFactory) -> None:
        self._activity_repo = activity_repo
        self._student_repo = student_repo
        self._registration_repo = registration_repo
        self._message_repo = message_repo
        self._publisher = publisher or EventPublisher()
        self._policy_factory = policy_factory

    # ==================================================================
    # 对外接口
    # ==================================================================
    def submit(self, activity_id: str, student_id: str) -> Registration:
        """学生报名（UC-03）。

        执行顺序至关重要：公共规则全部在前，策略只在决定状态这一步介入。
        """
        activity = self._activity_repo.get(activity_id)
        if activity is None:
            raise BusinessError("活动不存在")

        student = self._student_repo.get(student_id)
        if student is None:
            raise BusinessError("学生不存在")

        # ---- 公共规则（对所有活动类型一致）----
        self._check_common_rules(activity, student)

        # ---- 策略介入：只决定"提交后是什么状态" ----
        policy = self._create_policy(activity.policy_type)
        initial_status = policy.submit(activity, student)

        # ---- 名额占用：仅当策略声明需要配额且状态为已通过 ----
        if policy.requires_quota() and initial_status == STATUS_APPROVED:
            self._check_quota(activity)

        registration = Registration(
            registration_id=new_id("reg"),
            activity_id=activity.activity_id,
            student_id=student.student_id,
            status=initial_status,
            created_at=_now(),
            updated_at=_now(),
        )
        self._registration_repo.insert(registration)

        # ★ 事务已提交（insert 内含 commit），此后才发布事件 —— 通知失败不影响报名
        self._publisher.publish(
            RegistrationEvent(
                event_type=initial_status,
                student_id=student.student_id,
                activity_id=activity.activity_id,
                registration_id=registration.registration_id,
                content=self._build_content(activity, initial_status),
            )
        )
        return registration

    def cancel(self, registration_id: str, student_id: str) -> Registration:
        """学生取消报名（UC-04）。"""
        registration = self._registration_repo.get(registration_id)
        if registration is None:
            raise BusinessError("报名记录不存在")
        if registration.student_id != student_id:
            raise BusinessError("无权操作他人的报名")
        if not registration.is_cancellable():
            raise BusinessError("该报名状态不可取消")

        activity = self._activity_repo.get(registration.activity_id)
        registration.status = STATUS_CANCELLED
        registration.updated_at = _now()
        self._registration_repo.update(registration)

        self._publisher.publish(
            RegistrationEvent(
                event_type=STATUS_CANCELLED,
                student_id=registration.student_id,
                activity_id=registration.activity_id,
                registration_id=registration.registration_id,
                content=f"你已取消报名「{activity.title if activity else registration.activity_id}」",
            )
        )
        return registration

    def review(self, registration_id: str, approved: bool) -> Registration:
        """管理员审批（UC-05）。"""
        registration = self._registration_repo.get(registration_id)
        if registration is None:
            raise BusinessError("报名记录不存在")
        if registration.status != STATUS_PENDING:
            raise BusinessError("该报名不可审批（仅待审核状态可审批）")

        activity = self._activity_repo.get(registration.activity_id)
        if activity is None:
            raise BusinessError("活动不存在")

        # ★ 业务规则 2：批准时**再次检查**剩余名额
        if approved:
            self._check_quota(activity)

        policy = self._create_policy(activity.policy_type)
        new_status = policy.review(activity, registration, approved)

        registration.status = new_status
        registration.updated_at = _now()
        self._registration_repo.update(registration)

        self._publisher.publish(
            RegistrationEvent(
                event_type=new_status,
                student_id=registration.student_id,
                activity_id=registration.activity_id,
                registration_id=registration.registration_id,
                content=self._build_content(activity, new_status),
            )
        )
        return registration

    def list_messages(self, student_id: str) -> list[Message]:
        return self._message_repo.list_by_student(student_id)

    def mark_message_read(self, message_id: str) -> None:
        self._message_repo.mark_read(message_id)

    # ==================================================================
    # 内部：公共规则
    # ==================================================================
    def _check_common_rules(self, activity: Activity, student: Student) -> None:
        """公共规则校验：活动未开始 + 无重复有效报名。"""
        if activity.is_started():
            raise BusinessError("活动已开始，报名通道已关闭")
        if self._registration_repo.has_effective(activity.activity_id, student.student_id):
            raise BusinessError("不可重复报名（同一活动仅允许一条有效报名）")

    def _check_quota(self, activity: Activity) -> None:
        """名额校验（公共规则，不是策略责任）。

        ★ 待审核报名**不占用**名额，只按"已通过"计算（业务规则 3）。
        """
        approved = self._registration_repo.count_approved(activity.activity_id)
        if approved >= activity.capacity:
            raise BusinessError("名额已满")

    def _create_policy(self, policy_type: str) -> RegistrationPolicy:
        """工厂方法：系统中唯一知道具体策略实现的地方。"""
        try:
            return self._policy_factory.create(policy_type)
        except KeyError:
            raise BusinessError("报名方式无效")

    @staticmethod
    def _build_content(activity: Activity, status: str) -> str:
        mapping = {
            STATUS_APPROVED: f"报名成功：「{activity.title}」已通过",
            STATUS_PENDING: f"报名已提交：「{activity.title}」等待管理员审核",
            STATUS_REJECTED: f"报名被拒绝：「{activity.title}」未通过审核",
            STATUS_CANCELLED: f"你已取消报名：「{activity.title}」",
        }
        return mapping.get(status, f"「{activity.title}」状态更新为{status}")


class ActivityService:
    """活动管理编排（UC-01、UC-02、UC-07）。"""

    def __init__(self, activity_repo, registration_repo) -> None:
        self._activity_repo = activity_repo
        self._registration_repo = registration_repo

    @staticmethod
    def _validated_start(value: str) -> str:
        try:
            return parse_start_at(value.strip()).strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError, AttributeError):
            raise BusinessError("活动开始时间无效，请填写有效的日期和时间") from None

    def create_activity(self, data: dict) -> Activity:
        title = (data.get("title") or "").strip()
        if not title:
            raise BusinessError("活动名称不能为空")

        capacity = data.get("capacity")
        try:
            capacity = int(capacity)
        except (TypeError, ValueError):
            raise BusinessError("人数上限必须为正整数")
        if capacity <= 0:
            raise BusinessError("人数上限必须为正整数")

        policy_type = (data.get("policy_type") or "").strip()
        if policy_type not in ALL_POLICY_TYPES:
            raise BusinessError("报名方式无效")

        category = (data.get("category") or "").strip() or "其他"
        location = (data.get("location") or "").strip() or "待定"
        start_at = (data.get("start_at") or "").strip()
        if not start_at:
            raise BusinessError("活动开始时间不能为空")
        start_at = self._validated_start(start_at)

        activity = Activity(
            activity_id=new_id("act"),
            title=title,
            category=category,
            start_at=start_at,
            location=location,
            capacity=capacity,
            policy_type=policy_type,
            created_at=_now(),
        )
        return self._activity_repo.insert(activity)

    def update_activity(self, activity_id: str, data: dict) -> Activity:
        activity = self._activity_repo.get(activity_id)
        if activity is None:
            raise BusinessError("活动不存在")

        if data.get("title") is not None:
            title = data["title"].strip()
            if not title:
                raise BusinessError("活动名称不能为空")
            activity.title = title
        if data.get("capacity") is not None:
            try:
                capacity = int(data["capacity"])
            except (TypeError, ValueError):
                raise BusinessError("人数上限必须为正整数")
            if capacity <= 0:
                raise BusinessError("人数上限必须为正整数")
            approved = self._registration_repo.count_approved(activity_id)
            if capacity < approved:
                raise BusinessError(f"人数上限不能小于已通过报名数（当前已通过 {approved} 人）")
            activity.capacity = capacity
        if data.get("category") is not None:
            activity.category = data["category"].strip() or activity.category
        if data.get("location") is not None:
            activity.location = data["location"].strip() or activity.location
        if data.get("start_at") is not None:
            activity.start_at = self._validated_start(data["start_at"])
        if data.get("policy_type") is not None:
            if data["policy_type"] not in ALL_POLICY_TYPES:
                raise BusinessError("报名方式无效")
            if (data["policy_type"] != activity.policy_type and
                    self._registration_repo.count_by_status(activity_id, STATUS_PENDING)):
                raise BusinessError("存在待审核报名，不能修改报名方式")
            activity.policy_type = data["policy_type"]

        return self._activity_repo.update(activity)

    def delete_activity(self, activity_id: str) -> None:
        """删除活动。

        ★ 设计决策：若存在"待审核"或"已通过"的报名，**拒绝删除并提示**
        （见 design/00_设计决策说明.md 第 3 项取舍）。
        """
        activity = self._activity_repo.get(activity_id)
        if activity is None:
            raise BusinessError("活动不存在")
        if self._registration_repo.list_by_activity(activity_id):
            raise BusinessError("该活动存在报名历史，无法删除；请保留活动以供追溯")
        self._activity_repo.delete(activity_id)

    def list_activities(self, keyword: str = "") -> list[Activity]:
        return self._activity_repo.list(keyword.strip())

    def get_activity(self, activity_id: str) -> Activity | None:
        return self._activity_repo.get(activity_id)

    def statistics(self, activity_id: str) -> dict:
        """统计（UC-07）：已通过数、待审核数、剩余名额。"""
        activity = self._activity_repo.get(activity_id)
        if activity is None:
            raise BusinessError("活动不存在")
        approved = self._registration_repo.count_approved(activity_id)
        pending = self._registration_repo.count_by_status(activity_id, STATUS_PENDING)
        rejected = self._registration_repo.count_by_status(activity_id, STATUS_REJECTED)
        cancelled = self._registration_repo.count_by_status(activity_id, STATUS_CANCELLED)
        return {
            "activity": activity,
            "approved": approved,
            "pending": pending,
            "rejected": rejected,
            "cancelled": cancelled,
            "remaining": max(activity.capacity - approved, 0),
            "capacity": activity.capacity,
        }
