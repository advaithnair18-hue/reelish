import { FormEvent, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, Ingredient, Recipe } from "../api";

const UNITS = ["", "tsp", "tbsp", "cup", "ml", "l", "g", "kg", "oz", "lb", "clove", "can", "pinch", "bunch", "slice"];

interface Row extends Ingredient {
  key: number;
  quantity: string;
}

let nextKey = 1;
const toRow = (i: Ingredient): Row => ({ ...i, key: nextKey++, quantity: i.quantity_display ?? String(i.quantity ?? "") });

export default function RecipeEditPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [recipe, setRecipe] = useState<Recipe | null>(null);
  const [title, setTitle] = useState("");
  const [servings, setServings] = useState("");
  const [rows, setRows] = useState<Row[]>([]);
  const [steps, setSteps] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api
      .recipe(Number(id))
      .then((r) => {
        setRecipe(r);
        setTitle(r.title);
        setServings(r.servings ? String(r.servings) : "");
        setRows(r.ingredients.map(toRow));
        setSteps(r.steps.join("\n"));
      })
      .catch((e) => setError(e.message));
  }, [id]);

  const update = (key: number, patch: Partial<Row>) => setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));

  async function save(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const r = await api.saveRecipe(Number(id), {
        title,
        servings: servings ? Number(servings) : null,
        steps: steps.split("\n").map((s) => s.trim()).filter(Boolean),
        ingredients: rows
          .filter((r) => r.name.trim())
          .map((r) => ({ name: r.name, quantity: r.quantity.trim() || null, unit: r.unit, raw_text: r.raw_text })),
      });
      setRecipe(r);
      setRows(r.ingredients.map(toRow));
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function remove() {
    if (!confirm("Delete this recipe?")) return;
    await api.deleteRecipe(Number(id));
    navigate("/recipes");
  }

  if (!recipe) return <p className={error ? "error" : "muted"}>{error || "Loading…"}</p>;

  return (
    <form onSubmit={save} className="card stack">
      {!recipe.reviewed && (
        <p className="warn">Extracted automatically. Check the amounts against the video, then save.</p>
      )}
      <div className="grid-2">
        <label>
          Title
          <input value={title} onChange={(e) => setTitle(e.target.value)} required />
        </label>
        <label>
          Servings
          <input type="number" min={1} max={100} value={servings} onChange={(e) => setServings(e.target.value)} />
        </label>
      </div>

      <h3>Ingredients</h3>
      <div className="ingredients">
        <div className="ing-row head muted">
          <span>Amount</span>
          <span>Unit</span>
          <span>Ingredient</span>
          <span />
        </div>
        {rows.map((r) => (
          <div className="ing-row" key={r.key} title={r.raw_text ? `From: “${r.raw_text}”` : undefined}>
            <input value={r.quantity} onChange={(e) => update(r.key, { quantity: e.target.value })} placeholder="1 1/2" aria-label="Amount" />
            <select value={r.unit} onChange={(e) => update(r.key, { unit: e.target.value })} aria-label="Unit">
              {(UNITS.includes(r.unit) ? UNITS : [...UNITS, r.unit]).map((u) => (
                <option key={u} value={u}>
                  {u || "—"}
                </option>
              ))}
            </select>
            <input value={r.name} onChange={(e) => update(r.key, { name: e.target.value })} placeholder="onion" aria-label="Ingredient" />
            <button type="button" className="icon" onClick={() => setRows((rs) => rs.filter((x) => x.key !== r.key))} aria-label="Remove">
              ×
            </button>
          </div>
        ))}
        <button type="button" className="small ghost" onClick={() => setRows((rs) => [...rs, toRow({ name: "", quantity: "", unit: "" })])}>
          + Add ingredient
        </button>
      </div>

      <label>
        <span>
          Steps <span className="muted">(one per line)</span>
        </span>
        <textarea rows={6} value={steps} onChange={(e) => setSteps(e.target.value)} />
      </label>

      {error && <p className="error">{error}</p>}
      <div className="actions">
        <button type="button" className="danger ghost" onClick={remove}>
          Delete
        </button>
        <button className="primary">{saved ? "Saved ✓" : "Save recipe"}</button>
      </div>
    </form>
  );
}
