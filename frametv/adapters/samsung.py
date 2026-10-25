"""TVGateway implementation over the Samsung local network API (samsungtvws).

Channels used:
  * REST  http(s)://<tv>:8001|8002/api/v2/        device info, app run/close
  * WS    samsung.remote.control                    keys, installed apps, launch
  * WS    com.samsung.art-app                       Art Mode (The Frame only)
  * UDP   Wake-on-LAN magic packet                  power on from deep standby
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TypeVar

import wakeonlan
from samsungtvws import SamsungTVArt, SamsungTVWS
from samsungtvws.rest import SamsungTVRest

from ..config import Settings
from ..domain import App, Artwork, PowerState, TVError, TVStatus

log = logging.getLogger(__name__)
T = TypeVar("T")

# app_type values reported by ed.installedApp.get
_NATIVE_APP_TYPE = 4


class SamsungFrameGateway:
    def __init__(self, settings: Settings) -> None:
        if not settings.host:
            raise TVError("TV IP address is not configured (FRAMETV_HOST or config.json 'host')")
        self._s = settings
        # The TV copes badly with parallel sockets from one client: serialise all calls.
        self._lock = threading.RLock()
        Path(settings.token_file).parent.mkdir(parents=True, exist_ok=True)

    # ---- connection helpers -------------------------------------------------

    def _conn_kwargs(self) -> dict[str, Any]:
        return {
            "host": self._s.host,
            "port": self._s.port,
            "token_file": self._s.token_file,
            "timeout": self._s.timeout,
            "name": self._s.client_name,
        }

    @contextmanager
    def _remote(self) -> Iterator[SamsungTVWS]:
        with self._lock, self._guard("remote control"):
            with SamsungTVWS(**self._conn_kwargs()) as tv:
                yield tv

    @contextmanager
    def _art(self) -> Iterator[SamsungTVArt]:
        with self._lock, self._guard("art mode"):
            with SamsungTVArt(**self._conn_kwargs()) as art:
                yield art

    def _rest(self) -> SamsungTVRest:
        return SamsungTVRest(self._s.host, port=self._s.port, timeout=self._s.timeout)

    @contextmanager
    def _guard(self, what: str) -> Iterator[None]:
        try:
            yield
        except TVError:
            raise
        except Exception as exc:  # library raises a zoo of socket/ws/json errors
            log.debug("%s failed", what, exc_info=True)
            raise TVError(f"{what}: {exc.__class__.__name__}: {exc}") from exc

    def _try(self, fn: Callable[[], T], default: T) -> T:
        try:
            return fn()
        except Exception:
            log.debug("optional call failed", exc_info=True)
            return default

    # ---- TVGateway ----------------------------------------------------------

    def status(self) -> TVStatus:
        try:
            info = self._rest().rest_device_info()
        except Exception:
            return TVStatus(power=PowerState.UNREACHABLE)

        device = info.get("device", {})
        power = PowerState.STANDBY if device.get("PowerState") == "standby" else PowerState.ON
        frame = str(device.get("FrameTVSupport", "")).lower() == "true"
        status = TVStatus(
            power=power,
            model=device.get("modelName"),
            name=device.get("name"),
            frame_supported=frame,
            extra={"firmware_api": info.get("version"), "os": device.get("OS")},
        )
        if frame and power is PowerState.ON:
            with self._lock:
                art = self._try(lambda: self._art_state(), None)
            if art is not None:
                status.art_mode, status.current_artwork = art
        return status

    def _art_state(self) -> tuple[bool, Artwork | None]:
        with SamsungTVArt(**self._conn_kwargs()) as art:
            on = art.get_artmode() == "on"
            current = self._try(art.get_current, None)
        artwork = None
        if isinstance(current, dict) and current.get("content_id"):
            artwork = Artwork(current["content_id"], current.get("category_id"), current.get("matte_id"))
        return on, artwork

    def wake(self) -> None:
        if not self._s.mac:
            raise TVError("MAC address is not configured (FRAMETV_MAC) - needed for Wake-on-LAN")
        wakeonlan.send_magic_packet(self._s.mac)
        # also directed to the TV itself: some routers drop broadcast between Wi-Fi and LAN
        self._try(lambda: wakeonlan.send_magic_packet(self._s.mac, ip_address=self._s.host), None)

    def send_key(self, key: str, hold_seconds: float = 0) -> None:
        with self._remote() as tv:
            if hold_seconds:
                tv.hold_key(key, hold_seconds)
            else:
                tv.send_key(key)

    def installed_apps(self) -> list[App]:
        with self._remote() as tv:
            raw = tv.app_list() or []
        apps = [
            App(
                app_id=str(a["appId"]),
                name=a.get("name", a["appId"]),
                app_type="NATIVE_LAUNCH" if a.get("app_type") == _NATIVE_APP_TYPE else "DEEP_LINK",
            )
            for a in raw
        ]
        return sorted(apps, key=lambda a: a.name.lower())

    def launch_app(self, app: App) -> None:
        with self._lock, self._guard("launch app"):
            try:
                self._rest().rest_app_run(app.app_id)
                return
            except Exception:
                log.debug("REST launch failed, falling back to websocket", exc_info=True)
            with SamsungTVWS(**self._conn_kwargs()) as tv:
                tv.run_app(app.app_id, app.app_type)

    def close_app(self, app_id: str) -> None:
        with self._lock, self._guard("close app"):
            self._rest().rest_app_close(app_id)

    def set_art_mode(self, on: bool) -> None:
        with self._art() as art:
            art.set_artmode("on" if on else "off")

    def artworks(self, category_id: str | None = None) -> list[Artwork]:
        with self._art() as art:
            items = art.available(category_id) or []
        return [Artwork(i["content_id"], i.get("category_id"), i.get("matte_id")) for i in items]

    def select_artwork(self, content_id: str) -> None:
        with self._art() as art:
            art.select_image(content_id, show=True)

    def upload_artwork(self, data: bytes, file_type: str, matte: str) -> str:
        with self._art() as art:
            return art.upload(data, file_type=file_type, matte=matte, portrait_matte=matte)

    def delete_artwork(self, content_id: str) -> None:
        with self._art() as art:
            if not art.delete(content_id):
                raise TVError(f"TV refused to delete {content_id}")

    def artwork_thumbnail(self, content_id: str) -> bytes:
        with self._art() as art:
            data = art.get_thumbnail(content_id)
        if not data:
            raise TVError(f"no thumbnail for {content_id}")
        return bytes(data)  # type: ignore[arg-type]

    def set_art_brightness(self, value: int) -> None:
        with self._art() as art:
            art.set_brightness(value)

    def set_slideshow(self, minutes: int, shuffle: bool, category_id: str) -> None:
        # 2020 firmware (Art API 2.x/3.x) knows only "auto_rotation"; 2022+ renamed it "slideshow".
        with self._art() as art:
            try:
                art.set_auto_rotation_status(duration=minutes, type=shuffle, category_id=category_id)
            except Exception:
                log.debug("auto_rotation unsupported, trying slideshow", exc_info=True)
                art.set_slideshow_status(duration=minutes, type=shuffle, category_id=category_id)
