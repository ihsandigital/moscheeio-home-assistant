"""Switch rules running in Home Assistant."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moscheeio.automations import DueRun

from .conftest import config_payload, me_payload

SWITCH = "input_boolean.mischpult_strom"


def _rule(on: bool, mode: str = "on", **conditions) -> dict:
    return {
        "id": "7c9e6679-7425-40de-944b-000000000001",
        "name": "Mischpult vor Fajr" if on else "Mischpult nach Isha",
        "enabled": True,
        "mode": mode,
        "position": 0,
        "trigger": {"event": "adhan", "source": "schedule", "offsetMinutes": -15},
        "conditions": {
            "prayers": [],
            "weekdays": [],
            "onlyWhenLive": False,
            "skipTouchedMinutes": 0,
            **conditions,
        },
        "actions": [{"type": "switch", "entityId": SWITCH, "on": on}],
    }


async def _setup(
    hass: HomeAssistant, entry: MockConfigEntry, initial: bool = False
) -> None:
    assert await async_setup_component(
        hass,
        "input_boolean",
        {"input_boolean": {"mischpult_strom": {"initial": initial}}},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _run(rule: dict) -> DueRun:
    moment = {
        "id": "2026-10-31:fajr:adhan",
        "prayer": "fajr",
        "event": "adhan",
        "at": int(time.time() * 1000),
    }
    return DueRun(
        key=f"{rule['id']}|{moment['id']}",
        automation=rule,
        moment=moment,
        due_at=moment["at"],
    )


async def test_switches_on_before_fajr(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    mock_relay: AsyncMock,
) -> None:
    await _setup(hass, config_entry)
    runner = config_entry.runtime_data.runner
    report = await runner.execute(_run(_rule(True)))
    assert report["result"] == "done"
    assert report["actions"][0]["target"] == SWITCH
    assert hass.states.get(SWITCH).state == STATE_ON
    assert (
        config_entry.runtime_data.switch_states()[0]["changedBy"]["kind"]
        == "automation"
    )


async def test_dry_run_only_reports(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    mock_relay: AsyncMock,
) -> None:
    await _setup(hass, config_entry)
    report = await config_entry.runtime_data.runner.execute(
        _run(_rule(True, mode="dry_run"))
    )
    assert report["result"] == "dry_run"
    assert report["mode"] == "dry_run"
    assert hass.states.get(SWITCH).state == STATE_OFF


async def test_never_switches_off_while_live(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    mock_relay: AsyncMock,
) -> None:
    mock_api.me.return_value = me_payload(liveRooms=1)
    await _setup(hass, config_entry, initial=True)
    report = await config_entry.runtime_data.runner.execute(_run(_rule(False)))
    assert report["result"] == "skipped"
    assert report["actions"][0]["outcome"] == "skipped_live"
    assert hass.states.get(SWITCH).state == STATE_ON


async def test_paused_and_only_when_live(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    mock_relay: AsyncMock,
) -> None:
    mock_api.config.return_value = config_payload(
        pausedUntil="2100-01-01T00:00:00.000Z"
    )
    await _setup(hass, config_entry)
    runner = config_entry.runtime_data.runner
    assert (await runner.execute(_run(_rule(True))))["result"] == "skipped_paused"
    config_entry.runtime_data.config["pausedUntil"] = None
    assert (await runner.execute(_run(_rule(True, onlyWhenLive=True))))[
        "result"
    ] == "skipped_not_live"


async def test_a_person_wins(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    mock_relay: AsyncMock,
) -> None:
    await _setup(hass, config_entry, initial=True)
    await hass.services.async_call(
        "input_boolean", "turn_off", {"entity_id": SWITCH}, blocking=True
    )
    await hass.async_block_till_done()
    report = await config_entry.runtime_data.runner.execute(
        _run(_rule(True, skipTouchedMinutes=10))
    )
    assert report["actions"][0]["outcome"] == "skipped_touched"
    assert hass.states.get(SWITCH).state == STATE_OFF


async def test_due_rule_runs_and_is_reported(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    mock_relay: AsyncMock,
) -> None:
    now = int(time.time() * 1000)
    rule = _rule(True)
    mock_api.config.return_value = config_payload(
        automations=[rule],
        moments=[
            {
                "id": "m1",
                "prayer": "fajr",
                "event": "adhan",
                "at": now + 15 * 60_000 - 1000,
                "weekday": 6,
            }
        ],
    )
    await _setup(hass, config_entry)
    runner = config_entry.runtime_data.runner
    assert [run.key for run in runner.check()] == [f"{rule['id']}|m1"]
    assert runner.check() == []
    for _ in range(20):
        await hass.async_block_till_done()
        if mock_api.post_runs.await_count:
            break
    assert hass.states.get(SWITCH).state == STATE_ON
    reports = mock_api.post_runs.await_args.args[0]
    assert reports[0]["key"] == f"{rule['id']}|m1"
    assert reports[0]["result"] == "done"
    assert runner.unsent == []
