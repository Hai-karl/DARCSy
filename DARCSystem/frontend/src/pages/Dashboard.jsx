import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { controlChart, pareto, pct } from "../lib/stats";
import ChartCanvas from "../components/ChartCanvas";
import { Banner, Button, Card, Field, PageHeader, Segmented, Select, Skeleton, Stat } from "../components/ui";

const UNIT = { D: "days", W: "weeks", M: "months" };
const MA = { D: 7, W: 4, M: 3 };

export default function Dashboard() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [line, setLine] = useState(user.assigned_line || "All");
  const [gran, setGran] = useState("W");
  const [last, setLast] = useState(0);

  useEffect(() => { api("/api/dashboard/bundle").then(setData).catch((e) => setError(e.message)); }, []);

  const rows = useMemo(() => {
    const all = data?.trend?.[gran]?.[line] || data?.weekly?.[line] || [];
    return last ? all.slice(-last) : all;
  }, [data, gran, line, last]);
  const chart = useMemo(() => controlChart(rows, MA[gran]), [rows, gran]);

  if (error) return <Banner kind="error">{error}</Banner>;
  if (!data) return <div className="space-y-4"><Skeleton className="h-24" /><Skeleton className="h-80" /><Skeleton className="h-64" /></div>;
  if (!data.lines?.length) {
    return <Banner kind="info">No defect records yet. A QC Engineer can log defects or upload a CSV file to start the dashboard.</Banner>;
  }
  const scope = line === "All" ? "All lines" : line;
  const drift = Math.abs(chart.change) < 0.002 ? "The defect rate is holding steady."
    : `The defect rate has ${chart.change > 0 ? "risen" : "fallen"} by ${(Math.abs(chart.change) * 100).toFixed(1)} percentage points over this period.`;

  return (
    <div className="space-y-5">
      <PageHeader title="Dashboard">
        <div className="flex flex-wrap gap-2">
          {!user.assigned_line && (
            <Segmented label="Production line" value={line} onChange={setLine} options={["All", ...data.lines].map((l) => [l, l])} />
          )}
          <Segmented label="Time step" value={gran} onChange={setGran} options={[["D", "Daily"], ["W", "Weekly"], ["M", "Monthly"]]} />
          <Select aria-label="Period" value={last} onChange={(e) => setLast(+e.target.value)} className="!w-auto"
            options={[{ value: 0, label: "All" }, { value: 30, label: "Last 30" }, { value: 12, label: "Last 12" }, { value: 6, label: "Last 6" }]} />
        </div>
      </PageHeader>

      <Card>
        <p className="font-display text-3xl font-bold leading-tight sm:text-4xl">
          {scope} went outside its control limits in <span className="text-signal">{chart.outOfControl} of {chart.n}</span> {UNIT[gran]}
        </p>
        <p className="mt-1 text-slate-500 dark:text-slate-400">{drift}</p>
        <ChartCanvas label="Defect rate over time with control limits" height={300} deps={[chart]}
          build={(t) => ({
            type: "line",
            data: {
              labels: chart.rows.map((r) => r.label),
              datasets: [
                { label: "Defect rate", data: chart.rows.map((r) => r.p), borderColor: t.brand, borderWidth: 2, tension: 0.2,
                  pointRadius: chart.rows.map((r) => (r.p > r.ucl ? 5 : 2.5)),
                  pointBackgroundColor: chart.rows.map((r) => (r.p > r.ucl ? t.signal : t.brand)) },
                { label: "Upper limit", data: chart.rows.map((r) => r.ucl), borderColor: t.signal, borderDash: [6, 4], borderWidth: 1.2, pointRadius: 0 },
                { label: "Average", data: chart.rows.map(() => chart.center), borderColor: t.text, borderWidth: 1, pointRadius: 0 },
                { label: "Lower limit", data: chart.rows.map((r) => r.lcl), borderColor: t.signal, borderDash: [6, 4], borderWidth: 1.2, pointRadius: 0 },
                { label: "Moving average", data: chart.rows.map((r) => r.ma), borderColor: t.ok, borderDash: [2, 3], borderWidth: 2, pointRadius: 0 },
              ],
            },
            options: {
              maintainAspectRatio: false, animation: false, interaction: { mode: "index", intersect: false },
              plugins: { legend: { position: "bottom", labels: { color: t.text, boxWidth: 14 } } },
              scales: {
                x: { ticks: { color: t.text, maxTicksLimit: 8 }, grid: { display: false } },
                y: { beginAtZero: true, ticks: { color: t.text, callback: (v) => pct(v) }, grid: { color: t.grid } },
              },
            },
          })} />
        <p className="text-sm text-slate-500">Orange points are above the upper control limit.</p>
      </Card>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Overall defect rate" value={pct(chart.center, 2)} />
        <Stat label="Latest period" value={pct(chart.latest, 2)} tone={chart.latest > (chart.rows.at(-1)?.ucl ?? 1) ? "alert" : undefined} />
        <Stat label="Defects found" value={chart.defects.toLocaleString()} />
        <Stat label="Units inspected" value={chart.units.toLocaleString()} />
      </div>

      <ParetoCard data={data} line={line} />
      <RootCauseCard data={data} line={line} />
    </div>
  );
}

