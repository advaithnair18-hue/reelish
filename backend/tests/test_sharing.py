"""Share-a-link flow, the auto-updating default list, and estimated ingredients."""
import httpx
import pytest

from app.services import social
from app.services.extraction import ExtractedIngredient, ExtractedRecipe, extract_recipe

NOODLES = "Garlic butter noodles 🍜\n- 200 g noodles\n- 4 cloves garlic\n- 2 tbsp soy sauce"
RICE = "Fried rice\n- 2 cups rice\n- 2 cloves garlic\n- 1 tbsp soy sauce\n- 2 eggs"


@pytest.fixture
def oembed(monkeypatch):
    """Fake the platforms' oEmbed responses, keyed by URL."""
    posts = {}

    def fake(url, platform, client=None):
        if platform == "instagram":
            return social.LinkInfo()  # like the real thing without a Meta token
        if url not in posts:
            raise social.LinkError("Couldn't read that post (HTTP 404). Is it public?")
        return social.LinkInfo(caption=posts[url], author="@chef",
                               thumbnail_url=f"https://cdn.example/{len(url)}.jpg")

    monkeypatch.setattr(social, "fetch_link_info", fake)
    return posts


def share(client, auth, text, caption=""):
    return client.post("/api/videos/link", headers=auth, json={"url": text, "caption": caption})


def default_list(client, auth):
    return client.get("/api/lists/default", headers=auth).json()


def items(gl):
    return {i["name"]: i for i in gl["items"]}


# ------------------------------------------------------------------ link parsing

@pytest.mark.parametrize("text,url", [
    ("https://www.tiktok.com/@chef/video/123", "https://www.tiktok.com/@chef/video/123"),
    ("Check this out! https://vm.tiktok.com/ZMabc/ so good", "https://vm.tiktok.com/ZMabc/"),
    ("https://www.instagram.com/reel/Cxyz/?igsh=1.", "https://www.instagram.com/reel/Cxyz/?igsh=1"),
    ("no link here", None),
])
def test_find_url(text, url):
    assert social.find_url(text) == url


@pytest.mark.parametrize("url,platform", [
    ("https://www.tiktok.com/@a/video/1", "tiktok"), ("https://vm.tiktok.com/x", "tiktok"),
    ("https://www.instagram.com/reel/abc", "instagram"), ("https://youtu.be/abc", "youtube"),
    ("https://youtube.com/shorts/abc", "youtube"),
])
def test_detect_platform(url, platform):
    assert social.detect_platform(url) == platform


@pytest.mark.parametrize("url", ["https://evil-tiktok.com/x", "https://example.com", "ftp://tiktok.com/x"])
def test_detect_platform_rejects_lookalikes(url):
    with pytest.raises(social.LinkError):
        social.detect_platform(url)


def test_fetch_link_info_reads_tiktok_oembed():
    def handler(request: httpx.Request):
        assert request.url.host == "www.tiktok.com" and request.url.path == "/oembed"
        assert request.url.params["url"] == "https://www.tiktok.com/@a/video/1"
        return httpx.Response(200, json={"title": "Pasta - 2 cups penne", "author_name": "Chef A",
                                         "thumbnail_url": "https://p16.tiktokcdn.com/t.jpg"})

    info = social.fetch_link_info("https://www.tiktok.com/@a/video/1", "tiktok",
                                  httpx.Client(transport=httpx.MockTransport(handler)))
    assert (info.caption, info.author) == ("Pasta - 2 cups penne", "Chef A")
    assert info.thumbnail_url.endswith("t.jpg")


def test_fetch_link_info_private_post():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(400)))
    with pytest.raises(social.LinkError, match="public"):
        social.fetch_link_info("https://www.tiktok.com/@a/video/1", "tiktok", client)


# ------------------------------------------------------------------ share flow

