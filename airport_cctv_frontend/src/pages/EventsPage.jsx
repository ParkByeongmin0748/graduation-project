import { useState } from "react";
import { AlertTriangle, Users, Route, Activity, Bell, X, Play } from "lucide-react";
import SectionCard from "../components/SectionCard.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import { usePolling } from "../hooks/usePolling.js";
import { buildApiUrl } from "../api/client.js";

const EVENT_TYPES = ["ALL", "RestrictedZone", "CrowdDensity", "Loitering", "FallDetected", "Enter", "Exit"];

const TYPE_META = {
  RestrictedZone: { label: "금지구역 침입", icon: <AlertTriangle size={16} />, color: "red",    severity: "High" },
  CrowdDensity:   { label: "군중 밀집",     icon: <Users size={16} />,         color: "orange", severity: "Medium" },
  Loitering:      { label: "배회 감지",     icon: <Route size={16} />,         color: "orange", severity: "Medium" },
  FallDetected:   { label: "낙상 감지",     icon: <Activity size={16} />,      color: "red",    severity: "High" },
  Enter:          { label: "입장",           icon: <Bell size={16} />,          color: "blue",   severity: "Low" },
  Exit:           { label: "퇴장",           icon: <Bell size={16} />,          color: "blue",   severity: "Low" },
};

function getTypeMeta(type) {
  return TYPE_META[type] || { label: type, icon: <Bell size={16} />, color: "blue", severity: "Low" };
}

// ── Inline video player modal ──────────────────────────────────
function VideoModal({ url, title, onClose }) {
  return (
    <div
      style={{
        position: "fixed", inset: 0,
        background: "rgba(0,0,0,0.72)",
        zIndex: 2000,
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: 24,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "#0f172a", borderRadius: 16, overflow: "hidden",
          width: "min(720px, 96vw)", boxShadow: "0 24px 64px rgba(0,0,0,0.6)",
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "12px 16px", borderBottom: "1px solid #1e293b" }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: "#e2e8f0" }}>{title}</span>
          <button
            onClick={onClose}
            style={{ background: "none", border: "none", cursor: "pointer", color: "#64748b",
              display: "flex", padding: 4, borderRadius: 6 }}
          >
            <X size={18} />
          </button>
        </div>
        {/* Video */}
        <video
          src={url}
          controls
          autoPlay
          style={{ width: "100%", display: "block", background: "#000", maxHeight: "60vh" }}
        />
      </div>
    </div>
  );
}

function EventsPage() {
  const { data, loading } = usePolling("/events", 2000);
  const [filter, setFilter]       = useState("ALL");
  const [playing, setPlaying]     = useState(null); // { url, title }

  const rawEvents = data?.events || [];
  const filtered = filter === "ALL" ? rawEvents : rawEvents.filter(e => e.type === filter);

  const counts = {};
  EVENT_TYPES.slice(1).forEach(t => { counts[t] = rawEvents.filter(e => e.type === t).length; });

  function openClip(ev) {
    const url = buildApiUrl(ev.clip_url);
    const meta = getTypeMeta(ev.type);
    setPlaying({ url, title: `#${ev.id} · ${meta.label} · ${ev.time}` });
  }

  return (
    <div>
      {playing && (
        <VideoModal url={playing.url} title={playing.title} onClose={() => setPlaying(null)} />
      )}

      <div className="filter-tab-row">
        {EVENT_TYPES.map(t => (
          <button
            key={t}
            className={`filter-tab ${filter === t ? "active" : ""}`}
            onClick={() => setFilter(t)}
          >
            {t === "ALL" ? "전체" : getTypeMeta(t).label}
            <span className="filter-count">
              {t === "ALL" ? rawEvents.length : (counts[t] || 0)}
            </span>
          </button>
        ))}
      </div>

      <SectionCard title={`이벤트 목록 (${filtered.length}건)`}>
        {loading && <div className="info-strip blue">데이터 로딩 중...</div>}
        {!loading && filtered.length === 0 && (
          <div className="info-strip blue">감지된 이벤트가 없습니다.</div>
        )}
        {filtered.length > 0 && (
          <div className="events-table-wrap">
            <table className="events-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>이벤트 타입</th>
                  <th>Track ID</th>
                  <th>시각</th>
                  <th>심각도</th>
                  <th>클립</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(ev => {
                  const meta = getTypeMeta(ev.type);
                  return (
                    <tr key={ev.id}>
                      <td className="td-id">{ev.id}</td>
                      <td>
                        <div className="event-type-cell">
                          <span className={`event-type-icon ${meta.color}`}>{meta.icon}</span>
                          <span className="event-type-name">{meta.label}</span>
                        </div>
                      </td>
                      <td className="td-muted">
                        {ev.track_id != null && ev.track_id >= 0 ? `ID ${ev.track_id}` : "-"}
                      </td>
                      <td className="td-muted">{ev.time}</td>
                      <td>
                        <StatusBadge tone={meta.color}>{meta.severity}</StatusBadge>
                      </td>
                      <td>
                        {ev.clip_ready && ev.clip_url ? (
                          <button
                            className="clip-play-btn"
                            onClick={() => openClip(ev)}
                          >
                            <Play size={12} />
                            재생
                          </button>
                        ) : ev.clip_filename ? (
                          <span className="td-muted">저장 중...</span>
                        ) : (
                          <span className="td-muted">-</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
    </div>
  );
}

export default EventsPage;
