// All calls to the Flask API go through here. The token lives in sessionStorage (cleared when the tab closes).
const BASE = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
const KEY = "qc_token";

export const token = {
  get: () => sessionStorage.getItem(KEY),
  set: (t) => sessionStorage.setItem(KEY, t),
  clear: () => sessionStorage.removeItem(KEY),
};

let onExpired = () => {};
export const setExpiredHandler = (fn) => { onExpired = fn; };

export class ApiError extends Error {
  constructor(message, status, problems = []) {
    super(message);
    this.status = status;
    this.problems = problems;
  }
}

export async function api(path, { method = "GET", body, form, blob = false } = {}) {
  const headers = {};
  if (token.get()) headers.Authorization = `Bearer ${token.get()}`;
  if (body) headers["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch(BASE + path, { method, headers, body: form || (body ? JSON.stringify(body) : undefined) });
  } catch {
    throw new ApiError("Cannot reach the server. If it was idle it may need a minute to wake up. Try again shortly.", 0);
  }
  if (res.status === 401 && token.get() && !path.startsWith("/api/auth/login")) {
    token.clear();
    onExpired();
  }
  if (blob && res.ok) return res.blob();
  const data = res.status === 204 ? null : await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(data?.error || "Something went wrong. Please try again.", res.status, data?.problems);
  return data;
}
