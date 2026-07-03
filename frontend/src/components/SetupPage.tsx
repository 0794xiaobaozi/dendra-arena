import { useMemo, useState } from "react";
import {
  ArrowRight, Camera, Check, ChevronDown, CircleAlert, ClipboardCheck, Copy, Database,
  Eye, FileCode2, FileText, FolderOpen, Gauge, Import, ListChecks, Pencil, Play,
  Plus, RefreshCw, Save, Search, Settings2, ShieldCheck, SlidersHorizontal, Sparkles,
  Trash2, Upload, WandSparkles, Zap,
} from "lucide-react";
import { demoShocks } from "../mockData";
import { useArenaStore } from "../store";
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

function SetupPreview({ roi = true }: { roi?: boolean }) {
  return <div className="setup-camera-preview"><div className="setup-preview-floor" /><div className="setup-preview-mouse" />{roi && <div className="setup-preview-roi"><i /><i /><i /><i /></div>}<span><i />Live</span></div>;
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
  const [preflightDone, setPreflightDone] = useState(false);
  const selected = boxes.find((box) => box.id === selectedBoxId) ?? boxes[0];
  const updateSelected = (patch: Partial<SessionBoxDraft>) => setBoxes((items) => items.map((box) => box.id === selected.id ? { ...box, ...patch } : box));
  const updateFreeze = (key: keyof SessionBoxDraft["freeze"], value: number) => updateSelected({ freeze: { ...selected.freeze, [key]: value } });
  const totalShockTime = demoShocks.reduce((sum, shock) => sum + shock.durationSec, 0);
  const canRun = Boolean(name.trim() && saveDir.trim() && boxes.every((box) => box.camera && box.protocol && box.roi));

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
        <Field label="Save Directory"><div className="setup-input-action"><input value={saveDir} onChange={(event) => setSaveDir(event.target.value)} /><button aria-label="Choose save directory"><FolderOpen size={14} /></button></div></Field>
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
          <li><Check />{cameraOptions.length} Cameras Detected</li><li><Check />{boxes.length} Boxes Configured</li>
          <li><Check />Shock Controller Connected <span>COM3</span></li><li><Check />Output Directory Writable</li>
          <li><Check />Disk Space Sufficient <span>{diskFreeGB == null ? "Checking…" : `${diskFreeGB.toFixed(1)} GB`}</span></li>
        </ul>
        <button className="setup-outline-button" onClick={() => setPreflightDone(true)}><ShieldCheck size={15} />{preflightDone ? "Preflight Passed" : "Preflight Check"}</button>
      </section>
    </aside>

    <main className="box-config-panel setup-card setup-scroll-column">
      <header className="box-config-header"><h2>{selected.label} Configuration</h2><span><i />Active</span></header>
      <section className="box-config-section camera-config-section">
        <div className="config-form-block">
          <SectionTitle icon={<Camera size={15} />} title="Camera" />
          <Field label="Select Camera"><div className="inline-control"><select value={selected.camera} onChange={(event) => updateSelected({ camera: event.target.value })}><option>Unassigned</option>{cameraOptions.map((camera) => <option key={camera}>{camera}</option>)}</select><button className="setup-small-button">Test</button></div></Field>
          <Field label="Resolution"><select defaultValue="1920 × 1080 (30 FPS)"><option>1920 × 1080 (30 FPS)</option><option>1280 × 720 (60 FPS)</option><option>640 × 480 (30 FPS)</option></select></Field>
        </div><SetupPreview />
      </section>

      <section className="box-config-section roi-config-section" id="setup-roi-section">
        <div className="config-form-block">
          <SectionTitle icon={<SlidersHorizontal size={15} />} title="ROI (Region of Interest)" />
          <Field label="ROI Mode"><select value={selected.roi?.mode ?? "Rectangle"} onChange={(event) => updateSelected({ roi: selected.roi ? { ...selected.roi, mode: event.target.value as "Rectangle" | "Full Frame" } : { mode: "Rectangle", x: 120, y: 80, width: 1280, height: 720 } })}><option>Rectangle</option><option>Full Frame</option></select></Field>
          <div className="roi-coordinate-grid">{(["x", "y", "width", "height"] as const).map((key) => <Field label={key === "width" ? "W" : key === "height" ? "H" : key.toUpperCase()} key={key}><input type="number" value={selected.roi?.[key] ?? 0} onChange={(event) => selected.roi && updateSelected({ roi: { ...selected.roi, [key]: Number(event.target.value) } })} /></Field>)}</div>
          <div className="setup-button-row"><button className="setup-outline-button"><Pencil size={13} />Edit ROI</button><button className="setup-plain-button" onClick={() => updateSelected({ roi: null })}><Trash2 size={13} />Clear ROI</button></div>
        </div><SetupPreview roi={Boolean(selected.roi)} />
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
        <div className="schedule-summary"><span>Total Events: <b>{demoShocks.length}</b></span><span>First: <b>{demoShocks[0].timeSec} s</b></span><span>Last: <b>{demoShocks.at(-1)?.timeSec} s</b></span><span>Total Shock Time: <b>{totalShockTime.toFixed(1)} s</b></span></div>
        <div className="setup-table-scroll"><table><thead><tr><th>#</th><th>Time (s)</th><th>Duration (s)</th><th>Intensity (mA)</th><th>Notes</th></tr></thead><tbody>{demoShocks.map((shock, index) => <tr key={shock.id}><td>{index + 1}</td><td>{shock.timeSec}</td><td>{shock.durationSec.toFixed(1)}</td><td>{shock.intensityMA.toFixed(2)}</td><td /></tr>)}</tbody></table></div>
        <button className="setup-outline-button" disabled={selected.useTemplateSchedule}><Settings2 size={14} />Edit Schedule…</button>
      </section>
    </main>

    <aside className="session-right setup-scroll-column">
      <section className="setup-card target-box-card"><SectionTitle icon={<SlidersHorizontal size={15} />} title="Session Setup" /><Field label="Target Box"><select value={selected.id} onChange={(event) => setSelectedBoxId(event.target.value)}>{boxes.map((box) => <option value={box.id} key={box.id}>{box.label}</option>)}</select></Field></section>
      <section className="setup-card quick-settings-card"><SectionTitle icon={<Settings2 size={15} />} title="Quick Settings" /><Field label="Assigned Protocol"><select value={selected.protocol} onChange={(event) => updateSelected({ protocol: event.target.value })}><option>Unassigned</option>{protocolOptions.map((protocol) => <option key={protocol}>{protocol}</option>)}</select></Field><Field label="Camera Source"><select value={selected.camera} onChange={(event) => updateSelected({ camera: event.target.value })}><option>Unassigned</option>{cameraOptions.map((camera) => <option key={camera}>{camera}</option>)}</select></Field><div className="quick-status-row"><span>ROI Status</span><b className={selected.roi ? "ok" : "error"}><i />{selected.roi ? `Defined (${selected.roi.width} × ${selected.roi.height})` : "Missing"}</b><button onClick={() => document.getElementById("setup-roi-section")?.scrollIntoView({ behavior: "smooth" })}><Pencil size={13} /></button></div><Field label="Freeze Preset"><select value={selected.protocol} onChange={(event) => updateSelected({ protocol: event.target.value })}><option>Unassigned</option>{protocolOptions.map((protocol) => <option key={protocol}>{protocol}</option>)}</select></Field><div className="quick-toggle-row"><span>Shock Enabled</span><Toggle checked={selected.shockEnabled} onChange={(checked) => updateSelected({ shockEnabled: checked })} label="Enable shock for selected box" /></div></section>
      <section className="setup-card session-summary-card"><SectionTitle icon={<ClipboardCheck size={15} />} title="Session Summary" /><dl><div><dt>Total Boxes</dt><dd>{boxes.length}</dd></div><div><dt>Protocols</dt><dd>Mixed</dd></div><div><dt>Recording</dt><dd className="ok"><i />Enabled</dd></div><div><dt>Total Duration ({selected.label})</dt><dd>1800 s <small>(30:00)</small></dd></div><div><dt>Total Shock Events ({selected.label})</dt><dd>{selected.shockEnabled ? demoShocks.length : 0}</dd></div><div><dt>Total Shock Time ({selected.label})</dt><dd>{selected.shockEnabled ? `${totalShockTime.toFixed(1)} s` : "0.0 s"}</dd></div></dl></section>
      <section className="setup-card validation-card"><SectionTitle icon={<ShieldCheck size={15} />} title={`Validation (${selected.label})`} /><ul className="setup-check-list"><li><Check />Camera assigned</li><li className={selected.roi ? "" : "error"}>{selected.roi ? <Check /> : <CircleAlert />}ROI {selected.roi ? "defined" : "missing"}</li><li><Check />Protocol valid</li><li><Check />Freeze settings valid</li><li><Check />Shock schedule valid</li></ul></section>
      <section className="setup-card setup-actions-card"><SectionTitle icon={<WandSparkles size={15} />} title="Actions" /><div><button className="setup-outline-button"><Copy size={14} />Copy Settings to Other Boxes</button><button className="setup-plain-button"><Upload size={14} />Apply to Selected Boxes…</button></div></section>
    </aside>

    <footer className="session-action-footer"><div><i className="status-dot ok" />{canRun ? "System Ready" : "Setup Incomplete"}</div><span>Data will be saved to: <strong>{saveDir}</strong></span><div><span>Free Space: {diskFreeGB == null ? "Checking…" : `${diskFreeGB.toFixed(1)} GB`}</span><button className="setup-secondary-action"><Save size={15} />Save Session…</button><button className="setup-primary-action" disabled={!canRun} onClick={onReady}>Save &amp; Ready to Run <ArrowRight size={16} /></button></div></footer>
  </div>;
}

