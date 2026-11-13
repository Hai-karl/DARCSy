import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { ClipboardPlus, ExternalLink, Gauge, LogOut, Menu, UserCog, Users, X } from "lucide-react";
import { useAuth } from "../lib/auth";
import { navFor, needsClassic } from "../lib/nav";
import { cx } from "./ui";

const ICONS = { gauge: Gauge, clipboard: ClipboardPlus, users: Users, user: UserCog };
const CLASSIC_URL = `${(import.meta.env.VITE_API_URL || "").replace(/\/$/, "")}/`;

export default function AppShell() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const link = ({ isActive }) =>
    cx("flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition",
      isActive ? "bg-brand-600 text-white" : "text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800");

  const menu = (
    <nav aria-label="Main" className="flex h-full flex-col">
      <div className="mb-6 flex items-center gap-2 px-2 font-display text-xl font-bold text-brand-600 dark:text-brand-400">
        <span aria-hidden>📉</span> Defect QC
      </div>
      <ul className="space-y-1">
        {navFor(user).map(({ to, label, icon, end }) => {
          const Icon = ICONS[icon];
          return (
            <li key={to}>
              <NavLink to={to} end={end} className={link}><Icon size={18} aria-hidden />{label}</NavLink>
            </li>
          );
        })}
      </ul>
      {needsClassic(user) && (
        <div className="mt-6 border-t border-slate-200 pt-4 dark:border-slate-800">
          <p className="px-3 pb-1 text-xs font-medium uppercase tracking-wide text-slate-500">More tools</p>
          <a href={CLASSIC_URL} target="_blank" rel="noreferrer"
            className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800">
            <ExternalLink size={18} aria-hidden />Alerts, actions, reports
          </a>
        </div>
      )}
      <div className="mt-auto pt-6">
        <div className="mb-2 px-3 text-sm">
          <div className="font-medium">{user.full_name}</div>
          <div className="text-xs text-slate-500">{user.role}{user.assigned_line ? `, ${user.assigned_line}` : ""}</div>
        </div>
        <button onClick={() => logout()} className={cx(link({ isActive: false }), "w-full")}><LogOut size={18} aria-hidden />Sign out</button>
      </div>
    </nav>
  );

  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2">Skip to content</a>
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900 lg:block">{menu}</aside>

      {open && <div className="fixed inset-0 z-30 bg-black/40 lg:hidden" onClick={() => setOpen(false)} aria-hidden />}
      <aside aria-label="Menu" className={cx("fixed inset-y-0 left-0 z-40 w-72 transform bg-white p-4 shadow-xl transition-transform dark:bg-slate-900 lg:hidden", open ? "translate-x-0" : "-translate-x-full")}>
        <button onClick={() => setOpen(false)} aria-label="Close menu" className="absolute right-3 top-3 rounded p-1 hover:bg-slate-100 dark:hover:bg-slate-800"><X size={20} /></button>
        {menu}
      </aside>

      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-slate-200 bg-white/90 px-4 py-3 backdrop-blur dark:border-slate-800 dark:bg-slate-900/90 lg:hidden">
          <button onClick={() => setOpen(true)} aria-label="Open menu" aria-expanded={open} className="rounded p-1 hover:bg-slate-100 dark:hover:bg-slate-800"><Menu size={22} /></button>
          <span className="font-display text-lg font-bold text-brand-600 dark:text-brand-400">Defect QC</span>
          <span className="ml-auto rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700 dark:bg-slate-800 dark:text-brand-400">{user.role}</span>
        </header>
        <main id="main" className="mx-auto max-w-6xl p-4 sm:p-6"><Outlet /></main>
      </div>
    </div>
  );
}
