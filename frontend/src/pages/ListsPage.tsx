import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, GroceryList } from "../api";
import { progress } from "../grocery";

export default function ListsPage() {
  const [lists, setLists] = useState<GroceryList[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.lists().then(setLists).catch((e) => setError(e.message));
  }, []);

  return (
    <>
      <h2>Grocery lists</h2>
      {error && <p className="error">{error}</p>}
      {lists === null ? (
        <p className="muted">Loading…</p>
      ) : lists.length === 0 ? (
        <p className="muted">
          No lists yet. Pick some <Link to="/recipes">recipes</Link> to make one.
        </p>
      ) : (
        <ul className="rows">
          {lists.map((l) => {
            const p = progress(l.items);
            return (
              <li key={l.id} className="row">
                <Link to={`/lists/${l.id}`} className="row-main plain">
                  <strong className="truncate">{l.name}</strong>
                  <span className="muted">
                    {l.recipes.length} recipe{l.recipes.length === 1 ? "" : "s"} · {p.done}/{p.total} items
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
