# AK620 G2 telemetry protocol

Scope: DeepCool AK620 G2 DIGITAL NYX, USB VID `0x3633`, PID `0x0029`
(decimal PID 41), product name `AK620-GEN2`.

The numeric display has been tested on a connected device. The implementation
uses the existing Linux `hidraw` interface and checks the opened descriptor's
bus/VID/PID before sending. Device paths are discovered again after disconnects.

## Output report

64 bytes, including report ID. All unused bytes are zero.

| Offset | Encoding | Value / purpose |
|---|---|---|
| 0 | u8 | Report ID `0x10` |
| 1–6 | bytes | Fixed header `68 01 08 0c 01 02` |
| 7–8 | big-endian u16 | CPU package power in watts |
| 9 | u8 | Temperature unit: 0 Celsius, 1 Fahrenheit |
| 10–13 | big-endian IEEE-754 float32 | Temperature in the selected unit |
| 14 | u8 | CPU utilization, 0–100 percent |
| 15–16 | big-endian u16 | CPU frequency in MHz |
| 17 | u8 | Sum of bytes 1–16 modulo 256 |
| 18 | u8 | Terminator `0x16` |
| 19–63 | bytes | Zero padding |

Test vector: 125 W, 62.5°C, 45%, 5000 MHz yields:

```text
10 68 01 08 0c 01 02 00 7d 00 42 7a 00 00 2d 13 88 81 16
```

Append 45 zero bytes. The checksum is `0x81`.

## Evidence and attribution

The field layout follows Nortank12/deepcool-digital-linux, revision
`8ab8338460b0d4c3d77723feae95f66e4251f61c`:

- [Device mapping](https://github.com/Nortank12/deepcool-digital-linux/blob/8ab8338460b0d4c3d77723feae95f66e4251f61c/device-list/README.md)
- [LQ / AK G2 field table](https://github.com/Nortank12/deepcool-digital-linux/blob/8ab8338460b0d4c3d77723feae95f66e4251f61c/device-list/tables/lq-series.md)
- [Reference implementation](https://github.com/Nortank12/deepcool-digital-linux/blob/8ab8338460b0d4c3d77723feae95f66e4251f61c/src/devices/lq_series.rs)
- [Linux hidraw API](https://docs.kernel.org/hid/hidraw.html)

This implementation preserves fractional Celsius values before encoding them;
the reference implementation rounds the reading first. The field format is the
same. No fixed temperature offset is added. On Ryzen systems the default is a
CPU `Tdie`, package or `Tctl` sensor rather than a GPU/mainboard/CCD temperature.

Fan, RPM, screen power and alert controls use additional reports; their values
must not be inferred from telemetry fields. See [fan-control.md](fan-control.md).
