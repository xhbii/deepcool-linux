"""One HID writer with local, UID-authenticated configuration IPC."""

import fcntl
import json
import logging
import os
from pathlib import Path
import selectors
import signal
import socket
import struct
import time

from . import config
from .hardware import HidWriter, devices
from .protocol import telemetry_report
from .sensors import CpuSensors

LOG = logging.getLogger(__name__)


def dispatch(request: dict, uid: int, settings: dict, snapshot: dict,
             config_path: Path) -> dict:
    if not isinstance(request, dict):
        raise ValueError("Request must be an object")
    if request.get("command") == "status":
        return {"ok": True, "status": snapshot,
                "settings": {k: settings[k] for k in config.SETTINGS}}
    if request.get("command") == "settings":
        if uid not in (0, settings["controller_uid"]):
            raise PermissionError("Only the configured desktop user can change settings")
        values = request.get("values")
        if not isinstance(values, dict) or set(values) - config.SETTINGS:
            raise ValueError("Only unit, interval and enabled can be changed")
        updated = config.validate({**settings, **values})
        config.save(updated, config_path)
        settings.update(updated)
        return {"ok": True, "settings": {k: settings[k] for k in config.SETTINGS}}
    raise ValueError("Unknown command")


def request(command="status", values=None, socket_path=config.SOCKET) -> dict:
    payload = {"command": command}
    if values is not None:
        payload["values"] = values
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(2)
        client.connect(str(socket_path))
        client.sendall(json.dumps(payload).encode() + b"\n")
        result = b""
        while b"\n" not in result:
            chunk = client.recv(4096)
            if not chunk:
                raise OSError("Service disconnected")
            result += chunk
            if len(result) > 65536:
                raise ValueError("Service response too large")
    response = json.loads(result.split(b"\n", 1)[0])
    if not response.get("ok"):
        raise OSError(response.get("error", "Service request failed"))
    return response


def handle_client(server, settings, snapshot, config_path):
    connection, _ = server.accept()
    with connection:
        # A stalled client must not prevent telemetry updates for seconds.
        connection.settimeout(.05)
        deadline = time.monotonic() + .05
        try:
            _, uid, _ = struct.unpack("3i", connection.getsockopt(
                socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
            data = b""
            while b"\n" not in data:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Request deadline exceeded")
                connection.settimeout(remaining)
                chunk = connection.recv(4096)
                if not chunk:
                    raise ValueError("Missing request")
                data += chunk
                if len(data) > 8192:
                    raise ValueError("Request too large")
            result = dispatch(json.loads(data.split(b"\n", 1)[0]), uid,
                              settings, snapshot, config_path)
        except (OSError, ValueError) as e:
            result = {"ok": False, "error": str(e)}
        try:
            connection.sendall(json.dumps(result, ensure_ascii=False).encode() + b"\n")
        except OSError:
            pass


def run(config_path=config.CONFIG, socket_path=config.SOCKET,
        dry_run=False, count=0):
    settings = config.load(config_path)
    sensors = CpuSensors()
    writer = HidWriter()
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    lock = (socket_path.parent / "daemon.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    socket_path.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    selector = selectors.DefaultSelector()
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    old_handlers = {s: signal.signal(s, stop) for s in (signal.SIGINT, signal.SIGTERM)}
    iterations, sent = 0, 0
    last_error = None
    next_sample = time.monotonic() + settings["interval"]
    snapshot = {"state": "starting", "dry_run": dry_run, "sent_reports": 0}
    try:
        server.bind(str(socket_path))
        # Reads are available locally. Mutations are authenticated by SO_PEERCRED.
        os.chmod(socket_path, 0o666)
        server.listen(8)
        selector.register(server, selectors.EVENT_READ)
        LOG.info("Started, dry_run=%s, controller_uid=%s", dry_run, settings["controller_uid"])
        while not stopping:
            if selector.select(max(0, min(.2, next_sample - time.monotonic()))):
                handle_client(server, settings, snapshot, config_path)
            if time.monotonic() < next_sample:
                continue
            sample = sensors.sample()
            snapshot = {**sample, "dry_run": dry_run, "sent_reports": sent,
                        "device": writer.path, "state": "paused", "error": None,
                        "last_report_hex": None}
            if not settings["enabled"]:
                writer.close()
            elif sample["temperature_c"] is None or sample["usage_percent"] is None:
                snapshot["state"] = "sensor_error"
                snapshot["error"] = "CPU 温度或使用率不可读，停止发送"
                writer.close()
            else:
                report = telemetry_report(sample["temperature_c"], sample["usage_percent"],
                                          sample["power_w"] or 0,
                                          sample["frequency_mhz"] or 0, settings["unit"])
                snapshot["last_report_hex"] = report.hex(" ")
                if dry_run:
                    snapshot["state"] = "dry_run"
                    attached = devices()
                    snapshot["device"] = attached[0]["path"] if len(attached) == 1 else None
                else:
                    try:
                        writer.write(report)
                        sent += 1
                        snapshot.update(state="sending", device=writer.path,
                                        sent_reports=sent, last_sent=time.time())
                    except OSError as e:
                        snapshot.update(state="device_error", error=str(e))
            if snapshot["error"] != last_error:
                if snapshot["error"]:
                    LOG.warning("%s", snapshot["error"])
                elif last_error:
                    LOG.info("Device recovered")
                last_error = snapshot["error"]
            iterations += 1
            if count:
                print(json.dumps(snapshot, ensure_ascii=False), flush=True)
                if iterations >= count:
                    break
            next_sample = time.monotonic() + settings["interval"]
    finally:
        writer.close()
        selector.close()
        server.close()
        socket_path.unlink(missing_ok=True)
        lock.close()
        for s, handler in old_handlers.items():
            signal.signal(s, handler)
