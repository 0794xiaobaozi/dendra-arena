import { sendBackendCommand } from "./backend";

export interface CameraDeviceModel {
  deviceId: string;
  deviceIndex: number;
  deviceName: string;
  displayName: string;
  status: "available" | "busy" | "error";
  resolutionOptions: Array<{ width: number; height: number; fps: number }>;
}

export interface CheckItemModel {
  id: string;
  level: "success" | "warning" | "error" | "info";
  message: string;
  blocking: boolean;
  detail?: string;
}

export interface PreflightModel {
  global: CheckItemModel[];
  boxes: Record<string, CheckItemModel[]>;
  canRun: boolean;
  blockingReasons: string[];
  directory: { path: string; writable: boolean; freeGB: number; error?: string };
  stimulator: { connected: boolean; armed: boolean; calibrated: boolean; device_id?: string; error?: string };
}

export interface ProtocolSummaryModel {
  id: string;
  name: string;
  version: string;
  totalDurationSec: number;
  shockCount: number;
  validationStatus: "valid" | "warning" | "error";
  hash: string;
  path: string;
  warnings?: string[];
  error?: string;
}

export interface ProtocolDraftModel {
  schemaVersion: number;
  id: string;
  name: string;
  version: string;
  description: string;
  author: string;
  totalDurationSec: number;
  shocks: Array<{ id: string; timeSec: number; durationSec: number; intensityMA: number; notes?: string }>;
  freezeDefaults: Record<string, number>;
  phases: Array<Record<string, unknown>>;
  hash?: string;
  path?: string;
  validation?: { valid: boolean; errors: string[]; warnings: string[]; hash: string };
}

function isTauri() {
  return "__TAURI_INTERNALS__" in window;
}

export async function chooseSaveDirectory(): Promise<string | null> {
  if (!isTauri()) return null;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<string | null>("select_save_directory");
}

export async function chooseProtocolYaml(): Promise<string | null> {
  if (!isTauri()) return null;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<string | null>("select_protocol_yaml");
}

export async function listCameras(): Promise<CameraDeviceModel[]> {
  if (!isTauri()) return Array.from({ length: 4 }, (_, index) => ({ deviceId: `camera-${index}`, deviceIndex: index, deviceName: `USB Camera ${index + 1}`, displayName: `Camera ${index + 1} (USB3.0)`, status: "available" as const, resolutionOptions: [{ width: 1920, height: 1080, fps: 30 }] }));
  const result = await sendBackendCommand("list_cameras", { maxIndex: 10 });
  return (result.cameras ?? []) as CameraDeviceModel[];
}

export async function validateRoi(roi: Record<string, unknown>) {
  if (!isTauri()) {
    const imageWidth = Number(roi.imageWidth), imageHeight = Number(roi.imageHeight);
    const x = Number(roi.x), y = Number(roi.y), width = Number(roi.width), height = Number(roi.height);
    const errors = [];
    if (x < 0 || y < 0 || width <= 0 || height <= 0 || x + width > imageWidth || y + height > imageHeight) errors.push("ROI exceeds source image bounds");
    return { valid: !errors.length, errors, normalized: { x: x / imageWidth, y: y / imageHeight, width: width / imageWidth, height: height / imageHeight } };
  }
  return sendBackendCommand("validate_roi", roi);
}

export async function startSetupCameraPreview(boxId: string, device: CameraDeviceModel) {
  return sendBackendCommand("start_preview", { cameras: [{ boxId, label: boxId, deviceId: device.deviceId, deviceIndex: device.deviceIndex, enabled: true, roi: { shape: "rectangle", points: [] }, freezeStrategy: { threshold: 0.65, minDurationSec: 1 } }] });
}

export async function stopSetupCameraPreview() {
  return sendBackendCommand("stop_preview");
}

export async function runPreflight(sessionDraft: Record<string, unknown>): Promise<PreflightModel> {
  if (!isTauri()) {
    const boxes = sessionDraft.boxes as Array<Record<string, unknown>>;
    const boxChecks = Object.fromEntries(boxes.map((box) => [String(box.id), [
      { id: "camera", level: box.camera === "Unassigned" ? "error" : "success", message: box.camera === "Unassigned" ? "Camera is not assigned" : "Camera assigned", blocking: box.camera === "Unassigned" },
      { id: "roi", level: box.roi ? "success" : "error", message: box.roi ? "ROI defined" : "ROI is missing", blocking: !box.roi },
      { id: "protocol", level: box.protocol === "Unassigned" ? "error" : "success", message: box.protocol === "Unassigned" ? "Protocol is not assigned" : "Protocol assigned", blocking: box.protocol === "Unassigned" },
    ] as CheckItemModel[]]));
    const blockingReasons = Object.values(boxChecks).flat().filter((item) => item.blocking).map((item) => item.message);
    return { global: [{ id: "browser", level: "info", message: "Browser preview uses simulated hardware", blocking: false }], boxes: boxChecks, canRun: !blockingReasons.length, blockingReasons, directory: { path: String(sessionDraft.saveDir), writable: true, freeGB: 0 }, stimulator: { connected: false, armed: false, calibrated: false } };
  }
  return sendBackendCommand("run_preflight_check", { sessionDraft }) as unknown as PreflightModel;
}

