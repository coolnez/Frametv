"""Settings: environment variables override a JSON file (~/.frametv/config.json)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .domain import App

DEFAULT_HOME = Path(os.environ.get("FRAMETV_HOME", Path.home() / ".frametv"))


@dataclass
class Settings:
    host: str = ""
    mac: str = ""
    port: int = 8002
    timeout: float = 8.0
    client_name: str = "FrameTV Remote"
    token_file: str = str(DEFAULT_HOME / "token.txt")
    api_token: str = ""  # optional shared secret for the web API
    favorites: list[App] = field(default_factory=list)
    path: Path = DEFAULT_HOME / "config.json"

    _ENV = {
        "host": "FRAMETV_HOST",
        "mac": "FRAMETV_MAC",
        "port": "FRAMETV_PORT",
        "timeout": "FRAMETV_TIMEOUT",
        "client_name": "FRAMETV_CLIENT_NAME",
        "token_file": "FRAMETV_TOKEN_FILE",
        "api_token": "FRAMETV_API_TOKEN",
    }

    @classmethod
    def load(cls, path: str | Path | None = None) -> Settings:
        path = Path(path or os.environ.get("FRAMETV_CONFIG", DEFAULT_HOME / "config.json"))
        raw: dict[str, Any] = {}
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))

        settings = cls(path=path)
        for name, env in cls._ENV.items():
            value = os.environ.get(env, raw.get(name))
            if value in (None, ""):
                continue
            current = getattr(settings, name)
            setattr(settings, name, type(current)(value))

        settings.favorites = [
            App(app_id=str(f["app_id"]), name=f.get("name", f["app_id"]), app_type=f.get("app_type", "DEEP_LINK"))
            for f in raw.get("favorites", [])
        ]
        if not settings.favorites:
            settings.favorites = list(DEFAULT_FAVORITES)
        return settings

    def save(self) -> None:
        """Persist file-backed fields. Values coming from env vars are written too."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {name: getattr(self, name) for name in self._ENV}
        data["favorites"] = [f.to_dict() for f in self.favorites]
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# Tizen application IDs that are stable across 2018+ Samsung TVs.
# Russian services (Кинопоиск, Okko, Wink, ...) differ per region/firmware:
# add them from the TV's own list (`frametv apps`, or the "Все приложения" tab in the web UI).
DEFAULT_FAVORITES: tuple[App, ...] = (
    App("111299001912", "YouTube"),
    App("3201907018807", "Netflix"),
    App("org.tizen.browser", "Браузер", "NATIVE_LAUNCH"),
)
