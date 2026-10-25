"""In-memory TV used by tests and by `frametv serve --demo` (UI without a real TV)."""

from __future__ import annotations

import itertools

from ..domain import App, Artwork, PowerState, TVError, TVStatus


class FakeFrameGateway:
    def __init__(self) -> None:
        self.power = PowerState.ON
        self.art_mode = False
        self.running_app: str | None = None
        self.keys: list[tuple[str, float]] = []
        self.brightness = 5
        self.slideshow: tuple[int, bool, str] | None = None
        self.apps = [
            App("111299001912", "YouTube"),
            App("3201907018807", "Netflix"),
            App("org.tizen.browser", "Browser", "NATIVE_LAUNCH"),
        ]
        self.art = [
            Artwork("SAM-S0700", "MY-C0008"),
            Artwork("SAM-S2701", "MY-C0008"),
            Artwork("MY_F0001", "MY-C0002", "shadowbox_polar"),
        ]
        self.current = self.art[0]
        self._ids = itertools.count(2)

    def _require_on(self) -> None:
        if self.power is not PowerState.ON:
            raise TVError("TV is not reachable")

    def status(self) -> TVStatus:
        if self.power is not PowerState.ON:
            return TVStatus(power=self.power)
        return TVStatus(
            power=self.power,
            art_mode=self.art_mode,
            model="QE65LS03TAUXRU",
            name="[TV] The Frame (demo)",
            frame_supported=True,
            current_artwork=self.current,
            extra={"running_app": self.running_app},
        )

    def wake(self) -> None:
        self.power = PowerState.ON

    def send_key(self, key: str, hold_seconds: float = 0) -> None:
        self._require_on()
        self.keys.append((key, hold_seconds))
        if key == "KEY_POWER" and hold_seconds:
            self.power = PowerState.UNREACHABLE
        elif key == "KEY_POWER":
            self.art_mode = not self.art_mode

    def installed_apps(self) -> list[App]:
        self._require_on()
        return list(self.apps)

    def launch_app(self, app: App) -> None:
        self._require_on()
        self.art_mode = False
        self.running_app = app.app_id

    def close_app(self, app_id: str) -> None:
        self._require_on()
        if self.running_app == app_id:
            self.running_app = None

    def set_art_mode(self, on: bool) -> None:
        self._require_on()
        self.art_mode = on

    def artworks(self, category_id: str | None = None) -> list[Artwork]:
        self._require_on()
        return [a for a in self.art if category_id in (None, a.category_id)]

    def select_artwork(self, content_id: str) -> None:
        self._require_on()
        match = [a for a in self.art if a.content_id == content_id]
        if not match:
            raise TVError(f"unknown artwork {content_id}")
        self.current = match[0]

    def upload_artwork(self, data: bytes, file_type: str, matte: str) -> str:
        self._require_on()
        art = Artwork(f"MY_F{next(self._ids):04d}", "MY-C0002", matte)
        self.art.append(art)
        return art.content_id

    def delete_artwork(self, content_id: str) -> None:
        self._require_on()
        self.art = [a for a in self.art if a.content_id != content_id]

    def artwork_thumbnail(self, content_id: str) -> bytes:
        self._require_on()
        if not any(a.content_id == content_id for a in self.art):
            raise TVError(f"no thumbnail for {content_id}")
        return b"\xff\xd8fake-thumbnail"

    def set_art_brightness(self, value: int) -> None:
        self._require_on()
        self.brightness = value

    def set_slideshow(self, minutes: int, shuffle: bool, category_id: str) -> None:
        self._require_on()
        self.slideshow = (minutes, shuffle, category_id)
