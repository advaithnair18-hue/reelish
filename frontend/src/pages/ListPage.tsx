import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, GroceryItem, GroceryList } from "../api";
import { formatAmount, groupByAisle, progress } from "../grocery";

export default function ListPage() {
  const { id } = useParams();
  const listId = Number(id);
  const navigate = useNavigate();
  const [list, setList] = useState<GroceryList | null>(null);
  const [hideHave, setHideHave] = useState(false);
  const [newItem, setNewItem] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api.list(listId).then(setList).catch((e) => setError(e.message));
  }, [listId]);

  // Optimistic update: tick instantly, roll back if the server says no.
  async function patch(item: GroceryItem, change: Partial<Pick<GroceryItem, "checked" | "have_already">>) {
    if (!list) return;
    const apply = (it: GroceryItem) => setList((l) => l && { ...l, items: l.items.map((x) => (x.id === it.id ? it : x)) });
    apply({ ...item, ...change });
    try {
      apply(await api.updateItem(listId, item.id, change));
    } catch (err) {
      apply(item);
      setError((err as Error).message);
    }
  }

  async function add(e: FormEvent) {
    e.preventDefault();
    if (!newItem.trim()) return;
    const item = await api.addItem(listId, newItem.trim());
    setList((l) => l && { ...l, items: [...l.items, item] });
    setNewItem("");
  }

  async function remove() {
    if (!confirm("Delete this list?")) return;
    await api.deleteList(listId);
    navigate("/lists");
  }

  if (!list) return <p className={error ? "error" : "muted"}>{error || "Loading…"}</p>;
  const p = progress(list.items);

  return (
    <>
      <div className="page-head">
        <h2>{list.name}</h2>
        <button className="small danger ghost" onClick={remove}>
          Delete
        </button>
      </div>
      <p className="muted">
        From{" "}
        {list.recipes.map((r, i) => (
          <span key={r.id}>
            {i > 0 && ", "}
            <Link to={`/recipes/${r.id}`}>{r.title}</Link>
          </span>
        ))}
      </p>

      <div className="progress" aria-label={`${p.done} of ${p.total} items`}>
        <div style={{ width: `${p.total ? (100 * p.done) / p.total : 0}%` }} />
      </div>
      <div className="toolbar">
        <span className="muted">
          {p.done} of {p.total} in the cart
        </span>
        <label className="toggle">
          <input type="checkbox" checked={hideHave} onChange={(e) => setHideHave(e.target.checked)} />
          Hide what I have
        </label>
      </div>
      {error && <p className="error">{error}</p>}

      {groupByAisle(list.items, hideHave).map((g) => (
        <section key={g.aisle} className="aisle">
          <h4>{g.aisle}</h4>
          <ul>
            {g.items.map((it) => (
              <li key={it.id} className={`item ${it.checked ? "checked" : ""} ${it.have_already ? "have" : ""}`}>
                <label>
                  <input type="checkbox" checked={it.checked} disabled={it.have_already} onChange={() => patch(it, { checked: !it.checked })} />
                  <span className="item-name">{it.name}</span>
                  <span className="item-amount">{formatAmount(it)}</span>
                </label>
                <button className="chip" onClick={() => patch(it, { have_already: !it.have_already })}>
                  {it.have_already ? "Need it" : "Have it"}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}

      <form onSubmit={add} className="add-item">
        <input value={newItem} onChange={(e) => setNewItem(e.target.value)} placeholder="Add something else (coffee, paper towels…)" />
        <button className="small">Add</button>
      </form>
    </>
  );
}
