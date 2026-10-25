"""Domain models. Pure data, no I/O."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class PowerState(str, Enum):
    ON = "on"
    STANDBY = "standby"  # screen off, network alive (Art Mode or "off" on The Frame)
    UNREACHABLE = "unreachable"


@dataclass(frozen=True)
class App:
    app_id: str
    name: str
    app_type: str = "DEEP_LINK"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Artwork:
    content_id: str
    category_id: str | None = None
    matte_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TVStatus:
    power: PowerState
    art_mode: bool | None = None
    model: str | None = None
    name: str | None = None
    frame_supported: bool | None = None
    current_artwork: Artwork | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["power"] = self.power.value
        return data


class TVError(RuntimeError):
    """Raised when the TV cannot perform the request (offline, refused, etc.)."""
