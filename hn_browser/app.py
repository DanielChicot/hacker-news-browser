"""FastAPI application: one page per preset, all served from one cached snapshot."""

import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from hn_browser.cache import TtlCache
from hn_browser.feed import PRESETS, build_feed
from hn_browser.format import age_label, domain_of, hn_item_url
from hn_browser.hn_client import HackerNewsClient
from hn_browser.snapshot import Snapshot, load_snapshot

PACKAGE_DIR = Path(__file__).parent
SNAPSHOT_TTL_SECONDS = 180
USER_AGENT = "hn-browser (personal, non-commercial; https://codeberg.org/DanielChicot)"
DEFAULT_PRESET = "hot"

SnapshotLoader = Callable[[], Awaitable[Snapshot]]


def _live_loader(http: httpx.AsyncClient) -> SnapshotLoader:
    client = HackerNewsClient(http)
    cache: TtlCache[Snapshot] = TtlCache(ttl_seconds=SNAPSHOT_TTL_SECONDS)

    async def load() -> Snapshot:
        return await cache.get(lambda: load_snapshot(client, now=int(time.time())))

    return load


def create_app(snapshot_loader: SnapshotLoader | None = None) -> FastAPI:
    state: dict[str, SnapshotLoader] = {}
    if snapshot_loader is not None:
        state["load"] = snapshot_loader

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if snapshot_loader is not None:
            yield
            return
        async with httpx.AsyncClient(timeout=15, headers={"User-Agent": USER_AGENT}) as http:
            state["load"] = _live_loader(http)
            yield

    app = FastAPI(title="HN Browser", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")
    templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")
    templates.env.filters["domain"] = domain_of
    templates.env.filters["hn_url"] = hn_item_url

    @app.get("/")
    async def root() -> RedirectResponse:
        return RedirectResponse(url=f"/{DEFAULT_PRESET}")

    @app.get("/{preset_key}", response_class=HTMLResponse)
    async def feed_page(request: Request, preset_key: str) -> HTMLResponse:
        if preset_key not in PRESETS:
            raise HTTPException(status_code=404)
        snapshot = await state["load"]()
        feed = build_feed(snapshot, preset_key)
        return templates.TemplateResponse(
            request,
            "feed.html",
            {
                "feed": feed,
                "presets": PRESETS.values(),
                "age": lambda created_at: age_label(created_at, now=snapshot.now),
            },
        )

    return app


app = create_app()
