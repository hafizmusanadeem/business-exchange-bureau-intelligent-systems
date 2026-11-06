// Thin client for the BXB FastAPI backend (same origin, no /api prefix).
const BXB = {
  // Synthetic data ends 2026-06-30, so Q2 2026 is the latest quarter with events.
  QUARTER: "2026-Q2",
  TREND_FROM: "2025-Q2",
  TREND_TO: "2026-Q2",

  async request(method, path, params = {}, body = null) {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== "" && v !== null && v !== undefined) qs.append(k, v);
    });
    const url = qs.toString() ? `${path}?${qs}` : path;
    const res = await fetch(url, {
      method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try { const j = await res.json(); detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch (_) {}
      const err = new Error(detail);
      err.status = res.status;
      throw err;
    }
    return res.json();
  },
  get(path, params) { return this.request("GET", path, params); },
  post(path, params, body) { return this.request("POST", path, params, body); },

  // Formatting helpers
  aed(n) { return "AED " + Number(n).toLocaleString("en-US"); },
  esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  },
  multiple(price, base) {
    return base > 0 ? (price / base).toFixed(2) + "x" : "n/a";
  },
  pct(a, b) {
    return b > 0 ? ((a / b) * 100).toFixed(1) + "%" : "n/a";
  },
};
