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


def comment_hits(story_id, created_ats):
    return [{"story_id": story_id, "created_at_i": c} for c in created_ats]


async def test_comment_story_ids_since_pages_with_a_time_cursor_not_page_numbers():
    """Algolia silently caps page-number paging at 1000 hits, so page by created_at_i."""
    filters_seen = []

    def handler(req):
        qs = parse_qs(req.url.query.decode())
        per_page = int(qs["hitsPerPage"][0])
        filters_seen.append(qs["numericFilters"][0])
        assert "page" not in qs
        if len(filters_seen) == 1:
            return {"hits": comment_hits(10, range(5000, 5000 - per_page, -1))}
        if len(filters_seen) == 2:
            return {"hits": comment_hits(11, range(4000, 4000 - per_page, -1))}
        return {"hits": comment_hits(12, [3000])}  # short page: stop after this

    ids = await algolia(handler).comment_story_ids_since(since=123)

    assert filters_seen == [
        "created_at_i>123",
        f"created_at_i>123,created_at_i<{5000 - 999}",
        f"created_at_i>123,created_at_i<{4000 - 999}",
    ]
    assert ids.count(10) == 1000 and ids.count(11) == 1000 and ids.count(12) == 1


async def test_comment_story_ids_since_stops_on_empty_page():
    calls = []

    def handler(req):
        calls.append(1)
        return {"hits": []}

    assert await algolia(handler).comment_story_ids_since(since=0) == []
    assert len(calls) == 1


async def test_comment_story_ids_since_stops_at_page_cap_to_respect_rate_limit():
    calls = []

    def handler(req):
        calls.append(1)
        per_page = int(parse_qs(req.url.query.decode())["hitsPerPage"][0])
        return {"hits": comment_hits(1, range(10_000 - len(calls) * per_page, 0, -1)[:per_page])}

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


def item(id, type="comment", text="<p>hi</p>", children=(), **extra):
    base = {
        "id": id,
        "type": type,
        "author": "ann",
        "text": text,
        "created_at_i": 1_800_000_000,
        "children": list(children),
    }
    base.update(extra)
    return base


async def test_thread_parses_story_and_nested_comments():
    seen = {}

    def handler(req):
        seen["path"] = req.url.path
        return item(
            7,
            type="story",
            text=None,
            title="A story",
            url="https://example.com/a",
            points=55,
            children=[item(8, children=[item(9, text="<p>reply</p>")]), item(10, text=None)],
        )

    thread = await algolia(handler).thread(7)

    assert seen["path"] == "/api/v1/items/7"
    assert thread.story == Story(7, "A story", "https://example.com/a", "ann", 55, 3, 1_800_000_000)
    assert [c.id for c in thread.comments] == [8, 10]
    assert thread.comments[0].children[0].text_html == "<p>reply</p>"
    assert thread.comments[1].text_html is None


async def test_thread_counts_only_comments_not_the_story():
    client = algolia(lambda req: item(1, type="story", text=None, title="t", points=1, children=[item(2), item(3)]))

    thread = await client.thread(1)

    assert thread.story.num_comments == 2


async def test_thread_raises_not_found_for_missing_item():
    transport = httpx.MockTransport(lambda req: httpx.Response(404, json={"error": "not found"}))
    client = HackerNewsClient(httpx.AsyncClient(transport=transport))

    from hn_browser.hn_client import ItemNotFound

    with pytest.raises(ItemNotFound):
        await client.thread(123)


@pytest.mark.parametrize("newest_first, expected_path", [(False, "/api/v1/search"), (True, "/api/v1/search_by_date")])
async def test_search_stories_sends_query_with_story_tag(newest_first, expected_path):
    seen = {}

    def handler(req):
        seen["path"] = req.url.path
        seen["qs"] = parse_qs(req.url.query.decode())
        return {"hits": [story_hit(3), story_hit(4)]}

    stories = await algolia(handler).search_stories("rust grep", newest_first=newest_first)

    assert seen["path"] == expected_path
    assert seen["qs"]["query"] == ["rust grep"]
    assert seen["qs"]["tags"] == ["story"]
    assert seen["qs"]["hitsPerPage"] == ["100"]
    assert [s.id for s in stories] == [3, 4]
