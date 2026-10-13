"""Small native desktop panel; the system service owns hardware access."""

from collections import deque
from pathlib import Path
import queue
import threading

from .daemon import request


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
    root.geometry("780x620")
    root.minsize(720, 590)
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
    label(frame, "AK620 G2 数显控制", ("sans", 24, "bold")).pack(anchor="w", pady=(8, 4))
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
    messages = label(frame, "", color=muted, justify="left", anchor="w", wraplength=710)
    messages.pack(fill="x", pady=(6, 0))
    label(frame, "暂停发送会保留屏幕最后的数值。", ("sans", 10), muted).pack(anchor="w", pady=(10, 0))
    footer = tk.Frame(frame, bg=bg)
    footer.pack(fill="x", pady=(10, 0))
    label(footer, "风扇、AI 档位和数显开关：协议核实后提供。", ("sans", 10), muted).pack(side="left")
    ttk.Button(footer, text="关于", command=lambda: messagebox.showinfo(
        "DeepCool Linux", "AK620 G2 Linux controller 0.1.0\nGPL-3.0-or-later · 无担保\n"
        "协议参考 Nortank12/deepcool-digital-linux\n源码、许可证和依据见项目目录。" )).pack(side="right")
    commands, results = queue.Queue(), queue.Queue()
    stop = threading.Event()
    initialized = False
    last_sample_time = None

    def apply():
        try:
            from .config import validate
            settings = {"unit": unit.get(), "interval": float(interval.get()), "enabled": enabled.get()}
            validate(settings, partial=True)
            commands.put(settings)
            messages.configure(text="正在保存设置…")
        except ValueError as e:
            messagebox.showerror("设置错误", str(e))

    ttk.Button(controls, text="保存设置", command=apply).grid(row=1, column=3, padx=(14, 0))

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
                    initialized = True
                cpu_label.configure(text=sample.get("cpu", "正在采样…"))
                states = {"sending": "正在发送到散热器", "dry_run": "预览模式 · 未写入 USB",
                          "paused": "已暂停发送", "device_error": "设备通信异常 · 正在重试",
                          "sensor_error": "传感器异常", "starting": "正在采样…"}
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
