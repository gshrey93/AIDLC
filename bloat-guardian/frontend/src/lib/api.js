import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({ baseURL: API_BASE, timeout: 180000 });

export function apiError(err, fallback = "Something went wrong") {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) return detail.map((d) => d.msg || d).join("; ");
  return err?.message || fallback;
}

export const endpoints = {
  config: () => api.get("/config"),
  overview: () => api.get("/stats/overview"),
  me: () => api.get("/me"),
  listScans: (params) => api.get("/scans", { params }),
  listSeries: (params) => api.get("/series", { params }),
  getSeries: (id) => api.get(`/series/${id}`),
  setSeriesArchived: (id, archived) => api.patch(`/series/${id}/archive`, { archived }),
  deleteSeries: (id) => api.delete(`/series/${id}`),
  getScan: (id) => api.get(`/scans/${id}`),
  getResults: (id) => api.get(`/scans/${id}/results`),
  getFiles: (id, params) => api.get(`/scans/${id}/files`, { params }),
  deleteScan: (id) => api.delete(`/scans/${id}`),
  createScan: (formData) =>
    api.post("/scans", formData, { headers: { "Content-Type": "multipart/form-data" } }),
  createDraft: (id, sourcePath) => api.post(`/scans/${id}/drafts`, { source_path: sourcePath }),
  exportPreview: (id) => api.get(`/scans/${id}/export-preview`),
  handoff: (id) => api.get(`/scans/${id}/handoff`),
  settings: () => api.get("/settings"),
  saveSettings: (patch) => api.put("/settings", patch),
  resetAssumptions: () => api.post("/settings/assumptions/reset"),
  refreshRates: () => api.post("/settings/refresh-rates"),
};

export function printViewUrl(scanId, redacted) {
  return `${API_BASE}/scans/${scanId}/print${redacted ? "?redacted=true" : ""}`;
}

export async function downloadExport(scanId, exportType, filename) {
  const res = await api.get(`/scans/${scanId}/export/${exportType}`, { responseType: "blob" });
  triggerBlobDownload(res.data, filename);
}

export async function downloadArchiveBundle(filename) {
  const res = await api.get("/series/export/archive", { responseType: "blob" });
  triggerBlobDownload(res.data, filename);
}

function triggerBlobDownload(blob, filename) {
  const blobUrl = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => window.URL.revokeObjectURL(blobUrl), 4000);
}
