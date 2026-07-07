import { ChevronRight } from "lucide-react";
import { useArenaStore } from "../store";

function formatClock(seconds: number) {
  const whole = Math.max(0, Math.round(seconds));
  return `${String(Math.floor(whole / 3600)).padStart(2, "0")}:${String(Math.floor((whole % 3600) / 60)).padStart(2, "0")}:${String(whole % 60).padStart(2, "0")}`;
}

function ExperimentTimeline() {
  const { shocks, elapsedSec, totalDurationSec } = useArenaStore();
  const visible = shocks.filter((shock) => shock.timeSec <= totalDurationSec);
  return (
    <section className="monitor-card timeline-card card"><h4>EXPERIMENT TIMELINE</h4><div className="timeline-plot"><div className="timeline-track" />{Array.from({ length: 9 }, (_, index) => <span className="tick" key={index} style={{ left: `${index * 12.5}%` }}><i />{index * 60} s</span>)}{visible.map((shock) => <span className="shock-marker" key={shock.id} style={{ left: `${totalDurationSec > 0 ? (shock.timeSec / totalDurationSec) * 100 : 0}%` }}><i /></span>)}</div><div className="timeline-summary"><span><small>Elapsed</small><strong className="blue-text">{formatClock(elapsedSec)}</strong></span><span><small>Remaining</small><strong>{formatClock(totalDurationSec - elapsedSec)}</strong></span><span><small>Total Duration</small><strong>{formatClock(totalDurationSec)}</strong></span></div></section>
  );
}

function RecentEvents() {
  const allEvents = useArenaStore((state) => state.events);
  const events = allEvents.slice(-100);
  return <section className="monitor-card events-card card"><h4>RECENT EVENTS</h4><div className="event-list"><div className="event-grid">{events.map((event) => <div className="event-row" key={event.id}><time>{event.timeSec.toFixed(3)} s</time><i /><strong>{event.boxLabel}</strong><span>{event.label}</span><em>{event.durationSec ? `${event.durationSec.toFixed(2)} s` : ""}</em></div>)}</div></div><button className="view-events">View all events...<ChevronRight size={15} /></button></section>;
}

function MotionChart() {
  const { cameras, motionBoxId, selectMotionBox, motion } = useArenaStore();
  const camera = cameras.find((c) => c.boxId === motionBoxId);
  const threshold = camera?.freezeStrategy.threshold ?? 0.48;
  const samples = motion[motionBoxId] ?? [];
  const width = 430, height = 92;
  const threshFraction = 0.5;
  const thresholdY = height * threshFraction;
  const scaleY = (value: number) => {
    if (value <= threshold) return height - (value / threshold) * thresholdY;
    return (1 - Math.min((value - threshold) / (1 - threshold), 1)) * (height - thresholdY);
  };
  const points = samples.map((sample, index) => `${(index / Math.max(samples.length - 1, 1)) * width},${scaleY(sample.motion)}`).join(" ");
  const current = samples.at(-1)?.motion ?? 0;
  return (
    <section className="monitor-card motion-card card"><h4>MOTION (REAL-TIME) — SELECT WINDOW</h4><div className="segmented motion-tabs">{cameras.filter((camera) => camera.enabled).map((camera) => <button key={camera.boxId} className={motionBoxId === camera.boxId ? "active" : ""} onClick={() => selectMotionBox(camera.boxId)}>{camera.label}</button>)}</div><div className="chart-label">Velocity (a.u.)</div><div className="motion-plot"><svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none"><g className="grid-lines"><line x1="0" y1={thresholdY * 0.5} x2={width} y2={thresholdY * 0.5} /><line x1="0" y1={thresholdY} x2={width} y2={thresholdY} /><line x1="0" y1={thresholdY + (height - thresholdY) * 0.5} x2={width} y2={thresholdY + (height - thresholdY) * 0.5} /></g><rect x={width * 0.78} y="0" width={width * 0.22} height={height} className="now-region" /><line x1="0" y1={thresholdY} x2={width} y2={thresholdY} className="threshold-line" /><polyline points={points} className="motion-line" /></svg><div className="current-motion"><strong>{current.toFixed(5)}</strong><small>Current</small></div></div><div className="chart-axis"><span>-30s</span><span>-20s</span><span>-10s</span><span>Now</span></div><div className="chart-legend"><span><i className="velocity-key" />Velocity</span><span><i className="threshold-key" />Freeze Threshold</span></div></section>
  );
}

export function BottomMonitorStrip() {
  return <div className="bottom-monitor-strip"><ExperimentTimeline /><RecentEvents /><MotionChart /></div>;
}
