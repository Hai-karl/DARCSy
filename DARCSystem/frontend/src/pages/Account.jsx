import { useState } from "react";
import { api, token } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Banner, Button, Card, Field, PageHeader, PasswordRules, TextInput } from "../components/ui";

export default function Account() {
  const { user, logout } = useAuth();
  const [f, setF] = useState({ current_password: "", new_password: "", confirm: "" });
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const change = async (e) => {
    e.preventDefault();
    if (f.new_password !== f.confirm) return setMsg({ kind: "error", text: "The new passwords do not match." });
    setBusy(true); setMsg(null);
    try {
      const r = await api("/api/auth/change-password", { method: "POST", body: { current_password: f.current_password, new_password: f.new_password } });
      token.set(r.token);                                   // other devices were signed out; this tab stays signed in
      setF({ current_password: "", new_password: "", confirm: "" });
      setMsg({ kind: "success", text: "Password changed. Other devices were signed out." });
    } catch (ex) { setMsg({ kind: "error", text: ex.message, problems: ex.problems }); }
    setBusy(false);
  };
  const everywhere = async () => { await api("/api/auth/logout-all", { method: "POST" }).catch(() => {}); logout("You were signed out on all devices."); };

  return (
    <div className="max-w-xl space-y-5">
      <PageHeader title="Account" />
      <Card title={user.full_name} subtitle={`${user.role}${user.assigned_line ? `, ${user.assigned_line}` : ""}`}>
        <dl className="grid grid-cols-[110px_1fr] gap-y-1 text-sm">
          <dt className="text-slate-500">Username</dt><dd>{user.username}</dd>
          <dt className="text-slate-500">Email</dt><dd>{user.email || "Not set"}</dd>
        </dl>
      </Card>
      <Card title="Change password">
        <form onSubmit={change} className="space-y-3">
          <Field label="Current password"><TextInput type="password" value={f.current_password} onChange={set("current_password")} autoComplete="current-password" required /></Field>
          <Field label="New password"><TextInput type="password" value={f.new_password} onChange={set("new_password")} autoComplete="new-password" required /><PasswordRules password={f.new_password} username={user.username} /></Field>
          <Field label="Confirm new password"><TextInput type="password" value={f.confirm} onChange={set("confirm")} autoComplete="new-password" required /></Field>
          <Banner kind={msg?.kind} problems={msg?.problems}>{msg?.text}</Banner>
          <Button type="submit" busy={busy}>Change password</Button>
        </form>
      </Card>
      <Card title="Sessions" subtitle="Sign out on every phone and computer where you are signed in."><Button variant="secondary" onClick={everywhere}>Sign out everywhere</Button></Card>
    </div>
  );
}
