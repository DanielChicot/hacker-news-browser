"""One fetch of everything the presets need, so all tabs rank the same data."""

from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from hn_browser.ranking import HOUR_SECONDS, Story

STORY_WINDOW_HOURS = 24
HOT_WINDOW_HOURS = 6
DEFAULT_MAX_BACKFILL = 40


class StorySource(Protocol):
    async def stories_since(self, since: int) -> list[Story]: ...
    async def comment_story_ids_since(self, since: int) -> list[int]: ...
    async def stories_by_ids(self, ids: list[int]) -> list[Story]: ...


@dataclass(frozen=True)
class Snapshot:
    now: int
    stories: list[Story]
    comment_story_ids: list[int]


async def load_snapshot(
    client: StorySource, now: int, max_backfill: int = DEFAULT_MAX_BACKFILL
) -> Snapshot:
    stories = await client.stories_since(now - STORY_WINDOW_HOURS * HOUR_SECONDS)
    comment_ids = await client.comment_story_ids_since(now - HOT_WINDOW_HOURS * HOUR_SECONDS)

    known = {s.id for s in stories}
    busiest_missing = [
        sid for sid, _ in Counter(comment_ids).most_common() if sid not in known
    ][:max_backfill]
    if busiest_missing:
        stories = stories + await client.stories_by_ids(busiest_missing)

    return Snapshot(now=now, stories=stories, comment_story_ids=comment_ids)
