"""Midea split heat pump water heaters that report as device type C3.

The Midea MHW-V28WD2N7 split heat pump water heater (model ``171000AU``)
announces itself as device type 0xC3, but its frames follow Midea's
Australian hot water codec (``T_0000_C3_171000AU_2024010201.lua``), not the
C3 air-to-water layout that ``midealan`` decodes. The generic C3 parser turns
its status into nonsense (a static 98 °C tank, error code 7, two heating
zones).

This module replaces C3 query, decode and control for those models with the
hot water layout. Offsets below count from the body-type byte (frame byte 10).

Status body 0x01 (query reply, control echo and unsolicited report share it):
  [2] mode (0 off, 2 dhw)   [3] set point + 35
  [4..6] set point max/min/default + 35
  [7..9] e-heater ambient limit max/min/default + 35
  [10..12] restart offset max/min/default + 35
  [13] feature flags   [14] smart grid level   [15] error code
  [16] state: 0x01 disinfecting, 0x10 vacation, 0x20 e-heater running,
       0x80 compressor running
  [17] tank bottom temp + 35   [18] e-heater on ambient temp + 35
  [19] restart offset + 35
  [20] disinfect hour   [21] disinfect minute   [22] disinfect temp + 35
  [23] disinfect cycle (days)
  [24] switches: 0x10 auxiliary heater, 0x20 disinfect now, 0x40 vacation,
       0x80 auto disinfect
  [25] heat pump work temp limit + 35   [26..29] vacation dates
  [30] vacation mode
  [42] run mode (0 off, 1 run, 2 standby, 3 defrost, 4 antifreeze)
  [43] compressor Hz
  [44..45] energy counter, 0.01 kWh (16-bit, wraps)   [46..47] compressor hours

Control body 0x01 (message type 0x02, 51 bytes): the codec writes the FULL
settings block every time, so a command must echo the current values and
change only the requested one. Positions: [2] mode, [3] set point, [4] e-heater
on temp, [5] restart offset, [6..9] disinfect hour/minute/temp/cycle,
[10..13] vacation dates, [14] vacation mode, [15] mute level, [16] mute 0x01 |
force heat 0x02, [17] the switch byte (same bits as status [24]), [18] heat pump
work temp limit, [19..24] clock set (0 = leave alone), rest 0.

Report body 0x0D (unsolicited and queryable): [7..8] tank upper temp 0.1 °C,
[9..10] second tank probe 0.1 °C, [17..18] e-heater current 0.1 A,
[19..20] input power W, [21..24] e-heater energy 0.01 kWh,
[25..28] compressor energy 0.01 kWh.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from midealan.const import DeviceType
from midealan.devices.c3 import DeviceAttributes as C3Attributes
from midealan.message import ListTypes, MessageRequest, MessageType

if TYPE_CHECKING:
    from midealan.device import MideaDevice

_LOGGER = logging.getLogger(__name__)

SPLIT_HPWH_MODELS = ["171000AU"]

# Read-only sensors
HPWH_TANK_TEMP_1 = "hpwh_tank_temp_1"
HPWH_TANK_TEMP_2 = "hpwh_tank_temp_2"
HPWH_TANK_BOTTOM_TEMP = "hpwh_tank_bottom_temp"
HPWH_INPUT_POWER = "hpwh_input_power"
HPWH_ENERGY_COUNTER = "hpwh_energy_counter"
HPWH_EHEATER_CURRENT = "hpwh_eheater_current"
HPWH_EHEATER_ENERGY = "hpwh_eheater_energy"
HPWH_COMPRESSOR_ENERGY = "hpwh_compressor_energy"
HPWH_COMPRESSOR_FREQUENCY = "hpwh_compressor_frequency"
HPWH_COMPRESSOR_HOURS = "hpwh_compressor_hours"
HPWH_RUN_MODE = "hpwh_run_mode"
# Binary states
HPWH_EHEATER_RUNNING = "hpwh_eheater_running"
HPWH_COMPRESSOR_RUNNING = "hpwh_compressor_running"
HPWH_DISINFECT_RUNNING = "hpwh_disinfect_running"
# Writable settings (numbers)
HPWH_EHEATER_ON_TEMP = "hpwh_eheater_on_temp"
HPWH_RESTART_OFFSET = "hpwh_restart_offset"
HPWH_DISINFECT_HOUR = "hpwh_disinfect_hour"
HPWH_DISINFECT_TEMP = "hpwh_disinfect_temp"
HPWH_DISINFECT_CYCLE = "hpwh_disinfect_cycle"
# Writable switches
HPWH_AUX_HEATER = "hpwh_aux_heater"
HPWH_DISINFECT_NOW = "hpwh_disinfect_now"
HPWH_AUTO_DISINFECT = "hpwh_auto_disinfect"
# Bounds reported by the unit (used by the number entities)
HPWH_EHEATER_ON_TEMP_MIN = "hpwh_eheater_on_temp_min"
HPWH_EHEATER_ON_TEMP_MAX = "hpwh_eheater_on_temp_max"
HPWH_RESTART_OFFSET_MIN = "hpwh_restart_offset_min"
HPWH_RESTART_OFFSET_MAX = "hpwh_restart_offset_max"

HPWH_ATTRIBUTES = [
    HPWH_TANK_TEMP_1,
    HPWH_TANK_TEMP_2,
    HPWH_TANK_BOTTOM_TEMP,
    HPWH_INPUT_POWER,
    HPWH_ENERGY_COUNTER,
    HPWH_EHEATER_CURRENT,
    HPWH_EHEATER_ENERGY,
    HPWH_COMPRESSOR_ENERGY,
    HPWH_COMPRESSOR_FREQUENCY,
    HPWH_COMPRESSOR_HOURS,
    HPWH_RUN_MODE,
    HPWH_EHEATER_RUNNING,
    HPWH_COMPRESSOR_RUNNING,
    HPWH_DISINFECT_RUNNING,
    HPWH_EHEATER_ON_TEMP,
    HPWH_RESTART_OFFSET,
    HPWH_DISINFECT_HOUR,
    HPWH_DISINFECT_TEMP,
    HPWH_DISINFECT_CYCLE,
    HPWH_AUX_HEATER,
    HPWH_DISINFECT_NOW,
    HPWH_AUTO_DISINFECT,
    HPWH_EHEATER_ON_TEMP_MIN,
    HPWH_EHEATER_ON_TEMP_MAX,
    HPWH_RESTART_OFFSET_MIN,
    HPWH_RESTART_OFFSET_MAX,
]

HPWH_RUN_MODES = {0: "off", 1: "run", 2: "standby", 3: "defrost", 4: "antifreeze"}

_FRAME_START = 0xAA
_HEADER_LEN = 10
_MSG_TYPE_INDEX = 9
_BODY_BASIC = 0x01
_BODY_RUNPARA1 = 0x02
_BODY_SENSORS = 0x0D
_TEMP_OFFSET = 35
_MODE_OFF = 0x00
_MODE_DHW = 0x02
_BASIC_MIN_LEN = 48
_CONTROL_ECHO_MIN_LEN = 19
_RUNPARA1_MIN_LEN = 43
_SENSORS_MIN_LEN = 29
_CONTROL_BODY_LEN = 51
# Status byte [16]
_STA_DISINFECT = 0x01
_STA_EHEATER = 0x20
_STA_COMPRESSOR = 0x80
# Switch byte (status [24], control [17])
_SW_AUX_HEATER = 0x10
_SW_DISINFECT_NOW = 0x20
_SW_AUTO_DISINFECT = 0x80
_SWITCH_BITS = {
    HPWH_AUX_HEATER: _SW_AUX_HEATER,
    HPWH_DISINFECT_NOW: _SW_DISINFECT_NOW,
    HPWH_AUTO_DISINFECT: _SW_AUTO_DISINFECT,
}
_SETTABLE = {
    C3Attributes.dhw_power,
    C3Attributes.dhw_target_temp,
    HPWH_EHEATER_ON_TEMP,
    HPWH_RESTART_OFFSET,
    HPWH_DISINFECT_HOUR,
    HPWH_DISINFECT_TEMP,
    HPWH_DISINFECT_CYCLE,
    *_SWITCH_BITS,
}
_HOURS_MAX = 23
_CYCLE_MIN = 1
_CYCLE_MAX = 30


def is_split_hpwh(device: MideaDevice) -> bool:
    """Return True for a C3 device that is really a split heat pump water heater.

    Returns
    -------
    True when the device type is C3 and the model is a known split HPWH.

    """
    is_c3 = device.device_type == DeviceType.C3
    return is_c3 and str(device.model) in SPLIT_HPWH_MODELS


def _u16(body: bytes, offset: int) -> int:
    return (body[offset] << 8) | body[offset + 1]


def _u32(body: bytes, offset: int) -> int:
    return int.from_bytes(body[offset : offset + 4], "big")


def _temp(raw: int) -> float:
    return float(raw - _TEMP_OFFSET)


class MessageHPWHQuery(MessageRequest):
    """Query in the hot water codec's form: body type followed by 0x01."""

    def __init__(self, protocol_version: int, body_type: ListTypes) -> None:
        """Initialize a hot water query."""
        super().__init__(
            device_type=DeviceType.C3,
            protocol_version=protocol_version,
            message_type=MessageType.query,
            body_type=body_type,
        )

    @property
    def _body(self) -> bytearray:
        return bytearray([0x01])


