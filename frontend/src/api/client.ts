import axios from "axios";

// In production this app is served by the same FastAPI process, so a
// relative base URL works. In local dev, point VITE_API_BASE at the
// backend (see .env.example).
const baseURL = import.meta.env.VITE_API_BASE || "";

export const api = axios.create({ baseURL });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("token");
      localStorage.removeItem("role");
      localStorage.removeItem("username");
      if (!window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

/** Extract a human-readable message from a failed API call. Handles the
 * three shapes an error can actually take: a plain string `detail` (most
 * of this app's own HTTPException(...) calls), FastAPI's own 422
 * validation-error shape (`detail` is a list of {loc, msg, type} objects --
 * happens automatically when a request body doesn't match a Pydantic
 * schema, which every previous per-page inline version of this helper
 * silently swallowed into a generic "couldn't do X" message), or no
 * response at all (network drop / proxy or browser timeout -- the request
 * may still have gone through server-side even though this tab never
 * heard back, which is a materially different situation from a clean
 * error response and worth telling the user). */
export function errMsg(e: any, fallback: string): string {
  const detail = e?.response?.data?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((d: any) => {
        const field = Array.isArray(d?.loc) ? d.loc[d.loc.length - 1] : null;
        const msg = d?.msg || JSON.stringify(d);
        return field ? `${field}: ${msg}` : msg;
      })
      .join("; ");
  }
  if (detail) return JSON.stringify(detail);
  if (!e?.response) {
    return "No response came back from the server (connection dropped or timed out) -- it may" +
      " still have gone through. Refresh and check before retrying.";
  }
  return fallback;
}

/** Trigger a browser download for an Excel export endpoint that returns a
 * binary xlsx stream (can't just be a plain <a href> because auth needs a
 * bearer header, not a cookie). `params` (optional) are passed through as
 * the request's query string -- e.g. the currency/date-window a filtered
 * export endpoint needs. */
export async function downloadXlsx(url: string, filename: string, params?: Record<string, unknown>) {
  const res = await api.get(url, { responseType: "blob", params });
  const blobUrl = window.URL.createObjectURL(new Blob([res.data]));
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(blobUrl);
}
