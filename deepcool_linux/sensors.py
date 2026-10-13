"""CPU telemetry read from hwmon, procfs and package energy counters."""

import math
from pathlib import Path
import time


def read_text(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except OSError:
        return None


def read_number(path: Path) -> float | None:
    try:
        value = float(path.read_text().strip())
        return value if math.isfinite(value) else None
    except (OSError, ValueError):
        return None


def cpu_times(proc: Path = Path("/proc")) -> tuple[int, int]:
    fields = (proc / "stat").read_text().splitlines()[0].split()
    if fields[0] != "cpu" or len(fields) < 5:
        raise ValueError("Invalid aggregate /proc/stat")
    # guest and guest_nice are already included in user and nice.
    ticks = [int(x) for x in fields[1:9]]
    idle = ticks[3] + (ticks[4] if len(ticks) > 4 else 0)
    return sum(ticks), idle


def utilization(previous: tuple[int, int], current: tuple[int, int]) -> float | None:
    total = current[0] - previous[0]
    idle = current[1] - previous[1]
    if total <= 0 or idle < 0:
        return None
    return max(0.0, min(100.0, 100.0 * (total - idle) / total))


def discover_temperature(hwmon: Path) -> Path | None:
    candidates = []
    for node in sorted(hwmon.glob("hwmon*")):
        driver = read_text(node / "name")
        if driver not in ("k10temp", "zenpower", "coretemp"):
            continue
        for sensor in sorted(node.glob("temp*_input")):
            label = read_text(sensor.with_name(sensor.name.replace("_input", "_label"))) or ""
            if label == "Tdie":
                rank = 0
            elif label.startswith("Package id"):
                rank = 1
            elif label == "Tctl":
                rank = 2
            elif sensor.name == "temp1_input":
                rank = 3
            else:
                rank = 4
            candidates.append((rank, str(sensor), sensor))
    return min(candidates)[2] if candidates else None


def discover_energy(powercap: Path, hwmon: Path) -> list[tuple[Path, float | None]]:
    # Top-level package zones only. Do not double count nested core/uncore zones.
    counters = []
    for zone in sorted(powercap.glob("*:*")):
        if zone.name.count(":") != 1:
            continue
        name = read_text(zone / "name") or ""
        if name.startswith("package-") and (zone / "energy_uj").exists():
            counters.append((zone / "energy_uj", read_number(zone / "max_energy_range_uj")))
    if counters:
        return counters
    for node in sorted(hwmon.glob("hwmon*")):
        if read_text(node / "name") not in ("amd_energy", "zenergy"):
            continue
        for label in node.glob("energy*_label"):
            if (read_text(label) or "").startswith("Esocket"):
                path = label.with_name(label.name.replace("_label", "_input"))
                if path.exists():
                    counters.append((path, None))
    return counters


def power_delta(before: float, after: float, seconds: float,
                maximum: float | None) -> float | None:
    if seconds <= 0 or not all(math.isfinite(x) for x in (before, after, seconds)):
        return None
    delta = after - before
    if delta < 0:
        # A decrease may be a wrap or a reset; accept only a plausible boundary wrap.
        if maximum is None or not (before > maximum * .9 and after < maximum * .1):
            return None
        delta += maximum
    watts = delta / seconds / 1_000_000
    return watts if 0 <= watts <= 2000 else None


class CpuSensors:
    def __init__(self, hwmon=Path("/sys/class/hwmon"),
                 proc=Path("/proc"), powercap=Path("/sys/class/powercap")):
        self.hwmon, self.proc, self.powercap = hwmon, proc, powercap
        self.temperature_path = discover_temperature(hwmon)
        self.energy = discover_energy(powercap, hwmon)
        self.previous_time = time.monotonic()
        self.previous_ticks = cpu_times(proc)
        self.previous_energy = [read_number(p) for p, _ in self.energy]
        self.next_energy_scan = self.previous_time + 10
        text = read_text(proc / "cpuinfo") or ""
        self.model = next((line.split(":", 1)[1].strip() for line in text.splitlines()
                           if line.startswith("model name")), "CPU")

    def sample(self) -> dict:
        now = time.monotonic()
        ticks = cpu_times(self.proc)
        usage = utilization(self.previous_ticks, ticks)
        self.previous_ticks = ticks
        if self.temperature_path is None or not self.temperature_path.exists():
            self.temperature_path = discover_temperature(self.hwmon)
        temperature = read_number(self.temperature_path) if self.temperature_path else None
        if temperature is not None:
            temperature /= 1000
            if not -40 <= temperature <= 150:
                temperature = None
        energies = [read_number(p) for p, _ in self.energy]
        powers = [power_delta(before, after, now - self.previous_time, maximum)
                  if before is not None and after is not None else None
                  for before, after, (_, maximum) in
                  zip(self.previous_energy, energies, self.energy)]
        power = sum(powers) if powers and all(p is not None for p in powers) else None
        self.previous_energy, self.previous_time = energies, now
        if (not energies or all(e is None for e in energies)) and now >= self.next_energy_scan:
            self.energy = discover_energy(self.powercap, self.hwmon)
            self.previous_energy = [read_number(p) for p, _ in self.energy]
            self.next_energy_scan = now + 10
        clocks = []
        for line in (read_text(self.proc / "cpuinfo") or "").splitlines():
            if line.startswith("cpu MHz"):
                try:
                    value = float(line.split(":", 1)[1])
                    if math.isfinite(value) and value > 0:
                        clocks.append(value)
                except ValueError:
                    pass
        warnings = []
        if temperature is None:
            warnings.append("CPU 温度不可读：停止发送遥测，避免显示错误温度")
        if power is None:
            warnings.append("CPU 功耗不可读：屏幕功耗字段暂填 0；用系统服务可读取 RAPL")
        if not clocks:
            warnings.append("CPU 频率不可读：屏幕频率字段暂填 0")
        return {"cpu": self.model, "temperature_c": temperature, "usage_percent": usage,
                "power_w": power, "frequency_mhz": max(clocks) if clocks else None,
                "temperature_sensor": str(self.temperature_path) if self.temperature_path else None,
                "energy_sensors": [str(p) for p, _ in self.energy],
                "warnings": warnings, "time": time.time()}
