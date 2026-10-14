import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, token, User } from "../api";
import { isIOS, isStandalone, useInstall } from "../pwa";
import { Icon, Switch, useToast } from "../ui";

export default function SettingsPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const install = useInstall();
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    api.me().then(setUser).catch(() => {});
  }, []);

  async function setAutoAdd(v: boolean) {
    if (!user) return;
    setUser({ ...user, auto_add: v });
    setUser(await api.updateMe({ auto_add: v }));
    toast(v ? "New recipes go straight to your list" : "New recipes wait for you to add them");
  }

  return (
    <>
      <header className="screen-head">
        <h1>Settings</h1>
      </header>

      <section className="panel">
        <div className="setting">
          <div>
            <strong>Add new recipes to my list</strong>
            <p className="muted">When a shared video is ready, its ingredients go straight onto your grocery list.</p>
          </div>
          <Switch checked={user?.auto_add ?? true} onChange={setAutoAdd} label="Add new recipes to my list" />
        </div>
      </section>

      <section className="panel">
        <h2>Share from TikTok and Instagram</h2>
        {isStandalone() ? (
          <p className="notice ok">
            <Icon name="check" size={18} /> Reelish is installed.
          </p>
        ) : install ? (
          <>
            <p>Install the app first, so it appears in your phone's share sheet.</p>
            <button className="btn primary" onClick={install}>
              Install Reelish
            </button>
          </>
        ) : null}

        {isIOS() ? (
          <ol className="how">
            <li>
              <strong>Add to Home Screen</strong>
              <span>In Safari, tap the Share button, then Add to Home Screen.</span>
            </li>
            <li>
              <strong>Copy the video's link</strong>
              <span>On the video, tap Share, then Copy link.</span>
            </li>
            <li>
              <strong>Open Reelish and tap Paste</strong>
              <span>iPhone doesn't let web apps join the share sheet, so pasting is the quickest way.</span>
            </li>
          </ol>
        ) : (
          <ol className="how">
            <li>
              <strong>On the video, tap Share</strong>
              <span>In TikTok, Instagram or YouTube.</span>
            </li>
            <li>
              <strong>Choose Reelish</strong>
              <span>If you don't see it, tap More or Other apps.</span>
            </li>
            <li>
              <strong>That's it</strong>
              <span>The recipe saves and its ingredients go on your list.</span>
            </li>
          </ol>
        )}
      </section>

      <section className="panel">
        <div className="setting">
          <div>
            <strong>Account</strong>
            <p className="muted">{user?.email ?? "…"}</p>
          </div>
          <button
            className="btn ghost small"
            onClick={() => {
              token.clear();
              navigate("/welcome");
            }}
          >
            Log out
          </button>
        </div>
      </section>
    </>
  );
}
