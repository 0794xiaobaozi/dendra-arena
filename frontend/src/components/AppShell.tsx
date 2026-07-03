import { Activity, Check, ChevronDown, CircleStop, Database, HardDrive, Minus, MonitorUp, Play, Plus, Radio, Square, Thermometer, X } from "lucide-react";
import { CameraWall } from "./CameraWall";
import { BottomMonitorStrip } from "./MonitorStrip";
import { RightProtocolPanel } from "./ProtocolPanel";
import { useArenaStore } from "../store";
import type { AppPage } from "../types";
import { previewCommand, startExperimentCommand, stopCommand, windowAction } from "../backend";

const PAGE_LABELS: Record<AppPage, string> = { setup: "Setup", run: "Run", review: "Review" };

function CustomTitleBar() {
  return (
    <header className="titlebar" data-tauri-drag-region onDoubleClick={(event) => event.preventDefault()}>
      <div className="app-identity">
        <img className="app-logo" src="/icon.png" alt="" aria-hidden="true" />
        <strong>arena</strong>
      </div>
      <div className="window-controls">
        <button aria-label="Minimize" onClick={() => void windowAction("minimize")}><Minus size={15} /></button>
        <button aria-label="Fixed window size" title="Window size is fixed at 1440 × 1000" disabled><Square size={12} /></button>
        <button className="close" aria-label="Close" onClick={() => void windowAction("close")}><X size={16} /></button>
      </div>
    </header>
  );
}

function TopNavigationBar() {
  const { page, setPage, appState, saveDir } = useArenaStore();
  const ready = appState === "idle" ? "Ready" : appState === "previewing" ? "Previewing" : appState === "running" ? "Running" : "Stopping";
  return (
    <nav className="top-navigation">
      <div />
      <div className="segmented page-tabs">
        {(Object.keys(PAGE_LABELS) as AppPage[]).map((item) => (
          <button key={item} className={page === item ? "active" : ""} disabled={item !== "run"} onClick={() => setPage(item)}>{PAGE_LABELS[item]}</button>
        ))}
      </div>
      <div className="global-summary">
        <span className="run-status"><i className="status-dot ok" />{ready}</span>
        <span className="divider" />
        <span>Protocol: <strong>Fear Conditioning v2</strong></span>
        <span className="divider" />
        <span className="save-summary">Save to: <strong>{saveDir}</strong></span>
      </div>
    </nav>
  );
}

function CameraList() {
  const { cameras, selectedBoxId, selectBox, toggleCamera } = useArenaStore();
  return (
    <section className="camera-list-section">
      <div className="section-heading"><span>CAMERAS</span><button className="icon-button"><Plus size={16} /></button></div>
      <div className="camera-list">
        {cameras.map((camera) => (
          <button key={camera.boxId} className={`camera-list-item ${selectedBoxId === camera.boxId ? "selected" : ""}`} onClick={() => selectBox(camera.boxId)}>
            <span className="camera-device-icon"><span /></span>
            <span className="camera-list-copy"><strong>{camera.label}</strong><small>{camera.deviceName}</small></span>
            <span role="checkbox" aria-checked={camera.enabled} className={`check-toggle ${camera.enabled ? "checked" : ""}`} onClick={(event) => { event.stopPropagation(); toggleCamera(camera.boxId); }}>
              {camera.enabled && <Check size={14} strokeWidth={3} />}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}

function PreflightChecklist() {
  const { cameras, saveDir } = useArenaStore();
  const enabled = cameras.filter((camera) => camera.enabled);
  const rows = [
    ["Cameras selected", `${enabled.length} / ${cameras.length}`],
    ["ROI ready", `${enabled.filter((camera) => camera.roi.active).length} / ${enabled.length}`],
    ["Save folder", saveDir],
    ["Protocol valid", "Fear Conditioning v2"],
    ["Stimulator connected", "Shock Controller (COM3)"],
  ];
  return (
    <section className="preflight card">
      <div className="preflight-title"><strong>PREFLIGHT CHECKLIST</strong><span className="outline-ok"><Check size={13} /></span></div>
      <div className="preflight-rows">
        {rows.map(([label, value]) => <div className="preflight-row" key={label}><span className="mini-check"><Check size={11} /></span><span><strong>{label}</strong><small>{value}</small></span></div>)}
      </div>
    </section>
  );
}

function LeftSidebar() {
  const { appState, connectPreview } = useArenaStore();
  const connected = appState !== "idle";
  const handlePreview = async () => {
    try {
      if (!connected) await previewCommand();
      else await stopCommand(false);
      connectPreview();
    } catch (error) {
      window.alert(`Preview failed: ${error instanceof Error ? error.message : String(error)}`);
    }
  };
  return (
    <aside className="left-sidebar">
      <CameraList />
      <PreflightChecklist />
      <div className="connect-block">
        <button className="connect-button" onClick={() => void handlePreview()}><Radio size={19} />{connected ? "Preview Connected" : "Connect Preview"}</button>
        <span><i className={`status-dot ${connected ? "ok" : ""}`} />{connected ? "All cameras streaming" : "Cameras disconnected"}</span>
      </div>
    </aside>
  );
}

function RunActions() {
  const { appState, stop, startExperiment } = useArenaStore();
  const handleStop = async () => {
    if (appState === "running" && !window.confirm("Stop experiment? The current experiment will end and open behavior intervals will be finalized.")) return;
    await stopCommand(appState === "running");
    stop();
  };
  const handleStart = async () => {
    try {
      await startExperimentCommand();
      startExperiment();
    } catch (error) {
      window.alert(`Experiment failed to start: ${error instanceof Error ? error.message : String(error)}`);
    }
  };
  return (
    <div className="run-actions">
      <button className="secondary-action" disabled={appState === "idle"} onClick={() => void handleStop()}><CircleStop size={18} />Stop</button>
      {appState !== "running" && <button className="primary-action" disabled={appState !== "previewing"} onClick={() => void handleStart()}><Play size={17} fill="currentColor" />Start Experiment</button>}
    </div>
  );
}

function SystemStatusBar() {
  const system = useArenaStore((state) => state.system);
  return (
    <footer className="system-statusbar">
      <div><span><Thermometer size={15} />System Temperature <b className={system.temperatureC == null ? "" : "healthy"}>{system.temperatureC == null ? "Unavailable" : <><i className="status-dot ok" />{system.temperatureC.toFixed(1)} °C</>}</b></span><span><HardDrive size={15} />Disk Space <b>{system.diskFreeGB == null ? "Checking…" : <><i className="status-dot blue" />{system.diskFreeGB.toFixed(1)} GB free</>}</b></span></div>
      <div><span><Activity size={14} />Backend <b className={system.backendState === "connected" ? "healthy" : ""}>{system.backendState}</b></span><span>Python {system.pythonVersion}</span><span>•</span><span>arena {system.appVersion}</span></div>
    </footer>
  );
}

export function AppShell() {
  return (
    <div className="app-shell">
      <CustomTitleBar />
      <TopNavigationBar />
      <main className="dashboard-grid">
        <LeftSidebar />
        <section className="run-workspace">
          <div className="run-top-row">
            <CameraWall />
            <RightProtocolPanel />
          </div>
          <BottomMonitorStrip />
          <RunActions />
        </section>
      </main>
      <SystemStatusBar />
    </div>
  );
}
