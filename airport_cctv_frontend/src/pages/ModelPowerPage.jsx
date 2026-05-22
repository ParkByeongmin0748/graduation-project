import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import { Zap, Cpu, SlidersHorizontal } from "lucide-react";
import SectionCard from "../components/SectionCard.jsx";
import SummaryCard from "../components/SummaryCard.jsx";
import { usePolling } from "../hooks/usePolling.js";

const MODE_CONFIG_TABLE = [
  { mode: "IDLE",  imgsz: 416, every_n: 6, nvp: 1, clocks: "OFF", model: "yolo11n FP16", color: "idle"  },
  { mode: "WATCH", imgsz: 416, every_n: 3, nvp: 2, clocks: "OFF", model: "yolo11n FP16", color: "watch" },
  { mode: "ALERT", imgsz: 416, every_n: 2, nvp: 2, clocks: "OFF", model: "yolo11n FP16", color: "alert" },
  { mode: "EVENT", imgsz: 640, every_n: 1, nvp: 0, clocks: "ON",  model: "yolo11s FP16", color: "event" },
];

function ModelPowerPage() {
  const { data: metrics } = usePolling("/metrics", 1000);
  const { data: powerHistory } = usePolling("/api/power-mode/snapshot", 2000);

  const chartData = Array.isArray(powerHistory) ? powerHistory.slice(-30) : [];
  const currentMode = metrics?.current_mode || "IDLE";

  return (
    <div>
      <div className="summary-grid" style={{ marginBottom: 16 }}>
        <SummaryCard
          icon={<Zap size={28} />}
          label="현재 전력"
          value={metrics?.board_power_w != null ? `${metrics.board_power_w}W` : "-"}
          helper={metrics?.power_source || "INA3221"}
          color="green"
        />
        <SummaryCard
          icon={<Cpu size={28} />}
          label="현재 모드"
          value={currentMode}
          helper={`nvpmodel Mode ${MODE_CONFIG_TABLE.find(m => m.mode === currentMode)?.nvp ?? "-"}`}
          color="blue"
        />
        <SummaryCard
          icon={<SlidersHorizontal size={28} />}
          label="입력 크기"
          value={metrics?.imgsz ?? "-"}
          helper={`추론 주기: N=${metrics?.infer_every_n ?? "-"}`}
          color="blue"
        />
        <SummaryCard
          icon={<Cpu size={28} />}
          label="FPS"
          value={metrics?.fps ?? "-"}
          helper={`추론: ${metrics?.inference_ms ?? "-"} ms`}
          color="blue"
        />
        <SummaryCard
          icon={<Zap size={28} />}
          label="AI 모델"
          value={metrics?.model_size || "-"}
          helper={`${metrics?.model_precision || ""} · ${metrics?.model_name?.split(" ")[0] || ""}`}
          color="blue"
        />
      </div>

      <div className="model-power-grid">
        <SectionCard title="전력 / 모드 트렌드 (최근 30초)">
          {chartData.length === 0 ? (
            <div className="info-strip blue">데이터 수집 중... 백엔드 실행 후 잠시 기다려주세요.</div>
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="time" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} unit="W" />
                <Tooltip
                  formatter={(val, name) => [
                    name === "power" ? `${val}W` : val,
                    name === "power" ? "전력" : "모드",
                  ]}
                />
                <Legend formatter={(val) => val === "power" ? "전력 (W)" : "모드"} />
                <Line type="monotone" dataKey="power" stroke="#2563eb" strokeWidth={3} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </SectionCard>

        <SectionCard title="현재 모델 정보">
          <div className="model-info-list">
            <div className="model-info-row">
              <span>모델명</span>
              <strong>{metrics?.model_name || "-"}</strong>
            </div>
            <div className="model-info-row">
              <span>크기</span>
              <strong>{metrics?.model_size || "-"}</strong>
            </div>
            <div className="model-info-row">
              <span>정밀도</span>
              <strong>{metrics?.model_precision || "-"}</strong>
            </div>
            <div className="model-info-row">
              <span>경로</span>
              <strong style={{ fontSize: 12, wordBreak: "break-all" }}>{metrics?.model_path || "-"}</strong>
            </div>
          </div>
        </SectionCard>
      </div>

      <SectionCard title="모드별 설정 비교" style={{ marginTop: 16 }}>
        <div className="events-table-wrap">
          <table className="events-table">
            <thead>
              <tr>
                <th>모드</th>
                <th>모델</th>
                <th>입력 크기</th>
                <th>추론 주기</th>
                <th>nvpmodel</th>
                <th>jetson_clocks</th>
                <th>상태</th>
              </tr>
            </thead>
            <tbody>
              {MODE_CONFIG_TABLE.map((row) => (
                <tr key={row.mode} className={currentMode === row.mode ? "active-row" : ""}>
                  <td>
                    <span className={`mode-chip ${row.color}`}>{row.mode}</span>
                  </td>
                  <td>{row.model}</td>
                  <td>{row.imgsz}px</td>
                  <td>매 {row.every_n}프레임</td>
                  <td>Mode {row.nvp}</td>
                  <td style={{ color: row.clocks === "ON" ? "#ef4444" : "#64748b" }}>{row.clocks}</td>
                  <td>{currentMode === row.mode ? "▶ 현재" : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
}

export default ModelPowerPage;
