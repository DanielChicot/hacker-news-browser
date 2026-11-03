"""Pure ranking functions over Hacker News stories.

Each ranker returns a list of RankedStory ordered best-first. They never
touch the network, so they can be tested with plain data.
"""

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass

HOUR_SECONDS = 3600
MIN_AGE_HOURS = 1.0


@dataclass(frozen=True)
class Story:
    id: int
    title: str
    url: str | None
    author: str
    points: int
    num_comments: int
    created_at: int  # unix epoch seconds


@dataclass(frozen=True)
class RankedStory:
    rank: int
    story: Story
    metric: float


def _ranked(stories: Iterable[Story], metric_of: Callable[[Story], float]) -> list[RankedStory]:
    ordered = sorted(
        stories,
        key=lambda s: (-metric_of(s), -s.points, -s.num_comments, s.id),
    )
    return [RankedStory(rank=i, story=s, metric=metric_of(s)) for i, s in enumerate(ordered, 1)]


def rank_hot(stories: Iterable[Story], comment_story_ids: Iterable[int]) -> list[RankedStory]:
    """Order stories by how many of the given comments belong to them."""
    counts = Counter(comment_story_ids)
    commented = [s for s in stories if counts[s.id] > 0]
    return _ranked(commented, lambda s: counts[s.id])


def rank_discussed(stories: Iterable[Story]) -> list[RankedStory]:
    return _ranked(stories, lambda s: s.num_comments)


def rank_top(stories: Iterable[Story]) -> list[RankedStory]:
    return _ranked(stories, lambda s: s.points)


def rank_rising(stories: Iterable[Story], now: int) -> list[RankedStory]:
    """Order stories by points gained per hour of age, with a one hour floor."""

    def points_per_hour(s: Story) -> float:
        age_hours = max((now - s.created_at) / HOUR_SECONDS, MIN_AGE_HOURS)
        return round(s.points / age_hours, 1)

    return _ranked(stories, points_per_hour)
