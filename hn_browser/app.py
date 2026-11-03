"""FastAPI application: feed presets, story threads and search, all server rendered."""

import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Protocol

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from hn_browser.cache import TtlCache
from hn_browser.feed import PRESETS, build_feed
from hn_browser.format import age_label, domain_of, hn_item_url
from hn_browser.hn_client import HackerNewsClient, ItemNotFound
from hn_browser.ranking import Story
from hn_browser.search import SORTS, order_results
from hn_browser.snapshot import Snapshot, load_snapshot
from hn_browser.thread import Thread, clean_html, count_comments, prune_deleted

PACKAGE_DIR = Path(__file__).parent
SNAPSHOT_TTL_SECONDS = 180
USER_AGENT = "hn-browser (personal, non-commercial; https://github.com/DanielChicot/hacker-news-browser)"
DEFAULT_PRESET = "hot"
SortKey = Literal["relevance", "date", "points", "comments"]


class Backend(Protocol):
    """Everything the pages need from Hacker News; swapped for a fake in tests."""

    async def snapshot(self) -> Snapshot: ...
    async def thread(self, story_id: int) -> Thread: ...
    async def search(self, query: str, newest_first: bool) -> list[Story]: ...


class LiveBackend:
    def __init__(self, http: httpx.AsyncClient):
        self._client = HackerNewsClient(http)
        self._cache: TtlCache[Snapshot] = TtlCache(ttl_seconds=SNAPSHOT_TTL_SECONDS)

    async def snapshot(self) -> Snapshot:
        return await self._cache.get(lambda: load_snapshot(self._client, now=int(time.time())))

    async def thread(self, story_id: int) -> Thread:
        return await self._client.thread(story_id)

    async def search(self, query: str, newest_first: bool) -> list[Story]:
        return await self._client.search_stories(query, newest_first=newest_first)


def create_app(backend: Backend | None = None) -> FastAPI:
    state: dict[str, Backend] = {}
    if backend is not None:
        state["backend"] = backend

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if backend is not None:
            yield
            return
        async with httpx.AsyncClient(timeout=15, headers={"User-Agent": USER_AGENT}) as http:
            state["backend"] = LiveBackend(http)
            yield

    app = FastAPI(title="HN Browser", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")
    templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")
    templates.env.filters["domain"] = domain_of
    templates.env.filters["hn_url"] = hn_item_url
    templates.env.filters["clean"] = clean_html
    templates.env.filters["descendants"] = count_comments

    def render(request: Request, template: str, now: int, **context) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            template,
            {
                "presets": PRESETS.values(),
                "active_preset": None,
                "query": "",
                "age": lambda created_at: age_label(created_at, now=now),
                **context,
            },
        )

    @app.get("/")
    async def root() -> RedirectResponse:
        return RedirectResponse(url=f"/{DEFAULT_PRESET}")

    @app.get("/search", response_class=HTMLResponse)
    async def search_page(
        request: Request, q: str = "", sort: SortKey = "relevance"
    ) -> HTMLResponse:
        query = q.strip()
        results = order_results(await state["backend"].search(query, SORTS[sort].newest_first), sort) if query else []
        return render(
            request,
            "search.html",
            now=int(time.time()),
            query=query,
            results=results,
            sorts=SORTS.values(),
            active_sort=sort,
        )

    @app.get("/story/{story_id}", response_class=HTMLResponse)
    async def story_page(request: Request, story_id: int) -> HTMLResponse:
        try:
            thread = await state["backend"].thread(story_id)
        except ItemNotFound:
            raise HTTPException(status_code=404)
        thread = Thread(thread.story, prune_deleted(thread.comments), thread.fetched_at)
        return render(request, "story.html", now=thread.fetched_at, thread=thread)

    @app.get("/{preset_key}", response_class=HTMLResponse)
    async def feed_page(request: Request, preset_key: str) -> HTMLResponse:
        if preset_key not in PRESETS:
            raise HTTPException(status_code=404)
        snapshot = await state["backend"].snapshot()
        feed = build_feed(snapshot, preset_key)
        return render(request, "feed.html", now=snapshot.now, feed=feed, active_preset=preset_key)

    return app


app = create_app()
