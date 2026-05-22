import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Bell,
  Camera,
  Clapperboard,
  HeartPulse,
  Map,
  Monitor,
  Route,
  ShieldCheck,
  SlidersHorizontal,
  Users,
  Zap,
  ChartColumn,
  Info,
} from "lucide-react";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";

import SummaryCard from "../components/SummaryCard.jsx";
import QuickLinkCard from "../components/QuickLinkCard.jsx";
import SectionCard from "../components/SectionCard.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

import {
  dashboardSummary as mockDashboardSummary,
  powerTrend as mockPowerTrend,
  quickLinks,
  recentEvents as mockRecentEvents,
} from "../data/mockData.js";

import {
  getDashboardSummary,
  getPowerModeSnapshot,
  getRecentEvents,
  getVideoFeedUrl,
} from "../api/dashboardApi.js";

const quickIcons = {
  "실시간 모니터링": <Monitor size={26} />,
  "이벤트 센터": <Bell size={26} />,
  "클립 기록": <Clapperboard size={26} />,
  "구역 설정": <Map size={26} />,
  "모델/전력 제어": <SlidersHorizontal size={26} />,
  "리포트 분석": <ChartColumn size={26} />,
};

function getEventIcon(type) {
  if (type === "RestrictedZone") return <AlertTriangle size={18} />;
  if (type === "CrowdDensity") return <Users size={18} />;
  if (type === "Loitering") return <Route size={18} />;
  if (type === "Enter" || type === "Exit") return <Route size={18} />;
  return <Bell size={18} />;
}

function getSeverityTone(severity) {
  if (severity === "High" || severity === "EVENT") return "red";
  if (severity === "Medium" || severity === "ALERT") return "orange";
  return "blue";
}

function normalizeSummary(data) {
  if (!data) return mockDashboardSummary;

  if (Array.isArray(data)) {
    const findValue = (label, fallback) =>
      data.find((item) => item.label === label)?.value ?? fallback;

    return {
      currentMode: findValue("Current Mode", mockDashboardSummary.currentMode),
      activeCameras: findValue("Active Cameras", mockDashboardSummary.activeCameras),
      totalCameras: mockDashboardSummary.totalCameras ?? 1,
      todaysEvents: findValue("Today’s Events", mockDashboardSummary.todaysEvents),
      averagePower: findValue("Average Power", mockDashboardSummary.averagePower),
      systemHealth: findValue("System Health", mockDashboardSummary.systemHealth),
    };
  }

  return {
    ...mockDashboardSummary,
    ...data,
    totalCameras: data.totalCameras ?? mockDashboardSummary.totalCameras ?? 1,
  };
}

function normalizeEvents(data) {
  const events = Array.isArray(data) ? data : data?.events;
  if (!Array.isArray(events)) return mockRecentEvents;

  return events.map((event, index) => ({
    id: event.id ?? event.event_id ?? `${event.type ?? "event"}-${index}`,
    type: event.type ?? event.eventType ?? event.event_reason ?? "Event",
    camera: event.camera ?? event.camera_name ?? "Gate A1 / Cam 01",
    time: event.time ?? event.timestamp ?? "-",
    severity: event.severity ?? event.level ?? event.event_level ?? "Low",
    clip_url: event.clip_url,
    clip_ready: event.clip_ready,
  }));
}

function normalizePowerTrend(data) {
  const rows = Array.isArray(data) ? data : data?.powerTrend;
  if (!Array.isArray(rows) || rows.length === 0) return mockPowerTrend;

  return rows.map((row, index) => ({
    time: row.time ?? row.timestamp ?? `${index}`,
    power: Number(row.power ?? row.board_power_w ?? 0),
    mode: row.mode ?? row.current_mode ?? "IDLE",
  }));
}

