import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { ROLES } from "../lib/nav";
import { Banner, Button, Card, Field, PageHeader, PasswordRules, Select, Skeleton, TextInput, cx } from "../components/ui";

const BADGE = { active: "bg-emerald-100 text-emerald-800", pending: "bg-amber-100 text-amber-900", rejected: "bg-red-100 text-red-800" };

export default function Users() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState(null);
  const [msg, setMsg] = useState(null);
  const load = useCallback(() => api("/api/users").then(setUsers).catch((e) => setMsg({ kind: "error", text: e.message })), []);
  useEffect(() => { load(); }, [load]);

  const act = async (fn, ok) => {
    setMsg(null);
    try { await fn(); setMsg({ kind: "success", text: ok }); await load(); }
    catch (e) { setMsg({ kind: "error", text: e.message, problems: e.problems }); }
  };
  const patch = (u, body, ok) => act(() => api(`/api/users/${u.id}`, { method: "PATCH", body }), ok);

  if (!users) return <Skeleton className="h-64" />;
  const pending = users.filter((u) => u.status === "pending");

  return (
    <div className="space-y-5">
      <PageHeader title="Users" />
      <Banner kind={msg?.kind} problems={msg?.problems}>{msg?.text}</Banner>

      {pending.length > 0 && (
        <Card title={`Waiting for approval (${pending.length})`} className="border-amber-300 dark:border-amber-700">
          <ul className="divide-y divide-slate-200 dark:divide-slate-800">
            {pending.map((u) => <Pending key={u.id} u={u} onApprove={(role) => patch(u, { status: "active", role }, `${u.username} approved.`)} onReject={() => patch(u, { status: "rejected" }, `${u.username} rejected.`)} />)}
          </ul>
        </Card>
      )}

      <Card title="All accounts">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="text-slate-500"><tr>{["User", "Role", "Line", "Status", "Last sign in", ""].map((h) => <th key={h} className="border-b border-slate-200 py-2 pr-3 font-medium dark:border-slate-800">{h}</th>)}</tr></thead>
            <tbody>
              {users.filter((u) => u.status !== "pending").map((u) => (
                <tr key={u.id} className="border-b border-slate-100 align-middle dark:border-slate-800">
                  <td className="py-2 pr-3"><div className="font-medium">{u.full_name}</div><div className="text-xs text-slate-500">{u.username}{u.email ? `, ${u.email}` : ""}</div></td>
                  <td className="pr-3">
                    <Select aria-label={`Role for ${u.username}`} value={u.role} disabled={u.id === me.id} className="!w-44"
                      onChange={(e) => patch(u, { role: e.target.value }, `${u.username} is now ${e.target.value}.`)} options={ROLES} />
                  </td>
                  <td className="pr-3">
                    <TextInput aria-label={`Assigned line for ${u.username}`} defaultValue={u.assigned_line || ""} placeholder="All" className="!w-28"
                      onBlur={(e) => e.target.value !== (u.assigned_line || "") && patch(u, { assigned_line: e.target.value.trim() }, `Line updated for ${u.username}.`)} />
                  </td>
                  <td className="pr-3"><span className={cx("rounded-full px-2 py-0.5 text-xs font-medium", BADGE[u.status])}>{u.is_active ? u.status : "disabled"}</span></td>
                  <td className="pr-3 text-xs text-slate-500">{u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "Never"}</td>
                  <td className="space-x-2 whitespace-nowrap">
                    {u.id !== me.id && <Button variant="secondary" className="!px-2 !py-1" onClick={() => patch(u, { is_active: !u.is_active }, u.is_active ? `${u.username} disabled.` : `${u.username} enabled.`)}>{u.is_active ? "Disable" : "Enable"}</Button>}
                    <Reset u={u} act={act} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <AddUser act={act} />
    </div>
  );
}

function Pending({ u, onApprove, onReject }) {
  const [role, setRole] = useState(u.role);
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div><div className="font-medium">{u.full_name} <span className="text-slate-500">({u.username})</span></div><div className="text-xs text-slate-500">{u.email}, asked for {u.role}</div></div>
      <div className="flex flex-wrap items-center gap-2">
        <Select aria-label={`Role for ${u.username}`} value={role} onChange={(e) => setRole(e.target.value)} options={ROLES} className="!w-44" />
        <Button onClick={() => onApprove(role)}>Approve</Button>
        <Button variant="danger" onClick={onReject}>Reject</Button>
      </div>
    </li>
  );
}

function Reset({ u, act }) {
  const [open, setOpen] = useState(false);
  const [pw, setPw] = useState("");
  if (!open) return <Button variant="secondary" className="!px-2 !py-1" onClick={() => setOpen(true)}>Reset password</Button>;
  return (
    <div className="mt-2 rounded-lg border border-slate-300 p-3 dark:border-slate-700">
      <Field label={`Temporary password for ${u.username}`}><TextInput type="text" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="off" /></Field>
      <PasswordRules password={pw} username={u.username} />
      <div className="mt-2 flex gap-2">
        <Button onClick={() => act(() => api(`/api/users/${u.id}/reset-password`, { method: "POST", body: { new_password: pw } }), `Password reset for ${u.username}. Share it privately and ask them to change it.`).then(() => { setOpen(false); setPw(""); })}>Set password</Button>
        <Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
      </div>
    </div>
  );
}

function AddUser({ act }) {
  const [f, setF] = useState({ username: "", full_name: "", email: "", role: "QC Engineer", assigned_line: "", password: "" });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  return (
    <Card title="Add a user" subtitle="Accounts you add are active straight away.">
      <form className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" onSubmit={(e) => { e.preventDefault(); act(() => api("/api/users", { method: "POST", body: f }), `${f.username} added.`).then(() => setF({ ...f, username: "", full_name: "", email: "", password: "" })); }}>
        <Field label="Username"><TextInput value={f.username} onChange={set("username")} required /></Field>
        <Field label="Full name"><TextInput value={f.full_name} onChange={set("full_name")} required /></Field>
        <Field label="Email"><TextInput type="email" value={f.email} onChange={set("email")} /></Field>
        <Field label="Role"><Select value={f.role} onChange={set("role")} options={ROLES} /></Field>
        <Field label="Assigned line" hint="Optional. Limits what this user sees."><TextInput value={f.assigned_line} onChange={set("assigned_line")} /></Field>
        <Field label="Password"><TextInput type="password" value={f.password} onChange={set("password")} autoComplete="new-password" required /><PasswordRules password={f.password} username={f.username} /></Field>
        <div className="flex items-end"><Button type="submit">Add user</Button></div>
      </form>
    </Card>
  );
}
