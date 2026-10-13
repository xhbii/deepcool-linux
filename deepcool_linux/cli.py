"""Command line entry points; no third-party runtime dependencies."""

import argparse
import json
import logging
import os
import pwd
from pathlib import Path
import sys
import time

from . import __version__, config
from .daemon import request, run
from .hardware import devices
from .protocol import telemetry_report
from .sensors import CpuSensors


def main(argv=None):
    parser = argparse.ArgumentParser(description="DeepCool AK620 G2 Linux 数显控制器")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("devices", help="查找 3633:0029 设备（不写入）")
    doctor = sub.add_parser("doctor", help="检查设备、传感器和服务（不写入）")
    doctor.add_argument("--socket", type=Path, default=config.SOCKET)
    monitor = sub.add_parser("sample", help="读取 CPU 指标并打印数据包（不写入）")
    monitor.add_argument("--unit", choices=("C", "F"), default="C")
    monitor.add_argument("--interval", type=float, default=1)
    daemon = sub.add_parser("run", help="运行后台数显控制器")
    daemon.add_argument("--config", type=Path, default=config.CONFIG)
    daemon.add_argument("--socket", type=Path, default=config.SOCKET)
    daemon.add_argument("--dry-run", action="store_true", help="只读取并编码，不写 USB")
    daemon.add_argument("--count", type=int, default=0, help="运行指定采样次数后退出")
    status = sub.add_parser("status", help="查询后台服务状态")
    status.add_argument("--socket", type=Path, default=config.SOCKET)
    setting = sub.add_parser("set", help="修改后台服务设置")
    setting.add_argument("--socket", type=Path, default=config.SOCKET)
    setting.add_argument("--unit", choices=("C", "F"))
    setting.add_argument("--interval", type=float)
    setting.add_argument("--enabled", choices=("true", "false"))
    setting.add_argument("--screen-enabled", choices=("true", "false"))
    setting.add_argument("--temperature-alert", choices=("true", "false", "unchanged"))
    setting.add_argument("--fan-mode", choices=("unchanged", "motherboard", "manual",
                                               "quiet", "balanced", "performance", "curve"))
    setting.add_argument("--fan-pwm", type=int, help="手动 PWM，20–100%%")
    setting.add_argument("--fan-curve", type=json.loads, help='JSON 曲线，例如 [[30,30],[60,60],[80,100]]')
    setting.add_argument("--fan-acceleration", type=int, help="0–4，4 为立即加速")
    setting.add_argument("--fan-deceleration", type=int, help="0–4")
    gui = sub.add_parser("gui", help="打开中文桌面控制界面")
    gui.add_argument("--socket", type=Path, default=config.SOCKET)
    authorize = sub.add_parser("authorize-user", help="指定可修改设置的桌面用户（仅 root）")
    authorize.add_argument("user")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        if args.command == "devices":
            result = devices()
        elif args.command == "sample":
            config.validate({"interval": args.interval}, partial=True)
            sensors = CpuSensors()
            time.sleep(args.interval)
            result = sensors.sample()
            result["report_hex"] = None
            if result["temperature_c"] is not None and result["usage_percent"] is not None:
                result["report_hex"] = telemetry_report(result["temperature_c"],
                    result["usage_percent"], result["power_w"] or 0,
                    result["frequency_mhz"] or 0, args.unit).hex(" ")
        elif args.command == "doctor":
            sensors = CpuSensors()
            time.sleep(.25)
            result = {"devices": devices(), "sensors": sensors.sample(),
                      "service": None, "service_error": None}
            try:
                result["service"] = request(socket_path=args.socket)
            except OSError as e:
                result["service_error"] = str(e)
        elif args.command == "run":
            if args.count < 0:
                parser.error("--count must be non-negative")
            run(args.config, args.socket, args.dry_run, args.count)
            return 0
        elif args.command == "status":
            result = request(socket_path=args.socket)
        elif args.command == "set":
            values = {k: getattr(args, k) for k in config.SETTINGS if getattr(args, k) is not None}
            for key in ("enabled", "screen_enabled", "temperature_alert"):
                if key in values:
                    values[key] = None if values[key] == "unchanged" else values[key] == "true"
            config.validate(values, partial=True)
            if not values:
                parser.error("请指定至少一个设置；可用选项见 set --help")
            result = request("settings", values, args.socket)
        elif args.command == "authorize-user":
            if os.geteuid() != 0:
                raise PermissionError("请用 sudo 运行 authorize-user")
            try:
                uid = pwd.getpwnam(args.user).pw_uid
            except KeyError:
                raise ValueError("用户不存在") from None
            values = config.load()
            values["controller_uid"] = uid
            config.save(values)
            result = {"controller_uid": uid, "next_step": "sudo systemctl restart deepcool-linux.service"}
        else:
            from .gui import launch
            return launch(args.socket)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