function ParetoCard({ data, line }) {
  const [view, setView] = useState("defect");
  const src = { defect: data.pareto, machine: data.machine, severity: data.severity }[view]?.[line];
  const p = useMemo(() => pareto(src), [src]);
  return (
    <Card title="Pareto analysis" subtitle="Dark bars are the vital few that make up the first 80% of defects."
      action={<Segmented label="Group by" value={view} onChange={setView} options={[["defect", "Defect type"], ["machine", "Machine"], ["severity", "Severity"]]} />}>
      {p.length === 0 ? <Banner>No defects recorded for this view.</Banner> : (
        <ChartCanvas label="Pareto chart" height={260} deps={[p]}
          build={(t) => ({
            data: {
              labels: p.map((r) => r.name),
              datasets: [
                { type: "bar", data: p.map((r) => r.count), backgroundColor: p.map((r) => (r.vital ? t.brand : t.grid)), borderRadius: 3, yAxisID: "y" },
                { type: "line", data: p.map((r) => r.cumulative), borderColor: t.signal, borderWidth: 2, pointRadius: 3, yAxisID: "y2" },
              ],
            },
            options: {
              maintainAspectRatio: false, animation: false, plugins: { legend: { display: false } },
              scales: {
                x: { ticks: { color: t.text }, grid: { display: false } },
                y: { beginAtZero: true, ticks: { color: t.text }, grid: { color: t.grid } },
                y2: { position: "right", min: 0, max: 100, ticks: { color: t.text, callback: (v) => `${v}%` }, grid: { display: false } },
              },
            },
          })} />
      )}
    </Card>
  );
}

function RootCauseCard({ data, line }) {
  const { can } = useAuth();
  const [f, setF] = useState({ defect_type: "", line: "" });
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  if (!can("rootcause:predict")) return null;
  const types = Object.keys(data.pareto?.All || {});
  const recent = (data.pred || []).filter((p) => line === "All" || p.line === line);
  const run = async () => {
    setBusy(true);
    try {
      setRes(await api("/api/rootcause/investigate", { method: "POST", body: { defect_type: f.defect_type || undefined, line: f.line || undefined } }));
    } catch (e) { setRes({ error: e.message }); }
    setBusy(false);
  };
  return (
    <Card title="Root cause suggestions" subtitle="A decision tree suggests likely causes from past records. Treat them as leads to check, not confirmed causes.">
      {data.acc == null && <Banner kind="warn">The model has not been trained yet. A Quality Manager can train it from the classic page under More tools.</Banner>}
      <div className="my-3 flex flex-wrap items-end gap-3">
        <Field label="Defect type"><Select value={f.defect_type} onChange={(e) => setF({ ...f, defect_type: e.target.value })} options={[{ value: "", label: "Any" }, ...types]} /></Field>
        <Field label="Line"><Select value={f.line} onChange={(e) => setF({ ...f, line: e.target.value })} options={[{ value: "", label: "Any" }, ...(data.lines || [])]} /></Field>
        <Button onClick={run} busy={busy}>Find likely causes</Button>
      </div>
      {res?.error && <Banner kind="error">{res.error}</Banner>}
      {res && !res.error && (
        <div className="mb-4 space-y-2">
          <Banner kind={res.low_confidence ? "warn" : "info"}>{res.message}</Banner>
          {res.ranked.map((x) => (
            <div key={x.cause} className="grid grid-cols-[110px_1fr_48px] items-center gap-3 text-sm">
              <span>{x.cause}</span>
              <div className="h-2 rounded bg-slate-200 dark:bg-slate-800"><div className="h-2 rounded bg-brand-600" style={{ width: `${Math.max(2, x.confidence * 100)}%` }} /></div>
              <span className="text-right tabular-nums">{pct(x.confidence, 0)}</span>
            </div>
          ))}
        </div>
      )}
      {recent.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead className="text-slate-500"><tr>{["Record", "Defect", "Top suggestion", "Next most likely"].map((h) => <th key={h} className="border-b border-slate-200 py-2 pr-3 font-medium dark:border-slate-800">{h}</th>)}</tr></thead>
            <tbody>
              {recent.map((p, i) => (
                <tr key={i} className="border-b border-slate-100 dark:border-slate-800">
                  <td className="py-2 pr-3">{p.date}, {p.line}, {p.machine}, {p.shift}</td>
                  <td className="pr-3">{p.defect}</td>
                  <td className="pr-3 font-medium">{p.s[0][0]} {pct(p.s[0][1], 0)}</td>
                  <td className="text-slate-500">{p.s[1][0]} {pct(p.s[1][1], 0)}, {p.s[2][0]} {pct(p.s[2][1], 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
