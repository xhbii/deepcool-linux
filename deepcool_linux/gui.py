"""Small native desktop panel; the system service owns hardware access."""

from collections import deque
import json
from pathlib import Path
import queue
import threading

from .daemon import request
from . import __version__


def launch(socket_path: Path):
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
        root = tk.Tk()
    except (ImportError, RuntimeError) as e:
        print(f"无法打开图形界面：{e}。Arch 需要 python 和 tk，并在桌面终端运行。")
        return 1
    except Exception as e:
        # TclError is raised when no X11/Wayland desktop connection is available.
        print(f"无法连接桌面：{e}。请在图形桌面运行 deepcool-linux gui。")
        return 1
    bg, panel, muted, accent = "#10191e", "#1b292f", "#91a5ae", "#36ddbc"
    root.title("DeepCool · AK620 G2")
    root.geometry("820x890")
    root.minsize(780, 850)
    root.configure(bg=bg)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TCombobox", fieldbackground=panel, background=panel,
                    foreground="white", arrowcolor=accent)
    style.configure("TSpinbox", fieldbackground=panel, background=panel,
                    foreground="white", arrowcolor=accent)
    style.configure("TButton", background=panel, foreground="white", padding=9)
    style.map("TButton", background=[("active", "#285045")])
    style.configure("TCheckbutton", background=bg, foreground="white")
    style.map("TCheckbutton", background=[("active", bg)])
    frame = tk.Frame(root, bg=bg)
    frame.pack(fill="both", expand=True, padx=28, pady=22)

    def label(parent, text, font=("sans", 11), color="white", **kwargs):
        return tk.Label(parent, text=text, bg=parent["bg"], fg=color, font=font, **kwargs)

    label(frame, "DEEPCOOL / LINUX", ("sans", 11, "bold"), accent).pack(anchor="w")
    label(frame, "AK620 G2 控制面板", ("sans", 24, "bold")).pack(anchor="w", pady=(8, 4))
    cpu_label = label(frame, "正在连接后台服务…", color=muted)
    cpu_label.pack(anchor="w")
    state_label = label(frame, "连接中", color=accent)
    state_label.pack(anchor="w", pady=(14, 16))
    cards = tk.Frame(frame, bg=bg)
    cards.pack(fill="x")
    values = {}
    for i, (key, title) in enumerate((("temperature_c", "CPU 温度"),
                                    ("usage_percent", "使用率"),
                                    ("power_w", "封装功耗"),
                                    ("frequency_mhz", "最高核心频率"))):
        card = tk.Frame(cards, bg=panel, padx=12, pady=14)
        card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 5, 0))
        cards.columnconfigure(i, weight=1)
        label(card, title, color=muted).pack(anchor="w")
        values[key] = label(card, "—", ("sans", 20, "bold"))
        values[key].pack(anchor="w", pady=(8, 0))
    label(frame, "温度走势 · 最近 60 次采样", color=muted).pack(anchor="w", pady=(22, 6))
    canvas = tk.Canvas(frame, height=115, bg=panel, highlightthickness=0)
    canvas.pack(fill="x")
    history = deque(maxlen=60)
    controls = tk.Frame(frame, bg=bg)
    controls.pack(fill="x", pady=(20, 8))
    unit, interval, enabled = tk.StringVar(value="C"), tk.StringVar(value="1.0"), tk.BooleanVar(value=True)
    label(controls, "温度单位").grid(row=0, column=0, sticky="w")
    ttk.Combobox(controls, textvariable=unit, values=("C", "F"), state="readonly", width=5).grid(
        row=1, column=0, sticky="w", pady=7)
    label(controls, "刷新间隔（秒）").grid(row=0, column=1, sticky="w", padx=20)
    ttk.Spinbox(controls, from_=.25, to=10, increment=.25, textvariable=interval, width=7).grid(
        row=1, column=1, sticky="w", padx=20)
    ttk.Checkbutton(controls, text="发送到散热器", variable=enabled).grid(row=1, column=2, padx=10)
    screen, alert = tk.BooleanVar(value=True), tk.StringVar(value="保持原设置")
    ttk.Checkbutton(controls, text="数显屏幕开启", variable=screen).grid(row=2, column=0, columnspan=2, sticky="w")
    label(controls, "温度告警").grid(row=2, column=2, sticky="w", padx=10)
    ttk.Combobox(controls, textvariable=alert, values=("保持原设置", "开启", "关闭"),
                 state="readonly", width=11).grid(row=2, column=3, padx=14)
    fans = tk.Frame(frame, bg=panel, padx=14, pady=12)
    fans.pack(fill="x", pady=(12, 4))
    label(fans, "风扇控制", ("sans", 14, "bold")).grid(row=0, column=0, sticky="w")
    fan_state = label(fans, "正在读取…", color=accent)
    fan_state.grid(row=0, column=1, columnspan=3, sticky="e", padx=10)
    modes = {"保持当前设置": "unchanged", "跟随主板 PWM": "motherboard", "手动 PWM": "manual",
             "静音曲线": "quiet", "均衡曲线": "balanced", "性能曲线": "performance", "自定义曲线": "curve"}
    mode = tk.StringVar(value="保持当前设置")
    pwm = tk.StringVar(value="60")
    acceleration, deceleration = tk.StringVar(value="4"), tk.StringVar(value="2")
    curve = tk.StringVar(value="[[30,30],[50,45],[65,65],[75,90],[80,100]]")
    ttk.Combobox(fans, textvariable=mode, values=tuple(modes), state="readonly", width=17).grid(
        row=1, column=0, sticky="w", pady=12)
    label(fans, "手动 PWM（%）").grid(row=1, column=1, padx=(16, 5))
    ttk.Spinbox(fans, from_=20, to=100, increment=5, textvariable=pwm, width=5).grid(row=1, column=2)
    label(fans, "加速 / 减速等级（0–4）", color=muted).grid(row=2, column=0, columnspan=2, sticky="w")
    ttk.Spinbox(fans, from_=0, to=4, textvariable=acceleration, width=4).grid(row=2, column=2)
    ttk.Spinbox(fans, from_=0, to=4, textvariable=deceleration, width=4).grid(row=2, column=3, padx=10)
    label(fans, "自定义曲线：[[°C,PWM],…]", color=muted).grid(row=3, column=0, columnspan=4, sticky="w", pady=(10, 5))
    tk.Entry(fans, textvariable=curve, bg=bg, fg="white", insertbackground="white").grid(
        row=4, column=0, columnspan=4, sticky="ew")
    fans.columnconfigure(3, weight=1)
    label(frame, "软件模式：≥80°C 或温度不可读时全速；曲线为本项目的 Linux 策略。",
          ("sans", 10), muted).pack(anchor="w", pady=(8, 0))
    messages = label(frame, "", color=muted, justify="left", anchor="w", wraplength=750)
    messages.pack(fill="x", pady=(6, 0))
    footer = tk.Frame(frame, bg=bg)
    footer.pack(fill="x", pady=(10, 0))
    label(footer, "暂停遥测保留屏幕数值；风扇控制继续运行。", ("sans", 10), muted).pack(side="left")
    ttk.Button(footer, text="关于", command=lambda: messagebox.showinfo(
        "DeepCool Linux", f"AK620 G2 Linux controller {__version__}\nGPL-3.0-or-later · 无担保\n"
        "协议参考 Nortank12/deepcool-digital-linux\n源码、许可证和依据见项目目录。" )).pack(side="right")
    commands, results = queue.Queue(), queue.Queue()
    stop = threading.Event()
    initialized = False
    last_sample_time = None

    def apply():
        try:
            from .config import validate
            settings = {"unit": unit.get(), "interval": float(interval.get()), "enabled": enabled.get(),
                        "screen_enabled": screen.get(),
                        "temperature_alert": {"保持原设置": None, "开启": True, "关闭": False}[alert.get()]}
            validate(settings, partial=True)
            commands.put(settings)
            messages.configure(text="正在保存设置…")
        except ValueError as e:
            messagebox.showerror("设置错误", str(e))

    ttk.Button(controls, text="保存设置", command=apply).grid(row=1, column=3, padx=(14, 0))

    def apply_fan():
        try:
            from .config import validate
            settings = {"fan_mode": modes[mode.get()], "fan_pwm": int(pwm.get()),
                        "fan_acceleration": int(acceleration.get()), "fan_deceleration": int(deceleration.get()),
                        "fan_curve": json.loads(curve.get())}
            validate(settings, partial=True)
            commands.put(settings)
            messages.configure(text="正在保存风扇设置…")
        except ValueError as e:
            messagebox.showerror("风扇设置错误", str(e))

    ttk.Button(fans, text="应用风扇设置", command=apply_fan).grid(row=1, column=3, padx=10)

    def worker():
        while not stop.is_set():
            try:
                while not commands.empty():
                    request("settings", commands.get_nowait(), socket_path)
                results.put((request(socket_path=socket_path), None))
            except (OSError, ValueError) as e:
                results.put((None, str(e)))
            stop.wait(1)

    def refresh():
        nonlocal initialized, last_sample_time
        response, error = None, None
        changed = False
        while not results.empty():
            response, error = results.get_nowait()
            changed = True
        if changed:
            if error:
                state_label.configure(text="后台服务未连接", fg="#ffbe76")
                messages.configure(text="请先完成系统安装并启动 deepcool-linux.service。\n" + error)
                for item in values.values():
                    item.configure(text="—")
            else:
                sample, settings = response["status"], response["settings"]
                if not initialized:
                    unit.set(settings["unit"])
                    interval.set(str(settings["interval"]))
                    enabled.set(settings["enabled"])
                    screen.set(settings.get("screen_enabled", True))
                    alert.set({None: "保持原设置", True: "开启", False: "关闭"}[settings.get("temperature_alert")])
                    mode.set(next(k for k, v in modes.items() if v == settings.get("fan_mode", "unchanged")))
                    pwm.set(str(settings.get("fan_pwm", 60)))
                    acceleration.set(str(settings.get("fan_acceleration", 4)))
                    deceleration.set(str(settings.get("fan_deceleration", 2)))
                    if "fan_curve" in settings:
                        curve.set(json.dumps(settings["fan_curve"], separators=(",", ":")))
                    initialized = True
                cpu_label.configure(text=sample.get("cpu", "正在采样…"))
                states = {"sending": "正在发送到散热器", "dry_run": "预览模式 · 未写入 USB",
                          "paused": "已暂停发送", "device_error": "设备通信异常 · 正在重试",
                          "sensor_error": "传感器异常", "screen_off": "数显屏幕已发送关闭命令", "starting": "正在采样…"}
                state_label.configure(text=states.get(sample.get("state"), "正在采样…"),
                                      fg=accent if sample.get("state") in ("sending", "dry_run") else "#ffbe76")
                formats = {"temperature_c": "{:.1f} °" + settings["unit"], "usage_percent": "{:.0f} %",
                           "power_w": "{:.1f} W", "frequency_mhz": "{:.2f} GHz"}
                for key, widget in values.items():
                    value = sample.get(key)
                    if value is not None:
                        if key == "temperature_c" and settings["unit"] == "F":
                            value = value * 1.8 + 32
                        elif key == "frequency_mhz":
                            value /= 1000
                    widget.configure(text=formats[key].format(value) if value is not None else "不可读")
                messages.configure(text="\n".join([sample.get("error") or "", *sample.get("warnings", [])]).strip()
                                   or f"设备：{sample.get('device') or '—'} · 已发送 {sample.get('sent_reports', 0)} 个数据包")
                fan = sample.get("fan", {})
                rpm = fan.get("rpm")
                target = fan.get("target_pwm")
                fan_text = f"{rpm} RPM" if rpm is not None else "RPM 未反馈"
                if target is not None:
                    fan_text += f" · 目标 {target}%"
                reason = {"over_temperature": "温度保护", "sensor_fail_safe": "传感器保护"}.get(fan.get("reason"))
                if reason:
                    fan_text += " · " + reason
                application = {"preview": "预览", "unchanged": "保持当前", "failed": "写入失败",
                               "written_without_ack": "命令已写入"}.get(fan.get("application"), "待更新服务")
                fan_state.configure(text=fan_text + " · " + application)
                if sample.get("time") != last_sample_time:
                    last_sample_time = sample.get("time")
                    history.append(sample.get("temperature_c"))
                canvas.delete("all")
                width, height = max(1, canvas.winfo_width()), 115
                for temp in (40, 60, 80, 100):
                    y = height - 10 - temp / 110 * (height - 20)
                    canvas.create_line(28, y, width, y, fill="#304047")
                    canvas.create_text(16, y, text=str(temp), fill=muted, font=("sans", 8))
                points = []
                for i, temperature in enumerate(history):
                    if temperature is None:
                        if len(points) >= 4:
                            canvas.create_line(*points, fill=accent, width=2)
                        points = []
                        continue
                    x = 32 + i / 59 * (width - 44)
                    y = height - 10 - max(0, min(110, temperature)) / 110 * (height - 20)
                    points.extend((x, y))
                if len(points) >= 4:
                    canvas.create_line(*points, fill=accent, width=2)
        root.after(250, refresh)

    def close():
        stop.set()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    threading.Thread(target=worker, daemon=True).start()
    refresh()
    root.mainloop()
    return 0
