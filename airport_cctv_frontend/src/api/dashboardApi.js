import {
  API_BASE_URL,
  apiGet,
  apiPatch,
  buildApiUrl,
  getClipUrl,
  getVideoFeedUrl,
  getRawVideoFeedUrl,
} from "./client";

export function getDashboardSummary() {
  return apiGet("/api/dashboard/summary");
}

export function getRecentEvents() {
  return apiGet("/api/events/recent");
}

export function getPowerModeSnapshot() {
  return apiGet("/api/power-mode/snapshot");
}

export function getMetrics() {
  return apiGet("/metrics");
}

export function getRawEvents() {
  return apiGet("/events");
}

export function getSummary() {
  return apiGet("/summary");
}

export function getBackendVideoFeedUrl() {
  return getVideoFeedUrl();
}

export function getBackendRawVideoFeedUrl() {
  return getRawVideoFeedUrl();
}

export function getBackendClipUrl(clipUrl) {
  return getClipUrl(clipUrl);
}

export function getBackendUrl(path) {
  return buildApiUrl(path);
}

export function getConfig() {
  return apiGet("/api/config");
}

export function patchConfig(updates) {
  return apiPatch("/api/config", updates);
}

export function getEventStats() {
  return apiGet("/api/events/stats");
}

export function getZones() {
  return apiGet("/api/zones");
}

export function patchZones(updates) {
  return apiPatch("/api/zones", updates);
}

export { API_BASE_URL, getVideoFeedUrl, getRawVideoFeedUrl, apiPatch };