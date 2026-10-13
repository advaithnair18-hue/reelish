import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, RecipeSummary } from "../api";

function nextWeekName() {
  const d = new Date();
  return `Week of ${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;
}

export default function RecipesPage() {
  const navigate = useNavigate();
  const [recipes, setRecipes] = useState<RecipeSummary[] | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [name, setName] = useState(nextWeekName);
  const [error, setError] = useState("");

  useEffect(() => {
    api.recipes().then(setRecipes).catch((e) => setError(e.message));
  }, []);

  function toggle(id: number) {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function makeList(e: FormEvent) {
    e.preventDefault();
    try {
      const gl = await api.createList(name, [...selected]);
      navigate(`/lists/${gl.id}`);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function addBlank() {
    const r = await api.createRecipe({ title: "New recipe", servings: null, steps: [], ingredients: [] });
    navigate(`/recipes/${r.id}`);
  }

  return (
    <>
      <div className="page-head">
        <h2>Recipes</h2>
        <button className="small" onClick={addBlank}>
          + Add by hand
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {recipes === null ? (
        <p className="muted">Loading…</p>
      ) : recipes.length === 0 ? (
        <p className="muted">
          No recipes yet. <Link to="/">Upload a video</Link> to get started.
        </p>
      ) : (
        <ul className="rows">
          {recipes.map((r) => (
            <li key={r.id} className={`row selectable ${selected.has(r.id) ? "selected" : ""}`}>
              <label className="row-main">
                <input type="checkbox" checked={selected.has(r.id)} onChange={() => toggle(r.id)} />
                <span className="truncate">{r.title}</span>
                {!r.reviewed && <span className="badge processing">needs review</span>}
              </label>
              <Link to={`/recipes/${r.id}`} className="button small ghost">
                Edit
              </Link>
            </li>
          ))}
        </ul>
      )}

      {selected.size > 0 && (
        <form className="sticky-bar" onSubmit={makeList}>
          <input value={name} onChange={(e) => setName(e.target.value)} required aria-label="List name" />
          <button className="primary">
            Make grocery list ({selected.size} recipe{selected.size > 1 ? "s" : ""})
          </button>
        </form>
      )}
    </>
  );
}
