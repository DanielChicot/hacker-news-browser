"""Presets: fixed, named ways of ranking a Snapshot."""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from hn_browser.ranking import (
    RankedStory,
    rank_discussed,
    rank_hot,
    rank_rising,
    rank_top,
)
from hn_browser.snapshot import HOT_WINDOW_HOURS, Snapshot

DEFAULT_LIMIT = 30
NOTABLE_POINTS = 100


@dataclass(frozen=True)
class Preset:
    key: str
    label: str
    blurb: str
    metric_label: str
    rank: Callable[[Snapshot], list[RankedStory]]


@dataclass(frozen=True)
class Stat:
    label: str
    value: int
    sub: str = ""


@dataclass(frozen=True)
class Feed:
    preset: Preset
    ranked: list[RankedStory]
    stats: list[Stat]
    generated_at: int


PRESETS: dict[str, Preset] = {
    p.key: p
    for p in [
        Preset(
            "hot",
            "Hot now",
            f"Threads with the most comments in the last {HOT_WINDOW_HOURS} hours.",
            f"comments in {HOT_WINDOW_HOURS}h",
            lambda s: rank_hot(s.stories, s.comment_story_ids),
        ),
        Preset(
            "discussed",
            "Discussed today",
            "Stories from the last 24 hours with the most comments overall.",
            "comments",
            lambda s: rank_discussed(s.todays_stories),
        ),
        Preset(
            "top",
            "Top today",
            "Stories from the last 24 hours with the most points.",
            "points",
            lambda s: rank_top(s.todays_stories),
        ),
        Preset(
            "rising",
            "Rising",
            "Points per hour of age, so fast climbers beat old giants.",
            "points/hour",
            lambda s: rank_rising(s.todays_stories, now=s.now),
        ),
    ]
}


def _stats(snapshot: Snapshot) -> list[Stat]:
    by_id = {s.id: s for s in snapshot.stories}
    hottest_id, hottest_count = (Counter(snapshot.comment_story_ids).most_common(1) or [(None, 0)])[0]
    today = snapshot.todays_stories
    top = max(today, key=lambda s: s.points, default=None)
    return [
        Stat(f"Comments in {HOT_WINDOW_HOURS}h", len(snapshot.comment_story_ids)),
        Stat("Hottest thread", hottest_count, by_id[hottest_id].title if hottest_id in by_id else ""),
        Stat("Top points today", top.points if top else 0, top.title if top else ""),
        Stat(f"Over {NOTABLE_POINTS} points", sum(s.points >= NOTABLE_POINTS for s in today)),
    ]


def build_feed(snapshot: Snapshot, preset_key: str, limit: int = DEFAULT_LIMIT) -> Feed:
    preset = PRESETS[preset_key]
    return Feed(
        preset=preset,
        ranked=preset.rank(snapshot)[:limit],
        stats=_stats(snapshot),
        generated_at=snapshot.now,
    )
