#!/usr/bin/env node

/**
 * Record the reproducible OpenAI Build Week product demo.
 *
 * Scene B is deliberately fail-closed: it replays only the sanitized report
 * produced by run_live_gpt_validation.py after a genuine GPT-5.6 Sol call.
 * No credential, request header, browser profile, or local terminal is shown.
 */

import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(SCRIPT_DIR, "..");
const BASE_URL = process.env.AETERNUS_RECORD_BASE_URL || "http://127.0.0.1:5000";
const RAW_DIR = path.join(ROOT, "submission-artifacts", "raw");
const SCREENSHOT_DIR = path.join(RAW_DIR, "gallery-source");
const LIVE_REPORT_PATH = path.join(RAW_DIR, "live-gpt-report.json");
const VIDEO_DIR = path.join(RAW_DIR, "playwright-video");
const RAW_VIDEO_PATH = path.join(RAW_DIR, "aeternus-demo-raw.webm");
const REPOSITORY_URL = "https://github.com/shibaraven/aeternus-market-intelligence";
const LIVE_QUESTION =
  "Analyze the technical trend, available fundamental evidence, risk, and the " +
  "conflict between buy-and-hold and the SMA20/SMA50 strategy. Show evidence " +
  "IDs and uncertainty. Do not provide a guaranteed investment recommendation.";

const pause = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

function fail(message) {
  throw new Error(message);
}

function walkStrings(value, callback) {
  if (typeof value === "string") {
    callback(value);
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item) => walkStrings(item, callback));
    return;
  }
  if (value && typeof value === "object") {
    Object.values(value).forEach((item) => walkStrings(item, callback));
  }
}

function validateLiveReport(report) {
  if (report.gpt_used !== true) fail("The sanitized live report does not confirm GPT usage.");
  const models = [report.model, report.requested_model, ...(report.api_response_models || [])]
    .filter(Boolean);
  if (!models.length || models.some((model) => !String(model).startsWith("gpt-5.6-sol"))) {
    fail("The sanitized live report does not prove GPT-5.6 Sol usage.");
  }
  if (!report.live_validation?.structured_output_valid ||
      !report.live_validation?.numerical_traceability_valid) {
    fail("The sanitized live report has not passed structured-output and traceability checks.");
  }
  if (!Array.isArray(report.tool_timeline) || report.tool_timeline.length < 7) {
    fail("The sanitized live report does not contain the required tool timeline.");
  }
  if (!Array.isArray(report.evidence_catalog) || report.evidence_catalog.length === 0) {
    fail("The sanitized live report does not contain deterministic evidence.");
  }
  walkStrings(report, (text) => {
    if (/\bsk-[A-Za-z0-9_-]{12,}\b/.test(text) || /authorization:\s*bearer/i.test(text)) {
      fail("The sanitized live report contains a credential-like string.");
    }
  });
}

async function loadLiveReport() {
  if (!existsSync(LIVE_REPORT_PATH)) {
    fail(
      "Missing submission-artifacts/raw/live-gpt-report.json. Run " +
      "scripts/run_live_gpt_validation.py successfully before recording."
    );
  }
  const report = JSON.parse(await readFile(LIVE_REPORT_PATH, "utf8"));
  validateLiveReport(report);
  return report;
}

async function isHealthy() {
  try {
    const response = await fetch(`${BASE_URL}/api/health`, { signal: AbortSignal.timeout(2000) });
    return response.ok;
  } catch {
    return false;
  }
}

async function startApplication() {
  if (await isHealthy()) return null;

  const python = process.platform === "win32"
    ? path.join(ROOT, ".venv", "Scripts", "python.exe")
    : path.join(ROOT, ".venv", "bin", "python");
  if (!existsSync(python)) {
    fail("Create .venv and install backend/requirements.txt before recording.");
  }

  const child = spawn(python, [path.join(ROOT, "backend", "main.py")], {
    cwd: ROOT,
    env: {
      ...process.env,
      AETERNUS_NO_BROWSER: "1",
      AETERNUS_DISABLE_BACKGROUND_TASKS: "1",
    },
    stdio: "ignore",
    windowsHide: true,
  });

  for (let attempt = 0; attempt < 60; attempt += 1) {
    if (await isHealthy()) return child;
    if (child.exitCode !== null) fail("The application exited before becoming healthy.");
    await pause(500);
  }
  child.kill();
  fail("The application did not become healthy within 30 seconds.");
}

async function stopApplication(child) {
  if (!child || child.exitCode !== null) return;
  child.kill();
  await Promise.race([
    new Promise((resolve) => child.once("exit", resolve)),
    pause(3000),
  ]);
}

async function openResearch(page) {
  await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "✦ AI Research", exact: true }).click();
  await page.getByText("Evidence-grounded AI Research", { exact: true }).waitFor();
}

