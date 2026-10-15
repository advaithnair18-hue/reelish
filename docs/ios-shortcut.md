# Build the "Save to Reelish" iPhone shortcut

iPhones only let App Store apps put their own icon in the share menu, but any Apple Shortcut can appear there too. This shortcut takes whatever you share from TikTok, Instagram or YouTube, sends it to Reelish with your private key, and shows a notification like *"Added Garlic butter noodles to your list (6 ingredients)."* You never copy a link or open the app.

You build it **once**, on your own iPhone, then share its iCloud link. Everyone else installs it in one tap from Reelish → Settings and pastes their own key when asked.

Before you start, deploy Reelish so it has a public **https** address (the shortcut can't reach `localhost`). Below, `https://your-domain` means that address.

---

## 1. Create the shortcut

1. Open the **Shortcuts** app and tap **+** to make a new shortcut.
2. Tap the name at the top, choose **Rename**, and call it **Save to Reelish**.
3. Tap the name again, choose **Choose Icon**, and pick a colour and glyph (a shopping bag works well).

## 2. Make it appear in the share menu

1. Open the shortcut's details: tap the **ⓘ** button at the bottom of the editor (on some iOS versions it's under the name menu → **Details**).
2. Turn on **Show in Share Sheet**, then tap **Done**.
3. A block appears at the top: *"Receive **Any** input from **Share Sheet**"*. Tap **Any**, choose **Clear**, then select only **URLs** and **Text**.
4. In the same block, set *"If there's no input"* to **Stop and Respond**.

## 3. Add the actions

Search for each action with the search bar at the bottom and add them in this order.

**Action 1: Text**
Type the placeholder `PASTE_YOUR_KEY_HERE`. Don't put your real key here; everyone who installs the shortcut will be asked for their own (step 4).

**Action 2: Get Contents of URL**
- URL: `https://your-domain/api/shortcut/save`
- Tap **Show More** (the arrow), then:
  - **Method:** POST
  - **Headers:** tap **Add new header**. Key: `Authorization`. Value: type `Bearer ` (with the space), then tap the variable bar above the keyboard and insert **Text** (the output of action 1).
  - **Request Body:** JSON. Tap **Add new field** → **Text**. Key: `text`. Value: insert the **Shortcut Input** variable.

**Action 3: Get Dictionary Value**
Set it to *Get **Value** for **message** in **Contents of URL***.

**Action 4: Show Notification**
Tap the message area and insert **Dictionary Value**. Turn off **Play Sound** if you prefer it silent.

The finished shortcut reads:

```
Receive URLs and Text from Share Sheet  (if no input: Stop and Respond)
Text: PASTE_YOUR_KEY_HERE
Get Contents of URL  https://your-domain/api/shortcut/save
    Method POST · Header Authorization: Bearer [Text] · JSON { text: [Shortcut Input] }
Get Value for "message" in [Contents of URL]
Show Notification [Dictionary Value]
```

## 4. Ask each person for their key when they install it

1. Open the shortcut's details again (**ⓘ**) and go to the **Setup** tab (called **Import Questions** on some versions).
2. Tap **Add Question** and pick the **Text** action's content (`PASTE_YOUR_KEY_HERE`).
3. Set the question to: **Paste your Reelish key (Reelish → Settings → Copy my key)**.
4. Leave the default answer as the placeholder.

## 5. Test it with your own key

1. In Reelish, go to **Settings → Add Reelish to your share menu → Copy my key**.
2. Temporarily replace `PASTE_YOUR_KEY_HERE` in action 1 with your key.
3. Open a recipe on TikTok, tap **Share → More → Save to Reelish**. The first time, iPhone asks whether the shortcut may connect to your domain: tap **Always Allow**.
4. You should get a notification, and the ingredients should be on your list.
5. **Put the placeholder back** before sharing the shortcut, so your key isn't sent to anyone.

## 6. Share it and connect it to the app

1. In the Shortcuts app, long-press **Save to Reelish** → **Share** → **Copy iCloud Link**.
2. In `frontend/.env` (create it if needed), add the link:
   ```
   VITE_SHORTCUT_URL=https://www.icloud.com/shortcuts/xxxxxxxxxxxxxxxx
   ```
3. Rebuild and redeploy the frontend. The **Get the shortcut** button in Settings now opens your shortcut.

If you change the shortcut later, share it again; iCloud gives a new link each time, so update `VITE_SHORTCUT_URL`.

---

## What users see

1. **Reelish → Settings → Copy my key.**
2. **Get the shortcut → Add Shortcut**, then paste the key when asked.
3. On any recipe video: **Share → More → Save to Reelish.** A notification confirms what was added.

Tip for users: at the bottom of the share menu, **Edit Actions** → add **Save to Reelish** to **Favorites** to keep it near the top.

## How the endpoint behaves

`POST /api/shortcut/save` takes the shared text as JSON (`text`, `url` or `input`), a form, or a plain-text body. The key goes in `Authorization: Bearer rk_…` (or an `X-Reelish-Key` header). It waits up to `SHORTCUT_WAIT_SECONDS` (default 12) for the recipe, so the notification can say what was added. It always answers with JSON containing a `message` the shortcut can show as-is:

| Situation | Notification |
| --- | --- |
| Saved and added | Added Garlic butter noodles to your list (6 ingredients). |
| AI-estimated amounts | …(6 ingredients). Check the amounts. |
| Still processing | Saved to Reelish. The ingredients will be on your list in a moment. |
| Shared before | Already saved: Garlic butter noodles. |
| Not a video link | Reelish couldn't save that. Share a TikTok, Instagram Reel or YouTube Short. |
| Key wrong or replaced | Your Reelish key has changed. Reinstall the shortcut from Reelish → Settings. |

Keys are stored hashed. **New key** in Settings replaces the old one, and **Turn off the shortcut** revokes it.
