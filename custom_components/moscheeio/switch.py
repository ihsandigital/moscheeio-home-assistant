"""Desk channels Home Assistant may switch (moschee.io access "Steuern")."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import DeskEntity
from .hub import SIGNAL_NEW_TARGETS, MoscheeioConfigEntry, MoscheeioHub


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MoscheeioConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Channel switches as desks report their channels."""
    hub = entry.runtime_data
    if hub.desk_access != "control":
        return

    @callback
    def _add(targets: list[tuple[str, str]]) -> None:
        async_add_entities(
            DeskChannelSwitch(hub, box_id, target) for box_id, target in targets
        )

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_TARGETS.format(entry.entry_id), _add)
    )


class DeskChannelSwitch(DeskEntity, SwitchEntity):
    """A desk channel: on is not muted. The desk refuses to mute a protected
    channel during the prayer."""

    def __init__(self, hub: MoscheeioHub, box_id: str, target: str) -> None:
        super().__init__(hub, box_id, target, "channel")

    @property
    def name(self) -> str:
        """moschee.io's label of the channel."""
        return self.channel_name

    @property
    def icon(self) -> str:
        """A microphone, crossed out while muted."""
        return "mdi:microphone-off" if self.is_on is False else "mdi:microphone"

    @property
    def is_on(self) -> bool | None:
        """Not muted."""
        muted = (self.channel or {}).get("muted")
        return None if muted is None else not muted

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Unmute."""
        await self.hub.async_desk_command(
            self.box_id, {"type": "mixer_set", "target": self.target, "muted": False}
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Mute."""
        await self.hub.async_desk_command(
            self.box_id, {"type": "mixer_set", "target": self.target, "muted": True}
        )
