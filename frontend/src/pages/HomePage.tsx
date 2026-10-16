import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, RecipeSummary, Video } from "../api";
import { isIOS, isStandalone, looksLikeVideoLink, readClipboard, useInstall } from "../pwa";
import { Icon, PLATFORM_NAME, Thumb, useToast } from "../ui";

const POLL_MS = 1500;

export default function HomePage() {
  const toast = useToast();
  const [recipes, setRecipes] = useState<RecipeSummary[] | null>(null);
  const [pending, setPending] = useState<Video[]>([]);
  const [link, setLink] = useState("");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const known = useRef<Map<number, Video["status"]>>(new Map());

  const load = useCallback(async () => {
    const [r, v] = await Promise.all([api.recipes(), api.videos()]);
    setRecipes(r);
    // Announce videos that just finished while we were watching.
    for (const video of v) {
      const before = known.current.get(video.id);
      if (before && before !== "done" && video.status === "done") {
        const recipe = r.find((x) => x.id === video.recipe_id);
        if (recipe?.in_default_list) toast(`Added ${recipe.title} to your list`);
      }
      known.current.set(video.id, video.status);
    }
    setPending(v.filter((x) => x.status !== "done"));
  }, [toast]);

  useEffect(() => {
    load().catch(() => setRecipes([]));
  }, [load]);

  const working = pending.some((v) => v.status === "uploaded" || v.status === "processing");
  useEffect(() => {
    if (!working) return;
    const t = setInterval(() => load().catch(() => {}), POLL_MS);
    return () => clearInterval(t);
  }, [working, load]);

  async function save(e?: FormEvent, text = link) {
    e?.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    try {
      const v = await api.shareLink(text.trim());
      known.current.set(v.id, v.status);
      setLink("");
      await load();
    } catch (err) {
      toast((err as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function paste() {
    const text = await readClipboard();
    if (!text) {
      toast("Couldn't read the clipboard. Long-press the box and paste instead.", "error");
      return;
    }
    if (!looksLikeVideoLink(text)) {
      setLink(text);
      toast("That isn't a TikTok, Reel or Short link", "error");
      return;
    }
    // A video link: save it straight away, so on iPhone it's copy link → open → Paste.
    await save(undefined, text);
  }

  async function upload(file: File) {
    setBusy(true);
    try {
      const v = await api.uploadVideo(file);
      known.current.set(v.id, v.status);
      await load();
    } catch (err) {
      toast((err as Error).message, "error");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  const empty = recipes !== null && recipes.length === 0 && pending.length === 0;

  return (
    <>
      <header className="screen-head">
        <h1>Recipes</h1>
      </header>

      <form className="saver" onSubmit={save}>
        <div className="saver-input">
          <Icon name="link" size={20} />
          <input
            value={link}
            onChange={(e) => setLink(e.target.value)}
            placeholder="Paste a TikTok, Reel or Short link"
            inputMode="url"
            aria-label="Video link"
          />
          {!link && (
            <button type="button" className="chip-btn" onClick={paste}>
              Paste
            </button>
          )}
        </div>
        <div className="saver-actions">
          <button className="btn primary" disabled={!link.trim() || busy}>
            Save recipe
          </button>
          <label className="btn ghost">
            <Icon name="upload" size={18} />
            Upload video
            <input ref={fileRef} type="file" accept="video/*" hidden onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          </label>
        </div>
      </form>

      <InstallNudge />

      {empty && <EmptyState />}

      {(pending.length > 0 || (recipes && recipes.length > 0)) && (
        <section className="grid" aria-label="Your recipes">
          {pending.map((v) => (
            <PendingCard key={`v${v.id}`} video={v} onRetry={load} />
          ))}
          {recipes?.map((r) => <RecipeCard key={r.id} recipe={r} />)}
        </section>
      )}
    </>
  );
}

function RecipeCard({ recipe }: { recipe: RecipeSummary }) {
  return (
    <Link to={`/recipes/${recipe.id}`} className="card">
      <Thumb src={recipe.thumbnail_url} title={recipe.title} platform={recipe.platform} />
      <div className="card-shade" />
      <div className="card-body">
        {recipe.ingredient_count === 0 ? (
          <span className="sticker amber">No ingredients yet</span>
        ) : recipe.estimated ? (
          <span className="sticker amber">Check amounts</span>
        ) : recipe.in_default_list ? (
          <span className="sticker lime">On your list</span>
        ) : null}
        <h3>{recipe.title}</h3>
        <p>
          {recipe.ingredient_count} ingredient{recipe.ingredient_count === 1 ? "" : "s"}
        </p>
        {recipe.author && <p className="card-author">{recipe.author}</p>}
      </div>
    </Link>
  );
}

function PendingCard({ video, onRetry }: { video: Video; onRetry: () => void }) {
  const toast = useToast();
  const [caption, setCaption] = useState("");
  const failed = video.status === "failed";
  const label = video.platform ? PLATFORM_NAME[video.platform] : video.original_filename || "Video";

  async function retry() {
    try {
      await api.retryVideo(video.id, caption);
      onRetry();
    } catch (err) {
      toast((err as Error).message, "error");
    }
  }

  async function remove() {
    await api.deleteVideo(video.id);
    onRetry();
  }

  if (failed) {
    return (
      <div className="card failed">
        <div className="card-failed">
          <strong>Couldn't read this {label}</strong>
          <p>{video.error}</p>
          <textarea rows={3} value={caption} onChange={(e) => setCaption(e.target.value)} placeholder="Paste the caption here" />
          <div className="row-gap">
            <button className="btn primary small" onClick={retry} disabled={!caption.trim()}>
              Try again
            </button>
            <button className="btn text small" onClick={remove}>
              Remove
            </button>
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="card loading" aria-busy="true">
      {video.thumbnail_url ? <Thumb src={video.thumbnail_url} title={label} platform={video.platform} /> : <div className="thumb shimmer" />}
      <div className="card-shade" />
      <div className="card-body">
        <span className="sticker dark">
          <span className="dot" /> Reading the video
        </span>
        <h3>{label}</h3>
        <p>Finding the ingredients…</p>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <section className="empty">
      <h2>Your first recipe is one share away</h2>
      <ol className="how">
        <li>
          <strong>Find a recipe video</strong>
          <span>On TikTok, Instagram or YouTube Shorts.</span>
        </li>
        <li>
          <strong>Tap Share, then Reelish</strong>
          <span>On iPhone, set up Save to Reelish in Settings, or copy the link and paste it above.</span>
        </li>
        <li>
          <strong>Open your list</strong>
          <span>The ingredients are already there, sorted by aisle.</span>
        </li>
      </ol>
    </section>
  );
}

function InstallNudge() {
  const install = useInstall();
  const [hidden, setHidden] = useState(() => {
    try {
      return localStorage.getItem("rg_hide_install") === "1";
    } catch {
      return false;
    }
  });
  if (hidden || isStandalone() || (!install && !isIOS())) return null;
  const dismiss = () => {
    try {
      localStorage.setItem("rg_hide_install", "1");
    } catch {
      /* ignore */
    }
    setHidden(true);
  };
  return (
    <div className="nudge">
      <img src="/icons/icon-192.png" alt="" />
      <div>
        <strong>Add Reelish to your home screen</strong>
        <p>{install ? "Then it shows up when you tap Share on a video." : "Tap the Share button in Safari, then Add to Home Screen."}</p>
      </div>
      {install ? (
        <button className="btn primary small" onClick={install}>
          Install
        </button>
      ) : null}
      <button className="icon-btn" onClick={dismiss} aria-label="Dismiss">
        <Icon name="close" size={18} />
      </button>
    </div>
  );
}
