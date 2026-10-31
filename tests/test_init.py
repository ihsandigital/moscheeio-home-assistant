"""Setup, sharing switches, moschee.io's commands and the desk entities."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moscheeio.api import MoscheeioAuthError, MoscheeioConnectionError

from .conftest import DESK_ID, me_payload

SWITCH = "input_boolean.mischpult_strom"


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await async_setup_component(
        hass,
        "input_boolean",
        {"input_boolean": {"mischpult_strom": {"name": "Mischpult Strom"}}},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _desk(muted: bool = False, online: bool = True) -> dict:
    return {
        "boxId": DESK_ID,
        "boxName": "Mischpult",
        "online": online,
        "state": {
            "desk": {"model": "X32", "firmware": "4.06"},
            "targets": [
                {
                    "target": "ch/01",
                    "label": "Imam",
                    "role": "imam",
                    "protected": True,
                    "deskName": "Imam",
                    "muted": muted,
                    "db": -5.0,
                    "hasFader": True,
                    "changedAt": None,
                    "changedBy": None,
                }
            ],
        },
    }


async def test_setup_shares_the_switches(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    mock_relay: AsyncMock,
) -> None:
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED
    mock_api.put_switches.assert_awaited_with(
        [{"entityId": SWITCH, "name": "Mischpult Strom", "confirmOff": True}]
    )
    mock_relay.start.assert_called_once()
    assert (
        hass.states.get("binary_sensor.igs_moschee_moschee_io_connection") is not None
    )


async def test_setup_needs_reauth_when_removed(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    mock_relay: AsyncMock,
) -> None:
    mock_api.me.side_effect = MoscheeioAuthError("HTTP 401")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    assert any(
        flow["context"]["source"] == "reauth"
        for flow in hass.config_entries.flow.async_progress()
    )


async def test_setup_offline_without_cache_retries(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    mock_relay: AsyncMock,
) -> None:
    mock_api.me.side_effect = MoscheeioConnectionError("down")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_switch_set_from_moscheeio(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    mock_relay: AsyncMock,
) -> None:
    await _setup(hass, config_entry)
    hub = config_entry.runtime_data
    result = await hub.async_handle_command(
        {
            "type": "switch_set",
            "entityId": SWITCH,
            "on": True,
            "by": {"kind": "person", "name": "Youcef"},
        }
    )
    assert result == {"ok": True, "result": {"entityId": SWITCH, "on": True}}
    assert hass.states.get(SWITCH).state == STATE_ON
    await hass.async_block_till_done()
    state = hub.switch_states()[0]
    assert state["on"] is True
    assert state["changedBy"] == {"kind": "person", "name": "Youcef"}
    sent = [call.args[0] for call in mock_relay.send.await_args_list]
    assert any(
        message["type"] == "state" and message["switches"][0]["on"] for message in sent
    )


async def test_switch_set_refusals(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    mock_relay: AsyncMock,
) -> None:
    await _setup(hass, config_entry)
    hub = config_entry.runtime_data
    assert await hub.async_handle_command(
        {"type": "switch_set", "entityId": "input_boolean.other", "on": True}
    ) == {"ok": False, "code": "unknown_entity"}
    assert await hub.async_handle_command(
        {"type": "switch_set", "entityId": SWITCH}
    ) == {
        "ok": False,
        "code": "bad_request",
    }
    assert await hub.async_handle_command({"type": "mixer_set"}) == {
        "ok": False,
        "code": "unknown_command",
    }
    hass.states.async_set(SWITCH, STATE_UNAVAILABLE)
    assert await hub.async_handle_command(
        {"type": "switch_set", "entityId": SWITCH, "on": False}
    ) == {"ok": False, "code": "unavailable"}


async def test_state_and_config_changed_commands(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    mock_relay: AsyncMock,
) -> None:
    await _setup(hass, config_entry)
    hub = config_entry.runtime_data
    result = await hub.async_handle_command({"type": "state"})
    assert result["ok"] is True
    assert result["result"]["switches"][0]["entityId"] == SWITCH
    assert result["result"]["switches"][0]["on"] is False
    calls = mock_api.config.await_count
    assert await hub.async_handle_command({"type": "config_changed"}) == {"ok": True}
    assert mock_api.config.await_count == calls + 1


async def test_desk_channels_become_switches(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    mock_relay: AsyncMock,
) -> None:
    await _setup(hass, config_entry)
    hub = config_entry.runtime_data
    hub._on_relay_connection(True)
    await hub._on_relay_message(
        {"type": "desks", "deskAccess": "control", "desks": [_desk()]}
    )
    await hass.async_block_till_done()
    state = hass.states.get("switch.mischpult_imam")
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes["protected"] is True
    level = hass.states.get("sensor.mischpult_imam_level")
    assert level is not None
    assert float(level.state) == -5.0

    async def answer(message: dict) -> bool:
        if message["type"] == "desk_command":
            assert message["boxId"] == DESK_ID
            assert message["command"] == {
                "type": "mixer_set",
                "target": "ch/01",
                "muted": True,
            }
            hass.async_create_task(
                hub._on_relay_message(
                    {"type": "desk_command_result", "id": message["id"], "ok": True}
                )
            )
        return True

    mock_relay.send.side_effect = answer
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.mischpult_imam"}, blocking=True
    )

    await hub._on_relay_message({"type": "desk", **_desk(muted=True)})
    await hass.async_block_till_done()
    assert hass.states.get("switch.mischpult_imam").state == STATE_OFF

    await hub._on_relay_message(
        {"type": "desk", "boxId": DESK_ID, "online": False, "state": None}
    )
    await hass.async_block_till_done()
    assert hass.states.get("switch.mischpult_imam").state == STATE_UNAVAILABLE


async def test_desk_refusal_is_an_error(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    mock_relay: AsyncMock,
) -> None:
    await _setup(hass, config_entry)
    hub = config_entry.runtime_data
    hub._on_relay_connection(True)
    await hub._on_relay_message(
        {"type": "desks", "deskAccess": "control", "desks": [_desk()]}
    )
    await hass.async_block_till_done()

    async def refuse(message: dict) -> bool:
        if message["type"] == "desk_command":
            hass.async_create_task(
                hub._on_relay_message(
                    {
                        "type": "desk_command_result",
                        "id": message["id"],
                        "ok": False,
                        "code": "protected",
                    }
                )
            )
        return True

    mock_relay.send.side_effect = refuse
    with pytest.raises(HomeAssistantError, match="protected"):
        await hass.services.async_call(
            "switch", "turn_off", {"entity_id": "switch.mischpult_imam"}, blocking=True
        )


async def test_view_access_gives_read_only_channels(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    mock_relay: AsyncMock,
) -> None:
    mock_api.me.return_value = me_payload(deskAccess="view")
    mock_api.config.return_value["deskAccess"] = "view"
    await _setup(hass, config_entry)
    hub = config_entry.runtime_data
    hub._on_relay_connection(True)
    await hub._on_relay_message(
        {"type": "desks", "deskAccess": "view", "desks": [_desk()]}
    )
    await hass.async_block_till_done()
    assert hass.states.get("switch.mischpult_imam") is None
    assert hass.states.get("binary_sensor.mischpult_imam").state == STATE_ON


async def test_unload(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    mock_relay: AsyncMock,
) -> None:
    await _setup(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    mock_relay.stop.assert_awaited()
    assert config_entry.state is ConfigEntryState.NOT_LOADED
