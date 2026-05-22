import { useState } from "react";
import { Clapperboard, AlertTriangle, Users, Route, Activity, Bell } from "lucide-react";
import SectionCard from "../components/SectionCard.jsx";
import { usePolling } from "../hooks/usePolling.js";
import { buildApiUrl } from "../api/client.js";

const TYPE_META = {
  RestrictedZone: { label: "금지구역 침입", icon: <AlertTriangle size={15} />, color: "red" },
  CrowdDensity:   { label: "군중 밀집",     icon: <Users size={15} />,         color: "orange" },
  Loitering:      { label: "배회 감지",     icon: <Route size={15} />,         color: "orange" },
  FallDetected:   { label: "낙상 감지",     icon: <Activity size={15} />,      color: "red" },
  Enter:          { label: "입장",           icon: <Bell size={15} />,          color: "blue" },
  Exit:           { label: "퇴장",           icon: <Bell size={15} />,          color: "blue" },
};

function getTypeMeta(type) {
  return TYPE_META[type] || { label: type, icon: <Bell size={15} />, color: "blue" };
}

function ClipsPage() {
  const { data, loading } = usePolling("/events", 3000);
  const [selected, setSelected] = useState(null);

  const allEvents = data?.events || [];
  const withClips = allEvents.filter((e) => e.clip_ready && e.clip_url);
  const pending = allEvents.filter((e) => e.clip_filename && !e.clip_ready);

  function selectClip(ev) {
    setSelected(ev);
  }

  const playerUrl = selected ? buildApiUrl(selected.clip_url) : null;

  return (
    <div className="clips-layout">
      <div className="clips-left">
        <SectionCard title="클립 목록" action={<span style={{ fontSize: 13, color: "#64748b" }}>{withClips.length}개 준비됨</span>}>
          {loading && <div className="info-strip blue">로딩 중...</div>}

          {!loading && withClips.length === 0 && (
            <div className="info-strip blue">
              <Clapperboard size={18} />
              저장된 클립이 없습니다. 이벤트가 발생하면 자동 저장됩니다.
            </div>
          )}

          <div className="clip-list">
            {withClips.map((ev) => {
              const meta = getTypeMeta(ev.type);
              const isActive = selected?.id === ev.id;
              return (
                <div
                  key={ev.id}
                  className={`clip-item ${isActive ? "active" : ""}`}
                  onClick={() => selectClip(ev)}
                >
                  <div className={`clip-item-icon ${meta.color}`}>{meta.icon}</div>
                  <div className="clip-item-body">
                    <div className="clip-item-type">{meta.label}</div>
                    <div className="clip-item-meta">
                      {ev.track_id != null && ev.track_id >= 0 ? `ID ${ev.track_id} · ` : ""}
                      {ev.time}
                    </div>
                  </div>
                  <div className="clip-item-badge">Event #{ev.id}</div>
                </div>
              );
            })}

            {pending.length > 0 && (
              <div className="info-strip orange" style={{ marginTop: 8 }}>
                {pending.length}개 클립 저장 중...
              </div>
            )}
          </div>
        </SectionCard>
      </div>

      <div className="clips-right">
        <SectionCard
          title={selected ? `클립 재생 — Event #${selected.id}` : "클립 재생"}
          action={selected && (
            <span style={{ fontSize: 13, color: "#64748b" }}>
              {getTypeMeta(selected.type).label} · {selected.time}
            </span>
          )}
        >
          {!selected ? (
            <div className="placeholder-page" style={{ minHeight: 360 }}>
              <Clapperboard size={48} style={{ color: "#94a3b8", marginBottom: 12 }} />
              왼쪽에서 클립을 선택하세요
            </div>
          ) : (
            <video
              key={playerUrl}
              controls
              autoPlay
              className="clip-video-player"
              src={playerUrl}
            />
          )}
        </SectionCard>
      </div>
    </div>
  );
}

export default ClipsPage;