class MessageHPWHQueryBasic(MessageHPWHQuery):
    """Query 0x01: settings and state."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize the basic query."""
        super().__init__(protocol_version, ListTypes.X01)


class MessageHPWHQueryRunPara1(MessageHPWHQuery):
    """Query 0x02: run parameters (carries mute level and force heat)."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize the run parameter query."""
        super().__init__(protocol_version, ListTypes.X02)


class MessageHPWHQuerySensors(MessageHPWHQuery):
    """Query 0x0D: tank temperatures, power and energy."""

    def __init__(self, protocol_version: int) -> None:
        """Initialize the sensor query."""
        super().__init__(protocol_version, ListTypes.X0D)


class MessageHPWHSet(MessageRequest):
    """Control 0x01: the full settings block, echoed from the last status."""

    def __init__(self, protocol_version: int, body: bytearray) -> None:
        """Initialize a control message from a prepared 51-byte body."""
        super().__init__(
            device_type=DeviceType.C3,
            protocol_version=protocol_version,
            message_type=MessageType.set,
            body_type=ListTypes.X01,
        )
        # body[0] is the body type, which MessageRequest adds itself.
        self._payload = body[1:]

    @property
    def _body(self) -> bytearray:
        return self._payload


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

    if body_type == _BODY_BASIC and msg_type == MessageType.set:
        return _decode_control_echo(body)
    if body_type == _BODY_BASIC and msg_type in {
        MessageType.query,
        MessageType.notify1,
        MessageType.notify2,
    }:
        return _decode_basic(body)
    if body_type == _BODY_SENSORS and len(body) >= _SENSORS_MIN_LEN:
        return _decode_sensors(body)
    return {}


