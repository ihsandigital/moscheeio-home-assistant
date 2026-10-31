"""One moschee.io connection: heartbeat, config, relay, shared switches and desks."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
import logging
from typing import Any
import uuid

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_FRIENDLY_NAME,
    __version__ as HA_VERSION,
)
from homeassistant.core import (
    Context,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .api import (
    MoscheeioApi,
    MoscheeioAuthError,
    MoscheeioConnectionError,
    MoscheeioError,
    MoscheeioNotLinkedError,
)
from .const import (
    CONF_API_URL,
    CONF_CONFIRM_OFF,
    CONF_SWITCHES,
    CONF_TOKEN,
    CONFIG_REFRESH_SECONDS,
    CONFIRM_SECONDS,
    DESK_ACCESS,
    DESK_COMMAND_TIMEOUT_SECONDS,
    DOMAIN,
    HEARTBEAT_SECONDS,
    STORAGE_VERSION,
    SWITCH_DOMAINS,
)
from .helpers import entity_on
from .relay import RelayClient
from .runner import AutomationRunner

_LOGGER = logging.getLogger(__name__)

SIGNAL_UPDATE = f"{DOMAIN}_update_{{}}"
SIGNAL_NEW_TARGETS = f"{DOMAIN}_new_targets_{{}}"

type MoscheeioConfigEntry = ConfigEntry[MoscheeioHub]


class MoscheeioHub:
    """Everything one config entry keeps running."""

    def __init__(self, hass: HomeAssistant, entry: MoscheeioConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.api = MoscheeioApi(
            async_get_clientsession(hass),
            entry.data[CONF_API_URL],
            entry.data[CONF_TOKEN],
            platform=f"os=Home Assistant;osVersion={HA_VERSION}",
        )
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self.me: dict[str, Any] = {}
        self.config: dict[str, Any] = {}
        self.desk_access: str = "view"
        self.live_rooms = 0
        self.relay_connected = False
        self.online = False
        self.last_error: str | None = None
        # boxId -> { boxId, boxName, online, state }
        self.desks: dict[str, dict[str, Any]] = {}
        self._known_targets: set[tuple[str, str]] = set()
        # entityId -> { kind, name } of the last change, for moschee.io.
        self._changed_by: dict[str, dict[str, Any]] = {}
        self._contexts: dict[str, dict[str, Any]] = {}
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._unsubs: list[Callable[[], None]] = []
        self._unsub_states: Callable[[], None] | None = None
        self._state_task: asyncio.TimerHandle | None = None
        self.stored: dict[str, Any] = {}
        self.relay: RelayClient | None = None
        self.runner: AutomationRunner | None = None

    # Setup

    async def async_setup(self) -> None:
        """Load what was kept on disk and ask moschee.io; works offline from the cache."""
        self.stored = await self._store.async_load() or {}
        cached = self.stored.get("config")
        if isinstance(cached, dict):
            self.config = cached
        me = self.stored.get("me")
        if isinstance(me, dict):
            self._apply_me(me)
        try:
            self._apply_me(await self.api.me())
            self.online = True
        except MoscheeioAuthError:
            raise
        except MoscheeioNotLinkedError:
            self.last_error = "not_linked"
        except MoscheeioConnectionError as err:
            self.last_error = str(err)
            if not self.me:
                raise
        await self.async_refresh_config()
        await self.async_share_switches()

    def start(self) -> None:
        """Start the heartbeat, the relay and the switch-state listener."""
        self.relay = RelayClient(
            async_get_clientsession(self.hass),
            lambda: self.me.get("relayUrl"),
            lambda: self.api.token,
            self._on_relay_message,
            self._on_relay_connection,
        )
        self.relay.start(
            lambda coro: self.entry.async_create_background_task(
                self.hass, coro, f"{DOMAIN} relay"
            )
        )
        self.runner = AutomationRunner(self)
        self.runner.start()
        self._unsubs.append(
            async_track_time_interval(
                self.hass, self._heartbeat, timedelta(seconds=HEARTBEAT_SECONDS)
            )
        )
        self._unsubs.append(
            async_track_time_interval(
                self.hass,
                self._periodic_config,
                timedelta(seconds=CONFIG_REFRESH_SECONDS),
            )
        )
        self._track_shared_states()

    async def async_stop(self) -> None:
        """Stop everything (unload)."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._unsub_states:
            self._unsub_states()
            self._unsub_states = None
        if self._state_task:
            self._state_task.cancel()
        if self.runner:
            await self.runner.async_stop()
        if self.relay:
            await self.relay.stop()
        for future in self._pending.values():
            if not future.done():
                future.cancel()

    async def async_save(self) -> None:
        """Keep the config, the identity and the runner's state on disk."""
        self.stored["config"] = self.config
        self.stored["me"] = self.me
        await self._store.async_save(self.stored)

    # moschee.io

    def _apply_me(self, me: dict[str, Any]) -> None:
        previous_url = self.me.get("relayUrl")
        previous_config = self.me.get("configUpdatedAt")
        self.me = me
        access = me.get("deskAccess")
        if access in DESK_ACCESS:
            self.desk_access = access
        live = me.get("liveRooms")
        self.live_rooms = live if isinstance(live, int) and live >= 0 else 0
        if self.relay and previous_url and previous_url != me.get("relayUrl"):
            self.relay.reconnect()
        if previous_config and previous_config != me.get("configUpdatedAt"):
            self.hass.async_create_task(self.async_refresh_config())

    async def _heartbeat(self, _now: datetime | None = None) -> None:
        access_before = self.desk_access
        try:
            self._apply_me(await self.api.me())
            self.online = True
            self.last_error = None
        except MoscheeioAuthError:
            _LOGGER.warning("moschee.io no longer knows this Home Assistant")
            self.online = False
            self.entry.async_start_reauth(self.hass)
        except MoscheeioNotLinkedError:
            self.online = False
            self.last_error = "not_linked"
        except MoscheeioConnectionError as err:
            self.online = False
            self.last_error = str(err)
        self._signal_update()
        if access_before != self.desk_access:
            self._access_changed()

    async def _periodic_config(self, _now: datetime | None = None) -> None:
        await self.async_refresh_config()

    async def async_refresh_config(self) -> None:
        """Fetch the switch rules and the prayer moments; keep the last on failure."""
        try:
            config = await self.api.config()
        except MoscheeioError as err:
            _LOGGER.debug("Could not fetch the config: %s", err)
            return
        self.config = config
        access = config.get("deskAccess")
        if access in DESK_ACCESS and access != self.desk_access:
            self.desk_access = access
            self._access_changed()
        await self.async_save()
        self._signal_update()

    def shared_entity_ids(self) -> list[str]:
        """The entities the user chose to share, in their order."""
        return [
            entity_id
            for entity_id in self.entry.options.get(CONF_SWITCHES, [])
            if entity_id.split(".", 1)[0] in SWITCH_DOMAINS
        ]

    async def async_share_switches(self) -> None:
        """Send the shared entities to moschee.io (setup and options changes)."""
        confirm_off = set(self.entry.options.get(CONF_CONFIRM_OFF, []))
        payload = []
        for entity_id in self.shared_entity_ids():
            state = self.hass.states.get(entity_id)
            name = (
                state.attributes.get(ATTR_FRIENDLY_NAME) if state else None
            ) or entity_id
            payload.append(
                {
                    "entityId": entity_id,
                    "name": str(name)[:80],
                    "confirmOff": entity_id in confirm_off,
                }
            )
        try:
            await self.api.put_switches(payload)
        except MoscheeioError as err:
            _LOGGER.warning("Could not share the switches with moschee.io: %s", err)

    # Shared switches

    def _track_shared_states(self) -> None:
        if self._unsub_states:
            self._unsub_states()
        entity_ids = self.shared_entity_ids()
        self._unsub_states = (
            async_track_state_change_event(self.hass, entity_ids, self._state_changed)
            if entity_ids
            else None
        )

    @callback
    def _state_changed(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        new_state = event.data["new_state"]
        old_state = event.data["old_state"]
        if (
            new_state is not None
            and old_state is not None
            and new_state.state == old_state.state
        ):
            return
        context = event.context
        at = new_state.last_changed if new_state else dt_util.utcnow()
        by = self._contexts.get(context.id)
        if by is None:
            by = {"kind": "home_assistant", "name": None}
            if context.user_id:
                self.hass.async_create_task(
                    self._resolve_user(entity_id, context.user_id, at)
                )
        self._changed_by[entity_id] = {**by, "at": at}
        self._schedule_state()

    async def _resolve_user(self, entity_id: str, user_id: str, at: datetime) -> None:
        """Name the Home Assistant user who switched an entity."""
        user = await self.hass.auth.async_get_user(user_id)
        change = self._changed_by.get(entity_id)
        if user is not None and change is not None and change.get("at") == at:
            change["name"] = user.name
            self._schedule_state()

    def note_change(self, entity_id: str, by: dict[str, Any], context: Context) -> None:
        """Remember who asked for a change we make (moschee.io or a rule)."""
        self._contexts[context.id] = {"kind": by.get("kind"), "name": by.get("name")}
        if len(self._contexts) > 100:
            for key in list(self._contexts)[:50]:
                del self._contexts[key]
        self._changed_by[entity_id] = {
            **self._contexts[context.id],
            "at": dt_util.utcnow(),
        }

    def last_change(self, entity_id: str) -> dict[str, Any] | None:
        """Who changed the entity last, and when (only what we saw)."""
        return self._changed_by.get(entity_id)

    def switch_states(self) -> list[dict[str, Any]]:
        """The shared entities as moschee.io's Schalter card shows them."""
        out = []
        for entity_id in self.shared_entity_ids():
            state = self.hass.states.get(entity_id)
            on = entity_on(state)
            change = self._changed_by.get(entity_id)
            out.append(
                {
                    "entityId": entity_id,
                    "name": str(
                        (state.attributes.get(ATTR_FRIENDLY_NAME) if state else None)
                        or entity_id
                    )[:80],
                    "on": on,
                    "available": on is not None,
                    "changedAt": state.last_changed.isoformat() if state else None,
                    "changedBy": (
                        {"kind": change["kind"], "name": change.get("name")}
                        if change
                        else None
                    ),
                }
            )
        return out

    @callback
    def _schedule_state(self) -> None:
        """Send the switches' state soon (debounced)."""
        if self._state_task is not None:
            return

        def _send() -> None:
            self._state_task = None
            self.hass.async_create_task(self.async_send_state())

        self._state_task = self.hass.loop.call_later(0.3, _send)

    async def async_send_state(self) -> None:
        """The shared entities, to moschee.io through the relay."""
        if self.relay:
            await self.relay.send({"type": "state", "switches": self.switch_states()})

    async def async_switch(self, entity_id: str, on: bool, by: dict[str, Any]) -> bool:
        """Switch a shared entity and wait until it shows the new state."""
        domain = entity_id.split(".", 1)[0]
        context = Context()
        self.note_change(entity_id, by, context)
        await self.hass.services.async_call(
            domain,
            "turn_on" if on else "turn_off",
            {ATTR_ENTITY_ID: entity_id},
            blocking=True,
            context=context,
        )
        loop = asyncio.get_running_loop()
        deadline = loop.time() + CONFIRM_SECONDS
        while loop.time() < deadline:
            if entity_on(self.hass.states.get(entity_id)) is on:
                return True
            await asyncio.sleep(0.2)
        return entity_on(self.hass.states.get(entity_id)) is on

    # Relay

    @callback
    def _on_relay_connection(self, joined: bool) -> None:
        self.relay_connected = joined
        if not joined:
            for desk in self.desks.values():
                desk["online"] = False
        self._signal_update()

    async def _on_relay_message(self, message: dict[str, Any]) -> None:
        kind = message.get("type")
        if kind == "joined":
            access = message.get("deskAccess")
            if access in DESK_ACCESS and access != self.desk_access:
                self.desk_access = access
                self._access_changed()
            await self.async_send_state()
        elif kind == "desks":
            access = message.get("deskAccess")
            if access in DESK_ACCESS and access != self.desk_access:
                self.desk_access = access
                self._access_changed()
            self.desks = {}
            for desk in message.get("desks") or []:
                self._update_desk(desk)
            self._signal_update()
        elif kind == "desk":
            self._update_desk(message)
            self._signal_update()
        elif kind == "desk_command_result":
            future = self._pending.pop(str(message.get("id")), None)
            if future and not future.done():
                future.set_result(message)
        elif kind == "command":
            # Answered in its own task: a switch can take a few seconds.
            self.entry.async_create_background_task(
                self.hass, self._command(message), f"{DOMAIN} command"
            )

    def _update_desk(self, desk: Any) -> None:
        if not isinstance(desk, dict) or not isinstance(desk.get("boxId"), str):
            return
        box_id = desk["boxId"]
        state = desk.get("state") if isinstance(desk.get("state"), dict) else None
        previous = self.desks.get(box_id, {})
        self.desks[box_id] = {
            "boxId": box_id,
            "boxName": desk.get("boxName") or previous.get("boxName"),
            "online": desk.get("online") is True,
            # Keep the last state while a desk is offline: its entities stay known.
            "state": state if state is not None else previous.get("state"),
        }
        new = [
            (box_id, target["target"])
            for target in self.desk_targets(box_id)
            if (box_id, target["target"]) not in self._known_targets
        ]
        if new:
            self._known_targets.update(new)
            async_dispatcher_send(
                self.hass, SIGNAL_NEW_TARGETS.format(self.entry.entry_id), new
            )

    def desk_targets(self, box_id: str) -> list[dict[str, Any]]:
        """The mapped targets a desk reports."""
        state = (self.desks.get(box_id) or {}).get("state") or {}
        targets = state.get("targets")
        return [
            target
            for target in targets or []
            if isinstance(target, dict) and isinstance(target.get("target"), str)
        ]

    def desk_target(self, box_id: str, target: str) -> dict[str, Any] | None:
        """One mapped target of a desk."""
        for entry in self.desk_targets(box_id):
            if entry["target"] == target:
                return entry
        return None

    async def async_desk_command(self, box_id: str, command: dict[str, Any]) -> None:
        """Switch a desk channel through the relay; raise if refused."""
        if self.desk_access != "control":
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="not_allowed"
            )
        command_id = uuid.uuid4().hex
        future: asyncio.Future[dict[str, Any]] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending[command_id] = future
        sent = self.relay is not None and await self.relay.send(
            {
                "type": "desk_command",
                "id": command_id,
                "boxId": box_id,
                "command": command,
            }
        )
        if not sent:
            self._pending.pop(command_id, None)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="relay_offline"
            )
        try:
            result = await asyncio.wait_for(future, DESK_COMMAND_TIMEOUT_SECONDS)
        except TimeoutError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="desk_timeout"
            ) from err
        finally:
            self._pending.pop(command_id, None)
        if result.get("ok") is not True:
            code = str(result.get("code") or "failed")
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="desk_refused",
                translation_placeholders={"code": code},
            )

    async def _command(self, message: dict[str, Any]) -> None:
        command_id = message.get("id")
        command = message.get("command")
        result = await self.async_handle_command(
            command if isinstance(command, dict) else {}
        )
        if self.relay:
            await self.relay.send(
                {"type": "command_result", "id": command_id, **result}
            )

    async def async_handle_command(self, command: dict[str, Any]) -> dict[str, Any]:
        """moschee.io's commands: state, switch_set, config_changed."""
        kind = command.get("type")
        if kind == "state":
            await self.async_send_state()
            return {"ok": True, "result": {"switches": self.switch_states()}}
        if kind == "config_changed":
            await self.async_refresh_config()
            return {"ok": True}
        if kind != "switch_set":
            return {"ok": False, "code": "unknown_command"}
        entity_id = command.get("entityId")
        on = command.get("on")
        if not isinstance(entity_id, str) or not isinstance(on, bool):
            return {"ok": False, "code": "bad_request"}
        if entity_id not in self.shared_entity_ids():
            return {"ok": False, "code": "unknown_entity"}
        if entity_on(self.hass.states.get(entity_id)) is None:
            return {"ok": False, "code": "unavailable"}
        by = command.get("by") if isinstance(command.get("by"), dict) else {}
        try:
            confirmed = await self.async_switch(
                entity_id,
                on,
                {"kind": by.get("kind") or "person", "name": by.get("name")},
            )
        except HomeAssistantError as err:
            _LOGGER.warning("Could not switch %s: %s", entity_id, err)
            return {"ok": False, "code": "failed"}
        await self.async_send_state()
        if not confirmed:
            return {"ok": False, "code": "not_confirmed"}
        return {"ok": True, "result": {"entityId": entity_id, "on": on}}

    # Entities

    @callback
    def _access_changed(self) -> None:
        """Desk entities differ per access: reload to build the right ones."""
        _LOGGER.info("Desk access in moschee.io is now %s", self.desk_access)
        self.hass.config_entries.async_schedule_reload(self.entry.entry_id)

    @callback
    def _signal_update(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_UPDATE.format(self.entry.entry_id))

    @callback
    def options_changed(self) -> None:
        """Shared entities changed in the options: track and report them."""
        self._track_shared_states()
        self.hass.async_create_task(self.async_share_switches())
        self._schedule_state()
