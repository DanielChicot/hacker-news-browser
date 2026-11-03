import pytest

from hn_browser.thread import Comment, clean_html, count_comments, prune_deleted


def comment(id, text="hi", children=()):
    return Comment(id=id, author="ann", text_html=text, created_at=1_800_000_000, children=list(children))


def test_prune_deleted_drops_deleted_leaves_but_keeps_deleted_parents():
    tree = [
        comment(1, text=None),
        comment(2, text=None, children=[comment(3)]),
        comment(4, children=[comment(5, text=None)]),
    ]

    pruned = prune_deleted(tree)

    assert [c.id for c in pruned] == [2, 4]
    assert [c.id for c in pruned[0].children] == [3]
    assert pruned[1].children == []


def test_count_comments_counts_every_level():
    tree = [comment(1, children=[comment(2, children=[comment(3)]), comment(4)]), comment(5)]

    assert count_comments(tree) == 5


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("<p>plain <i>em</i> and <code>x</code></p>", "<p>plain <i>em</i> and <code>x</code></p>"),
        ('<a href="https://a.example/">link</a>', '<a href="https://a.example/" rel="noopener noreferrer">link</a>'),
        ("<script>alert(1)</script>safe", "safe"),
        ('<img src="x" onerror="alert(1)">text', "text"),
        ('<a href="javascript:alert(1)">bad</a>', "<a rel=\"noopener noreferrer\">bad</a>"),
    ],
)
def test_clean_html_keeps_hn_markup_and_strips_everything_else(raw, expected):
    assert clean_html(raw) == expected
