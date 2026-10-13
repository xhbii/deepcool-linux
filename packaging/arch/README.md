# Arch 包构建

直接安装脚本与 pacman 包安装任选其一，不需要同时安装。

项目根目录中重新生成源码包：

```bash
/usr/bin/python3 tools/build-release.py
cd packaging/arch
makepkg -s
sudo pacman -U deepcool-ak620g2-linux-0.1.0-1-any.pkg.tar.zst
sudo pacman -S --needed tk
sudo deepcool-linux authorize-user "$USER"
sudo systemctl enable --now deepcool-linux.service
deepcool-linux gui
```

只编译打包无需管理员权限，安装使用 pacman。PKGBUILD 的 check 阶段运行协议、
传感器、权限和输入验证测试。安装包不会自动向设备写入；启动服务后开始发送遥测。
后台代码安装到 `/usr/lib/deepcool-linux`，unit 安装到 `/usr/lib/systemd/system`。

停止并卸载：

```bash
sudo systemctl disable --now deepcool-linux.service
sudo pacman -R deepcool-ak620g2-linux
```

运行设置保存在 `/var/lib/deepcool-linux`，卸载包后保留。
源码 tar.gz 和 Arch 包均不含厂商安装包、提取的 Windows 程序或本机传感器资料。
