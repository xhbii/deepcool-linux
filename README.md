# DeepCool AK620 G2 · Arch Linux 数显控制器

为 **AK620 G2 DIGITAL NYX / AK620-GEN2，USB `3633:0029`**
编写的用户态 HID 控制程序。使用 Linux 已有的 `hidraw` 驱动，无需 Wine、
Windows 程序或第三方 Python 包。核心功能仅依赖 Arch 的 `python`，图形面板依赖 `tk`。

第一版支持 CPU 温度、使用率、封装功耗和最高核心频率；摄氏/华氏切换；
0.25–10 秒刷新；暂停/恢复发送；自动重新发现 USB 设备；中文桌面面板；
systemd 开机启动。用户关闭面板时，后台服务继续发送数据。

**暂不支持**风扇转速读取、风扇档位、AI 调速、主板同步、手动 PWM、
数显硬件开关和自定义温度警报。这些功能在 Windows 页面中存在，HID 命令尚未恢复。
暂停发送不会关闭屏幕，屏幕会保留最后的数值；恢复后重新更新。

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
```

`deepcool-linux doctor` 检查设备、CPU 传感器及服务状态，不向 USB 写数据。
`deepcool-linux sample` 读取一次实际 CPU 指标并输出编码的数据包，也不向 USB 写数据。
`sent_reports` 表示内核接受的完整写入次数，并不证明实体屏幕显示已核对。

```bash
systemctl status deepcool-linux.service
journalctl -u deepcool-linux.service -n 30 --no-pager
sudo systemctl restart deepcool-linux.service
sudo systemctl disable --now deepcool-linux.service
```

首次安装后查看 `status`：`state` 应为 `sending`，`sent_reports` 持续增加。
请同时核对实体散热器显示。`device_error` 表示没有成功写入，后台会重试。

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
