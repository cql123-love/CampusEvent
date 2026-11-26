# -*- coding: utf-8 -*-
"""写入演示数据（手动执行）。

用途：在没有 PORT/RENDER 等云环境标志的平台上（如 PythonAnywhere），
      首次部署后用本脚本一次性写入演示数据。

用法：
    python seed.py            # 数据库为空时才写入
    python seed.py --force    # 清空后重新写入

说明：仅影响演示数据，不改变任何业务逻辑；正式使用时可忽略本脚本。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from campusevent.factory import seed_demo_data  # noqa: E402
from campusevent.repositories import DEFAULT_DB_PATH  # noqa: E402

db_path = os.environ.get("CAMPUSEVENT_DB", DEFAULT_DB_PATH)

if "--force" in sys.argv:
    import sqlite3

    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='mock_emails'").fetchone():
            conn.execute("DELETE FROM mock_emails")
        conn.execute("DELETE FROM notification_log")
        conn.execute("DELETE FROM messages")
        conn.execute("DELETE FROM registrations")
        conn.execute("DELETE FROM activities")
        conn.commit()
        conn.close()
        print(f"已清空原有数据：{db_path}")

seed_demo_data(db_path)

import sqlite3  # noqa: E402

conn = sqlite3.connect(db_path)
acts = conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
sts = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
regs = conn.execute("SELECT COUNT(*) FROM registrations").fetchone()[0]
msgs = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
conn.close()

print(f"数据库：{db_path}")
print(f"演示数据：活动 {acts} 个 / 学生 {sts} 位 / 报名 {regs} 条 / 消息 {msgs} 条")
