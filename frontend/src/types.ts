export type AppPage = "setup" | "run" | "review";
export type AppState = "idle" | "previewing" | "running" | "stopping" | "review";
export type RecordingState = "idle" | "preview" | "recording" | "error";
export type BehaviorState = "unknown" | "moving" | "freeze" | "candidate_freeze";

export interface RoiConfig {
  preset: string;
  shape: "rectangle" | "polygon";
  coveragePercent: number;
  normalized: { x: number; y: number; width: number; height: number };
  active: boolean;
}

export interface FreezeStrategy {
  threshold: number;
  minDurationSec: number;
}

export interface ShockEvent {
  id: string;
  timeSec: number;
  durationSec: number;
  intensityMA: number;
  status: "pending" | "triggered" | "failed" | "skipped";
}

export interface CameraSession {
  boxId: string;
  label: string;
  deviceId: string;
  deviceIndex: number;
  deviceName: string;
  enabled: boolean;
  resolution: { width: number; height: number };
  targetFps: number;
  actualFps: number;
  recordingState: RecordingState;
  behaviorState: BehaviorState;
  protocolId: string;
  protocolName: string;
  roi: RoiConfig;
  freezeStrategy: FreezeStrategy;
  droppedFrames: number;
  motionValue: number;
}

export interface RuntimeEvent {
  id: string;
  timeSec: number;
  boxId?: string;
  boxLabel?: string;
  type: "freeze_start" | "freeze_end" | "move_start" | "move_end" | "shock_triggered" | "camera_error";
  label: string;
  durationSec?: number;
  severity: "info" | "warning" | "error";
}

export interface MotionSample {
  t: number;
  motion: number;
  threshold: number;
}

export interface SystemStatus {
  temperatureC?: number;
  diskFreeGB: number | null;
  pythonVersion: string;
  appVersion: string;
  backendState: "connected" | "disconnected" | "error" | "preview";
  stimulator: StimulatorStatus;
}

export interface StimulatorStatus {
  connected: boolean;
  armed: boolean;
  calibrated: boolean;
  deviceId?: string;
  error?: string;
}
