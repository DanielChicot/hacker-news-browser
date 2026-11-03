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
from hn_browser.hn_client import HackerNewsClient, ItemNotFound
from hn_browser.snapshot import Snapshot, load_snapshot
from hn_browser.thread import Thread, clean_html, prune_deleted

PACKAGE_DIR = Path(__file__).parent
SNAPSHOT_TTL_SECONDS = 180
USER_AGENT = "hn-browser (personal, non-commercial; https://codeberg.org/DanielChicot)"
DEFAULT_PRESET = "hot"

SnapshotLoader = Callable[[], Awaitable[Snapshot]]
ThreadLoader = Callable[[int], Awaitable[Thread]]


def _live_loaders(http: httpx.AsyncClient) -> tuple[SnapshotLoader, ThreadLoader]:
    client = HackerNewsClient(http)
    cache: TtlCache[Snapshot] = TtlCache(ttl_seconds=SNAPSHOT_TTL_SECONDS)

    async def load_feed() -> Snapshot:
        return await cache.get(lambda: load_snapshot(client, now=int(time.time())))

    return load_feed, client.thread


def create_app(
    snapshot_loader: SnapshotLoader | None = None,
    thread_loader: ThreadLoader | None = None,
) -> FastAPI:
    injected = snapshot_loader is not None and thread_loader is not None
    state: dict[str, Callable] = {}
    if injected:
        state["load"], state["thread"] = snapshot_loader, thread_loader

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if injected:
            yield
            return
        async with httpx.AsyncClient(timeout=15, headers={"User-Agent": USER_AGENT}) as http:
            state["load"], state["thread"] = _live_loaders(http)
            yield

    app = FastAPI(title="HN Browser", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")
    templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")
    templates.env.filters["domain"] = domain_of
    templates.env.filters["hn_url"] = hn_item_url
    templates.env.filters["clean"] = clean_html

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
                "active_preset": preset_key,
                "age": lambda created_at: age_label(created_at, now=snapshot.now),
            },
        )

    @app.get("/story/{story_id}", response_class=HTMLResponse)
    async def story_page(request: Request, story_id: int) -> HTMLResponse:
        try:
            thread = await state["thread"](story_id)
        except ItemNotFound:
            raise HTTPException(status_code=404)
        thread = Thread(thread.story, prune_deleted(thread.comments), thread.fetched_at)
        now = thread.fetched_at
        return templates.TemplateResponse(
            request,
            "story.html",
            {
                "thread": thread,
                "presets": PRESETS.values(),
                "active_preset": None,
                "age": lambda created_at: age_label(created_at, now=now),
            },
        )

    return app


app = create_app()
