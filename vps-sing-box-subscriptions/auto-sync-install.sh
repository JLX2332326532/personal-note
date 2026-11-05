#!/usr/bin/env bash
# Sing-Box-Plus v4.8.0: auto-refresh three existing subscription URLs.
# Does NOT change Sing-Box-Plus, ports, Caddy config, URL, or token.
set -Eeuo pipefail

if (( EUID != 0 )); then
  echo '请使用 root 运行此安装脚本' >&2
  exit 1
fi

for f in /root/sing-box-plus.sh /opt/sing-box/ports.env /opt/sing-box/config.json /root/sub-token.txt /root/subscription-url.txt; do
  if [[ ! -s "$f" ]]; then echo "缺少必要文件：$f。请先完成 Sing-Box-Plus 和 HTTPS 订阅部署。" >&2; exit 1; fi
done
if [[ ! -d /srv/sbp-sub ]]; then
  echo '缺少订阅目录 /srv/sbp-sub，请先完成 HTTPS 订阅部署' >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  apt-get update
  apt-get install -y python3
fi
if ! python3 -c 'import yaml' >/dev/null 2>&1 || ! command -v flock >/dev/null || ! command -v jq >/dev/null; then
  apt-get update
  apt-get install -y python3-yaml jq util-linux
fi

install -d -m 700 /usr/local/lib/sbp-sub-sync
cat > /usr/local/lib/sbp-sub-sync/converter.py <<'PY_CONVERTER'
#!/usr/bin/env python3
import base64
import json
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
import yaml

NODES = Path('/root/nodes.txt')
TOKEN = Path('/root/sub-token.txt')
WEB = Path('/srv/sbp-sub')

def decoded64(s):
    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4)).decode('utf-8')

def istrue(value):
    return str(value).lower() in ('1', 'true', 'yes')

def convert(link):
    if link.startswith('vmess://'):
        data = json.loads(decoded64(link[8:].split('#', 1)[0]))
        p = dict(name=data.get('ps', 'vmess'), type='vmess', server=data['add'],
                 port=int(data['port']), uuid=data['id'], alterId=int(data.get('aid', 0)),
                 cipher='auto', udp=True)
        if data.get('net') == 'ws':
            p['network'] = 'ws'
            ws = {'path': data.get('path') or '/'}
            if data.get('host'):
                ws['headers'] = {'Host': data['host']}
            p['ws-opts'] = ws
        if data.get('tls') == 'tls':
            p['tls'] = True
            if data.get('sni'):
                p['servername'] = data['sni']
        return p
    u = urlsplit(link)
    q = {k: v[-1] for k, v in parse_qs(u.query, keep_blank_values=True).items()}
    scheme = u.scheme.lower()
    name = unquote(u.fragment) or scheme
    p = dict(name=name, type=scheme, server=u.hostname, port=u.port, udp=True)
    if scheme in ('vless', 'trojan'):
        p['uuid' if scheme == 'vless' else 'password'] = unquote(u.username or '')
        if q.get('security') in ('reality', 'tls'):
            p['tls'] = True
        if q.get('sni'):
            p['servername' if scheme == 'vless' else 'sni'] = q['sni']
        if q.get('fp'):
            p['client-fingerprint'] = q['fp']
        if q.get('security') == 'reality':
            p['reality-opts'] = {'public-key': q['pbk'], 'short-id': q.get('sid', '')}
        if scheme == 'vless' and q.get('flow'):
            p['flow'] = q['flow']
        if q.get('type') == 'grpc':
            p['network'] = 'grpc'
            p['grpc-opts'] = {'grpc-service-name': q.get('serviceName', '')}
    elif scheme in ('hy2', 'hysteria2'):
        p['type'] = 'hysteria2'
        p['password'] = unquote(u.username or '')
        if q.get('sni'):
            p['sni'] = q['sni']
        if istrue(q.get('insecure', '0')) or istrue(q.get('allowInsecure', '0')):
            p['skip-cert-verify'] = True
        if q.get('alpn'):
            p['alpn'] = q['alpn'].split(',')
        if q.get('obfs'):
            p['obfs'] = q['obfs']
            p['obfs-password'] = q.get('obfs-password', '')
    elif scheme == 'ss':
        raw = unquote(u.username or '')
        if ':' not in raw:
            raw = decoded64(raw)
        cipher, password = raw.split(':', 1)
        p['cipher'], p['password'] = cipher, password
    elif scheme == 'tuic':
        p['uuid'] = unquote(u.username or '')
        p['password'] = unquote(u.password or '')
        if q.get('sni'):
            p['sni'] = q['sni']
        if q.get('alpn'):
            p['alpn'] = q['alpn'].split(',')
        if q.get('congestion_control'):
            p['congestion-controller'] = q['congestion_control']
        if istrue(q.get('insecure', '0')) or istrue(q.get('allowInsecure', '0')):
            p['skip-cert-verify'] = True
    elif scheme == 'anytls':
        p['password'] = unquote(u.username or '')
        if q.get('sni'):
            p['sni'] = q['sni']
        if istrue(q.get('insecure', '0')):
            p['skip-cert-verify'] = True
    else:
        raise ValueError('unsupported scheme: ' + scheme)
    if not p['server'] or not p['port']:
        raise ValueError('missing server or port: ' + scheme)
    return p


