"""Catalog tests. Museum responses below are trimmed samples in each API's documented format;
`frametv catalog-check` verifies the live services."""

from __future__ import annotations

import io
import random

import pytest
from fastapi.testclient import TestClient

from frametv.adapters.catalogs import ArtInstituteChicago, ClevelandMuseum, MetropolitanMuseum
from frametv.adapters.fake import FakeFrameGateway
from frametv.adapters.http import UrllibHttpClient
from frametv.api import create_app
from frametv.catalog_service import CatalogService
from frametv.config import Settings
from frametv.domain import CatalogError
from frametv.imaging import FRAME_SIZE, fit_for_frame
from frametv.service import FrameService



def _jpeg() -> bytes:
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (64, 36), "navy").save(out, "JPEG")
    return out.getvalue()


JPEG = _jpeg()

AIC_SEARCH = {
    "data": [
        {"id": 16568, "title": "Water Lilies", "artist_display": "Claude Monet\nFrench, 1840-1926",
         "date_display": "1906", "image_id": "3c27b499-af56-f0d5-93b5-a7f2f1ad5813", "is_public_domain": True},
        {"id": 1, "title": "No image", "image_id": None, "is_public_domain": True},
        {"id": 2, "title": "In copyright", "image_id": "abc", "is_public_domain": False},
    ],
    "config": {"iiif_url": "https://www.artic.edu/iiif/2"},
}
MET_SEARCH = {"total": 3, "objectIDs": [437133, 1, 438003]}
MET_OBJECTS = {
    437133: {"objectID": 437133, "title": "Garden at Sainte-Adresse", "artistDisplayName": "Claude Monet",
             "objectDate": "1867", "isPublicDomain": True,
             "primaryImage": "https://images.metmuseum.org/CRDImages/ep/original/DT1876.jpg",
             "primaryImageSmall": "https://images.metmuseum.org/CRDImages/ep/web-large/DT1876.jpg"},
    1: {"objectID": 1, "title": "No image", "isPublicDomain": True, "primaryImage": "", "primaryImageSmall": ""},
    438003: {"objectID": 438003, "title": "Bridge over a Pond of Water Lilies", "artistDisplayName": "Claude Monet",
             "objectDate": "1899", "isPublicDomain": True,
             "primaryImage": "https://images.metmuseum.org/CRDImages/ep/original/DT1891.jpg",
             "primaryImageSmall": ""},
}
CMA_ITEM = {
    "id": 135382, "title": "Water Lilies (Agapanthus)", "creation_date": "c. 1915-1926",
    "share_license_status": "CC0", "creators": [{"description": "Claude Monet (French, 1840-1926)"}],
    "images": {
        "web": {"url": "https://openaccess-cdn.clevelandart.org/1960.81/1960.81_web.jpg"},
        "print": {"url": "https://openaccess-cdn.clevelandart.org/1960.81/1960.81_print.jpg"},
    },
}


class FakeHttp:
    def __init__(self, routes: dict[str, object], files: dict[str, bytes | Exception] | None = None) -> None:
        self.routes = routes
        self.files = files or {}
        self.calls: list[tuple[str, dict | None]] = []

    def get_json(self, url, params=None):
        self.calls.append((url, params))
        for prefix, body in self.routes.items():
            if url == prefix:
                if isinstance(body, Exception):
                    raise body
                return body
        raise CatalogError(f"404 {url}")

    def get_bytes(self, url, max_bytes):
        data = self.files.get(url, JPEG)
        if isinstance(data, Exception):
            raise data
        return data


# ---- adapters --------------------------------------------------------------


def test_aic_search_keeps_only_public_domain_images():
    http = FakeHttp({"https://api.artic.edu/api/v1/artworks/search": AIC_SEARCH})
    items = ArtInstituteChicago(http).search("monet", 5)
    assert [i.item_id for i in items] == ["16568"]
    item = items[0]
    assert item.artist == "Claude Monet"
    assert item.image_urls[0].endswith("/3c27b499-af56-f0d5-93b5-a7f2f1ad5813/full/1686,/0/default.jpg")
    assert http.calls[0][1]["query[term][is_public_domain]"] == "true"


def test_aic_ignores_foreign_iiif_host():
    body = dict(AIC_SEARCH, config={"iiif_url": "https://evil.example/iiif"})
    items = ArtInstituteChicago(FakeHttp({"https://api.artic.edu/api/v1/artworks/search": body})).search("x", 5)
    assert items[0].image_urls[0].startswith("https://www.artic.edu/iiif/2/")


def test_met_search_fans_out_and_skips_imageless():
    base = "https://collectionapi.metmuseum.org/public/collection/v1"
    routes = {f"{base}/search": MET_SEARCH} | {f"{base}/objects/{k}": v for k, v in MET_OBJECTS.items()}
    items = MetropolitanMuseum(FakeHttp(routes)).search("monet", 5)
    assert [i.item_id for i in items] == ["437133", "438003"]
    assert items[0].image_urls == (MET_OBJECTS[437133]["primaryImage"], MET_OBJECTS[437133]["primaryImageSmall"])
    assert items[1].thumb_url == MET_OBJECTS[438003]["primaryImage"]


def test_met_search_handles_null_ids():
    url = "https://collectionapi.metmuseum.org/public/collection/v1/search"
    assert MetropolitanMuseum(FakeHttp({url: {"total": 0, "objectIDs": None}})).search("zzz", 5) == []


def test_cleveland_prefers_print_then_web():
    http = FakeHttp({
        "https://openaccess-api.clevelandart.org/api/artworks/": {"data": [CMA_ITEM]},
        "https://openaccess-api.clevelandart.org/api/artworks/135382": {"data": CMA_ITEM},
    })
    cma = ClevelandMuseum(http)
    [item] = cma.search("monet", 3)
    assert item.image_urls[0].endswith("_print.jpg") and item.image_urls[1].endswith("_web.jpg")
    assert cma.get("135382").title == "Water Lilies (Agapanthus)"
    assert http.calls[0][1]["cc0"] == "1"


