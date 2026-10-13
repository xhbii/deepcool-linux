#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
    echo '请运行：sudo bash install-system.sh --user "$USER"' >&2
    exit 1
fi
desktop_user=${SUDO_USER:-}
if [[ ${1:-} == --user && $# == 2 ]]; then
    desktop_user=$2
elif [[ $# != 0 ]]; then
    echo '用法：sudo bash install-system.sh --user 用户名' >&2
    exit 1
fi
if [[ -z $desktop_user || $desktop_user == root ]]; then
    echo '请用 --user 指定使用图形界面的普通用户。' >&2
    exit 1
fi
desktop_uid=$(id -u "$desktop_user")
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if ! /usr/bin/python3 -c 'import tkinter' 2>/dev/null; then
    echo '安装图形界面所需的 Arch tk 包。'
    pacman -S --needed --noconfirm tk
    /usr/bin/python3 -c 'import tkinter'
fi
echo "安装目录：/usr/lib/deepcool-linux；桌面控制用户：$desktop_user ($desktop_uid)"
echo '安装 root 系统服务以读取 RAPL 和访问 USB HID；控制界面以普通用户运行。'
install -d -m 0755 /usr/lib/deepcool-linux/deepcool_linux
for module in __init__ __main__ cli config daemon gui hardware protocol sensors; do
    install -m 0644 "$project_dir/deepcool_linux/$module.py" "/usr/lib/deepcool-linux/deepcool_linux/$module.py"
done
install -m 0644 "$project_dir/launcher.py" /usr/lib/deepcool-linux/launcher.py
install -m 0644 "$project_dir/service-launcher.py" /usr/lib/deepcool-linux/service-launcher.py
install -m 0644 "$project_dir/LICENSE" /usr/lib/deepcool-linux/LICENSE
install -m 0644 "$project_dir/NOTICE.md" /usr/lib/deepcool-linux/NOTICE.md
install -m 0644 "$project_dir/README.md" /usr/lib/deepcool-linux/README.md
install -d -m 0755 /usr/bin /usr/share/applications /etc/systemd/system
wrapper_tmp=$(mktemp)
trap 'rm -f -- "$wrapper_tmp"' EXIT
cat > "$wrapper_tmp" <<'EOF'
#!/bin/sh
exec /usr/bin/python3 -I /usr/lib/deepcool-linux/service-launcher-cli.py "$@"
EOF
install -m 0755 "$wrapper_tmp" /usr/bin/deepcool-linux
install -m 0644 "$project_dir/service-launcher-cli.py" /usr/lib/deepcool-linux/service-launcher-cli.py
install -m 0644 "$project_dir/packaging/deepcool-linux.desktop" /usr/share/applications/deepcool-linux.desktop
service_path=/etc/systemd/system/deepcool-linux.service
if [[ -f $service_path ]] && ! cmp -s "$project_dir/packaging/deepcool-linux.service" "$service_path"; then
    cp --preserve=mode -- "$service_path" "$service_path.backup.$(date +%s)"
fi
install -m 0644 "$project_dir/packaging/deepcool-linux.service" "$service_path"
install -d -m 0700 /var/lib/deepcool-linux
if [[ ! -f /var/lib/deepcool-linux/config.json ]]; then
    /usr/bin/python3 -I - "$desktop_uid" <<'PY'
import sys
sys.path.insert(0, '/usr/lib/deepcool-linux')
from deepcool_linux.config import save
save({'controller_uid': int(sys.argv[1])})
PY
else
    /usr/bin/python3 -I - "$desktop_uid" <<'PY'
import sys
sys.path.insert(0, '/usr/lib/deepcool-linux')
from deepcool_linux.config import load
cfg=load()
if cfg['controller_uid'] != int(sys.argv[1]):
    raise SystemExit('现有配置指定其他控制用户，请先核对 /var/lib/deepcool-linux/config.json')
PY
fi
systemctl daemon-reload
systemctl enable deepcool-linux.service
systemctl restart deepcool-linux.service
sleep 2
/usr/bin/deepcool-linux status
echo '安装完成。桌面应用菜单打开 DeepCool AK620 G2，或运行 deepcool-linux gui。'
