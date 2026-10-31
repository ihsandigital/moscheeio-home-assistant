"""Runs the mosque's switch rules in Home Assistant, from the stored timetable.

The rules and the prayer moments of the next days come from moschee.io and
are kept on disk, so "Mischpult einschalten 15 Minuten vor Fajr" also happens
while the internet is down. Each run is reported to moschee.io's Verlauf;
reports that could not be sent are kept and sent later.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import contextlib
from datetime import UTC, datetime, timedelta
import logging
import time
from typing import TYPE_CHECKING, Any

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval

from .api import MoscheeioError
from .automations import DueRun, due_runs, run_result
from .const import DOMAIN, RUN_FLUSH_SECONDS, RUN_TICK_SECONDS
from .helpers import entity_on

if TYPE_CHECKING:
    from .hub import MoscheeioHub

_LOGGER = logging.getLogger(__name__)

MAX_WAIT_SECONDS = 600
MAX_REPORTS_PER_CALL = 50
MAX_KEPT_REPORTS = 500
HANDLED_KEEP_MS = 3 * 24 * 60 * 60 * 1000


def _now_ms() -> int:
    return int(time.time() * 1000)


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat()


class AutomationRunner:
    """Ticks every few seconds; runs due rules one after the other."""

    def __init__(self, hub: MoscheeioHub, now: Callable[[], int] = _now_ms) -> None:
        self.hub = hub
        self.now = now
        stored = hub.stored
        handled = stored.get("handled")
        # run key -> due at (ms), to forget old keys.
        self.handled: dict[str, int] = handled if isinstance(handled, dict) else {}
        unsent = stored.get("unsent")
        self.unsent: list[dict[str, Any]] = unsent if isinstance(unsent, list) else []
        self.last_run: dict[str, Any] | None = stored.get("lastRun")
        self._queue: asyncio.Queue[DueRun] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self._unsubs: list[Callable[[], None]] = []
        self._flushing = False

    def start(self) -> None:
        """Start ticking."""
        hass = self.hub.hass
        self._worker = self.hub.entry.async_create_background_task(
            hass, self._work(), f"{DOMAIN} runner"
        )
        self._unsubs.append(
            async_track_time_interval(
                hass, self._tick, timedelta(seconds=RUN_TICK_SECONDS)
            )
        )
        self._unsubs.append(
            async_track_time_interval(
                hass, self._flush_tick, timedelta(seconds=RUN_FLUSH_SECONDS)
            )
        )

    async def async_stop(self) -> None:
        """Stop ticking; a run in progress is cancelled."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._worker:
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None

    def automations(self) -> list[dict[str, Any]]:
        """The rules moschee.io sent (empty without the plan)."""
        config = self.hub.config
        if config.get("enabled") is False:
            return []
        automations = config.get("automations")
        return [a for a in automations or [] if isinstance(a, dict)]

    def moments(self) -> list[dict[str, Any]]:
        """The prayer moments of the next days."""
        moments = self.hub.config.get("moments")
        return [m for m in moments or [] if isinstance(m, dict)]

    @callback
    def _tick(self, _now: datetime | None = None) -> None:
        self.check()

    def check(self) -> list[DueRun]:
        """Queue the runs that are due; mark missed ones handled."""
        now = self.now()
        due, missed = due_runs(
            self.automations(), self.moments(), set(self.handled), now
        )
        for run in missed:
            self.handled[run.key] = run.due_at
        for run in due:
            self.handled[run.key] = run.due_at
            self._queue.put_nowait(run)
        if due or missed:
            cutoff = now - HANDLED_KEEP_MS
            self.handled = {k: v for k, v in self.handled.items() if v >= cutoff}
            self._persist()
        return due

    async def _work(self) -> None:
        while True:
            run = await self._queue.get()
            try:
                report = await self.execute(run)
            except Exception as err:  # noqa: BLE001 - a broken run must not stop the runner
                _LOGGER.exception("Switch rule %s failed", run.automation.get("name"))
                report = self._report(run, "failed", [], str(err)[:160])
            self._log(report)
            self.last_run = report
            self.unsent.append(report)
            self.unsent = self.unsent[-MAX_KEPT_REPORTS:]
            self._persist()
            self.hub.hass.async_create_task(self.async_flush())

    def _paused(self) -> bool:
        until = self.hub.config.get("pausedUntil")
        if not isinstance(until, str):
            return False
        try:
            return (
                datetime.fromisoformat(until.replace("Z", "+00:00")).timestamp() * 1000
                > self.now()
            )
        except ValueError:
            return False

    async def execute(self, run: DueRun) -> dict[str, Any]:
        """Run one rule for one moment and build its report."""
        automation = run.automation
        conditions = automation.get("conditions") or {}
        if self._paused():
            return self._report(run, "skipped_paused", [])
        if conditions.get("onlyWhenLive") and self.hub.live_rooms <= 0:
            return self._report(run, "skipped_not_live", [])
        dry_run = automation.get("mode") != "on"
        skip_touched = int(conditions.get("skipTouchedMinutes") or 0)
        outcomes: list[dict[str, Any]] = []
        for index, action in enumerate(automation.get("actions") or []):
            if not isinstance(action, dict):
                continue
            outcome = await self._run_action(
                action, automation, dry_run=dry_run, skip_touched=skip_touched
            )
            outcomes.append(
                {
                    "index": index,
                    "type": action.get("type"),
                    "target": action.get("entityId"),
                    **outcome,
                }
            )
            if not dry_run and self._paused():
                break
        return self._report(run, run_result(outcomes, dry_run), outcomes)

    async def _run_action(
        self,
        action: dict[str, Any],
        automation: dict[str, Any],
        *,
        dry_run: bool,
        skip_touched: int,
    ) -> dict[str, Any]:
        kind = action.get("type")
        if kind == "wait":
            if not dry_run:
                seconds = min(max(int(action.get("seconds") or 0), 0), MAX_WAIT_SECONDS)
                await asyncio.sleep(seconds)
            return {"outcome": "dry_run" if dry_run else "done"}
        if kind != "switch":
            # Desk actions run on the desk's own box, never here.
            return {"outcome": "failed", "detail": "not a switch action"}
        entity_id = action.get("entityId")
        on = action.get("on")
        hub = self.hub
        if not isinstance(entity_id, str) or not isinstance(on, bool):
            return {"outcome": "failed", "detail": "bad action"}
        if entity_id not in hub.shared_entity_ids():
            return {"outcome": "failed", "detail": "no longer shared"}
        current = entity_on(hub.hass.states.get(entity_id))
        if current is None:
            return {"outcome": "unavailable"}
        if skip_touched > 0:
            change = hub.last_change(entity_id)
            if (
                change is not None
                and change.get("kind") != "automation"
                and isinstance(change.get("at"), datetime)
                and (self.now() - change["at"].timestamp() * 1000)
                < skip_touched * 60 * 1000
            ):
                return {"outcome": "skipped_touched"}
        if not on and hub.live_rooms > 0:
            # Never cut the power while a translation is live.
            return {"outcome": "skipped_live"}
        if dry_run:
            return {"outcome": "dry_run"}
        if current is on:
            return {"outcome": "done", "detail": "already"}
        try:
            confirmed = await hub.async_switch(
                entity_id, on, {"kind": "automation", "name": automation.get("name")}
            )
        except HomeAssistantError as err:
            return {"outcome": "failed", "detail": str(err)[:160]}
        if not confirmed:
            return {"outcome": "failed", "detail": "no confirmation"}
        return {"outcome": "done"}

    def _report(
        self,
        run: DueRun,
        result: str,
        actions: list[dict[str, Any]],
        detail: str | None = None,
    ) -> dict[str, Any]:
        return {
            "key": run.key,
            "automationId": run.automation.get("id"),
            "automationName": run.automation.get("name"),
            "momentId": run.moment.get("id"),
            "prayer": run.moment.get("prayer"),
            "event": run.moment.get("event"),
            "dueAt": _iso(run.due_at),
            "ranAt": _iso(self.now()),
            "triggerSource": "schedule",
            "mode": "on" if run.automation.get("mode") == "on" else "dry_run",
            "result": result,
            "detail": detail,
            "actions": actions,
        }

    def _log(self, report: dict[str, Any]) -> None:
        outcomes = ", ".join(
            f"{a.get('type')} {a.get('target') or ''}={a.get('outcome')}".replace(
                " =", "="
            )
            for a in report["actions"]
        )
        _LOGGER.info(
            "Switch rule %s (%s %s): %s%s",
            report.get("automationName") or report.get("automationId"),
            report.get("prayer"),
            report.get("event"),
            report.get("result"),
            f" [{outcomes}]" if outcomes else "",
        )

    @callback
    def _flush_tick(self, _now: datetime | None = None) -> None:
        if self.unsent:
            self.hub.hass.async_create_task(self.async_flush())

    async def async_flush(self) -> None:
        """Send the reports moschee.io has not got yet."""
        if self._flushing or not self.unsent:
            return
        self._flushing = True
        try:
            while self.unsent:
                batch = self.unsent[:MAX_REPORTS_PER_CALL]
                try:
                    await self.hub.api.post_runs(batch)
                except MoscheeioError as err:
                    _LOGGER.debug("Could not report runs yet: %s", err)
                    return
                self.unsent = self.unsent[len(batch) :]
                self._persist()
        finally:
            self._flushing = False

    def _persist(self) -> None:
        stored = self.hub.stored
        stored["handled"] = self.handled
        stored["unsent"] = self.unsent
        stored["lastRun"] = self.last_run
        self.hub.hass.async_create_task(self.hub.async_save())
