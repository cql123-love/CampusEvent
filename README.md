# CampusEvent —— 校园活动报名与管理系统

《软件工程》实验二：**基于设计模式的校园活动报名与管理系统**（项目代号 CampusEvent）。

| | |
|---|---|
| 姓名 | 陈倩林 |
| 学号 | 242806010126 |
| 班级 | 计科1班 |

> 需求依据：《软件工程》实验指导书 第三章 + 附录B（CampusEvent 初始需求与设计检查表）

## 老师验收入口：原版与新增版

原版完整保存在 `baseline-v1`，不覆盖、不移动该标签；新增功能在 `change/cr01-cr02` 分支实现，由 `change-v2` 固定。根目录展示新版，不代表原版被删除，无需再复制维护两套目录。

- [原版全部源码与原始文档](https://github.com/cql123-love/CampusEvent/tree/baseline-v1)
- [变更版全部源码与文档](https://github.com/cql123-love/CampusEvent/tree/change-v2)
- [两版逐文件差异](https://github.com/cql123-love/CampusEvent/compare/baseline-v1...change-v2)
- [版本保留与分别运行方法](docs/两版代码说明.md)
- [AI_DEV_LOG.md：指导书要求的过程记录](AI_DEV_LOG.md)

## 变更版验收（2026-11-26）

已实现教师 CR-01（年级限定报名）和 CR-02（模拟邮件通知），保留初版并提供实现前分析、代码差异和回归证据：

- [初版 / 变更图对照与说明](design/变更图说明.md)
- [变更版 UML 类图](design/07_UML类图_变更设计.svg)
- [年级限定报名时序图](design/08_时序图_年级限定报名.svg)
- [审批与双通道通知时序图](design/09_时序图_审批与双通道通知.svg)
- [变更影响分析与测试计划](docs/变更影响分析.md)
- [实际回归测试表](docs/变更回归测试表.md)：初版 22 项、变更版 77 项、Web 12 场景、浏览器桌面/手机 8 项检查
- [可维护性指标](docs/可维护性对照.md)：新增 5 类；两个核心服务中修改 1 类，报名核心类 AST 未变
- [项目总结](docs/项目总结.md)、[七页 PDF](docs/项目总结.pdf)、[Word 版](docs/项目总结.docx)、[答辩 PPT](docs/实验二答辩.pptx)

**仓库实现和本地验证已完成；腾讯云变更版尚未升级，同学评审签名仍须本人完成。** `baseline-v1` 不变，变更实现由 `change-v2` 固定。图已更新为实现版，设计稿仍可在 `995b351` 查看。线上升级必须先备份，步骤见 [变更版升级](docs/变更版部署升级.md)。

---

## 一、在线地址

| 项目 | 地址 |
|---|---|
| **代码仓库** | **https://github.com/cql123-love/CampusEvent** |
| **项目 Web 地址（公网可访问）** | **http://101.35.250.91/** |

2026-11-25 已从服务器外部验证首页、管理后台、消息、活动详情与 CSS 均返回 HTTP 200。当前使用腾讯云 Ubuntu + Nginx + Gunicorn + systemd；试用到期日及费用以账号控制台为准，不承诺永久免费。验证详情见 `docs/公网部署验收.md`。

---

## 二、项目定位

面向校园管理员与学生的活动报名系统：管理员发布活动，学生浏览并报名，报名结果通过站内消息与模拟邮件通知。

**核心技术特征（实验二重点）：**

- **策略模式**：原 `DirectPolicy` / `ReviewPolicy` 保留，新增 `GradeLimitedDirectPolicy`，仅新类型限制年级 2、3
- **观察者模式**：同时订阅 `MessageNotifier` 与 `EmailNotifier`，在报名提交后处理通知，失败不回滚报名
- **持久化与防重复**：SQLite 迁移、邮件事件唯一键、有效报名唯一索引、容量触发器与状态条件更新
- **SOLID 与代价**：见 [变更版设计原则](design/10_变更版设计原则.md)，不将历史文字中的“全系统零修改”作为当前结论

---

## 三、目录结构

```
CampusEvent/
├── app.py                     应用入口（python app.py / gunicorn app:app）
├── requirements.txt           依赖清单
├── pytest.ini                 测试配置
│
├── design/                    ★ 设计材料（AI 编码前置条件，需同学评审签字）
│   ├── 00_设计决策说明.md      ★ 职责划分 + 两个关键取舍的理由
│   ├── 01_用例说明.md          P2-F01~F08 用例 + 业务规则追踪矩阵
│   ├── 02_UML类图.puml/.png    UML 类图（PlantUML 源码 + 渲染图）
│   ├── 03_时序图_报名.puml/.png 报名时序图（直接/审核/重复/满员）
│   ├── 04_时序图_审批.puml/.png 审批时序图（通过/拒绝/容量已满/取消）
│   └── 05_设计原则说明.md      SOLID 逐条落地 + 模式收益与代价
│
├── src/campusevent/
│   ├── entities.py            实体层：Activity / Student / Registration / Message
│   ├── repositories.py        仓储层：6 个仓储（含邮件与通知日志）
│   ├── policies.py            ★ 策略层：RegistrationPolicy + 3 实现 + 工厂
│   ├── events.py              ★ 事件层：发布、站内消息、邮件订阅与 Mock 发送器
│   ├── errors.py              共享业务异常
│   ├── migrations.py          事务迁移与数据库最终约束
│   ├── services.py            应用层：RegistrationService / ActivityService（业务编排）
│   ├── routes.py              表现层：Flask 蓝图
│   └── factory.py             装配层：数据库初始化 + 依赖注入 + 演示数据
│
├── templates/  static/        前端模板与样式
├── tests/
│   ├── conftest.py            每个用例独立临时库
│   ├── test_campusevent.py    ★ C1~C10 验收用例 + 10 条边界补充（共 22 条）
│   ├── test_changes.py        CR、通知故障、重复与并发（47 项）
│   ├── test_migrations.py     旧库迁移、回滚与备份（6 项）
│   └── e2e_check.py           Web 层端到端验证（12 项）
│
└── docs/                      截图、测试记录、变更分析等
```

---

## 四、部署和运行说明

### 4.1 环境要求

- Python 3.11 或更高版本
- 操作系统：Windows / macOS / Linux 均可

### 4.2 本地运行

```bash
# 1. 克隆仓库
git clone https://github.com/cql123-love/CampusEvent.git
cd CampusEvent

# 2. 创建虚拟环境
python -m venv venv
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动（默认 http://127.0.0.1:5000）
python seed.py
python app.py
```

浏览器打开 <http://127.0.0.1:5000> 即可看到活动广场。

### 4.3 运行测试

```bash
pytest tests/ -v          # 当前 77 条，含 CR、边界、迁移、部署测试
python tests/e2e_check.py # 12 项 Web 层端到端验证
python tools/verify_release.py # 重跑初版、当前版并生成日志、XML、指标
```

`tools/verify_release.py` 会更新 `docs/verification/` 中证据文件，建议在独立克隆中复现。若 Windows 的旧 pytest 临时目录权限异常，可运行 `pytest -p no:cacheprovider --basetemp <新的可写临时目录>`，不要修改业务断言来掩盖环境错误。

界面新增的模拟邮件在“我的消息”下方。收件地址固定为 `学生ID@campusevent.invalid`，不连接 SMTP、不收费、不是真实外发邮件。故障演示可在独立测试环境设置 `CAMPUSEVENT_MOCK_EMAIL_FAIL=1` 后启动；已提交报名仍保留，邮件显示 FAILED 并记录错误。不要为此修改生产全部通知。

可选真实浏览器验收：在单独本地演示库启动 5088 端口后运行 `node tools/ui_smoke.cjs`（需要 Playwright 与已安装浏览器；可设 `CAMPUSEVENT_BROWSER_CHANNEL=msedge`）。此脚本只接受 localhost URL，会实际新建演示活动和报名，不能对生产执行。浏览器依赖不属于 Flask 运行必需项。

### 4.4 腾讯云 Ubuntu 部署（当前线上方案）

前提：已领取云服务器试用或零元资源。脚本不会购买产品、修改云计费或启用自动续费；云实例、磁盘、流量是否收费及到期日仍需在控制台确认。

在服务器的 `ubuntu` 用户终端执行：

```bash
sudo apt-get update
sudo apt-get install -y git
git clone https://github.com/cql123-love/CampusEvent.git ~/CampusEvent
cd ~/CampusEvent
bash deploy/ubuntu.sh <服务器公网IPv4>
```

若目录已经存在，不要重复 clone 或删除目录，先检查其内容。脚本安装 Nginx、建立 Python 虚拟环境、运行全部测试，再创建 `campusevent` systemd 服务。Gunicorn 仅监听 `127.0.0.1:8000`，Nginx 提供 HTTP 80 端口；应用以当前普通用户运行。

- 腾讯云安全组仅需额外允许入站 TCP 80（来源 `0.0.0.0/0`），无需开放 5000 或 8000。
- 数据库保存在 `~/CampusEvent/instance/campusevent.db`，服务重启不会清空。会话密钥存储在同目录的 `production.env`，不提交 Git。
- 首次仅生成虚拟演示数据。应用为公开教学演示，不含真实账号权限系统，不得录入敏感数据。
- 维护：`sudo systemctl status campusevent`；日志：`sudo journalctl -u campusevent -n 60 --no-pager`；重启：`sudo systemctl restart campusevent`。
- 更新到变更版：按 [备份及升级说明](docs/变更版部署升级.md) 获取 `change-v2`，执行 `bash deploy/upgrade.sh`。脚本先测试，再停止服务、备份、事务迁移并重启；不要删库或运行 `seed.py --force`。
- 验收：用外部浏览器访问 `http://<服务器公网IPv4>/`，验证创建活动、报名、审批、消息，再重启 `campusevent` 确认记录保留。服务器内部 HTTP 检查不等于公网验收。
- 这是 HTTP 演示地址，不代表已配置 HTTPS。若平台要求域名备案、限制 IP 访问或试用到期，须按平台规则处理，不绕过限制。

### 4.5 PythonAnywhere 备选方案（未部署）

本方案未使用，没有 PythonAnywhere 线上地址。

以下仅保留为备选部署参考，不是当前公网部署状态。免费账户限制和注册条件以平台页面为准；不要选择付费方案或绑定支付方式。

| 平台 | 配置文件 | 免费额度 | 说明 |
|---|---|---|---|
| PythonAnywhere（备选） | `deploy/pythonanywhere_wsgi.py` | 以平台当前免费计划为准 | 本次未使用 |
| Render（非默认方案） | `render.yaml` | 以平台当前免费计划为准 | 当前配置使用临时盘，不满足重启后数据保留要求 |
| Railway（非默认方案） | `railway.json` | 以账户剩余额度为准 | 不保证零费用；未配置持久卷前不作为交付方案 |

**PythonAnywhere 部署（备选）：**

完整步骤见 **`docs/部署_PythonAnywhere.md`**，要点如下：

1. 注册 <https://www.pythonanywhere.com/registration/register/beginner/>（无信用卡，用户名即网址前缀）
2. Consoles → Bash：克隆仓库，以 Web 页面支持的 Python 3.11 或更高版本建立虚拟环境，然后执行 `pip install -r requirements.txt`。
3. Web → Add a new web app → **Manual configuration** → 选与虚拟环境一致的 Python 版本
4. Virtualenv 填 `/home/<用户名>/.virtualenvs/campusevent-env`
5. 将仓库中的 WSGI 配置复制到平台指定的 WSGI 文件：
   ```bash
   cp ~/CampusEvent/deploy/pythonanywhere_wsgi.py /var/www/<用户名>_pythonanywhere_com_wsgi.py
   ```
   目标路径以 Web 页面显示的 **WSGI configuration file** 为准。配置会自动使用 `/home/<用户名>/CampusEvent/instance/campusevent.db`，只在空库中生成演示数据，不要设置数据库到 `/tmp`。
6. Static files 映射 `/static/` → `/home/<用户名>/CampusEvent/static`，然后点 **Reload**

**Render / Railway 部署：**

1. 打开 <https://dashboard.render.com/blueprint/new?repo=https%3A%2F%2Fgithub.com%2Fcql123-love%2FCampusEvent>
2. 页面确认后点击 **Apply**（首次需先「用 GitHub 登录」并授权仓库访问）
3. 等待构建完成（约 2~5 分钟），生成 `https://campusevent-xxxx.onrender.com` 固定地址

> ⚠️ 若创建时看到 **Starter / $7 per month** 之类的选项，**务必选 Free**——只有选付费实例才会要求绑定信用卡。
> 若 `render.com` 主域名因网络 DNS 污染打不开，改用 **https://dashboard.render.com/** 亦可。

**Railway 部署步骤：**

1. 打开 <https://railway.com/new> → 用 GitHub 登录 → 选择 **GitHub Repository**
2. 首次点 **Configure GitHub App** 授权（选 *Only select repositories* 并勾选 `CampusEvent`），授权后点 **Refresh**
3. 选择 `cql123-love/CampusEvent`，Railway 自动读取 `railway.json` 完成构建
4. 在 Service 的 **Settings → Networking** 点 **Generate Domain** 获得公网地址

**部署配置对照：**

| 配置项 | 值 |
|---|---|
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn app:app --bind 0.0.0.0:$PORT` |
| Healthcheck Path | `/` |
| 环境变量 | `CAMPUSEVENT_DB=/tmp/campusevent.db`（可选） |
| 工作目录 | 仓库根目录（**不设 rootDir**，确保 templates/static 与本地运行一致）|

> Render/Railway 的默认实例磁盘是临时盘，以上旧配置仅供参考，不作为符合 C10 的最终交付。PythonAnywhere 方案使用用户目录中的持久文件；重载应用不会主动清空数据库。首次生成 5 个活动、4 个学生和 1 个管理员，后续不会重复生成。
>
> WSGI 配置启用 HTTPS 安全 Cookie，并在每次启动时生成随机会话密钥。重载可能清除一次性提示消息，但不会丢失数据库记录。需要稳定会话时，可在平台私有配置中设置 `CAMPUSEVENT_SECRET`，不得将密钥提交到 Git。
>
> 本项目按指导书使用公开演示身份，没有真实登录权限控制。公网演示只使用虚拟活动与演示账号，不要录入真实个人信息。

---

## 五、演示账号

指导书允许使用固定演示账号，无需注册体系。系统内置：

| 学号 | 姓名 | 年级 | 角色 |
|---|---|---|---|
| S001 | 陈倩林 | 1 | 学生 |
| S002 | 李明轩 | 2 | 学生 |
| S003 | 王思远 | 3 | 学生 |
| S004 | 赵雨桐 | 4 | 学生 |
| A001 | 管理员 | 1（占位） | 管理员 |

页面上可切换当前学生身份（右上角下拉框），用于演示"不同学生视角"。

年级是虚拟演示数据，不推断实际姓名对应的真实年级。旧库升级只对上述演示 ID 设置映射，其他既有学生默认 1，不自动获得限定报名资格。新类型可在后台创建，首次种子仍为原有 5 个活动；升级不补发历史邮件。

---

## 六、核心业务规则实现对照（附录 B.2）

| 规则 | 实现位置 | 测试用例 |
|---|---|---|
| R1 直接报名 → 已通过 + 通知 | `DirectPolicy.submit()` | C2 |
| R2 审核型 → 待审核；批准时再查名额 | `ReviewPolicy` / `RegistrationService.review()` | C5、C6、C8 |
| R3 名额按"已通过"计，待审核不占名额 | `_check_quota()` / `count_approved()` | C4、C8、B7 |
| R4 禁止重复有效报名；取消后可再申请 | `_check_common_rules()` / `has_effective()` / 部分唯一索引 | C3、C3b |
| R5 可取消待审核/已通过；开始后不收新报名 | `cancel()` / `_check_common_rules()` | C9、B1 |
| R6 通知失败留痕但不使报名消失 | 事务边界 + `MessageNotifier` 异常隔离 | **B5** |
| R7 持久化；删有报名的活动要拒绝或软删除 | `ActivityService.delete_activity()`（本设计选**拒绝删除**） | B3、B4、C10 |

---

## 七、Git 版本标签（指导书 3.6 要求）

| 标签 | 含义 | 说明 |
|---|---|---|
| `baseline-v1` | 初始验收版本 | 原始标签保持不变；云端部署使用后续部署提交，详见部署验收记录 |
| `change-v2` | CR 实现与本地回归版本 | 年级策略、Mock 邮件、迁移、回归证据与材料；不代表生产已升级 |

> **变更实施规范：** 变更单（CR）未发布前不得提前实现；变更须在新分支上进行，**不得删除项目重建**；须保留每次关键修改的 Git 差异与 AI 交互记录。

---

## 八、文档索引

| 文档 | 内容 |
|---|---|
| `design/00_设计决策说明.md` | 职责划分、依赖方向、两个关键取舍的理由、评审签字栏 |
| `design/01_用例说明.md` | 7 个用例 + 业务规则追踪矩阵 |
| `design/05_设计原则说明.md` | SOLID 逐条落地 + 模式收益与代价 + 未来扩展路径 |
| `design/10_变更版设计原则.md` | 当前实现的设计理由、数据库保护和已知局限；历史文档偏差以此为准 |
| `design/变更图说明.md` | 初版图与 CR 变更设计图入口、原图偏差校正、渲染方法 |
| `AI_DEV_LOG.md` / `docs/AI_DEV_LOG.md` | 根目录入口与完整关键协作记录，含初版、部署和变更 |
| `docs/需求验收表.md` | C1~C10 与边界用例的逐条验收记录 |
| `docs/初始SRS分析.md` | 依据初版需求补充整理的范围、职责与验收映射，不冒称编码前已存在 |
| `docs/变更影响分析.md` | 保留实现前分析，并追加实际实现结果与差异 |
| `docs/变更回归测试表.md` | 教师 CR 编号、原用例、边界、故障与迁移结果 |
| `docs/可维护性对照.md` | 新类、核心类、回归、轮次和可确认修改时长的口径 |
| `docs/项目总结.md` | 七部分报告，附七页 PDF、Word 版与答辩 PPT |

材料再生成需要 Node.js、Playwright、已安装的 Chromium/Edge、`docx`、`pptxgenjs`、`pdf-lib`；运行 `node tools/build_materials.cjs`。脚本读取 Markdown 和实际测试汇总，生成 Word、PDF、PPT，并验证 PDF 七页及内容无溢出。Office 文件检查了结构，尚未逐页人工放映，提交前需本人打开审阅。
