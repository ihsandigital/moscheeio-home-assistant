"""Pairing with moschee.io by code, and choosing what moschee.io may switch."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
import voluptuous as vol

from .api import (
    DeviceCode,
    DeviceFlowError,
    MoscheeioApi,
    MoscheeioError,
    MoscheeioNotLinkedError,
)
from .const import (
    CONF_API_URL,
    CONF_BOX_ID,
    CONF_CONFIRM_OFF,
    CONF_ENVIRONMENT,
    CONF_ORGANIZATION_ID,
    CONF_SWITCHES,
    CONF_TOKEN,
    DOMAIN,
    ENVIRONMENTS,
    MAX_SHARED_SWITCHES,
    SWITCH_DOMAINS,
)
from .hub import MoscheeioConfigEntry

_LOGGER = logging.getLogger(__name__)


class MoscheeioConfigFlow(ConfigFlow, domain=DOMAIN):
    """Pair Home Assistant with a mosque on moschee.io."""

    VERSION = 1

    def __init__(self) -> None:
        self._api_url = ENVIRONMENTS["production"]
        self._code: DeviceCode | None = None
        self._poll: asyncio.Task[str] | None = None
        self._token: str | None = None
        self._me: dict[str, Any] = {}
        self._error: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose moschee.io or its stage environment."""
        if user_input is not None:
            self._api_url = ENVIRONMENTS[user_input[CONF_ENVIRONMENT]]
            return await self.async_step_code()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ENVIRONMENT, default="production"
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=list(ENVIRONMENTS),
                            translation_key="environment",
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """The connection was removed in moschee.io: pair again."""
        self._api_url = entry_data.get(CONF_API_URL, ENVIRONMENTS["production"])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask before showing a new code."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        return await self.async_step_code()

    async def async_step_code(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the code and wait until an admin confirms it on moschee.io."""
        if self._code is None:
            api = MoscheeioApi(async_get_clientsession(self.hass), self._api_url)
            try:
                self._code = await api.request_device_code()
            except MoscheeioError:
                return self.async_abort(reason="cannot_connect")
            self._poll = self.hass.async_create_task(api.wait_for_token(self._code))
        assert self._poll is not None
        if not self._poll.done():
            return self.async_show_progress(
                step_id="code",
                progress_action="wait_for_approval",
                description_placeholders={
                    "url": self._code.verification_uri_complete,
                    "code": self._code.user_code,
                },
                progress_task=self._poll,
            )
        try:
            self._token = self._poll.result()
        except DeviceFlowError as err:
            self._error = "denied" if err.code == "access_denied" else "expired"
            return self.async_show_progress_done(next_step_id="failed")
        except MoscheeioError:
            self._error = "cannot_connect"
            return self.async_show_progress_done(next_step_id="failed")
        return self.async_show_progress_done(next_step_id="finish")

    async def async_step_failed(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """The code was refused or expired."""
        return self.async_abort(reason=self._error or "expired")

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Name the entry after the mosque and store the token."""
        api = MoscheeioApi(
            async_get_clientsession(self.hass), self._api_url, self._token
        )
        try:
            self._me = await api.me()
        except MoscheeioNotLinkedError:
            return self.async_abort(reason="not_linked")
        except MoscheeioError:
            return self.async_abort(reason="cannot_connect")
        box_id = str(self._me.get("boxId"))
        data = {
            CONF_API_URL: self._api_url,
            CONF_TOKEN: self._token,
            CONF_BOX_ID: box_id,
            CONF_ORGANIZATION_ID: self._me.get("organizationId"),
        }
        title = str(self._me.get("organizationName") or "moschee.io")
        if self.source == SOURCE_REAUTH:
            # A new pairing is a new connection in moschee.io.
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), unique_id=box_id, title=title, data=data
            )
        await self.async_set_unique_id(box_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=title, data=data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: MoscheeioConfigEntry) -> OptionsFlow:
        """Choose the shared switches."""
        return MoscheeioOptionsFlow()


class MoscheeioOptionsFlow(OptionsFlow):
    """Which entities moschee.io may see and switch, and which ask before off."""

    def __init__(self) -> None:
        self._switches: list[str] = []

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the entities."""
        errors: dict[str, str] = {}
        if user_input is not None:
            chosen = list(dict.fromkeys(user_input.get(CONF_SWITCHES, [])))
            if len(chosen) > MAX_SHARED_SWITCHES:
                errors[CONF_SWITCHES] = "too_many"
            else:
                self._switches = chosen
                if not chosen:
                    return self.async_create_entry(
                        data={CONF_SWITCHES: [], CONF_CONFIRM_OFF: []}
                    )
                return await self.async_step_confirm()
        # The desk's own channels are not offered: moschee.io switches them directly.
        registry = er.async_get(self.hass)
        own = [
            entry.entity_id
            for entry in registry.entities.values()
            if entry.platform == DOMAIN
        ]
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SWITCHES,
                        default=self.config_entry.options.get(CONF_SWITCHES, []),
                    ): EntitySelector(
                        EntitySelectorConfig(
                            domain=list(SWITCH_DOMAINS),
                            multiple=True,
                            exclude_entities=own,
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Which of them moschee.io asks about before switching off."""
        if user_input is not None:
            confirm = [
                entity_id
                for entity_id in user_input.get(CONF_CONFIRM_OFF, [])
                if entity_id in self._switches
            ]
            return self.async_create_entry(
                data={CONF_SWITCHES: self._switches, CONF_CONFIRM_OFF: confirm}
            )
        options = []
        for entity_id in self._switches:
            state = self.hass.states.get(entity_id)
            name = state.name if state else entity_id
            options.append(SelectOptionDict(value=entity_id, label=name))
        previous = [
            entity_id
            for entity_id in self.config_entry.options.get(CONF_CONFIRM_OFF, [])
            if entity_id in self._switches
        ]
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_CONFIRM_OFF, default=previous): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )
