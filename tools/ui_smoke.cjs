/* Run against a disposable local database, never against the production site. */
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const pkg = name => require(process.env.CAMPUSEVENT_NODE_MODULES
  ? path.join(process.env.CAMPUSEVENT_NODE_MODULES, name) : name);
const { chromium } = pkg("playwright");
const root = path.resolve(__dirname, "..");
const base = process.env.CAMPUSEVENT_PREVIEW || "http://127.0.0.1:5088";
if (!/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(base)) {
  throw new Error("UI smoke tests are restricted to a disposable localhost server.");
}
const output = path.join(root, "docs", "verification", "images");
fs.mkdirSync(output, { recursive: true });
let browser;

(async () => {
  browser = await chromium.launch({
    headless: true, channel: process.env.CAMPUSEVENT_BROWSER_CHANNEL || undefined,
  });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", e => errors.push(String(e)));
  const title = `年级限定验收活动 ${Date.now()}`;
  await page.goto(`${base}/admin/activity/new`);
  await page.locator('[name="title"]').fill(title);
  await page.locator('[name="category"]').fill("学习交流");
  await page.locator('[name="location"]').fill("实验楼 B301");
  const start = new Date(Date.now() + 7 * 86400000);
  const date = `${start.getFullYear()}-${String(start.getMonth()+1).padStart(2,"0")}-${String(start.getDate()).padStart(2,"0")}T15:00`;
  await page.locator('[name="start_at"]').fill(date);
  await page.locator('[name="capacity"]').fill("2");
  await page.locator('[name="policy_type"]').selectOption("年级限定直接报名");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await page.waitForURL("**/admin");
  await page.goto(`${base}/?keyword=${encodeURIComponent(title)}&student=S001`);
  await page.getByRole("link", { name: "详情", exact: true }).first().click();
  const activityUrl = new URL(page.url());
  await page.getByRole("button", { name: "立即报名", exact: true }).click();
  await page.waitForLoadState("networkidle");
  assert.match(await page.locator(".flashes").innerText(), /大二.*大三/);
  await page.screenshot({ path: path.join(output, "grade-rejected-desktop.png"), fullPage: true });
  activityUrl.searchParams.set("student", "S002");
  await page.goto(activityUrl.href);
  await page.getByRole("button", { name: "立即报名", exact: true }).click();
  await page.waitForLoadState("networkidle");
  assert.match(await page.locator(".flashes").innerText(), /报名成功/);
  await page.getByRole("link", { name: "我的消息" }).click();
  await page.waitForURL("**/messages?student=S002");
  assert.match(await page.locator("body").innerText(), /S002@campusevent\.invalid/);
  assert.match(await page.locator("body").innerText(), /SENT/);
  await page.screenshot({ path: path.join(output, "dual-notifications-desktop.png"), fullPage: true });
  await page.screenshot({ path: path.join(output, "notifications-detail.png"),
    clip: { x: 230, y: 85, width: 1180, height: 470 } });
  const checks = [];
  for (const [width, height, label] of [[1440, 1000, "desktop"], [390, 844, "mobile"]]) {
    await page.setViewportSize({ width, height });
    for (const route of ["/?student=S002", "/messages?student=S002", "/admin/activity/new", `${activityUrl.pathname}?student=S002`]) {
      await page.goto(base + route);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
      assert.equal(overflow, false, `${label}: page overflows at ${route}`);
      checks.push({ viewport: label, route, noPageOverflow: !overflow });
    }
    await page.goto(base + "/messages?student=S002");
    await page.screenshot({ path: path.join(output, `messages-${label}.png`), fullPage: true });
  }
  assert.deepEqual(errors, []);
  fs.writeFileSync(path.join(root, "docs", "verification", "ui-check.json"),
    JSON.stringify({ checkedAt: new Date().toISOString(), base, checks, pageErrors: errors,
      flows: ["grade1_rejected", "grade2_approved", "identity_preserved", "both_channels_visible"],
      scope: "Real browser actions against a disposable local database; not production." }, null, 2));
  console.log(JSON.stringify({ status: "passed", checks: checks.length, pageErrors: errors.length }));
})().catch(e => { console.error(e); process.exitCode = 1; })
  .finally(async () => { if (browser) await browser.close(); });
