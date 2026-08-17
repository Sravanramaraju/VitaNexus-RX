// Use the local API directly in development. This avoids a stale Vite proxy
// process turning a healthy clinical database lookup into an empty dropdown.
const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api/v1";
const TOKEN_KEY = "vitanexus_access_token";

export const getAccessToken = () => localStorage.getItem(TOKEN_KEY);
export const setAccessToken = (token) => token ? localStorage.setItem(TOKEN_KEY, token) : localStorage.removeItem(TOKEN_KEY);

export async function api(path, options = {}) {
  const headers = { ...(options.body ? { "Content-Type": "application/json" } : {}), ...options.headers };
  const token = getAccessToken();
  // Terminology is a public, read-only reference catalogue. Keeping it free of
  // an old session token prevents an expired login from breaking autocomplete.
  if (token && !path.startsWith("/terminology/")) headers.Authorization = `Bearer ${token}`;
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch {
    throw new Error("Clinical API is unavailable. Start the VitaNexus-RX API service and verify its database connection.");
  }
  const raw = response.status === 204 ? "" : await response.text();
  let payload = null;
  try { payload = raw ? JSON.parse(raw) : null; } catch { throw new Error("Clinical API returned an invalid response."); }
  if (response.status === 401) {
    setAccessToken(null);
    window.dispatchEvent(new Event("vitanexus-auth-invalid"));
  }
  if (!response.ok) throw new Error(payload?.error?.message || "The request could not be completed.");
  return payload?.data;
}

export const apiJson = (path, method, body) => api(path, { method, body: JSON.stringify(body) });
