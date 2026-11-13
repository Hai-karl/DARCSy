// The menu is built from the permissions the server sends, so each role sees only its own pages.
export const NAV = [
  { to: "/", label: "Dashboard", icon: "gauge", perm: "dashboard:view", end: true },
  { to: "/log", label: "Log defect", icon: "clipboard", perm: "record:create" },
  { to: "/users", label: "Users", icon: "users", perm: "user:manage" },
  { to: "/account", label: "Account", icon: "user" },
];

export const navFor = (user) => NAV.filter((i) => !i.perm || user.permissions.includes(i.perm));

// Features not yet moved to this app (alerts, corrective actions, reports, dataset prediction) stay in the classic page.
const CLASSIC_PERMS = ["alert:view", "action:view", "report:export", "rootcause:train"];
export const needsClassic = (user) => CLASSIC_PERMS.some((p) => user.permissions.includes(p));

export const homeFor = (user) =>
  user.permissions.includes("dashboard:view") ? "/" : user.permissions.includes("user:manage") ? "/users" : "/account";
export const ROLES = ["QC Engineer", "Line Supervisor", "Quality Manager", "IT Administrator"];
