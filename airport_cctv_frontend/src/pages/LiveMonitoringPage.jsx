import { AlertTriangle } from "lucide-react";
import SectionCard from "../components/SectionCard.jsx";
import { usePolling } from "../hooks/usePolling.js";
import { getBackendVideoFeedUrl } from "../api/dashboardApi.js";

const MODE_COLOR = { IDLE: "idle", WATCH: "watch", ALERT: "alert", EVENT: "event" };

function MetricRow({ label, value, unit = "", color }) {
  return (
    <div className="live-metric-row">
      <span className="live-metric-label">{label}</span>
      <span className={`live-metric-value ${color || ""}`}>
        {value ?? "-"}{value != null ? unit : ""}
      </span>
    </div>
  );
}

function UsageBar({ label, value }) {
  const v = Math.min(100, Math.max(0, Number(value) || 0));
  const color = v > 85 ? "red" : v > 60 ? "orange" : "blue";
  return (
    <div className="usage-bar-wrap">
      <div className="usage-bar-header">
        <span>{label}</span>
        <span>{v}%</span>
      </div>
      <div className="usage-bar-track">
        <div className={`usage-bar-fill ${color}`} style={{ width: `${v}%` }} />
      </div>
    </div>
  );
}

function LiveMonitoringPage() {
  const { data: metrics } = usePolling("/metrics", 1000);
  const videoUrl = getBackendVideoFeedUrl();

  const mode = metrics?.current_mode || "IDLE";
  const eventLevel = metrics?.event_level || "NONE";
  const eventReason = metrics?.event_reason;
  const loiterTracks = metrics?.loiter_tracks || {};
  const loiterIds = Object.keys(loiterTracks).filter((id) => loiterTracks[id] >= 15);

  return (
    <div>
      {eventLevel !== "NONE" && (
        <div className={`alert-banner ${eventLevel.toLowerCase()}`}>
          <AlertTriangle size={18} />
          <strong>{eventLevel}</strong>
          {eventReason ? ` — ${eventReason}` : ""} 감지됨
        </div>
      )}

      <div className="live-layout">
        <SectionCard
          title="실시간 CCTV 스트림"
          action={
            <div className="live-dot-wrap">
              <span className="connection-dot" />
              <span style={{ fontSize: 13, fontWeight: 700, color: "#16a34a" }}>LIVE</span>
            </div>
          }
        >
        <div className="live-stream-frame">
          <img src={videoUrl} alt="CCTV Live" className="live-stream-img" />
        </div>
          <div className="stream-footer">
            <span>Gate A1 · Cam 01</span>
            <span>Jetson Xavier NX</span>
            <span>{metrics?.camera_ok ? "📷 카메라 정상" : "❌ 카메라 오류"}</span>
          </div>
        </SectionCard>

        <div className="live-metrics-panel">
          <SectionCard title="운영 모드">
            <div className={`mode-big-badge ${MODE_COLOR[mode] || "idle"}`}>{mode}</div>
            <MetricRow
              label="이벤트 레벨"
              value={eventLevel}
              color={eventLevel === "EVENT" ? "red" : eventLevel === "ALERT" ? "orange" : "green"}
            />
            {eventReason && <MetricRow label="이벤트 원인" value={eventReason} />}
            {metrics?.roi_id && <MetricRow label="구역 ID" value={metrics.roi_id} />}
          </SectionCard>

          <SectionCard title="탐지 현황">
            <MetricRow label="감지 인원" value={metrics?.person_count} unit="명" />
            <MetricRow label="FPS" value={metrics?.fps} />
            <MetricRow label="추론 시간" value={metrics?.inference_ms} unit=" ms" />
            <MetricRow label="군중 (CZ-1)" value={metrics?.crowd_count} unit="명" />
            {(metrics?.crowd_duration_sec || 0) > 0 && (
              <MetricRow label="혼잡 지속" value={metrics.crowd_duration_sec} unit=" s" color="orange" />
            )}
            {loiterIds.length > 0 && (
              <MetricRow
                label="배회 중"
                value={loiterIds.map((id) => `ID${id}:${loiterTracks[id]}s`).join(" / ")}
                color="orange"
              />
            )}
          </SectionCard>

          <SectionCard title="시스템 리소스">
            <UsageBar label="CPU 사용률" value={metrics?.cpu_usage_percent} />
            <UsageBar label="GPU 사용률" value={metrics?.gpu_usage_percent} />
            <div style={{ marginTop: 10 }}>
              <MetricRow label="CPU 온도" value={metrics?.cpu_temp_c} unit=" °C" />
              <MetricRow label="GPU 온도" value={metrics?.gpu_temp_c} unit=" °C" />
            </div>
          </SectionCard>

          <SectionCard title="전력 소비">
            <MetricRow label="전체 전력" value={metrics?.board_power_w} unit=" W" color="green" />
            <MetricRow label="VDD_IN" value={metrics?.rail_vdd_in_w} unit=" W" />
            <MetricRow label="CPU_GPU_CV" value={metrics?.rail_cpu_gpu_cv_w} unit=" W" />
            <MetricRow label="VDD_SOC" value={metrics?.rail_soc_w} unit=" W" />
            <MetricRow label="전력 소스" value={metrics?.power_source} />
          </SectionCard>
        </div>
      </div>
    </div>
  );
}

export default LiveMonitoringPage;
