import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, Recipe, Video } from "../api";
import { takeIncomingShare } from "../pwa";
import { formatAmount } from "../grocery";
import { Icon, PLATFORM_NAME, Thumb } from "../ui";

type Phase =
  | { kind: "receiving" }
  | { kind: "reading"; video: Video }
  | { kind: "done"; video: Video; recipe: Recipe }
  | { kind: "failed"; message: string; video?: Video };

const POLL_MS = 1200;

/**
 * Opened by the phone's share sheet (via the service worker), or by a link like
 * /share?url=https://www.tiktok.com/... (handy for an iPhone Shortcut).
 */
export default function SharePage() {
  const [params] = useSearchParams();
  const [phase, setPhase] = useState<Phase>({ kind: "receiving" });
  const [caption, setCaption] = useState("");
  const started = useRef(false);

  async function follow(video: Video) {
    setPhase({ kind: "reading", video });
    for (;;) {
      if (video.status === "done" && video.recipe_id) {
        setPhase({ kind: "done", video, recipe: await api.recipe(video.recipe_id) });
        return;
      }
      if (video.status === "failed") {
        setPhase({ kind: "failed", message: video.error, video });
        return;
      }
      await new Promise((r) => setTimeout(r, POLL_MS));
      video = await api.video(video.id);
      setPhase({ kind: "reading", video });
    }
  }

  useEffect(() => {
    if (started.current) return; // StrictMode runs effects twice in dev
    started.current = true;
    (async () => {
      try {
        const incoming = params.get("incoming") ? await takeIncomingShare() : null;
        const text = [incoming?.url, incoming?.text, incoming?.title, params.get("url"), params.get("text")]
          .filter(Boolean)
          .join(" ");
        let video: Video;
        if (incoming?.file) video = await api.uploadVideo(incoming.file, incoming.text || incoming.title);
        else if (text.trim()) video = await api.shareLink(text);
        else throw new Error("Nothing came through. Try sharing the video again, or paste its link in the app.");
        await follow(video);
      } catch (err) {
        setPhase({ kind: "failed", message: (err as Error).message });
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function retry() {
    if (phase.kind !== "failed" || !phase.video) return;
    try {
      await follow(await api.retryVideo(phase.video.id, caption));
    } catch (err) {
      setPhase({ kind: "failed", message: (err as Error).message, video: phase.video });
    }
  }

  return (
    <div className="share">
      {phase.kind === "receiving" && (
        <div className="share-card">
          <div className="pulse-ring" />
          <h1>Saving the recipe</h1>
        </div>
      )}

      {phase.kind === "reading" && (
        <div className="share-card">
          <div className="share-thumb reading">
            {phase.video.thumbnail_url ? (
              <Thumb src={phase.video.thumbnail_url} title={phase.video.author || "Video"} platform={phase.video.platform} />
            ) : (
              <div className="thumb shimmer" />
            )}
            <div className="scanline" />
          </div>
          <h1>Reading the ingredients</h1>
          <p className="muted">
            {phase.video.platform ? `From ${PLATFORM_NAME[phase.video.platform]}` : "From your video"}
            {phase.video.author ? `, ${phase.video.author}` : ""}
          </p>
        </div>
      )}

      {phase.kind === "done" && (
        <div className="share-card">
          <div className="share-thumb">
            <Thumb src={phase.recipe.thumbnail_url} title={phase.recipe.title} platform={phase.recipe.platform} />
            <span className="share-check">
              <Icon name="check" size={28} />
            </span>
          </div>
          <h1>{phase.recipe.in_default_list ? "On your list" : "Recipe saved"}</h1>
          <p className="share-title">{phase.recipe.title}</p>
          {phase.recipe.ingredients.length > 0 ? (
            <ul className="share-ings">
              {phase.recipe.ingredients.slice(0, 6).map((i) => (
                <li key={i.id}>
                  <span className="amt">{formatAmount(i)}</span> {i.name}
                </li>
              ))}
              {phase.recipe.ingredients.length > 6 && <li className="muted">and {phase.recipe.ingredients.length - 6} more</li>}
            </ul>
          ) : (
            <p className="notice amber">No ingredients in this one. Add them from the recipe page.</p>
          )}
          {phase.recipe.estimated && <p className="notice amber">Typical amounts for this dish. Check them against the video.</p>}
          <div className="share-actions">
            <Link to="/list" className="btn primary big">
              Open my list
            </Link>
            <Link to={`/recipes/${phase.recipe.id}`} className="btn ghost">
              See the recipe
            </Link>
          </div>
        </div>
      )}

      {phase.kind === "failed" && (
        <div className="share-card">
          <h1>Couldn't save that one</h1>
          <p className="notice error">{phase.message}</p>
          {phase.video && (
            <>
              <textarea rows={4} value={caption} onChange={(e) => setCaption(e.target.value)} placeholder="Paste the video's caption here" />
              <button className="btn primary big" onClick={retry} disabled={!caption.trim()}>
                Try again with this caption
              </button>
            </>
          )}
          <Link to="/" className="btn ghost">
            Go to my recipes
          </Link>
        </div>
      )}
    </div>
  );
}
