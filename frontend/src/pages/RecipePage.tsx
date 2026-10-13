import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, Ingredient, Recipe } from "../api";
import { formatAmount } from "../grocery";
import { Icon, PLATFORM_NAME, Switch, Thumb, useToast } from "../ui";

const UNITS = ["", "tsp", "tbsp", "cup", "ml", "l", "g", "kg", "oz", "lb", "clove", "can", "pinch", "bunch", "slice"];

export default function RecipePage() {
  const { id } = useParams();
  const recipeId = Number(id);
  const navigate = useNavigate();
  const toast = useToast();
  const [recipe, setRecipe] = useState<Recipe | null>(null);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.recipe(recipeId).then(setRecipe).catch((e) => setError(e.message));
  }, [recipeId]);

  async function toggleList(on: boolean) {
    if (!recipe) return;
    const list = await api.defaultList();
    if (on) await api.addRecipeToList(list.id, recipe.id);
    else await api.removeRecipeFromList(list.id, recipe.id);
    setRecipe({ ...recipe, in_default_list: on });
    toast(on ? "Added to your list" : "Removed from your list");
  }

  async function remove() {
    if (!confirm("Delete this recipe? Its ingredients come off your list too.")) return;
    await api.deleteRecipe(recipeId);
    toast("Recipe deleted");
    navigate("/");
  }

  if (!recipe) return <p className={error ? "notice error" : "muted pad"}>{error || "Loading…"}</p>;

  if (editing) {
    return (
      <RecipeEditor
        recipe={recipe}
        onCancel={() => setEditing(false)}
        onSaved={(r) => {
          setRecipe(r);
          setEditing(false);
          toast(r.in_default_list ? "Saved. Your list is updated." : "Saved");
        }}
      />
    );
  }

  return (
    <article className="recipe">
      <div className="recipe-top">
        <button className="icon-btn" onClick={() => navigate(-1)} aria-label="Back">
          <Icon name="back" />
        </button>
        <button className="btn ghost small" onClick={() => setEditing(true)}>
          <Icon name="edit" size={16} /> Edit
        </button>
      </div>

      <header className="recipe-hero">
        <div className="recipe-thumb">
          <Thumb src={recipe.thumbnail_url} title={recipe.title} platform={recipe.platform} />
        </div>
        <div>
          <h1>{recipe.title}</h1>
          {recipe.author && <p className="muted">{recipe.author}</p>}
          {recipe.source_url && (
            <a className="btn ghost small" href={recipe.source_url} target="_blank" rel="noreferrer">
              <Icon name="external" size={16} /> Watch on {PLATFORM_NAME[recipe.platform]}
            </a>
          )}
        </div>
      </header>

      <div className="list-toggle">
        <div>
          <strong>On my grocery list</strong>
          <p className="muted">{recipe.ingredients.length} ingredients</p>
        </div>
        <Switch checked={recipe.in_default_list} onChange={toggleList} label="On my grocery list" />
      </div>

      {recipe.estimated && (
        <p className="notice amber">
          <Icon name="sparkle" size={18} />
          This video didn't list its ingredients, so these are typical amounts for this dish. Tap Edit to match the
          video.
        </p>
      )}

      <section>
        <h2>Ingredients{recipe.servings ? <span className="muted"> for {recipe.servings}</span> : null}</h2>
        {recipe.ingredients.length === 0 ? (
          <p className="muted">
            None found in this video. <button className="btn text inline" onClick={() => setEditing(true)}>Add them</button>
          </p>
        ) : (
          <ul className="ingredients">
            {recipe.ingredients.map((i) => (
              <li key={i.id}>
                <span className="amt">{formatAmount(i)}</span>
                <span>{i.name}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {recipe.steps.length > 0 && (
        <section>
          <h2>Method</h2>
          <ol className="steps">
            {recipe.steps.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>
        </section>
      )}

      <button className="btn text danger" onClick={remove}>
        <Icon name="trash" size={16} /> Delete recipe
      </button>
      <p className="muted small">
        <Link to="/list">Go to your grocery list</Link>
      </p>
    </article>
  );
}

interface Row {
  key: number;
  name: string;
  quantity: string;
  unit: string;
  raw_text?: string;
}
let nextKey = 1;
const toRow = (i: Ingredient): Row => ({
  key: nextKey++,
  name: i.name,
  quantity: i.quantity_display ?? String(i.quantity ?? ""),
  unit: i.unit,
  raw_text: i.raw_text,
});

function RecipeEditor({ recipe, onCancel, onSaved }: { recipe: Recipe; onCancel: () => void; onSaved: (r: Recipe) => void }) {
  const [title, setTitle] = useState(recipe.title);
  const [servings, setServings] = useState(recipe.servings ? String(recipe.servings) : "");
  const [rows, setRows] = useState<Row[]>(() => (recipe.ingredients.length ? recipe.ingredients : [{ name: "", quantity: "", unit: "" }]).map(toRow));
  const [steps, setSteps] = useState(recipe.steps.join("\n"));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const update = (key: number, patch: Partial<Row>) => setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await api.saveRecipe(recipe.id, {
        title,
        servings: servings ? Number(servings) : null,
        steps: steps.split("\n").map((s) => s.trim()).filter(Boolean),
        ingredients: rows
          .filter((r) => r.name.trim())
          .map((r) => ({ name: r.name, quantity: r.quantity.trim() || null, unit: r.unit, raw_text: r.raw_text })),
      });
      onSaved(r);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="recipe editor" onSubmit={save}>
      <div className="recipe-top">
        <button type="button" className="btn text" onClick={onCancel}>
          Cancel
        </button>
        <button className="btn primary small" disabled={busy}>
          {busy ? "Saving…" : "Save"}
        </button>
      </div>
      <label className="field">
        <span>Name</span>
        <input value={title} onChange={(e) => setTitle(e.target.value)} required />
      </label>
      <label className="field narrow">
        <span>Serves</span>
        <input type="number" min={1} max={100} value={servings} onChange={(e) => setServings(e.target.value)} />
      </label>

      <h2>Ingredients</h2>
      <div className="edit-rows">
        {rows.map((r) => (
          <div className="edit-row" key={r.key}>
            <input value={r.quantity} onChange={(e) => update(r.key, { quantity: e.target.value })} placeholder="1 1/2" aria-label="Amount" inputMode="decimal" />
            <select value={r.unit} onChange={(e) => update(r.key, { unit: e.target.value })} aria-label="Unit">
              {(UNITS.includes(r.unit) ? UNITS : [...UNITS, r.unit]).map((u) => (
                <option key={u} value={u}>
                  {u || "each"}
                </option>
              ))}
            </select>
            <input value={r.name} onChange={(e) => update(r.key, { name: e.target.value })} placeholder="Ingredient" aria-label="Ingredient" />
            <button type="button" className="icon-btn" onClick={() => setRows((rs) => rs.filter((x) => x.key !== r.key))} aria-label={`Remove ${r.name || "row"}`}>
              <Icon name="close" size={18} />
            </button>
          </div>
        ))}
      </div>
      <button type="button" className="btn ghost small" onClick={() => setRows((rs) => [...rs, toRow({ name: "", quantity: "", unit: "" })])}>
        <Icon name="plus" size={16} /> Add ingredient
      </button>

      <label className="field">
        <span>Method, one step per line</span>
        <textarea rows={6} value={steps} onChange={(e) => setSteps(e.target.value)} />
      </label>
      {error && <p className="notice error">{error}</p>}
    </form>
  );
}