const registry = [
  ["Fear Conditioning v2", "1800 s · 13 shocks", "v2.1", "valid"], ["Open Field 10min", "600 s · 0 shock", "v1.2", "valid"],
  ["Shock Habituation", "900 s · 5 shocks", "v1.0", "warning"], ["Elevated Plus Maze", "300 s · 0 shock", "v1.0", "valid"],
  ["Social Interaction", "600 s · 0 shock", "v1.1", "valid"], ["Custom Protocol (Test)", "120 s · 2 shocks", "v0.1", "error"],
] as const;

function ProtocolLab() {
  const [selectedProtocol, setSelectedProtocol] = useState<string>(registry[0][0]);
  const [editorTab, setEditorTab] = useState<EditorTab>("form");
  const filtered = useMemo(() => registry, []);
  return <div className="protocol-lab-layout">
    <aside className="protocol-registry setup-card setup-scroll-column"><small>PROTOCOL REGISTRY</small><div className="registry-toolbar"><button className="setup-outline-button"><Plus size={13} />New Protocol</button><button className="setup-plain-button"><Import size={13} />Import YAML</button><button className="setup-plain-button"><Upload size={13} />Export</button><button className="setup-plain-button"><RefreshCw size={13} />Refresh</button></div><div className="registry-filters"><label><Search size={13} /><input placeholder="Search protocols…" /></label><select><option>All Status</option></select></div><div className="registry-list">{filtered.map(([name, summary, version, status]) => <button key={name} className={selectedProtocol === name ? "selected" : ""} onClick={() => setSelectedProtocol(name)}><span><strong>{name}</strong><em className={status}><i />{status[0].toUpperCase() + status.slice(1)}</em></span><small>{summary}</small><small>{version}</small></button>)}</div><button className="archived-protocols">Archived Protocols (3) <ChevronDown size={13} /></button></aside>

    <main className="protocol-editor setup-card setup-scroll-column"><header><div><strong>Editing: {selectedProtocol}</strong><span className="valid-chip">Valid</span><small>v2.1</small></div><div><button className="setup-plain-button"><Copy size={13} />Duplicate</button><button className="setup-plain-button"><Save size={13} />Save</button><button className="setup-primary-action">Save As New Version</button></div></header><nav className="editor-tabs"><button className={editorTab === "form" ? "active" : ""} onClick={() => setEditorTab("form")}>Form View</button><button className={editorTab === "yaml" ? "active" : ""} onClick={() => setEditorTab("yaml")}>YAML View</button></nav>{editorTab === "yaml" ? <textarea className="protocol-yaml-editor" defaultValue={`schema_version: 1\nprotocol:\n  id: fear_conditioning_v2\n  name: Fear Conditioning v2\n  version: 2.1\n  total_duration_sec: 1800\n  shocks:\n    - time_sec: 120\n      duration: 2.0\n      current_mA: 0.8`} /> : <div className="protocol-form-grid"><div>
      <section className="protocol-editor-section"><SectionTitle icon={<FileText size={14} />} title="Basic Information" /><div className="basic-info-grid"><Field label="Protocol ID"><input defaultValue="fear_conditioning_v2" /></Field><Field label="Total Duration (s)"><input type="number" defaultValue="1800" /></Field><Field label="Name"><input defaultValue="Fear Conditioning v2" /></Field><Field label="Author"><input defaultValue="Lab Default" /></Field><Field label="Version"><input defaultValue="2.1" /></Field><Field label="Created"><span>2025-05-10 14:22</span></Field><Field label="Description"><textarea defaultValue="Contextual fear conditioning with foot shocks." /></Field><Field label="Updated"><span>2025-05-20 10:31</span></Field></div></section>
      <section className="protocol-editor-section"><SectionTitle icon={<ListChecks size={14} />} title="Phases (3)" action={<button className="setup-small-button"><Plus size={12} />Add Phase</button>} /><table className="compact-editor-table"><thead><tr><th>#</th><th>Name</th><th>Start (s)</th><th>End (s)</th><th>Color</th></tr></thead><tbody><tr><td>1</td><td>Baseline</td><td>0</td><td>120</td><td><i className="phase-color blue" /></td></tr><tr><td>2</td><td>Conditioning</td><td>120</td><td>1560</td><td><i className="phase-color green" /></td></tr><tr><td>3</td><td>Post</td><td>1560</td><td>1800</td><td><i className="phase-color purple" /></td></tr></tbody></table></section>
      <section className="protocol-editor-section"><SectionTitle icon={<Sparkles size={14} />} title="Freeze Detection Defaults" /><div className="freeze-field-grid"><Field label="Threshold"><input defaultValue="0.65" /></Field><Field label="Min Duration (s)"><input defaultValue="1.00" /></Field><Field label="Exit Threshold"><input defaultValue="0.85" /></Field><Field label="Min Move Duration (s)"><input defaultValue="0.20" /></Field><Field label="Smoothing Window"><input defaultValue="5" /></Field><Field label="Motion Metric"><select><option>Mean Pixel Change</option></select></Field></div></section>
      <section className="protocol-editor-section"><SectionTitle icon={<Zap size={14} />} title="Shock Settings" /><div className="shock-settings-grid"><Field label="Enabled"><Toggle checked={true} onChange={() => undefined} label="Enable protocol shocks" /></Field><Field label="Type"><select><option>Foot Shock</option></select></Field><Field label="Default Intensity (mA)"><input defaultValue="0.80" /></Field><Field label="Default Duration (s)"><input defaultValue="2.0" /></Field></div><div className="safety-limits"><strong>Safety Limits</strong><Field label="Min Intensity (mA)"><input defaultValue="0.10" /></Field><Field label="Max Intensity (mA)"><input defaultValue="2.00" /></Field><Field label="Max Duration (s)"><input defaultValue="5.0" /></Field></div></section>
    </div><div>
      <section className="protocol-editor-section schedule-editor"><SectionTitle icon={<Zap size={14} />} title="Shock Schedule" action={<label className="setup-toggle-label">Enable Schedule <Toggle checked={true} onChange={() => undefined} label="Enable protocol schedule" /></label>} /><div className="schedule-tools"><button><Plus />Add Event</button><button><WandSparkles />Generate Pattern</button><button><Import />Import CSV</button><button><Trash2 />Clear All</button></div><div className="schedule-summary"><span>Total Events: <b>13</b></span><span>First: <b>120 s</b></span><span>Last: <b>1560 s</b></span><span>Total Shock Time: <b>26.0 s</b></span></div><div className="setup-table-scroll tall"><table><thead><tr><th>#</th><th>Time (s)</th><th>Duration (s)</th><th>Intensity (mA)</th><th>Notes</th></tr></thead><tbody>{demoShocks.map((shock, index) => <tr key={shock.id}><td>{index + 1}</td><td>{shock.timeSec}</td><td>{shock.durationSec.toFixed(1)}</td><td>{shock.intensityMA.toFixed(2)}</td><td /></tr>)}</tbody></table></div></section>
      <section className="protocol-editor-section schedule-generator"><SectionTitle icon={<WandSparkles size={14} />} title="Schedule Generator" /><nav><button className="active">Fixed Interval</button><button>Random Interval</button><button>Manual Input</button></nav><div>{[["Start Time (s)","120"],["End Time (s)","1560"],["Interval (s)","120"],["Duration (s)","2.0"],["Intensity (mA)","0.80"],["Jitter (s)","0"],["Seed","42"]].map(([label,value]) => <Field label={label} key={label}><input defaultValue={value} /></Field>)}<button className="setup-primary-action">Generate 13 Events</button></div></section>
    </div></div>}</main>

    <aside className="protocol-inspector setup-card setup-scroll-column"><section><h3>Validation</h3><div className="protocol-valid-hero"><ShieldCheck /><strong>Protocol is valid</strong><span>No blocking issues found.</span></div><div className="validation-counts"><span><b>0</b>Errors</span><span><b>1</b>Warnings</span><span><b>0</b>Infos</span></div><h4>Validation Details</h4><ul className="setup-check-list"><li><Check />Total duration is positive</li><li><Check />13 shock events</li><li><Check />All shock times within duration</li><li><Check />No overlapping shocks</li><li><Check />Schedule is sorted</li><li><Check />Freeze threshold in valid range</li><li className="warning"><CircleAlert />Exit threshold is high (0.85)</li></ul></section><section className="protocol-timeline-preview"><h3>Timeline Preview</h3><span>Total Duration: 1800 s</span><div className="phase-timeline"><i /><i /><i /></div><div className="shock-marks">{Array.from({ length: 13 }, (_, index) => <Zap key={index} />)}</div><div className="timeline-key"><span><i className="blue" />Baseline</span><span><i className="green" />Conditioning</span><span><i className="purple" />Post</span><span><Zap />Shock</span></div></section><section className="protocol-debug"><h3>Debug &amp; Test</h3><button className="setup-outline-button"><Play size={14} />Dry Run Protocol</button><button className="setup-outline-button"><Zap size={14} />Stimulator Test</button><button className="setup-plain-button" disabled><Upload size={14} />Export Protocol YAML</button></section></aside>
    <footer className="protocol-status-footer"><span>Protocol Hash: <strong>4f6c2e9a7b3d5a1e…</strong></span><span>Location: <strong>D:\\arena\\protocols\\fear_conditioning_v2.yaml</strong></span></footer>
  </div>;
}

export function SetupPage({ onReady }: { onReady: () => void }) {
  const [tab, setTab] = useState<SetupTab>("session");
  return <section className="setup-shell"><nav className="setup-subnav"><button className={tab === "session" ? "active" : ""} onClick={() => setTab("session")}>Session Setup</button><button className={tab === "protocol" ? "active" : ""} onClick={() => setTab("protocol")}>Protocol Lab</button></nav><div className={`setup-view ${tab === "session" ? "active" : ""}`}><SessionSetup onOpenProtocolLab={() => setTab("protocol")} onReady={onReady} /></div><div className={`setup-view ${tab === "protocol" ? "active" : ""}`}><ProtocolLab /></div></section>;
}
