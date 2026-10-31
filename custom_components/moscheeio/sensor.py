"""Live translations of the mosque, the next switch rule, and desk levels."""

from __future__ import annotations

from datetime import UTC, datetime
import time
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .automations import next_due
from .entity import ConnectionEntity, DeskEntity
from .hub import SIGNAL_NEW_TARGETS, MoscheeioConfigEntry, MoscheeioHub


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MoscheeioConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Connection sensors; a level sensor per desk channel with a fader."""
    hub = entry.runtime_data
    async_add_entities([LiveRoomsSensor(hub), NextRuleSensor(hub)])
    if hub.desk_access == "off":
        return

    @callback
    def _add(targets: list[tuple[str, str]]) -> None:
        entities = []
        for box_id, target in targets:
            channel = hub.desk_target(box_id, target) or {}
            if channel.get("hasFader"):
                entities.append(DeskLevelSensor(hub, box_id, target))
        async_add_entities(entities)

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_TARGETS.format(entry.entry_id), _add)
    )


class LiveRoomsSensor(ConnectionEntity, SensorEntity):
    """Live translation rooms of the mosque (rules never switch off while > 0)."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, hub: MoscheeioHub) -> None:
        super().__init__(hub, "live_rooms")

    @property
    def native_value(self) -> int:
        """How many rooms are live."""
        return self.hub.live_rooms


class NextRuleSensor(ConnectionEntity, SensorEntity):
    """When the next switch rule runs."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, hub: MoscheeioHub) -> None:
        super().__init__(hub, "next_rule")

    def _next(self) -> tuple[int, dict[str, Any], dict[str, Any]] | None:
        runner = self.hub.runner
        if runner is None:
            return None
        return next_due(runner.automations(), runner.moments(), int(time.time() * 1000))

    @property
    def native_value(self) -> datetime | None:
        """The next run's time."""
        upcoming = self._next()
        return datetime.fromtimestamp(upcoming[0] / 1000, tz=UTC) if upcoming else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Which rule, at which prayer."""
        upcoming = self._next()
        if not upcoming:
            return {}
        _, automation, moment = upcoming
        return {
            "rule": automation.get("name"),
            "mode": automation.get("mode"),
            "prayer": moment.get("prayer"),
            "event": moment.get("event"),
        }


class DeskLevelSensor(DeskEntity, SensorEntity):
    """A desk channel's fader in dB."""

    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_translation_key = "level"

    def __init__(self, hub: MoscheeioHub, box_id: str, target: str) -> None:
        super().__init__(hub, box_id, target, "level")

    @property
    def translation_placeholders(self) -> dict[str, str]:
        """The channel's name in the entity name."""
        return {"channel": self.channel_name}

    @property
    def native_value(self) -> float | None:
        """dB, or None below -90 (off)."""
        db = (self.channel or {}).get("db")
        return float(db) if isinstance(db, int | float) else None
