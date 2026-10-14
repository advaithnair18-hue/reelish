import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, GroceryItem, GroceryList } from "../api";
import { formatAmount, groupByAisle, progress } from "../grocery";
import { Icon, Thumb, useToast } from "../ui";

export default function ListPage() {
  const toast = useToast();
  const [list, setList] = useState<GroceryList | null>(null);
  const [hideHave, setHideHave] = useState(false);
  const [newItem, setNewItem] = useState("");
  const [menu, setMenu] = useState(false);

  useEffect(() => {
    api.defaultList().then(setList).catch((e) => toast(e.message, "error"));
  }, [toast]);

  // Optimistic: tick instantly, roll back if the server says no.
  async function patch(item: GroceryItem, change: Partial<Pick<GroceryItem, "checked" | "have_already">>) {
    if (!list) return;
    const apply = (it: GroceryItem) => setList((l) => l && { ...l, items: l.items.map((x) => (x.id === it.id ? it : x)) });
    apply({ ...item, ...change });
    try {
      apply(await api.updateItem(list.id, item.id, change));
    } catch (err) {
      apply(item);
      toast((err as Error).message, "error");
    }
  }

  async function add(e: FormEvent) {
    e.preventDefault();
    if (!list || !newItem.trim()) return;
    const item = await api.addItem(list.id, newItem.trim());
    setList({ ...list, items: [...list.items, item] });
    setNewItem("");
  }

  async function removeItem(item: GroceryItem) {
    if (!list) return;
    await api.deleteItem(list.id, item.id);
    setList({ ...list, items: list.items.filter((i) => i.id !== item.id) });
  }

  async function removeRecipe(recipeId: number, title: string) {
    if (!list) return;
    setList(await api.removeRecipeFromList(list.id, recipeId));
    toast(`Removed ${title}`);
  }

  async function run(action: "reset" | "clear") {
    if (!list) return;
    setMenu(false);
    if (action === "clear" && !confirm("Empty the list? Your saved recipes stay.")) return;
    setList(action === "reset" ? await api.resetList(list.id) : await api.clearList(list.id));
    toast(action === "reset" ? "Unticked everything" : "List emptied");
  }

  if (!list) return <p className="muted pad">Loading…</p>;
  const p = progress(list.items);
  const groups = groupByAisle(list.items, hideHave);
  const allDone = p.total > 0 && p.done === p.total;

  return (
    <>
      <header className="screen-head">
        <h1>Grocery list</h1>
        <div className="menu-wrap">
          <button className="icon-btn" onClick={() => setMenu(!menu)} aria-label="List options" aria-expanded={menu}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <circle cx="5" cy="12" r="2" />
              <circle cx="12" cy="12" r="2" />
              <circle cx="19" cy="12" r="2" />
            </svg>
          </button>
          {menu && (
            <div className="menu" role="menu">
              <button role="menuitem" onClick={() => run("reset")}>
                <Icon name="refresh" size={18} /> Untick everything
              </button>
              <button role="menuitem" className="danger" onClick={() => run("clear")}>
                <Icon name="trash" size={18} /> Empty the list
              </button>
            </div>
          )}
        </div>
      </header>

      {list.items.length === 0 ? (
        <section className="empty">
          <h2>Nothing to buy yet</h2>
          <p className="muted">Share a recipe video to Reelish and its ingredients appear here.</p>
          <Link to="/" className="btn primary">
            Save a recipe
          </Link>
        </section>
      ) : (
        <>
          <div className={`tally ${allDone ? "done" : ""}`}>
            <div className="tally-num">
              <strong>{p.done}</strong>
              <span>of {p.total}</span>
            </div>
            <div className="tally-bar" aria-hidden="true">
              <div style={{ width: `${p.total ? (100 * p.done) / p.total : 0}%` }} />
            </div>
            <span className="tally-label">{allDone ? "All in the cart" : "in the cart"}</span>
          </div>

          {list.recipes.length > 0 && (
            <div className="from-recipes" aria-label="Recipes on this list">
              {list.recipes.map((r) => (
                <div key={r.id} className="recipe-chip">
                  <Link to={`/recipes/${r.id}`}>
                    <Thumb src={r.thumbnail_url} title={r.title} platform={r.platform} />
                    <span>{r.title}</span>
                  </Link>
                  <button className="icon-btn" onClick={() => removeRecipe(r.id, r.title)} aria-label={`Remove ${r.title} from list`}>
                    <Icon name="close" size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}

          <label className="hide-have">
            <input type="checkbox" checked={hideHave} onChange={(e) => setHideHave(e.target.checked)} />
            Hide things I have at home
          </label>

          {groups.map((g) => (
            <section key={g.aisle} className="aisle">
              <h2>{g.aisle}</h2>
              <ul>
                {g.items.map((it) => (
                  <li key={it.id} className={`item ${it.checked ? "checked" : ""} ${it.have_already ? "have" : ""}`}>
                    <button
                      className="tick"
                      role="checkbox"
                      aria-checked={it.checked}
                      aria-label={it.name}
                      disabled={it.have_already}
                      onClick={() => patch(it, { checked: !it.checked })}
                    >
                      <Icon name="check" size={16} />
                    </button>
                    <span className="item-name">{it.name}</span>
                    <span className="item-amount">{it.have_already ? "at home" : formatAmount(it)}</span>
                    {it.custom ? (
                      <button className="icon-btn quiet" onClick={() => removeItem(it)} aria-label={`Delete ${it.name}`}>
                        <Icon name="close" size={16} />
                      </button>
                    ) : (
                      <button
                        className={`icon-btn quiet ${it.have_already ? "active" : ""}`}
                        onClick={() => patch(it, { have_already: !it.have_already, checked: false })}
                        aria-label={it.have_already ? `I need ${it.name}` : `I have ${it.name} at home`}
                        aria-pressed={it.have_already}
                      >
                        <Icon name="home" size={18} />
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </>
      )}

      <form onSubmit={add} className="add-item">
        <input value={newItem} onChange={(e) => setNewItem(e.target.value)} placeholder="Add something else, like coffee" aria-label="Add an item" />
        <button className="btn primary small" disabled={!newItem.trim()}>
          Add
        </button>
      </form>
    </>
  );
}
