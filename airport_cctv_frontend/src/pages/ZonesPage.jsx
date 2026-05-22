import { useState, useEffect, useRef, useCallback } from "react";
import { AlertTriangle, Users, Route, Shield, Save, RefreshCw, CheckCircle, AlertCircle } from "lucide-react";
import SectionCard from "../components/SectionCard.jsx";
import { apiGet, apiPatch } from "../api/client.js";
import { getBackendRawVideoFeedUrl } from "../api/dashboardApi.js";

const ZONE_META = {
  restricted: { label: "Restricted Zone",  color: "#ef4444", fill: "rgba(220,0,0,0.18)",   border: "#ef4444", icon: <AlertTriangle size={16}/> },
  crowd:      { label: "Crowd Zone",        color: "#06b6d4", fill: "rgba(6,182,212,0.15)", border: "#06b6d4", icon: <Users size={16}/> },
  loiter:     { label: "Loitering Zone",    color: "#eab308", fill: "rgba(234,179,8,0.15)", border: "#eab308", icon: <Route size={16}/> },
};

const HANDLE_R = 5.5;   // corner handle radius (SVG units)
const LINE_HANDLE_R = 5; // flow-line handle radius

function toSvg(v) { return v * 100; }
function toRatio(v) { return Math.max(0, Math.min(1, v / 100)); }

function svgPoint(e, svgEl) {
  const pt = svgEl.createSVGPoint();
  pt.x = e.clientX;
  pt.y = e.clientY;
  const ctm = svgEl.getScreenCTM();
  if (!ctm) return { x: 0, y: 0 };
  return pt.matrixTransform(ctm.inverse());
}

// ── Zone rectangle with corner handles + body drag ───────────
function ZoneRect({ group, index, rect, meta, selected, onSelect, onHandleDown, onBodyDown }) {
  const [rx1, ry1, rx2, ry2] = rect;
  const x  = toSvg(rx1), y  = toSvg(ry1);
  const x2 = toSvg(rx2), y2 = toSvg(ry2);
  const w  = x2 - x,     h  = y2 - y;

  const corners = [
    { name: "tl", cx: x,  cy: y  },
    { name: "tr", cx: x2, cy: y  },
    { name: "bl", cx: x,  cy: y2 },
    { name: "br", cx: x2, cy: y2 },
  ];

  return (
    <g>
      <rect
        x={x} y={y} width={w} height={h}
        fill={meta.fill}
        stroke={meta.border}
        strokeWidth={selected ? 1.8 : 1.2}
        style={{ cursor: selected ? "move" : "pointer" }}
        onClick={e => { e.stopPropagation(); onSelect(group, index); }}
        onMouseDown={e => { if (selected) { e.stopPropagation(); onBodyDown(e, group, index); } }}
      />
      <text
        x={x + 1.2} y={y + 5.5}
        fontSize={4} fontWeight="bold"
        fill={meta.border}
        style={{ pointerEvents: "none", userSelect: "none" }}
      >
        {meta.label}
      </text>
      {selected && corners.map(c => (
        <circle
          key={c.name}
          cx={c.cx} cy={c.cy} r={HANDLE_R}
          fill="white" stroke={meta.border} strokeWidth={1.5}
          style={{ cursor: "crosshair" }}
          onMouseDown={e => { e.stopPropagation(); onHandleDown(e, group, index, c.name); }}
        />
      ))}
    </g>
  );
}

