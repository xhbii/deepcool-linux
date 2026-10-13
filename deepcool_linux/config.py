"""Validated configuration; clients cannot change filesystem/device paths."""

import json
import math
import os
from pathlib import Path

DEFAULTS = {"unit": "C", "interval": 1.0, "enabled": True, "controller_uid": 0}
SETTINGS = {"unit", "interval", "enabled"}
CONFIG = Path("/var/lib/deepcool-linux/config.json")
SOCKET = Path("/run/deepcool-linux/control.sock")


def validate(values: dict, partial=False) -> dict:
    if not isinstance(values, dict):
        raise ValueError("Configuration must be a JSON object")
    if set(values) - set(DEFAULTS):
        raise ValueError("Unknown configuration key")
    result = values.copy() if partial else {**DEFAULTS, **values}
    if "unit" in result and result["unit"] not in ("C", "F"):
        raise ValueError("温度单位应为 C 或 F")
    if "interval" in result:
        n = result["interval"]
        if type(n) not in (int, float) or not .25 <= n <= 10 or not math.isfinite(n):
            raise ValueError("刷新间隔应为 0.25 至 10 秒")
    if "enabled" in result and type(result["enabled"]) is not bool:
        raise ValueError("enabled must be boolean")
    if "controller_uid" in result:
        uid = result["controller_uid"]
        if type(uid) is not int or not 0 <= uid <= 2**31 - 1:
            raise ValueError("controller_uid must be a valid Linux UID")
    return result


def load(path: Path = CONFIG) -> dict:
    try:
        if path.stat().st_size > 8192:
            raise ValueError("Config file exceeds 8 KiB")
        return validate(json.loads(path.read_text()))
    except FileNotFoundError:
        return DEFAULTS.copy()


def save(values: dict, path: Path = CONFIG):
    values = validate(values)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(values, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
