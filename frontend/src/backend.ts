import { useArenaStore } from "./store";
import { publishFrame } from "./frameBus";
import type { RuntimeEvent, ShockEvent } from "./types";
import { getStimulatorStatus } from "./setupBackend";

declare const __ARENA_PREVIEW_DISK_FREE_GB__: number;

type BackendMessage =
  | { kind: "event"; type: string; payload: Record<string, unknown> }
  | { kind: "response"; id: string; ok: boolean; result?: Record<string, unknown>; error?: { message: string } };

const pending = new Map<string, { resolve: (value: Record<string, unknown>) => void; reject: (error: Error) => void }>();
let initialized = false;

function isTauri() {
  return "__TAURI_INTERNALS__" in window;
}

function applyEvent(type: string, payload: Record<string, unknown>) {
  if (type === "backend_ready") useArenaStore.setState((state) => ({ system: { ...state.system, backendState: "connected" } }));
  if (type === "backend_stopped") useArenaStore.setState((state) => ({ appState: "idle", system: { ...state.system, backendState: "disconnected" } }));
  if (type === "session_status" && typeof payload.status === "string") {
    const status = payload.status;
    if (["idle", "previewing", "running", "stopping"].includes(status)) {
      useArenaStore.setState({ appState: status as "idle" | "previewing" | "running" | "stopping" });
    }
  }
  if (type === "camera_telemetry" && typeof payload.box_id === "string") {
    const store = useArenaStore.getState();
    const boxId = payload.box_id;
    const elapsed = Number(payload.experiment_time_sec ?? store.elapsedSec);
    const motionValue = Number(payload.motion_value ?? 0);
    const camera = store.cameras.find((item) => item.boxId === boxId);
    const threshold = camera?.freezeStrategy.threshold ?? 0;
    const samples = [...(store.motion[boxId] ?? []), { t: elapsed, motion: motionValue, threshold }].slice(-300);
    useArenaStore.setState({
      elapsedSec: elapsed,
      motion: { ...store.motion, [boxId]: samples },
      cameras: store.cameras.map((camera) => camera.boxId === boxId ? {
      ...camera,
      actualFps: Number(payload.actual_fps ?? camera.actualFps),
      motionValue,
      behaviorState: (payload.behavior_state as typeof camera.behaviorState) ?? camera.behaviorState,
      recordingState: (payload.recording_state as typeof camera.recordingState) ?? camera.recordingState,
    } : camera) });
  }
  if (type === "camera_frame" && typeof payload.boxId === "string" && typeof payload.data === "string") {
    publishFrame(payload.boxId, { encoding: String(payload.encoding ?? "jpeg-base64"), data: payload.data });
  }
  if (type === "behavior_event" && typeof payload.boxId === "string") {
    const store = useArenaStore.getState();
    const camera = store.cameras.find((item) => item.boxId === payload.boxId);
    const rawEventType = String(payload.type ?? "freeze_start");
    const eventType = rawEventType.replace("moving_", "move_");
    const event: RuntimeEvent = {
      id: crypto.randomUUID(),
      timeSec: Number(payload.timeSec ?? store.elapsedSec),
      boxId: payload.boxId,
      boxLabel: camera?.label ?? payload.boxId,
      type: eventType as "freeze_start" | "freeze_end" | "move_start" | "move_end",
      label: eventType.split("_").map((part) => part[0].toUpperCase() + part.slice(1)).join(" "),
      severity: "info",
    };
    useArenaStore.setState({ events: [...store.events, event].slice(-200) });
  }
  if (type === "experiment_tick") useArenaStore.setState({ elapsedSec: Number(payload.elapsedSec ?? 0), totalDurationSec: Number(payload.totalDurationSec ?? useArenaStore.getState().totalDurationSec) });
  if (type === "camera_error" && typeof payload.boxId === "string") {
    const store = useArenaStore.getState();
    const camera = store.cameras.find((item) => item.boxId === payload.boxId);
    const event: RuntimeEvent = { id: crypto.randomUUID(), timeSec: store.elapsedSec, boxId: payload.boxId, boxLabel: camera?.label ?? payload.boxId, type: "camera_error", label: String(payload.message ?? "Camera error"), severity: "error" };
    useArenaStore.setState({
      cameras: store.cameras.map((item) => item.boxId === payload.boxId ? { ...item, recordingState: "error" } : item),
      events: [...store.events, event].slice(-200),
    });
  }
  if (type === "shock_event" && typeof payload.id === "string") {
    const store = useArenaStore.getState();
    const skipped = payload.status === "skipped_unarmed";
    const shockStatus: ShockEvent["status"] = skipped ? "skipped" : "triggered";
    const event: RuntimeEvent = { id: crypto.randomUUID(), timeSec: Number(payload.actualTimeSec ?? store.elapsedSec), type: "shock_triggered", label: skipped ? "Shock skipped — stimulator not armed" : "Shock triggered", severity: skipped ? "warning" : "info" };
    useArenaStore.setState({
      shocks: store.shocks.map((shock) => shock.id === payload.id ? { ...shock, status: shockStatus } : shock),
      events: [...store.events, event].slice(-200),
    });
  }
}

