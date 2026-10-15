"""The iPhone "Save to Reelish" shortcut: private keys and the save endpoint."""
import pytest

from app.services import social

NOODLES = "Garlic butter noodles 🍜\n- 200 g noodles\n- 4 cloves garlic\n- 2 tbsp soy sauce"
RICE = "Fried rice\n- 2 cups rice\n- 2 cloves garlic\n- 2 eggs"
TIKTOK_1 = "https://www.tiktok.com/@chef/video/1"
TIKTOK_2 = "https://www.tiktok.com/@chef/video/2"


@pytest.fixture(autouse=True)
def oembed(monkeypatch):
    posts = {TIKTOK_1: NOODLES, TIKTOK_2: RICE}

    def fake(url, platform, client=None):
        if url not in posts:
            raise social.LinkError("Couldn't read that post (HTTP 404). Is it public?")
        return social.LinkInfo(caption=posts[url], author="@chef")

    monkeypatch.setattr(social, "fetch_link_info", fake)
    return posts


@pytest.fixture
def key(client, auth):
    r = client.post("/api/auth/share-key", headers=auth)
    assert r.status_code == 200
    return r.json()["key"]


def save(client, key, **kwargs):
    return client.post("/api/shortcut/save", headers={"Authorization": f"Bearer {key}"}, **kwargs)


def list_items(client, auth):
    return {i["name"]: i for i in client.get("/api/lists/default", headers=auth).json()["items"]}


# ------------------------------------------------------------------ keys

def test_key_is_shown_once_and_only_its_hint_is_kept(client, auth, key):
    assert key.startswith("rk_") and len(key) > 30
    me = client.get("/api/auth/me", headers=auth).json()
    assert me["has_share_key"] is True and me["share_key_hint"] == key[-4:]
    assert key not in str(me)


def test_new_key_replaces_old_one(client, auth, key):
    new = client.post("/api/auth/share-key", headers=auth).json()["key"]
    assert new != key
    r = save(client, key, json={"url": TIKTOK_1})
    assert r.status_code == 401 and "changed" in r.json()["message"]
    assert save(client, new, json={"url": TIKTOK_1}).status_code == 200


def test_revoked_key_stops_working(client, auth, key):
    assert client.delete("/api/auth/share-key", headers=auth).status_code == 204
    assert client.get("/api/auth/me", headers=auth).json()["has_share_key"] is False
    assert save(client, key, json={"url": TIKTOK_1}).status_code == 401


def test_share_key_needs_login(client):
    assert client.post("/api/auth/share-key").status_code == 401


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer nope"}, {"Authorization": "Bearer rk_madeup"}])
def test_bad_keys_get_a_readable_message(client, headers):
    r = client.post("/api/shortcut/save", headers=headers, json={"url": TIKTOK_1})
    assert r.status_code == 401
    assert r.json()["ok"] is False and "Settings" in r.json()["message"]


def test_login_token_is_not_a_share_key(client, auth):
    r = client.post("/api/shortcut/save", headers=auth, json={"url": TIKTOK_1})
    assert r.status_code == 401


# ------------------------------------------------------------------ saving

def test_share_saves_and_adds_to_list(client, auth, key):
    r = save(client, key, json={"url": TIKTOK_1})
    body = r.json()
    assert r.status_code == 200 and body["ok"] and body["status"] == "done"
    assert body["message"] == "Added Garlic butter noodles 🍜 to your list (3 ingredients)."
    assert list_items(client, auth)["garlic"]["quantity"] == 4


def test_accepts_share_sheet_text_form_and_plain_bodies(client, auth, key):
    # TikTok shares text with the link inside it.
    assert save(client, key, json={"text": f"Check this out! {TIKTOK_1} #food"}).json()["status"] == "done"
    assert save(client, key, data={"url": TIKTOK_2}).json()["status"] == "done"
    assert list_items(client, auth)["garlic"]["quantity"] == 6
    r = client.post("/api/shortcut/save", content=b"https://youtu.be/x",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "text/plain"})
    assert r.status_code == 200  # saved; this fake post just can't be read


def test_x_reelish_key_header_also_works(client, key):
    r = client.post("/api/shortcut/save", headers={"X-Reelish-Key": key}, json={"url": TIKTOK_1})
    assert r.json()["status"] == "done"


def test_sharing_twice_says_already_saved(client, auth, key):
    save(client, key, json={"url": TIKTOK_1})
    r = save(client, key, json={"url": f"again {TIKTOK_1}"}).json()
    assert r["duplicate"] is True and r["message"].startswith("Already saved: Garlic butter noodles")
    assert list_items(client, auth)["garlic"]["quantity"] == 4


@pytest.mark.parametrize("payload", [{"url": "https://example.com/recipe"}, {"text": "no link at all"}, {}])
def test_unsupported_shares_explain_why(client, key, payload):
    r = save(client, key, json=payload)
    assert r.status_code == 422 and r.json()["message"].startswith("Reelish couldn't save that.")


def test_unreadable_post_reports_failure(client, key):
    r = save(client, key, json={"url": "https://www.tiktok.com/@x/video/404"}).json()
    assert r["status"] == "failed" and "couldn't read" in r["message"]


def test_auto_add_off_saves_to_recipes_only(client, auth, key):
    client.patch("/api/auth/me", headers=auth, json={"auto_add": False})
    r = save(client, key, json={"url": TIKTOK_1}).json()
    assert r["message"] == "Saved Garlic butter noodles 🍜 to your recipes."
    assert list_items(client, auth) == {}


def test_keys_are_per_user(client, auth, other_auth, key):
    save(client, key, json={"url": TIKTOK_1})
    other = client.get("/api/lists/default", headers=other_auth).json()
    assert other["items"] == []
