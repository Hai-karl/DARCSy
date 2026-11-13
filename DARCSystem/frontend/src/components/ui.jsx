import { passwordRules } from "../lib/stats";

export const cx = (...c) => c.filter(Boolean).join(" ");

export function Card({ title, subtitle, action, children, className }) {
  return (
    <section className={cx("rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900", className)}>
      {(title || action) && (
        <header className="mb-3 flex flex-wrap items-start justify-between gap-2">
          <div>
            {title && <h2 className="text-lg font-semibold">{title}</h2>}
            {subtitle && <p className="text-sm text-slate-500 dark:text-slate-400">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function PageHeader({ title, children }) {
  return (
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
      <h1 className="text-2xl font-semibold">{title}</h1>
      {children}
    </div>
  );
}

const KIND = {
  error: "border-red-300 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200",
  success: "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200",
  warn: "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200",
  info: "border-slate-300 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300",
};
export function Banner({ kind = "info", children, problems }) {
  if (!children && !problems?.length) return null;
  return (
    <div role={kind === "error" ? "alert" : "status"} className={cx("rounded-lg border px-3 py-2 text-sm", KIND[kind])}>
      {children}
      {problems?.length > 0 && <ul className="mt-1 list-disc pl-5">{problems.map((p) => <li key={p}>{p}</li>)}</ul>}
    </div>
  );
}

const input = "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm placeholder:text-slate-400 dark:border-slate-700 dark:bg-slate-950";
export function Field({ label, hint, children, className }) {
  return (
    <label className={cx("block text-sm", className)}>
      <span className="mb-1 block font-medium text-slate-700 dark:text-slate-300">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}
export const TextInput = (p) => <input {...p} className={cx(input, p.className)} />;
export const Select = ({ options, ...p }) => (
  <select {...p} className={cx(input, p.className)}>
    {options.map((o) => (typeof o === "string" ? <option key={o}>{o}</option> : <option key={o.value} value={o.value}>{o.label}</option>))}
  </select>
);

export function Button({ variant = "primary", busy, children, className, ...p }) {
  const v = {
    primary: "bg-brand-600 text-white hover:bg-brand-700",
    secondary: "border border-slate-300 bg-white hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800",
    danger: "bg-red-600 text-white hover:bg-red-700",
  }[variant];
  return (
    <button {...p} disabled={busy || p.disabled}
      className={cx("inline-flex items-center justify-center rounded-lg px-4 py-2 text-sm font-semibold transition disabled:opacity-60", v, className)}>
      {busy ? "Working" : children}
    </button>
  );
}

export function Segmented({ value, onChange, options, label }) {
  return (
    <div role="group" aria-label={label} className="inline-flex overflow-hidden rounded-lg border border-slate-300 bg-white dark:border-slate-700 dark:bg-slate-900">
      {options.map(([v, text]) => (
        <button key={v} type="button" aria-pressed={value === v} onClick={() => onChange(v)}
          className={cx("px-3 py-1.5 text-sm", value === v ? "bg-brand-600 font-semibold text-white" : "hover:bg-slate-100 dark:hover:bg-slate-800")}>
          {text}
        </button>
      ))}
    </div>
  );
}

export function PasswordRules({ password, username }) {
  return (
    <ul className="mt-2 space-y-0.5 text-xs" aria-label="Password rules">
      {passwordRules(password, username).map((r) => (
        <li key={r.text} className={r.ok ? "text-emerald-600" : "text-slate-500"}>{r.ok ? "✓" : "○"} {r.text}</li>
      ))}
    </ul>
  );
}

export function Stat({ label, value, tone }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <div className={cx("font-display text-3xl font-bold", tone === "alert" && "text-signal")}>{value}</div>
      <div className="text-sm text-slate-500 dark:text-slate-400">{label}</div>
    </div>
  );
}

export const Skeleton = ({ className }) => <div className={cx("animate-pulse rounded-xl bg-slate-200 dark:bg-slate-800", className)} />;
