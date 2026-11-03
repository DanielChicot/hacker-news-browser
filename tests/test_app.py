import pytest
from fastapi.testclient import TestClient

from hn_browser.app import create_app
from hn_browser.ranking import Story
from hn_browser.hn_client import ItemNotFound
from hn_browser.snapshot import Snapshot
from hn_browser.thread import Comment, Thread

NOW = 1_800_000_000
HOUR = 3600

SNAPSHOT = Snapshot(
    now=NOW,
    stories=[
        Story(1, "Rust <b>rewrite</b> of grep", "https://www.example.com/x", "ann", 120, 44, NOW - 3 * HOUR),
        Story(2, "Ask HN: Favourite editor?", None, "bob", 15, 200, NOW - 10 * HOUR),
    ],
    comment_story_ids=[2, 2, 2, 1],
)


THREAD = Thread(
    story=Story(1, "Rust <b>rewrite</b> of grep", "https://www.example.com/x", "ann", 120, 3, NOW - 3 * HOUR),
    comments=[
        Comment(11, "bob", "<p>Top level <i>comment</i><script>alert(1)</script></p>", NOW - 2 * HOUR, [
            Comment(12, "cat", "<p>A reply</p>", NOW - HOUR),
        ]),
        Comment(13, "", None, NOW - HOUR),  # deleted leaf, should not render
    ],
    fetched_at=NOW,
)


@pytest.fixture
def client():
    async def loader():
        return SNAPSHOT

    async def thread_loader(story_id):
        if story_id != 1:
            raise ItemNotFound(str(story_id))
        return THREAD

    return TestClient(create_app(snapshot_loader=loader, thread_loader=thread_loader))


def test_root_redirects_to_hot(client):
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/hot"


def test_unknown_preset_is_404(client):
    assert client.get("/nope").status_code == 404


def test_hot_page_lists_stories_in_rank_order_with_metric(client):
    html = client.get("/hot").text

    assert html.index("Ask HN: Favourite editor?") < html.index("Rust &lt;b&gt;rewrite&lt;/b&gt; of grep")
    assert "comments in 6h" in html
    assert ">3<" in html  # metric for story 2


def test_story_rows_link_out_and_back_to_hn(client):
    html = client.get("/top").text

    assert 'href="https://www.example.com/x"' in html
    assert 'href="/story/1"' in html  # comments link opens our own thread page
    assert 'href="/story/2"' in html  # Ask HN has no url: title also goes to our page
    assert "example.com" in html
    assert "3h ago" in html


def test_every_preset_renders_as_a_tab_and_marks_the_active_one(client):
    html = client.get("/rising").text

    for label in ["Hot now", "Discussed today", "Top today", "Rising"]:
        assert label in html
    assert 'class="tab active" href="/rising"' in html


def test_hero_stats_are_rendered(client):
    html = client.get("/hot").text

    assert "Comments in 6h" in html
    assert "Hottest thread" in html
    assert "Top points today" in html


def test_story_page_renders_sanitised_nested_comments(client):
    html = client.get("/story/1").text

    assert "Rust &lt;b&gt;rewrite&lt;/b&gt; of grep" in html
    assert 'href="https://www.example.com/x"' in html
    assert 'href="https://news.ycombinator.com/item?id=1"' in html
    assert "<p>Top level <i>comment</i></p>" in html
    assert "alert(1)" not in html
    assert html.index("Top level") < html.index("A reply")
    assert "bob" in html and "cat" in html
    assert "2h ago" in html
    assert "3 comments" in html


def test_story_page_omits_deleted_leaf_comments(client):
    html = client.get("/story/1").text

    assert "[deleted]" not in html


def test_story_page_is_404_for_unknown_story(client):
    assert client.get("/story/999").status_code == 404


def test_story_page_rejects_non_numeric_id(client):
    assert client.get("/story/abc").status_code == 422
