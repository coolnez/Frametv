from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from frametv.adapters.fake import FakeFrameGateway
from frametv.api import create_app
from frametv.config import Settings
from frametv.domain import App, PowerState
from frametv.service import POWER_OFF_HOLD_SECONDS, FrameService


@pytest.fixture
def settings(tmp_path):
    return Settings.load(tmp_path / "config.json")


@pytest.fixture
def tv():
    return FakeFrameGateway()


@pytest.fixture
def svc(tv, settings):
    return FrameService(tv, settings, sleep=lambda _: None)


# ---- config ----------------------------------------------------------------


def test_settings_env_overrides_file(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"host": "10.0.0.1", "port": 8001, "favorites": [{"app_id": "x", "name": "X"}]}))
    monkeypatch.setenv("FRAMETV_HOST", "10.0.0.2")
    s = Settings.load(path)
    assert (s.host, s.port) == ("10.0.0.2", 8001)
    assert s.favorites == [App("x", "X")]


def test_settings_roundtrip(settings):
    settings.host = "192.168.1.50"
    settings.favorites.append(App("123", "Кинопоиск"))
    settings.save()
    loaded = Settings.load(settings.path)
    assert loaded.host == "192.168.1.50"
    assert App("123", "Кинопоиск") in loaded.favorites


# ---- service ---------------------------------------------------------------


def test_art_and_tv_mode(svc, tv):
    svc.art_mode()
    assert tv.art_mode is True
    svc.tv_mode()
    assert tv.art_mode is False


def test_mode_switch_wakes_tv_first(svc, tv):
    tv.power = PowerState.UNREACHABLE
    svc.art_mode()
    assert tv.power is PowerState.ON and tv.art_mode


def test_power_off_holds_power_key(svc, tv):
    svc.power_off()
    assert tv.keys == [("KEY_POWER", POWER_OFF_HOLD_SECONDS)]
    assert tv.power is PowerState.UNREACHABLE


def test_power_on_gives_up_after_timeout(svc, tv, monkeypatch):
    monkeypatch.setattr(tv, "wake", lambda: None)
    tv.power = PowerState.UNREACHABLE
    assert svc.power_on(wait_seconds=4, poll=2).power is PowerState.UNREACHABLE


def test_press_normalises_and_whitelists(svc, tv):
    svc.press("volup")
    assert tv.keys[-1] == ("KEY_VOLUP", 0)
    with pytest.raises(ValueError):
        svc.press("factory")


def test_launch_by_favorite_name(svc, tv):
    app = svc.launch("youtube")
    assert app.app_id == "111299001912"
    assert tv.running_app == "111299001912"


def test_add_favorite_from_installed(svc, tv, settings):
    tv.apps.append(App("3201710015067", "Кинопоиск"))
    svc.add_favorite("3201710015067")
    assert Settings.load(settings.path).favorites[-1].name == "Кинопоиск"
    with pytest.raises(ValueError):
        svc.add_favorite("not-installed")


def test_remove_favorite(svc, settings):
    svc.remove_favorite("111299001912")
    assert all(a.app_id != "111299001912" for a in Settings.load(settings.path).favorites)


def test_upload_shows_artwork(svc, tv):
    cid = svc.upload_artwork(b"\xff\xd8data", "photo.JPEG", matte="shadowbox_polar")
    assert tv.current.content_id == cid and tv.art_mode


@pytest.mark.parametrize("name,data", [("a.gif", b"x"), ("a.png", b""), ("noext", b"x")])
def test_upload_validation(svc, name, data):
    with pytest.raises(ValueError):
        svc.upload_artwork(data, name)


def test_cannot_delete_store_art(svc):
    with pytest.raises(ValueError):
        svc.delete_artwork("SAM-S0700")


def test_brightness_and_slideshow_validation(svc, tv):
    svc.set_brightness(7)
    svc.set_slideshow(60, True, "MY-C0004")
    assert tv.brightness == 7 and tv.slideshow == (60, True, "MY-C0004")
    with pytest.raises(ValueError):
        svc.set_brightness(0)
    with pytest.raises(ValueError):
        svc.set_slideshow(10, category_id="BOGUS")


# ---- web API ---------------------------------------------------------------


@pytest.fixture
def client(svc):
    return TestClient(create_app(svc))


def test_api_index_and_status(client):
    assert "The Frame" in client.get("/").text
    body = client.get("/api/status").json()
    assert body["power"] == "on" and body["frame_supported"] is True


def test_api_mode_and_keys(client, tv):
    assert client.post("/api/mode/art").json() == {"ok": True}
    assert tv.art_mode
    assert client.post("/api/key/HOME").status_code == 200
    assert client.post("/api/key/FACTORY").status_code == 400


def test_api_tv_error_is_502(client, tv):
    tv.power = PowerState.UNREACHABLE
    tv.wake = lambda: None
    assert client.post("/api/apps/111299001912/launch").status_code == 502


def test_api_upload_raw_body(client, tv):
    r = client.post("/api/art/upload?filename=x.png", content=b"\x89PNG", headers={"Content-Type": "image/png"})
    assert r.status_code == 200
    assert r.json()["content_id"] in [a.content_id for a in tv.art]


def test_api_token_required_when_configured(svc):
    svc.settings.api_token = "s3cret"
    c = TestClient(create_app(svc))
    assert c.get("/api/status").status_code == 401
    assert c.get("/api/status", headers={"X-API-Token": "s3cret"}).status_code == 200
    assert c.get("/").status_code == 200  # page itself is public, it asks for the token
