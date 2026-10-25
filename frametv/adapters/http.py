"""Minimal HTTPS client for the art catalogs (stdlib only)."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from .. import __version__
from ..domain import CatalogError

USER_AGENT = f"FrameTV/{__version__} (+https://github.com/coolnez/Frametv)"


class UrllibHttpClient:
    """Only https and only hosts the catalog adapters declared - no arbitrary URL fetching."""

    def __init__(self, allowed_hosts: frozenset[str], timeout: float = 20) -> None:
        self._allowed = allowed_hosts
        self._timeout = timeout

    def _open(self, url: str, accept: str):
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname not in self._allowed:
            raise CatalogError(f"refusing to fetch {parts.scheme}://{parts.hostname}")
        req = Request(url, headers={"User-Agent": USER_AGENT, "AIC-User-Agent": USER_AGENT, "Accept": accept})
        try:
            return urlopen(req, timeout=self._timeout)  # noqa: S310 - scheme/host checked above
        except HTTPError as exc:
            raise CatalogError(f"{parts.hostname}: HTTP {exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise CatalogError(f"{parts.hostname}: {exc}") from exc

    def get_json(self, url: str, params: dict[str, str] | None = None) -> Any:
        if params:
            url = f"{url}?{urlencode(params)}"
        with self._open(url, "application/json") as resp:
            try:
                return json.loads(resp.read(10 * 1024 * 1024))
            except ValueError as exc:
                raise CatalogError(f"{urlsplit(url).hostname}: invalid JSON") from exc

    def get_bytes(self, url: str, max_bytes: int) -> bytes:
        with self._open(url, "image/*") as resp:
            length = resp.headers.get("Content-Length")
            if length and length.isdigit() and int(length) > max_bytes:
                raise CatalogError(f"image too large ({int(length) // 1048576} MB)")
            data = resp.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise CatalogError(f"image larger than {max_bytes // 1048576} MB")
        return data
