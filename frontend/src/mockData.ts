import type { CameraSession, MotionSample, RuntimeEvent, ShockEvent } from "./types";

const behaviors = ["freeze", "moving", "moving", "freeze"] as const;

export const demoCameras: CameraSession[] = Array.from({ length: 4 }, (_, index) => ({
  boxId: `box-${index + 1}`,
  label: `Box ${String.fromCharCode(65 + index)}`,
  deviceId: `uvc-demo-${index + 1}`,
  deviceIndex: index,
  deviceName: `USB Camera ${String(index + 1).padStart(2, "0")}`,
  enabled: true,
  resolution: { width: 1920, height: 1080 },
  targetFps: 30,
  actualFps: 29.8 - index * 0.1,
  recordingState: "recording",
  behaviorState: behaviors[index],
  protocolId: "fear-conditioning-v2",
  protocolName: "Fear Conditioning v2",
  roi: {
    preset: "Center 70%",
    shape: "rectangle",
    coveragePercent: index === 0 ? 42.3 : 39.8 + index,
    normalized: {
      x: 0.22 + index * 0.035,
      y: 0.16 + index * 0.025,
      width: 0.55 - index * 0.045,
      height: 0.62 - index * 0.035,
    },
    active: true,
  },
  freezeStrategy: { threshold: 0.65, minDurationSec: 1 },
  droppedFrames: index,
  motionValue: [0.08, 0.42, 0.31, 0.05][index],
}));

export const demoShocks: ShockEvent[] = Array.from({ length: 8 }, (_, index) => ({
  id: `shock-${index + 1}`,
  timeSec: 120 + index * 180,
  durationSec: 2,
  intensityMA: 0.8,
  status: index === 0 ? "triggered" : "pending",
}));

export const demoEvents: RuntimeEvent[] = [
  { id: "event-1", timeSec: 12.35, boxId: "box-1", boxLabel: "Box A", type: "freeze_start", label: "Freeze start", severity: "info" },
  { id: "event-2", timeSec: 15.82, boxId: "box-1", boxLabel: "Box A", type: "freeze_end", label: "Freeze end", durationSec: 3.47, severity: "info" },
  { id: "event-3", timeSec: 18.1, boxId: "box-2", boxLabel: "Box B", type: "move_start", label: "Move start", severity: "info" },
  { id: "event-4", timeSec: 21.56, boxId: "box-2", boxLabel: "Box B", type: "move_end", label: "Move end", durationSec: 3.46, severity: "info" },
  { id: "event-5", timeSec: 24.3, boxId: "box-3", boxLabel: "Box C", type: "freeze_start", label: "Freeze start", severity: "info" },
];

export const demoMotion: Record<string, MotionSample[]> = Object.fromEntries(
  demoCameras.map((camera, cameraIndex) => [
    camera.boxId,
    Array.from({ length: 60 }, (_, index) => {
      const t = index / 2 - 30;
      const wave = Math.sin(index * 0.46 + cameraIndex) * 0.11;
      const bursts = index > 13 && index < 29 ? Math.abs(Math.sin(index * 1.7)) * 0.42 : 0;
      return { t, motion: Math.max(0.02, 0.12 + wave + bursts), threshold: 0.48 };
    }),
  ]),
);
