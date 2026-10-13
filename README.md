# DeepCool AK620 G2 · Arch Linux 控制器

为 **AK620 G2 DIGITAL NYX / AK620-GEN2，USB `3633:0029`**
编写的用户态 HID 控制程序。使用 Linux 已有的 `hidraw` 驱动，无需 Wine、
Windows 程序或第三方 Python 包。核心功能仅依赖 Arch 的 `python`，图形面板依赖 `tk`。

0.2.0 提供 CPU 温度、使用率、封装功耗和最高核心频率显示，摄氏/华氏切换、
0.25–10 秒遥测刷新、中文桌面面板和 systemd 开机启动。
新增主板 PWM 同步、20–100% 手动 PWM、静音/均衡/性能温度曲线、自定义曲线、
加速/减速等级、RPM 反馈读取、数显开关和温度告警开关。

数显遥测已由用户在连接的 AK620 G2 上确认正常。
新增控制命令来自原厂 1.2.14 程序的离线字节码分析，编码与策略通过自动测试；
**风扇实际响应、RPM 和开关屏效果仍待本机验证**。
服务区分命令写入、写入失败和转速反馈，写入成功不代表设备执行成功。
默认 `fan_mode=unchanged` 保持现有风扇设置。
Linux 曲线是本项目的独立策略，原厂 AI 算法尚未复现。

## 安装到本机

```bash
git clone https://github.com/xhbii/deepcool-linux.git
cd deepcool-linux
sudo bash install-system.sh --user "$USER"
```

安装脚本会检查 Python/Tk；缺少 Tk 时通过 pacman 安装 `tk`。
也可以先手动安装依赖：

```bash
sudo pacman -S python tk
```

安装脚本把程序复制到 `/usr/lib/deepcool-linux`，添加 `/usr/bin/deepcool-linux`
和桌面菜单项，把 unit 写到 `/etc/systemd/system/deepcool-linux.service`，
随后启用并启动服务。原设置文件会保留；替换已有不同 unit 时会先备份。
设置存储在 `/var/lib/deepcool-linux/config.json`；本地 IPC socket 为
`/run/deepcool-linux/control.sock`。只有安装时指定用户和 root 可以通过 IPC 改设置。

后台服务以 root 读取只允许 root 访问的 CPU RAPL 能量计数器并写 HID。
使用 systemd 限制文件系统写入、系统配置修改和网络协议，只允许 Unix socket；
可执行代码安装在 root 拥有的系统目录。桌面界面以普通用户运行。
不需要放宽所有 HID 设备权限，也不需要更改 RAPL 的全局权限。

## 使用

从应用菜单启动 **DeepCool AK620 G2 数显控制**，或在桌面终端运行：

```bash
deepcool-linux gui
deepcool-linux status
deepcool-linux set --unit F --interval 1
deepcool-linux set --enabled false
deepcool-linux set --enabled true
# 恢复主板控制
deepcool-linux set --fan-mode motherboard
# 使用本项目的均衡温度曲线
deepcool-linux set --fan-mode balanced
# 手动调速（温度保护仍然生效）
deepcool-linux set --fan-mode manual --fan-pwm 60
# 自定义曲线：摄氏温度、PWM百分比
deepcool-linux set --fan-mode curve --fan-curve '[[30,30],[60,60],[80,100]]'
deepcool-linux set --screen-enabled false
deepcool-linux set --screen-enabled true
deepcool-linux set --temperature-alert true
```

`deepcool-linux doctor` 检查设备、CPU 传感器及服务状态，不向 USB 写数据。
`deepcool-linux sample` 读取一次实际 CPU 指标并输出编码的数据包，也不向 USB 写数据。
`sent_reports` 表示内核接受的完整遥测写入次数，并不证明实体屏幕显示已核对。
`status.fan.target_pwm` 是软件目标；`rpm` 是收到的反馈，超过 5 秒没有新反馈显示为空。
`written_without_ack` 表示命令已经写入，还没有设备确认应答。RPM 也不作为设置命令的 ACK。
关闭屏幕停止普通遥测，避免遥测重新点亮屏幕；暂停遥测和关闭屏幕均不停止风扇控制。

