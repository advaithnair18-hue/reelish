import "@fontsource-variable/bricolage-grotesque";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, NavLink, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { token } from "./api";
import AuthPage from "./pages/AuthPage";
import HomePage from "./pages/HomePage";
import ListPage from "./pages/ListPage";
import RecipePage from "./pages/RecipePage";
import SettingsPage from "./pages/SettingsPage";
import SharePage from "./pages/SharePage";
import { registerServiceWorker } from "./pwa";
import "./styles.css";
import { Icon, ToastProvider } from "./ui";

function RequireAuth() {
  const location = useLocation();
  if (!token.get()) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/welcome?next=${next}`} replace />;
  }
  return <Outlet />;
}

function TabLayout() {
  return (
    <div className="app">
      <main className="screen">
        <Outlet />
      </main>
      <nav className="tabbar" aria-label="Main">
        <NavLink to="/" end>
          <Icon name="recipes" />
          <span>Recipes</span>
        </NavLink>
        <NavLink to="/list">
          <Icon name="list" />
          <span>List</span>
        </NavLink>
        <NavLink to="/settings">
          <Icon name="settings" />
          <span>Settings</span>
        </NavLink>
      </nav>
    </div>
  );
}

registerServiceWorker();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ToastProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/welcome" element={<AuthPage />} />
          <Route element={<RequireAuth />}>
            <Route path="/share" element={<SharePage />} />
            <Route element={<TabLayout />}>
              <Route path="/" element={<HomePage />} />
              <Route path="/recipes/:id" element={<RecipePage />} />
              <Route path="/list" element={<ListPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </ToastProvider>
  </React.StrictMode>,
);
