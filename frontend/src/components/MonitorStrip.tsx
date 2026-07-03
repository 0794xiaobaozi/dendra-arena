import { ChevronRight, Zap } from "lucide-react";
import { useArenaStore } from "../store";

function formatClock(seconds: number) {
  const whole = Math.max(0, Math.round(seconds));
  return `${String(Math.floor(whole / 3600)).padStart(2, "0")}:${String(Math.floor((whole % 3600) / 60)).padStart(2, "0")}:${String(whole % 60).padStart(2, "0")}`;
}

function ExperimentTimeline() {
  const { shocks, elapsedSec, totalDurationSec } = useArenaStore();
  const visible = shocks.filter((shock) => shock.timeSec <= totalDurationSec);
  return (
    <section className="monitor-card timeline-card card"><h4>EXPERIMENT TIMELINE</h4><div className="timeline-legend"><span><Zap size={14} fill="#f59e0b" />Shock (2.0 s)</span><span><i />Shock Duration</span></div><div className="timeline-plot"><div className="timeline-track" />{Array.from({ length: 9 }, (_, index) => <span className="tick" key={index} style={{ left: `${index * 12.5}%` }}><i />{index * 60} s</span>)}{visible.map((shock) => <span className="shock-marker" key={shock.id} style={{ left: `${(shock.timeSec / totalDurationSec) * 100}%` }}><Zap size={18} fill="#f59e0b" /><i /></span>)}</div><div className="timeline-summary"><span><small>Elapsed</small><strong className="blue-text">{formatClock(elapsedSec)}</strong></span><span><small>Remaining</small><strong>{formatClock(totalDurationSec - elapsedSec)}</strong></span><span><small>Total Duration</small><strong>{formatClock(totalDurationSec)}</strong></span></div></section>
  );
}

function RecentEvents() {
  const allEvents = useArenaStore((state) => state.events);
  const events = allEvents.slice(-5);
  return <section className="monitor-card events-card card"><h4>RECENT EVENTS</h4><div className="event-list">{events.map((event) => <div key={event.id}><time>{event.timeSec.toFixed(3)} s</time><i /><strong>{event.boxLabel}</strong><span>{event.label}</span><em>{event.durationSec ? `${event.durationSec.toFixed(2)} s` : ""}</em></div>)}</div><button className="view-events">View all events...<ChevronRight size={15} /></button></section>;
}

function MotionChart() {
  const { cameras, motionBoxId, selectMotionBox, motion } = useArenaStore();
  const samples = motion[motionBoxId] ?? [];
  const width = 430, height = 92;
  const points = samples.map((sample, index) => `${(index / Math.max(samples.length - 1, 1)) * width},${height - Math.min(sample.motion / 0.9, 1) * height}`).join(" ");
  const current = samples.at(-1)?.motion ?? 0;
  return (
    <section className="monitor-card motion-card card"><h4>MOTION (REAL-TIME) — SELECT WINDOW</h4><div className="segmented motion-tabs">{cameras.filter((camera) => camera.enabled).map((camera) => <button key={camera.boxId} className={motionBoxId === camera.boxId ? "active" : ""} onClick={() => selectMotionBox(camera.boxId)}>{camera.label}</button>)}</div><div className="chart-label">Velocity (a.u.)</div><div className="motion-plot"><svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none"><g className="grid-lines"><line x1="0" y1="23" x2={width} y2="23" /><line x1="0" y1="46" x2={width} y2="46" /><line x1="0" y1="69" x2={width} y2="69" /></g><rect x={width * 0.78} y="0" width={width * 0.22} height={height} className="now-region" /><line x1="0" y1="43" x2={width} y2="43" className="threshold-line" /><polyline points={points} className="motion-line" /></svg><div className="current-motion"><strong>{current.toFixed(2)}</strong><small>Current</small></div></div><div className="chart-axis"><span>-30s</span><span>-20s</span><span>-10s</span><span>Now</span></div><div className="chart-legend"><span><i className="velocity-key" />Velocity</span><span><i className="threshold-key" />Freeze Threshold</span></div></section>
  );
}

export function BottomMonitorStrip() {
  return <div className="bottom-monitor-strip"><ExperimentTimeline /><RecentEvents /><MotionChart /></div>;
}
