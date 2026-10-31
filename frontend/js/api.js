import { state } from "./store.js";

const BASE = "/api/v1";
export class ApiError extends Error {
  constructor(message, status, code) { super(message); this.status = status; this.code = code; }
}

let refreshing = null;
export async function refreshSession() {
  refreshing ??= (async () => {
    try {
      const r = await fetch(`${BASE}/auth/refresh`, { method: "POST" });
      if (!r.ok) return false;
      const d = await r.json();
      state.token = d.access_token; state.user = d.user;
      return true;
    } catch { return false; } finally { setTimeout(() => (refreshing = null), 0); }
  })();
  return refreshing;
}

function headers(extra = {}) {
  return { ...(state.token ? { Authorization: `Bearer ${state.token}` } : {}), ...extra };
}

async function toError(r) {
  let d = {}; try { d = await r.json(); } catch { /* not json */ }
  const msg = d.message || (Array.isArray(d.detail) ? "Please check the highlighted fields and try again." : d.detail) || "Something went wrong. Try again.";
  return new ApiError(msg, r.status, d.error);
}

export async function api(path, { method = "GET", body, form, auth = true } = {}) {
  const opts = () => ({
    method,
    headers: headers(body ? { "Content-Type": "application/json" } : {}),
    body: form ?? (body ? JSON.stringify(body) : undefined),
  });
  let r;
  try { r = await fetch(BASE + path, opts()); }
  catch { throw new ApiError("Can't reach the server. If it was idle it may be waking up; try again in a few seconds.", 0, "network"); }
  if (r.status === 401 && auth && await refreshSession()) r = await fetch(BASE + path, opts());
  if (!r.ok) throw await toError(r);
  return r.status === 204 ? null : r.json();
}

export async function fetchBlobUrl(url) {
  const r = await fetch(url, { headers: headers() });
  if (!r.ok) throw await toError(r);
  return URL.createObjectURL(await r.blob());
}

export { BASE };
