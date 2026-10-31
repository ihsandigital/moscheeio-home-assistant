"""Which switch rules are due, and how a run ends. No Home Assistant imports.

The rules come from moschee.io's ``GET /api/smart-mosque/config``: the
mosque's Home Assistant rules (schedule only) and the prayer moments of the
next days, in epoch milliseconds. The logic mirrors the Smart-Mosque-Box's
``agent/lib/automations.js``: a rule fires for each matching moment at the
moment plus its offset, a run more than two minutes late is skipped, and a
run is keyed by rule id and moment id so it happens once.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .const import MISSED_LIMIT_MS

MINUTE_MS = 60 * 1000
# Only moments this close to now are looked at.
WINDOW_MS = 6 * 60 * MINUTE_MS


@dataclass(frozen=True)
class DueRun:
    """One rule for one moment."""

    key: str
    automation: dict[str, Any]
    moment: dict[str, Any]
    due_at: int


def occurrence_key(automation: dict[str, Any], moment: dict[str, Any]) -> str:
    """The run key, as on the box."""
    return f"{automation.get('id')}|{moment.get('id')}"


def matches_conditions(automation: dict[str, Any], moment: dict[str, Any]) -> bool:
    """Prayers and weekdays; empty lists mean all."""
    conditions = automation.get("conditions") or {}
    prayers = conditions.get("prayers") or []
    weekdays = conditions.get("weekdays") or []
    if prayers and moment.get("prayer") not in prayers:
        return False
    return not (weekdays and moment.get("weekday") not in weekdays)


def due_runs(
    automations: list[dict[str, Any]],
    moments: list[dict[str, Any]],
    handled: set[str],
    now: int,
) -> tuple[list[DueRun], list[DueRun]]:
    """Runs due now, and runs missed (due more than two minutes ago).

    The caller marks both handled, so a missed run is not looked at again.
    Only timetable rules run here: Home Assistant hears no Adhan.
    """
    due: list[DueRun] = []
    missed: list[DueRun] = []
    for automation in automations:
        if not automation.get("enabled", True):
            continue
        trigger = automation.get("trigger") or {}
        if trigger.get("source", "schedule") != "schedule":
            continue
        offset = int(trigger.get("offsetMinutes") or 0) * MINUTE_MS
        for moment in moments:
            at = moment.get("at")
            if not isinstance(at, int | float) or moment.get("event") != trigger.get(
                "event"
            ):
                continue
            if abs(at - now) > WINDOW_MS or not matches_conditions(automation, moment):
                continue
            key = occurrence_key(automation, moment)
            if key in handled:
                continue
            due_at = int(at) + offset
            if due_at > now:
                continue
            run = DueRun(key=key, automation=automation, moment=moment, due_at=due_at)
            (missed if now - due_at > MISSED_LIMIT_MS else due).append(run)

    def order(run: DueRun) -> tuple[int, int]:
        return (run.due_at, int(run.automation.get("position") or 0))

    return sorted(due, key=order), sorted(missed, key=order)


def next_due(
    automations: list[dict[str, Any]],
    moments: list[dict[str, Any]],
    now: int,
) -> tuple[int, dict[str, Any], dict[str, Any]] | None:
    """The next run of any enabled rule: (due at, rule, moment)."""
    best: tuple[int, dict[str, Any], dict[str, Any]] | None = None
    for automation in automations:
        trigger = automation.get("trigger") or {}
        if not automation.get("enabled", True) or trigger.get("source") != "schedule":
            continue
        offset = int(trigger.get("offsetMinutes") or 0) * MINUTE_MS
        for moment in moments:
            at = moment.get("at")
            if not isinstance(at, int | float) or moment.get("event") != trigger.get(
                "event"
            ):
                continue
            if not matches_conditions(automation, moment):
                continue
            due_at = int(at) + offset
            if due_at > now and (best is None or due_at < best[0]):
                best = (due_at, automation, moment)
    return best


FAILED_OUTCOMES = frozenset({"failed", "unavailable"})


def run_result(outcomes: list[dict[str, Any]], dry_run: bool) -> str:
    """How a run ended, from its actions' outcomes (as on the box)."""
    if dry_run:
        return "dry_run"
    acted = [outcome for outcome in outcomes if outcome.get("type") != "wait"]
    done = any(outcome.get("outcome") == "done" for outcome in acted)
    if any(outcome.get("outcome") in FAILED_OUTCOMES for outcome in acted):
        return "partial" if done else "failed"
    if acted and all(outcome.get("outcome") == "done" for outcome in acted):
        return "done"
    return "partial" if done else "skipped"
