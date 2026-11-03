import pytest

from hn_browser.ranking import (
    Story,
    rank_discussed,
    rank_hot,
    rank_rising,
    rank_top,
)

HOUR = 3600
NOW = 1_800_000_000


def story(id, points=10, num_comments=5, age_hours=1.0):
    return Story(
        id=id,
        title=f"Story {id}",
        url=f"https://example.com/{id}",
        author="alice",
        points=points,
        num_comments=num_comments,
        created_at=int(NOW - age_hours * HOUR),
    )


@pytest.mark.parametrize(
    "comment_story_ids, expected_order, expected_metrics",
    [
        ([2, 2, 2, 1, 3, 3], [2, 3, 1], [3, 2, 1]),
        ([1], [1], [1]),
        ([], [], []),
    ],
)
def test_rank_hot_orders_by_recent_comment_count(
    comment_story_ids, expected_order, expected_metrics
):
    stories = [story(1), story(2), story(3)]

    ranked = rank_hot(stories, comment_story_ids)

    assert [r.story.id for r in ranked] == expected_order
    assert [r.metric for r in ranked] == expected_metrics
    assert [r.rank for r in ranked] == list(range(1, len(expected_order) + 1))


def test_rank_hot_ignores_comments_on_unknown_stories():
    ranked = rank_hot([story(1)], [1, 99, 99, 99])

    assert [r.story.id for r in ranked] == [1]


def test_rank_hot_breaks_ties_by_points():
    stories = [story(1, points=5), story(2, points=50)]

    ranked = rank_hot(stories, [1, 2])

    assert [r.story.id for r in ranked] == [2, 1]


@pytest.mark.parametrize(
    "ranker, field, values, expected_order",
    [
        (rank_discussed, "num_comments", [3, 30, 12], [2, 3, 1]),
        (rank_top, "points", [100, 7, 250], [3, 1, 2]),
    ],
)
def test_single_field_rankers_sort_descending(ranker, field, values, expected_order):
    stories = [story(i + 1, **{field: v}) for i, v in enumerate(values)]

    ranked = ranker(stories)

    assert [r.story.id for r in ranked] == expected_order
    assert [r.metric for r in ranked] == sorted(values, reverse=True)


@pytest.mark.parametrize(
    "points, age_hours, expected_metric",
    [
        (120, 4.0, 30.0),
        (10, 0.25, 10.0),  # ages under one hour are floored to one hour
        (90, 12.0, 7.5),
    ],
)
def test_rank_rising_uses_points_per_hour(points, age_hours, expected_metric):
    ranked = rank_rising([story(1, points=points, age_hours=age_hours)], now=NOW)

    assert ranked[0].metric == pytest.approx(expected_metric)


def test_rank_rising_prefers_fast_climbers_over_old_high_scores():
    old_big = story(1, points=500, age_hours=20)
    new_quick = story(2, points=60, age_hours=1.5)

    ranked = rank_rising([old_big, new_quick], now=NOW)

    assert [r.story.id for r in ranked] == [2, 1]
