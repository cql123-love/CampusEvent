/* Build the seven-page report and the presentation from checked-in evidence. */
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const pkg = name => require(process.env.CAMPUSEVENT_NODE_MODULES
  ? path.join(process.env.CAMPUSEVENT_NODE_MODULES, name) : name);
const pptxgen = pkg("pptxgenjs");
const { Document, Packer, Paragraph, TextRun, Header, Footer, AlignmentType } = pkg("docx");
const { chromium } = pkg("playwright");
const { PDFDocument } = pkg("pdf-lib");
const root = path.resolve(__dirname, "..");
const docs = path.join(root, "docs");
const evidence = JSON.parse(fs.readFileSync(path.join(docs, "verification", "summary.json"), "utf8"));
assert.equal(evidence.pytest_exit, 0);
assert.equal(evidence.baseline_exit, 0);
assert.equal(evidence.web_e2e_exit, 0);
const pages = fs.readFileSync(path.join(docs, "项目总结.md"), "utf8")
  .split("<!-- pagebreak -->").map(s => s.trim());
assert.equal(pages.length, 7);
const escape = text => text.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
const paragraphs = source => source.split(/\r?\n\s*\r?\n/).map(block => {
  const heading = block.match(/^(#{1,3})\s+([\s\S]+)$/);
  return heading ? { level: heading[1].length, text: heading[2] }
    : { level: 0, text: block.replace(/\s*\r?\n/g, " ").replaceAll("**", "") };
});

async function report() {
  const articles = pages.map((source, i) => `<article class="report-page">
    <div class="page-content">${paragraphs(source).map(p => p.level
      ? `<h${p.level}>${escape(p.text)}</h${p.level}>` : `<p>${escape(p.text)}</p>`).join("")}</div>
    <footer>CampusEvent / 软件工程实验二 <span>${i + 1} / 7</span></footer></article>`).join("");
  const html = `<!doctype html><html lang="zh-CN"><meta charset="utf-8">
  <title>CampusEvent 实验二项目总结</title><style>
  @page { size:A4; margin:18mm; }
  * { box-sizing:border-box; }
  body { margin:0; color:#20282b; font-family:"Microsoft YaHei",sans-serif; }
  .report-page { height:257mm; position:relative; break-after:page; padding-bottom:15mm; }
  .report-page:last-child { break-after:auto; }
  .page-content { display:flow-root; }
  h1 { font-size:22pt; line-height:1.4; margin:0 0 8mm; color:#176859; }
  h2 { font-size:17pt; line-height:1.5; margin:0 0 6mm; border-bottom:1pt solid #ccd7d4; padding-bottom:3mm; }
  p { font-size:11pt; line-height:1.7; margin:0 0 4.5mm; text-align:justify; }
  footer { position:absolute; bottom:0; width:100%; border-top:1px solid #ccd7d4;
    padding-top:3mm; font-size:9pt; color:#5b6763; }
  footer span { float:right; }
  @media screen { body { background:#eee; padding:12px; }
    .report-page { background:white; width:174mm; margin:0 auto 20px; } }
  </style>${articles}</html>`;
  fs.writeFileSync(path.join(docs, "项目总结.html"), html);
  const browser = await chromium.launch({
    headless: true, channel: process.env.CAMPUSEVENT_BROWSER_CHANNEL || undefined,
  });
  try {
    const page = await browser.newPage();
    await page.setContent(html, { waitUntil: "load" });
    await page.emulateMedia({ media: "print" });
    const overflow = await page.locator(".report-page").evaluateAll(articles =>
      articles.map((a, i) => ({ page: i + 1,
        overflow: a.querySelector(".page-content").getBoundingClientRect().height > a.clientHeight - 57 })));
    assert.equal(overflow.some(p => p.overflow), false, JSON.stringify(overflow));
    await page.pdf({ path: path.join(docs, "项目总结.pdf"), preferCSSPageSize: true,
      printBackground: true });
  } finally { await browser.close(); }
  const pdf = await PDFDocument.load(fs.readFileSync(path.join(docs, "项目总结.pdf")));
  assert.equal(pdf.getPageCount(), 7);

  const children = pages.flatMap((source, i) => paragraphs(source).map((p, j) => new Paragraph({
    pageBreakBefore: i > 0 && j === 0,
    spacing: { after: p.level ? 230 : 150, line: 340 },
    children: [new TextRun({
      text: p.text, font: "Microsoft YaHei",
      size: p.level === 1 ? 36 : p.level === 2 ? 30 : 22,
      bold: p.level > 0, color: p.level ? "176859" : "20282B",
    })],
  })));
  const doc = new Document({
    creator: "CampusEvent", title: "软件工程实验二项目总结", description: "七部分实验总结与证据边界",
    sections: [{
      properties: { page: { size: { width: 11906, height: 16838 },
        margin: { top: 1021, bottom: 1021, left: 1021, right: 1021 } } },
      headers: { default: new Header({ children: [new Paragraph({
        children: [new TextRun({ text: "CampusEvent / 软件工程实验二", size: 18, color: "5B6763" })],
      })] }) },
      footers: { default: new Footer({ children: [new Paragraph({
        alignment: AlignmentType.RIGHT,
        children: [new TextRun({ text: "2026-11-26 / 本地验收，线上升级待完成", size: 18 })],
      })] }) },
      children,
    }],
  });
  fs.writeFileSync(path.join(docs, "项目总结.docx"), await Packer.toBuffer(doc));
  return pdf.getPageCount();
}

async function slides() {
  const ppt = new pptxgen();
  ppt.layout = "LAYOUT_WIDE";
  ppt.author = "陈倩林 / CampusEvent";
  ppt.subject = "软件工程实验二：设计模式、需求变更与回归证据";
  ppt.title = "CampusEvent 实验二答辩";
  ppt.lang = "zh-CN";
  ppt.theme = { headFontFace: "Microsoft YaHei", bodyFontFace: "Microsoft YaHei", lang: "zh-CN" };
  const colors = { ink: "20282B", muted: "586660", green: "176859", red: "A73D3D", line: "D8E1DD" };
  let count = 0;
  const slide = (title, note) => {
    const s = ppt.addSlide();
    s.background = { color: "FFFFFF" };
    s.addShape(ppt.ShapeType.rect, { x: 0, y: 0, w: 0.13, h: 7.5,
      fill: { color: colors.green }, line: { color: colors.green } });
    s.addText(title, { x: 0.55, y: 0.4, w: 12.1, h: 0.65,
      fontSize: 27, bold: true, color: colors.ink, margin: 0 });
    s.addText(`CampusEvent  |  软件工程实验二  |  ${++count}`, {
      x: 0.55, y: 7.07, w: 12, h: 0.2, fontSize: 9, color: colors.muted, margin: 0,
    });
    s.addNotes(note);
    return s;
  };
  const text = (s, body, x = 0.6, y = 1.5, w = 12, h = 4.9, size = 22) =>
    s.addText(body, { x, y, w, h, fontSize: size, color: colors.ink, margin: 0.05,
      breakLine: false, paraSpaceAfterPt: 18, valign: "top", fit: "shrink" });
  const image = (s, name, x, y, w, h) => {
    const filename = path.join(root, name);
    const png = fs.readFileSync(filename);
    assert.equal(png.subarray(1, 4).toString(), "PNG");
    const width = png.readUInt32BE(16);
    const height = png.readUInt32BE(20);
    const scale = Math.min(w / width, h / height);
    s.addImage({ path: filename, x: x + (w - width * scale) / 2,
      y: y + (h - height * scale) / 2, w: width * scale, h: height * scale });
  };

  let s = slide("CampusEvent", "先说明项目与版本，再说明当前本地验证和生产状态的区别。");
  text(s, "校园活动报名与管理系统\n策略模式 · 观察者模式 · 需求变更与回归", 0.6, 1.6, 12, 2.2, 29);
  text(s, "陈倩林  |  计科1班  |  242806010126\nbaseline-v1 → change-v2\n2026-11-26", 0.6, 4.5, 12, 1.5, 19);

  s = slide("需求：新增功能，保留旧行为", "强调“不变”是兼容性，不是数据库、界面和文档都不能修改。");
  text(s, "CR-01：限定年级直接报名\n仅大二、大三；大一、大四明确拒绝。\n\nCR-02：模拟邮件通知\n通过/拒绝双渠道；失败不回滚；同事件不重复。", 0.6, 1.5, 7.8, 4.7);
  text(s, "保持不变\n普通直接 / 审核策略\n时间、容量、重复约束\n原 C1～C10", 9.0, 1.5, 3.7, 4.7, 20);

  s = slide("职责：规则、流程和通知各自独立", "仓储并非全是抽象接口；不要夸称所有依赖都指向接口。");
  text(s, "Flask 路由 → 应用服务 → 仓储 → SQLite\n\nRegistrationService → PolicyFactory → RegistrationPolicy\n\n报名 COMMIT → EventPublisher → 两个通知观察者", 0.6, 1.6, 12, 3.5, 25);
  text(s, "公共时间 / 重复 / 名额在服务层；数据库索引与触发器负责并发最终保护。", 0.6, 5.55, 12, 0.8, 20);

  s = slide("实现版 UML：保留初版，核对实际结构", "完整可缩放图和 PlantUML 在 design/07；初版图仍在02。");
  image(s, "design/07_UML类图_变更设计.png", 0.35, 1.12, 12.7, 5.75);

  s = slide("CR-01：只扩展新策略", "讲解年级默认值和演示映射，不从学号猜真实年级。");
  text(s, "GradeLimitedDirectPolicy 继承 DirectPolicy\n仅在 submit 检查 grade ∈ {2,3}\n通过后复用原直接报名行为\n\nStudent 与 SQLite 都校验 1～4\n后台、类型注册、仓储和页面同步适配", 0.6, 1.5, 12, 4.9, 24);

  s = slide("CR-02：提交后通知，持久去重", "模拟记录不等于真实SMTP投递，不承诺外部恰好一次发送。");
  text(s, "原 MessageNotifier 保留 + 新 EmailNotifier\nMockEmailSender 不连接 SMTP、不收费\n\nUNIQUE(registration_id, event_type)\nSENT / FAILED 与错误可见；失败日志同事务\n重启后重复事件不新增；失败不自动重试", 0.6, 1.5, 12, 4.9, 23);

  s = slide("真实浏览器：站内消息与模拟邮件", "截图来自一次性本地数据库，不冒充公网运行截图。");
  image(s, "docs/verification/images/notifications-detail.png", 0.55, 1.6, 12.2, 4.85);

  s = slide("回归：可复现证据，不只写“通过”", "演示 tools/verify_release.py 和 XML。原初版从 Git 解包重新运行。");
  text(s, `初版：${evidence.baseline_tests} 项通过\n变更版：${evidence.tests} 项通过，失败 ${evidence.failures}，错误 ${evidence.errors}\n原 Web：12 场景，0 失败\n浏览器：桌面/手机 8 项布局检查，0 pageerror\n\n证据：docs/verification/ + 变更回归测试表`, 0.6, 1.5, 12, 4.9, 25);

  s = slide("旧库升级：先备份，不清空历史", "生产尚未执行，必须由账号持有人在原服务器运行。");
  text(s, "停止写入 → SQLite backup → 显式事务迁移\n增加 grade，升级活动 CHECK，创建邮件表和约束\n保留原 ID、报名、已读消息和失败日志\n外键/版本错误安全拒绝；故障注入验证回滚\n\n生产升级脚本：deploy/upgrade.sh", 0.6, 1.5, 12, 4.9, 24);

  s = slide("维护性：同时报告收益和代价", "核心类数口径为两个应用服务；其他实体和仓储也真实修改。");
  text(s, "新增类：5 个；类总数 22 → 27\n核心业务类修改：1 / 2\nRegistrationService 类 AST 不变\n本次功能修改：19分48秒；实施请求 1 回合\n\n不是全系统零修改：迁移、校验、页面、SQL 均有成本。", 0.6, 1.5, 12, 4.9, 23);

  s = slide("实际问题：测试通过也可能漏边界", "区分代码缺陷和测试断言错误，说明为什么需要风险驱动补测。");
  text(s, "当天活动提前关闭 → 精确时间比较\n非法日期可保存 → 新建、编辑校验\n历史报名删除 500 → 拒绝删除并保留历史\n待审核改策略后审批异常 → 禁止切换 + 数据库保护\n\n并发报名 / 批准 / 陈旧审批均增加专项测试。", 0.6, 1.5, 12, 4.9, 23);

  s = slide("交付与仍需完成的人工环节", "提交答案两行；不要据本地结果宣称生产已经更新或同学已经签名。");
  text(s, "仓库：源码、两版标签、图、分析、日志、回归、总结、PPT\n\n待完成：真实同学评审签名\n待完成：腾讯云变更版升级、业务写入与重启保留验收\n\n公开演示无真实认证；云资源到期与费用须本人确认。", 0.6, 1.5, 12, 4.9, 23);

  await ppt.writeFile({ fileName: path.join(docs, "实验二答辩.pptx") });
  return count;
}

(async () => {
  const pageCount = await report();
  const slideCount = await slides();
  const manifest = { generatedAt: new Date().toISOString(), reportPdfPages: pageCount,
    reportSections: pages.length, slides: slideCount, testCount: evidence.tests,
    note: "PDF page count and report overflow verified; PPTX structure checked separately, not Office-rendered." };
  fs.writeFileSync(path.join(docs, "verification", "materials.json"), JSON.stringify(manifest, null, 2));
  console.log(JSON.stringify(manifest));
})().catch(e => { console.error(e); process.exitCode = 1; });
