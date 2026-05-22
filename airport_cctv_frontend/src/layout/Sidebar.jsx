import { NavLink } from "react-router-dom";
import {
  Activity,
  Bell,
  Camera,
  ChartColumn,
  Clapperboard,
  Gauge,
  Grid2X2,
  Map,
  Plane,
  Settings,
  SlidersHorizontal,
} from "lucide-react";

const menuItems = [
  {
    label: "메인 대시보드",
    sub: "Dashboard",
    path: "/dashboard",
    icon: Grid2X2,
  },
  {
    label: "실시간 모니터링",
    sub: "Live Monitoring",
    path: "/live-monitoring",
    icon: Camera,
  },
  {
    label: "이벤트 센터",
    sub: "Event Center",
    path: "/events",
    icon: Bell,
  },
  {
    label: "클립 기록",
    sub: "Clip Archive",
    path: "/clips",
    icon: Clapperboard,
  },
  {
    label: "구역 설정",
    sub: "Zone Settings",
    path: "/zones",
    icon: Map,
  },
  {
    label: "모델/전력 제어",
    sub: "Model & Power Tuning",
    path: "/model-power",
    icon: SlidersHorizontal,
  },
  {
    label: "리포트 분석",
    sub: "Reports",
    path: "/reports",
    icon: ChartColumn,
  },
  {
    label: "시스템 상태",
    sub: "System Status",
    path: "/system-status",
    icon: Activity,
  },
  {
    label: "설정",
    sub: "Settings",
    path: "/settings",
    icon: Settings,
  },
];

function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-icon">
          <Plane size={26} />
        </div>
        <div>
          <div className="brand-title">Airport Edge AI CCTV</div>
          <div className="brand-subtitle">Power Optimized</div>
        </div>
      </div>

      <nav className="sidebar-nav">
        {menuItems.map((item) => {
          const Icon = item.icon;

          return (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                isActive ? "nav-item active" : "nav-item"
              }
            >
              <Icon size={22} />
              <div>
                <div className="nav-label">{item.label}</div>
                <div className="nav-sub">{item.sub}</div>
              </div>
            </NavLink>
          );
        })}
      </nav>

      <div className="connection-card">
        <div className="connection-dot" />
        <div>
          <div className="connection-title">시스템 연결 상태</div>
          <div className="connection-sub">모든 시스템 정상 운영 중</div>
        </div>
        <Gauge size={20} />
      </div>
    </aside>
  );
}

export default Sidebar;