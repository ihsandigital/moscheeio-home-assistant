"""Diagnostics: the connection's state, without the token."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_TOKEN
from .hub import MoscheeioConfigEntry

TO_REDACT = {CONF_TOKEN, "deviceToken", "pinHash", "relayUrl"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MoscheeioConfigEntry
) -> dict[str, Any]:
    """What a bug report needs."""
    hub = entry.runtime_data
    runner = hub.runner
    config = hub.config
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "me": async_redact_data(hub.me, TO_REDACT),
        "online": hub.online,
        "last_error": hub.last_error,
        "relay_connected": hub.relay_connected,
        "relay_error": hub.relay.last_error if hub.relay else None,
        "desk_access": hub.desk_access,
        "live_rooms": hub.live_rooms,
        "desks": {
            box_id: {
                "online": desk.get("online"),
                "targets": len(hub.desk_targets(box_id)),
            }
            for box_id, desk in hub.desks.items()
        },
        "config": {
            "updatedAt": config.get("updatedAt"),
            "enabled": config.get("enabled"),
            "pausedUntil": config.get("pausedUntil"),
            "automations": [
                async_redact_data(automation, TO_REDACT)
                for automation in config.get("automations") or []
            ],
            "moments": len(config.get("moments") or []),
        },
        "switches": hub.switch_states(),
        "runner": {
            "unsent": len(runner.unsent) if runner else None,
            "last_run": runner.last_run if runner else None,
        },
    }
