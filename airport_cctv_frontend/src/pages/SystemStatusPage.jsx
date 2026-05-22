import { Camera, Cpu, Thermometer, Zap, Activity, CheckCircle, XCircle } from "lucide-react";
import SectionCard from "../components/SectionCard.jsx";
import SummaryCard from "../components/SummaryCard.jsx";
import { usePolling } from "../hooks/usePolling.js";

function StatusDot({ ok }) {
  return ok ? (
    <CheckCircle size={20} style={{ color: "#16a34a" }} />
  ) : (
    <XCircle size={20} style={{ color: "#ef4444" }} />
  );
}

function UsageBar({ label, value, unit = "%" }) {
  const v = Math.min(100, Math.max(0, Number(value) || 0));
  const color = v > 85 ? "red" : v > 60 ? "orange" : "blue";
  return (
    <div className="usage-bar-wrap" style={{ marginBottom: 14 }}>
      <div className="usage-bar-header">
        <span style={{ fontWeight: 600 }}>{label}</span>
        <span style={{ fontWeight: 700 }}>{v}{unit}</span>
      </div>
      <div className="usage-bar-track" style={{ height: 10 }}>
        <div className={`usage-bar-fill ${color}`} style={{ width: `${v}%` }} />
      </div>
    </div>
  );
}

function PowerRailRow({ label, value }) {
  return (
    <div className="live-metric-row">
      <span className="live-metric-label">{label}</span>
      <span className="live-metric-value green">
        {value != null ? `${value} W` : "-"}
      </span>
    </div>
  );
}

function SystemStatusPage() {
  const { data: m, loading } = usePolling("/metrics", 1000);

  const modeColor = { IDLE: "#94a3b8", WATCH: "#3b82f6", ALERT: "#f97316", EVENT: "#ef4444" };
  const currentMode = m?.current_mode || "IDLE";

  return (
    <div>
      <div className="summary-grid" style={{ marginBottom: 16 }}>
        <SummaryCard
          icon={<Camera size={28} />}
          label="카메라"
          value={m?.camera_ok ? "정상" : "오류"}
          helper="V4L2 연결 상태"
          color={m?.camera_ok ? "green" : "orange"}
        />
        <SummaryCard
          icon={<Activity size={28} />}
          label="AI 모델"
          value={m?.model_ok ? "로드됨" : "오류"}
          helper={m?.model_name || "TensorRT 엔진"}
          color={m?.model_ok ? "green" : "orange"}
        />
        <SummaryCard
          icon={<Zap size={28} />}
          label="현재 전력"
          value={m?.board_power_w != null ? `${m.board_power_w}W` : "-"}
          helper={m?.power_source || "측정 중"}
          color="green"
        />
        <SummaryCard
          icon={<Cpu size={28} />}
          label="현재 모드"
          value={currentMode}
          helper={`imgsz:${m?.imgsz || "-"} / N:${m?.infer_every_n || "-"}`}
          color="blue"
        />
        <SummaryCard
          icon={<Activity size={28} />}
          label="FPS"
          value={m?.fps ?? "-"}
          helper={`추론: ${m?.inference_ms ?? "-"} ms`}
          color="blue"
        />
      </div>

      <div className="sys-grid">
        <SectionCard title="CPU / GPU 사용률">
          {loading ? (
            <div className="info-strip blue">로딩 중...</div>
          ) : (
            <>
              <UsageBar label="CPU 사용률" value={m?.cpu_usage_percent} />
              <UsageBar label="GPU 사용률" value={m?.gpu_usage_percent} />
            </>
          )}
        </SectionCard>

        <SectionCard title="온도">
          <div className="temp-grid">
            <div className="temp-card">
              <Thermometer size={28} style={{ color: "#f97316" }} />
              <div className="temp-value">{m?.cpu_temp_c ?? "-"}°C</div>
              <div className="temp-label">CPU</div>
            </div>
            <div className="temp-card">
              <Thermometer size={28} style={{ color: "#ef4444" }} />
              <div className="temp-value">{m?.gpu_temp_c ?? "-"}°C</div>
              <div className="temp-label">GPU</div>
            </div>
          </div>
        </SectionCard>

        <SectionCard title="전력 레일 (INA3221)">
          <PowerRailRow label="VDD_IN (전체)" value={m?.rail_vdd_in_w} />
          <PowerRailRow label="VDD_CPU_GPU_CV" value={m?.rail_cpu_gpu_cv_w} />
          <PowerRailRow label="VDD_SOC" value={m?.rail_soc_w} />
          <div className="live-metric-row" style={{ marginTop: 8 }}>
            <span className="live-metric-label">측정 방식</span>
            <span className="live-metric-value">{m?.power_source || "-"}</span>
          </div>
        </SectionCard>

        <SectionCard title="연결 상태">
          <div className="status-check-list">
            <div className="status-check-row">
              <StatusDot ok={m?.camera_ok} />
              <span>카메라 (V4L2)</span>
              <span className="td-muted">{m?.camera_ok ? "연결됨" : "오류"}</span>
            </div>
            <div className="status-check-row">
              <StatusDot ok={m?.model_ok} />
              <span>TensorRT 모델</span>
              <span className="td-muted">{m?.model_ok ? "로드됨" : "실패"}</span>
            </div>
            <div className="status-check-row">
              <StatusDot ok={!!m} />
              <span>FastAPI 백엔드</span>
              <span className="td-muted">{m ? "응답 중" : "연결 안됨"}</span>
            </div>
          </div>
        </SectionCard>

        <SectionCard title="루프 타이밍">
          <div className="live-metric-row">
            <span className="live-metric-label">전체 루프</span>
            <span className="live-metric-value">{m?.loop_ms ?? "-"} ms</span>
          </div>
          <div className="live-metric-row">
            <span className="live-metric-label">캡처</span>
            <span className="live-metric-value">{m?.capture_ms ?? "-"} ms</span>
          </div>
          <div className="live-metric-row">
            <span className="live-metric-label">어노테이션</span>
            <span className="live-metric-value">{m?.annotate_ms ?? "-"} ms</span>
          </div>
          <div className="live-metric-row">
            <span className="live-metric-label">JPEG 인코딩</span>
            <span className="live-metric-value">{m?.jpeg_ms ?? "-"} ms</span>
          </div>
          <div className="live-metric-row">
            <span className="live-metric-label">클립 큐</span>
            <span className="live-metric-value">{m?.clip_queue_size ?? "-"}</span>
          </div>
        </SectionCard>

        <SectionCard title="이벤트 카운터">
          <div className="live-metric-row">
            <span className="live-metric-label">총 이벤트</span>
            <span className="live-metric-value blue">{m?.event_count ?? 0}</span>
          </div>
          <div className="live-metric-row">
            <span className="live-metric-label">입장 횟수</span>
            <span className="live-metric-value">{m?.enter_count ?? 0}</span>
          </div>
          <div className="live-metric-row">
            <span className="live-metric-label">퇴장 횟수</span>
            <span className="live-metric-value">{m?.exit_count ?? 0}</span>
          </div>
          <div className="live-metric-row">
            <span className="live-metric-label">현재 이벤트 레벨</span>
            <span
              className="live-metric-value"
              style={{ color: m?.event_level === "EVENT" ? "#ef4444" : m?.event_level === "ALERT" ? "#f97316" : "#16a34a" }}
            >
              {m?.event_level || "NONE"}
            </span>
          </div>
        </SectionCard>
      </div>
    </div>
  );
}

export default SystemStatusPage;
