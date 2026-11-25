# CampusEvent 部署到 PythonAnywhere（免信用卡 · 永不休眠）

> 适用于：需要「公网可访问、不用自己开电脑、不绑卡」的场景。
> 结果：获得 `https://<你的用户名>.pythonanywhere.com` 固定地址。

---

## 为什么选 PythonAnywhere

| 优势 | 说明 |
|---|---|
| **不需要信用卡** | 注册只要用户名 + 邮箱 + 密码 |
| **永不休眠** | 与 Render（15 分钟休眠）、Railway（会 sleep）不同，免费版也常驻 |
| **github.com 在白名单** | 免费账户可 `git clone` 拉取仓库 |
| **Web 应用不消耗 CPU 配额** | 免费 100 CPU 秒/天仅计控制台任务，网页访问不受影响 |

**需要注意的限制：**

- 免费账户只有 **1 个 Web 应用**（够用）
- 磁盘 512 MB（本项目代码 + SQLite 体积很小，完全够）
- **Web 应用每月需手动续期一次**（点一下按钮，见文末第 6 步）
- 地址固定为 `<用户名>.pythonanywhere.com`，不支持自定义域名（免费版）

---

## 部署步骤（约 10 分钟）

### 第 1 步 · 注册账号

打开 <https://www.pythonanywhere.com/registration/register/beginner/>

- Username：取一个好记的（**这就是你的网址前缀**，如 `cqlcampusevent` → `https://cqlcampusevent.pythonanywhere.com`）
- Email、Password
- **不需要填信用卡**，注册即完成

> ⚠️ 用户名会出现在最终网址里，建议用英文小写，别用中文或特殊字符。

---

### 第 2 步 · 打开 Bash 控制台

登录后，顶部菜单 **Consoles** → **Bash** → 在新窗口打开。

在控制台里依次粘贴执行：

```bash
# 2.1 克隆仓库
git clone https://github.com/cql123-love/CampusEvent.git

# 2.2 进入目录
cd ~/CampusEvent

# 2.3 创建虚拟环境（用你账号的 Python 版本，下面以 3.10 为例）
mkvirtualenv --python=/usr/bin/python3.10 campusevent-env

# 2.4 安装依赖
pip install -r requirements.txt

# 2.5 写入演示数据（可跳过，但建议执行，这样打开就有数据可看）
python seed.py
```

> 若 `mkvirtualenv` 提示找不到 python3.10，改用 `python3.13` 或先执行 `ls /usr/bin/python3*` 查看可用版本。

执行成功后应看到：

```
演示数据：活动 5 个 / 学生 5 位 / 报名 4 条 / 消息 2 条
```

---

### 第 3 步 · 创建 Web 应用

顶部菜单 **Web** → **Add a new web app**

1. 点 **Next**（若提示域名，确认使用 `<用户名>.pythonanywhere.com`）
2. 选择 **Manual configuration**（**不要选 Flask**！我们要自己配 WSGI，才能用项目的 `app.py`）
3. 选择 Python 版本，**必须与第 2 步建虚拟环境用的版本一致**（如 Python 3.10）
4. 点 **Next** 完成创建

---

### 第 4 步 · 指定虚拟环境

在 **Web** 页面找到 **Virtualenv** 区域：

- 填入：`/home/<你的用户名>/.virtualenvs/campusevent-env`
  （把 `<你的用户名>` 换成你自己的，例如 `/home/cqlcampusevent/.virtualenvs/campusevent-env`）
- 填完点旁边的勾/回车保存

---

### 第 5 步 · 配置 WSGI 文件（关键）

在同一 **Web** 页面找到 **Code** 区域，点 **WSGI configuration file** 链接
（路径形如 `/var/www/<用户名>_pythonanywhere_com_wsgi.py`）。

**把文件内容全部删掉**，替换为下面这段（记得改 `<你的用户名>`）：

```python
import sys
import os

# 项目路径
project_home = '/home/<你的用户名>/CampusEvent'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# 引入 Flask 应用对象（app.py 中的 app 变量）
os.environ['CAMPUSEVENT_SEED'] = '1'      # 首次访问时自动写入演示数据
from app import app as application
```

> ⚠️ 关键点：`from app import app as application`
> —— `app.py` 里定义的是 Flask 实例 `app`，PythonAnywhere 要求变量名必须是 `application`。

保存文件。

---

### 第 6 步 · 配置静态文件 + 重载

**6.1 静态文件映射**（否则 CSS 会 404，页面无样式）

在 **Web** 页面找到 **Static files** 区域，填两栏：

| URL | Directory |
|---|---|
| `/static/` | `/home/<你的用户名>/CampusEvent/static` |

点 **Enter** 保存。

**6.2 重载应用**

滚动回页面顶部，点绿色按钮 **Reload <用户名>.pythonanywhere.com**。

**6.3 访问**

打开 `https://<你的用户名>.pythonanywhere.com` —— 应看到活动广场页面，含 5 个演示活动与站内消息。

---

## 部署后自检

| 检查项 | 期望结果 |
|---|---|
| 首页 `https://<用户名>.pythonanywhere.com` | 显示「活动广场」+ 5 个活动卡片 |
| 样式是否正常 | 左侧深色导航栏、卡片有边框阴影（若无样式 → 回到第 6.1 步） |
| `/admin` 管理后台 | 显示「待审核报名队列」 |
| `/messages` 消息中心 | 显示 2 条演示消息 |
| 完整流程 | 创建活动 → 学生报名 → 管理员审批 → 取消报名 → 统计变化 |

---

## 每月续期（重要）

PythonAnywhere 免费账户的 Web 应用**每月需要点一次续期**，否则会被停用。

- 登录后在 **Web** 页面顶部会看到提示按钮：**Run until 3 months from today** / **Run until 1 month from today**
- **点一下即可**，应用恢复常驻

> 交作业期间正常使用不会遇到；如果老师几周后才检查，建议到期前登录点一次。

---

## 常见问题排查

### 页面报 `Error code: Unhandled Exception`

查看 **Web** 页面的 **Error log**，常见原因：

| 错误 | 原因 | 解决 |
|---|---|---|
| `ModuleNotFoundError: No module named 'flask'` | 虚拟环境没配或没装依赖 | 检查第 4 步路径；控制台执行 `workon campusevent-env && pip install -r requirements.txt` |
| `ModuleNotFoundError: No module named 'campusevent'` | 项目路径不对 | 检查 WSGI 里 `project_home` 是否为 `/home/<用户名>/CampusEvent` |
| `TemplateNotFound` | templates 路径问题 | 确认 `templates/` 与 `app.py` 同级（仓库结构即如此） |

### 页面无样式（纯文字）

第 6.1 步静态文件映射没配好。检查 URL 是否带尾斜杠 `/static/`。

### 浏览器缓存

改完配置后按 **Ctrl+F5** 强制刷新。

---

## 与实验一 StudyTask 的区别

| 项 | StudyTask（Railway） | CampusEvent（PythonAnywhere） |
|---|---|---|
| 休眠 | 会 sleep | **不休眠** |
| 绑卡 | 免卡 | **免卡** |
| 部署方式 | Git 自动构建 | **手动 clone + WSGI 配置** |
| 地址 | `xxx.up.railway.app` | `<用户名>.pythonanywhere.com` |
| 维护 | 无需 | **每月点一次续期** |

两个项目互不影响，可同时在线。
