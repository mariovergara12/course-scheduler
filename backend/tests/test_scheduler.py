import random
from datetime import date
from itertools import combinations, product

import pytest
from app.scheduler import allowed, conflicts, generate, meeting_conflict, score, study_windows
from app.schemas import Meeting, Preferences, Section, Unavailable


def meeting(start=540, end=600, days=None, **kwargs):
    return Meeting(
        days=days or [0],
        start=start,
        end=end,
        start_date=date(2026, 8, 24),
        end_date=date(2026, 12, 10),
        **kwargs,
    )


def section(id="A", meetings=None, **kwargs):
    return Section(
        id=id,
        course_code=id.split("-")[0],
        number="01",
        instructor="Test",
        seats=10,
        meetings=meetings if meetings is not None else [meeting()],
        **kwargs,
    )


def test_touching_meetings_are_allowed_but_overlap_is_not():
    assert not meeting_conflict(meeting(), meeting(600, 660))
    assert meeting_conflict(meeting(), meeting(599, 660))


def test_different_days_and_nonoverlapping_date_ranges():
    assert not meeting_conflict(meeting(), meeting(days=[1]))
    a, b = meeting(), meeting()
    a.end_date, b.start_date = date(2026, 9, 1), date(2026, 9, 2)
    assert not meeting_conflict(a, b)


def test_date_overlap_without_actual_shared_weekday():
    a, b = meeting(), meeting()
    a.end_date = date(2026, 9, 2)  # Wednesday
    b.start_date = date(2026, 9, 1)  # Tuesday; no shared Monday in intersection
    assert not meeting_conflict(a, b)


def test_travel_only_between_physical_campuses():
    assert meeting_conflict(meeting(campus="Edinburg"), meeting(620, 680, campus="Brownsville"), 60)
    assert not meeting_conflict(meeting(campus="Online"), meeting(620, 680, campus="Brownsville"), 60)


def test_all_lab_meetings_are_checked():
    bundle = section("A", [meeting(), meeting(780, 890, days=[4], kind="Lab")], linked_lab=True)
    assert conflicts(bundle, section("B", [meeting(850, 910, days=[4])]))
    assert not allowed(bundle, Preferences(unavailable=[Unavailable(day=4, start=800, end=900)]))


def test_internally_conflicting_bundle_is_rejected():
    assert not allowed(
        section(meetings=[meeting(), meeting(570, 630, kind="Lab")], linked_lab=True), Preferences()
    )


def test_closed_full_and_impossible_constraints():
    closed = section(status="closed")
    assert not allowed(closed, Preferences())
    assert generate({"A": [section()]}, Preferences(earliest=700))["schedules"] == []
    assert generate({"A": [section("A")], "B": [section("B")]}, Preferences())["schedules"] == []


def test_returns_fewer_than_three_and_reports_search_cap():
    assert len(generate({"A": [section()]}, Preferences())["schedules"]) == 1
    assert generate({"A": [section()]}, Preferences(), max_nodes=0)["truncated"]


@pytest.mark.parametrize("seed", range(12))
def test_backtracking_matches_exhaustive_oracle(seed):
    rng = random.Random(seed)
    options = {}
    for code in ["A", "B", "C", "D"]:
        options[code] = [
            section(
                f"{code}-{i}",
                [meeting(start := rng.randrange(16, 31) * 30, start + 60, days=[rng.randrange(4)])],
            )
            for i in range(3)
        ]
    pref = Preferences(time_of_day=rng.choice(["any", "morning", "afternoon"]))
    valid = [
        list(combo)
        for combo in product(*options.values())
        if all(not conflicts(a, b, pref.travel_minutes) for a, b in combinations(combo, 2))
    ]
    expected = sorted(valid, key=lambda ss: (-score(ss, pref)["score"], tuple(s.id for s in ss)))[:3]
    result = generate(options, pref)
    assert not result["truncated"]
    assert result["valid_count"] == len(valid)
    assert [[s["id"] for s in x["sections"]] for x in result["schedules"]] == [
        [s.id for s in ss] for ss in expected
    ]


def test_friend_bonus_has_explanation_and_actual_change():
    pref = Preferences(friend_priority="sections")
    a = section("A-1", [meeting()])
    b = section("A-2", [meeting(780, 840)])
    result = generate({"A": [a, b]}, pref, [b])
    assert result["schedules"][0]["sections"][0]["id"] == b.id
    assert result["schedules"][0]["shared_sections"] == 1
    assert result["schedules"][0]["social_bonus"] > 0


def test_study_windows_require_shared_dates_and_one_shared_campus():
    own = section("A", [meeting(540, 600), meeting(720, 780)])
    friend = section("B", [meeting(540, 600), meeting(720, 780)])
    windows = study_windows([own], [friend], Preferences())
    assert windows == [
        {
            "day": 0,
            "start": 600,
            "end": 720,
            "campus": "Edinburg",
            "start_date": "2026-08-24",
            "end_date": "2026-12-10",
        }
    ]
    own.meetings[1].campus = "Brownsville"
    assert study_windows([own], [friend], Preferences()) == []
    own.meetings[1].campus = "Edinburg"
    for m in own.meetings:
        m.end_date = date(2026, 9, 1)
    for m in friend.meetings:
        m.start_date = date(2026, 10, 1)
    assert study_windows([own], [friend], Preferences()) == []


def test_study_window_excludes_own_unavailable_time():
    own = section("A", [meeting(540, 600), meeting(720, 780)])
    friend = section("B", [meeting(540, 600), meeting(720, 780)])
    pref = Preferences(unavailable=[Unavailable(day=0, start=600, end=660)])
    assert study_windows([own], [friend], pref)[0]["start"] == 660
