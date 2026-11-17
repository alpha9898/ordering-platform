import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { Navigate } from "react-router";
import { ApiError, get, post } from "./api";
import { Spinner } from "../components/ui";

export type Me = {
  user: { id: number; username: string; display_name: string | null; role: "super_admin" | "owner" | "staff" };
  restaurant: { id: number; slug: string; name: string; status: string; demo_mode: boolean } | null;
  can_manage: boolean;
  is_super: boolean;
};

type AuthCtx = {
  me: Me | null;
  loading: boolean;
  setMe: (m: Me | null) => void;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
};

const Ctx = createContext<AuthCtx>(null as unknown as AuthCtx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const refresh = useCallback(async () => {
    try {
      setMe(await get<Me>("/auth/me"));
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);
  const logout = useCallback(async () => {
    await post("/auth/logout");
    setMe(null);
  }, []);
  useEffect(() => {
    // customer pages never need a staff session
    if (/^\/(r|o)\//.test(window.location.pathname)) setLoading(false);
    else refresh();
  }, [refresh]);
  return <Ctx.Provider value={{ me, loading, setMe, refresh, logout }}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);

export function RequireAuth({ children, superOnly }: { children: ReactNode; superOnly?: boolean }) {
  const { me, loading } = useAuth();
  if (loading)
    return (
      <div className="grid min-h-screen place-items-center text-muted">
        <Spinner />
      </div>
    );
  if (!me) return <Navigate to="/login" replace />;
  if (superOnly && !me.is_super) return <Navigate to="/dashboard" replace />;
  return <>{children}</>;
}
