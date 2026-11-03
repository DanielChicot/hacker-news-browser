import pytest

from hn_browser.ranking import Story
from hn_browser.search import SORTS, order_results

NOW = 1_800_000_000


def story(id, points, num_comments, created_at):
    return Story(id, f"Story {id}", None, "x", points, num_comments, created_at)


RESULTS = [  # in Algolia relevance order
    story(1, points=10, num_comments=50, created_at=NOW - 300),
    story(2, points=90, num_comments=5, created_at=NOW - 100),
    story(3, points=40, num_comments=20, created_at=NOW - 200),
]


def test_sort_keys_in_display_order():
    assert list(SORTS) == ["relevance", "date", "points", "comments"]


@pytest.mark.parametrize(
    "sort, expected_order",
    [
        ("relevance", [1, 2, 3]),
        ("date", [2, 3, 1]),
        ("points", [2, 3, 1]),
        ("comments", [1, 3, 2]),
    ],
)
def test_order_results(sort, expected_order):
    assert [s.id for s in order_results(RESULTS, sort)] == expected_order


def test_order_results_rejects_unknown_sort():
    with pytest.raises(KeyError):
        order_results(RESULTS, "magic")


@pytest.mark.parametrize("sort, newest_first", [("relevance", False), ("points", False), ("comments", False), ("date", True)])
def test_only_date_sort_asks_algolia_for_newest_first(sort, newest_first):
    assert SORTS[sort].newest_first is newest_first
