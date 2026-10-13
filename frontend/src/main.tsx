import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, NavLink, Outlet, Route, Routes, useNavigate } from "react-router-dom";
import { token } from "./api";
import AuthPage from "./pages/AuthPage";
import ListPage from "./pages/ListPage";
import ListsPage from "./pages/ListsPage";
import RecipeEditPage from "./pages/RecipeEditPage";
import RecipesPage from "./pages/RecipesPage";
import UploadPage from "./pages/UploadPage";
import "./styles.css";

function Layout() {
  const navigate = useNavigate();
  if (!token.get()) return <Navigate to="/login" replace />;
  return (
    <div className="shell">
      <header className="topbar">
        <NavLink to="/" className="brand">
          Reel<span>Groceries</span>
        </NavLink>
        <nav>
          <NavLink to="/" end>Add</NavLink>
          <NavLink to="/recipes">Recipes</NavLink>
          <NavLink to="/lists">Lists</NavLink>
          <button
            className="link"
            onClick={() => {
              token.clear();
              navigate("/login");
            }}
          >
            Log out
          </button>
        </nav>
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<AuthPage />} />
        <Route element={<Layout />}>
          <Route path="/" element={<UploadPage />} />
          <Route path="/recipes" element={<RecipesPage />} />
          <Route path="/recipes/:id" element={<RecipeEditPage />} />
          <Route path="/lists" element={<ListsPage />} />
          <Route path="/lists/:id" element={<ListPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);
