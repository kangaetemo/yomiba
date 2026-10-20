#!/usr/bin/env bash
# Yomiba — yeni Ubuntu 24.04 sunucusunun ilk kurulumu (root olarak, bir kez).
#
#   curl -fsSL https://raw.githubusercontent.com/kangaetemo/yomiba/main/deploy/kurulum.sh -o kurulum.sh
#   sudo bash kurulum.sh
#
# Yapar: sistem güncellemesi, Docker, güvenlik duvarı (22/80/443),
# otomatik güvenlik yamaları + gece yeniden başlatma, fail2ban,
# /srv/yomiba dizinleri, repo klonu ve gece yedeği cron'u.
# Yapmaz: .env doldurmak, DB taşımak, siteyi başlatmak (bkz. deploy/README.md).
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/kangaetemo/yomiba.git}"
BRANCH="${BRANCH:-main}"
ROOT=/srv/yomiba

[ "$(id -u)" -eq 0 ] || { echo "root olarak çalıştır: sudo bash kurulum.sh"; exit 1; }
. /etc/os-release
[ "$ID" = "ubuntu" ] || echo "UYARI: Ubuntu bekleniyordu, bulundu: $PRETTY_NAME"

echo "[1/7] sistem güncelleniyor..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get upgrade -yq
apt-get install -yq ca-certificates curl git ufw fail2ban unattended-upgrades sqlite3

echo "[2/7] Docker..."
if ! command -v docker >/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -yq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker

echo "[3/7] güvenlik duvarı..."
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable

echo "[4/7] otomatik güvenlik yamaları (gerekirse 04:30'da yeniden başlatma)..."
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
cat > /etc/apt/apt.conf.d/52yomiba-unattended <<'EOF'
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:30";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
EOF
systemctl enable --now unattended-upgrades fail2ban

echo "[5/7] dizinler..."
# Backend konteyneri uid 10001 olarak çalışır; DB ve kapaklar ona ait olmalı.
install -d -m 0700 -o 10001 -g 10001 "$ROOT/data" "$ROOT/data/backups"
install -d -m 0700 "$ROOT/backups"

echo "[6/7] repo..."
if [ ! -d "$ROOT/app/.git" ]; then
  git clone --branch "$BRANCH" "$REPO_URL" "$ROOT/app"
else
  git -C "$ROOT/app" pull --ff-only
fi
[ -f "$ROOT/app/deploy/.env" ] || install -m 0600 "$ROOT/app/deploy/.env.example" "$ROOT/app/deploy/.env"
chmod +x "$ROOT/app/deploy/"*.sh

echo "[7/7] gece yedeği (03:30)..."
cat > /etc/cron.d/yomiba-yedek <<EOF
30 3 * * * root $ROOT/app/deploy/yedekle.sh >> /var/log/yomiba-yedek.log 2>&1
EOF

cat <<EOF

Kurulum bitti. Sıradakiler (deploy/README.md):
  1) $ROOT/app/deploy/.env dosyasını doldur (ACME_EMAIL, AUTH_DEVICE_SECRET, ...).
  2) Railway'den alınan yomiba.db + covers/ -> $ROOT/data/ (sahibi 10001:10001).
  3) cd $ROOT/app/deploy && docker compose up -d --build
SSH: anahtarla girişi denedikten sonra /etc/ssh/sshd_config içinde
PasswordAuthentication no yapıp 'systemctl reload ssh' çalıştır.
EOF
