import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, Video } from "../api";

const POLL_MS = 2000;

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [caption, setCaption] = useState("");
  const [videos, setVideos] = useState<Video[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(() => api.videos().then(setVideos).catch((e) => setError(e.message)), []);
  useEffect(() => {
    load();
  }, [load]);

  // Poll only while something is still in the queue.
  const pending = videos.some((v) => v.status === "uploaded" || v.status === "processing");
  useEffect(() => {
    if (!pending) return;
    const t = setInterval(load, POLL_MS);
    return () => clearInterval(t);
  }, [pending, load]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const v = await api.uploadVideo(file, caption);
      setVideos((vs) => [v, ...vs]);
      setFile(null);
      setCaption("");
      if (inputRef.current) inputRef.current.value = "";
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <section className="card">
        <h2>Add a recipe video</h2>
        <p className="muted">
          Save the TikTok or Reel to your phone, then upload it here. Pasting the caption helps a lot: creators often
          list the ingredients there.
        </p>
        <form onSubmit={submit} className="stack">
          <label
            className={`dropzone ${file ? "has-file" : ""}`}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const f = e.dataTransfer.files[0];
              if (f) setFile(f);
            }}
          >
            <input
              ref={inputRef}
              type="file"
              accept="video/mp4,video/quicktime,video/webm,.mp4,.mov,.m4v,.webm,.mkv"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            {file ? (
              <span>
                🎬 <strong>{file.name}</strong> · {(file.size / 1024 / 1024).toFixed(1)} MB
              </span>
            ) : (
              <span>Drop a video here, or tap to choose</span>
            )}
          </label>
          <label>
            <span>
              Caption <span className="muted">(optional)</span>
            </span>
            <textarea
              rows={4}
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              placeholder={"Garlic butter noodles 🍜\n- 200g noodles\n- 4 cloves garlic…"}
            />
          </label>
          {error && <p className="error">{error}</p>}
          <button className="primary" disabled={!file || busy}>
            {busy ? "Uploading…" : "Extract recipe"}
          </button>
        </form>
      </section>

      <section>
        <h3>Recent uploads</h3>
        {videos.length === 0 && <p className="muted">Nothing yet. Your first upload will show up here.</p>}
        <ul className="rows">
          {videos.map((v) => (
            <VideoRow key={v.id} video={v} onChange={load} />
          ))}
        </ul>
      </section>
    </>
  );
}

function VideoRow({ video, onChange }: { video: Video; onChange: () => void }) {
  const [caption, setCaption] = useState(video.caption);
  const [retrying, setRetrying] = useState(false);

  async function retry() {
    setRetrying(true);
    try {
      await api.retryVideo(video.id, caption);
      onChange();
    } finally {
      setRetrying(false);
    }
  }

  return (
    <li className="row video-row">
      <div className="row-main">
        <span className={`badge ${video.status}`}>{video.status === "uploaded" ? "queued" : video.status}</span>
        <span className="truncate">{video.original_filename || `Video #${video.id}`}</span>
        {video.status === "done" && video.recipe_id && (
          <Link className="button small" to={`/recipes/${video.recipe_id}`}>
            Review recipe →
          </Link>
        )}
      </div>
      {video.error && <p className={video.status === "failed" ? "error" : "warn"}>{video.error}</p>}
      {video.status === "failed" && (
        <div className="stack">
          <textarea rows={3} value={caption} onChange={(e) => setCaption(e.target.value)} placeholder="Paste the caption…" />
          <button className="small" onClick={retry} disabled={retrying}>
            Retry with this caption
          </button>
        </div>
      )}
    </li>
  );
}
