# -*- coding: utf-8 -*-
"""pytest 夹具：每个测试用独立的临时数据库，互不干扰。"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import date, timedelta

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "src"))

from campusevent.factory import AppContainer  # noqa: E402
from campusevent.repositories import (  # noqa: E402
    ActivityRepository,
    MessageRepository,
    NotificationLogRepository,
    RegistrationRepository,
    StudentRepository,
)
from campusevent.services import ActivityService, RegistrationService  # noqa: E402


@pytest.fixture()
def db_path():
    """每个用例一个独立临时库，测试结束后自动删除。"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)          # 让 sqlite 重新创建
    yield path
    for suffix in ("", "-wal", "-shm"):
        p = path + suffix
        if os.path.exists(p):
            try:
                os.unlink(p)
            except OSError:
                pass


@pytest.fixture()
def container(db_path):
    return AppContainer(db_path)


@pytest.fixture()
def services(container):
    return container.registration_service, container.activity_service


@pytest.fixture()
def repos(container):
    return (container.activity_repo, container.student_repo,
            container.registration_repo, container.message_repo)


@pytest.fixture()
def client(container):
    container.app = None
    from campusevent.factory import build_app
    app, _ = build_app(container.db_path)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture()
def tomorrow():
    return (date.today() + timedelta(days=1)).strftime("%Y-%m-%d 10:00")


@pytest.fixture()
def yesterday():
    return (date.today() - timedelta(days=1)).strftime("%Y-%m-%d 10:00")


def make_student(student_repo, student_id="S001", name="测试学生"):
    from campusevent.entities import Student
    return student_repo.insert(Student(student_id=student_id, name=name))


def make_activity(activity_service, title="测试活动", capacity=2,
                  policy_type="直接报名", start_at=None):
    return activity_service.create_activity({
        "title": title,
        "category": "技术讲座",
        "location": "实验楼",
        "capacity": capacity,
        "policy_type": policy_type,
        "start_at": start_at or (date.today() + timedelta(days=3)).strftime("%Y-%m-%d 10:00"),
    })