def test_shared_link_lands_on_default_list_automatically(client, auth, oembed):
    oembed["https://www.tiktok.com/@chef/video/1"] = NOODLES
    r = share(client, auth, "omg try this https://www.tiktok.com/@chef/video/1")
    assert r.status_code == 202
    video = client.get(f"/api/videos/{r.json()['id']}", headers=auth).json()
    assert video["status"] == "done" and video["platform"] == "tiktok"
    assert video["thumbnail_url"].startswith("https://cdn.example/")

    recipe = client.get(f"/api/recipes/{video['recipe_id']}", headers=auth).json()
    assert recipe["title"] == "Garlic butter noodles 🍜" and recipe["author"] == "@chef"
    assert recipe["in_default_list"] is True

    gl = default_list(client, auth)
    assert gl["is_default"] and items(gl)["garlic"]["quantity"] == 4


def test_two_shares_merge_and_keep_ticks(client, auth, oembed):
    oembed["https://www.tiktok.com/@chef/video/1"] = NOODLES
    oembed["https://www.tiktok.com/@chef/video/2"] = RICE
    share(client, auth, "https://www.tiktok.com/@chef/video/1")
    gl = default_list(client, auth)
    garlic_id = items(gl)["garlic"]["id"]
    client.patch(f"/api/lists/{gl['id']}/items/{garlic_id}", headers=auth, json={"checked": True})

    share(client, auth, "https://www.tiktok.com/@chef/video/2")
    garlic = items(default_list(client, auth))["garlic"]
    assert garlic["quantity"] == 6 and garlic["checked"] is True


def test_sharing_same_link_twice_is_a_noop(client, auth, oembed):
    oembed["https://www.tiktok.com/@chef/video/1"] = NOODLES
    a = share(client, auth, "https://www.tiktok.com/@chef/video/1").json()
    b = share(client, auth, "look https://www.tiktok.com/@chef/video/1").json()
    assert a["id"] == b["id"]
    assert items(default_list(client, auth))["garlic"]["quantity"] == 4


@pytest.mark.parametrize("text", ["https://example.com/recipe", "just some words"])
def test_rejects_unsupported_shares(client, auth, text):
    assert share(client, auth, text).status_code == 422


def test_instagram_without_caption_asks_for_it(client, auth, oembed):
    vid = share(client, auth, "https://www.instagram.com/reel/abc/").json()["id"]
    video = client.get(f"/api/videos/{vid}", headers=auth).json()
    assert video["status"] == "failed" and "caption" in video["error"].lower()

    client.post(f"/api/videos/{vid}/retry", headers=auth, data={"caption": RICE})
    assert client.get(f"/api/videos/{vid}", headers=auth).json()["status"] == "done"
    assert "rice" in items(default_list(client, auth))


def test_private_post_with_typed_caption_still_works(client, auth, oembed):
    vid = share(client, auth, "https://www.tiktok.com/@x/video/9", caption=RICE).json()["id"]
    assert client.get(f"/api/videos/{vid}", headers=auth).json()["status"] == "done"


def test_auto_add_can_be_turned_off(client, auth, oembed):
    assert client.patch("/api/auth/me", headers=auth, json={"auto_add": False}).json()["auto_add"] is False
    oembed["https://www.tiktok.com/@chef/video/1"] = NOODLES
    share(client, auth, "https://www.tiktok.com/@chef/video/1")
    assert default_list(client, auth)["items"] == []


# ------------------------------------------------------------------ list stays in sync

def _shared_recipe(client, auth, oembed, n, caption):
    url = f"https://www.tiktok.com/@chef/video/{n}"
    oembed[url] = caption
    vid = share(client, auth, url).json()["id"]
    return client.get(f"/api/videos/{vid}", headers=auth).json()["recipe_id"]


def test_editing_a_recipe_updates_the_list(client, auth, oembed):
    rid = _shared_recipe(client, auth, oembed, 1, NOODLES)
    recipe = client.get(f"/api/recipes/{rid}", headers=auth).json()
    body = {"title": recipe["title"], "steps": [],
            "ingredients": [{"name": "garlic", "quantity": 10, "unit": "clove"}]}
    client.put(f"/api/recipes/{rid}", headers=auth, json=body)
    gl = default_list(client, auth)
    assert list(items(gl)) == ["garlic"] and items(gl)["garlic"]["quantity"] == 10


