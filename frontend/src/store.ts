import { create } from "zustand";
import type { AppPage, AppState, CameraSession, MotionSample, RuntimeEvent, ShockEvent, StimulatorStatus, SystemStatus } from "./types";

interface SessionClientView {
  cameras: CameraSession[];
  shocks: ShockEvent[];
  totalDurationSec: number;
  saveDir: string;
  protocolName: string;
}

export interface SetupBoxDraft {
  id: string;
  label: string;
  color: string;
  camera: string;
  protocol: string;
  instanceName: string;
  roi: { mode: string; x: number; y: number; width: number; height: number } | null;
  useFreezeDefaults: boolean;
  freeze: { threshold: number; minDuration: number; exitThreshold: number; minMoveDuration: number };
  useTemplateSchedule: boolean;
  shockEnabled: boolean;
}

export interface SessionSetupDraft {
  name: string;
  saveDir: string;
  notes: string;
  boxes: SetupBoxDraft[];
  selectedBoxId: string;
}

interface ArenaStore {
  page: AppPage;
  appState: AppState;
  cameras: CameraSession[];
  selectedBoxId: string;
  motionBoxId: string;
  shocks: ShockEvent[];
  events: RuntimeEvent[];
  motion: Record<string, MotionSample[]>;
  elapsedSec: number;
  totalDurationSec: number;
  saveDir: string;
  batchNumber: number;
  system: SystemStatus;
  protocolDraft: Record<string, unknown> | null;
  protocolName: string;
  sessionSetup: SessionSetupDraft;
  setPage: (page: AppPage) => void;
  selectBox: (boxId: string) => void;
  selectMotionBox: (boxId: string) => void;
  toggleCamera: (boxId: string) => void;
  connectPreview: () => void;
  startExperiment: () => void;
  stop: () => void;
  setShocks: (shocks: ShockEvent[]) => void;
  setTotalDurationSec: (sec: number) => void;
  applySessionConfig: (config: SessionClientView) => void;
  nextBatch: () => void;
  setSessionSetup: (draft: Partial<SessionSetupDraft>) => void;
  updateStimulator: (patch: Partial<StimulatorStatus>) => void;
  setProtocolDraft: (draft: Record<string, unknown> | null) => void;
  setProtocolName: (name: string) => void;
}

const defaultStimulator: StimulatorStatus = { connected: false, armed: false, calibrated: false };

const boxColors = ["#2774f6", "#8b5cf6", "#f59e0b", "#18b8c9", "#ec4899", "#22c55e"];

const defaultSetupBoxes: SetupBoxDraft[] = ["A", "B", "C", "D"].map((letter, index) => ({
  id: `box-${index + 1}`,
  label: `Box ${letter}`,
  color: boxColors[index],
  camera: `Camera ${index + 1} (USB3.0)`,
  protocol: index < 2 ? "Fear Conditioning" : "Fear Conditioning (intense)",
  instanceName: `Box${letter}_FC`,
  roi: { mode: "Rectangle", x: 120, y: 80, width: 1280, height: 720 },
  useFreezeDefaults: true,
  freeze: { threshold: 0.65, minDuration: 1, exitThreshold: 0.85, minMoveDuration: 0.2 },
  useTemplateSchedule: true,
  shockEnabled: index < 2,
}));

export const useArenaStore = create<ArenaStore>((set) => ({
  page: "setup",
  appState: "idle",
  cameras: [],
  selectedBoxId: "",
  motionBoxId: "",
  shocks: [],
  events: [],
  motion: {},
  elapsedSec: 0,
  totalDurationSec: 0,
  saveDir: "",
  batchNumber: 1,
  system: { diskFreeGB: null, pythonVersion: "Browser preview", appVersion: "1.0.0-dev", backendState: "preview", stimulator: defaultStimulator },
  protocolDraft: null,
  protocolName: "",
  sessionSetup: {
    name: "Fear Conditioning_2026-07-03",
    saveDir: "D:\\Data\\2026-07-03_FC\\",
    notes: "Morning cohort - Contextual FC.",
    boxes: defaultSetupBoxes,
    selectedBoxId: defaultSetupBoxes[0].id,
  },
  setPage: (page) => set({ page }),
  selectBox: (boxId) => set({ selectedBoxId: boxId }),
  selectMotionBox: (boxId) => set({ motionBoxId: boxId }),
  toggleCamera: (boxId) => set((state) => ({ cameras: state.cameras.map((camera) => camera.boxId === boxId ? { ...camera, enabled: !camera.enabled } : camera) })),
  connectPreview: () => set((state) => ({ appState: state.appState === "idle" ? "previewing" : "idle", cameras: state.cameras.map((camera) => ({ ...camera, recordingState: state.appState === "idle" ? "preview" : "idle" })) })),
  startExperiment: () => set((state) => ({ appState: "running", cameras: state.cameras.map((camera) => camera.enabled ? { ...camera, recordingState: "recording" } : camera) })),
  stop: () => set((state) => ({ appState: "idle", cameras: state.cameras.map((camera) => ({ ...camera, recordingState: "idle", behaviorState: "unknown" })) })),
  setShocks: (shocks) => set({ shocks }),
  setTotalDurationSec: (sec) => set({ totalDurationSec: sec }),
  applySessionConfig: (config) => set({
    cameras: config.cameras,
    shocks: config.shocks,
    totalDurationSec: config.totalDurationSec,
    saveDir: config.saveDir,
    protocolName: config.protocolName,
    events: [],
    motion: {},
    elapsedSec: 0,
    batchNumber: 1,
    appState: "idle",
    selectedBoxId: config.cameras[0]?.boxId ?? "box-1",
    motionBoxId: config.cameras[0]?.boxId ?? "box-1",
  }),
  nextBatch: () => set((state) => ({
    batchNumber: state.batchNumber + 1,
    events: [],
    motion: {},
    elapsedSec: 0,
    shocks: state.shocks.map((s) => ({ ...s, status: "pending" as const })),
    cameras: state.cameras.map((c) => ({ ...c, recordingState: "idle" as const, behaviorState: "unknown" as const, actualFps: 0, motionValue: 0, droppedFrames: 0 })),
  })),
  setSessionSetup: (draft) => set((state) => ({ sessionSetup: { ...state.sessionSetup, ...draft } })),
  updateStimulator: (patch) => set((state) => ({ system: { ...state.system, stimulator: { ...state.system.stimulator, ...patch } } })),
  setProtocolDraft: (draft) => set({ protocolDraft: draft }),
  setProtocolName: (name) => set({ protocolName: name }),
}));