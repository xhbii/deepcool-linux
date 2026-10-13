"""Linux fan policy, independent of the USB transport.

Curves here are Linux presets, not reconstructions of the vendor's AI model.
"""

import math

PRESETS = {
    "quiet": [(30, 25), (50, 35), (65, 55), (75, 85), (80, 100)],
    "balanced": [(30, 30), (50, 45), (65, 65), (75, 90), (80, 100)],
    "performance": [(30, 45), (50, 60), (65, 80), (75, 100), (80, 100)],
}
EMERGENCY_C = 80.0
MIN_DUTY = 20


def validate_curve(points) -> list[tuple[float, float]]:
    if not isinstance(points, list) or not 2 <= len(points) <= 16:
        raise ValueError("风扇曲线需要 2–16 个温度/PWM 点")
    result = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError("曲线点应为 [摄氏温度, PWM百分比]")
        temperature, duty = point
        if type(temperature) not in (int, float) or not 0 <= temperature <= 100:
            raise ValueError("曲线温度应为 0–100°C")
        if type(duty) not in (int, float) or not MIN_DUTY <= duty <= 100:
            raise ValueError("PWM 应为 20–100%")
        if result and (temperature <= result[-1][0] or duty < result[-1][1]):
            raise ValueError("曲线温度必须递增，PWM 不得随温度下降")
        result.append((float(temperature), float(duty)))
    return result


def curve_duty(temperature: float, points: list) -> float:
    points = validate_curve(points)
    if temperature <= points[0][0]:
        return points[0][1]
    for (t0, p0), (t1, p1) in zip(points, points[1:]):
        if temperature <= t1:
            return p0 + (p1 - p0) * (temperature - t0) / (t1 - t0)
    return points[-1][1]


def target_duty(temperature_c, mode: str, manual: int, points: list) -> tuple[int | None, str]:
    if mode == "motherboard":
        return None, "motherboard"
    if (type(temperature_c) not in (int, float)
            or not -40 <= temperature_c <= 150 or not math.isfinite(temperature_c)):
        return 100, "sensor_fail_safe"
    if temperature_c >= EMERGENCY_C:
        return 100, "over_temperature"
    if mode == "manual":
        duty = manual
    elif mode == "curve":
        duty = curve_duty(temperature_c, points)
    else:
        raise ValueError("Unknown fan mode")
    return max(MIN_DUTY, min(100, math.floor(duty + .5))), mode


def smooth_duty(previous: int | None, target: int, seconds: float, reason: str) -> int:
    # Heating response is immediate. Slow only normal downward transitions.
    if previous is None or target >= previous or reason in ("over_temperature", "sensor_fail_safe"):
        return target
    return max(target, math.ceil(previous - max(0, seconds) * 5))
