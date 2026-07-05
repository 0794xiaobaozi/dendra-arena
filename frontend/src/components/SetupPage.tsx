import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight, Camera, Check, ChevronDown, CircleAlert, ClipboardCheck, Copy, Database,
  Eye, FileCode2, FileText, FolderOpen, Gauge, Import, ListChecks, Pencil, Play,
  Plus, RefreshCw, Save, Search, Settings2, ShieldCheck, SlidersHorizontal, Sparkles,
  Square, Trash2, Upload, WandSparkles, Zap,
} from "lucide-react";
import { demoShocks } from "../mockData";
import { subscribeFrame } from "../frameBus";
import { useArenaStore } from "../store";
import {
  chooseSaveDirectory, listCameras, lockSessionForRun, runPreflight, saveSessionDraft,
  startSetupCameraPreview, stopSetupCameraPreview, validateRoi,
  armStimulator, chooseProtocolYaml, disarmStimulator, dryRunProtocol, generateShockSchedule,
  importProtocolYaml, listProtocolTemplates, loadProtocolTemplate, runStimulatorTest,
  saveProtocolTemplate, validateProtocolTemplate,
  type CameraDeviceModel, type PreflightModel, type ProtocolDraftModel, type ProtocolSummaryModel,
} from "../setupBackend";
import "../setup.css";

type SetupTab = "session" | "protocol";
type EditorTab = "form" | "yaml";

interface SessionBoxDraft {
  id: string;
  label: string;
  color: string;
  camera: string;
  protocol: string;
  instanceName: string;
  roi: { mode: "Rectangle" | "Full Frame"; x: number; y: number; width: number; height: number } | null;
  useFreezeDefaults: boolean;
  freeze: { threshold: number; minDuration: number; exitThreshold: number; minMoveDuration: number };
  useTemplateSchedule: boolean;
  shockEnabled: boolean;
}

const protocolOptions = ["Fear Conditioning v2", "Open Field 10min", "Shock Habituation"];
const cameraOptions = ["Camera 1 (USB3.0)", "Camera 2 (USB3.0)", "Camera 3 (USB3.0)", "Camera 4 (USB3.0)"];
const boxColors = ["#2774f6", "#8b5cf6", "#f59e0b", "#18b8c9", "#ec4899", "#22c55e"];

const initialBoxes: SessionBoxDraft[] = ["A", "B", "C", "D"].map((letter, index) => ({
  id: `box-${index + 1}`,
  label: `Box ${letter}`,
  color: boxColors[index],
  camera: cameraOptions[index],
  protocol: index < 2 ? protocolOptions[0] : protocolOptions[1],
  instanceName: `Box${letter}_${index < 2 ? "FC_v2" : "OF_10m"}`,
  roi: { mode: "Rectangle", x: 120, y: 80, width: 1280, height: 720 },
  useFreezeDefaults: true,
  freeze: { threshold: 0.65, minDuration: 1, exitThreshold: 0.85, minMoveDuration: 0.2 },
  useTemplateSchedule: true,
  shockEnabled: index < 2,
}));

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (checked: boolean) => void; label: string }) {
  return <button type="button" role="switch" aria-checked={checked} aria-label={label} className={`setup-toggle ${checked ? "on" : ""}`} onClick={() => onChange(!checked)}><i /></button>;
}

function SetupPreview({ boxId, roiConfig, live = false, editing = false, onRoiChange, onCommit, onCancel }: { boxId: string; roiConfig?: SessionBoxDraft["roi"]; live?: boolean; editing?: boolean; onRoiChange?: (roi: NonNullable<SessionBoxDraft["roi"]>) => void; onCommit?: () => void; onCancel?: () => void }) {
  const [frame, setFrame] = useState<string | null>(null);
  const drag = useRef<{ mode: string; startX: number; startY: number; roi: NonNullable<SessionBoxDraft["roi"]> } | null>(null);
  useEffect(() => subscribeFrame(boxId, ({ data }) => setFrame(`data:image/jpeg;base64,${data}`)), [boxId]);
  useEffect(() => {
    if (!editing) return;
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel?.();
      if (event.key === "Enter") onCommit?.();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [editing, onCancel, onCommit]);
  const roiStyle = roiConfig ? { left: `${roiConfig.x / 19.2}%`, top: `${roiConfig.y / 10.8}%`, width: `${roiConfig.width / 19.2}%`, height: `${roiConfig.height / 10.8}%` } : undefined;
  const startDrag = (event: React.PointerEvent, mode: string) => {
    if (!editing || !roiConfig) return;
    event.preventDefault(); event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { mode, startX: event.clientX, startY: event.clientY, roi: { ...roiConfig } };
  };
  const moveDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    const active = drag.current;
    if (!active || !onRoiChange) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const dx = (event.clientX - active.startX) / bounds.width * 1920;
    const dy = (event.clientY - active.startY) / bounds.height * 1080;
    let { x, y, width, height } = active.roi;
    if (active.mode === "move") { x = Math.max(0, Math.min(1920 - width, x + dx)); y = Math.max(0, Math.min(1080 - height, y + dy)); }
    else {
      let left = x, top = y, right = x + width, bottom = y + height;
      if (active.mode.includes("w")) left = Math.max(0, Math.min(right - 20, left + dx));
      if (active.mode.includes("e")) right = Math.min(1920, Math.max(left + 20, right + dx));
      if (active.mode.includes("n")) top = Math.max(0, Math.min(bottom - 20, top + dy));
      if (active.mode.includes("s")) bottom = Math.min(1080, Math.max(top + 20, bottom + dy));
      x = left; y = top; width = right - left; height = bottom - top;
    }
    onRoiChange({ ...active.roi, x: Math.round(x), y: Math.round(y), width: Math.round(width), height: Math.round(height) });
  };
  return <div className={`setup-camera-preview ${editing ? "roi-editing" : ""}`} tabIndex={editing ? 0 : -1} onPointerMove={moveDrag} onPointerUp={() => { drag.current = null; }}>{live && frame ? <img src={frame} alt={`${boxId} live preview`} /> : <><div className="setup-preview-floor" /><div className="setup-preview-mouse" /></>}{roiConfig && <div className="setup-preview-roi" style={roiStyle} onPointerDown={(event) => startDrag(event, "move")}><i onPointerDown={(event) => startDrag(event, "nw")} /><i onPointerDown={(event) => startDrag(event, "ne")} /><i onPointerDown={(event) => startDrag(event, "sw")} /><i onPointerDown={(event) => startDrag(event, "se")} />{editing && <b>{roiConfig.x}, {roiConfig.y} · {roiConfig.width} × {roiConfig.height}</b>}</div>}<span><i />{editing ? "Editing ROI · Enter to save · Esc to cancel" : live ? "Live" : "Ready"}</span></div>;
}

