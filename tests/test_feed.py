import pytest

from hn_browser.feed import PRESETS, build_feed
from hn_browser.ranking import Story
from hn_browser.snapshot import Snapshot

NOW = 1_800_000_000
HOUR = 3600


def story(id, points=10, num_comments=3, age_hours=2.0):
    return Story(id, f"Story {id}", None, "bob", points, num_comments, int(NOW - age_hours * HOUR))


SNAPSHOT = Snapshot(
    now=NOW,
    stories=[
        story(1, points=300, num_comments=10, age_hours=20),
        story(2, points=40, num_comments=90, age_hours=1.0),
        story(3, points=150, num_comments=50, age_hours=5),
    ],
    comment_story_ids=[3, 3, 3, 2, 2, 1],
)


def test_preset_keys_are_the_four_tabs_in_order():
    assert list(PRESETS) == ["hot", "discussed", "top", "rising"]


@pytest.mark.parametrize(
    "preset, expected_order, expected_metric_label",
    [
        ("hot", [3, 2, 1], "comments in 6h"),
        ("discussed", [2, 3, 1], "comments"),
        ("top", [1, 3, 2], "points"),
        ("rising", [2, 3, 1], "points/hour"),
    ],
)
def test_build_feed_ranks_according_to_preset(preset, expected_order, expected_metric_label):
    feed = build_feed(SNAPSHOT, preset)

    assert [r.story.id for r in feed.ranked] == expected_order
    assert feed.preset.key == preset
    assert feed.preset.metric_label == expected_metric_label


def test_build_feed_truncates_to_limit():
    feed = build_feed(SNAPSHOT, "top", limit=2)

    assert [r.story.id for r in feed.ranked] == [1, 3]


def test_build_feed_rejects_unknown_preset():
    with pytest.raises(KeyError):
        build_feed(SNAPSHOT, "nope")


def test_build_feed_stats_summarise_the_snapshot():
    feed = build_feed(SNAPSHOT, "hot")

    assert [(s.label, s.value) for s in feed.stats] == [
        ("Comments in 6h", 6),
        ("Hottest thread", 3),
        ("Top points today", 300),
        ("Over 100 points", 2),
    ]
    assert feed.stats[1].sub == "Story 3"
    assert feed.stats[2].sub == "Story 1"
