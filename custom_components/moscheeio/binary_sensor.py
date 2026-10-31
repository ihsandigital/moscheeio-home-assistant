"""The relay connection, and the desk channels while moschee.io allows viewing only."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import ConnectionEntity, DeskEntity
from .hub import SIGNAL_NEW_TARGETS, MoscheeioConfigEntry, MoscheeioHub


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MoscheeioConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """The connection sensor; channel sensors as desks report their channels."""
    hub = entry.runtime_data
    async_add_entities([RelayConnectedSensor(hub)])
    if hub.desk_access != "view":
        return

    @callback
    def _add(targets: list[tuple[str, str]]) -> None:
        async_add_entities(
            DeskChannelSensor(hub, box_id, target) for box_id, target in targets
        )

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_TARGETS.format(entry.entry_id), _add)
    )


class RelayConnectedSensor(ConnectionEntity, BinarySensorEntity):
    """Connected to moschee.io's relay (moschee.io can switch now)."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hub: MoscheeioHub) -> None:
        super().__init__(hub, "relay")

    @property
    def is_on(self) -> bool:
        """Joined the relay."""
        return self.hub.relay_connected


class DeskChannelSensor(DeskEntity, BinarySensorEntity):
    """A desk channel, on while it is not muted (read only)."""

    _attr_device_class = BinarySensorDeviceClass.SOUND

    def __init__(self, hub: MoscheeioHub, box_id: str, target: str) -> None:
        super().__init__(hub, box_id, target, "channel")

    @property
    def name(self) -> str:
        """moschee.io's label of the channel."""
        return self.channel_name

    @property
    def is_on(self) -> bool | None:
        """Not muted."""
        muted = (self.channel or {}).get("muted")
        return None if muted is None else not muted
