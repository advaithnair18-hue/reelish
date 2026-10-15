/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** iCloud link to the "Save to Reelish" shortcut (see docs/ios-shortcut.md). */
  readonly VITE_SHORTCUT_URL?: string;
}
