import { create } from "zustand";
import { demoCameras, demoEvents, demoMotion, demoShocks } from "./mockData";
import type { AppPage, AppState, CameraSession, MotionSample, RuntimeEvent, ShockEvent, SystemStatus } from "./types";

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
  system: SystemStatus;
  setPage: (page: AppPage) => void;
  selectBox: (boxId: string) => void;
  selectMotionBox: (boxId: string) => void;
  toggleCamera: (boxId: string) => void;
  connectPreview: () => void;
  startExperiment: () => void;
  stop: () => void;
}

export const useArenaStore = create<ArenaStore>((set) => ({
  page: "setup",
  appState: "previewing",
  cameras: demoCameras,
  selectedBoxId: "box-1",
  motionBoxId: "box-1",
  shocks: demoShocks,
  events: demoEvents,
  motion: demoMotion,
  elapsedSec: 192,
  totalDurationSec: 480,
  saveDir: "C:\\Shared\\arena\\2026-07-03",
  system: { diskFreeGB: null, pythonVersion: "Browser preview", appVersion: "1.0.0-dev", backendState: "preview" },
  setPage: (page) => set({ page }),
  selectBox: (boxId) => set({ selectedBoxId: boxId }),
  selectMotionBox: (boxId) => set({ motionBoxId: boxId }),
  toggleCamera: (boxId) => set((state) => ({ cameras: state.cameras.map((camera) => camera.boxId === boxId ? { ...camera, enabled: !camera.enabled } : camera) })),
  connectPreview: () => set((state) => ({ appState: state.appState === "idle" ? "previewing" : "idle", cameras: state.cameras.map((camera) => ({ ...camera, recordingState: state.appState === "idle" ? "preview" : "idle" })) })),
  startExperiment: () => set((state) => ({ appState: "running", cameras: state.cameras.map((camera) => camera.enabled ? { ...camera, recordingState: "recording" } : camera) })),
  stop: () => set((state) => ({ appState: "idle", cameras: state.cameras.map((camera) => ({ ...camera, recordingState: "idle", behaviorState: "unknown" })) })),
}));