export async function saveSessionDraft(sessionDraft: Record<string, unknown>) {
  if (!isTauri()) return { path: null, sessionDraft };
  return sendBackendCommand("save_session_draft", { sessionDraft });
}

export async function lockSessionForRun(sessionDraft: Record<string, unknown>) {
  if (!isTauri()) return { path: null, lockedConfig: { status: "preview", session: sessionDraft } };
  return sendBackendCommand("lock_session_for_run", { sessionDraft });
}

export async function listProtocolTemplates(): Promise<ProtocolSummaryModel[]> {
  if (!isTauri()) return [];
  const result = await sendBackendCommand("list_protocol_templates");
  return (result.protocols ?? []) as ProtocolSummaryModel[];
}

export async function loadProtocolTemplate(protocolId: string): Promise<ProtocolDraftModel> {
  const result = await sendBackendCommand("load_protocol_template", { protocolId });
  return result.protocol as unknown as ProtocolDraftModel;
}

export async function importProtocolYaml(path: string): Promise<ProtocolDraftModel> {
  const result = await sendBackendCommand("import_protocol_yaml", { path });
  return result.protocol as unknown as ProtocolDraftModel;
}

export async function saveProtocolTemplate(protocolDraft: ProtocolDraftModel): Promise<ProtocolDraftModel> {
  if (!isTauri()) return { ...protocolDraft, hash: "browser-preview-unsaved" };
  const result = await sendBackendCommand("save_protocol_template", { protocolDraft });
  return result.protocol as unknown as ProtocolDraftModel;
}

export async function validateProtocolTemplate(protocolDraft: ProtocolDraftModel) {
  if (!isTauri()) {
    const errors: string[] = [];
    if (!/^[a-z0-9_]+$/.test(protocolDraft.id)) errors.push("Protocol ID must contain only lowercase letters, numbers, and underscores");
    if (protocolDraft.totalDurationSec <= 0) errors.push("Total duration must be positive");
    protocolDraft.shocks.forEach((shock, index) => { if (shock.timeSec < 0 || shock.timeSec + shock.durationSec > protocolDraft.totalDurationSec) errors.push(`Shock #${index + 1} is outside protocol duration`); });
    return { valid: !errors.length, errors, warnings: Number(protocolDraft.freezeDefaults.exitThreshold ?? 0) > 0.8 ? ["Exit threshold is high"] : [], hash: "browser-preview" };
  }
  return sendBackendCommand("validate_protocol", { protocolDraft });
}

export async function generateShockSchedule(generatorConfig: Record<string, unknown>) {
  if (!isTauri()) {
    const events = [];
    const start = Number(generatorConfig.startTimeSec), end = Number(generatorConfig.endTimeSec), interval = Number(generatorConfig.intervalSec);
    for (let time = start, index = 0; time <= end; time += interval, index += 1) events.push({ id: `shock-${index + 1}`, timeSec: time, durationSec: Number(generatorConfig.durationSec), intensityMA: Number(generatorConfig.intensityMA), notes: "" });
    return { events };
  }
  return sendBackendCommand("generate_shock_schedule", { generatorConfig });
}

export async function dryRunProtocol(protocolDraft: ProtocolDraftModel) {
  if (!isTauri()) return { lines: ["0.000 Protocol started", ...protocolDraft.shocks.flatMap((shock, index) => [`${shock.timeSec.toFixed(3)} Shock #${index + 1} would trigger`, `${(shock.timeSec + shock.durationSec).toFixed(3)} Shock #${index + 1} would end`]), `${protocolDraft.totalDurationSec.toFixed(3)} Protocol finished`] };
  return sendBackendCommand("dry_run_protocol", { protocolDraft });
}

export async function getStimulatorStatus() {
  if (!isTauri()) return { connected: false, armed: false, calibrated: false, error: "Browser preview" };
  return sendBackendCommand("get_stimulator_status");
}

export async function armStimulator(confirmed: boolean) {
  return sendBackendCommand("arm_stimulator", { confirmed });
}

export async function disarmStimulator() {
  return sendBackendCommand("disarm_stimulator");
}

export async function runStimulatorTest(currentMA: number, durationSeconds: number) {
  return sendBackendCommand("stimulator_test", { currentMA, durationSeconds, confirmed: true });
}
