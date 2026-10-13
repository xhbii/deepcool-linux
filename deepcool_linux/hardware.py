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

    def write(self, report: bytes):
        if len(report) != 64 or report[0] != 0x10:
            raise ValueError("Expected a 64-byte report with ID 0x10")
        if self.fd is None:
            candidates = devices()
            if not candidates:
                raise FileNotFoundError(errno.ENODEV, "未发现 AK620 G2 (3633:0029)")
            if len(candidates) > 1:
                raise OSError("发现多个 AK620 G2，暂不支持自动选择")
            path = candidates[0]["path"]
            fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK | os.O_CLOEXEC)
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
        try:
            n = os.write(self.fd, report)
            if n != len(report):
                raise OSError(f"Incomplete HID report ({n}/64)")
        except OSError:
            self.close()
            raise