def _decode_basic(body: bytes) -> dict[str, Any]:
    if len(body) < _BASIC_MIN_LEN:
        return {}
    state = body[16]
    switches = body[24]
    return {
        C3Attributes.dhw_power: body[2] != _MODE_OFF,
        C3Attributes.dhw_target_temp: _temp(body[3]),
        C3Attributes.dhw_temp_max: _temp(body[4]),
        C3Attributes.dhw_temp_min: _temp(body[5]),
        HPWH_EHEATER_ON_TEMP_MAX: _temp(body[7]),
        HPWH_EHEATER_ON_TEMP_MIN: _temp(body[8]),
        HPWH_RESTART_OFFSET_MAX: _temp(body[10]),
        HPWH_RESTART_OFFSET_MIN: _temp(body[11]),
        C3Attributes.error_code: body[15],
        HPWH_DISINFECT_RUNNING: bool(state & _STA_DISINFECT),
        HPWH_EHEATER_RUNNING: bool(state & _STA_EHEATER),
        HPWH_COMPRESSOR_RUNNING: bool(state & _STA_COMPRESSOR),
        HPWH_TANK_BOTTOM_TEMP: _temp(body[17]),
        HPWH_EHEATER_ON_TEMP: _temp(body[18]),
        HPWH_RESTART_OFFSET: _temp(body[19]),
        HPWH_DISINFECT_HOUR: body[20],
        HPWH_DISINFECT_TEMP: _temp(body[22]),
        HPWH_DISINFECT_CYCLE: body[23],
        HPWH_AUX_HEATER: bool(switches & _SW_AUX_HEATER),
        HPWH_DISINFECT_NOW: bool(switches & _SW_DISINFECT_NOW),
        HPWH_AUTO_DISINFECT: bool(switches & _SW_AUTO_DISINFECT),
        HPWH_RUN_MODE: body[42],
        HPWH_COMPRESSOR_FREQUENCY: body[43],
        # 16-bit, so it wraps; total_increasing treats the wrap as a reset.
        HPWH_ENERGY_COUNTER: round(_u16(body, 44) / 100, 2),
        HPWH_COMPRESSOR_HOURS: _u16(body, 46),
    }


