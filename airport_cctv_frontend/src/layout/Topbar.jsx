import { useState, useEffect, useRef } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import {
  Bell, ChevronDown, Search, UserRound, X,
  Settings, LogOut, Info, AlertTriangle, Users, Route,
  Monitor, Clapperboard, Map, SlidersHorizontal, ChartColumn, Activity,
} from "lucide-react";
import { apiGet } from "../api/client.js";

// ── 페이지/구역/이벤트 검색 목록 ──────────────────────────
const SEARCH_ITEMS = [
  { type: "page",  label: "메인 대시보드",     sub: "Dashboard",          path: "/dashboard",        icon: <Monitor size={14}/> },
  { type: "page",  label: "실시간 모니터링",   sub: "Live Monitoring",     path: "/live-monitoring",  icon: <Monitor size={14}/> },
  { type: "page",  label: "이벤트 센터",       sub: "Event Center",        path: "/events",           icon: <Bell size={14}/> },
  { type: "page",  label: "클립 기록",         sub: "Clip Archive",        path: "/clips",            icon: <Clapperboard size={14}/> },
  { type: "page",  label: "구역 설정",         sub: "Zone Settings",       path: "/zones",            icon: <Map size={14}/> },
  { type: "page",  label: "모델/전력 제어",    sub: "Model & Power Tuning",path: "/model-power",      icon: <SlidersHorizontal size={14}/> },
  { type: "page",  label: "리포트 분석",       sub: "Reports",             path: "/reports",          icon: <ChartColumn size={14}/> },
  { type: "page",  label: "시스템 상태",       sub: "System Status",       path: "/system-status",    icon: <Activity size={14}/> },
  { type: "page",  label: "설정",             sub: "Settings",             path: "/settings",         icon: <Settings size={14}/> },
  { type: "zone",  label: "금지구역",          sub: "Restricted Zone (RZ-1)", path: "/zones",         icon: <AlertTriangle size={14}/> },
  { type: "zone",  label: "군중 감지 구역",    sub: "Crowd Zone (CZ-1)",      path: "/zones",         icon: <Users size={14}/> },
  { type: "zone",  label: "배회 감지 구역",    sub: "Loitering Zone (LZ-1)", path: "/zones",          icon: <Route size={14}/> },
  { type: "event", label: "RestrictedZone",   sub: "제한구역 침입 이벤트",   path: "/events",          icon: <AlertTriangle size={14}/> },
  { type: "event", label: "CrowdDensity",     sub: "군중 밀집 이벤트",       path: "/events",          icon: <Users size={14}/> },
  { type: "event", label: "Loitering",        sub: "배회 감지 이벤트",       path: "/events",          icon: <Route size={14}/> },
  { type: "event", label: "FallDetected",     sub: "낙상 감지 이벤트",       path: "/events",          icon: <AlertTriangle size={14}/> },
  { type: "event", label: "Enter / Exit",     sub: "입장·퇴장 이벤트",       path: "/events",          icon: <Route size={14}/> },
];

const PAGE_TITLES = {
  "/dashboard":     { title: "Main Dashboard",      sub: "Overview & quick access" },
  "/live-monitoring":{ title: "실시간 모니터링",     sub: "Live CCTV Stream" },
  "/events":        { title: "이벤트 센터",          sub: "Event Center" },
  "/clips":         { title: "클립 기록",            sub: "Clip Archive" },
  "/zones":         { title: "구역 설정",            sub: "Zone Settings" },
  "/model-power":   { title: "모델/전력 제어",       sub: "Model & Power Tuning" },
  "/reports":       { title: "리포트 분석",          sub: "Reports" },
  "/system-status": { title: "시스템 상태",          sub: "System Status" },
  "/settings":      { title: "설정",                sub: "Settings" },
};

function getSeverityColor(sev) {
  if (sev === "High" || sev === "EVENT") return "#ef4444";
  if (sev === "Medium" || sev === "ALERT") return "#f97316";
  return "#2563eb";
}

function getEventIcon(type) {
  if (type === "RestrictedZone" || type === "FallDetected") return <AlertTriangle size={13} />;
  if (type === "CrowdDensity") return <Users size={13} />;
  return <Route size={13} />;
}

