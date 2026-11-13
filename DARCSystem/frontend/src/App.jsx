import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./lib/auth";
import { homeFor } from "./lib/nav";
import AppShell from "./components/AppShell";
import { Banner, Skeleton } from "./components/ui";
import Account from "./pages/Account";
import LogDefect from "./pages/LogDefect";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Users from "./pages/Users";

const Dashboard = lazy(() => import("./pages/Dashboard"));   // keeps the chart library out of the sign-in page

function Protected({ children }) {
  const { user, ready } = useAuth();
  const loc = useLocation();
  if (!ready) return <Skeleton className="m-8 h-40" />;
  return user ? children : <Navigate to="/login" replace state={{ from: loc.pathname }} />;
}

function Guard({ perm, children }) {
  const { can } = useAuth();
  return can(perm) ? children : <Banner kind="warn">Your role does not have access to this page.</Banner>;
}

function Home() {
  const { user, can } = useAuth();
  return can("dashboard:view") ? <Suspense fallback={<Skeleton className="h-64" />}><Dashboard /></Suspense> : <Navigate to={homeFor(user)} replace />;
}

export default function App() {
  const { user } = useAuth();
  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to={homeFor(user)} replace /> : <Login />} />
      <Route path="/register" element={user ? <Navigate to={homeFor(user)} replace /> : <Register />} />
      <Route element={<Protected><AppShell /></Protected>}>
        <Route index element={<Home />} />
        <Route path="log" element={<Guard perm="record:create"><LogDefect /></Guard>} />
        <Route path="users" element={<Guard perm="user:manage"><Users /></Guard>} />
        <Route path="account" element={<Account />} />
        <Route path="*" element={<Banner kind="warn">That page does not exist.</Banner>} />
      </Route>
    </Routes>
  );
}