async function showLiveResult(page, report, dwell = true) {
  let replayLive = true;
  const handler = async (route) => {
    if (!replayLive) return route.continue();
    replayLive = false;
    return route.fulfill({
      status: 200,
      contentType: "application/json; charset=utf-8",
      body: JSON.stringify(report),
    });
  };
  await page.route("**/api/research/run", handler);
  await page.locator("#research-mode").selectOption("live");
  await page.locator("#research-market").selectOption("japan");
  await pause(500);
  await page.locator("#research-symbol").fill("7203.T");
  await page.locator("#research-period").selectOption("1y");
  await page.locator("#research-question").fill(LIVE_QUESTION);
  if (await page.locator("#research-prefer-gpt").isEnabled()) {
    await page.locator("#research-prefer-gpt").check();
  }
  if (dwell) await pause(5000);
  await page.locator("#research-run").click();
  await page.getByText("GPT-5.6 tool synthesis", { exact: true }).waitFor();
  await page.unroute("**/api/research/run", handler);
}

async function showFixedDemo(page, dwell = true) {
  await page.locator("#research-mode").selectOption("demo");
  await page.locator("#research-prefer-gpt").uncheck();
  if (dwell) await pause(6000);
  await page.locator("#research-run").click();
  await page.getByText("Deterministic fallback · GPT not called", { exact: true }).waitFor();
}

async function scrollToText(page, text, milliseconds) {
  const target = page.getByText(text, { exact: true });
  await target.scrollIntoViewIfNeeded();
  await pause(milliseconds);
}

async function recordProductDemo(browser, report) {
  await rm(VIDEO_DIR, { recursive: true, force: true });
  await mkdir(VIDEO_DIR, { recursive: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    recordVideo: { dir: VIDEO_DIR, size: { width: 1920, height: 1080 } },
  });
  const page = await context.newPage();
  const video = page.video();

  await openResearch(page);
  await pause(25000); // Scene A — problem, product, and research controls.

  await showLiveResult(page, report, true);
  await pause(8000);
  await scrollToText(page, "🧰 Tool execution timeline", 8000);
  await scrollToText(page, "Evidence ID: technical.close", 7000).catch(() => pause(7000));

  await page.locator("#research-mode").scrollIntoViewIfNeeded();
  await showFixedDemo(page, true);
  await pause(10000);
  await scrollToText(page, "📈 Technical view", 5000);
  await scrollToText(page, "🏢 Fundamental view", 5000);
  await scrollToText(page, "🧪 Backtest comparison", 6000);
  await scrollToText(page, "🛡️ Risk view", 5000);
  await scrollToText(page, "🟢 Bull case", 4000);
  await scrollToText(page, "⚖️ Conflicting signals", 4000);
  await scrollToText(page, "🧰 Tool execution timeline", 3000);
  await scrollToText(page, "Financial disclaimer", 2000);

  await page.goto(`${REPOSITORY_URL}/blob/build-week-2026/README.md`, {
    waitUntil: "domcontentloaded",
  });
  await pause(8000);
  await page.goto(`${REPOSITORY_URL}/blob/build-week-2026/docs/VALIDATION_REPORT.md#automated-tests`, {
    waitUntil: "domcontentloaded",
  });
  await pause(8000);
  await page.goto(`${REPOSITORY_URL}/blob/build-week-2026/docs/VALIDATION_REPORT.md#windows-package-build`, {
    waitUntil: "domcontentloaded",
  });
  await pause(7000);
  await page.goto(`${REPOSITORY_URL}/blob/build-week-2026/docs/ARCHITECTURE.md`, {
    waitUntil: "domcontentloaded",
  });
  await pause(8000);

  await page.close();
  await context.close();
  const recordedPath = await video.path();
  await rm(RAW_VIDEO_PATH, { force: true });
  await writeFile(RAW_VIDEO_PATH, await readFile(recordedPath));
  return RAW_VIDEO_PATH;
}

async function captureGallerySources(browser, report) {
  await mkdir(SCREENSHOT_DIR, { recursive: true });
  const context = await browser.newContext({ viewport: { width: 1800, height: 1200 } });
  const page = await context.newPage();
  await openResearch(page);

  await page.locator("#research-prefer-gpt").uncheck();
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "cover-base.png") });
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "ai-research-input.png") });

  await showLiveResult(page, report, false);
  await scrollToText(page, "🧰 Tool execution timeline", 250);
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "live-gpt-tool-timeline.png") });

  await page.locator("#research-mode").scrollIntoViewIfNeeded();
  await showFixedDemo(page, false);
  await scrollToText(page, "🟢 Bull case", 250);
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "evidence-report.png") });
  await scrollToText(page, "🧪 Backtest comparison", 250);
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "backtest-comparison.png") });

  await context.close();
}

async function main() {
  await mkdir(RAW_DIR, { recursive: true });
  const report = await loadLiveReport();
  const server = await startApplication();
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const videoPath = await recordProductDemo(browser, report);
    await captureGallerySources(browser, report);
    const entries = await readdir(SCREENSHOT_DIR);
    process.stdout.write(JSON.stringify({
      pass: true,
      video: path.relative(ROOT, videoPath).replaceAll("\\", "/"),
      gallery_sources: entries.sort().map((name) =>
        path.relative(ROOT, path.join(SCREENSHOT_DIR, name)).replaceAll("\\", "/")),
    }, null, 2) + "\n");
  } finally {
    if (browser) await browser.close();
    await stopApplication(server);
  }
}

main().catch((error) => {
  process.stderr.write(`Recording failed: ${error.message}\n`);
  process.exitCode = 1;
});
