"""AK G2 telemetry report, corroborated by Nortank12's LQ protocol mapping.

Reference revision: 8ab8338460b0d4c3d77723feae95f66e4251f61c.
G2 controls recovered from the manufacturer's 1.2.14 V8 bytecode.
SPDX-License-Identifier: GPL-3.0-or-later
"""

import math
import struct

VID = 0x3633
PID = 0x0029
HEADER = bytes.fromhex("10 68 01 08 0c 01 02")


def bounded(value: float, limit: int) -> int:
    if not math.isfinite(value):
        raise ValueError("Telemetry must be finite")
    return max(0, min(limit, math.floor(value + 0.5)))


def telemetry_report(temperature_c: float, usage: float, power_w: float,
                     frequency_mhz: float, unit: str = "C") -> bytes:
    if unit not in ("C", "F"):
        raise ValueError("Temperature unit must be C or F")
    if not math.isfinite(temperature_c) or not -40 <= temperature_c <= 150:
        raise ValueError("CPU temperature is missing or out of range")
    temperature = temperature_c if unit == "C" else temperature_c * 1.8 + 32
    report = bytearray(64)
    report[:7] = HEADER
    struct.pack_into(">H", report, 7, bounded(power_w, 65535))
    report[9] = int(unit == "F")
    struct.pack_into(">f", report, 10, temperature)
    report[14] = bounded(usage, 100)
    struct.pack_into(">H", report, 15, bounded(frequency_mhz, 65535))
    report[17] = sum(report[1:17]) & 0xff
    report[18] = 0x16
    return bytes(report)


def command_report(command: int, value: int | None = None) -> bytes:
    """G2 write reports recovered from original V8 bytecode (version 1.2.14)."""
    if type(command) is not int or command not in (2, 3, 4, 5, 6, 8):
        raise ValueError("Unsupported G2 command")
    if command == 8:
        if value is not None:
            raise ValueError("RPM query has no argument")
        payload = bytes.fromhex("68 01 11 01 08")
    else:
        if type(value) is not int:
            raise ValueError("Command argument must be an integer")
        limits = {2: 1, 3: 100, 4: 40, 5: 40, 6: 1}
        if not 0 <= value <= limits[command]:
            raise ValueError("Command argument outside supported range")
        payload = bytes((0x68, 1, 0x11, 2, command, value))
    frame = bytes((0x10,)) + payload + bytes((sum(payload) & 255, 0x16))
    return frame + bytes(64 - len(frame))


def display_report(enabled: bool, temperature_c: float, usage: float,
                   power_w: float, frequency_mhz: float, unit="C") -> bytes:
    if type(enabled) is not bool:
        raise ValueError("Display state must be boolean")
    report = bytearray(telemetry_report(temperature_c, usage, power_w, frequency_mhz, unit))
    report[3] = 0x11
    report[6] = int(enabled)
    report[17] = sum(report[1:17]) & 255
    return bytes(report)


def decode_rpm(report: bytes) -> int | None:
    # The original app checks selector[5] == 7 and reads [6:10] big-endian.
    # Header/checksum of input responses have not been observed on Linux yet.
    if len(report) != 64 or report[0] != 0x10 or report[5] != 7:
        return None
    rpm = int.from_bytes(report[6:10], "big")
    return rpm if 0 <= rpm <= 10000 else None
