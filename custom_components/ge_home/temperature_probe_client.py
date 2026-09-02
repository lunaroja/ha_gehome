"""SmartHQ client extension for probing event-class refrigerator temperatures."""

from __future__ import annotations

import json
import logging
from typing import Any

from gehomesdk import GeAppliance, GeWebsocketClient
from gehomesdk.clients.websocket_client import API_HOST

_LOGGER = logging.getLogger(__name__)

ACTUAL_TEMPERATURE_ERDS = ("0x105c", "0x105d")
_PROBE_MESSAGE_PREFIX = "actualTemperatureProbe"


class GeTemperatureProbeClient(GeWebsocketClient):
    """Request actual-temperature ERDs omitted from the normal ERD snapshot."""

    async def async_request_actual_temperatures(
        self, appliance: GeAppliance
    ) -> None:
        """Request the event-class fresh-food and freezer temperature ERDs."""
        for erd_code in ACTUAL_TEMPERATURE_ERDS:
            message = {
                "kind": "websocket#api",
                "action": "api",
                "host": API_HOST,
                "method": "GET",
                "path": f"/v1/appliance/{appliance.mac_addr}/erd/{erd_code}",
                "id": self._probe_message_id(appliance.mac_addr, erd_code),
            }
            await self._send_dict(message)

    async def _process_message(self, message: str) -> None:
        """Handle targeted ERD responses before delegating other SDK traffic."""
        message_dict = json.loads(message)
        message_id = message_dict.get("id", "")

        if not self._is_probe_message(message_dict, message_id):
            await super()._process_message(message)
            return

        mac_addr, requested_erd = self._parse_probe_message_id(message_id)
        code = message_dict.get("code", 200)
        success = message_dict.get("success", True)

        if not success or code != 200:
            _LOGGER.warning(
                "SmartHQ did not expose refrigerator temperature ERD %s for %s "
                "(HTTP %s: %s)",
                requested_erd,
                mac_addr,
                code,
                message_dict.get("reason", "request rejected"),
            )
            return

        erd_code, raw_value = self._extract_erd_value(
            message_dict.get("body"), requested_erd
        )
        if raw_value is None:
            _LOGGER.warning(
                "SmartHQ returned no value for refrigerator temperature ERD %s "
                "for %s",
                requested_erd,
                mac_addr,
            )
            return

        _LOGGER.info(
            "SmartHQ exposed refrigerator temperature ERD %s for %s",
            erd_code,
            mac_addr,
        )
        await self._update_appliance_state(mac_addr, {erd_code: raw_value})

    @staticmethod
    def _probe_message_id(mac_addr: str, erd_code: str) -> str:
        return f"{_PROBE_MESSAGE_PREFIX}:{mac_addr}:{erd_code.lower()}"

    @staticmethod
    def _is_probe_message(message: dict[str, Any], message_id: str) -> bool:
        return (
            message.get("kind", "").lower() == "websocket#api"
            and message_id.startswith(f"{_PROBE_MESSAGE_PREFIX}:")
        )

    @staticmethod
    def _parse_probe_message_id(message_id: str) -> tuple[str, str]:
        _, mac_addr, erd_code = message_id.split(":", 2)
        return mac_addr.upper(), erd_code.lower()

    @classmethod
    def _extract_erd_value(
        cls, body: Any, requested_erd: str
    ) -> tuple[str, str | None]:
        """Accept both single-entry and list-shaped SmartHQ responses."""
        if not isinstance(body, dict):
            return requested_erd, None

        candidates: list[Any] = []
        if isinstance(body.get("items"), list):
            candidates.extend(body["items"])
        if isinstance(body.get("item"), dict):
            candidates.append(body["item"])
        candidates.append(body)

        requested_erd = requested_erd.lower()
        fallback: tuple[str, str] | None = None
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            raw_value = candidate.get("value")
            if not isinstance(raw_value, str):
                continue
            erd_code = str(candidate.get("erd", requested_erd)).lower()
            if erd_code == requested_erd:
                return erd_code, raw_value
            if fallback is None:
                fallback = (erd_code, raw_value)

        return fallback or (requested_erd, None)
