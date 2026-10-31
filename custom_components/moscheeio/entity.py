"""Base entities: the moschee.io connection itself, and a desk channel."""

from __future__ import annotations

from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import CONF_BOX_ID, DOMAIN
from .hub import SIGNAL_UPDATE, MoscheeioHub


class MoscheeioEntity(Entity):
    """Updates whenever the hub signals."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hub: MoscheeioHub) -> None:
        self.hub = hub

    async def async_added_to_hass(self) -> None:
        """Listen to the hub."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_UPDATE.format(self.hub.entry.entry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class ConnectionEntity(MoscheeioEntity):
    """An entity of the moschee.io connection (one device per mosque)."""

    def __init__(self, hub: MoscheeioHub, key: str) -> None:
        super().__init__(hub)
        box_id = hub.entry.data[CONF_BOX_ID]
        self._attr_unique_id = f"{box_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, box_id)},
            name=hub.entry.title,
            manufacturer="moschee.io",
            model="Home Assistant",
            configuration_url=f"{hub.api.base_url}/smart-mosque/mixer",
        )


class DeskEntity(MoscheeioEntity):
    """One mapped channel of a sound desk of the mosque."""

    def __init__(self, hub: MoscheeioHub, box_id: str, target: str, key: str) -> None:
        super().__init__(hub)
        self.box_id = box_id
        self.target = target
        suffix = "" if key == "channel" else f"_{key}"
        self._attr_unique_id = f"{box_id}_{target.replace('/', '_')}{suffix}"
        desk = hub.desks.get(box_id) or {}
        info = ((desk.get("state") or {}).get("desk")) or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, box_id)},
            name=desk.get("boxName") or "Mischpult",
            manufacturer="Behringer",
            model=info.get("model") or "X32",
            sw_version=info.get("firmware"),
            via_device=(DOMAIN, hub.entry.data[CONF_BOX_ID]),
            configuration_url=f"{hub.api.base_url}/smart-mosque/mixer",
        )

    @property
    def channel(self) -> dict[str, Any] | None:
        """The target's last reported state."""
        return self.hub.desk_target(self.box_id, self.target)

    @property
    def channel_name(self) -> str:
        """moschee.io's label, the desk's name, or the target id."""
        channel = self.channel or {}
        return str(channel.get("label") or channel.get("deskName") or self.target)

    @property
    def available(self) -> bool:
        """Only while the desk is connected and reports the channel."""
        desk = self.hub.desks.get(self.box_id) or {}
        return (
            self.hub.relay_connected
            and desk.get("online") is True
            and self.channel is not None
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Target id, role, protection and who changed it last."""
        channel = self.channel or {}
        changed_by = channel.get("changedBy") or {}
        return {
            "target": self.target,
            "role": channel.get("role"),
            "protected": channel.get("protected"),
            "desk_name": channel.get("deskName"),
            "changed_at": channel.get("changedAt"),
            "changed_by": changed_by.get("name") or changed_by.get("kind"),
        }
