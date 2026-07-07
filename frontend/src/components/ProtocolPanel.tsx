import { Check, ChevronDown, PanelRightClose } from "lucide-react";
import { useArenaStore } from "../store";

export function RightProtocolPanel({ onCollapse }: { onCollapse: () => void }) {
  const { cameras, selectedBoxId, selectBox, shocks } = useArenaStore();
  const camera = cameras.find((item) => item.boxId === selectedBoxId) ?? cameras[0];
  if (!camera) {
    return (
      <aside className="right-protocol-panel">
        <div className="protocol-heading"><div className="protocol-title"><strong>PROTOCOL</strong><button className="icon-button" aria-label="Collapse protocol panel" onClick={onCollapse}><PanelRightClose size={15} /></button></div></div>
        <section className="protocol-card card"><p>No session loaded. Configure and save a session in Setup first.</p></section>
      </aside>
    );
  }
  return (
    <aside className="right-protocol-panel">
      <div className="protocol-heading"><div className="protocol-title"><strong>PROTOCOL</strong><button className="icon-button" aria-label="Collapse protocol panel" onClick={onCollapse}><PanelRightClose size={15} /></button></div><label>Target Box:<span className="select-wrap"><select value={camera.boxId} onChange={(event) => selectBox(event.target.value)}>{cameras.filter((item) => item.enabled).map((item) => <option key={item.boxId} value={item.boxId}>{item.label}</option>)}</select><ChevronDown size={14} /></span><i className="status-dot ok" /></label></div>
      <section className="protocol-card card"><h4>Assigned Protocol</h4><div className="readonly-field">{camera.protocolName}</div><p>Contextual fear conditioning with foot shock.</p></section>
      <section className="protocol-card roi-detail card"><h4>ROI (Read Only)</h4><div className="roi-detail-content"><dl><div><dt>Preset:</dt><dd>{camera.roi.preset}</dd></div><div><dt>Shape:</dt><dd>Rectangle</dd></div><div><dt>Coverage:</dt><dd>{camera.roi.coveragePercent.toFixed(1)}% of area</dd></div><div><dt>Status:</dt><dd className="healthy"><i className="status-dot ok" />Active</dd></div></dl><div className="roi-mini-preview"><div style={{ left: `${camera.roi.normalized.x * 100}%`, top: `${camera.roi.normalized.y * 100}%`, width: `${camera.roi.normalized.width * 100}%`, height: `${camera.roi.normalized.height * 100}%` }}><i /><i /><i /><i /></div></div></div></section>
      <section className="protocol-card freeze-detail card"><h4>Freeze Detection (Read Only)</h4><dl><div><dt>Freeze Threshold:</dt><dd>{camera.freezeStrategy.threshold.toFixed(5)}</dd></div><div><dt>Minimum Freeze Duration:</dt><dd>{camera.freezeStrategy.minDurationSec.toFixed(2)} s</dd></div></dl></section>
      <section className="protocol-card shock-detail card"><h4>Shock Schedule (Read Only)</h4><div className="shock-table-scroll"><table><thead><tr><th>#</th><th>Time (s)</th><th>Duration (s)</th><th>Intensity (mA)</th></tr></thead><tbody>{shocks.map((shock, index) => <tr key={shock.id} className={shock.status === "triggered" ? "triggered" : ""}><td>{shock.status === "triggered" ? <Check size={12} /> : index + 1}</td><td>{shock.timeSec}</td><td>{shock.durationSec.toFixed(1)}</td><td>{shock.intensityMA.toFixed(2)}</td></tr>)}</tbody></table></div></section>
    </aside>
  );
}
