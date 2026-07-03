import { execFileSync, spawn } from "node:child_process";
import { existsSync, statfsSync } from "node:fs";
import { chromium } from "playwright-core";

const port = 1421;
const url = `http://127.0.0.1:${port}`;
const candidates = [
  process.env.CHROMIUM_PATH,
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
].filter(Boolean);
const executablePath = candidates.find(existsSync);
if (!executablePath) throw new Error("Set CHROMIUM_PATH to an installed Chromium or Edge executable");

const server = spawn("npm", ["run", "dev", "--", "--host", "127.0.0.1", "--port", String(port), "--strictPort"], {
  shell: true,
  stdio: "ignore",
});

async function waitForServer() {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch { /* server is still starting */ }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error("Vite did not start within 10 seconds");
}

try {
  await waitForServer();
  const browser = await chromium.launch({ headless: true, executablePath });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const runtimeErrors = [];
  page.on("pageerror", (error) => runtimeErrors.push(error.message));
  await page.goto(url, { waitUntil: "networkidle" });
  const expectedDisk = Number(statfsSync(existsSync("C:\\") ? "C:\\" : ".").bavail * statfsSync(existsSync("C:\\") ? "C:\\" : ".").bsize) / 1024 ** 3;
  if (!(await page.getByRole("button", { name: "Setup", exact: true }).isEnabled())) throw new Error("Setup must be enabled");
  if (!(await page.locator(".setup-shell").isVisible()) || !(await page.getByRole("button", { name: "Session Setup", exact: true }).isVisible())) throw new Error("Session Setup must be the default development page");
  const setupColumns = await Promise.all([".session-left", ".box-config-panel", ".session-right"].map((selector) => page.locator(selector).boundingBox()));
  if (setupColumns.some((bounds) => !bounds) || setupColumns[0].x + setupColumns[0].width > setupColumns[1].x + 1 || setupColumns[1].x + setupColumns[1].width > setupColumns[2].x + 1) throw new Error("Session Setup must use ordered left, center, and right columns");
  const setupOverflow = await page.locator(".session-setup-layout").evaluate((element) => ({ x: element.scrollWidth > element.clientWidth + 1, y: element.scrollHeight > element.clientHeight + 1 }));
  if (setupOverflow.x || setupOverflow.y) throw new Error("Session Setup shell must fit the 1440x1000 development viewport");
  const setupStatusText = await page.locator(".setup-system-card").textContent();
  if (!setupStatusText.includes(`${expectedDisk.toFixed(1)} GB`)) throw new Error("Setup disk space must use the real local drive value");
  await page.locator(".setup-box-item").nth(1).click();
  if (await page.locator(".target-box-card select").inputValue() !== "box-2" || !(await page.locator(".box-config-header").textContent()).includes("Box B")) throw new Error("Session Setup box selection must synchronize all three columns");
  await page.locator(".experiment-card input").first().fill("Persistent Session Draft");
  const quickCardBounds = await page.locator(".quick-settings-card").boundingBox();
  const shockToggleBounds = await page.getByRole("switch", { name: "Enable shock for selected box" }).boundingBox();
  if (!quickCardBounds || !shockToggleBounds || shockToggleBounds.y + shockToggleBounds.height > quickCardBounds.y + quickCardBounds.height + 1) throw new Error("Quick Settings controls must remain inside their card");
  const rightPanelMetrics = await page.locator(".session-right").evaluate((element) => ({ scrollHeight: element.scrollHeight, clientHeight: element.clientHeight }));
  if (rightPanelMetrics.scrollHeight > rightPanelMetrics.clientHeight + 1) throw new Error(`Session Setup right panel must fit all cards at 1440x1000: ${JSON.stringify(rightPanelMetrics)}`);
  await page.getByRole("button", { name: "Protocol Lab", exact: true }).click();
  if (await page.locator(".protocol-registry").count() !== 1 || await page.locator(".protocol-editor").count() !== 1 || await page.locator(".protocol-inspector").count() !== 1) throw new Error("Protocol Lab must expose registry, editor, and inspector columns");
  await page.getByRole("button", { name: "Session Setup", exact: true }).click();
  if (await page.locator(".experiment-card input").first().inputValue() !== "Persistent Session Draft") throw new Error("Session draft must survive Protocol Lab navigation");
  await page.getByRole("button", { name: "Run", exact: true }).click();
  const statusText = await page.locator(".system-statusbar").textContent();
  if (!statusText.includes(`${expectedDisk.toFixed(1)} GB free`)) throw new Error("Disk space must match the local save drive");
  if (await page.locator(".camera-card").count() !== 4) throw new Error("Run page must show four camera cards");
  const viewportStyle = await page.locator(".video-viewport").first().evaluate((element) => {
    const style = getComputedStyle(element);
    const bounds = element.getBoundingClientRect();
    const canvas = element.querySelector("canvas");
    return {
      ratio: bounds.width / bounds.height,
      canvasObjectFit: canvas ? getComputedStyle(canvas).objectFit : "missing",
      canvasParentMatches: canvas?.parentElement === element,
      roiParentMatches: element.querySelector(".live-roi")?.parentElement === element,
    };
  });
  if (Math.abs(viewportStyle.ratio - 16 / 9) > 0.01) throw new Error("Camera viewport must remain 16:9");
  if (viewportStyle.canvasObjectFit !== "contain") throw new Error("Camera canvas must use object-fit: contain");
  if (!viewportStyle.canvasParentMatches || !viewportStyle.roiParentMatches) throw new Error("Canvas and ROI must share the same viewport");
  const wallStyle = await page.locator(".camera-wall").evaluate((element) => {
    const style = getComputedStyle(element);
    const cards = [...element.querySelectorAll(".camera-card")].map((card) => {
      const bounds = card.getBoundingClientRect();
      return { width: bounds.width, height: bounds.height, ratio: bounds.width / bounds.height };
    });
    const slots = [...element.querySelectorAll(".camera-slot")].map((slot) => {
      const bounds = slot.getBoundingClientRect();
      return { width: bounds.width, height: bounds.height };
    });
    return { overflowY: style.overflowY, hasVerticalOverflow: element.scrollHeight > element.clientHeight + 1, cards, slots };
  });
  if (wallStyle.overflowY !== "hidden" || wallStyle.hasVerticalOverflow) throw new Error("Camera wall must fit cards without a scrollbar");
  if (wallStyle.cards.some((card) => Math.abs(card.ratio - 4 / 3) > 0.01)) throw new Error("Camera cards must retain a 4:3 component ratio");
  if (wallStyle.slots.some((slot) => Math.abs(slot.width - wallStyle.slots[0].width) > 1 || Math.abs(slot.height - wallStyle.slots[0].height) > 1)) throw new Error("Camera wall slots must be evenly divided");
  if ((await page.locator(".timeline-legend").textContent()).includes("Shock (")) throw new Error("Shock legend must not assume a fixed duration");
  const initialCameraTitleSize = Number.parseFloat(await page.locator(".camera-card h3").first().evaluate((element) => getComputedStyle(element).fontSize));
  await page.locator(".camera-list-item").nth(1).click();
  if (await page.locator(".camera-card.selected h3").textContent() !== "Box B") throw new Error("Box selection is not synchronized");
  await page.locator(".motion-tabs button").nth(3).click();
  if (await page.locator(".motion-tabs button.active").textContent() !== "Box D") throw new Error("Motion selection must remain independent");
  if (!(await page.getByRole("button", { name: "Setup", exact: true }).isEnabled())) throw new Error("Setup must remain available from Run");
  if (await page.getByRole("button", { name: "Review", exact: true }).isEnabled()) throw new Error("Review must stay disabled during Run-only development");
  if (!(await page.getByRole("button", { name: "Toggle window size" }).isEnabled())) throw new Error("Small/large window toggle must be enabled");
  const recentEventsLayout = await page.locator(".events-card").evaluate((card) => {
    const list = card.querySelector(".event-list");
    const action = card.querySelector(".view-events");
    const eventLabel = list?.querySelector(".event-row span");
    const originalLabel = eventLabel?.textContent ?? "";
    if (eventLabel) eventLabel.textContent = "An intentionally long event description that exceeds the available panel width";
    const longContentOverflows = list ? list.scrollWidth > list.clientWidth + 1 : false;
    if (eventLabel) eventLabel.textContent = originalLabel;
    return {
      rows: getComputedStyle(card).gridTemplateRows,
      overflowX: list ? getComputedStyle(list).overflowX : "missing",
      overflowY: list ? getComputedStyle(list).overflowY : "missing",
      longContentOverflows,
      actionPosition: action ? getComputedStyle(action).position : "missing",
    };
  });
  if (recentEventsLayout.overflowX !== "auto" || recentEventsLayout.overflowY !== "auto" || !recentEventsLayout.longContentOverflows || recentEventsLayout.actionPosition !== "static") throw new Error("Recent events must scroll in both directions while keeping its action visible");
  const durationStarts = await page.locator(".event-row em").evaluateAll((elements) => elements.filter((element) => element.textContent?.trim()).map((element) => element.getBoundingClientRect().x));
  if (durationStarts.some((x) => Math.abs(x - durationStarts[0]) > 0.5)) throw new Error("Recent event duration values must share one aligned column");
  for (const viewport of [{ width: 1440, height: 1000 }, { width: 1296, height: 900 }, { width: 1152, height: 800 }]) {
    await page.setViewportSize(viewport);
    const bounds = async (selector) => page.locator(selector).boundingBox();
    const camera = await bounds(".camera-wall");
    const protocol = await bounds(".right-protocol-panel");
    const monitor = await bounds(".bottom-monitor-strip");
    const actions = await bounds(".run-actions");
    const dashboard = await bounds(".dashboard-grid");
    const status = await bounds(".system-statusbar");
    const shock = await bounds(".shock-detail");
    if (!camera || !protocol || !monitor || !actions || !dashboard || !status || !shock) throw new Error("Run layout component is missing");
    if (camera.x + camera.width > protocol.x + 1 || Math.abs(camera.y - protocol.y) > 1) throw new Error(`MainRunArea columns are misaligned at ${viewport.width}x${viewport.height}: camera=${JSON.stringify(camera)}, protocol=${JSON.stringify(protocol)}`);
    if (monitor.y < camera.y + camera.height - 1) throw new Error(`Bottom panels overlap the camera wall at ${viewport.width}x${viewport.height}`);
    if (Math.abs(monitor.x - camera.x) > 1 || Math.abs(monitor.width - camera.width) > 1) throw new Error(`Bottom panels must remain inside CenterWorkspace at ${viewport.width}x${viewport.height}`);
    if (actions.y < dashboard.y + dashboard.height - 1) throw new Error(`Bottom action bar overlaps MainRunArea at ${viewport.width}x${viewport.height}`);
    if (Math.abs(actions.x) > 1 || Math.abs(actions.width - viewport.width) > 1) throw new Error(`Bottom action bar must span the app window at ${viewport.width}x${viewport.height}`);
    if (status.y < actions.y + actions.height - 1 || status.y + status.height > viewport.height + 1) throw new Error(`Status bar overlaps the action bar at ${viewport.width}x${viewport.height}`);
    if (shock.y + shock.height > protocol.y + protocol.height + 1) throw new Error(`Shock schedule is clipped at ${viewport.width}x${viewport.height}`);
  }
  const compactCameraTitleSize = Number.parseFloat(await page.locator(".camera-card h3").first().evaluate((element) => getComputedStyle(element).fontSize));
  if (compactCameraTitleSize >= initialCameraTitleSize) throw new Error("Camera card typography must scale down with the card");
  const expandedDashboard = await page.locator(".dashboard-grid").evaluate((element) => getComputedStyle(element).gridTemplateColumns);
  await page.getByRole("button", { name: "Collapse camera sidebar" }).click();
  await page.getByRole("button", { name: "Collapse protocol panel" }).click();
  const collapsedColumns = await page.locator(".dashboard-grid").evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").map((value) => Number.parseFloat(value)));
  if (collapsedColumns[0] !== 46 || collapsedColumns.at(-1) !== 46) throw new Error(`Side panels must collapse to 46px rails; expanded columns were ${expandedDashboard}`);
  await page.getByRole("button", { name: "Expand camera sidebar" }).click();
  await page.getByRole("button", { name: "Expand protocol panel" }).click();
  if (runtimeErrors.length) throw new Error(`Runtime errors: ${runtimeErrors.join("; ")}`);
  await browser.close();
  console.log("UI smoke test passed");
} finally {
  if (process.platform === "win32") {
    try { execFileSync("taskkill", ["/pid", String(server.pid), "/t", "/f"], { stdio: "ignore" }); } catch { /* process already stopped */ }
  } else {
    server.kill("SIGTERM");
  }
}
