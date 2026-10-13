"""End-to-end API tests: real HTTP routes, real SQLite, real ffmpeg, no network."""
CAPTION_A = "Garlic noodles\n- 200 g noodles\n- 4 cloves garlic\n- 2 tbsp soy sauce\n- 1 onion"
CAPTION_B = "Fried rice\n- 1 cup rice\n- 2 cloves garlic\n- 1 tbsp soy sauce\n- 2 eggs\n- 1/2 onion"


def upload(client, auth, video, caption="", name="clip.mp4"):
    return client.post("/api/videos", headers=auth, data={"caption": caption},
                       files={"file": (name, video, "video/mp4")})


# ------------------------------------------------------------------ auth

def test_register_login_me(client, auth):
    assert client.get("/api/auth/me", headers=auth).json()["email"] == "alex@example.com"
    r = client.post("/api/auth/login", json={"email": "ALEX@example.com", "password": "correct-horse-1"})
    assert r.status_code == 200 and r.json()["access_token"]


def test_duplicate_email_rejected(client, auth):
    r = client.post("/api/auth/register", json={"email": "Alex@Example.com", "password": "another-pass"})
    assert r.status_code == 409


def test_wrong_password_and_unknown_email_look_the_same(client, auth):
    a = client.post("/api/auth/login", json={"email": "alex@example.com", "password": "wrong-pass-1"})
    b = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "wrong-pass-1"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_short_password_rejected(client):
    r = client.post("/api/auth/register", json={"email": "x@example.com", "password": "short"})
    assert r.status_code == 422


def test_endpoints_require_auth(client):
    for path in ("/api/videos", "/api/recipes", "/api/lists", "/api/auth/me"):
        assert client.get(path).status_code == 401
    assert client.get("/api/recipes", headers={"Authorization": "Bearer garbage"}).status_code == 401


# ------------------------------------------------------------------ videos

def test_upload_processes_into_draft_recipe(client, auth, silent_video):
    r = upload(client, auth, silent_video, CAPTION_A)
    assert r.status_code == 202
    video = client.get(f"/api/videos/{r.json()['id']}", headers=auth).json()
    assert video["status"] == "done", video
    recipe = client.get(f"/api/recipes/{video['recipe_id']}", headers=auth).json()
    assert recipe["title"] == "Garlic noodles" and recipe["reviewed"] is False
    garlic = next(i for i in recipe["ingredients"] if i["name"] == "garlic")
    assert (garlic["quantity"], garlic["unit"]) == (4, "clove")


def test_silent_video_without_caption_fails_then_retry_succeeds(client, auth, silent_video):
    vid = upload(client, auth, silent_video).json()["id"]
    failed = client.get(f"/api/videos/{vid}", headers=auth).json()
    assert failed["status"] == "failed" and "caption" in failed["error"].lower()

    r = client.post(f"/api/videos/{vid}/retry", headers=auth, data={"caption": CAPTION_B})
    assert r.status_code == 202
    assert client.get(f"/api/videos/{vid}", headers=auth).json()["status"] == "done"


def test_rejects_non_video_and_empty_files(client, auth):
    r = client.post("/api/videos", headers=auth, files={"file": ("notes.txt", b"hi", "text/plain")})
    assert r.status_code == 422
    r = client.post("/api/videos", headers=auth, files={"file": ("empty.mp4", b"", "video/mp4")})
    assert r.status_code == 422


def test_users_cannot_see_each_others_data(client, auth, other_auth, silent_video):
    vid = upload(client, auth, silent_video, CAPTION_A).json()["id"]
    rid = client.get(f"/api/videos/{vid}", headers=auth).json()["recipe_id"]
    assert client.get(f"/api/videos/{vid}", headers=other_auth).status_code == 404
    assert client.get(f"/api/recipes/{rid}", headers=other_auth).status_code == 404
    assert client.delete(f"/api/recipes/{rid}", headers=other_auth).status_code == 404
    assert client.get("/api/videos", headers=other_auth).json() == []
    r = client.post("/api/lists", headers=other_auth, json={"name": "x", "recipe_ids": [rid]})
    assert r.status_code == 404


