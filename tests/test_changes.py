"""Teacher CR acceptance, delivery failures and unchanged original behavior."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import sqlite3
from threading import Barrier

import pytest

from campusevent.entities import (
    POLICY_GRADE_LIMITED, STATUS_APPROVED, STATUS_PENDING, STATUS_REJECTED, Student,
)
from campusevent.events import RegistrationEvent
from campusevent.factory import AppContainer, build_app
from campusevent.services import BusinessError
from tests.conftest import make_activity


def student(container, grade, sid=None):
    sid = sid or f"G{grade}"
    return container.student_repo.insert(Student(sid, f"Grade {grade}", grade=grade))


def event_for(reg):
    return RegistrationEvent(
        event_type=reg.status, student_id=reg.student_id,
        activity_id=reg.activity_id, registration_id=reg.registration_id,
        content=f"Result: {reg.status}",
    )


@pytest.mark.parametrize("grade", [2, 3], ids=["CR1-01", "CR1-02"])
def test_grade_allowed(container, grade):
    s = student(container, grade)
    activity = make_activity(container.activity_service, policy_type=POLICY_GRADE_LIMITED)
    reg = container.registration_service.submit(activity.activity_id, s.student_id)
    assert reg.status == STATUS_APPROVED
    assert container.student_repo.get(s.student_id).grade == grade
    assert container.student_repo.get(s.student_id).to_dict()["grade"] == grade
    assert len(container.email_repo.list_by_student(s.student_id)) == 1


@pytest.mark.parametrize("grade", [1, 4], ids=["CR1-03", "CR1-04"])
def test_grade_rejected_with_reason(container, grade):
    s = student(container, grade)
    activity = make_activity(container.activity_service, policy_type=POLICY_GRADE_LIMITED)
    with pytest.raises(BusinessError, match="大二.*大三"):
        container.registration_service.submit(activity.activity_id, s.student_id)
    assert container.registration_repo.list_by_student(s.student_id) == []
    assert container.message_repo.list_by_student(s.student_id) == []
    assert container.email_repo.list_by_student(s.student_id) == []


@pytest.mark.parametrize("grade", [1, 4])
@pytest.mark.parametrize("policy,status", [("直接报名", STATUS_APPROVED), ("审核型", STATUS_PENDING)])
def test_old_policies_ignore_grade(container, grade, policy, status):
    s = student(container, grade)
    activity = make_activity(container.activity_service, policy_type=policy)
    assert container.registration_service.submit(activity.activity_id, s.student_id).status == status


@pytest.mark.parametrize("grade", [0, 5, True, False, "2", 2.0, None])
def test_invalid_grade_is_not_silently_accepted(grade):
    with pytest.raises(ValueError, match="年级"):
        Student("bad", "Bad", grade=grade)


def test_database_rejects_invalid_grade(container):
    with sqlite3.connect(container.db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO students(student_id,name,created_at,grade) VALUES('bad','Bad','now',2.5)"
            )


def test_grade_policy_keeps_common_rules(container):
    a = make_activity(container.activity_service, capacity=1, policy_type=POLICY_GRADE_LIMITED)
    student(container, 2)
    student(container, 3)
    container.registration_service.submit(a.activity_id, "G2")
    with pytest.raises(BusinessError, match="重复"):
        container.registration_service.submit(a.activity_id, "G2")
    with pytest.raises(BusinessError, match="名额已满"):
        container.registration_service.submit(a.activity_id, "G3")
    past = make_activity(
        container.activity_service, policy_type=POLICY_GRADE_LIMITED,
        start_at=(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M"),
    )
    with pytest.raises(BusinessError, match="已开始"):
        container.registration_service.submit(past.activity_id, "G2")


def test_cr2_01_direct_result_has_both_channels(container):
    student(container, 1)
    a = make_activity(container.activity_service)
    reg = container.registration_service.submit(a.activity_id, "G1")
    emails = container.email_repo.list_by_student("G1")
    assert len(container.message_repo.list_by_student("G1")) == len(emails) == 1
    email = emails[0]
    assert email.registration_id == reg.registration_id
    assert email.recipient == "G1@campusevent.invalid"
    assert email.subject and email.content and email.created_at
    assert email.status == "SENT" and not email.error


@pytest.mark.parametrize("approved,status", [(True, STATUS_APPROVED), (False, STATUS_REJECTED)])
def test_cr2_02_review_result(container, approved, status):
    student(container, 2)
    a = make_activity(container.activity_service, policy_type="审核型")
    reg = container.registration_service.submit(a.activity_id, "G2")
    assert container.email_repo.list_by_student("G2") == []
    container.registration_service.review(reg.registration_id, approved)
    emails = container.email_repo.list_by_student("G2")
    assert len(emails) == 1 and emails[0].event_type == status
    assert status in emails[0].subject and status in emails[0].content
    assert len(container.message_repo.list_by_student("G2")) == 2


def test_cr2_03_failure_does_not_rollback_and_is_logged(container):
    student(container, 2)
    container.email_sender.fail = True
    a = make_activity(container.activity_service)
    reg = container.registration_service.submit(a.activity_id, "G2")
    assert container.registration_repo.get(reg.registration_id).status == STATUS_APPROVED
    assert len(container.message_repo.list_by_student("G2")) == 1
    emails = container.email_repo.list_by_student("G2")
    assert len(emails) == 1 and emails[0].status == "FAILED" and emails[0].error
    logs = container.notification_log_repo.list_all()
    assert len(logs) == 1 and logs[0]["registration_id"] == reg.registration_id
    assert "邮件" in logs[0]["reason"]
    container.publisher.publish(event_for(reg))
    assert len(container.email_repo.list_by_student("G2")) == 1
    assert len(container.notification_log_repo.list_all()) == 1


def test_cr2_04_repeated_action_event_and_restart_are_idempotent(container):
    student(container, 2)
    a = make_activity(container.activity_service, policy_type="审核型")
    reg = container.registration_service.submit(a.activity_id, "G2")
    reg = container.registration_service.review(reg.registration_id, True)
    with pytest.raises(BusinessError):
        container.registration_service.review(reg.registration_id, True)
    with pytest.raises(BusinessError):
        container.registration_service.submit(a.activity_id, "G2")
    restarted = AppContainer(container.db_path)
    for _ in range(3):
        restarted.publisher.publish(event_for(reg))
    assert len(restarted.email_repo.list_by_student("G2")) == 1
    assert len(restarted.message_repo.list_by_student("G2")) == 2


def test_cancel_and_reapply_creates_new_result_email(container):
    student(container, 2)
    a = make_activity(container.activity_service, policy_type=POLICY_GRADE_LIMITED)
    first = container.registration_service.submit(a.activity_id, "G2")
    container.registration_service.cancel(first.registration_id, "G2")
    assert len(container.email_repo.list_by_student("G2")) == 1
    second = container.registration_service.submit(a.activity_id, "G2")
    assert second.registration_id != first.registration_id
    assert len(container.email_repo.list_by_student("G2")) == 2


def test_rejected_then_reapply_creates_distinct_events(container):
    student(container, 2)
    a = make_activity(container.activity_service, policy_type="审核型")
    first = container.registration_service.submit(a.activity_id, "G2")
    container.registration_service.review(first.registration_id, False)
    second = container.registration_service.submit(a.activity_id, "G2")
    container.registration_service.review(second.registration_id, True)
    assert len(container.email_repo.list_by_student("G2")) == 2
    assert len(container.registration_repo.list_by_student("G2")) == 2


def test_email_storage_failure_is_logged_to_application(container, monkeypatch, caplog):
    student(container, 2)
    a = make_activity(container.activity_service)

    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("email store unavailable")

    monkeypatch.setattr(container.email_repo, "record_once", broken)
    reg = container.registration_service.submit(a.activity_id, "G2")
    assert container.registration_repo.get(reg.registration_id).status == STATUS_APPROVED
    assert len(container.message_repo.list_by_student("G2")) == 1
    assert "email store unavailable" in caplog.text
    assert container.notification_log_repo.list_all()


def test_observer_failure_does_not_block_email(container, monkeypatch):
    student(container, 2)
    a = make_activity(container.activity_service)
    monkeypatch.setattr(container.message_repo, "insert", lambda m: (_ for _ in ()).throw(
        RuntimeError("message store unavailable")))
    reg = container.registration_service.submit(a.activity_id, "G2")
    assert len(container.email_repo.list_by_student("G2")) == 1
    assert container.registration_repo.get(reg.registration_id).status == STATUS_APPROVED


def test_concurrent_event_delivery_only_records_once(container):
    student(container, 2)
    a = make_activity(container.activity_service)
    reg = container.registration_service.submit(a.activity_id, "G2")
    restarted = AppContainer(container.db_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: restarted.publisher.publish(event_for(reg)), range(12)))
    assert len(restarted.email_repo.list_by_student("G2")) == 1
    assert len(restarted.message_repo.list_by_student("G2")) == 1


def test_web_grade_rejection_email_records_and_identity(container):
    student(container, 1)
    student(container, 2)
    app, c = build_app(container.db_path)
    app.config["TESTING"] = True
    a = make_activity(c.activity_service, policy_type=POLICY_GRADE_LIMITED)
    client = app.test_client()
    assert POLICY_GRADE_LIMITED in client.get("/admin/activity/new").get_data(as_text=True)
    rejected = client.post(f"/register/{a.activity_id}", data={"student_id": "G1"},
                           follow_redirects=True)
    assert "大二" in rejected.get_data(as_text=True)
    accepted = client.post(f"/register/{a.activity_id}", data={"student_id": "G2"},
                           follow_redirects=True)
    assert "已通过" in accepted.get_data(as_text=True)
    page = client.get("/messages?student=G2").get_data(as_text=True)
    assert "G2@campusevent.invalid" in page and "SENT" in page
    assert "student=G2" in page


def test_today_future_time_is_not_started(container):
    a = make_activity(container.activity_service, start_at="2030-01-02 15:00")
    assert not a.is_started(datetime(2030, 1, 2, 14, 59))
    assert a.is_started(datetime(2030, 1, 2, 15, 0))


@pytest.mark.parametrize("value", ["not-a-date", "2030-02-30 10:00", "", "2030-01-01T10:00+08:00"])
def test_invalid_date_rejected_on_create_and_update(container, value):
    data = dict(title="bad date", capacity=1, policy_type="直接报名", start_at=value)
    with pytest.raises(BusinessError, match="时间"):
        container.activity_service.create_activity(data)
    a = make_activity(container.activity_service)
    with pytest.raises(BusinessError, match="时间"):
        container.activity_service.update_activity(a.activity_id, {"start_at": value})


@pytest.mark.parametrize("outcome", ["cancel", "reject"])
def test_historical_registration_blocks_delete_without_500(container, outcome):
    student(container, 2)
    a = make_activity(container.activity_service, policy_type="审核型")
    reg = container.registration_service.submit(a.activity_id, "G2")
    if outcome == "cancel":
        container.registration_service.cancel(reg.registration_id, "G2")
    else:
        container.registration_service.review(reg.registration_id, False)
    with pytest.raises(BusinessError, match="无法删除"):
        container.activity_service.delete_activity(a.activity_id)


def test_pending_registration_prevents_policy_switch(container):
    student(container, 2)
    a = make_activity(container.activity_service, policy_type="审核型")
    reg = container.registration_service.submit(a.activity_id, "G2")
    with pytest.raises(BusinessError, match="待审核"):
        container.activity_service.update_activity(a.activity_id, {"policy_type": "直接报名"})
    assert container.registration_service.review(reg.registration_id, True).status == STATUS_APPROVED


def test_activity_page_can_reapply_after_cancel(container):
    student(container, 2)
    app, c = build_app(container.db_path)
    a = make_activity(c.activity_service)
    reg = c.registration_service.submit(a.activity_id, "G2")
    c.registration_service.cancel(reg.registration_id, "G2")
    page = app.test_client().get(f"/activity/{a.activity_id}?student=G2").get_data(as_text=True)
    assert "立即报名" in page


@pytest.mark.parametrize("same_student", [False, True])
def test_concurrent_signups_preserve_capacity_and_duplicate_rule(container, monkeypatch, same_student):
    student(container, 2)
    student(container, 3)
    a = make_activity(container.activity_service, capacity=1)
    barrier = Barrier(2)
    original = container.registration_service._check_quota

    def checked(activity):
        original(activity)
        barrier.wait(timeout=10)

    monkeypatch.setattr(container.registration_service, "_check_quota", checked)

    def submit(sid):
        try:
            return container.registration_service.submit(a.activity_id, sid).status
        except BusinessError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, ["G2", "G2" if same_student else "G3"]))
    assert sorted(results) == sorted([STATUS_APPROVED, "rejected"])
    assert container.registration_repo.count_approved(a.activity_id) == 1


def test_repeat_stale_review_cannot_overwrite_completed_state(container):
    student(container, 2)
    a = make_activity(container.activity_service, policy_type="审核型")
    reg = container.registration_service.submit(a.activity_id, "G2")
    stale = container.registration_repo.get(reg.registration_id)
    container.registration_service.review(reg.registration_id, True)
    stale.status = STATUS_REJECTED
    with pytest.raises(BusinessError):
        container.registration_repo.update(stale)
    assert container.registration_repo.get(reg.registration_id).status == STATUS_APPROVED
