"""AK G2 telemetry report, corroborated by Nortank12's LQ protocol mapping.

Reference revision: 8ab8338460b0d4c3d77723feae95f66e4251f61c.
Only the telemetry report is implemented; no fan/firmware commands are sent.
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
