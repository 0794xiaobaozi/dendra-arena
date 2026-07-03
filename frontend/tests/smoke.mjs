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
  const statusText = await page.locator(".system-statusbar").textContent();
  if (!statusText.includes(`${expectedDisk.toFixed(1)} GB free`)) throw new Error("Disk space must match the local save drive");
  if (await page.locator(".camera-card").count() !== 4) throw new Error("Run page must show four camera cards");
  await page.locator(".camera-list-item").nth(1).click();
  if (await page.locator(".camera-card.selected h3").textContent() !== "Box B") throw new Error("Box selection is not synchronized");
  await page.locator(".motion-tabs button").nth(3).click();
  if (await page.locator(".motion-tabs button.active").textContent() !== "Box D") throw new Error("Motion selection must remain independent");
  if (await page.getByRole("button", { name: "Setup", exact: true }).isEnabled()) throw new Error("Setup must stay disabled during Run-only development");
  if (await page.getByRole("button", { name: "Review", exact: true }).isEnabled()) throw new Error("Review must stay disabled during Run-only development");
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
    if (camera.x + camera.width > protocol.x + 1 || Math.abs(camera.y - protocol.y) > 1) throw new Error(`Top row is misaligned at ${viewport.width}x${viewport.height}`);
    if (monitor.y < Math.max(camera.y + camera.height, protocol.y + protocol.height) - 1) throw new Error(`Monitor overlaps top row at ${viewport.width}x${viewport.height}`);
    if (monitor.x > camera.x + 1 || monitor.x + monitor.width < protocol.x + protocol.width - 1) throw new Error(`Monitor does not span both top columns at ${viewport.width}x${viewport.height}`);
    if (actions.y < monitor.y + monitor.height - 1) throw new Error(`Actions overlap monitor at ${viewport.width}x${viewport.height}`);
    if (status.y < dashboard.y + dashboard.height - 1 || status.y + status.height > viewport.height + 1) throw new Error(`Status bar overlaps dashboard at ${viewport.width}x${viewport.height}`);
    if (shock.y + shock.height > protocol.y + protocol.height + 1) throw new Error(`Shock schedule is clipped at ${viewport.width}x${viewport.height}`);
  }
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
