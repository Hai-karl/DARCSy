import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { homeFor } from "../lib/nav";
import { Banner, Button, Card, Field, TextInput } from "../components/ui";

export default function Login() {
  const { login, notice } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [f, setF] = useState({ username: "", password: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [slow, setSlow] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setErr("");
    const timer = setTimeout(() => setSlow(true), 4000);
    try {
      const u = await login(f.username, f.password);
      nav(loc.state?.from || homeFor(u), { replace: true });
    } catch (ex) { setErr(ex.message); }
    clearTimeout(timer); setSlow(false); setBusy(false);
  };

  return (
    <div className="grid min-h-screen place-items-center p-4">
      <Card className="w-full max-w-sm">
        <div className="mb-4 text-center">
          <div className="text-4xl" aria-hidden>📉</div>
          <h1 className="font-display text-2xl font-bold">Defect QC</h1>
          <p className="text-sm text-slate-500">Sign in to view quality control analytics.</p>
        </div>
        <form onSubmit={submit} className="space-y-3">
          <Banner kind="info">{notice}</Banner>
          <Field label="Username"><TextInput value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} autoComplete="username" required /></Field>
          <Field label="Password"><TextInput type="password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} autoComplete="current-password" required /></Field>
          <Banner kind="error">{err}</Banner>
          {slow && <Banner kind="info">Waking the server up. This can take up to a minute on the first visit.</Banner>}
          <Button type="submit" busy={busy} className="w-full">Sign in</Button>
        </form>
        <p className="mt-4 text-center text-sm text-slate-500">New here? <Link to="/register" className="font-medium text-brand-600 underline dark:text-brand-400">Request an account</Link></p>
      </Card>
    </div>
  );
}