export default function Topbar() {
  const navigate = useNavigate();
  const location = useLocation();

  // ── Search ───────────────────────────────────────────
  const [searchVal, setSearchVal] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const searchRef = useRef(null);

  // ── Notifications ────────────────────────────────────
  const [events, setEvents] = useState([]);
  const [lastSeenId, setLastSeenId] = useState(
    () => parseInt(localStorage.getItem("lastSeenEventId") || "0", 10)
  );
  const [notifOpen, setNotifOpen] = useState(false);
  const notifRef = useRef(null);

  // ── Admin ────────────────────────────────────────────
  const [adminOpen, setAdminOpen] = useState(false);
  const adminRef = useRef(null);

  // Poll events every 5s
  useEffect(() => {
    let mounted = true;
    async function fetchEvents() {
      try {
        const data = await apiGet("/events");
        if (!mounted) return;
        const evs = Array.isArray(data) ? data : (data?.events || []);
        setEvents(evs.slice(0, 20));
      } catch { /* silent */ }
    }
    fetchEvents();
    const t = setInterval(fetchEvents, 5000);
    return () => { mounted = false; clearInterval(t); };
  }, []);

  // Click-outside close
  useEffect(() => {
    function onDown(e) {
      if (searchRef.current && !searchRef.current.contains(e.target)) setSearchOpen(false);
      if (notifRef.current && !notifRef.current.contains(e.target)) setNotifOpen(false);
      if (adminRef.current && !adminRef.current.contains(e.target)) setAdminOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  const searchResults = searchVal.length < 1 ? [] :
    SEARCH_ITEMS.filter(item =>
      item.label.toLowerCase().includes(searchVal.toLowerCase()) ||
      item.sub.toLowerCase().includes(searchVal.toLowerCase())
    ).slice(0, 7);

  const unreadCount = events.filter(e => (e.id || 0) > lastSeenId).length;

  function markAllRead() {
    const maxId = events.reduce((m, e) => Math.max(m, e.id || 0), 0);
    setLastSeenId(maxId);
    localStorage.setItem("lastSeenEventId", String(maxId));
  }

  function handleNotifClick() {
    setNotifOpen(v => !v);
    if (!notifOpen) markAllRead();
    setAdminOpen(false);
    setSearchOpen(false);
  }

  function handleAdminClick() {
    setAdminOpen(v => !v);
    setNotifOpen(false);
    setSearchOpen(false);
  }

  const pageInfo = PAGE_TITLES[location.pathname] || PAGE_TITLES["/dashboard"];

  return (
    <header
      className="topbar"
      style={{
        position: "sticky",
        top: 0,
        zIndex: 10000,
        background: "#fff",
      }}
>
      <div>
        <h1>{pageInfo.title}</h1>
        <p>{pageInfo.sub}</p>
      </div>

      <div className="topbar-right">

        {/* ── Search ── */}
        <div className="search-wrapper" ref={searchRef}>
          <div className={`search-box${searchOpen ? " focused" : ""}`}>
            <Search size={16} color="#94a3b8" />
            <input
              placeholder="카메라, 이벤트, 구역 검색..."
              value={searchVal}
              onChange={e => { setSearchVal(e.target.value); setSearchOpen(true); setNotifOpen(false); setAdminOpen(false); }}
              onFocus={() => setSearchOpen(true)}
            />
            {searchVal && (
              <button
                onClick={() => { setSearchVal(""); setSearchOpen(false); }}
                style={{ border: "none", background: "none", cursor: "pointer", color: "#94a3b8", padding: 0, display: "flex" }}
              >
                <X size={14} />
              </button>
            )}
          </div>

          {searchOpen && searchResults.length > 0 && (
            <div className="search-dropdown">
              {searchResults.map((item, i) => (
                <div
                  key={i}
                  className="search-item"
                  onClick={() => { navigate(item.path); setSearchVal(""); setSearchOpen(false); }}
                >
                  <span className={`search-type-chip ${item.type}`}>{item.type}</span>
                  <span className="search-item-icon">{item.icon}</span>
                  <div className="search-item-text">
                    <div className="search-item-label">{item.label}</div>
                    <div className="search-item-sub">{item.sub}</div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {searchOpen && searchVal.length > 0 && searchResults.length === 0 && (
            <div className="search-dropdown">
              <div style={{ padding: "14px 16px", color: "#94a3b8", fontSize: 13 }}>
                '{searchVal}' 검색 결과 없음
              </div>
            </div>
          )}
        </div>

        {/* ── Notifications ── */}
        <div className="notif-wrapper" ref={notifRef}>
          <button className="topbar-icon-btn" onClick={handleNotifClick}>
            <Bell size={22} />
            {unreadCount > 0 && (
              <span className="notif-badge">{unreadCount > 9 ? "9+" : unreadCount}</span>
            )}
          </button>

          {notifOpen && (
            <div className="notif-panel">
              <div className="notif-panel-header">
                <span className="notif-panel-title">알림</span>
                {unreadCount > 0 && (
                  <span className="notif-unread-chip">{unreadCount}개 새 알림</span>
                )}
                <button className="notif-read-all-btn" onClick={markAllRead}>
                  모두 읽음
                </button>
              </div>

              {events.length === 0 ? (
                <div className="notif-empty">
                  <Bell size={30} color="#cbd5e1" />
                  <p>새로운 알림이 없습니다</p>
                </div>
              ) : (
                <div className="notif-list">
                  {events.slice(0, 12).map(ev => {
                    const isUnread = (ev.id || 0) > lastSeenId;
                    const sevColor = getSeverityColor(ev.severity || ev.level);
                    return (
                      <div
                        key={ev.id}
                        className={`notif-item${isUnread ? " unread" : ""}`}
                        onClick={() => { navigate("/events"); setNotifOpen(false); }}
                      >
                        <div className="notif-icon-wrap" style={{ color: sevColor }}>
                          {getEventIcon(ev.type)}
                        </div>
                        <div className="notif-content">
                          <div className="notif-title">{ev.type}</div>
                          <div className="notif-time">{ev.time || "-"}</div>
                        </div>
                        {isUnread && <div className="notif-unread-dot" />}
                      </div>
                    );
                  })}
                </div>
              )}

              <div className="notif-panel-footer" onClick={() => { navigate("/events"); setNotifOpen(false); }}>
                전체 이벤트 보기 →
              </div>
            </div>
          )}
        </div>

        {/* ── Admin ── */}
        <div className="admin-wrapper" ref={adminRef}>
          <button
            className="profile"
            onClick={handleAdminClick}
            style={{ background: "none", border: "none", cursor: "pointer", display: "flex", alignItems: "center", gap: 10, paddingLeft: 18, borderLeft: "1px solid #e5eaf3" }}
          >
            <div className="profile-avatar"><UserRound size={20} /></div>
            <div style={{ textAlign: "left" }}>
              <div className="profile-name">admin</div>
              <div className="profile-role">관리자</div>
            </div>
            <ChevronDown size={16} style={{ color: "#64748b", transform: adminOpen ? "rotate(180deg)" : "none", transition: "0.2s" }} />
          </button>

          {adminOpen && (
            <div className="admin-dropdown">
              <div className="admin-user-info">
                <div className="admin-avatar-lg"><UserRound size={26} /></div>
                <div>
                  <div className="admin-name">관리자</div>
                  <div className="admin-email">admin@airport.local</div>
                </div>
              </div>
              <div className="admin-divider" />
              <button className="admin-menu-item" onClick={() => { navigate("/settings"); setAdminOpen(false); }}>
                <Settings size={15} /> 설정
              </button>
              <button className="admin-menu-item" onClick={() => { navigate("/system-status"); setAdminOpen(false); }}>
                <Info size={15} /> 시스템 상태
              </button>
              <button className="admin-menu-item" onClick={() => { navigate("/reports"); setAdminOpen(false); }}>
                <ChartColumn size={15} /> 리포트 분석
              </button>
              <div className="admin-divider" />
              <button
                className="admin-menu-item logout"
                onClick={() => {
                  if (window.confirm("로그아웃 하시겠습니까?\n(데모 환경 — 인증 시스템 미연동)")) {
                    setAdminOpen(false);
                  }
                }}
              >
                <LogOut size={15} /> 로그아웃
              </button>
            </div>
          )}
        </div>

      </div>
    </header>
  );
}
