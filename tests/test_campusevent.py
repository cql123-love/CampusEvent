# -*- coding: utf-8 -*-
"""C1 ~ C10 核心验收用例（指导书 3.5 节），另加若干边界补充用例。

每条用例对应指导书原文的输入/操作与预期结果。
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from campusevent.entities import (  # noqa: E402
    STATUS_APPROVED,
    STATUS_CANCELLED,
    STATUS_PENDING,
    STATUS_REJECTED,
    Activity,
    Registration,
    Student,
)
from campusevent.events import EventPublisher, MessageNotifier  # noqa: E402
from campusevent.services import BusinessError  # noqa: E402
from tests.conftest import make_activity, make_student  # noqa: E402


# ======================================================================
# C1  管理员创建直接报名活动，容量2
# ======================================================================
def test_c1_create_direct_activity(services, repos):
    reg_svc, act_svc = services
    activity_repo, student_repo, *_ = repos

    make_student(student_repo)
    activity = make_activity(act_svc, title="Python 工作坊", capacity=2,
                             policy_type="直接报名")

    assert activity.capacity == 2
    assert activity.policy_type == "直接报名"
    assert activity_repo.get(activity.activity_id) is not None
    # 可供学生报名：活动未开始
    assert activity.is_started() is False


# ======================================================================
# C2  学生A报名直接报名活动 → 直接变为"已通过"并通知
# ======================================================================
def test_c2_direct_signup_auto_approved(services, repos):
    reg_svc, act_svc = services
    activity_repo, student_repo, registration_repo, message_repo = repos

    make_student(student_repo, "S001", "学生A")
    activity = make_activity(act_svc, capacity=2, policy_type="直接报名")

    reg = reg_svc.submit(activity.activity_id, "S001")

    assert reg.status == STATUS_APPROVED
    assert registration_repo.get(reg.registration_id).status == STATUS_APPROVED
    # 产生了站内通知
    msgs = message_repo.list_by_student("S001")
    assert len(msgs) == 1
    assert "已通过" in msgs[0].content


# ======================================================================
# C3  学生A再次提交相同活动报名 → 拒绝重复有效报名
# ======================================================================
def test_c3_duplicate_signup_rejected(services, repos):
    reg_svc, act_svc = services
    _, student_repo, registration_repo, _ = repos

    make_student(student_repo, "S001", "学生A")
    activity = make_activity(act_svc, capacity=5, policy_type="直接报名")
    reg_svc.submit(activity.activity_id, "S001")

    with pytest.raises(BusinessError) as exc:
        reg_svc.submit(activity.activity_id, "S001")
    assert "重复" in str(exc.value)
    # 数据库中仍只有一条有效报名
    assert len(registration_repo.list_by_activity(activity.activity_id)) == 1


def test_c3b_cancelled_then_reapply_allowed(services, repos):
    """边界补充：已取消的记录保留历史，允许再次申请（业务规则 4）。"""
    reg_svc, act_svc = services
    _, student_repo, registration_repo, _ = repos

    make_student(student_repo, "S001", "学生A")
    activity = make_activity(act_svc, capacity=5, policy_type="直接报名")
    reg = reg_svc.submit(activity.activity_id, "S001")
    reg_svc.cancel(reg.registration_id, "S001")

    # 再次申请应成功，且历史记录保留（共 2 条）
    reg2 = reg_svc.submit(activity.activity_id, "S001")
    assert reg2.status == STATUS_APPROVED
    assert len(registration_repo.list_by_activity(activity.activity_id)) == 2


# ======================================================================
# C4  学生B报名同一活动，名额已满后学生C再报名
# ======================================================================
def test_c4_quota_full_rejects_third_student(services, repos):
    reg_svc, act_svc = services
    _, student_repo, registration_repo, _ = repos

    make_student(student_repo, "S001", "学生A")
    make_student(student_repo, "S002", "学生B")
    make_student(student_repo, "S003", "学生C")
    activity = make_activity(act_svc, capacity=2, policy_type="直接报名")

    # 先让 A、B 占满 2 个名额
    reg_a = reg_svc.submit(activity.activity_id, "S001")
    reg_b = reg_svc.submit(activity.activity_id, "S002")
    assert reg_a.status == STATUS_APPROVED
    assert reg_b.status == STATUS_APPROVED
    assert registration_repo.count_approved(activity.activity_id) == 2

    # 名额已满后学生C再报名 → 失败
    with pytest.raises(BusinessError) as exc:
        reg_svc.submit(activity.activity_id, "S003")
    assert "名额已满" in str(exc.value)
    # C 没有产生报名记录
    assert len(registration_repo.list_by_activity(activity.activity_id)) == 2


# ======================================================================
# C5  创建审核型活动，学生A申请 → 状态为"待审核"
# ======================================================================
def test_c5_review_signup_pending(services, repos):
    reg_svc, act_svc = services
    _, student_repo, registration_repo, message_repo = repos

    make_student(student_repo, "S001", "学生A")
    activity = make_activity(act_svc, capacity=10, policy_type="审核型")

    reg = reg_svc.submit(activity.activity_id, "S001")
    assert reg.status == STATUS_PENDING
    assert registration_repo.get(reg.registration_id).status == STATUS_PENDING
    # 待审核暂不占用名额（业务规则 3）
    assert registration_repo.count_approved(activity.activity_id) == 0
    # 但会产生"待审核"通知
    msgs = message_repo.list_by_student("S001")
    assert len(msgs) == 1
    assert "待审核" in msgs[0].content or "等待" in msgs[0].content


# ======================================================================
# C6  管理员批准A的待审核报名 → 变为"已通过"且生成通知
# ======================================================================
def test_c6_admin_approve_pending(services, repos):
    reg_svc, act_svc = services
    _, student_repo, _, message_repo = repos

    make_student(student_repo, "S001", "学生A")
    activity = make_activity(act_svc, capacity=10, policy_type="审核型")
    reg = reg_svc.submit(activity.activity_id, "S001")

    result = reg_svc.review(reg.registration_id, approved=True)
    assert result.status == STATUS_APPROVED

    msgs = message_repo.list_by_student("S001")
    assert len(msgs) == 2                      # 待审核 + 已通过
    assert any("已通过" in m.content for m in msgs)


# ======================================================================
# C7  管理员拒绝另一待审核报名 → 变为"已拒绝"且生成通知
# ======================================================================
def test_c7_admin_reject_pending(services, repos):
    reg_svc, act_svc = services
    _, student_repo, _, message_repo = repos

    make_student(student_repo, "S002", "学生B")
    activity = make_activity(act_svc, capacity=10, policy_type="审核型")
    reg = reg_svc.submit(activity.activity_id, "S002")

    result = reg_svc.review(reg.registration_id, approved=False)
    assert result.status == STATUS_REJECTED

    msgs = message_repo.list_by_student("S002")
    assert len(msgs) == 2
    assert any("拒绝" in m.content for m in msgs)


# ======================================================================
# C8  批准操作时容量已满 → 批准失败，不超出人数上限
# ======================================================================
def test_c8_approve_when_quota_full_fails(services, repos):
    """指导书 C8：批准操作时容量已满 → 批准失败，不超出人数上限。

    场景：审核型活动容量 1；A、B 均申请（待审核不占名额）；
         管理员先批准 A（占满名额）；再批准 B → 必须失败，B 保持待审核。
    """
    reg_svc, act_svc = services
    _, student_repo, registration_repo, message_repo = repos

    make_student(student_repo, "S001", "学生A")
    make_student(student_repo, "S002", "学生B")
    activity = make_activity(act_svc, capacity=1, policy_type="审核型")

    reg_a = reg_svc.submit(activity.activity_id, "S001")
    reg_b = reg_svc.submit(activity.activity_id, "S002")
    assert reg_a.status == STATUS_PENDING
    assert reg_b.status == STATUS_PENDING

    # 批准 A：名额充足，批准成功
    reg_svc.review(reg_a.registration_id, approved=True)
    assert registration_repo.count_approved(activity.activity_id) == 1

    # ★ 此时名额已满，批准 B 必须失败
    with pytest.raises(BusinessError) as exc:
        reg_svc.review(reg_b.registration_id, approved=True)
    assert "名额已满" in str(exc.value)
    # 状态保持待审核，且不超出人数上限
    assert registration_repo.get(reg_b.registration_id).status == STATUS_PENDING
    assert registration_repo.count_approved(activity.activity_id) == 1
    # B 没有收到"已通过"通知
    assert not any("已通过" in m.content for m in message_repo.list_by_student("S002"))


# ======================================================================
# C9  学生取消待审核或已通过报名 → 状态"已取消"，统计同步变化
# ======================================================================
def test_c9_cancel_pending_and_approved(services, repos):
    reg_svc, act_svc = services
    _, student_repo, registration_repo, message_repo = repos

    make_student(student_repo, "S001", "学生A")
    make_student(student_repo, "S002", "学生B")

    # (a) 取消"已通过"
    act1 = make_activity(act_svc, title="活动一", capacity=5, policy_type="直接报名")
    reg1 = reg_svc.submit(act1.activity_id, "S001")
    assert registration_repo.count_approved(act1.activity_id) == 1
    reg_svc.cancel(reg1.registration_id, "S001")
    assert registration_repo.get(reg1.registration_id).status == STATUS_CANCELLED
    # 统计同步变化：已通过数减少 → 剩余名额回升
    stats = act_svc.statistics(act1.activity_id)
    assert stats["approved"] == 0
    assert stats["remaining"] == 5

    # (b) 取消"待审核"
    act2 = make_activity(act_svc, title="活动二", capacity=5, policy_type="审核型")
    reg2 = reg_svc.submit(act2.activity_id, "S002")
    assert reg2.status == STATUS_PENDING
    reg_svc.cancel(reg2.registration_id, "S002")
    assert registration_repo.get(reg2.registration_id).status == STATUS_CANCELLED

    # 产生了取消通知
    assert any("取消" in m.content for m in message_repo.list_by_student("S001"))


def test_c9b_cannot_cancel_others_registration(services, repos):
    """边界补充：不能取消他人的报名。"""
    reg_svc, act_svc = services
    _, student_repo, _, _ = repos
    make_student(student_repo, "S001", "学生A")
    make_student(student_repo, "S002", "学生B")
    activity = make_activity(act_svc, capacity=5, policy_type="直接报名")
    reg = reg_svc.submit(activity.activity_id, "S001")

    with pytest.raises(BusinessError) as exc:
        reg_svc.cancel(reg.registration_id, "S002")
    assert "无权" in str(exc.value)


# ======================================================================
# C10 重新启动服务，查询活动、报名、通知 → 数据仍一致
# ======================================================================
def test_c10_persistence_across_restart(container, repos):
    """模拟重启：用同一个数据库文件重新构建应用容器。"""
    from campusevent.factory import AppContainer

    activity_repo, student_repo, registration_repo, message_repo = repos
    make_student(student_repo, "S001", "学生A")
    activity = make_activity(container.activity_service, capacity=3,
                             policy_type="直接报名")
    reg = container.registration_service.submit(activity.activity_id, "S001")

    # ★ 重新创建容器（相当于重启服务）
    restarted = AppContainer(container.db_path)

    assert restarted.activity_repo.get(activity.activity_id) is not None
    assert restarted.registration_repo.get(reg.registration_id) is not None
    assert restarted.registration_repo.get(reg.registration_id).status == STATUS_APPROVED
    msgs = restarted.message_repo.list_by_student("S001")
    assert len(msgs) == 1


# ======================================================================
# 边界补充用例（不在指导书 C1~C10 内，但属于必须正确处理的规则）
# ======================================================================
def test_b1_activity_started_blocks_signup(services, repos):
    """边界补充：活动开始后不允许新增报名（业务规则 5）。"""
    reg_svc, act_svc = services
    _, student_repo, registration_repo, _ = repos
    make_student(student_repo, "S001", "学生A")
    past = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d 10:00")
    activity = make_activity(act_svc, capacity=5, policy_type="直接报名", start_at=past)

    with pytest.raises(BusinessError) as exc:
        reg_svc.submit(activity.activity_id, "S001")
    assert "已开始" in str(exc.value)
    assert len(registration_repo.list_by_activity(activity.activity_id)) == 0


def test_b2_invalid_activity_input_rejected(services, repos):
    """边界补充：活动名称为空 / 容量非正整数 / 报名方式非法 → 拒绝创建。"""
    reg_svc, act_svc = services
    for bad in (
        {"title": "", "capacity": 5, "policy_type": "直接报名"},
        {"title": "x", "capacity": 0, "policy_type": "直接报名"},
        {"title": "x", "capacity": -3, "policy_type": "直接报名"},
        {"title": "x", "capacity": "abc", "policy_type": "直接报名"},
        {"title": "x", "capacity": 5, "policy_type": "随便什么"},
    ):
        bad.setdefault("category", "讲座")
        bad.setdefault("location", "地点")
        bad.setdefault("start_at", "2026-12-01 10:00")
        with pytest.raises(BusinessError):
            act_svc.create_activity(bad)


def test_b3_delete_activity_with_effective_registration_rejected(services, repos):
    """边界补充：存在有效报名时拒绝删除活动（设计决策第 3 项）。"""
    reg_svc, act_svc = services
    _, student_repo, _, _ = repos
    make_student(student_repo, "S001", "学生A")
    activity = make_activity(act_svc, capacity=5, policy_type="直接报名")
    reg_svc.submit(activity.activity_id, "S001")

    with pytest.raises(BusinessError) as exc:
        act_svc.delete_activity(activity.activity_id)
    assert "无法删除" in str(exc.value)


def test_b4_delete_activity_without_registration_ok(services, repos):
    """边界补充：无有效报名时可以删除。"""
    reg_svc, act_svc = services
    activity = make_activity(act_svc, capacity=5, policy_type="直接报名")
    act_svc.delete_activity(activity.activity_id)
    assert act_svc.get_activity(activity.activity_id) is None


def test_b5_notification_failure_does_not_lose_registration(container, repos):
    """★ 关键边界：通知失败**不得**导致已合法提交的报名记录消失（业务规则 6）。"""
    activity_repo, student_repo, registration_repo, message_repo = repos
    make_student(student_repo, "S001", "学生A")
    activity = make_activity(container.activity_service, capacity=5,
                             policy_type="直接报名")

    # 注入一个必定抛异常的观察者，模拟通知渠道故障
    class BrokenNotifier:
        def update(self, event):
            raise RuntimeError("通知服务不可用")

    publisher = EventPublisher()
    publisher.subscribe(BrokenNotifier())
    broken_msg_repo = _ExplodingMessageRepo()
    publisher.subscribe(MessageNotifier(broken_msg_repo, container.notification_log_repo))

    from campusevent.services import RegistrationService
    svc = RegistrationService(activity_repo, student_repo, registration_repo,
                              message_repo, publisher)

    reg = svc.submit(activity.activity_id, "S001")

    # ★ 报名记录必须仍然存在且状态正确
    assert registration_repo.get(reg.registration_id) is not None
    assert registration_repo.get(reg.registration_id).status == STATUS_APPROVED
    # 通知失败已留痕（消息仓库写入失败被捕获并记录）
    logs = container.notification_log_repo.list_all()
    assert len(logs) >= 1
    assert "失败" in logs[0]["reason"]
    assert logs[0]["registration_id"] == reg.registration_id


class _ExplodingMessageRepo:
    """模拟消息仓库写入失败。"""

    def insert(self, message):
        raise RuntimeError("数据库写入失败")

    def list_by_student(self, student_id):
        return []

    def mark_read(self, message_id):
        pass

    def exists_once(self, related_id, event_type):
        return False


def test_b6_no_duplicate_notification_on_repeat_publish(services, repos):
    """★ 关键边界：同一报名 + 同一事件类型只产生一条通知（幂等）。"""
    from campusevent.events import RegistrationEvent
    reg_svc, act_svc = services
    _, student_repo, _, message_repo = repos
    make_student(student_repo, "S001", "学生A")
    activity = make_activity(act_svc, capacity=5, policy_type="直接报名")
    reg = reg_svc.submit(activity.activity_id, "S001")

    assert len(message_repo.list_by_student("S001")) == 1
    # 重复发布同一事件 → 幂等，不产生第二条
    container_publisher = reg_svc._publisher
    container_publisher.publish(RegistrationEvent(
        event_type=STATUS_APPROVED, student_id="S001",
        activity_id=activity.activity_id, registration_id=reg.registration_id,
        content="重复投递",
    ))
    assert len(message_repo.list_by_student("S001")) == 1


def test_b7_pending_does_not_occupy_quota(services, repos):
    """★ 关键边界：待审核报名不占用名额（业务规则 3）。"""
    reg_svc, act_svc = services
    _, student_repo, registration_repo, _ = repos
    for i in range(1, 6):
        make_student(student_repo, f"S00{i}", f"学生{i}")
    activity = make_activity(act_svc, capacity=2, policy_type="审核型")

    for i in range(1, 6):
        reg_svc.submit(activity.activity_id, f"S00{i}")   # 5 个待审核

    stats = act_svc.statistics(activity.activity_id)
    assert stats["pending"] == 5
    assert stats["approved"] == 0
    assert stats["remaining"] == 2      # 名额未被占用


def test_b8_review_policy_direct_policy_status(services, repos):
    """策略行为单元测试：无需数据库即可验证。"""
    from campusevent.policies import PolicyFactory
    make_student(None, "S001") if False else None

    _, student_repo, _, _ = repos
    student = make_student(student_repo, "S001", "学生A")
    activity = Activity(activity_id="a1", title="活动", category="讲座",
                        start_at="2026-12-01 10:00", location="地点",
                        capacity=10, policy_type="直接报名")
    reg = Registration(registration_id="r1", activity_id="a1",
                       student_id="S001", status=STATUS_PENDING)

    direct = PolicyFactory.create("直接报名")
    review = PolicyFactory.create("审核型")

    assert direct.submit(activity, student) == STATUS_APPROVED
    assert review.submit(activity, student) == STATUS_PENDING
    assert review.review(activity, reg, True) == STATUS_APPROVED
    assert review.review(activity, reg, False) == STATUS_REJECTED
    # 直接报名不支持审批
    with pytest.raises(NotImplementedError):
        direct.review(activity, reg, True)


def test_b9_service_depends_on_policy_abstraction(services, repos):
    """边界补充：服务层不硬编码活动类型判断，策略由工厂注入。"""
    from campusevent.policies import DirectPolicy, ReviewPolicy
    reg_svc, act_svc = services
    _, student_repo, _, _ = repos
    make_student(student_repo, "S001", "学生A")

    seen = []

    class SpyFactory:
        @staticmethod
        def create(policy_type):
            seen.append(policy_type)
            return ReviewPolicy() if policy_type == "审核型" else DirectPolicy()

    reg_svc._policy_factory = SpyFactory
    activity = make_activity(act_svc, capacity=5, policy_type="审核型")
    reg = reg_svc.submit(activity.activity_id, "S001")

    assert seen == ["审核型"]        # 服务层通过工厂取策略
    assert reg.status == STATUS_PENDING


def test_b10_activity_list_filter_by_keyword(services, repos):
    """边界补充：按名称筛选活动（UC-02 / P2-F02）。"""
    reg_svc, act_svc = services
    make_activity(act_svc, title="Python 工作坊", capacity=5, policy_type="直接报名")
    make_activity(act_svc, title="篮球友谊赛", capacity=5, policy_type="直接报名")

    assert len(act_svc.list_activities("")) == 2
    assert len(act_svc.list_activities("Python")) == 1
    assert act_svc.list_activities("Python")[0].title == "Python 工作坊"
    assert len(act_svc.list_activities("不存在的关键字")) == 0
