"""Due runs and run results (no Home Assistant needed)."""

from __future__ import annotations

from custom_components.moscheeio.automations import (
    due_runs,
    matches_conditions,
    next_due,
    run_result,
)

MINUTE = 60_000
FAJR_ADHAN = 1_793_330_000_000


def rule(**overrides):
    return {
        "id": "a1",
        "name": "Mischpult 15 Minuten vor Fajr einschalten",
        "enabled": True,
        "mode": "on",
        "position": 0,
        "trigger": {"event": "adhan", "source": "schedule", "offsetMinutes": -15},
        "conditions": {"prayers": ["fajr"], "weekdays": []},
        "actions": [{"type": "switch", "entityId": "switch.strom", "on": True}],
        **overrides,
    }


MOMENTS = [
    {
        "id": "2026-10-31:fajr:adhan",
        "prayer": "fajr",
        "event": "adhan",
        "at": FAJR_ADHAN,
        "weekday": 6,
    },
    {
        "id": "2026-10-31:dhuhr:adhan",
        "prayer": "dhuhr",
        "event": "adhan",
        "at": FAJR_ADHAN + 6 * 60 * MINUTE,
        "weekday": 6,
    },
]


def test_due_fifteen_minutes_before_fajr() -> None:
    now = FAJR_ADHAN - 15 * MINUTE + 3_000
    due, missed = due_runs([rule()], MOMENTS, set(), now)
    assert [run.key for run in due] == ["a1|2026-10-31:fajr:adhan"]
    assert due[0].due_at == FAJR_ADHAN - 15 * MINUTE
    assert missed == []


def test_not_yet_handled_or_missed() -> None:
    before = FAJR_ADHAN - 16 * MINUTE
    assert due_runs([rule()], MOMENTS, set(), before) == ([], [])
    now = FAJR_ADHAN - 15 * MINUTE + 1000
    assert due_runs([rule()], MOMENTS, {"a1|2026-10-31:fajr:adhan"}, now) == ([], [])
    late = FAJR_ADHAN - 10 * MINUTE
    due, missed = due_runs([rule()], MOMENTS, set(), late)
    assert due == []
    assert [run.key for run in missed] == ["a1|2026-10-31:fajr:adhan"]


def test_only_schedule_and_enabled_rules() -> None:
    now = FAJR_ADHAN + 1000
    detected = rule(
        trigger={"event": "adhan", "source": "detected", "offsetMinutes": 0}
    )
    off = rule(
        enabled=False,
        trigger={"event": "adhan", "source": "schedule", "offsetMinutes": 0},
    )
    assert due_runs([detected, off], MOMENTS, set(), now) == ([], [])


def test_conditions() -> None:
    assert matches_conditions(rule(), MOMENTS[0])
    assert not matches_conditions(rule(), MOMENTS[1])
    assert not matches_conditions(
        rule(conditions={"prayers": [], "weekdays": [5]}), MOMENTS[0]
    )
    assert matches_conditions(rule(conditions={}), MOMENTS[1])


def test_next_due() -> None:
    upcoming = next_due([rule()], MOMENTS, FAJR_ADHAN - 60 * MINUTE)
    assert upcoming is not None
    assert upcoming[0] == FAJR_ADHAN - 15 * MINUTE
    assert next_due([rule()], MOMENTS, FAJR_ADHAN) is None


def test_run_result() -> None:
    done = {"type": "switch", "outcome": "done"}
    wait = {"type": "wait", "outcome": "done"}
    assert run_result([done, wait], dry_run=False) == "done"
    assert run_result([done], dry_run=True) == "dry_run"
    assert (
        run_result([done, {"type": "switch", "outcome": "unavailable"}], dry_run=False)
        == "partial"
    )
    assert (
        run_result([{"type": "switch", "outcome": "failed"}], dry_run=False) == "failed"
    )
    assert (
        run_result([{"type": "switch", "outcome": "skipped_live"}], dry_run=False)
        == "skipped"
    )
    assert (
        run_result(
            [done, {"type": "switch", "outcome": "skipped_touched"}], dry_run=False
        )
        == "partial"
    )
