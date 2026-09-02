"""Actual refrigerator temperature sensors from event-class SmartHQ ERDs."""

from __future__ import annotations

from propcache.api import cached_property

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfTemperature

from ...const import DOMAIN
from ...devices import ApplianceApi
from ..common.ge_erd_sensor import GeErdSensor


class GeActualTemperatureSensor(GeErdSensor):
    """Decode a signed Fahrenheit x100 value from an actual-temperature ERD."""

    register_without_erd = True

    def __init__(
        self, api: ApplianceApi, erd_code: str, compartment: str
    ) -> None:
        super().__init__(
            api,
            erd_code,
            erd_override=f"actual_temperature_{compartment}",
            device_class_override=SensorDeviceClass.TEMPERATURE,
            state_class_override=SensorStateClass.MEASUREMENT,
            uom_override=UnitOfTemperature.FAHRENHEIT,
            entity_category=EntityCategory.DIAGNOSTIC,
        )
        self._compartment = compartment

    @cached_property
    def name(self) -> str:
        return f"{self.entity_identifier} Actual Temperature {self._compartment.title()}"

    @cached_property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self.entity_identifier}_actual_temperature_{self._compartment}"

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None

    @property
    def native_value(self) -> float | None:
        raw_value = self.appliance.get_raw_erd_value(self.erd_code)
        return self.decode_temperature(raw_value)

    @staticmethod
    def decode_temperature(raw_value: str | None) -> float | None:
        """Decode a two-byte, signed, big-endian Fahrenheit x100 value."""
        if raw_value is None:
            return None

        try:
            raw_bytes = bytes.fromhex(raw_value)
        except ValueError:
            return None

        if len(raw_bytes) != 2:
            return None

        temperature = int.from_bytes(raw_bytes, byteorder="big", signed=True) / 100
        if not -100 <= temperature <= 200:
            return None
        return temperature