def test_deleting_video_keeps_recipe(client, auth, silent_video):
    vid = upload(client, auth, silent_video, CAPTION_A).json()["id"]
    rid = client.get(f"/api/videos/{vid}", headers=auth).json()["recipe_id"]
    assert client.delete(f"/api/videos/{vid}", headers=auth).status_code == 204
    assert client.get(f"/api/recipes/{rid}", headers=auth).json()["video_id"] is None


# ------------------------------------------------------------------ recipes

def test_review_screen_saves_edits(client, auth):
    rid = client.post("/api/recipes", headers=auth, json={"title": "Toast", "ingredients": []}).json()["id"]
    body = {"title": "Better toast", "servings": 2, "steps": ["Toast it", "  "],
            "ingredients": [{"name": "bread", "quantity": "2", "unit": "slices"},
                            {"name": "butter", "quantity": "1 1/2", "unit": "Tablespoons"},
                            {"name": "salt"}]}
    r = client.put(f"/api/recipes/{rid}", headers=auth, json=body).json()
    assert r["reviewed"] is True and r["steps"] == ["Toast it"]
    butter = r["ingredients"][1]
    assert (butter["quantity"], butter["quantity_display"], butter["unit"]) == (1.5, "1 1/2", "tbsp")
    assert r["ingredients"][2]["quantity"] is None


def test_recipe_validation(client, auth):
    bad = {"title": "x", "ingredients": [{"name": "egg", "quantity": "lots"}]}
    assert client.post("/api/recipes", headers=auth, json=bad).status_code == 422
    neg = {"title": "x", "ingredients": [{"name": "egg", "quantity": -1}]}
    assert client.post("/api/recipes", headers=auth, json=neg).status_code == 422
    assert client.post("/api/recipes", headers=auth, json={"title": ""}).status_code == 422


# ------------------------------------------------------------------ grocery lists

def test_grocery_list_merges_and_groups_by_aisle(client, auth, silent_video):
    ids = []
    for caption in (CAPTION_A, CAPTION_B):
        vid = upload(client, auth, silent_video, caption).json()["id"]
        ids.append(client.get(f"/api/videos/{vid}", headers=auth).json()["recipe_id"])

    gl = client.post("/api/lists", headers=auth, json={"name": "This week", "recipe_ids": ids}).json()
    items = {i["name"]: i for i in gl["items"]}
    assert (items["garlic"]["quantity"], items["garlic"]["unit"]) == (6, "clove")
    assert (items["soy sauce"]["quantity"], items["soy sauce"]["unit"]) == (3, "tbsp")
    assert items["onion"]["quantity_display"] == "1 1/2"
    assert items["onion"]["aisle"] == "Produce"
    aisles = [i["aisle"] for i in gl["items"]]
    assert aisles.index("Produce") < aisles.index("Pantry")  # store walking order
    assert len(gl["recipes"]) == 2


def test_check_off_and_add_items(client, auth):
    rid = client.post("/api/recipes", headers=auth, json={
        "title": "Tea", "ingredients": [{"name": "milk", "quantity": 1, "unit": "cup"}]}).json()["id"]
    gl = client.post("/api/lists", headers=auth, json={"name": "W", "recipe_ids": [rid, rid]}).json()
    assert len(gl["items"]) == 1  # duplicate recipe ids don't double the list
    item_id = gl["items"][0]["id"]

    r = client.patch(f"/api/lists/{gl['id']}/items/{item_id}", headers=auth, json={"checked": True})
    assert r.json()["checked"] is True and r.json()["have_already"] is False

    r = client.post(f"/api/lists/{gl['id']}/items", headers=auth, json={"name": "paper towels"})
    assert r.status_code == 201
    assert len(client.get(f"/api/lists/{gl['id']}", headers=auth).json()["items"]) == 2


def test_list_needs_at_least_one_recipe(client, auth):
    assert client.post("/api/lists", headers=auth, json={"name": "x", "recipe_ids": []}).status_code == 422
