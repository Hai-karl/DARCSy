export const pct = (v, d = 1) => `${(v * 100).toFixed(d)}%`;

/** p-chart: rows are [label, units, defects, start, end]. Limits widen for small samples. */
export function controlChart(weeks, maWindow = 4, sigma = 3) {
  const units = weeks.reduce((a, r) => a + r[1], 0);
  const defects = weeks.reduce((a, r) => a + r[2], 0);
  const center = units ? defects / units : 0;
  const rows = weeks.map(([label, u, d, start, end]) => {
    const p = d / u, se = Math.sqrt((center * (1 - center)) / u);
    return { label, start, end, p, ucl: center + sigma * se, lcl: Math.max(0, center - sigma * se) };
  });
  rows.forEach((r, i) => {
    const w = rows.slice(Math.max(0, i - maWindow + 1), i + 1);
    r.ma = w.reduce((a, x) => a + x.p, 0) / w.length;
  });
  const n = rows.length, mx = (n - 1) / 2, my = rows.reduce((a, r) => a + r.p, 0) / (n || 1);
  let sxy = 0, sxx = 0;
  rows.forEach((r, i) => { sxy += (i - mx) * (r.p - my); sxx += (i - mx) ** 2; });
  return {
    rows, center, units, defects, n,
    outOfControl: rows.filter((r) => r.p > r.ucl || r.p < r.lcl).length,
    change: n > 1 && sxx ? (sxy / sxx) * (n - 1) : 0,    // total movement of the rate across the period
    latest: rows[n - 1]?.p ?? 0,
  };
}

/** counts: {name: count}. Ranked rows with cumulative % and the "vital few" flag (first 80%). */
export function pareto(counts) {
  const e = Object.entries(counts || {}).sort((a, b) => b[1] - a[1]);
  const total = e.reduce((a, x) => a + x[1], 0);
  let run = 0;
  return e.map(([name, count]) => {
    const before = run / (total || 1);
    run += count;
    return { name, count, cumulative: (run / (total || 1)) * 100, vital: before < 0.8 };
  });
}

export const passwordRules = (pw, username = "") => [
  { ok: pw.length >= 10, text: "At least 10 characters" },
  { ok: /[A-Za-z]/.test(pw) && /\d/.test(pw), text: "A letter and a number" },
  { ok: !username || username.length < 3 || !pw.toLowerCase().includes(username.toLowerCase()), text: "Does not contain your username" },
];
