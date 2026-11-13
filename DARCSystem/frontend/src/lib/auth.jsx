import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, setExpiredHandler, token } from "./api";

const Ctx = createContext(null);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(!token.get());
  const [notice, setNotice] = useState("");

  const logout = useCallback((message = "") => {
    token.clear();
    setUser(null);
    setNotice(typeof message === "string" ? message : "");
  }, []);

  useEffect(() => {
    setExpiredHandler(() => logout("Your session ended. Please sign in again."));
    if (!token.get()) return;
    api("/api/auth/me").then(setUser).catch(() => token.clear()).finally(() => setReady(true));
  }, [logout]);

  const login = useCallback(async (username, password) => {
    const r = await api("/api/auth/login", { method: "POST", body: { username, password } });
    token.set(r.token);
    setNotice("");
    setUser(r.user);
    return r.user;
  }, []);

  const value = useMemo(() => ({
    user, ready, notice, login, logout,
    can: (perm) => !!user?.permissions?.includes(perm),
  }), [user, ready, notice, login, logout]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