export function cameraCommandModels() {
  return useArenaStore.getState().cameras.filter((camera) => camera.enabled).map((camera) => ({
    boxId: camera.boxId,
    label: camera.label,
    deviceId: camera.deviceId,
    deviceIndex: Number(camera.deviceId.match(/\d+$/)?.[0] ?? 1) - 1,
    enabled: camera.enabled,
    roi: { shape: camera.roi.shape, points: [] },
    freezeStrategy: { threshold: camera.freezeStrategy.threshold, minDurationSec: camera.freezeStrategy.minDurationSec },
  }));
}

export async function previewCommand() {
  return sendBackendCommand("start_preview", { cameras: cameraCommandModels() });
}

export async function startExperimentCommand() {
  const state = useArenaStore.getState();
  const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+/, "");
  return sendBackendCommand("start_experiment", {
    sessionConfig: {
      sessionId: `arena_${stamp}`,
      saveDir: state.saveDir,
      cameras: cameraCommandModels(),
      shocks: state.shocks,
      totalDurationSec: state.totalDurationSec,
      globalOptions: { saveVideo: true, enableStimulator: state.shocks.length > 0 },
    },
  });
}

export async function stopCommand(running: boolean) {
  return sendBackendCommand(running ? "stop_experiment" : "stop_preview");
}

export async function captureSnapshotCommand(boxId: string) {
  return sendBackendCommand("capture_snapshot", { boxId, outputDir: useArenaStore.getState().saveDir });
}

export async function windowAction(action: "minimize" | "toggle-size" | "close") {
  if (!isTauri()) return;
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  const appWindow = getCurrentWindow();
  if (action === "minimize") await appWindow.minimize();
  if (action === "toggle-size") {
    const [{ LogicalSize }, size, scaleFactor] = await Promise.all([
      import("@tauri-apps/api/dpi"),
      appWindow.innerSize(),
      appWindow.scaleFactor(),
    ]);
    const isLarge = size.width / scaleFactor > 1296;
    await appWindow.setSize(new LogicalSize(isLarge ? 1152 : 1440, isLarge ? 800 : 1000));
    await appWindow.center();
  }
  if (action === "close") await appWindow.close();
}

export async function initializeBackend() {
  if (initialized) return;
  initialized = true;
  if (!isTauri()) {
    useArenaStore.setState((state) => ({ system: { ...state.system, diskFreeGB: __ARENA_PREVIEW_DISK_FREE_GB__ } }));
    return;
  }
  try {
    const [{ invoke }, { listen }] = await Promise.all([import("@tauri-apps/api/core"), import("@tauri-apps/api/event")]);
    await listen<BackendMessage>("backend-message", ({ payload }) => {
      if (payload.kind === "event") applyEvent(payload.type, payload.payload);
      if (payload.kind === "response") {
        const request = pending.get(payload.id);
        if (!request) return;
        pending.delete(payload.id);
        payload.ok ? request.resolve(payload.result ?? {}) : request.reject(new Error(payload.error?.message ?? "Backend command failed"));
      }
    });
    await invoke("start_backend");
    const state = await sendBackendCommand("get_state", { saveDir: useArenaStore.getState().saveDir });
useArenaStore.setState((current) => ({
      appState: (state.state as typeof current.appState) ?? "idle",
      elapsedSec: Number(state.elapsedSec ?? 0),
      system: {
        ...current.system,
        backendState: "connected",
        diskFreeGB: Number(state.diskFreeGB ?? current.system.diskFreeGB),
        pythonVersion: String(state.pythonVersion ?? current.system.pythonVersion),
      },
    }));
    void getStimulatorStatus().then((stimulator) => {
        const s = stimulator as { connected?: boolean; armed?: boolean; calibrated?: boolean; device_id?: string; error?: string };
        useArenaStore.getState().updateStimulator({
          connected: s.connected ?? false,
          armed: s.armed ?? false,
          calibrated: s.calibrated ?? false,
          deviceId: s.device_id,
          error: s.error,
        });
      });
  } catch (error) {
    console.error("arena backend initialization failed", error);
    useArenaStore.setState((state) => ({ appState: "idle", system: { ...state.system, backendState: "error" } }));
  }
}

export async function sendBackendCommand(type: string, payload: Record<string, unknown> = {}) {
  if (!isTauri()) return {};
  const { invoke } = await import("@tauri-apps/api/core");
  const id = crypto.randomUUID();
  const response = new Promise<Record<string, unknown>>((resolve, reject) => pending.set(id, { resolve, reject }));
  await invoke("backend_command", { message: { id, type, payload } });
  return response;
}
