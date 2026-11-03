"""Orderings for search results.

Algolia can rank by relevance or by date; ordering by points or comments
is applied here to the page of results it returns.
"""

from collections.abc import Callable
from dataclasses import dataclass

from hn_browser.ranking import Story


@dataclass(frozen=True)
class Sort:
    key: str
    label: str
    newest_first: bool  # ask Algolia's date-ordered endpoint instead of relevance
    key_fn: Callable[[Story], tuple] | None  # None keeps Algolia's order


SORTS: dict[str, Sort] = {
    s.key: s
    for s in [
        Sort("relevance", "Relevance", False, None),
        Sort("date", "Newest", True, lambda s: (-s.created_at, s.id)),
        Sort("points", "Most points", False, lambda s: (-s.points, -s.num_comments, s.id)),
        Sort("comments", "Most comments", False, lambda s: (-s.num_comments, -s.points, s.id)),
    ]
}


def order_results(stories: list[Story], sort_key: str) -> list[Story]:
    sort = SORTS[sort_key]
    if sort.key_fn is None:
        return list(stories)
    return sorted(stories, key=sort.key_fn)