def main():
    if not NODES.is_file():
        sys.exit('缺少 /root/nodes.txt')
    if not TOKEN.is_file() or not WEB.is_dir():
        sys.exit('尚未部署Caddy订阅服务：缺少 /root/sub-token.txt 或 /srv/sbp-sub')
    token = TOKEN.read_text().strip()
    if len(token) < 32 or not all(ch in '0123456789abcdef' for ch in token):
        sys.exit('订阅Token不符合预期；为安全起见终止')
    links = [l.strip() for l in NODES.read_text().splitlines() if l.strip()]
    if len(links) != 20:
        sys.exit('节点数量不是20，实际为：' + str(len(links)))
    proxies = [convert(u) for u in links]
    names = [p['name'] for p in proxies]
    if len(set(names)) != len(names):
        sys.exit('节点名重复，无法生成Clash配置')
    config = {
        'mixed-port': 7890,
        'allow-lan': False,
        'mode': 'rule',
        'log-level': 'warning',
        'proxies': proxies,
        'proxy-groups': [
            {'name': '节点选择', 'type': 'select', 'proxies': ['自动选择', 'DIRECT'] + names},
            {'name': '自动选择', 'type': 'url-test', 'proxies': names,
             'url': 'https://www.gstatic.com/generate_204', 'interval': 300, 'tolerance': 50},
        ],
        'rules': ['MATCH,节点选择'],
    }
    raw = NODES.read_bytes()
    sub = base64.b64encode(raw)
    items = {
        f'{token}.txt': sub,
        f'{token}.shadowrocket.txt': sub,
        f'{token}.clash.yaml': yaml.safe_dump(
            config, allow_unicode=True, sort_keys=False, width=120).encode(),
    }
    for name, data in items.items():
        temp = WEB / ('.tmp-' + name)
        temp.write_bytes(data)
        os.chmod(temp, 0o644)
        os.replace(temp, WEB / name)
    print('成功：20个节点，生成三种订阅文件')
    urlfile = Path('/root/subscription-url.txt')
    if urlfile.is_file() and urlfile.read_text().strip().endswith(f'/{token}.txt'):
        original = urlfile.read_text().strip()
        prefix = original[:-4]
        print('v2rayN:        ' + original)
        print('Clash/Mihomo:  ' + prefix + '.clash.yaml')
        print('Shadowrocket:  ' + prefix + '.shadowrocket.txt')
    else:
        print('订阅文件已生成；原HTTPS链接信息缺失，请核实Caddy域名后组合URL')

if __name__ == '__main__':
    main()
PY_CONVERTER
chmod 600 /usr/local/lib/sbp-sub-sync/converter.py

cat > /usr/local/sbin/sbp-sub-sync <<'SYNC_SCRIPT'
#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
exec 9>/run/sbp-sub-sync.lock
flock -n 9 || exit 0

SOURCE=/root/sing-box-plus.sh
PORTS=/opt/sing-box/ports.env
CONFIG=/opt/sing-box/config.json
TOKEN_FILE=/root/sub-token.txt
WEB_DIR=/srv/sbp-sub
CONVERTER_DIR=/usr/local/lib/sbp-sub-sync

for f in "$SOURCE" "$PORTS" "$CONFIG" "$TOKEN_FILE"; do
  test -s "$f" || { echo "缺少文件 $f" >&2; exit 1; }
done

# Port files are written before config/restart. Avoid publishing a premature snapshot.
sleep 6
systemctl is-active --quiet sing-box.service || { echo 'Sing-Box 服务未运行；不更新订阅' >&2; exit 1; }

# Ensure ports.env (20 entries) and config.json (20 active listeners) agree.
mapfile -t ENV_PORTS < <(awk -F= '/^PORT_[A-Z0-9_]+=[0-9]+$/ {print $2}' "$PORTS" | sort -n)
mapfile -t CFG_PORTS < <(jq -er '.inbounds[].listen_port' "$CONFIG" | sort -n)
if [[ "${#ENV_PORTS[@]}" -ne 20 || "${#CFG_PORTS[@]}" -ne 20 || "${ENV_PORTS[*]}" != "${CFG_PORTS[*]}" ]]; then
  echo '端口文件与运行配置不一致；暂不发布，定时器会再次检查' >&2
  exit 1
fi

tmp=$(mktemp /root/.sbp-nodes.XXXXXX)
trap 'rm -f "$tmp"' EXIT

