"""Small helpers shared by the hub and the runner."""

from __future__ import annotations

from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import State


def entity_on(state: State | None) -> bool | None:
    """On, off, or None while unavailable."""
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return None
    return state.state == STATE_ON
