import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
  LineChart, Line, Area, AreaChart,
} from "recharts";
import { ChartColumn, Zap, Bell, Activity, Clock, Cpu, TrendingUp } from "lucide-react";
import SectionCard from "../components/SectionCard.jsx";
import { usePolling } from "../hooks/usePolling.js";
import { usePrometheusRange } from "../hooks/usePrometheus.js";

const MODE_COLORS = {
  IDLE:  "#94a3b8",
  WATCH: "#3b82f6",
  ALERT: "#f97316",
  EVENT: "#ef4444",
};

const EVENT_COLORS = {
  RestrictedZone: "#ef4444",
  CrowdDensity:   "#f97316",
  Loitering:      "#eab308",
  FallDetected:   "#8b5cf6",
  Enter:          "#22c55e",
  Exit:           "#06b6d4",
};

// ── Custom bar tooltip ────────────────────────────────────────
function CustomBarTooltip({ active, payload, label, unit = "" }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background:"#1e293b", border:"1px solid #334155", borderRadius:10, padding:"8px 12px", fontSize:12 }}>
      <div style={{ color:"#94a3b8", marginBottom:4 }}>{label}</div>
      <div style={{ color:"#fff", fontWeight:700 }}>{payload[0].value}{unit}</div>
    </div>
  );
}

// ── Stat card (mini) ──────────────────────────────────────────
function StatCard({ icon, label, value, sub, color = "blue" }) {
  const bg = { blue:"#eff6ff", green:"#f0fdf4", orange:"#fff7ed", purple:"#faf5ff", red:"#fef2f2" };
  const fg = { blue:"#2563eb", green:"#16a34a", orange:"#f97316", purple:"#7c3aed",  red:"#dc2626" };
  return (
    <div style={{ background:"#fff", border:"1px solid #e5eaf3", borderRadius:16, padding:"18px 20px",
      display:"flex", alignItems:"center", gap:14 }}>
      <div style={{ width:46, height:46, borderRadius:12, background:bg[color], color:fg[color],
        display:"grid", placeItems:"center", flexShrink:0 }}>
        {icon}
      </div>
      <div>
        <div style={{ fontSize:22, fontWeight:900, color:"#0f172a", lineHeight:1 }}>{value}</div>
        <div style={{ fontSize:13, fontWeight:700, color:"#334155", marginTop:4 }}>{label}</div>
        {sub && <div style={{ fontSize:11, color:"#94a3b8", marginTop:2 }}>{sub}</div>}
      </div>
    </div>
  );
}

// ── Chart section wrapper ─────────────────────────────────────
function ChartCard({ title, children, badge }) {
  return (
    <div style={{ background:"#fff", border:"1px solid #e5eaf3", borderRadius:16, padding:"20px 22px" }}>
      <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:16 }}>
        <span style={{ fontSize:14, fontWeight:800, color:"#1e293b" }}>{title}</span>
        {badge && <span style={{ fontSize:11, fontWeight:700, background:"#f1f5f9", color:"#64748b",
          borderRadius:999, padding:"2px 10px" }}>{badge}</span>}
      </div>
      {children}
    </div>
  );
}

// ── No-data placeholder ───────────────────────────────────────
function NoData({ msg = "데이터 없음" }) {
  return (
    <div style={{ height:180, display:"grid", placeItems:"center", color:"#94a3b8", fontSize:13,
      background:"#f8fafc", borderRadius:10, border:"1px dashed #e2e8f0" }}>
      {msg}
    </div>
  );
}