function Field({ label, children, className = "" }: { label: string; children: React.ReactNode; className?: string }) {
  return <label className={`setup-field ${className}`}><span>{label}</span>{children}</label>;
}

function SectionTitle({ icon, title, action }: { icon: React.ReactNode; title: string; action?: React.ReactNode }) {
  return <div className="setup-section-title"><span>{icon}<strong>{title}</strong></span>{action}</div>;
}

function SessionSetup({ onOpenProtocolLab, onReady }: { onOpenProtocolLab: () => void; onReady: () => void }) {
  const diskFreeGB = useArenaStore((state) => state.system.diskFreeGB);
  const [name, setName] = useState("Fear Conditioning_2026-07-03");
  const [saveDir, setSaveDir] = useState("D:\\Data\\2026-07-03_FC\\");
  const [notes, setNotes] = useState("Morning cohort - Contextual FC.");
  const [boxes, setBoxes] = useState(initialBoxes);
  const [selectedBoxId, setSelectedBoxId] = useState(initialBoxes[0].id);
  const [devices, setDevices] = useState<CameraDeviceModel[]>([]);
  const [hardwareLoading, setHardwareLoading] = useState(true);
  const [preflight, setPreflight] = useState<PreflightModel | null>(null);
  const [feedback, setFeedback] = useState<string>("");
  const [previewingBoxId, setPreviewingBoxId] = useState<string | null>(null);
  const [roiEditing, setRoiEditing] = useState(false);
  const [roiSnapshot, setRoiSnapshot] = useState<SessionBoxDraft["roi"]>(null);
  const editingRoiRef = useRef<SessionBoxDraft["roi"]>(null);
  const [loadedShocks, setLoadedShocks] = useState(demoShocks);
  const selected = boxes.find((box) => box.id === selectedBoxId) ?? boxes[0];
  editingRoiRef.current = selected.roi;
  const updateSelected = (patch: Partial<SessionBoxDraft>) => setBoxes((items) => items.map((box) => box.id === selected.id ? { ...box, ...patch } : box));
  const updateFreeze = (key: keyof SessionBoxDraft["freeze"], value: number) => updateSelected({ freeze: { ...selected.freeze, [key]: value } });
  const totalShockTime = loadedShocks.reduce((sum, shock) => sum + shock.durationSec, 0);
  const locallyComplete = Boolean(name.trim() && saveDir.trim() && boxes.every((box) => box.camera !== "Unassigned" && box.protocol !== "Unassigned" && box.roi));
  const availableCameraOptions = devices.length ? devices.map((device) => device.displayName) : cameraOptions;
  const sessionDraft = useMemo(() => ({
    name, saveDir, notes, minimumFreeGB: 5,
    boxes: boxes.map((box) => ({ ...box, cameraId: devices.find((device) => device.displayName === box.camera)?.deviceId ?? box.camera, protocolTemplateId: box.protocol, roi: box.roi ? { ...box.roi, mode: box.roi.mode === "Full Frame" ? "full_frame" : "rectangle", imageWidth: 1920, imageHeight: 1080 } : null })),
  }), [boxes, devices, name, notes, saveDir]);

  useEffect(() => {
    let active = true;
    void listCameras().then((items) => {
      if (!active) return;
      setDevices(items);
      setBoxes((current) => current.map((box, index) => items[index] ? { ...box, camera: items[index].displayName } : box));
    }).catch((error) => setFeedback(`Camera enumeration failed: ${error instanceof Error ? error.message : String(error)}`)).finally(() => active && setHardwareLoading(false));
    return () => { active = false; void stopSetupCameraPreview(); };
  }, []);

  useEffect(() => {
    let active = true;
    void (async () => {
      const summaries = await listProtocolTemplates();
      if (!active) return;
      const summary = summaries.find((s) => s.name === selected.protocol);
      if (!summary) return;
      try {
        const protocol = await loadProtocolTemplate(summary.id);
        if (!active) return;
        const shocks = protocol.shocks.map((s) => ({ id: s.id, timeSec: s.timeSec, durationSec: s.durationSec, intensityMA: s.intensityMA, status: "pending" as const }));
        setLoadedShocks(shocks);
        useArenaStore.getState().setShocks(shocks);
      } catch { /* keep current */ }
    })();
    return () => { active = false; };
  }, [selected.protocol, selected.id]);

  const handleChooseDirectory = async () => {
    const selectedPath = await chooseSaveDirectory();
    if (selectedPath) { setSaveDir(selectedPath); setPreflight(null); }
  };
  const handlePreflight = async () => {
    setFeedback("Running preflight…");
    try {
      const result = await runPreflight(sessionDraft);
      setPreflight(result);
      setFeedback(result.canRun ? "Preflight passed" : result.blockingReasons.join(" · "));
      return result;
    } catch (error) {
      setFeedback(`Preflight failed: ${error instanceof Error ? error.message : String(error)}`);
      return null;
    }
  };
  const handleSave = async () => {
    try { const result = await saveSessionDraft(sessionDraft); setFeedback(result.path ? `Draft saved: ${String(result.path)}` : "Draft validated in browser preview"); }
    catch (error) { setFeedback(`Save failed: ${error instanceof Error ? error.message : String(error)}`); }
  };
  const handleReady = async () => {
    const result = await handlePreflight();
    if (!result?.canRun) return;
    try { await lockSessionForRun(sessionDraft); onReady(); }
    catch (error) { setFeedback(`Lock failed: ${error instanceof Error ? error.message : String(error)}`); }
  };
  const handleCameraTest = async () => {
    try {
      if (previewingBoxId === selected.id) { await stopSetupCameraPreview(); setPreviewingBoxId(null); return; }
      const device = devices.find((item) => item.displayName === selected.camera);
      if (!device) throw new Error("Selected camera is unavailable");
      await startSetupCameraPreview(selected.id, device);
      setPreviewingBoxId(selected.id);
    } catch (error) { setFeedback(`Camera test failed: ${error instanceof Error ? error.message : String(error)}`); }
  };
const beginRoiEdit = () => {
    const roi = selected.roi ?? { mode: "Rectangle" as const, x: 120, y: 80, width: 1280, height: 720 };
    setRoiSnapshot(selected.roi ? { ...selected.roi } : null);
    updateSelected({ roi: { ...roi } });
    setRoiEditing(true);
  };
  const cancelRoiEdit = () => { updateSelected({ roi: roiSnapshot }); setRoiEditing(false); setFeedback("ROI edit cancelled"); };
  const commitRoiEdit = async () => {
    const roi = editingRoiRef.current;
    if (!roi) { setRoiEditing(false); setFeedback("ROI is missing — click Edit ROI first"); return; }
    try {
      const result = await validateRoi({ ...roi, mode: roi.mode === "Full Frame" ? "full_frame" : "rectangle", imageWidth: 1920, imageHeight: 1080 });
      const errors = Array.isArray(result.errors) ? result.errors as string[] : [];
      if (!result.valid) { setFeedback(`ROI invalid: ${errors.join(" · ")}`); return; }
      setRoiEditing(false); setPreflight(null); setFeedback(`ROI saved: ${roi.width} × ${roi.height}`);
    } catch (error) {
      setRoiEditing(false);
      setFeedback(`ROI validation failed: ${error instanceof Error ? error.message : String(error)}`);
    }
  };
  const addBox = () => {
    const index = boxes.length;
    const next: SessionBoxDraft = {
      id: `box-${index + 1}`, label: `Box ${String.fromCharCode(65 + index)}`, color: boxColors[index % boxColors.length],
      camera: "Unassigned", protocol: "Unassigned", instanceName: `Box${String.fromCharCode(65 + index)}_draft`, roi: null,
      useFreezeDefaults: true, freeze: { threshold: 0.65, minDuration: 1, exitThreshold: 0.85, minMoveDuration: 0.2 },
      useTemplateSchedule: true, shockEnabled: false,
    };
    setBoxes((items) => [...items, next]);
    setSelectedBoxId(next.id);
  };

  return <div className="session-setup-layout">
    <aside className="session-left setup-scroll-column">
      <section className="setup-card experiment-card">
        <SectionTitle icon={<FileText size={15} />} title="Experiment" />
        <Field label="Experiment Name"><input value={name} onChange={(event) => setName(event.target.value)} /></Field>
        <Field label="Save Directory"><div className="setup-input-action"><input value={saveDir} onChange={(event) => { setSaveDir(event.target.value); setPreflight(null); }} /><button aria-label="Choose save directory" onClick={() => void handleChooseDirectory()}><FolderOpen size={14} /></button></div></Field>
        <Field label="Notes"><textarea value={notes} onChange={(event) => setNotes(event.target.value)} /></Field>
      </section>

      <section className="setup-card boxes-card">
        <SectionTitle icon={<Database size={15} />} title={`Boxes (${boxes.length})`} action={<button className="setup-small-button" onClick={addBox}><Plus size={13} />Add Box</button>} />
        <div className="setup-box-list">{boxes.map((box) => <button key={box.id} className={`setup-box-item ${box.id === selected.id ? "selected" : ""}`} onClick={() => setSelectedBoxId(box.id)} style={{ "--box-color": box.color } as React.CSSProperties}>
          <i className="box-color-line" /><span><strong>{box.label}</strong><small>{box.camera}</small><small>Protocol: <b>{box.protocol}</b></small></span><em><i className={box.roi && box.camera !== "Unassigned" ? "ok" : "warning"} />{box.roi && box.camera !== "Unassigned" ? "Active" : "Incomplete"}</em>
        </button>)}</div>
      </section>

      <section className="setup-card setup-system-card">
        <SectionTitle icon={<Gauge size={15} />} title="System Status" />
        <ul className="setup-check-list">
          <li className={!hardwareLoading && !devices.length ? "error" : ""}>{hardwareLoading ? <RefreshCw /> : devices.length ? <Check /> : <CircleAlert />}{hardwareLoading ? "Detecting Cameras…" : `${devices.length} Cameras Detected`}</li><li><Check />{boxes.length} Boxes Configured</li>
          <li className={preflight?.stimulator.connected ? "" : "warning"}>{preflight?.stimulator.connected ? <Check /> : <CircleAlert />}Shock Controller {preflight?.stimulator.connected ? "Connected" : "Not verified"}<span>{preflight?.stimulator.device_id ?? "USB"}</span></li><li className={preflight && !preflight.directory.writable ? "error" : ""}>{preflight && !preflight.directory.writable ? <CircleAlert /> : <Check />}Output Directory {preflight?.directory.writable === false ? "Not Writable" : "Writable"}</li>
          <li><Check />Disk Space Sufficient <span>{preflight ? `${preflight.directory.freeGB.toFixed(1)} GB` : diskFreeGB == null ? "Checking…" : `${diskFreeGB.toFixed(1)} GB`}</span></li>
        </ul>
        <button className="setup-outline-button" onClick={() => void handlePreflight()}><ShieldCheck size={15} />{preflight?.canRun ? "Preflight Passed" : "Preflight Check"}</button>
      </section>
    </aside>

    <main className="box-config-panel setup-card setup-scroll-column">
      <header className="box-config-header"><h2>{selected.label} Configuration</h2><span><i />Active</span></header>
      <section className="box-config-section camera-config-section">
        <div className="config-form-block">
          <SectionTitle icon={<Camera size={15} />} title="Camera" />
          <Field label="Select Camera"><div className="inline-control"><select value={selected.camera} onChange={(event) => { updateSelected({ camera: event.target.value }); setPreflight(null); }}><option>Unassigned</option>{availableCameraOptions.map((camera) => <option key={camera}>{camera}</option>)}</select><button className="setup-small-button" onClick={() => void handleCameraTest()}>{previewingBoxId === selected.id ? "Stop" : "Test"}</button></div></Field>
          <Field label="Resolution"><select defaultValue="1920 × 1080 (30 FPS)"><option>1920 × 1080 (30 FPS)</option><option>1280 × 720 (60 FPS)</option><option>640 × 480 (30 FPS)</option></select></Field>
        </div><SetupPreview boxId={selected.id} roiConfig={selected.roi} live={previewingBoxId === selected.id} />
      </section>

      <section className="box-config-section roi-config-section" id="setup-roi-section">
        <div className="config-form-block">
          <SectionTitle icon={<SlidersHorizontal size={15} />} title="ROI (Region of Interest)" />
          <Field label="ROI Mode"><select value={selected.roi?.mode ?? "Rectangle"} onChange={(event) => updateSelected({ roi: selected.roi ? { ...selected.roi, mode: event.target.value as "Rectangle" | "Full Frame" } : { mode: "Rectangle", x: 120, y: 80, width: 1280, height: 720 } })}><option>Rectangle</option><option>Full Frame</option></select></Field>
          <div className="roi-coordinate-grid">{(["x", "y", "width", "height"] as const).map((key) => <Field label={key === "width" ? "W" : key === "height" ? "H" : key.toUpperCase()} key={key}><input type="number" value={selected.roi?.[key] ?? 0} onChange={(event) => selected.roi && updateSelected({ roi: { ...selected.roi, [key]: Number(event.target.value) } })} /></Field>)}</div>
          <div className="setup-button-row"><button className="setup-outline-button" onClick={() => roiEditing ? void commitRoiEdit() : beginRoiEdit()}><Pencil size={13} />{roiEditing ? "Save ROI" : "Edit ROI"}</button>{roiEditing && <button className="setup-plain-button" onClick={cancelRoiEdit}>Cancel</button>}<button className="setup-plain-button" onClick={() => { updateSelected({ roi: null }); setRoiEditing(false); setPreflight(null); }}><Trash2 size={13} />Clear ROI</button></div>
        </div><SetupPreview boxId={selected.id} roiConfig={selected.roi} live={previewingBoxId === selected.id} editing={roiEditing} onRoiChange={(roi) => updateSelected({ roi })} onCommit={() => void commitRoiEdit()} onCancel={cancelRoiEdit} />
      </section>

      <section className="box-config-section protocol-instance-section">
        <SectionTitle icon={<FileCode2 size={15} />} title="Protocol Instance" />
        <div className="protocol-instance-grid"><Field label="Protocol Template"><select value={selected.protocol} onChange={(event) => updateSelected({ protocol: event.target.value })}><option>Unassigned</option>{protocolOptions.map((protocol) => <option key={protocol}>{protocol}</option>)}</select></Field><button className="setup-plain-button" onClick={onOpenProtocolLab}><Eye size={13} />View Template</button><Field label="Instance Name"><input value={selected.instanceName} onChange={(event) => updateSelected({ instanceName: event.target.value })} /></Field><span className="protocol-validity">1800 s (30:00) <b><Check size={12} />Valid</b></span></div>
      </section>

      <section className="box-config-section freeze-config-section">
        <SectionTitle icon={<Sparkles size={15} />} title="Freeze Detection (Overrides)" action={<label className="setup-toggle-label">Use Template Defaults <Toggle checked={selected.useFreezeDefaults} onChange={(checked) => updateSelected({ useFreezeDefaults: checked })} label="Use template freeze defaults" /></label>} />
        <div className="freeze-field-grid">{([
          ["Threshold", "threshold"], ["Min Duration (s)", "minDuration"], ["Exit Threshold", "exitThreshold"], ["Min Move Duration (s)", "minMoveDuration"],
        ] as const).map(([label, key]) => <Field label={label} key={key}><input type="number" step="0.05" disabled={selected.useFreezeDefaults} value={selected.freeze[key]} onChange={(event) => updateFreeze(key, Number(event.target.value))} /></Field>)}</div>
      </section>

      <section className="box-config-section schedule-config-section">
        <SectionTitle icon={<Zap size={15} />} title="Shock Schedule (Overrides)" action={<label className="setup-toggle-label">Use Template Schedule <Toggle checked={selected.useTemplateSchedule} onChange={(checked) => updateSelected({ useTemplateSchedule: checked })} label="Use template shock schedule" /></label>} />
        <div className="schedule-summary"><span>Total Events: <b>{loadedShocks.length}</b></span><span>First: <b>{loadedShocks[0]?.timeSec ?? 0} s</b></span><span>Last: <b>{loadedShocks.at(-1)?.timeSec ?? 0} s</b></span><span>Total Shock Time: <b>{totalShockTime.toFixed(1)} s</b></span></div>
        <div className="setup-table-scroll"><table><thead><tr><th>#</th><th>Time (s)</th><th>Duration (s)</th><th>Intensity (mA)</th><th>Notes</th></tr></thead><tbody>{loadedShocks.map((shock, index) => <tr key={shock.id}><td>{index + 1}</td><td>{shock.timeSec}</td><td>{shock.durationSec.toFixed(1)}</td><td>{shock.intensityMA.toFixed(2)}</td><td /></tr>)}</tbody></table></div>
        <button className="setup-outline-button" disabled={selected.useTemplateSchedule}><Settings2 size={14} />Edit Schedule…</button>
      </section>
    </main>

    <aside className="session-right setup-scroll-column">
      <section className="setup-card target-box-card"><SectionTitle icon={<SlidersHorizontal size={15} />} title="Session Setup" /><Field label="Target Box"><select value={selected.id} onChange={(event) => setSelectedBoxId(event.target.value)}>{boxes.map((box) => <option value={box.id} key={box.id}>{box.label}</option>)}</select></Field></section>
      <section className="setup-card quick-settings-card"><SectionTitle icon={<Settings2 size={15} />} title="Quick Settings" /><Field label="Assigned Protocol"><select value={selected.protocol} onChange={(event) => updateSelected({ protocol: event.target.value })}><option>Unassigned</option>{protocolOptions.map((protocol) => <option key={protocol}>{protocol}</option>)}</select></Field><Field label="Camera Source"><select value={selected.camera} onChange={(event) => updateSelected({ camera: event.target.value })}><option>Unassigned</option>{availableCameraOptions.map((camera) => <option key={camera}>{camera}</option>)}</select></Field><div className="quick-status-row"><span>ROI Status</span><b className={selected.roi ? "ok" : "error"}><i />{selected.roi ? `Defined (${selected.roi.width} × ${selected.roi.height})` : "Missing"}</b><button onClick={() => document.getElementById("setup-roi-section")?.scrollIntoView({ behavior: "smooth" })}><Pencil size={13} /></button></div><Field label="Freeze Preset"><select value={selected.protocol} onChange={(event) => updateSelected({ protocol: event.target.value })}><option>Unassigned</option>{protocolOptions.map((protocol) => <option key={protocol}>{protocol}</option>)}</select></Field><div className="quick-toggle-row"><span>Shock Enabled</span><Toggle checked={selected.shockEnabled} onChange={(checked) => { updateSelected({ shockEnabled: checked }); setPreflight(null); }} label="Enable shock for selected box" /></div></section>
      <section className="setup-card session-summary-card"><SectionTitle icon={<ClipboardCheck size={15} />} title="Session Summary" /><dl><div><dt>Total Boxes</dt><dd>{boxes.length}</dd></div><div><dt>Protocols</dt><dd>Mixed</dd></div><div><dt>Recording</dt><dd className="ok"><i />Enabled</dd></div><div><dt>Total Duration ({selected.label})</dt><dd>1800 s <small>(30:00)</small></dd></div><div><dt>Total Shock Events ({selected.label})</dt><dd>{selected.shockEnabled ? loadedShocks.length : 0}</dd></div><div><dt>Total Shock Time ({selected.label})</dt><dd>{selected.shockEnabled ? `${totalShockTime.toFixed(1)} s` : "0.0 s"}</dd></div></dl></section>
      <section className="setup-card validation-card"><SectionTitle icon={<ShieldCheck size={15} />} title={`Validation (${selected.label})`} /><ul className="setup-check-list">{(preflight?.boxes[selected.id] ?? [{ id: "camera", level: "success", message: "Camera assigned", blocking: false }, { id: "roi", level: selected.roi ? "success" : "error", message: selected.roi ? "ROI defined" : "ROI missing", blocking: !selected.roi }, { id: "protocol", level: "success", message: "Protocol valid", blocking: false }, { id: "freeze", level: "success", message: "Freeze settings valid", blocking: false }]).map((item) => <li key={item.id} className={item.level === "error" ? "error" : item.level === "warning" ? "warning" : ""}>{item.level === "success" ? <Check /> : <CircleAlert />}{item.message}</li>)}</ul></section>
      <section className="setup-card setup-actions-card"><SectionTitle icon={<WandSparkles size={15} />} title="Actions" /><div><button className="setup-outline-button" onClick={() => { setBoxes((items) => items.map((box) => box.id === selected.id ? box : { ...box, camera: selected.camera, protocol: selected.protocol, roi: selected.roi ? { ...selected.roi } : null, freeze: { ...selected.freeze }, useFreezeDefaults: selected.useFreezeDefaults, shockEnabled: selected.shockEnabled, useTemplateSchedule: selected.useTemplateSchedule })); setFeedback(`Copied settings from ${selected.label} to all other boxes`); }}><Copy size={14} />Copy Settings to Other Boxes</button><button className="setup-plain-button" onClick={() => { setBoxes((items) => items.map((box) => box.shockEnabled === selected.shockEnabled ? box : { ...box, shockEnabled: selected.shockEnabled })); setFeedback(`Applied ${selected.shockEnabled ? "enabled" : "disabled"} shock to all boxes`); }}><Upload size={14} />Apply Shock to All Boxes</button></div></section>
    </aside>

    <footer className="session-action-footer"><div><i className={`status-dot ${locallyComplete ? "ok" : ""}`} />{preflight ? preflight.canRun ? "System Ready" : "Preflight Blocked" : locallyComplete ? "Ready for Preflight" : "Setup Incomplete"}</div><span title={feedback}>{feedback || <>Data will be saved to: <strong>{saveDir}</strong></>}</span><div><span>Free Space: {preflight ? `${preflight.directory.freeGB.toFixed(1)} GB` : diskFreeGB == null ? "Checking…" : `${diskFreeGB.toFixed(1)} GB`}</span><button className="setup-secondary-action" onClick={() => void handleSave()}><Save size={15} />Save Session…</button><button className="setup-primary-action" disabled={!locallyComplete} onClick={() => void handleReady()}>Save &amp; Ready to Run <ArrowRight size={16} /></button></div></footer>
  </div>;
}