def test_removing_recipe_from_list_keeps_custom_items(client, auth, oembed):
    rid = _shared_recipe(client, auth, oembed, 1, NOODLES)
    gl = default_list(client, auth)
    client.post(f"/api/lists/{gl['id']}/items", headers=auth, json={"name": "coffee"})
    gl = client.delete(f"/api/lists/{gl['id']}/recipes/{rid}", headers=auth).json()
    assert [i["name"] for i in gl["items"]] == ["coffee"]
    assert client.get(f"/api/recipes/{rid}", headers=auth).json()["in_default_list"] is False

    gl = client.post(f"/api/lists/{gl['id']}/recipes", headers=auth, json={"recipe_id": rid}).json()
    assert "garlic" in items(gl) and "coffee" in items(gl)


def test_deleting_recipe_removes_its_ingredients(client, auth, oembed):
    a = _shared_recipe(client, auth, oembed, 1, NOODLES)
    _shared_recipe(client, auth, oembed, 2, RICE)
    client.delete(f"/api/recipes/{a}", headers=auth)
    gl = items(default_list(client, auth))
    assert "noodles" not in gl and gl["garlic"]["quantity"] == 2


def test_only_custom_items_can_be_deleted(client, auth, oembed):
    _shared_recipe(client, auth, oembed, 1, NOODLES)
    gl = default_list(client, auth)
    garlic = items(gl)["garlic"]["id"]
    assert client.delete(f"/api/lists/{gl['id']}/items/{garlic}", headers=auth).status_code == 409
    coffee = client.post(f"/api/lists/{gl['id']}/items", headers=auth, json={"name": "coffee"}).json()
    assert client.delete(f"/api/lists/{gl['id']}/items/{coffee['id']}", headers=auth).status_code == 204


def test_reset_and_clear(client, auth, oembed):
    rid = _shared_recipe(client, auth, oembed, 1, NOODLES)
    gl = default_list(client, auth)
    for it in gl["items"]:
        client.patch(f"/api/lists/{gl['id']}/items/{it['id']}", headers=auth, json={"checked": True})
    gl = client.post(f"/api/lists/{gl['id']}/reset", headers=auth).json()
    assert not any(i["checked"] for i in gl["items"])
    gl = client.post(f"/api/lists/{gl['id']}/clear", headers=auth).json()
    assert gl["items"] == [] and gl["recipes"] == []
    assert client.get(f"/api/recipes/{rid}", headers=auth).status_code == 200  # recipe kept
    assert client.delete(f"/api/lists/{gl['id']}", headers=auth).status_code == 409


def test_other_users_cannot_touch_my_list(client, auth, other_auth, oembed):
    rid = _shared_recipe(client, auth, oembed, 1, NOODLES)
    mine = default_list(client, auth)
    theirs = default_list(client, other_auth)
    assert mine["id"] != theirs["id"]
    assert client.get(f"/api/lists/{mine['id']}", headers=other_auth).status_code == 404
    r = client.post(f"/api/lists/{theirs['id']}/recipes", headers=other_auth, json={"recipe_id": rid})
    assert r.status_code == 404


# ------------------------------------------------------------------ estimated ingredients

class FakeLLM:
    def __init__(self, extracted, estimate):
        self.extracted, self.estimate_result, self.estimate_calls = extracted, estimate, 0

    def extract(self, caption, transcript):
        return self.extracted

    def estimate(self, text, servings):
        self.estimate_calls += 1
        self.estimate_result.estimated = True
        return self.estimate_result


def test_estimates_when_video_lists_no_ingredients():
    llm = FakeLLM(ExtractedRecipe(title="Viral feta pasta"),
                  ExtractedRecipe(title="Feta pasta", ingredients=[
                      ExtractedIngredient("feta", "200", "g"), ExtractedIngredient("cherry tomatoes", "2", "cup")]))
    r = extract_recipe("Viral feta pasta 🤯 #pasta", "", extractor=llm)
    assert r.estimated and len(r.ingredients) == 2
    assert r.title == "Viral feta pasta"  # keeps the video's title, not the estimate's


def test_no_estimate_when_ingredients_were_found():
    llm = FakeLLM(ExtractedRecipe(title="X", ingredients=[ExtractedIngredient("egg", "2")]),
                  ExtractedRecipe(title="never"))
    r = extract_recipe("X", "", extractor=llm)
    assert not r.estimated and llm.estimate_calls == 0
