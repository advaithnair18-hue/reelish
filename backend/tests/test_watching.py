"""Reelish watching and listening to the video itself, not just reading the caption."""
import base64
import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import inspect, text

from app.config import settings
from app.db import engine, ensure_schema
from app.services import extraction, media, social
from app.services.extraction import ClaudeExtractor, ExtractedIngredient, ExtractedRecipe

LINK = "https://www.tiktok.com/@wokstar/video/77"


@pytest.fixture
def video_file(tmp_path, talking_video) -> Path:
    path = tmp_path / "v.mp4"
    path.write_bytes(talking_video)
    return path


# ------------------------------------------------------------------ frames and audio

def test_frame_times_skip_the_ends():
    assert media.frame_times(100, 5) == [5.0, 27.5, 50.0, 72.5, 95.0]
    assert media.frame_times(10, 1) == [5.0]
    assert media.frame_times(0, 8) == [0.0]
    assert media.frame_times(10, 0) == []


def test_probe_and_sample_frames(video_file, tmp_path):
    duration, has_audio = media.probe(video_file)
    assert 2.5 < duration < 3.5 and has_audio
    frames = media.sample_frames(video_file, tmp_path, duration, count=4)
    assert len(frames) == 4 and all(f[:2] == b"\xff\xd8" for f in frames)  # JPEGs
    assert all(len(f) < 60_000 for f in frames)  # small enough to send cheaply


def test_hosted_transcription(monkeypatch, video_file, tmp_path):
    monkeypatch.setattr(settings, "transcribe_api_key", "gsk_test")
    seen = {}

    def handler(request: httpx.Request):
        seen["auth"] = request.headers["authorization"]
        seen["body"] = request.content
        return httpx.Response(200, json={"text": " add two eggs and a cup of rice "})

    audio = media.extract_audio(video_file, tmp_path / "a.mp3")
    text_out = media.transcribe(audio, httpx.Client(transport=httpx.MockTransport(handler)))
    assert text_out == "add two eggs and a cup of rice"
    assert seen["auth"] == "Bearer gsk_test"
    assert b"whisper-large-v3-turbo" in seen["body"] and b'filename="a.mp3"' in seen["body"]


def test_transcription_error_is_reported(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "transcribe_api_key", "gsk_test")
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"ID3")
    with pytest.raises(media.MediaError):
        media.transcribe(audio, httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429))))


def test_no_speech_service_means_no_transcript(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "transcribe_api_key", "")
    monkeypatch.setattr(media, "_transcribe_locally", lambda path: None)
    assert media.transcribe(tmp_path / "a.mp3") == ""


# ------------------------------------------------------------------ the AI sees the frames

def test_extractor_sends_frames_as_images():
    sent = {}

    def handler(request: httpx.Request):
        sent.update(json.loads(request.content))
        reply = {"title": "Egg fried rice", "servings": 2, "steps": ["Fry"],
                 "ingredients": [{"name": "rice", "quantity": "2", "unit": "cup", "raw_text": "2 cups rice"},
                                 {"name": "egg", "quantity": "2", "unit": "", "estimated": True}]}
        return httpx.Response(200, json={"content": [{"type": "text", "text": json.dumps(reply)}]})

    ex = ClaudeExtractor("k", "m", httpx.Client(transport=httpx.MockTransport(handler)))
    r = ex.extract("egg fried rice 🍳", "so first the rice", [b"\xff\xd8one", b"\xff\xd8two"])
    blocks = sent["messages"][0]["content"]
    images = [b for b in blocks if b["type"] == "image"]
    assert len(images) == 2 and base64.b64decode(images[0]["source"]["data"]) == b"\xff\xd8one"
    assert "2 still frames" in blocks[-1]["text"] and "so first the rice" in blocks[-1]["text"]
    assert r.estimated is True and [i.name for i in r.ingredients] == ["rice", "egg"]


def test_extractor_without_frames_sends_plain_text():
    sent = {}

    def handler(request):
        sent.update(json.loads(request.content))
        return httpx.Response(200, json={"content": [{"type": "text", "text": '{"title":"X","ingredients":[]}'}]})

    ClaudeExtractor("k", "m", httpx.Client(transport=httpx.MockTransport(handler))).extract("cap", "")
    assert isinstance(sent["messages"][0]["content"], str)


