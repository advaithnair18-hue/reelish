// Installable-app plumbing: service worker, install prompt, and the share inbox.
import { useEffect, useState } from "react";

export function registerServiceWorker() {
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        /* the app still works without it, just without share-to-app */
      });
    });
  }
}

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

let deferred: BeforeInstallPromptEvent | null = null;
const listeners = new Set<() => void>();
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  deferred = e as BeforeInstallPromptEvent;
  listeners.forEach((l) => l());
});
window.addEventListener("appinstalled", () => {
  deferred = null;
  listeners.forEach((l) => l());
});

export const isStandalone = () =>
  window.matchMedia("(display-mode: standalone)").matches ||
  (navigator as Navigator & { standalone?: boolean }).standalone === true;

export const isIOS = () => /iphone|ipad|ipod/i.test(navigator.userAgent);

/** Returns a function that shows the browser's install dialog, or null if it isn't available. */
export function useInstall(): (() => Promise<void>) | null {
  const [, force] = useState(0);
  useEffect(() => {
    const l = () => force((n) => n + 1);
    listeners.add(l);
    return () => void listeners.delete(l);
  }, []);
  if (!deferred) return null;
  return async () => {
    await deferred?.prompt();
    deferred = null;
    listeners.forEach((l) => l());
  };
}

export interface IncomingShare {
  title: string;
  text: string;
  url: string;
  file: File | null;
}

const INBOX = "share-inbox";

/**
 * When the user picks Reel Groceries in their phone's share sheet, the service worker
 * stashes what was shared in the Cache API and opens /share. This reads it back out.
 */
export async function takeIncomingShare(): Promise<IncomingShare | null> {
  if (!("caches" in window)) return null;
  const cache = await caches.open(INBOX);
  const meta = await cache.match("/inbox/meta");
  if (!meta) return null;
  const { title = "", text = "", url = "", fileName = "", fileType = "" } = await meta.json();
  const fileRes = await cache.match("/inbox/file");
  const file = fileRes ? new File([await fileRes.blob()], fileName || "shared.mp4", { type: fileType || "video/mp4" }) : null;
  await caches.delete(INBOX);
  return { title, text, url, file };
}

/** Clipboard text, if the browser allows reading it. */
export async function readClipboard(): Promise<string> {
  try {
    return (await navigator.clipboard.readText()).trim();
  } catch {
    return "";
  }
}

export const looksLikeVideoLink = (text: string) =>
  /https?:\/\/[^\s]*(tiktok\.com|instagram\.com|instagr\.am|youtube\.com\/shorts|youtu\.be)/i.test(text);
