import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import "./index.css";
import { AuthProvider, RequireAuth, useAuth } from "./lib/auth";
import { ToastProvider } from "./components/ui";
import Login from "./pages/Login";
import ChatSim from "./pages/chat/ChatSim";
import MenuPage from "./pages/menu/MenuPage";
import Track from "./pages/menu/Track";
import Dashboard from "./pages/dashboard/Dashboard";
import Admin from "./pages/admin/Admin";

function Home() {
  const { me, loading } = useAuth();
  if (loading) return null;
  if (!me) return <Navigate to="/login" replace />;
  return <Navigate to={me.is_super && !me.restaurant ? "/admin" : "/dashboard"} replace />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <ToastProvider>
        <AuthProvider>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/login" element={<Login />} />
            <Route path="/r/:slug" element={<MenuPage />} />
            <Route path="/r/:slug/chat" element={<ChatSim />} />
            <Route path="/o/:token" element={<Track />} />
            <Route
              path="/dashboard/*"
              element={
                <RequireAuth>
                  <Dashboard />
                </RequireAuth>
              }
            />
            <Route
              path="/admin/*"
              element={
                <RequireAuth superOnly>
                  <Admin />
                </RequireAuth>
              }
            />
            <Route path="*" element={<div className="grid min-h-screen place-items-center text-muted">الصفحة مش موجودة</div>} />
          </Routes>
        </AuthProvider>
      </ToastProvider>
    </BrowserRouter>
  </StrictMode>,
);
