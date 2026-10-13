import math
import unittest

from deepcool_linux.fan_policy import (PRESETS, curve_duty, target_duty,
                                      smooth_duty, validate_curve)


class FanPolicyTests(unittest.TestCase):
    def test_curve_interpolation(self):
        points = [[30, 30], [60, 60], [80, 100]]
        self.assertEqual(curve_duty(45, points), 45)
        self.assertEqual(curve_duty(70, points), 80)
        self.assertEqual(curve_duty(10, points), 30)

    def test_presets_are_monotonic(self):
        for points in PRESETS.values():
            validate_curve(points)

    def test_over_temperature_bypasses_manual_setting(self):
        self.assertEqual(target_duty(80, "manual", 20, []), (100, "over_temperature"))
        self.assertEqual(smooth_duty(20, 100, .1, "over_temperature"), 100)

    def test_missing_or_nonfinite_sensor_means_full_speed(self):
        for temperature in (None, math.nan, math.inf, -41, 151):
            with self.subTest(temperature=temperature):
                self.assertEqual(target_duty(temperature, "manual", 20, []), (100, "sensor_fail_safe"))

    def test_motherboard_has_no_software_target(self):
        self.assertEqual(target_duty(None, "motherboard", 20, []), (None, "motherboard"))

    def test_downward_ramp_only(self):
        self.assertEqual(smooth_duty(60, 80, .25, "curve"), 80)
        self.assertEqual(smooth_duty(80, 30, 1, "curve"), 75)
        self.assertEqual(smooth_duty(80, 30, 20, "curve"), 30)

    def test_bad_curves(self):
        for points in ([], [[30, 30]], [[30, 30], [30, 50]], [[30, 60], [40, 40]],
                       [[30, 0], [40, 40]], [[30, 30], [math.nan, 50]],
                       [[30, 30], [10**400, 50]]):
            with self.subTest(points=points), self.assertRaises(ValueError):
                validate_curve(points)


if __name__ == "__main__":
    unittest.main()
