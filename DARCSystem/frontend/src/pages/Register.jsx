import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { ROLES } from "../lib/nav";
import { Banner, Button, Card, Field, PasswordRules, Select, TextInput } from "../components/ui";

const SELF_SERVICE = ROLES.filter((r) => r !== "IT Administrator");

export default function Register() {
  const [f, setF] = useState({ username: "", full_name: "", email: "", role: "QC Engineer", password: "", confirm: "" });
  const [err, setErr] = useState({ message: "", problems: [] });
  const [done, setDone] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    if (f.password !== f.confirm) return setErr({ message: "The two passwords do not match.", problems: [] });
    setBusy(true); setErr({ message: "", problems: [] });
    try {
      const { confirm, ...body } = f;
      setDone((await api("/api/auth/register", { method: "POST", body })).message);
    } catch (ex) { setErr({ message: ex.message, problems: ex.problems }); }
    setBusy(false);
  };

  return (
    <div className="grid min-h-screen place-items-center p-4">
      <Card className="w-full max-w-md" title="Request an account" subtitle="An administrator reviews every request before you can sign in.">
        {done ? (
          <div className="space-y-3">
            <Banner kind="success">{done}</Banner>
            <Link to="/login" className="text-sm font-medium text-brand-600 underline dark:text-brand-400">Back to sign in</Link>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-3">
            <Field label="Full name"><TextInput value={f.full_name} onChange={set("full_name")} autoComplete="name" required /></Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Username"><TextInput value={f.username} onChange={set("username")} autoComplete="username" required /></Field>
              <Field label="Role you need"><Select value={f.role} onChange={set("role")} options={SELF_SERVICE} /></Field>
            </div>
            <Field label="Email"><TextInput type="email" value={f.email} onChange={set("email")} autoComplete="email" required /></Field>
            <Field label="Password">
              <TextInput type="password" value={f.password} onChange={set("password")} autoComplete="new-password" required />
              <PasswordRules password={f.password} username={f.username} />
            </Field>
            <Field label="Confirm password"><TextInput type="password" value={f.confirm} onChange={set("confirm")} autoComplete="new-password" required /></Field>
            <Banner kind="error" problems={err.problems}>{err.message}</Banner>
            <Button type="submit" busy={busy} className="w-full">Send request</Button>
            <p className="text-center text-sm text-slate-500">Already approved? <Link to="/login" className="font-medium text-brand-600 underline dark:text-brand-400">Sign in</Link></p>
          </form>
        )}
      </Card>
    </div>
  );
}
