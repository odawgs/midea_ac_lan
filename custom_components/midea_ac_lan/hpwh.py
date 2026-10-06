"""Read-only support for Midea split heat pump water heaters reporting as C3.

The Midea MHW-V28WD2N7 split heat pump water heater (model ``171000AU``)
announces itself as device type 0xC3, but its frames do not follow the C3
air-to-water layout that ``midealan`` decodes. The generic C3 parser turns its
status into nonsense (a static 98 °C tank, error code 7, two heating zones).

This module replaces C3 message processing for those models with a decoder
mapped from captured frames. It is read-only: the C3 set messages use the
air-to-water layout, so writes are blocked rather than sent to the unit.

Frame offsets below count from the body-type byte (frame byte 10).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from midealan.devices.c3 import DeviceAttributes as C3Attributes

if TYPE_CHECKING:
    from midealan.device import MideaDevice

_LOGGER = logging.getLogger(__name__)

SPLIT_HPWH_MODELS = ["171000AU"]

HPWH_TANK_TEMP_1 = "hpwh_tank_temp_1"
HPWH_TANK_TEMP_2 = "hpwh_tank_temp_2"
HPWH_INPUT_POWER = "hpwh_input_power"
HPWH_ENERGY_COUNTER = "hpwh_energy_counter"
HPWH_EHEATER_ON_TEMP = "hpwh_eheater_on_temp"
HPWH_DISINFECT_HOUR = "hpwh_disinfect_hour"

HPWH_ATTRIBUTES = [
    HPWH_TANK_TEMP_1,
    HPWH_TANK_TEMP_2,
    HPWH_INPUT_POWER,
    HPWH_ENERGY_COUNTER,
    HPWH_EHEATER_ON_TEMP,
    HPWH_DISINFECT_HOUR,
]

_DEVICE_TYPE_C3 = 0xC3
_FRAME_START = 0xAA
_HEADER_LEN = 10
_MSG_TYPE_INDEX = 9
_MSG_QUERY = 0x03
_MSG_NOTIFY1 = 0x04
_MSG_NOTIFY2 = 0x05
_BODY_BASIC = 0x01
_BODY_SENSORS = 0x0D
_TEMP_OFFSET = 35
_BASIC_MIN_LEN = 46
_SENSORS_MIN_LEN = 21


def is_split_hpwh(device: MideaDevice) -> bool:
    """Return True for a C3 device that is really a split heat pump water heater.

    Returns
    -------
    True when the device type is C3 and the model is a known split HPWH.

    """
    is_c3 = device.device_type == _DEVICE_TYPE_C3
    return is_c3 and str(device.model) in SPLIT_HPWH_MODELS


def _u16(body: bytes, offset: int) -> int:
    return (body[offset] << 8) | body[offset + 1]


def decode_frame(msg: bytes) -> dict[str, Any]:
    """Decode one plaintext frame (starting 0xAA) into attribute values.

    Returns
    -------
    The attributes found in the frame, or an empty dict for frames this
    decoder does not understand.

    """
    if len(msg) <= _HEADER_LEN or msg[0] != _FRAME_START:
        return {}
    msg_type = msg[_MSG_TYPE_INDEX]
    body = msg[_HEADER_LEN:-1]  # drop the trailing checksum
    body_type = body[0]

    if (
        body_type == _BODY_BASIC
        and msg_type in {_MSG_QUERY, _MSG_NOTIFY1, _MSG_NOTIFY2}
        and len(body) >= _BASIC_MIN_LEN
    ):
        return {
            C3Attributes.dhw_power: bool(body[1] & 0x01),
            C3Attributes.dhw_target_temp: float(body[3] - _TEMP_OFFSET),
            C3Attributes.dhw_temp_max: float(body[4] - _TEMP_OFFSET),
            C3Attributes.dhw_temp_min: float(body[5] - _TEMP_OFFSET),
            HPWH_EHEATER_ON_TEMP: float(body[7] - _TEMP_OFFSET),
            HPWH_DISINFECT_HOUR: body[20],
            # Rises ~0.01 per 36 s at ~2.85 kW input, so 0.01 kWh per count.
            # 16-bit, so it wraps; total_increasing treats the wrap as a reset.
            HPWH_ENERGY_COUNTER: round(_u16(body, 44) / 100, 2),
            C3Attributes.error_code: None,
        }

    if (
        body_type == _BODY_SENSORS
        and msg_type == _MSG_NOTIFY1
        and len(body) >= _SENSORS_MIN_LEN
    ):
        # Two tank probes in 0.1 °C; which sits higher in the tank is unconfirmed.
        tank_1 = _u16(body, 7) / 10
        return {
            HPWH_TANK_TEMP_1: tank_1,
            HPWH_TANK_TEMP_2: _u16(body, 9) / 10,
            HPWH_INPUT_POWER: _u16(body, 19),
            C3Attributes.tank_actual_temperature: tank_1,
        }

    return {}


def install(device: MideaDevice) -> None:
    """Swap the device's C3 decoder for the split HPWH one and block writes."""
    attributes: dict[str, Any] = device._attributes  # ruff: ignore[private-member-access]  # pylint: disable=protected-access
    for attr in HPWH_ATTRIBUTES:
        attributes.setdefault(attr, None)
    attributes[C3Attributes.error_code] = None
    attributes[C3Attributes.tank_actual_temperature] = None

    def process_message(msg: bytes) -> dict[str, Any]:
        new_status = decode_frame(msg)
        attributes.update(new_status)
        return {str(attr): value for attr, value in new_status.items()}

    def set_attribute(attr: str, value: Any) -> None:  # ruff: ignore[any-type]
        _LOGGER.warning(
            "[%s] Split heat pump water heater support is read-only; "
            "ignoring set %s=%s",
            device.device_id,
            attr,
            value,
        )

    device.process_message = process_message  # type: ignore[method-assign]
    device.set_attribute = set_attribute  # type: ignore[method-assign]
