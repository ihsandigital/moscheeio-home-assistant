"""The websocket to the Smart Mosque relay, which Home Assistant joins like a box.

The relay checks the token with moschee.io, then sends the mosque's desks
(``desks``, ``desk``) and moschee.io's commands (``command``), and passes
Home Assistant's ``desk_command`` on to a desk. The connection is kept up
with pings and rebuilt with backoff; nothing here is fatal.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import contextlib
import json
import logging
from typing import Any

import aiohttp

from .const import VERSION

_LOGGER = logging.getLogger(__name__)

PROTOCOL_VERSION = 1
PING_SECONDS = 25
# No message (not even a pong) for this long: the connection is dead.
STALE_SECONDS = 70
MIN_BACKOFF = 2
MAX_BACKOFF = 60

MessageHandler = Callable[[dict[str, Any]], Awaitable[None] | None]


class RelayClient:
    """Keeps one websocket to the relay open while started."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        get_url: Callable[[], str | None],
        get_token: Callable[[], str | None],
        on_message: MessageHandler,
        on_connection: Callable[[bool], None],
    ) -> None:
        self._session = session
        self._get_url = get_url
        self._get_token = get_token
        self._on_message = on_message
        self._on_connection = on_connection
        self._socket: aiohttp.ClientWebSocketResponse | None = None
        self._task: asyncio.Task[None] | None = None
        self._joined = False
        self._stopped = True
        self._wake = asyncio.Event()
        self.last_error: str | None = None

    @property
    def joined(self) -> bool:
        """Joined and accepted by the relay."""
        return self._joined

    def start(self, create_task: Callable[..., asyncio.Task[None]]) -> None:
        """Start connecting (create_task: the config entry's background task helper)."""
        if self._task is not None:
            return
        self._stopped = False
        self._task = create_task(self._run())

    def reconnect(self) -> None:
        """Connect again now (the relay URL changed, or a new token)."""
        self._wake.set()
        if self._socket is not None and not self._socket.closed:
            asyncio.get_running_loop().create_task(self._socket.close())

    async def stop(self) -> None:
        """Close the connection for good."""
        self._stopped = True
        self._wake.set()
        if self._socket is not None and not self._socket.closed:
            await self._socket.close()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self._set_joined(False)

    async def send(self, message: dict[str, Any]) -> bool:
        """Send a message if joined; False otherwise."""
        socket = self._socket
        if socket is None or socket.closed or not self._joined:
            return False
        try:
            await socket.send_str(json.dumps(message, separators=(",", ":")))
        except (aiohttp.ClientError, ConnectionError, RuntimeError):
            return False
        return True

    def _set_joined(self, joined: bool) -> None:
        if joined != self._joined:
            self._joined = joined
            self._on_connection(joined)

    async def _run(self) -> None:
        backoff = MIN_BACKOFF
        while not self._stopped:
            url = self._get_url()
            token = self._get_token()
            if url and token:
                try:
                    await self._connect_once(url, token)
                    backoff = MIN_BACKOFF
                except (aiohttp.ClientError, TimeoutError, ConnectionError) as err:
                    self.last_error = str(err) or type(err).__name__
                    _LOGGER.debug("Relay connection failed: %s", self.last_error)
                finally:
                    self._socket = None
                    self._set_joined(False)
            if self._stopped:
                break
            self._wake.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=backoff)
            backoff = min(backoff * 2, MAX_BACKOFF)

    async def _connect_once(self, url: str, token: str) -> None:
        async with self._session.ws_connect(
            url, heartbeat=None, timeout=aiohttp.ClientWSTimeout(ws_close=10)
        ) as socket:
            self._socket = socket
            await socket.send_str(
                json.dumps(
                    {
                        "type": "join",
                        "deviceToken": token,
                        "protocol": PROTOCOL_VERSION,
                        "version": VERSION,
                        "capabilities": ["switches", "desks"],
                    }
                )
            )
            pinger = asyncio.get_running_loop().create_task(self._ping(socket))
            try:
                while True:
                    message = await socket.receive(timeout=STALE_SECONDS)
                    if message.type in (
                        aiohttp.WSMsgType.CLOSE,
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.CLOSING,
                        aiohttp.WSMsgType.ERROR,
                    ):
                        break
                    if message.type != aiohttp.WSMsgType.TEXT:
                        continue
                    await self._handle(socket, message.data)
            finally:
                pinger.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await pinger

    async def _ping(self, socket: aiohttp.ClientWebSocketResponse) -> None:
        while not socket.closed:
            await asyncio.sleep(PING_SECONDS)
            with contextlib.suppress(
                aiohttp.ClientError, ConnectionError, RuntimeError
            ):
                await socket.send_str('{"type":"ping"}')

    async def _handle(self, socket: aiohttp.ClientWebSocketResponse, raw: str) -> None:
        try:
            message = json.loads(raw)
        except ValueError:
            return
        if not isinstance(message, dict) or not isinstance(message.get("type"), str):
            return
        kind = message["type"]
        if kind == "ping":
            await socket.send_str('{"type":"pong"}')
            return
        if kind == "pong":
            return
        if kind == "join_error":
            self.last_error = str(message.get("code") or "join_error")
            _LOGGER.warning("The relay refused Home Assistant: %s", self.last_error)
            await socket.close()
            return
        if kind == "joined":
            self.last_error = None
            self._set_joined(True)
        result = self._on_message(message)
        if asyncio.iscoroutine(result):
            await result
