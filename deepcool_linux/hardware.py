"""Linux hidraw access, with sysfs discovery and opened-fd identity checks."""

import errno
import fcntl
import os
from pathlib import Path
import struct

from .protocol import VID, PID


def devices(sys_class: Path = Path("/sys/class/hidraw"),
            dev_root: Path = Path("/dev")) -> list[dict]:
    found = []
    for entry in sorted(sys_class.glob("hidraw*")):
        try:
            fields = dict(line.split("=", 1) for line in
                          (entry / "device/uevent").read_text().splitlines() if "=" in line)
            bus, vendor, product = (int(v, 16) for v in fields["HID_ID"].split(":"))
            if (bus, vendor, product) != (3, VID, PID):
                continue
            node = dev_root / entry.name
            found.append({"path": str(node), "name": fields.get("HID_NAME", "AK620-GEN2"),
                          "serial": fields.get("HID_UNIQ", ""),
                          "writable": os.access(node, os.W_OK)})
        except (OSError, ValueError, KeyError):
            continue
    return found


class HidWriter:
    def __init__(self):
        self.fd = None
        self.path = None

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
        self.fd = self.path = None

    def open(self):
        if self.fd is None:
            candidates = devices()
            if not candidates:
                raise FileNotFoundError(errno.ENODEV, "未发现 AK620 G2 (3633:0029)")
            if len(candidates) > 1:
                raise OSError("发现多个 AK620 G2，暂不支持自动选择")
            path = candidates[0]["path"]
            fd = os.open(path, os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)
            try:
                info = bytearray(8)
                # _IOR('H', 0x03, struct hidraw_devinfo), from linux/hidraw.h.
                fcntl.ioctl(fd, 0x80084803, info, True)
                bus, vid, pid = struct.unpack("=IHH", info)
                if (bus, vid, pid) != (3, VID, PID):
                    raise OSError("HID 设备身份变化，取消写入")
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BaseException:
                os.close(fd)
                raise
            self.fd, self.path = fd, path

    def write(self, report: bytes):
        if len(report) != 64 or report[0] != 0x10:
            raise ValueError("Expected a 64-byte report with ID 0x10")
        self.open()
        try:
            n = os.write(self.fd, report)
            if n != len(report):
                raise OSError(f"Incomplete HID report ({n}/64)")
        except OSError:
            self.close()
            raise

    def get_feature(self, report_id: int) -> bytes:
        # Sizes come from this model's HID report descriptor, including the ID.
        lengths = {2: 64, 3: 64, 4: 64, 5: 2}
        if type(report_id) is not int or report_id not in lengths:
            raise ValueError("Unsupported AK620 G2 feature report")
        length = lengths[report_id]
        self.open()
        data = bytearray(length)
        data[0] = report_id
        try:
            size = fcntl.ioctl(self.fd, 0xC0004807 | (length << 16), data, True)
            if not 1 <= size <= length or data[0] != report_id:
                raise OSError("Invalid HID feature response")
            return bytes(data[:size])
        except OSError:
            self.close()
            raise

    def send_feature(self, report: bytes):
        lengths = {2: 64, 3: 64, 4: 64, 5: 2}
        if not report or len(report) != lengths.get(report[0]):
            raise ValueError("Unsupported AK620 G2 feature report")
        self.open()
        try:
            size = fcntl.ioctl(self.fd, 0xC0004806 | (len(report) << 16), bytearray(report), True)
            if size != len(report):
                raise OSError(f"Incomplete HID feature write ({size}/{len(report)})")
        except OSError:
            self.close()
            raise

    def read_inputs(self, limit: int = 16) -> list[bytes]:
        if type(limit) is not int or not 1 <= limit <= 32:
            raise ValueError("Invalid input report budget")
        self.open()
        reports = []
        try:
            for _ in range(limit):
                try:
                    report = os.read(self.fd, 64)
                except BlockingIOError:
                    break
                if not report:
                    raise OSError("HID input disconnected")
                reports.append(report)
        except OSError:
            self.close()
            raise
        return reports
