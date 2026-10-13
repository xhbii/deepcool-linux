# 来源与许可

本项目的 Linux 实现、控制面板和服务是新编写的代码。遥测字段依据
Nortank12/deepcool-digital-linux 的 LQ / AK G2 协议记录，以 GPL-3.0-or-later 发布。
该仓库本次核查版本：`8ab8338460b0d4c3d77723feae95f66e4251f61c`。

- 项目：https://github.com/Nortank12/deepcool-digital-linux
- 字段表：`device-list/tables/lq-series.md`
- 发送实现：`src/devices/lq_series.rs`
- 字段解释见 `docs/protocol.md`；GPL 许可副本为项目根目录的 `LICENSE`。
- 未复制或移植 DeepCool 专有程序的实现、UI 资源或原生 DLL。

`analysis/windows/` 仅为用户提供的安装包的本地研究产物，包含专有文件，
不属于 GPL 授权源码，不随源码包或 Arch 包分发。
DeepCool 商标及软件的权利属于各自权利人。

验证范围：软件测试与本地静态取证不等于实体屏幕显示验证。
本项目的数显功能已由设备持有者验证，软件测试覆盖数据包与传感器计算。
风扇功能的当前状态见 `docs/fan-control.md`。
