# -*- coding: utf-8 -*-
"""CampusEvent 应用入口。

启动：python app.py     （默认 http://127.0.0.1:5000）
生产：gunicorn app:app --bind 0.0.0.0:$PORT
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from campusevent.factory import build_app  # noqa: E402

app, container = build_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"[CampusEvent] 启动中... http://127.0.0.1:{port}")
    print(f"[CampusEvent] 数据库: {container.db_path}")
    app.run(host="0.0.0.0", port=port, debug=False)