def _decode_control_echo(body: bytes) -> dict[str, Any]:
    """Decode the unit's reply to a control message (control layout).

    Returns
    -------
    The settings echoed by the unit, or an empty dict for a short body.

    """
    if len(body) < _CONTROL_ECHO_MIN_LEN:
        return {}
    switches = body[17]
    return {
        C3Attributes.dhw_power: body[2] != _MODE_OFF,
        C3Attributes.dhw_target_temp: _temp(body[3]),
        HPWH_EHEATER_ON_TEMP: _temp(body[4]),
        HPWH_RESTART_OFFSET: _temp(body[5]),
        HPWH_DISINFECT_HOUR: body[6],
        HPWH_DISINFECT_TEMP: _temp(body[8]),
        HPWH_DISINFECT_CYCLE: body[9],
        HPWH_AUX_HEATER: bool(switches & _SW_AUX_HEATER),
        HPWH_DISINFECT_NOW: bool(switches & _SW_DISINFECT_NOW),
        HPWH_AUTO_DISINFECT: bool(switches & _SW_AUTO_DISINFECT),
    }


def _decode_sensors(body: bytes) -> dict[str, Any]:
    tank_upper = _u16(body, 7) / 10
    return {
        HPWH_TANK_TEMP_1: tank_upper,
        HPWH_TANK_TEMP_2: _u16(body, 9) / 10,
        HPWH_EHEATER_CURRENT: _u16(body, 17) / 10,
        HPWH_INPUT_POWER: _u16(body, 19),
        HPWH_EHEATER_ENERGY: round(_u32(body, 21) / 100, 2),
        HPWH_COMPRESSOR_ENERGY: round(_u32(body, 25) / 100, 2),
        C3Attributes.tank_actual_temperature: tank_upper,
    }


