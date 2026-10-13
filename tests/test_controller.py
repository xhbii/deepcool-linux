import math
import unittest

from deepcool_linux import config
from deepcool_linux.controller import Controller
from deepcool_linux.protocol import command_report, decode_rpm, display_report


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Writer:
    def __init__(self, clock):
        self.fd = None
        self.clock = clock
        self.frames, self.inputs, self.times = [], [], []
        self.fail_command = None

    def write(self, frame):
        if frame[4] == 2 and frame[5] == self.fail_command:
            self.fd = None
            raise OSError("disconnected")
        self.fd = 1
        self.frames.append(frame)
        self.times.append(self.clock())

    def read_inputs(self):
        frames, self.inputs = self.inputs, []
        return frames

    def commands(self):
        return [(f[5], f[6]) for f in self.frames if f[4] == 2]


SAMPLE = {"temperature_c": 50, "usage_percent": 30, "power_w": 100, "frequency_mhz": 5000}


class PacketTests(unittest.TestCase):
    def test_independent_vendor_vectors(self):
        for command, value, hex_data in (
                (2, 0, "10 68 01 11 02 02 00 7e 16"),
                (2, 1, "10 68 01 11 02 02 01 7f 16"),
                (3, 100, "10 68 01 11 02 03 64 e3 16"),
                (4, 0, "10 68 01 11 02 04 00 80 16"),
                (5, 20, "10 68 01 11 02 05 14 95 16"),
                (6, 1, "10 68 01 11 02 06 01 83 16"),
                (8, None, "10 68 01 11 01 08 83 16")):
            with self.subTest(command=command):
                vector = bytes.fromhex(hex_data)
                self.assertEqual(command_report(command, value), vector + bytes(64 - len(vector)))
        vector = bytes.fromhex("10 68 01 11 0c 01 00 00 7d 00 42 7a 00 00 2d 13 88 88 16")
        self.assertEqual(display_report(False, 62.5, 45, 125, 5000), vector + bytes(45))

    def test_rpm_bounds_and_report_identity(self):
        response = bytes.fromhex("10 68 01 11 05 07 00 00 06 40") + bytes(54)
        self.assertEqual(decode_rpm(response), 1600)
        for invalid in (response[:10], bytes([5]) + response[1:],
                        response[:5] + b"\x08" + response[6:],
                        response[:6] + b"\xff\xff\xff\xff" + response[10:]):
            self.assertIsNone(decode_rpm(invalid))

    def test_invalid_arguments(self):
        for command, value in ((True, 1), (3, -1), (3, 101), (2, 2), (4, 41), (8, 0), (3, True)):
            with self.subTest(command=command, value=value), self.assertRaises(ValueError):
                command_report(command, value)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.writer = Writer(self.clock)
        self.controller = Controller(self.writer, clock=self.clock, sleep=self.clock.sleep)
        self.settings = config.validate({})

    def tick(self, **settings):
        self.settings.update(settings)
        return self.controller.tick(self.settings, SAMPLE)

    def test_default_leaves_pwm_and_sync_unchanged(self):
        self.tick()
        self.assertEqual(self.writer.commands(), [])
        self.assertEqual(self.writer.frames[-1], command_report(8))

    def test_manual_sets_nonzero_duty_before_taking_control(self):
        fan, _, _ = self.tick(fan_mode="manual", fan_pwm=45)
        commands = self.writer.commands()
        self.assertLess(commands.index((3, 45)), commands.index((2, 0)))
        self.assertEqual(fan["application"], "written_without_ack")
        self.assertIsNone(fan["rpm"])
        self.assertTrue(all(b - a >= .099 for a, b in zip(self.writer.times, self.writer.times[1:])))
        self.writer.frames.clear()
        self.tick()
        self.assertEqual(self.writer.commands(), [])  # successful settings are cached

    def test_sensor_failure_requests_full_speed_without_telemetry(self):
        self.settings.update(fan_mode="manual", fan_pwm=20)
        for temperature in (None, math.nan, 151):
            with self.subTest(temperature=temperature):
                fan, _, sent = self.controller.tick(self.settings, {**SAMPLE, "temperature_c": temperature})
                self.assertEqual(fan["target_pwm"], 100)
                self.assertEqual(fan["reason"], "sensor_fail_safe")
                self.assertFalse(sent)
        self.assertIn((3, 100), self.writer.commands())

    def test_failed_duty_write_never_takes_control_and_is_retried(self):
        self.writer.fail_command = 3
        with self.assertRaises(OSError):
            self.tick(fan_mode="manual")
        self.assertNotIn((2, 0), self.writer.commands())
        self.assertNotIn("pwm", self.controller.applied)
        self.writer.fail_command = None
        self.tick()
        self.assertIn((3, 60), self.writer.commands())
        self.assertIn((2, 0), self.writer.commands())

    def test_normal_exit_and_leaving_software_restore_motherboard(self):
        self.tick(fan_mode="manual")
        self.controller.release()
        self.assertEqual(self.writer.commands()[-1], (2, 1))
        self.tick(fan_mode="manual")
        self.tick(fan_mode="unchanged")
        self.assertEqual(self.writer.commands()[-1], (2, 1))

    def test_disconnect_does_not_forget_owned_fans(self):
        self.tick(fan_mode="manual")
        self.writer.fd = None
        self.tick(fan_mode="unchanged")
        self.assertEqual(self.writer.commands()[-1], (2, 1))

    def test_screen_off_suppresses_telemetry_but_not_fan_control(self):
        _, frame, sent = self.tick(screen_enabled=False, fan_mode="manual")
        self.assertEqual(frame[6], 0)
        self.assertFalse(sent)
        self.writer.frames.clear()
        self.tick()
        self.assertEqual(self.writer.frames, [command_report(8)])
        _, frame, sent = self.tick(screen_enabled=True, enabled=False)
        self.assertEqual(frame[6], 1)
        self.assertFalse(sent)

    def test_rpm_expires_without_fresh_feedback(self):
        self.writer.inputs = [bytes.fromhex("10 68 01 11 05 07 00 00 06 40") + bytes(54)]
        fan, _, _ = self.tick()
        self.assertEqual(fan["rpm"], 1600)
        self.clock.now += 6
        fan, _, _ = self.tick()
        self.assertIsNone(fan["rpm"])

    def test_cooling_runs_when_display_not_due_or_paused(self):
        self.settings.update(fan_mode="manual", enabled=False)
        fan, _, sent = self.controller.tick(self.settings, {**SAMPLE, "temperature_c": 85}, False)
        self.assertEqual(fan["target_pwm"], 100)
        self.assertFalse(sent)

    def test_dry_run_does_not_touch_writer(self):
        controller = Controller(self.writer, dry_run=True, clock=self.clock)
        self.settings.update(fan_mode="balanced", screen_enabled=False, temperature_alert=True)
        fan, _, _ = controller.tick(self.settings, SAMPLE)
        self.assertEqual(fan["application"], "preview")
        self.assertEqual(self.writer.frames, [])
        self.assertIsNone(self.writer.fd)


class FanConfigTests(unittest.TestCase):
    def test_bad_fan_settings_and_old_config_migration(self):
        old = config.validate({"unit": "F", "interval": 1, "enabled": True, "controller_uid": 1000})
        self.assertEqual(old["fan_mode"], "unchanged")
        for values in ({"fan_pwm": 0}, {"fan_pwm": True}, {"fan_mode": "AI"},
                       {"fan_acceleration": 5}, {"screen_enabled": 1}, {"temperature_alert": "true"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                config.validate(values)
