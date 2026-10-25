"""Use cases. The only layer the CLI and web API talk to."""

from __future__ import annotations

import time
from collections.abc import Callable

from .config import Settings
from .domain import App, Artwork, PowerState, TVStatus
from .ports import TVGateway

# Keys the remote is allowed to send. Keeps the API from becoming a raw passthrough
# (KEY_FACTORY etc. are deliberately absent).
ALLOWED_KEYS = frozenset(
    {
        "KEY_POWER", "KEY_HOME", "KEY_RETURN", "KEY_EXIT", "KEY_MENU", "KEY_SOURCE", "KEY_INFO",
        "KEY_UP", "KEY_DOWN", "KEY_LEFT", "KEY_RIGHT", "KEY_ENTER",
        "KEY_VOLUP", "KEY_VOLDOWN", "KEY_MUTE", "KEY_CHUP", "KEY_CHDOWN",
        "KEY_PLAY", "KEY_PAUSE", "KEY_STOP", "KEY_FF", "KEY_REWIND",
        "KEY_HDMI", "KEY_HDMI1", "KEY_HDMI2", "KEY_HDMI3", "KEY_HDMI4",
    }
)
SLIDESHOW_CATEGORIES = {"MY-C0002": "Мои фото", "MY-C0004": "Избранное", "MY-C0008": "Art Store"}
UPLOAD_TYPES = {"jpg", "jpeg", "png"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
# Holding POWER ~3 s turns The Frame fully off; a short press only toggles Art Mode <-> TV.
POWER_OFF_HOLD_SECONDS = 3.0


class FrameService:
    def __init__(
        self,
        tv: TVGateway,
        settings: Settings,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.tv = tv
        self.settings = settings
        self._sleep = sleep

    # ---- power / mode -------------------------------------------------------

    def status(self) -> TVStatus:
        return self.tv.status()

    def power_on(self, wait_seconds: float = 20, poll: float = 2) -> TVStatus:
        self.tv.wake()
        waited = 0.0
        while True:
            status = self.tv.status()
            if status.power is PowerState.ON or waited >= wait_seconds:
                return status
            self._sleep(poll)
            waited += poll

    def power_off(self) -> None:
        self.tv.send_key("KEY_POWER", hold_seconds=POWER_OFF_HOLD_SECONDS)

    def art_mode(self) -> None:
        self._ensure_on()
        self.tv.set_art_mode(True)

    def tv_mode(self) -> None:
        self._ensure_on()
        self.tv.set_art_mode(False)

    def _ensure_on(self) -> None:
        if self.tv.status().power is not PowerState.ON:
            self.power_on()

    def press(self, key: str, hold_seconds: float = 0) -> None:
        key = key.upper()
        if not key.startswith("KEY_"):
            key = f"KEY_{key}"
        if key not in ALLOWED_KEYS:
            raise ValueError(f"key {key} is not allowed")
        if not 0 <= hold_seconds <= 5:
            raise ValueError("hold_seconds must be within 0..5")
        self.tv.send_key(key, hold_seconds)

    # ---- apps ---------------------------------------------------------------

    def installed_apps(self) -> list[App]:
        return self.tv.installed_apps()

    def favorites(self) -> list[App]:
        return list(self.settings.favorites)

    def add_favorite(self, app_id: str, name: str | None = None, app_type: str | None = None) -> App:
        known = {a.app_id: a for a in self.settings.favorites}
        if app_id in known:
            return known[app_id]
        if name:
            app = App(app_id, name, app_type or "DEEP_LINK")
        else:
            installed = {a.app_id: a for a in self.tv.installed_apps()}
            if app_id not in installed:
                raise ValueError(f"app {app_id} is not installed on the TV")
            app = installed[app_id]
        self.settings.favorites.append(app)
        self.settings.save()
        return app

    def remove_favorite(self, app_id: str) -> None:
        self.settings.favorites = [a for a in self.settings.favorites if a.app_id != app_id]
        self.settings.save()

    def launch(self, app_id_or_name: str) -> App:
        app = self._resolve_app(app_id_or_name)
        self._ensure_on()
        self.tv.launch_app(app)
        return app

    def close(self, app_id_or_name: str) -> None:
        self.tv.close_app(self._resolve_app(app_id_or_name).app_id)

    def _resolve_app(self, ref: str) -> App:
        ref = ref.strip()
        if not ref:
            raise ValueError("app id or name is required")
        needle = ref.lower()
        for app in self.settings.favorites:
            if needle in (app.app_id.lower(), app.name.lower()):
                return app
        # Not a favorite: treat it as an app id, the TV rejects unknown ones.
        return App(ref, ref)

    # ---- art ----------------------------------------------------------------

    def artworks(self, category_id: str | None = None) -> list[Artwork]:
        return self.tv.artworks(category_id)

    def show_artwork(self, content_id: str) -> None:
        self.tv.select_artwork(content_id)
        self.tv.set_art_mode(True)

    def upload_artwork(self, data: bytes, filename: str, matte: str = "none", show: bool = True) -> str:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in UPLOAD_TYPES:
            raise ValueError("only .jpg / .png images are supported")
        if not data or len(data) > MAX_UPLOAD_BYTES:
            raise ValueError("image must be between 1 byte and 20 MB")
        content_id = self.tv.upload_artwork(data, "jpg" if ext == "jpeg" else ext, matte)
        if show:
            self.show_artwork(content_id)
        return content_id

    def delete_artwork(self, content_id: str) -> None:
        if not content_id.startswith("MY_"):
            raise ValueError("only your own uploads (MY_...) can be deleted")
        self.tv.delete_artwork(content_id)

    def set_brightness(self, value: int) -> None:
        if not 1 <= value <= 10:
            raise ValueError("brightness must be within 1..10")
        self.tv.set_art_brightness(value)

    def set_slideshow(self, minutes: int, shuffle: bool = True, category_id: str = "MY-C0002") -> None:
        if not 0 <= minutes <= 7 * 24 * 60:
            raise ValueError("minutes must be within 0 (off) .. 10080")
        if category_id not in SLIDESHOW_CATEGORIES:
            raise ValueError(f"category must be one of {', '.join(SLIDESHOW_CATEGORIES)}")
        self.tv.set_slideshow(minutes, shuffle, category_id)