const registry = [
  ["Fear Conditioning v2", "1800 s · 13 shocks", "v2.1", "valid"], ["Open Field 10min", "600 s · 0 shock", "v1.2", "valid"],
  ["Shock Habituation", "900 s · 5 shocks", "v1.0", "warning"], ["Elevated Plus Maze", "300 s · 0 shock", "v1.0", "valid"],
  ["Social Interaction", "600 s · 0 shock", "v1.1", "valid"], ["Custom Protocol (Test)", "120 s · 2 shocks", "v0.1", "error"],
] as const;

const initialProtocolDraft: ProtocolDraftModel = {
  schemaVersion: 1, id: "fear_conditioning_v2", name: "Fear Conditioning v2", version: "2.1",
  description: "Contextual fear conditioning with foot shocks.", author: "Lab Default", totalDurationSec: 1800,
  freezeDefaults: { threshold: 0.65, minDurationSec: 1, exitThreshold: 0.85, minMoveDurationSec: 0.2, smoothingWindowFrames: 5 },
  phases: [{ name: "Baseline", startSec: 0, endSec: 120, color: "blue" }, { name: "Conditioning", startSec: 120, endSec: 1560, color: "green" }, { name: "Post", startSec: 1560, endSec: 1800, color: "purple" }],
  shocks: demoShocks.map((shock) => ({ id: shock.id, timeSec: shock.timeSec, durationSec: shock.durationSec, intensityMA: shock.intensityMA, notes: "" })),
};

