"""Open-access museum catalogs: public-domain works, no API key required.

  aic        Art Institute of Chicago   https://api.artic.edu/docs/
  met        The Metropolitan Museum    https://metmuseum.github.io/
  cleveland  Cleveland Museum of Art    https://openaccess-api.clevelandart.org/
"""

from __future__ import annotations

from typing import Any

from ..domain import CatalogError, CatalogItem
from ..ports import HttpClient


def _str(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _item_id(item_id: str) -> str:
    if not item_id.isdigit():  # all three museums use numeric ids; also blocks path injection
        raise ValueError(f"invalid catalog item id {item_id!r}")
    return item_id


class _MuseumCatalog:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def download(self, url: str, max_bytes: int) -> bytes:
        return self._http.get_bytes(url, max_bytes)


class ArtInstituteChicago(_MuseumCatalog):
    source_id = "aic"
    title = "Art Institute of Chicago"
    hosts = frozenset({"api.artic.edu", "www.artic.edu"})

    _API = "https://api.artic.edu/api/v1/artworks"
    _FIELDS = "id,title,artist_display,date_display,image_id,is_public_domain"
    _IIIF = "https://www.artic.edu/iiif/2"

    def _item(self, d: dict[str, Any], iiif: str) -> CatalogItem | None:
        image_id = _str(d.get("image_id"))
        if not image_id or not d.get("is_public_domain"):
            return None
        # AIC serves up to 1686 px wide to the public; 843 is the officially recommended size.
        base = f"{iiif}/{image_id}/full"
        return CatalogItem(
            source=self.source_id,
            item_id=_str(d.get("id")),
            title=_str(d.get("title")),
            artist=_str(d.get("artist_display")).split("\n")[0],
            date=_str(d.get("date_display")),
            thumb_url=f"{base}/400,/0/default.jpg",
            image_urls=(f"{base}/1686,/0/default.jpg", f"{base}/843,/0/default.jpg"),
        )

    def _iiif(self, body: dict[str, Any]) -> str:
        iiif = _str(body.get("config", {}).get("iiif_url")) or self._IIIF
        return iiif if iiif.startswith("https://www.artic.edu/") else self._IIIF

    def search(self, query: str, limit: int) -> list[CatalogItem]:
        body = self._http.get_json(
            f"{self._API}/search",
            {
                "q": query,
                "limit": str(limit),
                "fields": self._FIELDS,
                "query[term][is_public_domain]": "true",
            },
        )
        iiif = self._iiif(body)
        return [i for d in body.get("data", []) if (i := self._item(d, iiif))]

    def get(self, item_id: str) -> CatalogItem:
        body = self._http.get_json(f"{self._API}/{_item_id(item_id)}", {"fields": self._FIELDS})
        item = self._item(body.get("data") or {}, self._iiif(body))
        if not item:
            raise CatalogError(f"aic {item_id}: no public-domain image")
        return item


class MetropolitanMuseum(_MuseumCatalog):
    source_id = "met"
    title = "The Metropolitan Museum of Art"
    hosts = frozenset({"collectionapi.metmuseum.org", "images.metmuseum.org"})

    _API = "https://collectionapi.metmuseum.org/public/collection/v1"

    def _item(self, d: dict[str, Any]) -> CatalogItem | None:
        full, small = _str(d.get("primaryImage")), _str(d.get("primaryImageSmall"))
        if not (full or small) or not d.get("isPublicDomain"):
            return None
        return CatalogItem(
            source=self.source_id,
            item_id=_str(d.get("objectID")),
            title=_str(d.get("title")),
            artist=_str(d.get("artistDisplayName")),
            date=_str(d.get("objectDate")),
            thumb_url=small or full,
            image_urls=tuple(u for u in (full, small) if u),
        )

    def search(self, query: str, limit: int) -> list[CatalogItem]:
        body = self._http.get_json(
            f"{self._API}/search", {"q": query, "hasImages": "true", "isPublicDomain": "true"}
        )
        ids = body.get("objectIDs") or []
        # Search returns ids only; each object is a separate request, so cap the fan-out.
        items: list[CatalogItem] = []
        for object_id in ids[: limit * 2]:
            try:
                item = self._item(self._http.get_json(f"{self._API}/objects/{int(object_id)}"))
            except CatalogError:
                continue
            if item:
                items.append(item)
            if len(items) >= limit:
                break
        return items

    def get(self, item_id: str) -> CatalogItem:
        item = self._item(self._http.get_json(f"{self._API}/objects/{_item_id(item_id)}"))
        if not item:
            raise CatalogError(f"met {item_id}: no public-domain image")
        return item


class ClevelandMuseum(_MuseumCatalog):
    source_id = "cleveland"
    title = "Cleveland Museum of Art"
    hosts = frozenset({"openaccess-api.clevelandart.org", "openaccess-cdn.clevelandart.org"})

    _API = "https://openaccess-api.clevelandart.org/api/artworks"

    def _item(self, d: dict[str, Any]) -> CatalogItem | None:
        images = d.get("images") or {}
        urls = tuple(
            u for key in ("print", "web") if (u := _str((images.get(key) or {}).get("url")))
        )
        if not urls or _str(d.get("share_license_status")).upper() not in ("", "CC0"):
            return None
        creators = d.get("creators") or [{}]
        return CatalogItem(
            source=self.source_id,
            item_id=_str(d.get("id")),
            title=_str(d.get("title")),
            artist=_str(creators[0].get("description")),
            date=_str(d.get("creation_date")),
            thumb_url=urls[-1],
            image_urls=urls,
        )

    def search(self, query: str, limit: int) -> list[CatalogItem]:
        body = self._http.get_json(
            f"{self._API}/", {"q": query, "cc0": "1", "has_image": "1", "limit": str(limit)}
        )
        return [i for d in body.get("data", []) if (i := self._item(d))]

    def get(self, item_id: str) -> CatalogItem:
        item = self._item(self._http.get_json(f"{self._API}/{_item_id(item_id)}").get("data") or {})
        if not item:
            raise CatalogError(f"cleveland {item_id}: no CC0 image")
        return item


MUSEUM_CATALOGS = (ArtInstituteChicago, MetropolitanMuseum, ClevelandMuseum)


def build_catalogs(timeout: float = 20) -> dict[str, Any]:
    from .http import UrllibHttpClient

    return {
        cls.source_id: cls(UrllibHttpClient(cls.hosts, timeout))  # type: ignore[arg-type]
        for cls in MUSEUM_CATALOGS
    }
