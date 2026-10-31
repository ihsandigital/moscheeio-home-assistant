"""Constants of the moschee.io integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "moscheeio"
VERSION: Final = "0.1.2"

# The device-authorization client moschee.io knows Home Assistant by. It
# creates a smart_mosque_box row of kind "home_assistant".
CLIENT_ID: Final = "smart-mosque-ha"
CLIENT_HEADER: Final = f"moscheeio-ha/{VERSION}"

ENVIRONMENTS: Final[dict[str, str]] = {
    "production": "https://app.moschee.io",
    "stage": "https://app.moschee-stage.de",
}

CONF_ENVIRONMENT: Final = "environment"
CONF_API_URL: Final = "api_url"
CONF_TOKEN: Final = "token"
CONF_BOX_ID: Final = "box_id"
CONF_ORGANIZATION_ID: Final = "organization_id"
CONF_SWITCHES: Final = "switches"
CONF_CONFIRM_OFF: Final = "confirm_off"

# What can be shared with moschee.io (it refuses other domains).
SWITCH_DOMAINS: Final = ("switch", "input_boolean", "light")
MAX_SHARED_SWITCHES: Final = 50

HEARTBEAT_SECONDS: Final = 60
CONFIG_REFRESH_SECONDS: Final = 600
RUN_TICK_SECONDS: Final = 5
RUN_FLUSH_SECONDS: Final = 30
# A run more than this late (Home Assistant was off) is skipped, as on the box.
MISSED_LIMIT_MS: Final = 2 * 60 * 1000
# How long Home Assistant waits for an entity to take its new state.
CONFIRM_SECONDS: Final = 5
DESK_COMMAND_TIMEOUT_SECONDS: Final = 10

DESK_ACCESS: Final = ("off", "view", "control")

STORAGE_VERSION: Final = 1
