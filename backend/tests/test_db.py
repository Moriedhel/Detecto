from datetime import datetime, timedelta, timezone

import pytest

from backend.db import DetectionRepository
from backend.models.record import DetectionRecordCreate, HistoryQuery, PersonBox

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def repo(tmp_path):
    return DetectionRepository(tmp_path / "test.db")


def _rec(count=2, avg=0.8, **kw) -> DetectionRecordCreate:
    base = dict(
        count=count, avg_confidence=avg if count else None, inference_ms=50.0,
        total_ms=60.0, source="img.jpg", image_width=640, image_height=480,
        conf_threshold=0.4,
    )
    return DetectionRecordCreate(**{**base, **kw})


def test_add_and_get_roundtrip(repo):
    box = PersonBox(bbox=[1, 2, 3, 4], confidence=0.9, center=[2, 3])
    saved = repo.add(_rec(count=1, avg=0.9, detections=[box], contrast_enhanced=True), timestamp=T0)

    assert saved.id == 1
    assert saved.timestamp == T0
    loaded = repo.get(saved.id)
    assert loaded == saved
    assert loaded.detections[0].bbox == [1, 2, 3, 4]
    assert loaded.contrast_enhanced is True


def test_zero_people_stores_null_confidence(repo):
    saved = repo.add(_rec(count=0))
    assert saved.count == 0 and saved.avg_confidence is None


def test_list_orders_newest_first_and_paginates(repo):
    for i in range(5):
        repo.add(_rec(count=i + 1), timestamp=T0 + timedelta(minutes=i))

    page = repo.list(HistoryQuery(limit=2))
    assert page.total == 5
    assert [r.count for r in page.items] == [5, 4]

    page = repo.list(HistoryQuery(limit=2, offset=2, newest_first=False))
    assert [r.count for r in page.items] == [3, 4]


def test_date_range_filter(repo):
    for h in range(4):
        repo.add(_rec(count=h + 1), timestamp=T0 + timedelta(hours=h))

    page = repo.list(HistoryQuery(start=T0 + timedelta(hours=1), end=T0 + timedelta(hours=2)))
    assert sorted(r.count for r in page.items) == [2, 3]


def test_naive_and_other_timezones_treated_correctly(repo):
    repo.add(_rec(), timestamp=T0)
    athens = timezone(timedelta(hours=3))
    # 15:00 Athens == 12:00 UTC -> inclusive bound should match
    assert repo.list(HistoryQuery(start=datetime(2026, 10, 1, 15, 0, tzinfo=athens))).total == 1
    # naive datetime is read as UTC
    assert repo.list(HistoryQuery(start=datetime(2026, 10, 1, 12, 1))).total == 0


def test_confidence_and_count_filters(repo):
    repo.add(_rec(count=1, avg=0.5))
    repo.add(_rec(count=3, avg=0.9))
    repo.add(_rec(count=0))

    assert repo.list(HistoryQuery(min_confidence=0.7)).total == 1
    assert repo.list(HistoryQuery(min_count=1)).total == 2
    assert repo.list().total == 3


def test_clear_removes_everything_and_resets_ids(repo):
    repo.add(_rec())
    repo.add(_rec())
    assert repo.clear() == 2
    assert repo.list().total == 0
    assert repo.add(_rec()).id == 1


def test_invalid_record_rejected():
    with pytest.raises(ValueError):
        _rec(avg=1.5)
