# -*- coding: utf-8 -*-
"""Web 层端到端验证：通过 HTTP 接口走完整流程，验证页面与业务串联正确。"""
import os
import sys
import tempfile
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from campusevent.factory import build_app  # noqa: E402
from campusevent.entities import Student  # noqa: E402

fd, db = tempfile.mkstemp(suffix=".db"); os.close(fd); os.unlink(db)
app, container = build_app(db)
container.student_repo.insert(Student(student_id="S001", name="陈倩林"))
container.student_repo.insert(Student(student_id="S002", name="李明轩"))
app.config["TESTING"] = True
c = app.test_client()

ok = lambda m: print(f"  OK  {m}")
fail = []

def check(cond, msg):
    if cond: ok(msg)
    else:
        print(f"  FAIL {msg}"); fail.append(msg)

print("=== W1 首页 ===")
r = c.get("/")
check(r.status_code == 200, "首页返回 200")
check("CampusEvent" in r.get_data(as_text=True), "含品牌名")

print("=== W2 管理员创建直接报名活动 ===")
r = c.post("/admin/activity/new", data={
    "title": "端到端测试活动", "category": "技术讲座", "location": "实验楼",
    "capacity": "2", "policy_type": "直接报名",
    "start_at": (date.today() + timedelta(days=5)).strftime("%Y-%m-%dT10:00"),
}, follow_redirects=True)
body = r.get_data(as_text=True)
check("创建成功" in body, "创建成功提示")
acts = container.activity_service.list_activities("端到端测试活动")
check(len(acts) == 1, "活动已入库")
aid = acts[0].activity_id

print("=== W3 非法输入被拒绝 ===")
# (a) 容量非法（标题合法，隔离出容量这一项校验）
r = c.post("/admin/activity/new", data={
    "title": "容量非法活动", "category": "x", "location": "x", "capacity": "0",
    "policy_type": "直接报名", "start_at": "2026-12-01T10:00",
}, follow_redirects=True)
check("人数上限必须为正整数" in r.get_data(as_text=True), "容量非法被拒绝")
# (b) 标题为空（容量合法，隔离出标题这一项校验）
r = c.post("/admin/activity/new", data={
    "title": "", "category": "x", "location": "x", "capacity": "5",
    "policy_type": "直接报名", "start_at": "2026-12-01T10:00",
}, follow_redirects=True)
check("活动名称不能为空" in r.get_data(as_text=True), "标题为空被拒绝")
# (c) 报名方式非法
r = c.post("/admin/activity/new", data={
    "title": "方式非法活动", "category": "x", "location": "x", "capacity": "5",
    "policy_type": "随便什么", "start_at": "2026-12-01T10:00",
}, follow_redirects=True)
check("报名方式无效" in r.get_data(as_text=True), "报名方式非法被拒绝")

print("=== W4 学生报名 → 已通过 ===")
r = c.post(f"/register/{aid}", data={"student_id": "S001"}, follow_redirects=True)
check("报名成功" in r.get_data(as_text=True), "报名成功提示")
regs = container.registration_repo.list_by_student("S001")
check(len(regs) == 1 and regs[0].status == "已通过", "状态为已通过")

print("=== W5 重复报名被拒绝 ===")
r = c.post(f"/register/{aid}", data={"student_id": "S001"}, follow_redirects=True)
check("重复" in r.get_data(as_text=True), "重复报名被拒")

print("=== W6 站内消息 ===")
r = c.get("/messages?student=S001")
check("已通过" in r.get_data(as_text=True), "消息中心显示通知")

print("=== W7 名额已满 ===")
c.post(f"/register/{aid}", data={"student_id": "S002"}, follow_redirects=True)
r = c.post(f"/register/{aid}", data={"student_id": "S003"}, follow_redirects=True)
check("名额已满" in r.get_data(as_text=True), "第三人报名被拒")

print("=== W8 审核型活动 + 审批 ===")
r = c.post("/admin/activity/new", data={
    "title": "端到端审核活动", "category": "文艺", "location": "中心",
    "capacity": "1", "policy_type": "审核型",
    "start_at": (date.today() + timedelta(days=6)).strftime("%Y-%m-%dT10:00"),
}, follow_redirects=True)
aid2 = container.activity_service.list_activities("端到端审核活动")[0].activity_id
c.post(f"/register/{aid2}", data={"student_id": "S001"}, follow_redirects=True)
r = c.get("/admin")
check("待审核" in r.get_data(as_text=True), "管理后台出现待审核队列")
reg2 = [r for r in container.registration_repo.list_by_activity(aid2)][0]
r = c.post(f"/admin/review/{reg2.registration_id}", data={"approved": "1"}, follow_redirects=True)
check("已批准" in r.get_data(as_text=True), "批准成功")

print("=== W9 统计页数据 ===")
stats = container.activity_service.statistics(aid)
check(stats["approved"] == 2 and stats["remaining"] == 0, f"统计正确 {stats['approved']}/{stats['remaining']}")

print("=== W10 取消报名 ===")
r = c.post(f"/cancel/{regs[0].registration_id}", data={"student_id": "S001"}, follow_redirects=True)
check("已取消报名" in r.get_data(as_text=True), "取消成功")

print("=== W11 删除有有效报名的活动被拒绝 ===")
r = c.post(f"/admin/activity/{aid}/delete", follow_redirects=True)
check("无法删除" in r.get_data(as_text=True), "删除被拒绝")

print("=== W12 活动筛选 ===")
r = c.get("/?keyword=端到端")
check("端到端测试活动" in r.get_data(as_text=True), "筛选命中")
r = c.get("/?keyword=不存在的活动")
check("暂无符合条件" in r.get_data(as_text=True), "筛选无结果")

print()
print(f"总计 12 项端到端验证，失败 {len(fail)} 项")
for f in fail: print("  -", f)
os.unlink(db) if os.path.exists(db) else None
sys.exit(1 if fail else 0)
