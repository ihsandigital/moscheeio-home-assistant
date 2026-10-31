"""moschee.io for Home Assistant.

Shares chosen switches with moschee.io (shown next to the Mischpult, switched
from the dashboard and the app), runs the mosque's switch rules at the prayer
times, and shows the mosque's sound desk channels as entities.
"""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .api import MoscheeioAuthError, MoscheeioConnectionError
from .hub import MoscheeioConfigEntry, MoscheeioHub

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: MoscheeioConfigEntry) -> bool:
    """Connect to moschee.io and its relay."""
    hub = MoscheeioHub(hass, entry)
    try:
        await hub.async_setup()
    except MoscheeioAuthError as err:
        raise ConfigEntryAuthFailed(
            translation_domain="moscheeio", translation_key="auth_failed"
        ) from err
    except MoscheeioConnectionError as err:
        raise ConfigEntryNotReady(str(err)) from err
    entry.runtime_data = hub
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    hub.start()
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    return True


async def _options_updated(hass: HomeAssistant, entry: MoscheeioConfigEntry) -> None:
    entry.runtime_data.options_changed()


async def async_unload_entry(hass: HomeAssistant, entry: MoscheeioConfigEntry) -> bool:
    """Close the relay and stop the rules."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_stop()
    return unloaded
