"""Read-only access to Hacker News via the Algolia HN Search API.

Only the public API is used; the HN website itself is never fetched.
Algolia allows 10,000 requests per hour per IP, so comment paging is capped.
"""

from collections.abc import Iterable

import time

import httpx

from hn_browser.ranking import Story
from hn_browser.thread import Comment, Thread, count_comments

ALGOLIA_BASE_URL = "https://hn.algolia.com/api/v1"
PAGE_SIZE = 1000
SEARCH_PAGE_SIZE = 100
DEFAULT_MAX_COMMENT_PAGES = 6


class ItemNotFound(LookupError):
    pass


def _comment_from_item(item: dict) -> Comment:
    return Comment(
        id=int(item["id"]),
        author=item.get("author") or "",
        text_html=item.get("text"),
        created_at=int(item.get("created_at_i") or 0),
        children=[_comment_from_item(c) for c in item.get("children", [])],
    )


def _story_from_hit(hit: dict) -> Story:
    return Story(
        id=int(hit["objectID"]),
        title=hit.get("title") or "(untitled)",
        url=hit.get("url") or None,
        author=hit.get("author") or "",
        points=hit.get("points") or 0,
        num_comments=hit.get("num_comments") or 0,
        created_at=int(hit.get("created_at_i") or 0),
    )


class HackerNewsClient:
    def __init__(self, http: httpx.AsyncClient, base_url: str = ALGOLIA_BASE_URL):
        self._http = http
        self._base_url = base_url.rstrip("/")

    async def _get(self, endpoint: str, params: dict | None = None) -> dict:
        response = await self._http.get(f"{self._base_url}/{endpoint}", params=params)
        if response.status_code == 404:
            raise ItemNotFound(endpoint)
        response.raise_for_status()
        return response.json()

    async def thread(self, story_id: int) -> Thread:
        """A story with its full comment tree, from the items endpoint."""
        item = await self._get(f"items/{story_id}")
        comments = [_comment_from_item(c) for c in item.get("children", [])]
        story = Story(
            id=int(item["id"]),
            title=item.get("title") or "(untitled)",
            url=item.get("url") or None,
            author=item.get("author") or "",
            points=item.get("points") or 0,
            num_comments=count_comments(comments),
            created_at=int(item.get("created_at_i") or 0),
        )
        return Thread(story=story, comments=comments, fetched_at=int(time.time()))

    async def stories_since(self, since: int) -> list[Story]:
        """Stories created after `since` (epoch seconds).

        Uses the relevance-sorted endpoint so that, if the window holds more
        than one page, the popular stories are the ones kept.
        """
        data = await self._get(
            "search",
            {
                "tags": "story",
                "numericFilters": f"created_at_i>{since}",
                "hitsPerPage": PAGE_SIZE,
            },
        )
        return [_story_from_hit(h) for h in data["hits"]]

    async def comment_story_ids_since(
        self, since: int, max_pages: int = DEFAULT_MAX_COMMENT_PAGES
    ) -> list[int]:
        """The story id of every comment posted after `since`, one entry per comment.

        Algolia silently caps page-number paging at 1000 hits, so this walks
        backwards in time instead: each page asks for comments older than the
        oldest one seen so far, and stops at the first short page.
        """
        ids: list[int] = []
        before: int | None = None
        for _ in range(max_pages):
            filters = f"created_at_i>{since}"
            if before is not None:
                filters += f",created_at_i<{before}"
            data = await self._get(
                "search_by_date",
                {"tags": "comment", "numericFilters": filters, "hitsPerPage": PAGE_SIZE},
            )
            hits = data["hits"]
            ids.extend(int(h["story_id"]) for h in hits if h.get("story_id"))
            if len(hits) < PAGE_SIZE:
                break
            before = min(int(h["created_at_i"]) for h in hits)
        return ids

    async def search_stories(self, query: str, newest_first: bool = False) -> list[Story]:
        """Full-text search over stories, in Algolia's relevance or date order."""
        data = await self._get(
            "search_by_date" if newest_first else "search",
            {"query": query, "tags": "story", "hitsPerPage": SEARCH_PAGE_SIZE},
        )
        return [_story_from_hit(h) for h in data["hits"]]

    async def stories_by_ids(self, ids: Iterable[int]) -> list[Story]:
        ids = list(ids)
        if not ids:
            return []
        tag_filter = ",".join(f"story_{i}" for i in ids)
        data = await self._get(
            "search",
            {"tags": f"story,({tag_filter})", "hitsPerPage": len(ids)},
        )
        return [_story_from_hit(h) for h in data["hits"]]
