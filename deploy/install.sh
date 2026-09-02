#!/bin/bash
# Install the monitoring demo on Amazon Linux 2023 (ARM64 / t4g.nano).
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "run as root: sudo ./deploy/install.sh" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INSTALL_DIR="${DEMO_INSTALL_DIR:-/opt/demo-target}"
STATE_DIR="/var/lib/demo-faults"
DISK_IMG="${STATE_DIR}/disk.img"
DISK_MOUNT="/mnt/demo-disk"
SWAP_FILE="/var/swapfile"
TOKEN_DIR="/etc/demo-target"
TOKEN_PATH="${TOKEN_DIR}/token"

echo "==> installing packages"
dnf install -y python3 python3-pip python3-venv nginx stress-ng util-linux e2fsprogs curl rsync
dnf install -y awscli || dnf install -y aws-cli || true

echo "==> creating demo user"
if ! id -u demo >/dev/null 2>&1; then
  useradd --system --home "$INSTALL_DIR" --shell /sbin/nologin demo
fi

echo "==> installing application to ${INSTALL_DIR}"
mkdir -p "$INSTALL_DIR"
if [[ "$REPO_DIR" != "$INSTALL_DIR" ]]; then
  rsync -a --delete \
    --exclude '.venv' \
    --exclude '__pycache__' \
    --exclude '.pytest_cache' \
    --exclude '.git' \
    "$REPO_DIR/" "$INSTALL_DIR/"
fi
python3 -m venv "${INSTALL_DIR}/.venv"
"${INSTALL_DIR}/.venv/bin/pip" install --upgrade pip
"${INSTALL_DIR}/.venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"
chmod 755 "${INSTALL_DIR}/deploy/bin/demo-fault-ctl" "${INSTALL_DIR}/deploy/bin/demo-probe.sh"
chown -R demo:demo "$INSTALL_DIR"

echo "==> state directory and token"
mkdir -p "$STATE_DIR" "$TOKEN_DIR" "$DISK_MOUNT"
if [[ ! -s "$TOKEN_PATH" ]]; then
  python3 - <<'PY' > "$TOKEN_PATH"
import secrets
print(secrets.token_urlsafe(24))
PY
fi
chmod 640 "$TOKEN_PATH"
chown root:demo "$TOKEN_PATH"
touch "${STATE_DIR}/state.json"
chown -R demo:demo "$STATE_DIR"

echo "==> 512 MiB disk-backed swap (nano / zram safety)"
if ! swapon --show=NAME | awk 'NR>1 {print $1}' | grep -qx "$SWAP_FILE"; then
  if [[ ! -f "$SWAP_FILE" ]]; then
    fallocate -l 512M "$SWAP_FILE"
    chmod 600 "$SWAP_FILE"
    mkswap "$SWAP_FILE"
  fi
  swapon "$SWAP_FILE" || true
fi
if ! grep -qE "^${SWAP_FILE}[[:space:]]" /etc/fstab; then
  echo "${SWAP_FILE} none swap sw 0 0" >> /etc/fstab
fi

echo "==> isolated 256 MiB loop disk at ${DISK_MOUNT}"
if [[ ! -f "$DISK_IMG" ]]; then
  fallocate -l 256M "$DISK_IMG"
  mkfs.ext4 -F "$DISK_IMG"
fi
if ! grep -qE "^${DISK_IMG}[[:space:]]" /etc/fstab; then
  echo "${DISK_IMG} ${DISK_MOUNT} ext4 loop,defaults,nofail 0 0" >> /etc/fstab
fi
mountpoint -q "$DISK_MOUNT" || mount "$DISK_MOUNT"
chown demo:demo "$DISK_MOUNT"

echo "==> sudoers, nginx, systemd"
install -m 440 "${INSTALL_DIR}/deploy/sudoers/demo" /etc/sudoers.d/demo
visudo -cf /etc/sudoers.d/demo
install -m 644 "${INSTALL_DIR}/deploy/nginx/demo-target.conf" /etc/nginx/conf.d/demo-target.conf
if [[ -f /etc/nginx/nginx.conf ]] && grep -q "default_server" /etc/nginx/nginx.conf; then
  # Keep the packaged default from stealing :80 when possible.
  sed -i 's/listen[[:space:]]\+80;/listen 80;/g' /etc/nginx/nginx.conf || true
fi
for unit in demo-controller.service demo-target.service demo-probe.service demo-probe.timer; do
  install -m 644 "${INSTALL_DIR}/deploy/systemd/${unit}" "/etc/systemd/system/${unit}"
done
systemctl disable --now demo-watchdog.timer 2>/dev/null || true
systemctl daemon-reload
nginx -t
systemctl enable --now nginx.service
systemctl enable --now demo-target.service demo-controller.service
systemctl enable --now demo-probe.timer

echo
echo "Installed."
echo "  Dashboard:  http://<host>:8080/?token=$(cat "$TOKEN_PATH")"
echo "  Target:     http://<host>/health"
echo "  Token file: ${TOKEN_PATH}"
echo
echo "Measure idle memory before setting DemoApp-Memory-High:"
echo "  grep -E 'MemTotal|MemAvailable' /proc/meminfo"
echo "  See docs/safety.md"
