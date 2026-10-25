"""Use cases for Art Mode content from the Samsung catalog and museum catalogs."""

from __future__ import annotations

import random
from typing import Any

from .domain import Artwork, CatalogError, CatalogItem
from .imaging import fit_for_frame
from .ports import ArtCatalog
from .service import MAX_UPLOAD_BYTES, FrameService

SAMSUNG_SOURCE = "samsung"
# Content on the TV: SAM-* ids are Samsung Art Store / preinstalled works, MY_* are user uploads.
SAMSUNG_CATEGORY = "MY-C0008"
# Museums often publish 30-100 MB masters; refuse those and fall back to a smaller rendition.
MAX_DOWNLOAD_BYTES = 40 * 1024 * 1024


class CatalogService:
    def __init__(self, frame: FrameService, catalogs: dict[str, ArtCatalog], rng: random.Random | None = None) -> None:
        self.frame = frame
        self.catalogs = catalogs
        self._rng = rng or random.Random()

    def sources(self) -> list[dict[str, Any]]:
        return [{"id": SAMSUNG_SOURCE, "title": "Samsung (на телевизоре)", "kind": "tv"}] + [
            {"id": c.source_id, "title": c.title, "kind": "museum"} for c in self.catalogs.values()
        ]

    # ---- Samsung catalog: what the TV already has --------------------------

    def samsung_artworks(self) -> list[Artwork]:
        items = self.frame.tv.artworks(None)
        return [a for a in items if a.content_id.startswith("SAM-") or a.category_id == SAMSUNG_CATEGORY]

    def thumbnail(self, content_id: str) -> bytes:
        return self.frame.tv.artwork_thumbnail(content_id)

    # ---- museum catalogs ----------------------------------------------------

    def _catalog(self, source: str) -> ArtCatalog:
        try:
            return self.catalogs[source]
        except KeyError:
            raise ValueError(f"unknown catalog {source!r}; available: {', '.join(self.catalogs)}") from None

    def search(self, source: str, query: str, limit: int = 12) -> list[CatalogItem]:
        query = query.strip()
        if not query or len(query) > 100:
            raise ValueError("query must be 1..100 characters")
        if not 1 <= limit <= 50:
            raise ValueError("limit must be within 1..50")
        return self._catalog(source).search(query, limit)

    def send(self, source: str, item_id: str, matte: str = "none", show: bool = True) -> dict[str, Any]:
        """Download a museum work, upload it to the TV once, and show it."""
        key = f"{source}:{item_id}"
        cached = self.frame.settings.uploads.get(key)
        if cached and any(a.content_id == cached for a in self.frame.tv.artworks(None)):
            if show:
                self.frame.show_artwork(cached)
            return {"content_id": cached, "cached": True}

        item = self._catalog(source).get(item_id)
        data, file_type = self._download(item)
        content_id = self.frame.upload_artwork(data, f"{source}-{item_id}.{file_type}", matte, show)
        self.frame.settings.uploads[key] = content_id
        self.frame.settings.save()
        return {"content_id": content_id, "cached": False, "item": item.to_dict()}

    def send_random(self, source: str, query: str, matte: str = "none") -> dict[str, Any]:
        items = self.search(source, query, limit=20)
        if not items:
            raise CatalogError(f"{source}: nothing found for {query!r}")
        item = self._rng.choice(items)
        return self.send(source, item.item_id, matte)

    def _download(self, item: CatalogItem) -> tuple[bytes, str]:
        catalog = self._catalog(item.source)
        errors = []
        for url in item.image_urls:
            try:
                data, file_type = fit_for_frame(catalog.download(url, MAX_DOWNLOAD_BYTES))
            except (CatalogError, ValueError) as exc:
                errors.append(str(exc))
                continue
            if len(data) <= MAX_UPLOAD_BYTES:
                return data, file_type
            errors.append(f"{len(data) // 1048576} MB after processing")
        raise CatalogError(f"{item.source} {item.item_id}: no usable image ({'; '.join(errors) or 'no urls'})")

    # ---- live self-check ----------------------------------------------------

    def check(self, query: str = "landscape") -> list[dict[str, Any]]:
        """Hit every museum API for real: search + download one image. Does not touch the TV."""
        report = []
        for source, catalog in self.catalogs.items():
            row: dict[str, Any] = {"source": source, "ok": False}
            try:
                items = catalog.search(query, 3)
                row["found"] = len(items)
                if items:
                    data, file_type = self._download(catalog.get(items[0].item_id))
                    row.update(ok=True, sample=items[0].title, bytes=len(data), type=file_type)
                else:
                    row["error"] = "search returned no public-domain images"
            except (CatalogError, ValueError) as exc:
                row["error"] = str(exc)
            report.append(row)
        return report
