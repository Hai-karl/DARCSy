import { useRef, useState } from "react";
import { api } from "../lib/api";
import { Banner, Button, Card, Field, PageHeader, Select, TextInput } from "../components/ui";

const SEVERITY = ["Minor", "Major", "Critical", "Safety-Critical"];
const blank = () => ({ date: new Date().toISOString().slice(0, 10), line: "", product: "", shift: "Morning", machine: "", batch: "", dtype: "", severity: "Minor", units: "", defects: "" });

export default function LogDefect() {
  const [f, setF] = useState(blank());
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const file = useRef(null);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    const u = Number(f.units), d = Number(f.defects);
    const bad = !(u > 0) ? "Units inspected must be greater than 0."
      : f.defects === "" || !(d >= 0) ? "Defects found must be 0 or more."
      : d > u ? "Defects found can’t be higher than units inspected."
      : d > 0 && !f.dtype.trim() ? "Enter the defect type." : "";
    if (bad) return setMsg({ kind: "error", text: bad });
    setBusy(true); setMsg(null);
    try {
      await api("/api/records", { method: "POST", body: {
        inspection_date: f.date, production_line: f.line.trim(), product_type: f.product.trim(), shift: f.shift,
        machine_id: f.machine.trim(), batch_number: f.batch.trim(), defect_type: d > 0 ? f.dtype.trim() : "None",
        severity: d > 0 ? f.severity : "None", units_inspected: u, defect_count: d } });
      setF({ ...f, units: "", defects: "", dtype: "" });
      setMsg({ kind: "success", text: f.severity === "Safety-Critical" && d > 0 ? "Saved. A safety-critical alert was raised." : "Record saved." });
    } catch (ex) { setMsg({ kind: "error", text: ex.message, problems: ex.problems }); }
    setBusy(false);
  };

  const upload = async () => {
    if (!file.current?.files[0]) return setMsg({ kind: "error", text: "Choose a CSV or Excel file first." });
    const form = new FormData();
    form.append("file", file.current.files[0]);
    setBusy(true); setMsg(null);
    try {
      const r = await api("/api/records/import", { method: "POST", form });
      setMsg({ kind: "success", text: `${r.created} records imported.` });
      file.current.value = "";
    } catch (ex) { setMsg({ kind: "error", text: ex.message, problems: ex.problems }); }
    setBusy(false);
  };

  return (
    <div className="space-y-5">
      <PageHeader title="Log a defect" />
      <Card subtitle="Enter 0 defects for a clean batch. A Safety-Critical defect raises an alert straight away.">
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Date"><TextInput type="date" value={f.date} onChange={set("date")} required /></Field>
          <Field label="Production line"><TextInput value={f.line} onChange={set("line")} placeholder="Line A" required /></Field>
          <Field label="Product"><TextInput value={f.product} onChange={set("product")} placeholder="Housing" required /></Field>
          <Field label="Shift"><Select value={f.shift} onChange={set("shift")} options={["Morning", "Evening", "Night"]} /></Field>
          <Field label="Machine"><TextInput value={f.machine} onChange={set("machine")} placeholder="M-01" required /></Field>
          <Field label="Batch number"><TextInput value={f.batch} onChange={set("batch")} required /></Field>
          <Field label="Units inspected"><TextInput type="number" min="1" value={f.units} onChange={set("units")} required /></Field>
          <Field label="Defects found (quantity)"><TextInput type="number" min="0" value={f.defects} onChange={set("defects")} required /></Field>
          <Field label="Defect type" hint="Only needed when defects are found"><TextInput value={f.dtype} onChange={set("dtype")} placeholder="Scratch" /></Field>
          <Field label="Severity"><Select value={f.severity} onChange={set("severity")} options={SEVERITY} /></Field>
          <div className="flex items-end"><Button type="submit" busy={busy}>Save record</Button></div>
        </form>
        <div className="mt-3"><Banner kind={msg?.kind} problems={msg?.problems}>{msg?.text}</Banner></div>
      </Card>

      <Card title="Upload many records" subtitle="CSV or Excel with the columns: inspection_date, production_line, product_type, shift, machine_id, defect_type, batch_number, severity, units_inspected, defect_count. Use None for defect type and severity when there are 0 defects. If any row is wrong, nothing is saved.">
        <div className="flex flex-wrap items-center gap-3">
          <input ref={file} type="file" accept=".csv,.xlsx,.xls" className="text-sm" aria-label="File to upload" />
          <Button variant="secondary" onClick={upload} busy={busy}>Upload</Button>
        </div>
      </Card>
    </div>
  );
}
