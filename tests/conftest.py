"""Fixtures."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.moscheeio.const import (
    CONF_API_URL,
    CONF_BOX_ID,
    CONF_ORGANIZATION_ID,
    CONF_TOKEN,
    DOMAIN,
)

BOX_ID = "7c9e6679-7425-40de-944b-e07fc1f90ae7"
DESK_ID = "9b2f0c1e-1111-4222-8333-444455556666"
ORG_ID = "org_1"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components/."""


def me_payload(**overrides: Any) -> dict[str, Any]:
    """What /api/smart-mosque/me answers for Home Assistant."""
    return {
        "boxId": BOX_ID,
        "kind": "home_assistant",
        "deskAccess": "control",
        "organizationId": ORG_ID,
        "organizationName": "IGS Moschee",
        "organizationSlug": "igs",
        "boxName": "Home Assistant",
        "relayUrl": "wss://relay.test",
        "locale": "de",
        "configUpdatedAt": "2026-10-31T10:00:00.000Z",
        "liveRooms": 0,
        **overrides,
    }


def config_payload(**overrides: Any) -> dict[str, Any]:
    """What /api/smart-mosque/config answers for Home Assistant."""
    return {
        "updatedAt": "2026-10-31T10:00:00.000Z",
        "kind": "home_assistant",
        "timeZone": "Europe/Berlin",
        "enabled": True,
        "pausedUntil": None,
        "mapping": [],
        "automations": [],
        "moments": [],
        "switches": [],
        "deskAccess": "control",
        **overrides,
    }


@pytest.fixture
def mock_api() -> Generator[AsyncMock]:
    """The REST client, without network."""
    with patch(
        "custom_components.moscheeio.hub.MoscheeioApi", autospec=True
    ) as api_class:
        api = api_class.return_value
        api.base_url = "https://app.moschee.io"
        api.token = "token"
        api.me.return_value = me_payload()
        api.config.return_value = config_payload()
        api.put_switches.return_value = {"switches": []}
        api.post_runs.return_value = None
        yield api


@pytest.fixture
def mock_relay() -> Generator[AsyncMock]:
    """The relay websocket, without network."""
    with patch(
        "custom_components.moscheeio.hub.RelayClient", autospec=True
    ) as relay_class:
        relay = relay_class.return_value
        relay.send.return_value = True
        relay.last_error = None
        yield relay


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A paired entry sharing one switch."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=BOX_ID,
        title="IGS Moschee",
        data={
            CONF_API_URL: "https://app.moschee.io",
            CONF_TOKEN: "token",
            CONF_BOX_ID: BOX_ID,
            CONF_ORGANIZATION_ID: ORG_ID,
        },
        options={
            "switches": ["input_boolean.mischpult_strom"],
            "confirm_off": ["input_boolean.mischpult_strom"],
        },
    )