class SplitHPWHController:
    """Decode state and build control messages for one split HPWH device."""

    def __init__(self, device: MideaDevice) -> None:
        """Attach to a midealan C3 device."""
        self._device = device
        self._attributes: dict[str, Any] = device._attributes  # ruff: ignore[private-member-access]
        self._last_basic: bytes | None = None
        self._mute_level = 0
        self._mute_force_heat = 0

    def build_query(self) -> list[MessageRequest]:
        """Query settings, run parameters and sensors each refresh.

        Returns
        -------
        The three hot water queries.

        """
        version = self._device._message_protocol_version  # ruff: ignore[private-member-access]
        return [
            MessageHPWHQueryBasic(version),
            MessageHPWHQueryRunPara1(version),
            MessageHPWHQuerySensors(version),
        ]

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Decode a frame, remember the raw settings and update attributes.

        Returns
        -------
        The attributes changed by this frame, keyed by name.

        """
        if len(msg) > _HEADER_LEN and msg[0] == _FRAME_START:
            body = msg[_HEADER_LEN:-1]
            msg_type = msg[_MSG_TYPE_INDEX]
            if (
                body[0] == _BODY_BASIC
                and msg_type != MessageType.set
                and len(body) >= _BASIC_MIN_LEN
            ):
                self._last_basic = bytes(body)
            elif body[0] == _BODY_RUNPARA1 and len(body) >= _RUNPARA1_MIN_LEN:
                self._mute_level = body[41]
                self._mute_force_heat = body[42] & 0x03
        new_status = decode_frame(msg)
        self._attributes.update(new_status)
        return {str(attr): value for attr, value in new_status.items()}

    def build_control_body(self, attr: str, value: Any) -> bytearray:  # ruff: ignore[any-type]
        """Build the 51-byte control body for one changed setting.

        Returns
        -------
        The body, echoing every current setting except ``attr``.

        Raises
        ------
        ValueError
            If no status frame has been received yet.

        """
        status = self._last_basic
        if status is None:
            msg = "no status received from the water heater yet"
            raise ValueError(msg)
        body = bytearray(_CONTROL_BODY_LEN)
        body[0] = _BODY_BASIC
        body[1] = 0x01
        body[2] = status[2]
        body[3] = status[3]
        body[4] = status[18]
        body[5] = status[19]
        body[6:10] = status[20:24]
        body[10:14] = status[26:30]
        body[14] = status[30]
        body[15] = self._mute_level
        body[16] = self._mute_force_heat
        body[17] = status[24]
        body[18] = status[25]

        if attr == C3Attributes.dhw_power:
            body[2] = _MODE_DHW if value else _MODE_OFF
            if not value:
                # The app clears both momentary buttons when switching off.
                body[17] &= ~(_SW_AUX_HEATER | _SW_DISINFECT_NOW) & 0xFF
        elif attr == C3Attributes.dhw_target_temp:
            body[3] = self._encode_temp(value, status[5], status[4])
        elif attr == HPWH_EHEATER_ON_TEMP:
            body[4] = self._encode_temp(value, status[8], status[7])
        elif attr == HPWH_RESTART_OFFSET:
            body[5] = self._encode_temp(value, status[11], status[10])
        elif attr == HPWH_DISINFECT_HOUR:
            body[6] = min(max(int(value), 0), _HOURS_MAX)
        elif attr == HPWH_DISINFECT_TEMP:
            body[8] = self._encode_temp(value, status[3], status[4])
        elif attr == HPWH_DISINFECT_CYCLE:
            body[9] = min(max(int(value), _CYCLE_MIN), _CYCLE_MAX)
        elif attr in _SWITCH_BITS:
            bit = _SWITCH_BITS[attr]
            body[17] = (body[17] | bit) if value else (body[17] & ~bit & 0xFF)
        return body

    @staticmethod
    def _encode_temp(value: Any, raw_min: int, raw_max: int) -> int:  # ruff: ignore[any-type]
        raw = round(float(value)) + _TEMP_OFFSET
        return min(max(raw, raw_min), raw_max)

    def set_attribute(self, attr: str, value: Any) -> None:  # ruff: ignore[any-type]
        """Send one changed setting to the unit."""
        if attr not in _SETTABLE:
            _LOGGER.warning(
                "[%s] Split heat pump water heater: %s is not writable",
                self._device.device_id,
                attr,
            )
            return
        try:
            body = self.build_control_body(attr, value)
        except ValueError as err:
            _LOGGER.warning(
                "[%s] Cannot set %s=%s: %s",
                self._device.device_id,
                attr,
                value,
                err,
            )
            return
        version = self._device._message_protocol_version  # ruff: ignore[private-member-access]
        message = MessageHPWHSet(version, body)
        _LOGGER.info(
            "[%s] Split heat pump water heater set %s=%s, body %s",
            self._device.device_id,
            attr,
            value,
            body.hex(),
        )
        self._device.build_send(message)


def install(device: MideaDevice) -> SplitHPWHController:
    """Swap the device's C3 query, decoder and control for the split HPWH ones.

    Returns
    -------
    The controller now driving the device.

    """
    controller = SplitHPWHController(device)
    attributes: dict[str, Any] = device._attributes  # ruff: ignore[private-member-access]
    for attr in HPWH_ATTRIBUTES:
        attributes.setdefault(attr, None)
    attributes[C3Attributes.error_code] = None
    attributes[C3Attributes.tank_actual_temperature] = None
    device.build_query = controller.build_query  # type: ignore[method-assign]
    device.process_message = controller.process_message  # type: ignore[method-assign]
    device.set_attribute = controller.set_attribute  # type: ignore[method-assign]
    return controller
