"""moschee.io's REST API, as the Smart-Mosque-Box uses it.

Pairing is the OAuth 2.0 device authorization grant (RFC 8628) with the
client id ``smart-mosque-ha``: Home Assistant shows a code, an admin of the
mosque confirms it on moschee.io, and Home Assistant gets a session token it
sends as a Bearer credential from then on.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import aiohttp

from .const import CLIENT_HEADER, CLIENT_ID

SCOPE = "openid profile email"
GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)


class MoscheeioError(Exception):
    """Base error of the API client."""


class MoscheeioConnectionError(MoscheeioError):
    """moschee.io could not be reached or answered with a server error."""


class MoscheeioAuthError(MoscheeioError):
    """The token is no longer valid: the connection was removed in moschee.io."""


class MoscheeioNotLinkedError(MoscheeioError):
    """The token is valid but not linked to a mosque (yet)."""


class DeviceFlowError(MoscheeioError):
    """The pairing code ended: denied, expired or refused."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class DeviceCode:
    """A pairing code for the admin to confirm."""

    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    interval: int
    expires_in: int


class MoscheeioApi:
    """The endpoints Home Assistant talks to."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        token: str | None = None,
        platform: str | None = None,
    ) -> None:
        self._session = session
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._platform = platform

    # Pairing

    async def request_device_code(self) -> DeviceCode:
        """Ask moschee.io for a new pairing code."""
        data = await self._post_json(
            "/api/auth/device/code", {"client_id": CLIENT_ID, "scope": SCOPE}
        )
        device_code = data.get("device_code")
        user_code = data.get("user_code")
        uri = data.get("verification_uri")
        if not (
            isinstance(device_code, str)
            and isinstance(user_code, str)
            and isinstance(uri, str)
        ):
            raise MoscheeioConnectionError("unexpected response")
        complete = data.get("verification_uri_complete")
        if not isinstance(complete, str) or not complete:
            joiner = "&" if "?" in uri else "?"
            complete = f"{uri}{joiner}user_code={user_code.strip()}"
        return DeviceCode(
            device_code=device_code,
            user_code=user_code.strip(),
            verification_uri=uri,
            verification_uri_complete=complete,
            interval=min(max(_int(data.get("interval"), 5), 1), 60),
            expires_in=max(_int(data.get("expires_in"), 1800), 60),
        )

    async def wait_for_token(self, code: DeviceCode) -> str:
        """Poll until the admin confirmed the code; raise DeviceFlowError if it ends."""
        interval = code.interval
        loop = asyncio.get_running_loop()
        deadline = loop.time() + code.expires_in
        while loop.time() < deadline:
            await asyncio.sleep(interval)
            try:
                data = await self._post_json(
                    "/api/auth/device/token",
                    {
                        "grant_type": GRANT_TYPE,
                        "device_code": code.device_code,
                        "client_id": CLIENT_ID,
                    },
                    accept_errors=True,
                )
            except MoscheeioConnectionError:
                # A network hiccup: keep polling until the code expires.
                continue
            token = data.get("access_token")
            if isinstance(token, str) and token.strip():
                return token.strip()
            error = data.get("error")
            if error in (None, "authorization_pending"):
                continue
            if error == "slow_down":
                interval = min(interval + 5, 60)
                continue
            raise DeviceFlowError(str(error))
        raise DeviceFlowError("expired_token")

    # Device endpoints

    async def me(self) -> dict[str, Any]:
        """Heartbeat and identity: boxId, kind, deskAccess, relayUrl, liveRooms."""
        headers = {"X-Smart-Client": CLIENT_HEADER}
        if self._platform:
            headers["X-Smart-Platform"] = self._platform
        return await self._request("GET", "/api/smart-mosque/me", headers=headers)

    async def config(self) -> dict[str, Any]:
        """Switch rules, pause and the prayer moments of the next days."""
        return await self._request("GET", "/api/smart-mosque/config")

    async def put_switches(self, switches: list[dict[str, Any]]) -> dict[str, Any]:
        """Tell moschee.io which entities it may see and switch."""
        return await self._request(
            "PUT", "/api/smart-mosque/switches", json={"switches": switches}
        )

    async def post_runs(self, runs: list[dict[str, Any]]) -> None:
        """Report what the switch rules did (the Verlauf)."""
        await self._request("POST", "/api/smart-mosque/runs", json={"runs": runs})

    # Plumbing

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if not self.token:
            raise MoscheeioAuthError("not paired")
        all_headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            **(headers or {}),
        }
        try:
            async with self._session.request(
                method,
                f"{self.base_url}{path}",
                json=json,
                headers=all_headers,
                timeout=REQUEST_TIMEOUT,
            ) as response:
                if response.status in (401, 404):
                    raise MoscheeioAuthError(f"HTTP {response.status}")
                if response.status == 409:
                    raise MoscheeioNotLinkedError("not linked to a mosque")
                if response.status >= 400:
                    raise MoscheeioConnectionError(f"HTTP {response.status}")
                data = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise MoscheeioConnectionError(str(err) or type(err).__name__) from err
        return data if isinstance(data, dict) else {}

    async def _post_json(
        self, path: str, body: dict[str, Any], *, accept_errors: bool = False
    ) -> dict[str, Any]:
        try:
            async with self._session.post(
                f"{self.base_url}{path}",
                json=body,
                headers={"Accept": "application/json"},
                timeout=REQUEST_TIMEOUT,
            ) as response:
                # Device-flow errors come back as 400 with a JSON body.
                if response.status >= 400 and not (
                    accept_errors and response.status < 500
                ):
                    raise MoscheeioConnectionError(f"HTTP {response.status}")
                data = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise MoscheeioConnectionError(str(err) or type(err).__name__) from err
        return data if isinstance(data, dict) else {}


def _int(value: Any, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default
