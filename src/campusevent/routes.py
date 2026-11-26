# -*- coding: utf-8 -*-
"""表现层：Flask 蓝图。只做参数解析与模板渲染，不含业务判断。"""
from __future__ import annotations

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from .entities import ALL_POLICY_TYPES, ALL_STATUSES, STATUS_PENDING
from flask import abort
from .services import BusinessError

bp = Blueprint("main", __name__)


def _container():
    return current_app.config["CONTAINER"]


def _current_student_id() -> str:
    """演示用：固定学生账号（指导书允许固定演示账号，无需注册体系）。"""
    return request.args.get("student", request.form.get("student", "S001")) or "S001"


# ======================================================================
# 学生端
# ======================================================================
@bp.route("/")
def index():
    """活动列表 + 名称筛选（UC-02）。"""
    c = _container()
    keyword = request.args.get("keyword", "").strip()
    student_id = _current_student_id()
    activities = c.activity_service.list_activities(keyword)

    my_regs = {}
    for reg in c.registration_repo.list_by_student(student_id):
        if reg.activity_id not in my_regs or reg.is_effective():
            my_regs[reg.activity_id] = reg
    items = []
    for activity in activities:
        stats = c.activity_service.statistics(activity.activity_id)
        items.append({
            "activity": activity,
            "stats": stats,
            "my_registration": my_regs.get(activity.activity_id),
        })

    return render_template(
        "index.html",
        items=items,
        keyword=keyword,
        student_id=student_id,
        students=c.student_repo.list(),
        policy_types=ALL_POLICY_TYPES,
    )


@bp.route("/activity/<activity_id>")
def activity_detail(activity_id):
    """活动详情（UC-02 扩展 / UC-07）。"""
    c = _container()
    student_id = _current_student_id()
    if c.activity_repo.get(activity_id) is None:
        abort(404)
    stats = c.activity_service.statistics(activity_id)
    my_regs = [r for r in c.registration_repo.list_by_student(student_id)
               if r.activity_id == activity_id]
    return render_template(
        "activity.html",
        stats=stats,
        student_id=student_id,
        my_registrations=my_regs,
        effective_registrations=[r for r in my_regs if r.is_effective()],
        registrations=c.registration_repo.list_by_activity(activity_id),
        students=c.student_repo.list(),
    )


@bp.route("/register/<activity_id>", methods=["POST"])
def register(activity_id):
    """学生报名（UC-03）。"""
    c = _container()
    student_id = request.form.get("student_id", "S001")
    try:
        c.registration_service.submit(activity_id, student_id)
        flash("报名成功", "ok")
    except BusinessError as exc:
        flash(str(exc), "err")
    return redirect(url_for("main.activity_detail", activity_id=activity_id,
                            student=student_id))


@bp.route("/cancel/<registration_id>", methods=["POST"])
def cancel(registration_id):
    """学生取消报名（UC-04）。"""
    c = _container()
    student_id = request.form.get("student_id", "S001")
    try:
        c.registration_service.cancel(registration_id, student_id)
        flash("已取消报名", "ok")
    except BusinessError as exc:
        flash(str(exc), "err")
    return redirect(request.referrer or url_for("main.index", student=student_id))


@bp.route("/messages")
def messages():
    """站内消息中心（UC-06）。"""
    c = _container()
    student_id = _current_student_id()
    return render_template(
        "messages.html",
        messages=c.registration_service.list_messages(student_id),
        emails=c.email_repo.list_by_student(student_id),
        student_id=student_id,
        students=c.student_repo.list(),
    )


@bp.route("/message/<message_id>/read", methods=["POST"])
def read_message(message_id):
    c = _container()
    c.registration_service.mark_message_read(message_id)
    return redirect(url_for("main.messages", student=_current_student_id()))


# ======================================================================
# 管理端
# ======================================================================
@bp.route("/admin")
def admin_home():
    """管理首页：活动列表 + 待审核队列。"""
    c = _container()
    keyword = request.args.get("keyword", "").strip()
    return render_template(
        "admin.html",
        activities=c.activity_service.list_activities(keyword),
        pending=c.registration_repo.list_pending(),
        keyword=keyword,
        policy_types=ALL_POLICY_TYPES,
        students=c.student_repo.list(),
    )


@bp.route("/admin/activity/new", methods=["GET", "POST"])
def admin_activity_new():
    """创建活动（UC-01）。"""
    c = _container()
    if request.method == "POST":
        try:
            activity = c.activity_service.create_activity(request.form.to_dict())
            flash(f"活动「{activity.title}」创建成功", "ok")
            return redirect(url_for("main.admin_home"))
        except BusinessError as exc:
            flash(str(exc), "err")
    return render_template("activity_form.html",
                           activity=None, policy_types=ALL_POLICY_TYPES)


@bp.route("/admin/activity/<activity_id>/edit", methods=["GET", "POST"])
def admin_activity_edit(activity_id):
    """编辑活动（UC-01 扩展）。"""
    c = _container()
    activity = c.activity_service.get_activity(activity_id)
    if activity is None:
        flash("活动不存在", "err")
        return redirect(url_for("main.admin_home"))
    if request.method == "POST":
        try:
            c.activity_service.update_activity(activity_id, request.form.to_dict())
            flash("活动已更新", "ok")
            return redirect(url_for("main.admin_home"))
        except BusinessError as exc:
            flash(str(exc), "err")
    return render_template("activity_form.html",
                           activity=activity, policy_types=ALL_POLICY_TYPES)


@bp.route("/admin/activity/<activity_id>/delete", methods=["POST"])
def admin_activity_delete(activity_id):
    """删除活动（有有效报名则拒绝）。"""
    c = _container()
    try:
        c.activity_service.delete_activity(activity_id)
        flash("活动已删除", "ok")
    except BusinessError as exc:
        flash(str(exc), "err")
    return redirect(url_for("main.admin_home"))


@bp.route("/admin/review/<registration_id>", methods=["POST"])
def admin_review(registration_id):
    """管理员审批（UC-05）。"""
    c = _container()
    approved = request.form.get("approved") == "1"
    try:
        reg = c.registration_service.review(registration_id, approved)
        flash("已批准该报名" if approved else "已拒绝该报名", "ok")
    except BusinessError as exc:
        flash(str(exc), "err")
    return redirect(request.referrer or url_for("main.admin_home"))