@pytest.mark.parametrize("bad", ["../../etc", "1?x=1", "abc", ""])
def test_item_ids_must_be_numeric(bad):
    with pytest.raises(ValueError):
        ClevelandMuseum(FakeHttp({})).get(bad)


# ---- http client -----------------------------------------------------------


@pytest.mark.parametrize("url", ["http://api.artic.edu/x", "https://evil.example/x", "file:///etc/passwd"])
def test_http_client_refuses_unlisted_urls(url):
    with pytest.raises(CatalogError):
        UrllibHttpClient(frozenset({"api.artic.edu"})).get_bytes(url, 10)


# ---- imaging ---------------------------------------------------------------


def _png(size):
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", size, "white").save(out, "PNG")
    return out.getvalue()


def test_fit_for_frame_downscales_to_4k():
    pytest.importorskip("PIL")
    from PIL import Image

    data, ftype = fit_for_frame(_png((6000, 4000)))
    assert ftype == "jpg"
    with Image.open(io.BytesIO(data)) as img:
        assert img.width <= FRAME_SIZE[0] and img.height <= FRAME_SIZE[1]


@pytest.mark.parametrize("data", [b"<html>not an image</html>", JPEG[: len(JPEG) // 2]])
def test_fit_for_frame_rejects_non_images_and_truncated(data):
    with pytest.raises(ValueError):
        fit_for_frame(data)


# ---- service ---------------------------------------------------------------


@pytest.fixture
def tv():
    return FakeFrameGateway()


@pytest.fixture
def cma_http():
    return FakeHttp({
        "https://openaccess-api.clevelandart.org/api/artworks/": {"data": [CMA_ITEM]},
        "https://openaccess-api.clevelandart.org/api/artworks/135382": {"data": CMA_ITEM},
    })


@pytest.fixture
def cat(tv, tmp_path, cma_http):
    frame = FrameService(tv, Settings.load(tmp_path / "config.json"), sleep=lambda _: None)
    return CatalogService(frame, {"cleveland": ClevelandMuseum(cma_http)}, rng=random.Random(0))


def test_samsung_catalog_lists_store_works_only(cat):
    assert [a.content_id for a in cat.samsung_artworks()] == ["SAM-S0700", "SAM-S2701"]


def test_send_uploads_shows_and_caches(cat, tv):
    first = cat.send("cleveland", "135382", matte="shadowbox_polar")
    assert first["cached"] is False
    assert tv.current.content_id == first["content_id"] and tv.art_mode
    assert Settings.load(cat.frame.settings.path).uploads == {"cleveland:135382": first["content_id"]}

    uploads_before = len(tv.art)
    second = cat.send("cleveland", "135382")
    assert second == {"content_id": first["content_id"], "cached": True}
    assert len(tv.art) == uploads_before


def test_send_reuploads_when_deleted_on_tv(cat, tv):
    cid = cat.send("cleveland", "135382")["content_id"]
    tv.delete_artwork(cid)
    assert cat.send("cleveland", "135382")["cached"] is False


def test_download_falls_back_to_smaller_rendition(cat, tv, cma_http):
    cma_http.files[CMA_ITEM["images"]["print"]["url"]] = CatalogError("image too large (95 MB)")
    assert cat.send("cleveland", "135382")["cached"] is False


def test_download_fails_when_nothing_usable(cat, cma_http):
    for key in ("print", "web"):
        cma_http.files[CMA_ITEM["images"][key]["url"]] = b"<html>"
    with pytest.raises(CatalogError, match="no usable image"):
        cat.send("cleveland", "135382")


def test_send_random_and_search_validation(cat):
    assert cat.send_random("cleveland", "monet")["content_id"].startswith("MY_")
    with pytest.raises(ValueError):
        cat.search("cleveland", " ")
    with pytest.raises(ValueError):
        cat.search("louvre", "monet")


def test_check_reports_per_source(cat, cma_http):
    assert cat.check()[0] | {"bytes": 0} == {
        "source": "cleveland", "ok": True, "found": 1, "sample": "Water Lilies (Agapanthus)", "bytes": 0, "type": "jpg"
    }
    cma_http.routes["https://openaccess-api.clevelandart.org/api/artworks/"] = CatalogError("HTTP 503")
    assert cat.check()[0] == {"source": "cleveland", "ok": False, "error": "HTTP 503"}


# ---- API -------------------------------------------------------------------


@pytest.fixture
def client(cat):
    return TestClient(create_app(cat.frame, cat))


def test_api_catalog_flow(client, tv):
    sources = [c["id"] for c in client.get("/api/catalogs").json()]
    assert sources == ["samsung", "cleveland"]
    assert len(client.get("/api/catalogs/samsung/items").json()) == 2
    found = client.get("/api/catalogs/cleveland/search", params={"q": "monet"}).json()
    assert found[0]["item_id"] == "135382"
    sent = client.post("/api/catalogs/cleveland/items/135382/send", json={"matte": "none"}).json()
    assert tv.current.content_id == sent["content_id"]


def test_api_thumbnail_and_errors(client, cma_http):
    r = client.get("/api/art/SAM-S0700/thumbnail")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert client.get("/api/catalogs/louvre/search", params={"q": "x"}).status_code == 400
    cma_http.routes["https://openaccess-api.clevelandart.org/api/artworks/"] = CatalogError("HTTP 503")
    assert client.get("/api/catalogs/cleveland/search", params={"q": "x"}).status_code == 502