function CameraFeed({ url }) {
  const [state, setState] = useState("loading"); // loading | ok | error
  const retryRef = useRef(null);

  function tryLoad() {
    setState("loading");
    // Clear previous retry
    if (retryRef.current) clearTimeout(retryRef.current);
  }

  function handleLoad() { setState("ok"); }
  function handleError() {
    setState("error");
    retryRef.current = setTimeout(tryLoad, 5000);
  }

  useEffect(() => () => { if (retryRef.current) clearTimeout(retryRef.current); }, []);

  return (
    <div style={{ position: "relative", width: "100%", height: "100%", background: "#0f172a", borderRadius: 12, overflow: "hidden", minHeight: 240 }}>
      <img
        key={state === "loading" ? url + Date.now() : url}
        src={url}
        alt="CCTV Live"
        onLoad={handleLoad}
        onError={handleError}
        style={{ width: "100%", height: "100%", objectFit: "contain", display: state === "error" ? "none" : "block" }}
      />
      {state !== "ok" && (
        <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", color: "#475569", gap: 10 }}>
          {state === "loading" ? (
            <>
              <div style={{ width: 32, height: 32, border: "3px solid #334155", borderTopColor: "#2563eb", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
              <span style={{ fontSize: 13 }}>카메라 스트림 연결 중...</span>
            </>
          ) : (
            <>
              <span style={{ fontSize: 28 }}>📷</span>
              <span style={{ fontSize: 13 }}>카메라 신호 없음</span>
              <span style={{ fontSize: 11, color: "#64748b" }}>5초 후 재시도...</span>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function DashboardPage() {
  const [dashboardSummary, setDashboardSummary] = useState(mockDashboardSummary);
  const [recentEvents, setRecentEvents] = useState(mockRecentEvents);
  const [powerTrend, setPowerTrend] = useState(mockPowerTrend);
  const [apiConnected, setApiConnected] = useState(false);
  const [lastSync, setLastSync] = useState(null);

  const videoFeedUrl = useMemo(() => getVideoFeedUrl(), []);

  useEffect(() => {
    let mounted = true;

    async function loadDashboardData() {
      try {
        const [summaryData, eventsData, powerData] = await Promise.all([
          getDashboardSummary(),
          getRecentEvents(),
          getPowerModeSnapshot(),
        ]);

        if (!mounted) return;

        setDashboardSummary(normalizeSummary(summaryData));
        setRecentEvents(normalizeEvents(eventsData));
        setPowerTrend(normalizePowerTrend(powerData));
        setApiConnected(true);
        setLastSync(new Date());
      } catch (error) {
        console.error("Dashboard API 연결 실패:", error);
        if (!mounted) return;
        setApiConnected(false);
      }
    }

    loadDashboardData();
    const timer = setInterval(loadDashboardData, 1000);

    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, []);

  const averagePowerText = useMemo(() => {
    if (!powerTrend.length) return dashboardSummary.averagePower;
    const values = powerTrend.map((item) => Number(item.power)).filter(Number.isFinite);
    if (!values.length) return dashboardSummary.averagePower;
    const avg = values.reduce((sum, value) => sum + value, 0) / values.length;
    return `${avg.toFixed(1)}W 평균`;
  }, [dashboardSummary.averagePower, powerTrend]);

  const timelineItems = powerTrend.slice(-6);

  return (
    <div className="dashboard-page">
      <div className="summary-grid">
        <SummaryCard
          icon={<ShieldCheck size={30} />}
          label="Current Mode"
          value={dashboardSummary.currentMode}
          helper="현재 동작 모드"
          color="blue"
        />
        <SummaryCard
          icon={<Camera size={30} />}
          label="Active Cameras"
          value={dashboardSummary.activeCameras}
          helper={`/ ${dashboardSummary.totalCameras}대 연결 중`}
          color="blue"
        />
        <SummaryCard
          icon={<Bell size={30} />}
          label="Today’s Events"
          value={dashboardSummary.todaysEvents}
          helper="누적 감지 이벤트"
          color="orange"
        />
        <SummaryCard
          icon={<Zap size={30} />}
          label="Average Power"
          value={dashboardSummary.averagePower}
          helper="현재 소비 전력"
          color="green"
        />
        <SummaryCard
          icon={<HeartPulse size={30} />}
          label="System Health"
          value={dashboardSummary.systemHealth}
          helper={apiConnected ? "백엔드 연결 정상" : "mockData 표시 중"}
          color={apiConnected ? "blue" : "orange"}
        />
      </div>

      <div className="main-grid">
        <SectionCard
          title="Live Preview Summary"
          action={
            <div className="live-meta">
              <span>Gate A1</span>
              <span>Cam 01</span>
              <span className="live-dot">LIVE</span>
            </div>
          }
          className="preview-card"
        >
          <div className="cctv-preview">
            <CameraFeed url={videoFeedUrl} />
          </div>

          <div className="preview-legend">
            <span>
              <i className="legend-dot red" />
              Restricted Zone
            </span>
            <span>
              <i className="legend-dot yellow" />
              Crowd Zone
            </span>
            <span>
              <i className="legend-line" />
              Flow Line
            </span>
          </div>
        </SectionCard>

        <SectionCard title="빠른 페이지 이동" className="quick-panel">
          <div className="quick-grid">
            {quickLinks.map((link) => (
              <QuickLinkCard
                key={link.path}
                icon={quickIcons[link.title]}
                title={link.title}
                subtitle={link.subtitle}
                path={link.path}
                color={link.color}
              />
            ))}
          </div>

          <div className={apiConnected ? "info-strip blue" : "info-strip orange"}>
            <Info size={18} />
            {apiConnected
              ? `백엔드 API 연결됨${lastSync ? ` · ${lastSync.toLocaleTimeString()} 동기화` : ""}`
              : "백엔드 API 미연결: mockData 기준으로 표시 중"}
          </div>
        </SectionCard>
      </div>

      <div className="bottom-grid">
        <SectionCard title="Recent Events" action={<a className="view-all">전체 보기 →</a>}>
          <div className="event-list">
            {recentEvents.length === 0 ? (
              <div className="info-strip blue">
                <Info size={18} />
                아직 감지된 이벤트가 없습니다.
              </div>
            ) : (
              recentEvents.map((event) => (
                <div
                  className="event-row"
                  key={event.id}
                  onClick={() => {
                    if (event.clip_ready && event.clip_url) {
                      window.open(event.clip_url, "_blank");
                    }
                  }}
                  style={{ cursor: event.clip_ready && event.clip_url ? "pointer" : "default" }}
                >
                  <div className={`event-icon ${getSeverityTone(event.severity)}`}>
                    {getEventIcon(event.type)}
                  </div>
                  <div className="event-name">{event.type}</div>
                  <div className="event-camera">{event.camera}</div>
                  <div className="event-time">{event.time}</div>
                  <StatusBadge tone={getSeverityTone(event.severity)}>
                    {event.severity}
                  </StatusBadge>
                </div>
              ))
            )}
          </div>
        </SectionCard>

        <SectionCard title="Power / Mode Trend Snapshot">
          <div className="trend-layout">
            <div className="chart-box">
              <div className="chart-title-row">
                <span>Average Power (W)</span>
                <strong>{averagePowerText}</strong>
              </div>

              <ResponsiveContainer width="100%" height={170}>
                <LineChart data={powerTrend}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="time" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Line
                    type="monotone"
                    dataKey="power"
                    stroke="#2563eb"
                    strokeWidth={3}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>

            <div className="mode-timeline">
              <div className="timeline-title">Mode Timeline</div>
              <div className="timeline-row">
                {timelineItems.map((item, index) => (
                  <span
                    key={`${item.time}-${index}`}
                    className={`mode-chip ${(item.mode || "idle").toLowerCase()}`}
                  >
                    {item.mode || "IDLE"}
                  </span>
                ))}
              </div>

              <div className="timeline-times">
                {timelineItems.map((item, index) => (
                  <span key={`${item.time}-time-${index}`}>{item.time}</span>
                ))}
              </div>

              <div className="mode-legend">
                <span>
                  <i className="dot idle" />
                  IDLE
                </span>
                <span>
                  <i className="dot watch" />
                  WATCH
                </span>
                <span>
                  <i className="dot alert" />
                  ALERT
                </span>
                <span>
                  <i className="dot event" />
                  EVENT
                </span>
              </div>
            </div>
          </div>
        </SectionCard>
      </div>

      <div className="footer-note">
        {apiConnected
          ? "✅ React 프론트엔드가 Jetson FastAPI 백엔드와 연결되어 실시간 데이터를 표시 중입니다."
          : "💡 백엔드 연결 실패 시 기존 mockData 화면으로 유지됩니다. 백엔드 주소와 /api 엔드포인트를 확인하세요."}
      </div>
    </div>
  );
}

export default DashboardPage;
