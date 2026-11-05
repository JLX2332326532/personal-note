#!/usr/bin/env bash
# Fresh Debian 13 VPS deployment. Review scripts before execution.
set -Eeuo pipefail
umask 077
test "$EUID" -eq 0 || { echo "Run as root" >&2; exit 1; }
grep -q '^VERSION_ID="13"\|^VERSION_ID=13' /etc/os-release || { echo "Requires Debian 13" >&2; exit 1; }
BASE=https://raw.githubusercontent.com/JLX2332326532/personal-note/main/vps-sing-box-subscriptions
UPSTREAM=https://raw.githubusercontent.com/Alvin9999-newpac/Sing-Box-Plus/main/sing-box-plus.sh
apt-get -o DPkg::Lock::Timeout=300 update
apt-get -o DPkg::Lock::Timeout=300 install -y curl wget jq python3 python3-yaml ca-certificates openssl tar unzip xz-utils util-linux caddy

if test ! -s /root/sing-box-plus.sh; then
  curl -fL --retry 3 "$UPSTREAM" -o /root/sing-box-plus.sh
  chmod 700 /root/sing-box-plus.sh
fi

if test ! -s /opt/sing-box/config.json; then
  echo "Installing upstream Sing-Box-Plus; any error is logged in /root/sbp-deploy.log (secret)."
  printf '1\n' | SBP_SKIP_DEPS=1 bash <(sed '/^[[:space:]]*stty erase \^H/d' /root/sing-box-plus.sh) > /root/sbp-deploy.log 2>&1 || {
    chmod 600 /root/sbp-deploy.log
    echo "Installation failed, see /root/sbp-deploy.log" >&2
    exit 1
  }
  chmod 600 /root/sbp-deploy.log
fi

systemctl is-active --quiet sing-box.service || { echo "Sing-Box not running" >&2; exit 1; }
if test -s /etc/caddy/Caddyfile &&
   ! grep -q '# managed-by-sbp-sub' /etc/caddy/Caddyfile &&
   ! grep -q 'respond "Hello, world!"' /etc/caddy/Caddyfile; then
  echo "Refusing to overwrite existing custom Caddyfile" >&2
  exit 1
fi

if test ! -s /root/sub-token.txt; then openssl rand -hex 24 > /root/sub-token.txt; fi
chmod 600 /root/sub-token.txt
IP=$(curl -4fsS --connect-timeout 10 https://ipv4.icanhazip.com | tr -d '\r\n')
python3 - "$IP" <<'PY'
import ipaddress,sys
assert ipaddress.ip_address(sys.argv[1]).is_global, "Public IPv4 required"
PY
HOST=$(printf '%s' "$IP" | tr . -).sslip.io
if test -n "${SUB_DOMAIN:-}"; then HOST="$SUB_DOMAIN"; fi
case "$HOST" in *[!a-zA-Z0-9.-]*|'') echo "Invalid hostname" >&2; exit 1;; esac
install -d -m 755 /srv/sbp-sub
TOKEN=$(cat /root/sub-token.txt)
printf 'https://%s/%s.txt\n' "$HOST" "$TOKEN" >/root/subscription-url.txt
chmod 600 /root/subscription-url.txt
cp -a /etc/caddy/Caddyfile "/etc/caddy/Caddyfile.bak.$(date +%s)"
cat >/etc/caddy/Caddyfile <<EOF
# managed-by-sbp-sub
$HOST {
    root * /srv/sbp-sub
    header Cache-Control "no-store"
    file_server
}
EOF
caddy validate --config /etc/caddy/Caddyfile
systemctl enable --now caddy
systemctl reload caddy
if command -v ufw >/dev/null && ufw status | grep -q 'Status: active'; then
  ufw allow 80/tcp
  ufw allow 443/tcp
fi
curl -fL --retry 3 "$BASE/auto-sync-install.sh" -o /root/sbp-sub-auto-install.sh
chmod 700 /root/sbp-sub-auto-install.sh
bash /root/sbp-sub-auto-install.sh
echo "Allow inbound TCP 80/443 and all node ports in provider firewall."
echo "Private subscriptions:"
cat /root/subscription-url.txt
