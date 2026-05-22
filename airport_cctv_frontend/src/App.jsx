import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import MainLayout from "./layout/MainLayout.jsx";

import DashboardPage from "./pages/DashboardPage.jsx";
import LiveMonitoringPage from "./pages/LiveMonitoringPage.jsx";
import EventsPage from "./pages/EventsPage.jsx";
import ClipsPage from "./pages/ClipsPage.jsx";
import ZonesPage from "./pages/ZonesPage.jsx";
import ModelPowerPage from "./pages/ModelPowerPage.jsx";
import ReportsPage from "./pages/ReportsPage.jsx";
import SystemStatusPage from "./pages/SystemStatusPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<MainLayout />}>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/live-monitoring" element={<LiveMonitoringPage />} />
          <Route path="/events" element={<EventsPage />} />
          <Route path="/clips" element={<ClipsPage />} />
          <Route path="/zones" element={<ZonesPage />} />
          <Route path="/model-power" element={<ModelPowerPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/system-status" element={<SystemStatusPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;