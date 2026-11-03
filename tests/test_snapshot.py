from hn_browser.ranking import Story
from hn_browser.snapshot import HOT_WINDOW_HOURS, STORY_WINDOW_HOURS, load_snapshot

NOW = 1_800_000_000
HOUR = 3600


def story(id, points=10, num_comments=3, age_hours=2.0):
    return Story(id, f"Story {id}", None, "bob", points, num_comments, int(NOW - age_hours * HOUR))


class FakeClient:
    def __init__(self, recent_stories, comment_ids, older_stories):
        self.recent_stories = recent_stories
        self.comment_ids = comment_ids
        self.older_stories = {s.id: s for s in older_stories}
        self.calls = []

    async def stories_since(self, since):
        self.calls.append(("stories_since", since))
        return self.recent_stories

    async def comment_story_ids_since(self, since):
        self.calls.append(("comment_story_ids_since", since))
        return self.comment_ids

    async def stories_by_ids(self, ids):
        self.calls.append(("stories_by_ids", list(ids)))
        return [self.older_stories[i] for i in ids if i in self.older_stories]


async def test_snapshot_uses_24h_story_window_and_6h_comment_window():
    client = FakeClient([story(1)], [1], [])

    await load_snapshot(client, now=NOW)

    assert ("stories_since", NOW - STORY_WINDOW_HOURS * HOUR) in client.calls
    assert ("comment_story_ids_since", NOW - HOT_WINDOW_HOURS * HOUR) in client.calls
    assert STORY_WINDOW_HOURS == 24 and HOT_WINDOW_HOURS == 6


async def test_snapshot_fetches_commented_stories_missing_from_the_recent_window():
    old_but_busy = story(77, age_hours=40)
    client = FakeClient([story(1)], [77, 77, 1], [old_but_busy])

    snap = await load_snapshot(client, now=NOW)

    assert ("stories_by_ids", [77]) in client.calls
    assert {s.id for s in snap.stories} == {1, 77}
    assert snap.comment_story_ids == [77, 77, 1]
    assert snap.now == NOW


async def test_snapshot_only_backfills_the_most_commented_missing_ids():
    comment_ids = [i for i in range(100, 160) for _ in range(160 - i)]  # 100 is busiest
    client = FakeClient([], comment_ids, [])

    await load_snapshot(client, now=NOW, max_backfill=5)

    assert ("stories_by_ids", [100, 101, 102, 103, 104]) in client.calls
