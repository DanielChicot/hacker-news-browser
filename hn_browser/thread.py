"""A story's comment tree, and the pure helpers that shape it for display."""

from dataclasses import dataclass, field

import nh3

from hn_browser.ranking import Story

# The subset of HTML that Hacker News itself produces in comment bodies.
ALLOWED_TAGS = {"p", "i", "b", "em", "strong", "pre", "code", "a", "br", "blockquote"}
ALLOWED_ATTRIBUTES = {"a": {"href"}}
ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}


@dataclass
class Comment:
    id: int
    author: str
    text_html: str | None  # None when the comment was deleted
    created_at: int
    children: list["Comment"] = field(default_factory=list)


@dataclass(frozen=True)
class Thread:
    story: Story
    comments: list[Comment]
    fetched_at: int = 0  # unix epoch seconds; ages on the page are relative to this


def clean_html(raw: str) -> str:
    return nh3.clean(
        raw,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_URL_SCHEMES,
        link_rel="noopener noreferrer",
    )


def prune_deleted(comments: list[Comment]) -> list[Comment]:
    """Drop deleted comments that have nothing under them; keep deleted parents so replies stay."""
    kept = []
    for c in comments:
        c.children = prune_deleted(c.children)
        if c.text_html is not None or c.children:
            kept.append(c)
    return kept


def count_comments(comments: list[Comment]) -> int:
    return sum(1 + count_comments(c.children) for c in comments)