// ── Main component ────────────────────────────────────────────
export default function ZonesPage() {
  const videoUrl = getBackendRawVideoFeedUrl();
  const svgRef   = useRef(null);

  const [zones, setZones]       = useState(null);
  const [saving, setSaving]     = useState(false);
  const [status, setStatus]     = useState(null);
  const [selected, setSelected] = useState(null);  // { group, index }
  const dragging = useRef(null);

  useEffect(() => {
    apiGet("/api/zones")
      .then(data => setZones(data))
      .catch(() => {
        setZones({
          restricted:     [{ id:"RZ-1", name:"Restricted Zone", rect:[0.68,0.20,0.98,0.95] }],
          crowd:          [{ id:"CZ-1", name:"Crowd Zone",       rect:[0.05,0.20,0.65,0.95] }],
          loiter:         [{ id:"LZ-1", name:"Loitering Zone",   rect:[0.00,0.00,1.00,1.00] }],
          line_x_ratio:      0.50,
          line_angle_deg:    0.0,
          line_length_ratio: 1.0,
        });
        setStatus({ ok: false, msg: "백엔드 미연결 — 기본값 표시 중" });
      });
  }, []);

  // ── Corner handle drag ──────────────────────────────────────
  const handleHandleDown = useCallback((e, group, idx, corner) => {
    if (!svgRef.current) return;
    e.preventDefault();
    const pt = svgPoint(e, svgRef.current);
    dragging.current = { type: "corner", group, idx, corner, startPt: pt, startRect: [...zones[group][idx].rect] };
  }, [zones]);

  // ── Zone body drag ──────────────────────────────────────────
  const handleBodyDown = useCallback((e, group, idx) => {
    if (!svgRef.current) return;
    e.preventDefault();
    const pt = svgPoint(e, svgRef.current);
    dragging.current = { type: "body", group, idx, startPt: pt, startRect: [...zones[group][idx].rect] };
  }, [zones]);

  // ── Flow-line handle drag ───────────────────────────────────
  const handleLineDown = useCallback((e, role) => {
    if (!svgRef.current || !zones) return;
    e.preventDefault();
    e.stopPropagation();
    const pt = svgPoint(e, svgRef.current);
    dragging.current = {
      type: "line", role,  // "top" | "bot" | "mid"
      startPt: pt,
      startX:  zones.line_x_ratio,
      startA:  zones.line_angle_deg ?? 0,
    };
  }, [zones]);

  // ── Mouse move ──────────────────────────────────────────────
  const handleMouseMove = useCallback(e => {
    if (!dragging.current || !svgRef.current) return;
    const d = dragging.current;
    const pt = svgPoint(e, svgRef.current);

    if (d.type === "corner") {
      const { group, idx, corner, startPt, startRect } = d;
      const dx = (pt.x - startPt.x) / 100;
      const dy = (pt.y - startPt.y) / 100;
      setZones(prev => {
        const rects = prev[group].map((z, i) => {
          if (i !== idx) return z;
          let [rx1, ry1, rx2, ry2] = startRect;
          if (corner === "tl") { rx1 += dx; ry1 += dy; }
          if (corner === "tr") { rx2 += dx; ry1 += dy; }
          if (corner === "bl") { rx1 += dx; ry2 += dy; }
          if (corner === "br") { rx2 += dx; ry2 += dy; }
          rx1 = Math.max(0, Math.min(rx1, rx2 - 0.02));
          ry1 = Math.max(0, Math.min(ry1, ry2 - 0.02));
          rx2 = Math.min(1, Math.max(rx2, rx1 + 0.02));
          ry2 = Math.min(1, Math.max(ry2, ry1 + 0.02));
          return { ...z, rect: [rx1, ry1, rx2, ry2] };
        });
        return { ...prev, [group]: rects };
      });
      return;
    }

    if (d.type === "body") {
      const { group, idx, startPt, startRect } = d;
      const dx = (pt.x - startPt.x) / 100;
      const dy = (pt.y - startPt.y) / 100;
      const zw = startRect[2] - startRect[0];
      const zh = startRect[3] - startRect[1];
      setZones(prev => {
        const rects = prev[group].map((z, i) => {
          if (i !== idx) return z;
          let rx1 = Math.max(0, Math.min(1 - zw, startRect[0] + dx));
          let ry1 = Math.max(0, Math.min(1 - zh, startRect[1] + dy));
          return { ...z, rect: [rx1, ry1, rx1 + zw, ry1 + zh] };
        });
        return { ...prev, [group]: rects };
      });
      return;
    }

    if (d.type === "line") {
      const { role, startPt, startX, startA } = d;
      const lineXSvg = startX * 100;

      if (role === "mid") {
        const newX = Math.max(0.05, Math.min(0.95, startX + (pt.x - startPt.x) / 100));
        setZones(prev => ({ ...prev, line_x_ratio: newX }));
        return;
      }

      // top/bot handle: compute angle from dragged handle to line center (50,50)
      // halfH is the distance in SVG units from center to handle
      setZones(prev => {
        const curLen = Math.max(0.1, Math.min(1.0, prev.line_length_ratio ?? 1.0));
        const hh = 50 * curLen;
        let newAngleRad;
        if (role === "top") {
          // top handle is at yTop = 50 - hh
          // angle: tan(a) = (lineXSvg - pt.x) / hh
          newAngleRad = Math.atan2(lineXSvg - pt.x, hh);
        } else {
          // bot handle is at yBot = 50 + hh
          newAngleRad = Math.atan2(pt.x - lineXSvg, hh);
        }
        const deg = Math.max(-60, Math.min(60, newAngleRad * 180 / Math.PI));
        return { ...prev, line_angle_deg: parseFloat(deg.toFixed(1)) };
      });
    }
  }, []);

  const handleMouseUp = useCallback(() => { dragging.current = null; }, []);

  // ── Save ────────────────────────────────────────────────────
  async function handleSave() {
    if (!zones) return;
    setSaving(true);
    setStatus(null);
    try {
      await apiPatch("/api/zones", zones);
      setStatus({ ok: true, msg: "구역 설정 저장 완료 (즉시 적용됨)" });
      setTimeout(() => setStatus(null), 3000);
    } catch (e) {
      setStatus({ ok: false, msg: `저장 실패: ${e.message}` });
    } finally {
      setSaving(false);
    }
  }

  async function handleReload() {
    try {
      const data = await apiGet("/api/zones");
      setZones(data);
      setStatus({ ok: true, msg: "백엔드 설정 다시 불러옴" });
      setTimeout(() => setStatus(null), 2000);
    } catch {
      setStatus({ ok: false, msg: "로드 실패" });
    }
  }

  function handleRectInput(group, idx, rectIdx, value) {
    const num = parseFloat(value);
    if (isNaN(num)) return;
    setZones(prev => {
      const rects = prev[group].map((z, i) => {
        if (i !== idx) return z;
        const newRect = [...z.rect];
        newRect[rectIdx] = Math.max(0, Math.min(1, num));
        return { ...z, rect: newRect };
      });
      return { ...prev, [group]: rects };
    });
  }

  function handleLineX(value) {
    const num = parseFloat(value);
    if (!isNaN(num)) setZones(prev => ({ ...prev, line_x_ratio: Math.max(0.05, Math.min(0.95, num)) }));
  }

  function handleLineAngle(value) {
    const num = parseFloat(value);
    if (!isNaN(num)) setZones(prev => ({ ...prev, line_angle_deg: Math.max(-60, Math.min(60, num)) }));
  }

  function handleLineLength(value) {
    const num = parseFloat(value);
    if (!isNaN(num)) setZones(prev => ({ ...prev, line_length_ratio: Math.max(0.1, Math.min(1.0, num)) }));
  }

  // ── Flow line SVG geometry ──────────────────────────────────
  const lineX      = zones ? toSvg(zones.line_x_ratio) : 50;
  const angleRad   = zones ? ((zones.line_angle_deg ?? 0) * Math.PI / 180) : 0;
  const lenRatio   = Math.max(0.1, Math.min(1.0, zones?.line_length_ratio ?? 1.0));
  const halfH      = 50 * lenRatio;   // SVG half-height of line (viewBox 0-100, center=50)
  const yTop       = 50 - halfH;
  const yBot       = 50 + halfH;
  const lxTop      = lineX + (yTop - 50) * Math.tan(angleRad);
  const lxBot      = lineX + (yBot - 50) * Math.tan(angleRad);
  const lxMid      = lineX;

  // Dashed segments for flow line SVG
  const LINE_DASH = 7, LINE_GAP = 4;
  function dashedLinePts(x1, y1, x2, y2) {
    const len = Math.hypot(x2 - x1, y2 - y1);
    const dx = (x2 - x1) / len, dy = (y2 - y1) / len;
    const segs = [];
    let pos = 0, draw = true;
    while (pos < len) {
      const seg = draw ? LINE_DASH : LINE_GAP;
      const end = Math.min(pos + seg, len);
      if (draw) segs.push({ x1: x1 + dx * pos, y1: y1 + dy * pos, x2: x1 + dx * end, y2: y1 + dy * end });
      pos = end;
      draw = !draw;
    }
    return segs;
  }

  return (
    <div>
      {status && (
        <div className={`info-strip ${status.ok ? "green" : "red"}`}
          style={{ marginBottom: 14, display: "flex", gap: 8, alignItems: "center" }}>
          {status.ok ? <CheckCircle size={15}/> : <AlertCircle size={15}/>}
          {status.msg}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 16 }}>

        {/* ── Left: live editor ── */}
        <SectionCard
          title="라이브 ROI 편집기"
          action={
            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={handleReload} disabled={saving}
                style={{ display:"flex", alignItems:"center", gap:5, background:"#f1f5f9", border:"1px solid #e2e8f0", borderRadius:8, padding:"6px 12px", cursor:"pointer", fontSize:13, color:"#475569" }}>
                <RefreshCw size={13}/> 재로드
              </button>
              <button onClick={handleSave} disabled={saving || !zones}
                style={{ display:"flex", alignItems:"center", gap:5, background:"#2563eb", border:"none", borderRadius:8, padding:"6px 14px", cursor:"pointer", fontSize:13, color:"#fff", opacity: saving ? 0.6 : 1 }}>
                <Save size={13}/> {saving ? "저장 중..." : "저장 적용"}
              </button>
            </div>
          }
        >
          <p style={{ fontSize:12, color:"#64748b", margin:"0 0 10px" }}>
            구역 클릭 후 코너 핸들로 크기 조정, 내부 드래그로 이동 | 라인 핸들로 위치·회전 조정
          </p>

          <div style={{ position:"relative", background:"#000", borderRadius:10, overflow:"hidden" }}>
            <img
              src={videoUrl}
              alt="CCTV Live"
              style={{ width:"100%", display:"block" }}
              onError={e => { e.currentTarget.style.minHeight = "240px"; }}
            />

            {zones && (
              <svg
                ref={svgRef}
                viewBox="0 0 100 100"
                preserveAspectRatio="none"
                style={{ position:"absolute", inset:0, width:"100%", height:"100%", overflow:"visible" }}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
                onMouseLeave={handleMouseUp}
                onClick={e => { if (e.target === svgRef.current) setSelected(null); }}
              >
                {/* Loitering Zone */}
                {zones.loiter.map((z, i) => {
                  const [rx1,ry1,rx2,ry2] = z.rect;
                  const isFull = rx1===0&&ry1===0&&rx2===1&&ry2===1;
                  if (isFull) return (
                    <rect key={`lz-${i}`}
                      x={toSvg(rx1)} y={toSvg(ry1)}
                      width={toSvg(rx2-rx1)} height={toSvg(ry2-ry1)}
                      fill="none" stroke="#eab308" strokeWidth={0.6} strokeDasharray="3 2"
                      style={{ cursor:"pointer" }}
                      onClick={() => setSelected({ group:"loiter", index:i })}
                    />
                  );
                  return (
                    <ZoneRect key={`lz-${i}`} group="loiter" index={i} rect={z.rect}
                      meta={ZONE_META.loiter}
                      selected={selected?.group==="loiter" && selected?.index===i}
                      onSelect={(g,idx) => setSelected({group:g,index:idx})}
                      onHandleDown={handleHandleDown}
                      onBodyDown={handleBodyDown}
                    />
                  );
                })}

                {/* Crowd Zone */}
                {zones.crowd.map((z, i) => (
                  <ZoneRect key={`cz-${i}`} group="crowd" index={i} rect={z.rect}
                    meta={ZONE_META.crowd}
                    selected={selected?.group==="crowd" && selected?.index===i}
                    onSelect={(g,idx) => setSelected({group:g,index:idx})}
                    onHandleDown={handleHandleDown}
                    onBodyDown={handleBodyDown}
                  />
                ))}

                {/* Restricted Zone */}
                {zones.restricted.map((z, i) => (
                  <ZoneRect key={`rz-${i}`} group="restricted" index={i} rect={z.rect}
                    meta={ZONE_META.restricted}
                    selected={selected?.group==="restricted" && selected?.index===i}
                    onSelect={(g,idx) => setSelected({group:g,index:idx})}
                    onHandleDown={handleHandleDown}
                    onBodyDown={handleBodyDown}
                  />
                ))}

                {/* Flow Line — dashed + handles */}
                {dashedLinePts(lxTop, yTop, lxBot, yBot).map((s, k) => (
                  <line key={k} x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2}
                    stroke="#22c55e" strokeWidth={1.4} />
                ))}
                <text x={lxMid + 1.2} y={Math.max(4.5, yTop - 1)} fontSize={3.2} fill="#22c55e" fontWeight="bold">Flow</text>

                {/* Top rotation handle */}
                <circle
                  cx={lxTop} cy={yTop} r={LINE_HANDLE_R}
                  fill="#22c55e" stroke="white" strokeWidth={1.2}
                  style={{ cursor:"crosshair" }}
                  onMouseDown={e => handleLineDown(e, "top")}
                />
                {/* Mid position handle */}
                <circle
                  cx={lxMid} cy={50} r={LINE_HANDLE_R}
                  fill="white" stroke="#22c55e" strokeWidth={1.5}
                  style={{ cursor:"ew-resize" }}
                  onMouseDown={e => handleLineDown(e, "mid")}
                />
                {/* Bottom rotation handle */}
                <circle
                  cx={lxBot} cy={yBot} r={LINE_HANDLE_R}
                  fill="#22c55e" stroke="white" strokeWidth={1.2}
                  style={{ cursor:"crosshair" }}
                  onMouseDown={e => handleLineDown(e, "bot")}
                />
              </svg>
            )}
          </div>

          {/* Legend */}
          <div style={{ display:"flex", gap:16, marginTop:10, fontSize:12, color:"#64748b", flexWrap:"wrap" }}>
            {Object.entries(ZONE_META).map(([k, m]) => (
              <span key={k} style={{ display:"flex", alignItems:"center", gap:5 }}>
                <span style={{ width:12, height:12, borderRadius:3, background:m.color, display:"inline-block" }}/>
                {m.label}
              </span>
            ))}
            <span style={{ display:"flex", alignItems:"center", gap:5 }}>
              <span style={{ width:16, borderTop:"2px dashed #22c55e", display:"inline-block" }}/>
              Flow Line
            </span>
          </div>
        </SectionCard>

        {/* ── Right: edit panel ── */}
        <div style={{ display:"flex", flexDirection:"column", gap:12 }}>

          {/* Selected zone editor */}
          {selected && zones && (
            <SectionCard title={`편집 중: ${ZONE_META[selected.group]?.label}`}>
              {(() => {
                const z = zones[selected.group][selected.index];
                const labels = ["Left (x1)", "Top (y1)", "Right (x2)", "Bottom (y2)"];
                return (
                  <div>
                    <div style={{ fontSize:12, color:"#64748b", marginBottom:8 }}>
                      비율 좌표 (0.00 ~ 1.00) — 드래그 또는 직접 입력
                    </div>
                    {z.rect.map((val, ri) => (
                      <div key={ri} style={{ display:"flex", alignItems:"center", gap:8, marginBottom:6 }}>
                        <label style={{ fontSize:12, color:"#475569", width:80 }}>{labels[ri]}</label>
                        <input
                          type="number" step={0.01} min={0} max={1}
                          value={val.toFixed(3)}
                          onChange={e => handleRectInput(selected.group, selected.index, ri, e.target.value)}
                          style={{ flex:1, background:"#f8fafc", border:"1px solid #e2e8f0", borderRadius:6, padding:"4px 8px", fontSize:13, color:"#1e293b" }}
                        />
                      </div>
                    ))}
                    <div style={{ marginTop:8, padding:"8px 10px", background:"#f8fafc", borderRadius:8, fontSize:11, color:"#64748b" }}>
                      x1={z.rect[0].toFixed(3)}, y1={z.rect[1].toFixed(3)}, x2={z.rect[2].toFixed(3)}, y2={z.rect[3].toFixed(3)}
                    </div>
                  </div>
                );
              })()}
            </SectionCard>
          )}

          {/* Flow Line controls */}
          {zones && (
            <SectionCard title="Flow Line (출입 카운팅 라인)">
              <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:10 }}>
                <label style={{ fontSize:13, color:"#475569", width:70, flexShrink:0 }}>X 위치</label>
                <input
                  type="range" min={0.05} max={0.95} step={0.01}
                  value={zones.line_x_ratio}
                  onChange={e => handleLineX(e.target.value)}
                  style={{ flex:1 }}
                />
                <span style={{ fontSize:13, color:"#2563eb", width:44, textAlign:"right" }}>
                  {(zones.line_x_ratio * 100).toFixed(0)}%
                </span>
              </div>
              <div style={{ display:"flex", alignItems:"center", gap:8 }}>
                <label style={{ fontSize:13, color:"#475569", width:70, flexShrink:0 }}>각도 (°)</label>
                <input
                  type="range" min={-60} max={60} step={1}
                  value={zones.line_angle_deg ?? 0}
                  onChange={e => handleLineAngle(e.target.value)}
                  style={{ flex:1 }}
                />
                <span style={{ fontSize:13, color:"#2563eb", width:44, textAlign:"right" }}>
                  {(zones.line_angle_deg ?? 0).toFixed(0)}°
                </span>
              </div>
              <div style={{ display:"flex", alignItems:"center", gap:8, marginTop:10 }}>
                <label style={{ fontSize:13, color:"#475569", width:70, flexShrink:0 }}>길이 (%)</label>
                <input
                  type="range" min={0.1} max={1.0} step={0.05}
                  value={zones.line_length_ratio ?? 1.0}
                  onChange={e => handleLineLength(e.target.value)}
                  style={{ flex:1 }}
                />
                <span style={{ fontSize:13, color:"#2563eb", width:44, textAlign:"right" }}>
                  {Math.round((zones.line_length_ratio ?? 1.0) * 100)}%
                </span>
              </div>
              <div style={{ marginTop:8, fontSize:11, color:"#94a3b8" }}>
                위·아래 녹색 핸들: 회전 | 중간 흰색 핸들: 좌우 이동
              </div>
            </SectionCard>
          )}

          {/* Zone event conditions */}
          <SectionCard title="구역 이벤트 조건">
            {[
              { id:"RZ-1", name:"Restricted Zone", color:"#ef4444", event:"침입 즉시 EVENT", debounce:"5초",  icon:<AlertTriangle size={16}/> },
              { id:"CZ-1", name:"Crowd Zone",       color:"#06b6d4", event:"3명↑ 1초→ALERT / 3초→EVENT", debounce:"8초", icon:<Users size={16}/> },
              { id:"LZ-1", name:"Loitering Zone",   color:"#eab308", event:"15초→ALERT / 30초→EVENT",  debounce:"60초", icon:<Route size={16}/> },
              { id:"FD",   name:"Fall Detection",   color:"#8b5cf6", event:"종횡비 급변 즉시 EVENT",   debounce:"10초", icon:<Shield size={16}/> },
            ].map(z => (
              <div key={z.id} style={{ display:"flex", alignItems:"flex-start", gap:10, padding:"8px 0", borderBottom:"1px solid #f1f5f9" }}>
                <div style={{ width:30, height:30, borderRadius:8, background:`${z.color}20`, color:z.color, display:"grid", placeItems:"center", flexShrink:0 }}>
                  {z.icon}
                </div>
                <div style={{ flex:1 }}>
                  <div style={{ fontWeight:700, fontSize:13, color:"#1e293b" }}>{z.id} — {z.name}</div>
                  <div style={{ fontSize:11, color:z.color, marginTop:2 }}>{z.event}</div>
                  <div style={{ fontSize:11, color:"#94a3b8" }}>Debounce: {z.debounce}</div>
                </div>
              </div>
            ))}
          </SectionCard>
        </div>
      </div>
    </div>
  );
}
