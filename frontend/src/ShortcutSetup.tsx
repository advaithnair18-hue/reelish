import { useState } from "react";
import { api, User } from "./api";
import { Icon, useToast } from "./ui";

const SHORTCUT_URL = import.meta.env.VITE_SHORTCUT_URL ?? "";

/**
 * Copy text even though the key arrives after an await. Safari only allows clipboard writes
 * during the tap itself, so hand it a ClipboardItem whose content is still loading.
 */
async function copyWhenReady(text: Promise<string>): Promise<boolean> {
  try {
    if (typeof ClipboardItem !== "undefined" && navigator.clipboard?.write) {
      const blob = text.then((t) => new Blob([t], { type: "text/plain" }));
      await navigator.clipboard.write([new ClipboardItem({ "text/plain": blob })]);
      return true;
    }
    await navigator.clipboard.writeText(await text);
    return true;
  } catch {
    return false;
  }
}

/** iPhone: put "Save to Reelish" in the share menu via an Apple Shortcut. */
export default function ShortcutSetup({ user, onChange }: { user: User | null; onChange: (u: User) => void }) {
  const toast = useToast();
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);

  async function getKey() {
    if (user?.has_share_key && !confirm("Make a new key? The shortcut already on your phone will stop working until you reinstall it.")) return;
    setBusy(true);
    const created = api.createShareKey();
    const copied = await copyWhenReady(created.then((r) => r.key));
    try {
      const r = await created;
      setKey(r.key);
      if (user) onChange({ ...user, has_share_key: true, share_key_hint: r.hint });
      toast(copied ? "Key copied" : "Key ready. Tap Copy.");
    } catch (err) {
      toast((err as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function copyAgain() {
    if (await copyWhenReady(Promise.resolve(key))) toast("Key copied");
  }

  async function turnOff() {
    if (!user || !confirm("Turn off the shortcut? It stops saving until you set it up again.")) return;
    await api.revokeShareKey();
    setKey("");
    onChange({ ...user, has_share_key: false, share_key_hint: "" });
    toast("Shortcut turned off");
  }

  return (
    <section className="panel shortcut">
      <div className="shortcut-head">
        <span className="shortcut-badge" aria-hidden="true">
          <Icon name="share" size={22} />
        </span>
        <div>
          <h2>Add Reelish to your share menu</h2>
          <p className="muted">On iPhone, an Apple Shortcut puts "Save to Reelish" in TikTok's share menu. One tap saves the recipe.</p>
        </div>
      </div>

      <ol className="how">
        <li>
          <strong>Get your private key</strong>
          <span>It connects the shortcut to your account. Keep it to yourself.</span>
          <div className="key-row">
            {key ? (
              <>
                <code className="key" aria-label="Your key">{key}</code>
                <button className="btn ghost small" onClick={copyAgain}>
                  Copy
                </button>
              </>
            ) : user?.has_share_key ? (
              <>
                <span className="key-status">
                  <Icon name="check" size={16} /> Key ending {user.share_key_hint} is active
                </span>
                <button className="btn ghost small" onClick={getKey} disabled={busy}>
                  New key
                </button>
              </>
            ) : (
              <button className="btn primary small" onClick={getKey} disabled={busy}>
                {busy ? "Making your key…" : "Copy my key"}
              </button>
            )}
          </div>
        </li>
        <li>
          <strong>Install the shortcut</strong>
          <span>When it asks for your key, paste it.</span>
          <div className="key-row">
            {SHORTCUT_URL ? (
              <a className={`btn small ${key ? "primary" : "ghost"}`} href={SHORTCUT_URL} target="_blank" rel="noreferrer">
                <Icon name="external" size={16} /> Get the shortcut
              </a>
            ) : (
              <span className="muted small">The shortcut link isn't available yet.</span>
            )}
          </div>
        </li>
        <li>
          <strong>Share a recipe</strong>
          <span>
            On a TikTok, tap Share, then More, then Save to Reelish. You'll get a notification when it's on your list. The
            first time, your iPhone asks to let it connect to Reelish: tap Always Allow.
          </span>
        </li>
      </ol>

      <p className="muted small">
        Tip: at the bottom of the share menu, tap Edit Actions and add Save to Reelish to Favorites so it's always near the top.
      </p>
      {user?.has_share_key && (
        <button className="btn text small danger shortcut-off" onClick={turnOff}>
          Turn off the shortcut
        </button>
      )}
    </section>
  );
}
