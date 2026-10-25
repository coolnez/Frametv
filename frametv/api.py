"""HTTP API + single-page remote (served at /)."""

from __future__ import annotations

import hmac
from importlib.resources import files
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from .domain import TVError
from .service import ALLOWED_KEYS, SLIDESHOW_CATEGORIES, FrameService


class KeyIn(BaseModel):
    hold_seconds: float = Field(0, ge=0, le=5)


class FavoriteIn(BaseModel):
    app_id: str = Field(min_length=1, max_length=128)
    name: str | None = Field(None, max_length=64)
    app_type: str | None = None


class BrightnessIn(BaseModel):
    value: int = Field(ge=1, le=10)


class SlideshowIn(BaseModel):
    minutes: int = Field(ge=0, le=10080)
    shuffle: bool = True
    category_id: str = "MY-C0002"


def create_app(service: FrameService) -> FastAPI:
    app = FastAPI(title="FrameTV", version="0.1.0")
    index_html = files("frametv").joinpath("web/index.html").read_text(encoding="utf-8")

    def auth(x_api_token: str | None = Header(None), token: str | None = Query(None)) -> None:
        expected = service.settings.api_token
        if not expected:
            return
        supplied = x_api_token or token or ""
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            raise HTTPException(401, "invalid or missing API token")

    @app.exception_handler(TVError)
    async def tv_error(_: Request, exc: TVError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=502)

    @app.exception_handler(ValueError)
    async def bad_value(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index() -> str:
        return index_html

    api = FastAPI()  # mounted sub-app so auth applies to every /api route
    api.add_exception_handler(TVError, tv_error)
    api.add_exception_handler(ValueError, bad_value)
    app.mount("/api", api)
    deps = [Depends(auth)]
    ok = {"ok": True}

    @api.get("/status", dependencies=deps)
    def status() -> dict[str, Any]:
        return service.status().to_dict()

    @api.get("/meta", dependencies=deps)
    def meta() -> dict[str, Any]:
        return {"keys": sorted(ALLOWED_KEYS), "slideshow_categories": SLIDESHOW_CATEGORIES}

    @api.post("/power/on", dependencies=deps)
    def power_on() -> dict[str, Any]:
        return service.power_on().to_dict()

    @api.post("/power/off", dependencies=deps)
    def power_off() -> dict[str, Any]:
        service.power_off()
        return ok

    @api.post("/mode/art", dependencies=deps)
    def mode_art() -> dict[str, Any]:
        service.art_mode()
        return ok

    @api.post("/mode/tv", dependencies=deps)
    def mode_tv() -> dict[str, Any]:
        service.tv_mode()
        return ok

    @api.post("/key/{key}", dependencies=deps)
    def key(key: str, body: KeyIn | None = None) -> dict[str, Any]:
        service.press(key, body.hold_seconds if body else 0)
        return ok

    @api.get("/apps", dependencies=deps)
    def apps() -> list[dict[str, Any]]:
        return [a.to_dict() for a in service.installed_apps()]

    @api.get("/favorites", dependencies=deps)
    def favorites() -> list[dict[str, Any]]:
        return [a.to_dict() for a in service.favorites()]

    @api.post("/favorites", dependencies=deps)
    def add_favorite(body: FavoriteIn) -> dict[str, Any]:
        return service.add_favorite(body.app_id, body.name, body.app_type).to_dict()

    @api.delete("/favorites/{app_id}", dependencies=deps)
    def remove_favorite(app_id: str) -> dict[str, Any]:
        service.remove_favorite(app_id)
        return ok

    @api.post("/apps/{app_id}/launch", dependencies=deps)
    def launch(app_id: str) -> dict[str, Any]:
        return service.launch(app_id).to_dict()

    @api.post("/apps/{app_id}/close", dependencies=deps)
    def close(app_id: str) -> dict[str, Any]:
        service.close(app_id)
        return ok

    @api.get("/art", dependencies=deps)
    def art(category_id: str | None = None) -> list[dict[str, Any]]:
        return [a.to_dict() for a in service.artworks(category_id)]

    @api.post("/art/upload", dependencies=deps)
    async def upload(
        request: Request,
        filename: str = Query(..., max_length=255),
        matte: str = Query("none", max_length=64),
        show: bool = True,
    ) -> dict[str, Any]:
        # Raw image body (Content-Type: image/*) - avoids a multipart dependency.
        data = await request.body()
        return {"content_id": service.upload_artwork(data, filename, matte, show)}

    @api.post("/art/brightness", dependencies=deps)
    def brightness(body: BrightnessIn) -> dict[str, Any]:
        service.set_brightness(body.value)
        return ok

    @api.post("/art/slideshow", dependencies=deps)
    def slideshow(body: SlideshowIn) -> dict[str, Any]:
        service.set_slideshow(body.minutes, body.shuffle, body.category_id)
        return ok

    @api.post("/art/{content_id}/show", dependencies=deps)
    def show(content_id: str) -> dict[str, Any]:
        service.show_artwork(content_id)
        return ok

    @api.delete("/art/{content_id}", dependencies=deps)
    def delete(content_id: str) -> dict[str, Any]:
        service.delete_artwork(content_id)
        return ok

    return app
