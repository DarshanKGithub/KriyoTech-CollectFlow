export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api/v1").replace(/\/+$/, "");
export function workspaceKey() { return typeof window === "undefined" ? "" : localStorage.getItem("kriyopay_workspace") || ""; }
export function accessToken() { return typeof window === "undefined" ? "" : localStorage.getItem("kriyopay_access") || ""; }
export function refreshToken() { return typeof window === "undefined" ? "" : localStorage.getItem("kriyopay_refresh") || ""; }

let refreshInFlight: Promise<string | null> | null = null;

function expireSession() {
  if (typeof window === "undefined") return;
  ["kriyopay_access", "kriyopay_refresh", "kriyopay_workspace"].forEach(key => localStorage.removeItem(key));
  if (window.location.pathname === "/login") return;
  const next = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  window.location.assign(`/login?reason=session_expired&next=${encodeURIComponent(next)}`);
}

function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;
  const refresh = refreshToken();
  if (!refresh) {
    expireSession();
    return Promise.resolve(null);
  }
  refreshInFlight = (async () => {
    try {
      const response = await fetch(`${API_URL}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh }),
        cache: "no-store",
      });
      if (!response.ok) { expireSession(); return null; }
      const data = await response.json() as { access?: string; refresh?: string };
      if (!data.access) { expireSession(); return null; }
      localStorage.setItem("kriyopay_access", data.access);
      if (data.refresh) localStorage.setItem("kriyopay_refresh", data.refresh);
      return data.access;
    } catch {
      // Network outages should not sign a user out; the original request can be retried later.
      return null;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

// Share simultaneous reads and briefly reuse list/dashboard responses while a
// user moves between pages. Writes invalidate the cache immediately.
const readsInFlight = new Map<string, Promise<Response>>();
const recentReads = new Map<string, { expiresAt: number; response: Response }>();
const READ_CACHE_MS = 2000;
let readCacheEpoch = 0;

export async function apiFetch(path: string, init: RequestInit = {}) {
  if (typeof window === "undefined") return performFetch(path, init);
  const method = (init.method || "GET").toUpperCase();
  // Permission checks must always reflect current Super Admin feature access.
  const cacheable = method === "GET" && path !== "/auth/me" && Object.keys(init).length === 0;
  if (!cacheable) {
    if (method !== "GET") {
      readCacheEpoch += 1;
      recentReads.clear();
    }
    const response = await performFetch(path, init);
    if (method !== "GET") recentReads.clear();
    return response;
  }
  const key = JSON.stringify([path, workspaceKey(), accessToken()]);
  const now = Date.now();
  for (const [cacheKey, entry] of recentReads) {
    if (entry.expiresAt <= now) recentReads.delete(cacheKey);
  }
  const cached = recentReads.get(key);
  if (cached && cached.expiresAt > now) return cached.response.clone();
  let pending = readsInFlight.get(key);
  if (!pending) {
    const requestEpoch = readCacheEpoch;
    pending = performFetch(path, init);
    readsInFlight.set(key, pending);
    void pending.then(response => {
      if (!response.ok || requestEpoch !== readCacheEpoch) return;
      if (recentReads.size >= 128) recentReads.delete(recentReads.keys().next().value as string);
      recentReads.set(key, { expiresAt: Date.now() + READ_CACHE_MS, response: response.clone() });
    }).catch(() => {}).finally(() => {
      if (readsInFlight.get(key) === pending) readsInFlight.delete(key);
    });
  }
  // Each consumer needs its own body stream for .json()/.blob().
  return (await pending).clone();
}

async function performFetch(path: string, init: RequestInit) {
  const makeHeaders = (token: string) => {
    const headers = new Headers(init.headers);
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const workspace = workspaceKey();
    if (workspace) headers.set("X-Workspace", workspace);
    if (typeof FormData !== "undefined" && !(init.body instanceof FormData) && init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    return headers;
  };
  try {
    const first = await fetch(`${API_URL}${path}`, { ...init, headers: makeHeaders(accessToken()), cache: "no-store" });
    if (first.status === 403 && path !== "/auth/me") window.dispatchEvent(new Event("kriyopay:access-check"));
    if (first.status !== 401 || (!accessToken() && !refreshToken())) return first;
    const refreshed = await refreshAccessToken();
    if (!refreshed) return first;
    const retry = await fetch(`${API_URL}${path}`, { ...init, headers: makeHeaders(refreshed), cache: "no-store" });
    if (retry.status === 401) expireSession();
    return retry;
  } catch {
    throw new Error(`Cannot reach the KriyoPay API at ${API_URL}. Start KriyoPay with start-dev.ps1 and check that its backend address matches this URL. If it is already running, check its logs and CORS settings.`);
  }
}
