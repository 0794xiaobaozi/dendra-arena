import { useEffect, useRef } from "react";
import { Camera, Info, Settings2, SignalHigh, Snowflake } from "lucide-react";
import { useArenaStore } from "../store";
import type { BehaviorState, CameraSession } from "../types";
import { subscribeFrame } from "../frameBus";
import { captureSnapshotCommand } from "../backend";

function BehaviorBadge({ state }: { state: BehaviorState }) {
  if (state === "freeze") return <span className="behavior-badge freeze"><Snowflake size={13} />FREEZE</span>;
  if (state === "moving") return <span className="behavior-badge moving">MOVE</span>;
  if (state === "candidate_freeze") return <span className="behavior-badge candidate">LOW MOTION</span>;
  return <span className="behavior-badge unknown">UNKNOWN</span>;
}

function ArenaPlaceholder({ camera }: { camera: CameraSession }) {
  const n = Number(camera.boxId.split("-").at(-1) ?? 1);
  return (
    <div className={`arena arena-${n}`}>
      <div className="arena-wall" />
      <div className="arena-floor" />
      <div className="water-spout" />
      <div className="mouse-shape"><i className="mouse-ear" /><i className="mouse-tail" /></div>
      <div className="roi-box" style={{ left: `${camera.roi.normalized.x * 100}%`, top: `${camera.roi.normalized.y * 100}%`, width: `${camera.roi.normalized.width * 100}%`, height: `${camera.roi.normalized.height * 100}%` }}>
        <i /><i /><i /><i />
      </div>
    </div>
  );
}

function CameraCanvas({ boxId }: { boxId: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => subscribeFrame(boxId, ({ data }) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const image = new Image();
    image.onload = () => {
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;
      canvas.getContext("2d", { alpha: false })?.drawImage(image, 0, 0);
      canvas.dataset.ready = "true";
    };
    image.src = `data:image/jpeg;base64,${data}`;
  }), [boxId]);
  return <canvas ref={canvasRef} className="camera-canvas" />;
}

function CameraCard({ camera }: { camera: CameraSession }) {
  const { selectedBoxId, selectBox } = useArenaStore();
  const recording = camera.recordingState === "recording";
  return (
    <article className={`camera-card card ${selectedBoxId === camera.boxId ? "selected" : ""}`} onClick={() => selectBox(camera.boxId)}>
      <header className="camera-card-header">
        <h3>{camera.label}</h3>
        <div className="camera-badges">
          <span className={`rec-badge ${recording ? "recording" : "live"}`}><i />{recording ? "REC" : "LIVE"}</span>
          <BehaviorBadge state={camera.behaviorState} />
          <span className="fps-badge">{camera.actualFps.toFixed(1)} fps</span>
        </div>
      </header>
      <div className="camera-meta">
        <span>Cam {camera.boxId.at(-1)?.padStart(2, "0")}</span><span>{camera.resolution.width}×{camera.resolution.height}</span><i />
        <span>{camera.targetFps} fps</span><button>{camera.protocolName}<span>⌄</span></button><Info size={15} />
      </div>
      <div className="video-viewport"><ArenaPlaceholder camera={camera} /><CameraCanvas boxId={camera.boxId} /><div className="live-roi roi-box" style={{ left: `${camera.roi.normalized.x * 100}%`, top: `${camera.roi.normalized.y * 100}%`, width: `${camera.roi.normalized.width * 100}%`, height: `${camera.roi.normalized.height * 100}%` }}><i /><i /><i /><i /></div></div>
      <footer className="camera-footer"><button aria-label={`Snapshot ${camera.label}`} onClick={(event) => { event.stopPropagation(); void captureSnapshotCommand(camera.boxId).catch(console.error); }}><Camera size={18} /></button><SignalHigh className="signal-good" size={20} /><button className="camera-settings" aria-label="Camera information"><Settings2 size={17} /></button></footer>
    </article>
  );
}

export function CameraWall() {
  const allCameras = useArenaStore((state) => state.cameras);
  const cameras = allCameras.filter((camera) => camera.enabled);
  return <div className="camera-wall" data-count={cameras.length}>{cameras.map((camera) => <div className="camera-slot" key={camera.boxId}><CameraCard camera={camera} /></div>)}</div>;
}