export default function ReportsPage() {
  const { data: summary, loading } = usePolling("/summary", 5000);
  const { data: eventsData }       = usePolling("/events", 5000);

  const { data: fpsTrend,   error: promErr } = usePrometheusRange("cctv_fps", 10, 5);
  const { data: powerTrend }                 = usePrometheusRange("cctv_board_power_w", 10, 5);
  const { data: eventRate }                  = usePrometheusRange("rate(cctv_event_total[1m])", 10, 5);
  const { data: cpuTempTrend }               = usePrometheusRange("cctv_cpu_temp_c", 10, 5);
  const prometheusAvailable = !promErr;

  const modes = summary?.modes || {};
  const modeChartData = Object.entries(modes).map(([mode, stats]) => ({
    mode,
    samples:   stats.samples || 0,
    avg_fps:   +(stats.avg_fps || 0).toFixed(1),
    avg_power: +(stats.avg_power_w || 0).toFixed(2),
    avg_infer: +(stats.avg_inference_ms || 0).toFixed(1),
  }));

  const allEvents = eventsData?.events || [];
  const eventTypeCounts = {};
  allEvents.forEach(e => { eventTypeCounts[e.type] = (eventTypeCounts[e.type] || 0) + 1; });
  const eventChartData = Object.entries(eventTypeCounts)
    .map(([type, count]) => ({ type, count }))
    .sort((a, b) => b.count - a.count);

  const totalSamples   = modeChartData.reduce((s, r) => s + r.samples, 0);
  const weightedPower  = modeChartData.reduce((s, r) => s + r.avg_power * r.samples, 0);
  const overallAvgPower = totalSamples > 0 ? (weightedPower / totalSamples).toFixed(1) : "-";
  const topMode = modeChartData.length
    ? modeChartData.reduce((a, b) => a.samples > b.samples ? a : b).mode
    : "-";
  const totalEvents = allEvents.length;
  const avgInfer = modeChartData.filter(d => d.avg_infer > 0).length
    ? (modeChartData.filter(d => d.avg_infer > 0).reduce((s, d) => s + d.avg_infer, 0)
       / modeChartData.filter(d => d.avg_infer > 0).length).toFixed(1)
    : "-";

  return (
    <div style={{ display:"flex", flexDirection:"column", gap:20 }}>

      {/* ── Top stat cards ── */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(4, 1fr)", gap:14 }}>
        <StatCard icon={<Bell size={22}/>}        label="총 이벤트"     value={totalEvents}  sub="런 이후 누적"       color="orange" />
        <StatCard icon={<Zap size={22}/>}         label="평균 전력"     value={overallAvgPower !== "-" ? `${overallAvgPower}W` : "-"}  sub="전체 모드 가중 평균"  color="green" />
        <StatCard icon={<ChartColumn size={22}/>} label="총 샘플 수"    value={totalSamples} sub="CSV 로그 행"         color="blue" />
        <StatCard icon={<Clock size={22}/>}       label="평균 추론 ms"  value={avgInfer !== "-" ? `${avgInfer}ms` : "-"} sub="모드 평균"  color="purple" />
      </div>

      {/* ── Mode charts row ── */}
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:16 }}>
        <ChartCard title="모드별 샘플 수" badge={`총 ${totalSamples}건`}>
          {loading || modeChartData.every(d => d.samples === 0) ? (
            <NoData msg={loading ? "수집 중..." : "백엔드를 더 오래 실행하세요"} />
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={modeChartData} barCategoryGap="30%">
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                <XAxis dataKey="mode" tick={{ fontSize:12, fontWeight:700, fill:"#475569" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize:11, fill:"#94a3b8" }} axisLine={false} tickLine={false} />
                <Tooltip content={<CustomBarTooltip unit="건" />} cursor={{ fill:"rgba(0,0,0,0.04)" }} />
                <Bar dataKey="samples" radius={[8, 8, 0, 0]}>
                  {modeChartData.map(e => <Cell key={e.mode} fill={MODE_COLORS[e.mode] || "#94a3b8"} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
          {!loading && modeChartData.some(d => d.samples > 0) && (
            <div style={{ display:"flex", gap:10, marginTop:10, flexWrap:"wrap" }}>
              {modeChartData.filter(d => d.samples > 0).map(d => (
                <div key={d.mode} style={{ display:"flex", alignItems:"center", gap:5, fontSize:12 }}>
                  <span style={{ width:8, height:8, borderRadius:999, background:MODE_COLORS[d.mode], display:"inline-block" }}/>
                  <span style={{ color:"#475569", fontWeight:700 }}>{d.mode}</span>
                  <span style={{ color:"#94a3b8" }}>{((d.samples / totalSamples) * 100).toFixed(1)}%</span>
                </div>
              ))}
            </div>
          )}
        </ChartCard>

        <ChartCard title="이벤트 타입별 발생 횟수" badge={`${eventChartData.length}종류`}>
          {eventChartData.length === 0 ? (
            <NoData msg="아직 이벤트 없음" />
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={eventChartData} barCategoryGap="30%">
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                <XAxis dataKey="type" tick={{ fontSize:10, fill:"#475569" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize:11, fill:"#94a3b8" }} axisLine={false} tickLine={false} />
                <Tooltip content={<CustomBarTooltip unit="건" />} cursor={{ fill:"rgba(0,0,0,0.04)" }} />
                <Bar dataKey="count" radius={[8, 8, 0, 0]}>
                  {eventChartData.map(e => (
                    <Cell key={e.type} fill={EVENT_COLORS[e.type] || "#6366f1"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard title="모드별 평균 전력 (W)">
          {modeChartData.every(d => !d.avg_power) ? (
            <NoData msg="전력 데이터 없음 (INA3221 미연결 가능)" />
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={modeChartData} barCategoryGap="30%">
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                <XAxis dataKey="mode" tick={{ fontSize:12, fontWeight:700, fill:"#475569" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize:11, fill:"#94a3b8" }} axisLine={false} tickLine={false} unit="W" />
                <Tooltip content={<CustomBarTooltip unit="W" />} cursor={{ fill:"rgba(0,0,0,0.04)" }} />
                <Bar dataKey="avg_power" radius={[8, 8, 0, 0]}>
                  {modeChartData.map(e => <Cell key={e.mode} fill={MODE_COLORS[e.mode] || "#94a3b8"} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard title="모드별 평균 추론 시간 (ms)">
          {modeChartData.every(d => !d.avg_infer) ? (
            <NoData msg="추론 데이터 없음" />
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={modeChartData} barCategoryGap="30%">
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                <XAxis dataKey="mode" tick={{ fontSize:12, fontWeight:700, fill:"#475569" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize:11, fill:"#94a3b8" }} axisLine={false} tickLine={false} unit="ms" />
                <Tooltip content={<CustomBarTooltip unit="ms" />} cursor={{ fill:"rgba(0,0,0,0.04)" }} />
                <Bar dataKey="avg_infer" radius={[8, 8, 0, 0]}>
                  {modeChartData.map(e => <Cell key={e.mode} fill={MODE_COLORS[e.mode] || "#94a3b8"} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>
      </div>

      {/* ── Prometheus real-time trend ── */}
      <div style={{ background:"#fff", border:"1px solid #e5eaf3", borderRadius:16, padding:"20px 22px" }}>
        <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:16 }}>
          <span style={{ fontSize:14, fontWeight:800, color:"#1e293b" }}>실시간 트렌드 (Prometheus · 최근 10분)</span>
          <span style={{ fontSize:11, fontWeight:700, padding:"3px 10px", borderRadius:999,
            background: prometheusAvailable ? "#f0fdf4" : "#fff7ed",
            color:      prometheusAvailable ? "#16a34a" : "#f97316" }}>
            {prometheusAvailable ? "● 연결됨" : "● Prometheus 미연결"}
          </span>
        </div>

        {!prometheusAvailable ? (
          <div className="info-strip orange">
            Prometheus 미연결 — docker-compose up -d 실행 후 새로고침하세요.
          </div>
        ) : (
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:20 }}>
            {[
              { label:"FPS 추이",       data:fpsTrend,     color:"#22c55e", unit:" fps" },
              { label:"전력 추이 (W)",   data:powerTrend,   color:"#eab308", unit:"W" },
              { label:"CPU 온도 (°C)",   data:cpuTempTrend, color:"#f97316", unit:"°C" },
              { label:"이벤트율 (/s)",   data:eventRate,    color:"#ef4444", unit:"/s" },
            ].map(({ label, data, color, unit }) => (
              <div key={label}>
                <div style={{ fontSize:12, fontWeight:700, color:"#475569", marginBottom:8 }}>{label}</div>
                <ResponsiveContainer width="100%" height={150}>
                  <AreaChart data={data}>
                    <defs>
                      <linearGradient id={`grad-${label}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%"  stopColor={color} stopOpacity={0.18} />
                        <stop offset="95%" stopColor={color} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                    <XAxis dataKey="time" tick={{ fontSize:10, fill:"#94a3b8" }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                    <YAxis tick={{ fontSize:10, fill:"#94a3b8" }} axisLine={false} tickLine={false} unit={unit} width={36} />
                    <Tooltip
                      contentStyle={{ background:"#1e293b", border:"none", borderRadius:8, fontSize:12 }}
                      labelStyle={{ color:"#94a3b8" }}
                      itemStyle={{ color:"#fff" }}
                      formatter={v => [`${v}${unit}`, label]}
                    />
                    <Area type="monotone" dataKey="value" stroke={color} strokeWidth={2}
                      fill={`url(#grad-${label})`} dot={false} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Mode operation timeline ── */}
      <div style={{ background:"#fff", border:"1px solid #e5eaf3", borderRadius:16, padding:"20px 22px" }}>
        <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:16 }}>
          <span style={{ fontSize:14, fontWeight:800, color:"#1e293b" }}>모드 운영 타임라인</span>
          <span style={{ fontSize:11, fontWeight:700, background:"#f1f5f9", color:"#64748b",
            borderRadius:999, padding:"2px 10px" }}>샘플 기준 비율</span>
        </div>

        {totalSamples === 0 ? (
          <div className="info-strip orange">데이터 없음 — 백엔드를 더 오래 실행하세요.</div>
        ) : (
          <>
            {/* Stacked horizontal bar */}
            <ResponsiveContainer width="100%" height={52}>
              <BarChart
                layout="vertical"
                data={[Object.fromEntries(modeChartData.map(d => [d.mode, d.samples]))]}
                margin={{ top:0, right:0, bottom:0, left:0 }}
                barSize={32}
              >
                <XAxis type="number" hide domain={[0, totalSamples]} />
                <YAxis type="category" hide />
                <Tooltip
                  contentStyle={{ background:"#1e293b", border:"none", borderRadius:8, fontSize:12 }}
                  labelStyle={{ color:"#94a3b8" }}
                  itemStyle={{ color:"#fff" }}
                  formatter={(v, name) => [`${((v / totalSamples) * 100).toFixed(1)}%  (${v}건)`, name]}
                />
                {["IDLE","WATCH","ALERT","EVENT"].map((mode, i, arr) => (
                  <Bar
                    key={mode}
                    dataKey={mode}
                    stackId="timeline"
                    fill={MODE_COLORS[mode]}
                    radius={i === 0 ? [6,0,0,6] : i === arr.length-1 ? [0,6,6,0] : [0,0,0,0]}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>

            {/* Legend with % labels */}
            <div style={{ display:"flex", gap:0, marginTop:6, borderRadius:8, overflow:"hidden",
              border:"1px solid #e2e8f0" }}>
              {["IDLE","WATCH","ALERT","EVENT"].map(mode => {
                const d = modeChartData.find(r => r.mode === mode);
                const pct = d && totalSamples > 0 ? ((d.samples / totalSamples) * 100).toFixed(1) : "0.0";
                return (
                  <div key={mode} style={{
                    flex: d ? d.samples : 0,
                    minWidth: d?.samples > 0 ? 40 : 0,
                    background: MODE_COLORS[mode] + "22",
                    borderLeft: `3px solid ${MODE_COLORS[mode]}`,
                    padding:"8px 10px",
                    display: d?.samples > 0 ? "block" : "none",
                  }}>
                    <div style={{ fontSize:11, fontWeight:800, color:MODE_COLORS[mode] }}>{mode}</div>
                    <div style={{ fontSize:13, fontWeight:900, color:"#0f172a" }}>{pct}%</div>
                    <div style={{ fontSize:10, color:"#94a3b8" }}>{d?.samples ?? 0}건</div>
                  </div>
                );
              })}
            </div>

            {/* Per-mode stat grid */}
            <div style={{ display:"grid", gridTemplateColumns:"repeat(4, 1fr)", gap:10, marginTop:14 }}>
              {["IDLE","WATCH","ALERT","EVENT"].map(mode => {
                const d = modeChartData.find(r => r.mode === mode);
                const pct = d && totalSamples > 0 ? ((d.samples / totalSamples) * 100).toFixed(1) : "0.0";
                return (
                  <div key={mode} style={{
                    borderRadius:12, border:`1px solid ${MODE_COLORS[mode]}44`,
                    background: MODE_COLORS[mode] + "0d",
                    padding:"12px 14px",
                  }}>
                    <div style={{ display:"flex", alignItems:"center", gap:6, marginBottom:8 }}>
                      <span style={{ width:10, height:10, borderRadius:999, background:MODE_COLORS[mode],
                        display:"inline-block", flexShrink:0 }}/>
                      <span style={{ fontSize:13, fontWeight:800, color:MODE_COLORS[mode] }}>{mode}</span>
                    </div>
                    <div style={{ fontSize:20, fontWeight:900, color:"#0f172a", lineHeight:1 }}>{pct}%</div>
                    <div style={{ fontSize:11, color:"#64748b", marginTop:4 }}>{d?.samples ?? 0} 샘플</div>
                    <div style={{ marginTop:8, display:"flex", flexDirection:"column", gap:3 }}>
                      {d?.avg_fps > 0 && (
                        <div style={{ fontSize:11, color:"#475569" }}>
                          <span style={{ color:"#94a3b8" }}>FPS </span>{d.avg_fps}
                        </div>
                      )}
                      {d?.avg_power > 0 && (
                        <div style={{ fontSize:11, color:"#475569" }}>
                          <span style={{ color:"#94a3b8" }}>전력 </span>{d.avg_power}W
                        </div>
                      )}
                      {d?.avg_infer > 0 && (
                        <div style={{ fontSize:11, color:"#475569" }}>
                          <span style={{ color:"#94a3b8" }}>추론 </span>{d.avg_infer}ms
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>

      {/* ── Run info ── */}
      {summary && (
        <div style={{ background:"#fff", border:"1px solid #e5eaf3", borderRadius:16, padding:"20px 22px" }}>
          <div style={{ fontSize:14, fontWeight:800, color:"#1e293b", marginBottom:14 }}>런 정보</div>
          <div className="model-info-list">
            <div className="model-info-row"><span>Run ID</span><strong>{summary.run_id}</strong></div>
            <div className="model-info-row"><span>생성 시각</span><strong>{summary.generated_at}</strong></div>
            <div className="model-info-row"><span>디바이스</span><strong>{summary.device_model}</strong></div>
            <div className="model-info-row">
              <span>CSV 경로</span>
              <strong style={{ fontSize:12, wordBreak:"break-all" }}>{summary.csv_path}</strong>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
