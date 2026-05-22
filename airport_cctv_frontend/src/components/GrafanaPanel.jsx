import { useState } from "react";

const GRAFANA_BASE = "http://localhost:3000";

export function GrafanaPanel({ title, panelId, dashboardUid, height = 220 }) {
  const [error, setError] = useState(false);

  const src =
    `${GRAFANA_BASE}/d-solo/${dashboardUid}` +
    `?orgId=1&panelId=${panelId}` +
    `&refresh=5s&theme=dark`;

  if (error) {
    return (
      <div
        style={{
          height,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#0f172a",
          borderRadius: 12,
          color: "#64748b",
          fontSize: 13,
          flexDirection: "column",
          gap: 8,
        }}
      >
        <span style={{ fontSize: 24 }}>📡</span>
        Grafana 연결 필요 (localhost:3000)
        <span style={{ fontSize: 11, color: "#475569" }}>
          docker-compose up -d 실행 후 새로고침
        </span>
      </div>
    );
  }

  return (
    <iframe
      src={src}
      width="100%"
      height={height}
      style={{ border: "none", borderRadius: 12, display: "block" }}
      onError={() => setError(true)}
      title={title}
    />
  );
}

export default GrafanaPanel;
