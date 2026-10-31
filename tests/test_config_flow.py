"""Pairing by code and choosing the shared switches."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moscheeio.api import DeviceCode, DeviceFlowError
from custom_components.moscheeio.const import DOMAIN

from .conftest import BOX_ID, me_payload

CODE = DeviceCode(
    device_code="dev",
    user_code="ABCD-EFGH",
    verification_uri="https://app.moschee.io/device",
    verification_uri_complete="https://app.moschee.io/device?user_code=ABCD-EFGH",
    interval=5,
    expires_in=1800,
)


def _patch_api(token: str | Exception = "token"):
    api = AsyncMock()
    api.request_device_code.return_value = CODE
    approved = asyncio.Event()

    async def wait_for_token(code: DeviceCode) -> str:
        await approved.wait()
        if isinstance(token, Exception):
            raise token
        return token

    api.wait_for_token.side_effect = wait_for_token
    api.approved = approved
    api.me.return_value = me_payload()
    return patch(
        "custom_components.moscheeio.config_flow.MoscheeioApi", return_value=api
    ), api


async def _run_until_progress_done(
    hass: HomeAssistant, result: dict, api: AsyncMock
) -> dict:
    assert result["type"] is FlowResultType.SHOW_PROGRESS
    assert result["description_placeholders"]["code"] == "ABCD-EFGH"
    api.approved.set()
    await hass.async_block_till_done()
    return await hass.config_entries.flow.async_configure(result["flow_id"])


async def test_pairs_with_moschee_io(
    hass: HomeAssistant, mock_api: AsyncMock, mock_relay: AsyncMock
) -> None:
    patcher, api = _patch_api()
    with patcher:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        # Without advanced mode there is nothing to choose.
        assert "environment" not in result["data_schema"].schema
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        result = await _run_until_progress_done(hass, result, api)
        assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "IGS Moschee"
    assert result["data"]["api_url"] == "https://app.moschee.io"
    assert result["data"]["token"] == "token"
    assert result["result"].unique_id == BOX_ID


async def test_stage_only_in_advanced_mode(
    hass: HomeAssistant, mock_api: AsyncMock, mock_relay: AsyncMock
) -> None:
    patcher, api = _patch_api()
    with patcher:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_USER,
                "show_advanced_options": True,
            },
        )
        assert "environment" in result["data_schema"].schema
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"environment": "stage"}
        )
        result = await _run_until_progress_done(hass, result, api)
        assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["api_url"] == "https://app.moschee-stage.de"


async def test_declined_code_aborts(hass: HomeAssistant) -> None:
    patcher, api = _patch_api(DeviceFlowError("access_denied"))
    with patcher:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        result = await _run_until_progress_done(hass, result, api)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "denied"


async def test_same_connection_twice_aborts(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    patcher, api = _patch_api()
    with patcher:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        result = await _run_until_progress_done(hass, result, api)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_choose_switches(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    mock_relay: AsyncMock,
) -> None:
    assert await async_setup_component(
        hass,
        "input_boolean",
        {
            "input_boolean": {
                "mischpult_strom": {"name": "Mischpult Strom"},
                "licht": {"name": "Licht"},
            }
        },
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"switches": ["input_boolean.mischpult_strom", "input_boolean.licht"]},
    )
    assert result["step_id"] == "confirm"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"confirm_off": ["input_boolean.mischpult_strom"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert config_entry.options["switches"] == [
        "input_boolean.mischpult_strom",
        "input_boolean.licht",
    ]
    mock_api.put_switches.assert_awaited_with(
        [
            {
                "entityId": "input_boolean.mischpult_strom",
                "name": "Mischpult Strom",
                "confirmOff": True,
            },
            {"entityId": "input_boolean.licht", "name": "Licht", "confirmOff": False},
        ]
    )
