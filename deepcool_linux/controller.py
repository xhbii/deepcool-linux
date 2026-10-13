"""Single-session command ordering, fan policy and bounded RPM feedback."""

import time
import math

from .fan_policy import PRESETS, target_duty, smooth_duty
from .protocol import command_report, decode_rpm, display_report, telemetry_report


class Controller:
    def __init__(self, writer, dry_run=False, clock=time.monotonic, sleep=time.sleep):
        self.writer, self.dry_run, self.clock = writer, dry_run, clock
        self.sleep = sleep
        self.last_write = None
        self.applied = {}
        self.last_pwm = None
        self.last_tick = clock()
        self.rpm = None
        self.rpm_time = None
        self.input_frames = []
        self.command_count = 0
        self.closed_display = False
        self.software_owned = False

    def reset(self):
        self.applied.clear()
        self.last_pwm = None
        self.rpm = self.rpm_time = None
        self.closed_display = False

    def write(self, report):
        if not self.dry_run:
            # Match the factory's 100ms spacing rather than flooding firmware.
            if self.last_write is not None:
                self.sleep(max(0, .1 - (self.clock() - self.last_write)))
            self.writer.write(report)
            self.last_write = self.clock()

    def send(self, command, value=None):
        self.write(command_report(command, value))
        self.command_count += 1

    def apply(self, key, value, command):
        if self.applied.get(key) != value:
            self.send(command, value)
            self.applied[key] = value

    def fan(self, settings, sample, now):
        mode = settings["fan_mode"]
        reason, target = mode, None
        if mode in ("unchanged", "motherboard"):
            if mode == "motherboard" or self.software_owned:
                self.apply("sync", 1, 2)
            self.last_pwm = None
            self.software_owned = False
        else:
            points = PRESETS.get(mode, settings["fan_curve"])
            policy = "manual" if mode == "manual" else "curve"
            target, reason = target_duty(sample.get("temperature_c"), policy,
                                         settings["fan_pwm"], points)
            target = smooth_duty(self.last_pwm, target, now - self.last_tick, reason)
            # Write a nonzero target BEFORE taking control from the motherboard.
            # Never cache unsuccessful writes. Overtemperature bypasses acceleration.
            ramp = 0 if reason in ("over_temperature", "sensor_fail_safe") else (
                4 - settings["fan_acceleration"]) * 10
            self.apply("acceleration", ramp, 4)
            self.apply("deceleration", (4 - settings["fan_deceleration"]) * 10, 5)
            self.apply("pwm", target, 3)
            self.apply("sync", 0, 2)
            self.last_pwm = target
            self.software_owned = True
        self.last_tick = now
        return {"mode": mode, "target_pwm": target, "reason": reason,
                "application": "preview" if self.dry_run else (
                    "unchanged" if mode == "unchanged" else "written_without_ack")}

    def tick(self, settings, sample, telemetry_due=True):
        now = self.clock()
        if not self.dry_run and self.writer.fd is None:
            self.reset()
        fan = self.fan(settings, sample, now)
        if settings["temperature_alert"] is not None:
            self.apply("alert", int(settings["temperature_alert"]), 6)
        temperature = sample.get("temperature_c")
        usage = sample.get("usage_percent")
        valid_temperature = (type(temperature) in (int, float) and -40 <= temperature <= 150
                             and math.isfinite(temperature))
        valid_usage = type(usage) in (int, float) and math.isfinite(usage)
        valid = valid_temperature and valid_usage
        report = None
        sent_telemetry = False
        # On/off reports require telemetry fields even if sensors are unavailable.
        # These placeholder fields are not sent as regular telemetry.
        args = (temperature if valid_temperature else 0, usage if valid_usage else 0,
                sample.get("power_w") or 0, sample.get("frequency_mhz") or 0, settings["unit"])
        if not settings["screen_enabled"]:
            if not self.closed_display:
                report = display_report(False, *args)
                self.write(report)
                self.closed_display = True
        else:
            if self.closed_display and valid:
                report = display_report(True, *args)
                self.write(report)
                self.closed_display = False
            if settings["enabled"] and valid and telemetry_due:
                report = telemetry_report(*args)
                self.write(report)
                sent_telemetry = True
        # RPM poll is independent of screen state and telemetry pause.
        self.send(8)
        if not self.dry_run:
            frames = self.writer.read_inputs()
            if frames:
                self.input_frames = [f.hex(" ") for f in frames[-4:]]
            for frame in frames:
                rpm = decode_rpm(frame)
                if rpm is not None:
                    self.rpm, self.rpm_time = rpm, now
        age = now - self.rpm_time if self.rpm_time is not None else None
        fan.update(rpm=self.rpm if age is not None and age <= 5 else None,
                   rpm_age_seconds=age, input_frames=self.input_frames,
                   command_writes=self.command_count)
        return fan, report, sent_telemetry

    def release(self):
        # Restore motherboard control when software owned the fans.
        if self.software_owned and not self.dry_run:
            self.send(2, 1)
        self.software_owned = False
