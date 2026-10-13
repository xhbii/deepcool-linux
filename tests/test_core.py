import json
import math
import os
from pathlib import Path
import socket
import struct
import tempfile
import threading
import time
import unittest

from deepcool_linux import config
from deepcool_linux.daemon import dispatch, handle_client
from deepcool_linux.hardware import devices
from deepcool_linux.protocol import telemetry_report
from deepcool_linux.sensors import (cpu_times, utilization, power_delta,
                                   discover_energy, discover_temperature)


class ProtocolTests(unittest.TestCase):
    def test_independent_known_report(self):
        # Upstream table: 125W, 62.5C, 45%, 5000MHz; checksum 641 mod 256 = 129.
        expected = bytes.fromhex("10 68 01 08 0c 01 02 00 7d 00 42 7a 00 00 2d 13 88 81 16") + bytes(45)
        self.assertEqual(telemetry_report(62.5, 45, 125, 5000), expected)

    def test_fahrenheit(self):
        report = telemetry_report(62.5, 45, 125, 5000, "F")
        self.assertEqual(report[9:14], bytes.fromhex("01 43 10 80 00"))  # 144.5F

    def test_missing_or_nonfinite_temperature_rejected(self):
        for t in (math.nan, math.inf, -41, 151):
            with self.subTest(t=t), self.assertRaises(ValueError):
                telemetry_report(t, 45, 125, 5000)

    def test_range_clamping_and_bad_units(self):
        report = telemetry_report(62.5, 200, -1, 1e6)
        self.assertEqual(report[7:9], b"\0\0")
        self.assertEqual(report[14:17], bytes.fromhex("64 ff ff"))
        with self.assertRaises(ValueError):
            telemetry_report(62.5, 45, 125, 5000, "K")


class SensorTests(unittest.TestCase):
    def test_guest_does_not_double_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = Path(tmp)
            (proc / "stat").write_text("cpu 100 20 30 200 10 5 5 0 40 10\n")
            self.assertEqual(cpu_times(proc), (370, 210))
            self.assertAlmostEqual(utilization((270, 160), cpu_times(proc)), 50)

    def test_power_zero_and_rollover(self):
        self.assertEqual(power_delta(1e6, 3e6, 2, None), 1)
        self.assertEqual(power_delta(1e6, 1e6, 1, 1e9), 0)
        self.assertEqual(power_delta(99e6, 1e6, 1, 100e6), 2)
        self.assertIsNone(power_delta(50e6, 1e6, 1, 100e6))
        self.assertIsNone(power_delta(50, 1, 1, None))

    def test_no_package_core_double_counting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, label in (("intel-rapl:0", "package-0"), ("intel-rapl:0:0", "core")):
                zone = root / name
                zone.mkdir()
                (zone / "name").write_text(label)
                (zone / "energy_uj").write_text("123")
                (zone / "max_energy_range_uj").write_text("9999")
            self.assertEqual(discover_energy(root, root), [(root / "intel-rapl:0/energy_uj", 9999)])

    def test_cpu_temperature_not_gpu_or_board(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i, driver, label in ((0, "amdgpu", "edge"), (1, "gigabyte_wmi", ""),
                                     (2, "k10temp", "Tctl")):
                node = root / f"hwmon{i}"
                node.mkdir()
                (node / "name").write_text(driver)
                (node / "temp1_input").write_text("50000")
                (node / "temp1_label").write_text(label)
            self.assertEqual(discover_temperature(root), root / "hwmon2/temp1_input")


class DeviceTests(unittest.TestCase):
    def test_only_current_generation_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i, pid in ((0, "00000002"), (1, "00000029")):
                node = root / f"hidraw{i}/device"
                node.mkdir(parents=True)
                (node / "uevent").write_text(
                    f"HID_ID=0003:00003633:{pid}\nHID_NAME=DC\nHID_UNIQ=test\n")
            found = devices(root, root)
            self.assertEqual([d["path"] for d in found], [str(root / "hidraw1")])


class SettingsTests(unittest.TestCase):
    def test_reject_bad_types_ranges_and_overflow(self):
        for values in ({"interval": 10**400}, {"interval": True}, {"interval": math.nan},
                       {"interval": .01}, {"enabled": "yes"}, {"device": "/dev/hidraw0"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                config.validate(values)

    def test_peer_uid_and_restricted_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            settings = config.validate({"controller_uid": 1000})
            with self.assertRaises(PermissionError):
                dispatch({"command": "settings", "values": {"unit": "F"}}, 1001, settings, {}, path)
            with self.assertRaises(ValueError):
                dispatch({"command": "settings", "values": {"controller_uid": 1001}}, 1000, settings, {}, path)
            dispatch({"command": "settings", "values": {"unit": "F"}}, 1000, settings, {}, path)
            self.assertEqual(config.load(path)["unit"], "F")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertTrue(dispatch({"command": "status"}, 1001, settings, {}, path)["ok"])

    def test_slow_client_has_absolute_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.sock"
            server = socket.socket(socket.AF_UNIX)
            server.bind(str(path))
            server.listen()
            client = socket.socket(socket.AF_UNIX)
            client.connect(str(path))
            def trickle():
                try:
                    for _ in range(8):
                        client.sendall(b" ")
                        time.sleep(.03)
                except OSError:
                    pass
            thread = threading.Thread(target=trickle)
            thread.start()
            start = time.monotonic()
            handle_client(server, config.DEFAULTS.copy(), {}, Path(tmp) / "config.json")
            elapsed = time.monotonic() - start
            client.close()
            server.close()
            thread.join()
            self.assertLess(elapsed, .2)


if __name__ == "__main__":
    unittest.main()
