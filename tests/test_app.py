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
            Comment(12, "cat", "<p>A reply</p>", NOW - HOUR, [
                Comment(14, "dan", "<p>Nested reply</p>", NOW - HOUR),
            ]),
        ]),
        Comment(13, "", None, NOW - HOUR),  # deleted leaf, should not render
    ],
    fetched_at=NOW,
)


class FakeBackend:
    def __init__(self):
        self.searches = []

    async def snapshot(self):
        return SNAPSHOT

    async def thread(self, story_id):
        if story_id != 1:
            raise ItemNotFound(str(story_id))
        return THREAD

    async def search(self, query, newest_first):
        self.searches.append((query, newest_first))
        return SNAPSHOT.stories


@pytest.fixture
def backend():
    return FakeBackend()


@pytest.fixture
def client(backend):
    return TestClient(create_app(backend=backend))


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


def test_replies_fold_as_a_subtree_labelled_with_descendant_count(client):
    html = client.get("/story/1").text

    assert html.count('<details class="replies" open>') == 2
    assert '<summary class="replies-toggle">2 replies</summary>' in html  # 12 and 14 under 11
    assert '<summary class="replies-toggle">1 reply</summary>' in html  # 14 under 12
    assert html.index("2 replies") < html.index("A reply") < html.index("1 reply") < html.index("Nested reply")


@pytest.mark.parametrize("path", ["/hot", "/story/1", "/search?q=x"])
def test_every_page_has_a_search_form_posting_to_search(client, path):
    html = client.get(path).text

    assert '<form class="search" action="/search" method="get" role="search">' in html
    assert 'name="q"' in html


def test_search_page_lists_results_and_passes_query_to_backend(client, backend):
    html = client.get("/search?q=rust+grep").text

    assert backend.searches == [("rust grep", False)]
    assert "Rust &lt;b&gt;rewrite&lt;/b&gt; of grep" in html
    assert "Ask HN: Favourite editor?" in html
    assert 'value="rust grep"' in html  # the box keeps the query


def test_search_sort_links_keep_the_query_and_mark_the_active_sort(client):
    html = client.get("/search?q=rust&sort=points").text

    assert 'class="pill active" href="/search?q=rust&amp;sort=points"' in html
    assert 'class="pill" href="/search?q=rust&amp;sort=date"' in html
    assert html.index("Rust &lt;b&gt;") < html.index("Ask HN")  # 120 points before 15


def test_search_by_comments_reorders_results(client):
    html = client.get("/search?q=rust&sort=comments").text

    assert html.index("Ask HN") < html.index("Rust &lt;b&gt;")  # 200 comments before 44


def test_search_by_date_asks_backend_for_newest_first(client, backend):
    client.get("/search?q=rust&sort=date")

    assert backend.searches == [("rust", True)]


def test_search_without_query_shows_prompt_and_calls_nothing(client, backend):
    response = client.get("/search")

    assert response.status_code == 200
    assert backend.searches == []
    assert "Search Hacker News" in response.text


def test_search_with_unknown_sort_is_422(client):
    assert client.get("/search?q=rust&sort=magic").status_code == 422
