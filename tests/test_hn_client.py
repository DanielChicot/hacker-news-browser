import json
from urllib.parse import parse_qs

import httpx
import pytest

from hn_browser.hn_client import HackerNewsClient
from hn_browser.ranking import Story


def algolia(handler):
    """Build a client whose HTTP goes to `handler(request) -> dict`."""
    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json=handler(req))
    )
    return HackerNewsClient(httpx.AsyncClient(transport=transport))


def story_hit(id, **overrides):
    hit = {
        "objectID": str(id),
        "title": f"Story {id}",
        "url": f"https://example.com/{id}",
        "author": "alice",
        "points": 42,
        "num_comments": 7,
        "created_at_i": 1_800_000_000,
    }
    hit.update(overrides)
    return hit


async def test_stories_since_queries_story_tag_with_time_filter():
    seen = {}

    def handler(req):
        seen["path"] = req.url.path
        seen["qs"] = parse_qs(req.url.query.decode())
        return {"hits": [story_hit(1)], "nbPages": 1, "page": 0}

    stories = await algolia(handler).stories_since(since=1_799_000_000)

    assert seen["path"] == "/api/v1/search"
    assert seen["qs"]["tags"] == ["story"]
    assert seen["qs"]["numericFilters"] == ["created_at_i>1799000000"]
    assert stories == [
        Story(
            id=1,
            title="Story 1",
            url="https://example.com/1",
            author="alice",
            points=42,
            num_comments=7,
            created_at=1_800_000_000,
        )
    ]


@pytest.mark.parametrize(
    "overrides, expected_url, expected_points, expected_comments",
    [
        ({"url": None}, None, 42, 7),
        ({"points": None, "num_comments": None}, "https://example.com/1", 0, 0),
    ],
)
async def test_stories_since_tolerates_missing_fields(
    overrides, expected_url, expected_points, expected_comments
):
    client = algolia(lambda req: {"hits": [story_hit(1, **overrides)], "nbPages": 1})

    [s] = await client.stories_since(since=0)

    assert (s.url, s.points, s.num_comments) == (
        expected_url,
        expected_points,
        expected_comments,
    )


async def test_comment_story_ids_since_follows_every_page():
    pages = {
        0: {"hits": [{"story_id": 10}, {"story_id": 10}], "nbPages": 3, "page": 0},
        1: {"hits": [{"story_id": 11}], "nbPages": 3, "page": 1},
        2: {"hits": [{"story_id": 10}], "nbPages": 3, "page": 2},
    }
    requested = []

    def handler(req):
        qs = parse_qs(req.url.query.decode())
        requested.append((req.url.path, qs["tags"][0], qs["numericFilters"][0]))
        return pages[int(qs.get("page", ["0"])[0])]

    ids = await algolia(handler).comment_story_ids_since(since=123)

    assert ids == [10, 10, 11, 10]
    assert requested == [("/api/v1/search_by_date", "comment", "created_at_i>123")] * 3


async def test_comment_story_ids_since_stops_at_page_cap_to_respect_rate_limit():
    calls = []

    def handler(req):
        calls.append(1)
        return {"hits": [{"story_id": 1}], "nbPages": 50, "page": len(calls) - 1}

    await algolia(handler).comment_story_ids_since(since=0, max_pages=4)

    assert len(calls) == 4


async def test_stories_by_ids_uses_or_tag_filter_and_preserves_all_hits():
    seen = {}

    def handler(req):
        seen["qs"] = parse_qs(req.url.query.decode())
        return {"hits": [story_hit(5), story_hit(9)], "nbPages": 1}

    stories = await algolia(handler).stories_by_ids([5, 9])

    assert seen["qs"]["tags"] == ["story,(story_5,story_9)"]
    assert seen["qs"]["hitsPerPage"] == ["2"]
    assert [s.id for s in stories] == [5, 9]


async def test_stories_by_ids_with_no_ids_makes_no_request():
    calls = []
    client = algolia(lambda req: calls.append(req) or {"hits": []})

    assert await client.stories_by_ids([]) == []
    assert calls == []