软件调速模式下，CPU 控制温度达到 80°C 或温度不可读时请求 100% PWM。
温度上升时立即提高目标，下降时每秒最多降低 5 个百分点。
即使显示间隔设为 10 秒，软件调速仍约每秒检查温度。
正常退出服务会请求恢复主板控制；`SIGKILL`、系统崩溃或 USB 断连时无法保证恢复。
设备独立看门狗尚未确认，不能把这些保护当作固件级保障。

```bash
systemctl status deepcool-linux.service
journalctl -u deepcool-linux.service -n 30 --no-pager
sudo systemctl restart deepcool-linux.service
sudo systemctl disable --now deepcool-linux.service
```

首次安装后查看 `status`：`state` 应为 `sending`，`sent_reports` 持续增加。
请同时核对实体散热器显示。`device_error` 表示没有成功写入，后台会重试。

## 升级

已经安装旧版时，在项目目录执行：

```bash
git pull --ff-only
sudo bash install-system.sh --user "$USER"
```

脚本复制新代码并重启服务，保留原配置，旧配置自动补齐新字段。
安装完成后重新打开面板。

## 数据来源与限制

- 温度来自 `hwmon`，优先 Tdie、CPU package 或 Tctl。Ryzen 处理器通常
  使用 `k10temp` 的 Tctl；Tctl 是 CPU 报告的控制温度。
- 使用率来自 `/proc/stat`，排除 guest 的重复计数，idle 包含 iowait。
- 功耗来自顶层 package RAPL 能量差分，或 `amd_energy/zenergy` 的 socket
  能量计数器；不累计 core 子域，按实际单调时钟间隔计算瓦数，并处理合理计数回绕。
  包功耗并不等于整机功耗，或厂商软件的其他 CPU 功耗口径。
- 频率取 `/proc/cpuinfo` 中最高的核心 MHz，与参考开源实现相同；它不是全核平均值。
- 温度不可读时停止发送，避免把错误的 0°C 当作真实温度。功耗或频率不可读时，
  面板显示“不可读”并注明对应硬件字段填 0；能量接口每 10 秒尝试重新发现。
- 只匹配 `3633:0029`。其他代际即使外观相同也不采用本协议；发现多个同型号设备时拒绝自动选择。

## 开发与只读预览

```bash
/usr/bin/python3 launcher.py doctor
/usr/bin/python3 launcher.py sample --unit C
/usr/bin/python3 -m unittest discover -s tests -v
```

没有 USB 权限也能预览面板：

```bash
mkdir -p /tmp/deepcool-preview-$UID
/usr/bin/python3 launcher.py run --dry-run \
  --config /tmp/deepcool-preview-$UID/config.json \
  --socket /tmp/deepcool-preview-$UID/control.sock
```

另一个桌面终端中运行 `launcher.py gui --socket /tmp/deepcool-preview-$UID/control.sock`。
预览不会发送 HID；普通用户通常不能读取 RAPL，因此功耗不可读。
若要保存预览设置，应先用本项目 `config.save({'controller_uid': os.getuid()}, path)`
创建配置；默认控制 UID 是 root。

遥测字段说明见 [协议文档](docs/protocol.md)，风扇功能进展见
[风扇控制说明](docs/fan-control.md)。Windows 原安装包和取证文件只保留在本地，
不随 GitHub 仓库或 Arch 包分发。

## Arch 包

先在项目根目录执行 `/usr/bin/python3 tools/build-release.py` 生成源码包。

`packaging/arch/PKGBUILD` 使用 `dist/` 中的独立源码包。源码包只包含本项目
程序、服务、桌面项、README、NOTICE 和 LICENSE，不包括本地取证或厂家程序。
按 `packaging/arch/README.md` 构建并使用 pacman 安装。

## 许可

GPL-3.0-or-later。详见 `LICENSE` 和 `NOTICE.md`。