# ------------------------------------------------------------------ the whole flow

class WatchingLLM:
    """Stands in for Claude: 'sees' ingredients only when it's given frames."""
    calls = []

    def __init__(self, *a, **k):
        pass

    def extract(self, caption, transcript, frames=None):
        WatchingLLM.calls.append({"frames": len(frames or []), "transcript": transcript})
        if not frames:
            return ExtractedRecipe(title="Egg fried rice")
        return ExtractedRecipe(title="Egg fried rice", ingredients=[
            ExtractedIngredient("rice", "2", "cup"), ExtractedIngredient("egg", "3"),
            ExtractedIngredient("soy sauce", "2", "tbsp")])

    def estimate(self, text, servings):
        return ExtractedRecipe(title="Egg fried rice", estimated=True,
                               ingredients=[ExtractedIngredient("rice", "1", "cup")])


@pytest.fixture
def ai_on(monkeypatch):
    WatchingLLM.calls = []
    monkeypatch.setattr(settings, "anthropic_api_key", "test")
    monkeypatch.setattr(extraction, "ClaudeExtractor", WatchingLLM)
    monkeypatch.setattr(media, "transcribe", lambda path, client=None: "add three eggs and some soy sauce")
    monkeypatch.setattr(social, "fetch_link_info",
                        lambda url, platform, client=None: social.LinkInfo(caption="egg fried rice 🍳 #fyp",
                                                                           author="@wokstar"))


def share(client, auth):
    vid = client.post("/api/videos/link", headers=auth, json={"url": LINK}).json()["id"]
    video = client.get(f"/api/videos/{vid}", headers=auth).json()
    return video, client.get(f"/api/recipes/{video['recipe_id']}", headers=auth).json()


def test_downloaded_video_is_watched_and_heard(client, auth, ai_on, monkeypatch, video_file):
    monkeypatch.setattr(social, "download_video", lambda url, dest: video_file)
    video, recipe = share(client, auth)
    assert video["transcript"] == "add three eggs and some soy sauce"
    assert WatchingLLM.calls[-1]["frames"] == settings.max_frames
    assert recipe["watched"] is True and recipe["estimated"] is False
    assert {i["name"] for i in recipe["ingredients"]} == {"rice", "egg", "soy sauce"}


def test_blocked_download_falls_back_then_attached_video_fixes_it(client, auth, ai_on, monkeypatch, talking_video):
    monkeypatch.setattr(social, "download_video", lambda url, dest: None)  # TikTok said no
    video, recipe = share(client, auth)
    assert recipe["watched"] is False and recipe["estimated"] is True  # caption-only guess

    # Save video in TikTok, then "Add the video" on the recipe page.
    r = client.post(f"/api/videos/{video['id']}/file", headers=auth,
                    files={"file": ("saved.mp4", talking_video, "video/mp4")})
    assert r.status_code == 202
    after = client.get(f"/api/recipes/{recipe['id']}", headers=auth).json()
    assert after["id"] == recipe["id"] and after["watched"] is True and after["estimated"] is False
    assert {i["name"] for i in after["ingredients"]} == {"rice", "egg", "soy sauce"}
    assert after["in_default_list"] is True


def test_attach_file_checks_owner_and_type(client, auth, other_auth, ai_on, monkeypatch, talking_video):
    monkeypatch.setattr(social, "download_video", lambda url, dest: None)
    video, _ = share(client, auth)
    url = f"/api/videos/{video['id']}/file"
    mp4 = {"file": ("v.mp4", talking_video, "video/mp4")}
    assert client.post(url, headers=other_auth, files=mp4).status_code == 404
    assert client.post(url, headers=auth, files={"file": ("notes.txt", b"hi", "text/plain")}).status_code == 422


def test_download_is_off_when_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "enable_video_download", False)
    assert social.download_video(LINK, tmp_path) is None


# ------------------------------------------------------------------ live databases get new columns

def test_ensure_schema_adds_missing_columns():
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE recipes DROP COLUMN watched"))
    assert "watched" not in {c["name"] for c in inspect(engine).get_columns("recipes")}
    ensure_schema()
    assert "watched" in {c["name"] for c in inspect(engine).get_columns("recipes")}
    ensure_schema()  # running again is a no-op
