import pytest

from hn_browser.format import age_label, domain_of, hn_item_url

NOW = 1_800_000_000


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.example.com/a/b?c=1", "example.com"),
        ("http://blog.example.org/post", "blog.example.org"),
        ("https://github.com/HackerNews/API", "github.com/HackerNews"),
        (None, "news.ycombinator.com"),
    ],
)
def test_domain_of_strips_www_and_keeps_github_owner(url, expected):
    assert domain_of(url) == expected


@pytest.mark.parametrize(
    "seconds_ago, expected",
    [
        (30, "just now"),
        (59 * 60, "59m ago"),
        (60 * 60, "1h ago"),
        (5 * 3600 + 1800, "5h ago"),
        (26 * 3600, "1d ago"),
        (3 * 86400, "3d ago"),
        (29 * 86400, "29d ago"),
        (30 * 86400, "1mo ago"),
        (11 * 30 * 86400, "11mo ago"),
        (365 * 86400, "1y ago"),
        (2064 * 86400, "5y ago"),
    ],
)
def test_age_label_rounds_down_to_the_largest_unit(seconds_ago, expected):
    assert age_label(NOW - seconds_ago, now=NOW) == expected


def test_hn_item_url():
    assert hn_item_url(123) == "https://news.ycombinator.com/item?id=123"