function ProtocolLab() {
  const [selectedProtocol, setSelectedProtocol] = useState<string>(registry[0][0]);
  const [editorTab, setEditorTab] = useState<EditorTab>("form");
  const [summaries, setSummaries] = useState<ProtocolSummaryModel[]>([]);
  const [draft, setDraft] = useState<ProtocolDraftModel>(initialProtocolDraft);
  const [validation, setValidation] = useState<{ valid: boolean; errors: string[]; warnings: string[]; hash?: string }>({ valid: true, errors: [], warnings: ["Exit threshold is high (0.85)"] });
  const [labFeedback, setLabFeedback] = useState("");
  const [stimTestOpen, setStimTestOpen] = useState(false);
  const [stimConfirmed, setStimConfirmed] = useState(false);
  const [stimCurrent, setStimCurrent] = useState(0.2);
  const [stimDuration, setStimDuration] = useState(0.5);
  const refreshRegistry = async () => {
    try { setSummaries(await listProtocolTemplates()); }
    catch (error) { setLabFeedback(`Registry refresh failed: ${error instanceof Error ? error.message : String(error)}`); }
  };
  useEffect(() => { void refreshRegistry(); }, []);
  const filtered = useMemo(() => summaries.length ? summaries.map((item) => [item.name, `${item.totalDurationSec} s · ${item.shockCount} shocks`, item.version.startsWith("v") ? item.version : `v${item.version}`, item.validationStatus] as const) : registry, [summaries]);
  const selectProtocol = async (name: string) => {
    setSelectedProtocol(name);
    const summary = summaries.find((item) => item.name === name);
    if (!summary) return;
    try {
      const loaded = await loadProtocolTemplate(summary.id);
      setDraft(loaded);
      setValidation(loaded.validation ?? { valid: true, errors: [], warnings: [] });
    } catch (error) { setLabFeedback(`Protocol load failed: ${error instanceof Error ? error.message : String(error)}`); }
  };
  const handleImport = async () => {
    const path = await chooseProtocolYaml(); if (!path) return;
    try { const imported = await importProtocolYaml(path); setDraft(imported); setSelectedProtocol(imported.name); setValidation(imported.validation ?? { valid: true, errors: [], warnings: [] }); await refreshRegistry(); setLabFeedback(`Imported ${imported.name}`); }
    catch (error) { setLabFeedback(`Import failed: ${error instanceof Error ? error.message : String(error)}`); }
  };
  const handleValidate = async () => {
    try { const result = await validateProtocolTemplate(draft) as unknown as { valid: boolean; errors: string[]; warnings: string[]; hash: string }; setValidation(result); return result; }
    catch (error) { setLabFeedback(`Validation failed: ${error instanceof Error ? error.message : String(error)}`); return null; }
  };
  const handleSaveProtocol = async () => {
    const result = await handleValidate(); if (!result?.valid) return;
    try { const saved = await saveProtocolTemplate(draft); setDraft(saved); await refreshRegistry(); setLabFeedback(`Saved ${saved.name} · ${saved.hash?.slice(0, 12)}`); }
    catch (error) { setLabFeedback(`Save failed: ${error instanceof Error ? error.message : String(error)}`); }
  };
  const handleSaveAsNewVersion = async () => {
    const numeric = Number.parseFloat(draft.version || "0");
    const next = { ...draft, version: Number.isFinite(numeric) ? (numeric + 0.1).toFixed(1) : "1.0" };
    try {
      const checked = await validateProtocolTemplate(next) as unknown as { valid: boolean; errors: string[]; warnings: string[]; hash: string };
      setValidation(checked);
      if (!checked.valid) return;
      const saved = await saveProtocolTemplate(next);
      setDraft(saved); await refreshRegistry(); setLabFeedback(`Saved new version ${saved.version}`);
    } catch (error) { setLabFeedback(`Save as new version failed: ${error instanceof Error ? error.message : String(error)}`); }
  };
  const handleGenerate = async () => {
    try { const result = await generateShockSchedule({ mode: "fixed", startTimeSec: 120, endTimeSec: 1560, intervalSec: 120, durationSec: 2, intensityMA: 0.8, jitterSec: 0, seed: 42 }); setDraft((current) => ({ ...current, shocks: result.events as ProtocolDraftModel["shocks"] })); setLabFeedback(`Generated ${(result.events as unknown[]).length} deterministic events`); }
    catch (error) { setLabFeedback(`Schedule generation failed: ${error instanceof Error ? error.message : String(error)}`); }
  };
  const handleDryRun = async () => {
    try { const result = await dryRunProtocol(draft); const lines = result.lines as string[]; setLabFeedback(`Dry run passed · ${lines.length} log lines · ${lines.at(-1)}`); }
    catch (error) { setLabFeedback(`Dry run failed: ${error instanceof Error ? error.message : String(error)}`); }
  };
  const handleStimulatorTest = async () => {
    if (!stimConfirmed) return;
    try { await armStimulator(true); const result = await runStimulatorTest(stimCurrent, stimDuration); setLabFeedback(`Test pulse sent · ${String(result.durationUnits)} protocol units`); setStimTestOpen(false); }
    catch (error) { setLabFeedback(`Stimulator test blocked: ${error instanceof Error ? error.message : String(error)}`); }
    finally { await disarmStimulator().catch(() => undefined); setStimConfirmed(false); }
  };
  return <div className="protocol-lab-layout">
    <aside className="protocol-registry setup-card setup-scroll-column"><small>PROTOCOL REGISTRY</small><div className="registry-toolbar"><button className="setup-outline-button" onClick={() => { setDraft({ ...initialProtocolDraft, id: "new_protocol", name: "New Protocol", version: "0.1", totalDurationSec: 600, shocks: [] }); setSelectedProtocol("New Protocol"); }}><Plus size={13} />New Protocol</button><button className="setup-plain-button" onClick={() => void handleImport()}><Import size={13} />Import YAML</button><button className="setup-plain-button"><Upload size={13} />Export</button><button className="setup-plain-button" onClick={() => void refreshRegistry()}><RefreshCw size={13} />Refresh</button></div><div className="registry-filters"><label><Search size={13} /><input placeholder="Search protocols…" /></label><select><option>All Status</option></select></div><div className="registry-list">{filtered.map(([name, summary, version, status]) => <button key={name} className={selectedProtocol === name ? "selected" : ""} onClick={() => void selectProtocol(name)}><span><strong>{name}</strong><em className={status}><i />{status[0].toUpperCase() + status.slice(1)}</em></span><small>{summary}</small><small>{version}</small></button>)}</div><button className="archived-protocols">Archived Protocols (3) <ChevronDown size={13} /></button></aside>

    <main className="protocol-editor setup-card setup-scroll-column"><header><div><strong>Editing: {draft.name}</strong><span className={`valid-chip ${validation.valid ? "" : "invalid"}`}>{validation.valid ? "Valid" : "Error"}</span><small>v{draft.version}</small></div><div><button className="setup-plain-button" onClick={() => { setDraft((current) => ({ ...current, id: `${current.id}_copy`, name: `${current.name} Copy`, version: "0.1" })); setSelectedProtocol(`${draft.name} Copy`); }}><Copy size={13} />Duplicate</button><button className="setup-plain-button" onClick={() => void handleSaveProtocol()}><Save size={13} />Save</button><button className="setup-primary-action" onClick={() => void handleSaveAsNewVersion()}>Save As New Version</button></div></header><nav className="editor-tabs"><button className={editorTab === "form" ? "active" : ""} onClick={() => setEditorTab("form")}>Form View</button><button className={editorTab === "yaml" ? "active" : ""} onClick={() => setEditorTab("yaml")}>YAML View</button></nav>{editorTab === "yaml" ? <textarea className="protocol-yaml-editor" value={JSON.stringify(draft, null, 2)} readOnly /> : <div className="protocol-form-grid"><div>
      <section className="protocol-editor-section"><SectionTitle icon={<FileText size={14} />} title="Basic Information" /><div className="basic-info-grid"><Field label="Protocol ID"><input value={draft.id} onChange={(event) => setDraft((current) => ({ ...current, id: event.target.value }))} /></Field><Field label="Total Duration (s)"><input type="number" value={draft.totalDurationSec} onChange={(event) => setDraft((current) => ({ ...current, totalDurationSec: Number(event.target.value) }))} /></Field><Field label="Name"><input value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} /></Field><Field label="Author"><input value={draft.author} onChange={(event) => setDraft((current) => ({ ...current, author: event.target.value }))} /></Field><Field label="Version"><input value={draft.version} onChange={(event) => setDraft((current) => ({ ...current, version: event.target.value }))} /></Field><Field label="Created"><span>2025-05-10 14:22</span></Field><Field label="Description"><textarea value={draft.description} onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))} /></Field><Field label="Updated"><span>2025-05-20 10:31</span></Field></div></section>
      <section className="protocol-editor-section"><SectionTitle icon={<ListChecks size={14} />} title="Phases (3)" action={<button className="setup-small-button"><Plus size={12} />Add Phase</button>} /><table className="compact-editor-table"><thead><tr><th>#</th><th>Name</th><th>Start (s)</th><th>End (s)</th><th>Color</th></tr></thead><tbody><tr><td>1</td><td>Baseline</td><td>0</td><td>120</td><td><i className="phase-color blue" /></td></tr><tr><td>2</td><td>Conditioning</td><td>120</td><td>1560</td><td><i className="phase-color green" /></td></tr><tr><td>3</td><td>Post</td><td>1560</td><td>1800</td><td><i className="phase-color purple" /></td></tr></tbody></table></section>
      <section className="protocol-editor-section"><SectionTitle icon={<Sparkles size={14} />} title="Freeze Detection Defaults" /><div className="freeze-field-grid"><Field label="Threshold"><input defaultValue="0.65" /></Field><Field label="Min Duration (s)"><input defaultValue="1.00" /></Field><Field label="Exit Threshold"><input defaultValue="0.85" /></Field><Field label="Min Move Duration (s)"><input defaultValue="0.20" /></Field><Field label="Smoothing Window"><input defaultValue="5" /></Field><Field label="Motion Metric"><select><option>Mean Pixel Change</option></select></Field></div></section>
      <section className="protocol-editor-section"><SectionTitle icon={<Zap size={14} />} title="Shock Settings" /><div className="shock-settings-grid"><Field label="Enabled"><Toggle checked={true} onChange={() => undefined} label="Enable protocol shocks" /></Field><Field label="Type"><select><option>Foot Shock</option></select></Field><Field label="Default Intensity (mA)"><input defaultValue="0.80" /></Field><Field label="Default Duration (s)"><input defaultValue="2.0" /></Field></div><div className="safety-limits"><strong>Safety Limits</strong><Field label="Min Intensity (mA)"><input defaultValue="0.10" /></Field><Field label="Max Intensity (mA)"><input defaultValue="2.00" /></Field><Field label="Max Duration (s)"><input defaultValue="5.0" /></Field></div></section>
    </div><div>
      <section className="protocol-editor-section schedule-editor"><SectionTitle icon={<Zap size={14} />} title="Shock Schedule" action={<label className="setup-toggle-label">Enable Schedule <Toggle checked={draft.shocks.length > 0} onChange={(checked) => !checked && setDraft((current) => ({ ...current, shocks: [] }))} label="Enable protocol schedule" /></label>} /><div className="schedule-tools"><button onClick={() => setDraft((current) => ({ ...current, shocks: [...current.shocks, { id: `shock-${current.shocks.length + 1}`, timeSec: 0, durationSec: 2, intensityMA: 0.8, notes: "" }] }))}><Plus />Add Event</button><button onClick={() => void handleGenerate()}><WandSparkles />Generate Pattern</button><button><Import />Import CSV</button><button onClick={() => setDraft((current) => ({ ...current, shocks: [] }))}><Trash2 />Clear All</button></div><div className="schedule-summary"><span>Total Events: <b>{draft.shocks.length}</b></span><span>First: <b>{draft.shocks[0]?.timeSec ?? 0} s</b></span><span>Last: <b>{draft.shocks.at(-1)?.timeSec ?? 0} s</b></span><span>Total Shock Time: <b>{draft.shocks.reduce((sum, shock) => sum + shock.durationSec, 0).toFixed(1)} s</b></span></div><div className="setup-table-scroll tall"><table><thead><tr><th>#</th><th>Time (s)</th><th>Duration (s)</th><th>Intensity (mA)</th><th>Notes</th></tr></thead><tbody>{draft.shocks.map((shock, index) => <tr key={shock.id}><td>{index + 1}</td><td>{shock.timeSec}</td><td>{shock.durationSec.toFixed(1)}</td><td>{shock.intensityMA.toFixed(2)}</td><td>{shock.notes}</td></tr>)}</tbody></table></div></section>
      <section className="protocol-editor-section schedule-generator"><SectionTitle icon={<WandSparkles size={14} />} title="Schedule Generator" /><nav><button className="active">Fixed Interval</button><button>Random Interval</button><button>Manual Input</button></nav><div>{[["Start Time (s)","120"],["End Time (s)","1560"],["Interval (s)","120"],["Duration (s)","2.0"],["Intensity (mA)","0.80"],["Jitter (s)","0"],["Seed","42"]].map(([label,value]) => <Field label={label} key={label}><input defaultValue={value} /></Field>)}<button className="setup-primary-action" onClick={() => void handleGenerate()}>Generate Events</button></div></section>
    </div></div>}</main>

    <aside className="protocol-inspector setup-card setup-scroll-column"><section><h3>Validation</h3><div className={`protocol-valid-hero ${validation.valid ? "" : "invalid"}`}><ShieldCheck /><strong>{validation.valid ? "Protocol is valid" : "Protocol has blocking errors"}</strong><span>{validation.valid ? "No blocking issues found." : validation.errors[0]}</span></div><div className="validation-counts"><span><b>{validation.errors.length}</b>Errors</span><span><b>{validation.warnings.length}</b>Warnings</span><span><b>0</b>Infos</span></div><h4>Validation Details</h4><ul className="setup-check-list">{validation.errors.map((message) => <li className="error" key={message}><CircleAlert />{message}</li>)}{validation.warnings.map((message) => <li className="warning" key={message}><CircleAlert />{message}</li>)}{validation.valid && <><li><Check />Total duration is positive</li><li><Check />{draft.shocks.length} shock events</li><li><Check />All shock times within duration</li><li><Check />No overlapping shocks</li></>}</ul><button className="setup-plain-button" onClick={() => void handleValidate()}>Validate Now</button></section><section className="protocol-timeline-preview"><h3>Timeline Preview</h3><span>Total Duration: {draft.totalDurationSec} s</span><div className="phase-timeline"><i /><i /><i /></div><div className="shock-marks">{draft.shocks.slice(0, 20).map((shock) => <Zap key={shock.id} />)}</div><div className="timeline-key"><span><i className="blue" />Baseline</span><span><i className="green" />Conditioning</span><span><i className="purple" />Post</span><span><Zap />Shock</span></div></section><section className="protocol-debug"><h3>Debug &amp; Test</h3><button className="setup-outline-button" onClick={() => void handleDryRun()}><Play size={14} />Dry Run Protocol</button><button className="setup-outline-button" onClick={() => setStimTestOpen(true)}><Zap size={14} />Stimulator Test</button><button className="setup-plain-button" disabled><Upload size={14} />Export Protocol YAML</button>{labFeedback && <p className="protocol-feedback">{labFeedback}</p>}</section></aside>
    <footer className="protocol-status-footer"><span>Protocol Hash: <strong>{draft.hash?.slice(0, 16) ?? validation.hash?.slice(0, 16) ?? "unsaved"}…</strong></span><span>Location: <strong>{draft.path ?? "Not saved"}</strong></span></footer>
    {stimTestOpen && <div className="setup-modal-backdrop" role="dialog" aria-modal="true" aria-label="Stimulator Test"><div className="setup-modal"><h3>Stimulator Test</h3><p className="danger-copy">This will send a real test pulse.</p><Field label="Intensity (mA)"><input type="number" step="0.01" value={stimCurrent} onChange={(event) => setStimCurrent(Number(event.target.value))} /></Field><Field label="Duration (s)"><input type="number" step="0.1" value={stimDuration} onChange={(event) => setStimDuration(Number(event.target.value))} /></Field><label className="stim-confirm"><input type="checkbox" checked={stimConfirmed} onChange={(event) => setStimConfirmed(event.target.checked)} />I confirm the stimulator output is safely connected.</label><div><button className="setup-plain-button" onClick={() => { setStimTestOpen(false); setStimConfirmed(false); }}>Cancel</button><button className="setup-primary-action" disabled={!stimConfirmed} onClick={() => void handleStimulatorTest()}>Send Test Pulse</button></div></div></div>}
  </div>;
}

export function SetupPage({ onReady }: { onReady: () => void }) {
  const [tab, setTab] = useState<SetupTab>("session");
  return <section className="setup-shell"><nav className="setup-subnav"><button className={tab === "session" ? "active" : ""} onClick={() => setTab("session")}>Session Setup</button><button className={tab === "protocol" ? "active" : ""} onClick={() => setTab("protocol")}>Protocol Lab</button><button className="window-size-toggle" title="Toggle window size (1440 / 1152)" onClick={() => void import("../backend").then((m) => m.windowAction("toggle-size"))}><Square size={12} /></button></nav><div className={`setup-view ${tab === "session" ? "active" : ""}`}><SessionSetup onOpenProtocolLab={() => setTab("protocol")} onReady={onReady} /></div><div className={`setup-view ${tab === "protocol" ? "active" : ""}`}><ProtocolLab /></div></section>;
}
