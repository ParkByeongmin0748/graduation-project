export const dashboardSummary = {
  currentMode: "WATCH",
  activeCameras: 8,
  totalCameras: 12,
  todaysEvents: 24,
  averagePower: "6.2W",
  systemHealth: "Normal",
};

export const recentEvents = [
  {
    id: 1,
    type: "RestrictedZone",
    camera: "Gate A1 / Cam 01",
    time: "10:24:31",
    severity: "High",
  },
  {
    id: 2,
    type: "CrowdDensity",
    camera: "Gate B3 / Cam 04",
    time: "10:20:15",
    severity: "Medium",
  },
  {
    id: 3,
    type: "Loitering",
    camera: "Gate A2 / Cam 02",
    time: "10:15:42",
    severity: "Medium",
  },
  {
    id: 4,
    type: "CrowdDensity",
    camera: "Gate B1 / Cam 03",
    time: "10:10:05",
    severity: "Medium",
  },
  {
    id: 5,
    type: "RestrictedZone",
    camera: "Gate C2 / Cam 06",
    time: "10:05:18",
    severity: "High",
  },
];

export const powerTrend = [
  { time: "00:00", power: 4.8 },
  { time: "04:00", power: 5.2 },
  { time: "08:00", power: 6.1 },
  { time: "12:00", power: 8.4 },
  { time: "16:00", power: 7.0 },
  { time: "20:00", power: 6.5 },
  { time: "24:00", power: 6.2 },
];

export const quickLinks = [
  {
    title: "실시간 모니터링",
    subtitle: "Live Monitoring",
    path: "/live-monitoring",
    color: "blue",
  },
  {
    title: "이벤트 센터",
    subtitle: "Event Center",
    path: "/events",
    color: "orange",
  },
  {
    title: "클립 기록",
    subtitle: "Clip Archive",
    path: "/clips",
    color: "purple",
  },
  {
    title: "구역 설정",
    subtitle: "Zone Settings",
    path: "/zones",
    color: "green",
  },
  {
    title: "모델/전력 제어",
    subtitle: "Model & Power Tuning",
    path: "/model-power",
    color: "cyan",
  },
  {
    title: "리포트 분석",
    subtitle: "Reports",
    path: "/reports",
    color: "indigo",
  },
];