# Remove only the interactive stty line; use the upstream script's menu 2.
# Never send credential-bearing output to journal/syslog.
if ! (printf '2\n' | SBP_SKIP_DEPS=1 bash <(
  sed '/^[[:space:]]*stty erase \^H/d' "$SOURCE"
) | awk '
  /^[[:space:]]*(vless|trojan|hy2|vmess|ss|tuic|anytls):\/\// {
    sub(/^[[:space:]]+/, "")
    if (++count <= 20) print
  }
' > "$tmp"); then
  echo '无法从原脚本提取节点，保留已有订阅' >&2
  exit 1
fi

# Parse all 20 links and verify their ports match the generated config.
python3 - "$tmp" "$CONVERTER_DIR" "$CONFIG" <<'PY_VALIDATE'
import json, ipaddress, sys
from pathlib import Path
sys.path.insert(0, sys.argv[2])
from converter import convert
links = [s.strip() for s in Path(sys.argv[1]).read_text().splitlines() if s.strip()]
assert len(links) == 20, f'只提取到 {len(links)} 个节点'
proxies = [convert(link) for link in links]
assert len({p['name'] for p in proxies}) == 20, '节点名称重复'
assert len({p['port'] for p in proxies}) == 20, '端口重复'
servers = {p['server'] for p in proxies}
assert len(servers) == 1 and ipaddress.ip_address(next(iter(servers))).is_global, '节点地址不是一致的公网 IP'
config = json.loads(Path(sys.argv[3]).read_text())
assert {p['port'] for p in proxies} == {p['listen_port'] for p in config['inbounds']}, '节点端口与 Sing-Box 配置不一致'
PY_VALIDATE

token=$(<"$TOKEN_FILE")
stamp=/root/.sbp-sub.last.sha256
current_hash=$(sha256sum "$tmp" | awk '{print $1}')
if [[ -s "$stamp" && "$(cat "$stamp")" == "$current_hash" ]] \
   && [[ -s "$WEB_DIR/$token.txt" ]] \
   && [[ -s "$WEB_DIR/$token.clash.yaml" ]] \
   && [[ -s "$WEB_DIR/$token.shadowrocket.txt" ]]; then
  echo '检查完成：20 个节点未变化，订阅无需更新'
  exit 0
fi

install -m 600 "$tmp" /root/nodes.txt
python3 "$CONVERTER_DIR/converter.py" >/dev/null
# Record successful publish only after all three outputs were written.
printf '%s\n' "$current_hash" > "${stamp}.tmp"
mv -f "${stamp}.tmp" "$stamp"
# A successful converter invocation atomically replaces each published file.
echo '成功：三种订阅已经更新（20 节点，URL/Token 保持不变）'
SYNC_SCRIPT
chmod 700 /usr/local/sbin/sbp-sub-sync

cat > /etc/systemd/system/sbp-sub-sync.service <<'SERVICE_UNIT'
[Unit]
Description=Regenerate Sing-Box-Plus subscriptions after port changes
After=network-online.target sing-box.service

[Service]
Type=oneshot
User=root
ExecStart=/usr/local/sbin/sbp-sub-sync
TimeoutStartSec=90
SERVICE_UNIT

cat > /etc/systemd/system/sbp-sub-sync.path <<'PATH_UNIT'
[Unit]
Description=Watch Sing-Box-Plus port changes

[Path]
PathChanged=/opt/sing-box/ports.env
Unit=sbp-sub-sync.service

[Install]
WantedBy=multi-user.target
PATH_UNIT

cat > /etc/systemd/system/sbp-sub-sync.timer <<'TIMER_UNIT'
[Unit]
Description=Periodic fallback for Sing-Box-Plus subscription sync

[Timer]
OnBootSec=45s
OnUnitInactiveSec=1min
AccuracySec=5s
Unit=sbp-sub-sync.service

[Install]
WantedBy=timers.target
TIMER_UNIT

systemctl daemon-reload
# Run once before enabling the watcher/timer, to avoid a first-run race.
if systemctl start sbp-sub-sync.service; then
  systemctl enable --now sbp-sub-sync.path sbp-sub-sync.timer
  echo '已安装并启用自动同步。'
  echo '订阅地址不变；查看三条地址：'
  python3 - <<'PY_URLS'
from pathlib import Path
url = Path('/root/subscription-url.txt').read_text().strip()
if not url.endswith('.txt'): raise SystemExit('订阅网址不是 .txt 结尾，请检查原部署')
prefix = url[:-4]
print('v2rayN:       ', url)
print('Clash/Mihomo: ', prefix + '.clash.yaml')
print('Shadowrocket: ', prefix + '.shadowrocket.txt')
PY_URLS
else
  echo '首次同步失败，监控尚未启用。查看：journalctl -u sbp-sub-sync.service -n 40 --no-pager' >&2
  exit 1
fi