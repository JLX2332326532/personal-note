#!/usr/bin/env python3
"""SBP manager v1.0.0: local Debian 13 relay and optional landing exit."""
import base64
import copy
import errno
import fcntl
import getpass
import ipaddress
import json
import os
import random
import re
import secrets
import shutil
import socket
import subprocess as sp
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

VERSION = '1.0.0'
URL = 'https://raw.githubusercontent.com/JLX2332326532/personal-note/main/vps-sing-box-subscriptions/'
BASE = Path('/opt/sing-box')
LAND = Path('/opt/sing-box-landing')
STAGE = Path('/root/sbp-landing')
UP = Path('/root/sing-box-plus.sh')
UNIT = Path('/etc/systemd/system/sing-box-landing.service')
TOKEN = Path('/root/sub-token.txt')
SUBURL = Path('/root/subscription-url.txt')
NODES = Path('/root/nodes.txt')
WEB = Path('/srv/sbp-sub')
STAMP = Path('/root/.sbp-sub.last.sha256')
BACKUPS = Path('/root/sbp-backups')
SYNC = 'sbp-sub-sync.service'
WATCH = ('sbp-sub-sync.path', 'sbp-sub-sync.timer')
SERVICES = ('sing-box.service', 'sing-box-landing.service', 'caddy.service')
SUFFIXES = ('.txt', '.clash.yaml', '.shadowrocket.txt', '.shadowrocket.conf', '.v2rayn-routing.json')
PORT_RE = re.compile(r'(?m)^(PORT_[A-Z0-9_]+)=(\d+)$')
SCHEME_RE = re.compile(r'(?m)^[ \t]*((?:vless|trojan|hy2|hysteria2|vmess|ss|tuic|anytls)://[^\s]+)')
SNAP_PATHS = (
    BASE, LAND, STAGE, UP, TOKEN, SUBURL, NODES, STAMP, WEB,
    Path('/etc/caddy/Caddyfile'), UNIT, Path('/etc/systemd/system/sing-box.service'),
    Path('/usr/local/sbin/sbp-sub-sync'), Path('/usr/local/lib/sbp-sub-sync'),
    *(Path('/etc/systemd/system') / u for u in (SYNC, *WATCH)),
)
SNAP_UNITS = (*SERVICES, *WATCH)
REMOTE_SCRIPT = r"""set -eu
umask 077
stage="$1"
unit=/etc/systemd/system/sing-box-landing-exit.service
dir=/opt/sing-box-landing-exit
bin=/usr/local/bin/sing-box-landing-exit
test ! -e "$unit" && test ! -e "$dir" && test ! -e "$bin" || {
    echo 'Existing landing-exit installation; refusing overwrite.' >&2
    exit 1
}
test -x "$stage/sing-box"
"$stage/sing-box" check -c "$stage/server.json"
install -d -m 700 "$dir"
rollback() {
    systemctl disable --now sing-box-landing-exit.service >/dev/null 2>&1 || true
    rm -f "$unit" "$bin"
    rm -rf "$dir"
    systemctl daemon-reload || true
}
trap rollback EXIT
install -m 755 "$stage/sing-box" "$bin"
install -m 600 "$stage/server.json" "$dir/config.json"
cat > "$unit" <<'EOF'
[Unit]
Description=Sing-Box Landing Exit
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/sing-box-landing-exit
ExecStart=/usr/local/bin/sing-box-landing-exit run -c /opt/sing-box-landing-exit/config.json
Restart=on-failure
RestartSec=3
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF
chmod 644 "$unit"
systemctl daemon-reload
systemctl enable --now sing-box-landing-exit.service
sleep 2
systemctl is-active --quiet sing-box-landing-exit.service
trap - EXIT
echo 'Landing exit service installed.'
"""

class Failure(RuntimeError):
    pass

def need(condition, message):
    if not condition:
        raise Failure(message)

def run(args, *, ok=True, quiet=False, capture=False, timeout=120, stdin=None):
    p = sp.run([str(x) for x in args], text=True, input=stdin, timeout=timeout,
               stdout=sp.PIPE if capture or quiet else None,
               stderr=sp.PIPE if capture or quiet else None)
    if ok and p.returncode:
        raise Failure(f'命令失败：{Path(str(args[0])).name}（退出码 {p.returncode}）')
    return p.stdout.strip() if capture else p.returncode

def system(*args, ok=True, quiet=False):
    return run(['systemctl', *args], ok=ok, quiet=quiet, timeout=180)

def active(unit):
    return system('is-active', '--quiet', unit, ok=False, quiet=True) == 0

def enabled(unit):
    return system('is-enabled', '--quiet', unit, ok=False, quiet=True) == 0

def confirm(msg):
    return input(msg + ' [y/N]: ').strip().lower() in ('y', 'yes')

def ask(msg, default=None):
    value = input(msg + (f' [{default}]' if default is not None else '') + ': ').strip()
    return value or default

def ip4(value):
    try:
        addr = ipaddress.IPv4Address(value)
        need(addr.is_global, '需要真实公网 IPv4。')
        return str(addr)
    except ValueError:
        raise Failure('IPv4 格式错误，请检查是否有多余字符。') from None

def portnum(value):
    try:
        n = int(value)
        need(1 <= n <= 65535, '端口超出范围。')
        return n
    except (ValueError, TypeError):
        raise Failure('端口必须为整数。') from None

def binary():
    b = shutil.which('sing-box')
    need(b, '未安装基础 Sing-Box，请先使用菜单1。')
    return b

def atomic(path, data, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.sbpm-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data if isinstance(data, bytes) else data.encode())
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)

def dump(path, value):
    atomic(path, json.dumps(value, indent=2, ensure_ascii=False) + '\n')

def readj(path):
    return json.loads(Path(path).read_text())

def check(path, b=None):
    need(run([b or binary(), 'check', '-c', path], quiet=True, ok=False) == 0,
         f'Sing-Box 配置校验失败：{path}；未发布新订阅。')

def download(name, dest, *, python=False):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.download-', dir=dest.parent)
    os.close(fd)
    try:
        run(['curl', '-fLsS', '--retry', '2', '--connect-timeout', '15', URL+name, '-o', tmp])
        if python:
            compile(Path(tmp).read_text(), name, 'exec')
        else:
            run(['bash', '-n', tmp])
        os.chmod(tmp, 0o700)
        os.replace(tmp, dest)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return dest

def landing_present():
    return LAND.exists() or UNIT.exists()

def need_base(require_active=True):
    need(BASE.joinpath('config.json').is_file() and BASE.joinpath('ports.env').is_file()
         and UP.is_file(), '基础20节点未安装。')
    if require_active:
        need(active(SERVICES[0]), '基础服务未运行，请使用菜单3重启。')

def need_land():
    need(LAND.joinpath('config.json').is_file() and LAND.joinpath('nodes.txt').is_file()
         and UNIT.is_file(), '落地服务文件缺失；先安装或恢复配置。')

def links_from_upstream(option=2):
    need(UP.is_file(), '缺少 /root/sing-box-plus.sh。')
    cmd = r"""set -o pipefail
printf '%s\n' "$1" | SBP_SKIP_DEPS=1 bash <(sed '/^[[:space:]]*stty erase \^H/d' /root/sing-box-plus.sh)
"""
    return run(['bash', '-c', cmd, 'sbp-manager', str(option)], capture=True, timeout=120)

def decode64(s):
    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))

def link_info(s):
    if s.startswith('vmess://'):
        d = json.loads(decode64(s[8:].split('#', 1)[0]))
        return d['ps'], int(d['port']), d['add']
    from urllib.parse import unquote
    u = urlsplit(s)
    return unquote(u.fragment), u.port, u.hostname

def replace_port(s, mapping):
    if s.startswith('vmess://'):
        d = json.loads(decode64(s[8:].split('#', 1)[0]))
        d['port'] = str(mapping[int(d['port'])])
        return 'vmess://' + base64.b64encode(json.dumps(d, separators=(',', ':')).encode()).decode()
    u = urlsplit(s)
    auth, sep, hostport = u.netloc.rpartition('@')
    host = u.hostname
    need(host is not None and u.port in mapping, '节点地址或端口无法解析。')
    if ':' in host:
        host = '[' + host + ']'
    netloc = auth + sep + host + ':' + str(mapping[u.port])
    return urlunsplit((u.scheme, netloc, u.path, u.query, u.fragment))

def base_links():
    links = SCHEME_RE.findall(links_from_upstream())[:20]
    cfg = readj(BASE/'config.json')
    rows = [link_info(s) for s in links]
    need(len(links) == 20 and len({r[0] for r in rows}) == 20 and
         len({r[1] for r in rows}) == 20 and
         {r[1] for r in rows} == {i['listen_port'] for i in cfg['inbounds']} and
         sum(r[0].endswith('-warp') for r in rows) == 10,
         '基础分享链接和配置不一致。')
    return links

def extra_links():
    need_land()
    links = [s.strip() for s in (LAND/'nodes.txt').read_text().splitlines() if s.strip()]
    rows = [link_info(s) for s in links]
    cfg = readj(LAND/'config.json')
    need(len(links) == 10 and all(r[0].endswith('-landing') for r in rows)
         and len({r[0] for r in rows}) == len({r[1] for r in rows}) == 10
         and {r[1] for r in rows} == {i['listen_port'] for i in cfg['inbounds']},
         '落地分享链接和配置不一致。')
    return links

def sync_ready():
    need(TOKEN.is_file() and SUBURL.is_file() and WEB.is_dir(), '缺少 HTTPS 订阅部署，请先运行菜单1。')

def install_sync():
    sync_ready()
    script = download('auto-sync-install.sh', '/root/sbp-sub-auto-install.sh')
    run(['bash', script], timeout=600)
    
def ensure_sync():
    sync_ready()
    worker = Path('/usr/local/sbin/sbp-sub-sync')
    if not worker.is_file() or 'LANDING_DIR=' not in worker.read_text():
        print('安装/升级 20/30 节点同步组件。')
        install_sync()


def sync(force=False):
    ensure_sync()
    if force:
        STAMP.unlink(missing_ok=True)
    system('start', SYNC)
    n = 30 if landing_present() else 20
    token = TOKEN.read_text().strip()
    need(bool(re.fullmatch(r'[0-9a-f]{32,128}', token)), 'Token 格式异常。')
    need(NODES.is_file() and len(NODES.read_text().splitlines()) == n, '同步结果节点数量异常。')
    for ext in SUFFIXES:
        need((WEB/(token+ext)).is_file() and (WEB/(token+ext)).stat().st_size > 0, '订阅输出文件缺失。')
    for ext in ('.txt', '.shadowrocket.txt'):
        count = len(base64.b64decode((WEB/(token+ext)).read_bytes(), validate=True).splitlines())
        need(count == n, 'Base64 订阅节点数量异常。')
    import yaml
    y = yaml.safe_load((WEB/(token+'.clash.yaml')).read_text())
    need(len(y['proxies']) == n, 'Clash 订阅节点数量异常。')
    print(f'同步完成：{n} 个节点，原订阅 URL/Token 保持不变。')

@contextmanager
def pause_sync():
    was = [u for u in WATCH if active(u)]
    for u in was:
        system('stop', u)
    try:
        for _ in range(100):
            state = run(['systemctl', 'show', SYNC, '-p', 'ActiveState', '--value'],
                        capture=True, ok=False)
            if state not in ('activating', 'active', 'deactivating', 'reloading'):
                break
            time.sleep(1)
        else:
            raise Failure('订阅同步仍在进行，未修改配置。')
        yield
    finally:
        for u in was:
            system('start', u, ok=False)

def status():
    for u in (*SERVICES, *WATCH):
        print(f'  {u:34} {"运行中" if active(u) else "未运行"}')
    try:
        n = len(NODES.read_text().splitlines())
        print(f'  当前聚合订阅：{n} 条（文件记录，不等于全部可用）')
    except OSError:
        pass

def restart(unit):
    system('restart', unit)
    time.sleep(2)
    need(active(unit), '服务重启后未处于 active 状态：' + unit)

def show_urls():
    sync_ready()
    url = SUBURL.read_text().strip()
    need(url.startswith('https://') and url.endswith('.txt'), '订阅 URL 格式异常。')
    token = TOKEN.read_text().strip()
    need(url.endswith('/'+token+'.txt'), '订阅 URL 与 Token 不一致。')
    if not confirm('订阅链接包含访问密钥，将在当前终端显示，是否继续？'):
        return
    for label, ext in zip(('v2rayN', 'Clash/Mihomo', 'Shadowrocket', 'Shadowrocket 规则', 'v2rayN 路由'), SUFFIXES):
        print(label + ': ' + url[:-4] + ext)

def show_links():
    need_base()
    links = base_links() + (extra_links() if landing_present() else [])
    if confirm(f'显示全部 {len(links)} 条私有节点链接？'):
        print('\n'.join(links))

def port_free(port):
    # Probe both transports on IPv4 and, where supported, IPv6.
    opened = []
    try:
        for family, address in ((socket.AF_INET, '0.0.0.0'), (socket.AF_INET6, '::')):
            for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
                try:
                    s = socket.socket(family, kind)
                    opened.append(s)
                    if family == socket.AF_INET6:
                        s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                    s.bind((address, port))
                except OSError as e:
                    if family == socket.AF_INET6 and e.errno in (errno.EAFNOSUPPORT, errno.EPROTONOSUPPORT, errno.EADDRNOTAVAIL):
                        continue
                    return False
        return True
    finally:
        for s in opened:
            s.close()

def choose_ports(count, start, end, exclude):
    selected = []
    for p in random.SystemRandom().sample(range(start, end+1), end-start+1):
        if p not in exclude and port_free(p):
            selected.append(p)
            if len(selected) == count:
                return selected
    raise Failure('可用端口不足。')

def portmap(config, new):
    old = [int(x['listen_port']) for x in config['inbounds']]
    need(len(old) == len(set(old)) == len(new), '入站端口数量或唯一性校验失败。')
    return dict(zip(old, new))

def change_config_ports(config, mapping):
    result = copy.deepcopy(config)
    for item in result['inbounds']:
        item['listen_port'] = mapping[item['listen_port']]
    return result

def change_env_ports(raw, mapping):
    matches = PORT_RE.findall(raw)
    need(len(matches) == len(mapping) and {int(v) for _, v in matches} == set(mapping),
         'ports.env 格式不符合已知版本，拒绝修改。')
    return PORT_RE.sub(lambda m: m[1] + '=' + str(mapping[int(m[2])]), raw)

def verify_listeners(ports):
    listening=set()
    for row in run(['ss','-H','-lntu'],capture=True).splitlines():
        fields=row.split()
        if len(fields)>4:
            tail=fields[4].rsplit(':',1)[-1]
            if tail.isdigit():
                listening.add(int(tail))
    need(set(ports)<=listening, '存在未监听的新端口，拒绝发布订阅。')

def allow_ports(ports):
    print('新入站端口（TCP/UDP，按实际监听与云安全组设置）：')
    print(', '.join(map(str, sorted(ports))))
    need(confirm('确认这些端口已在服务商防火墙放行或该防火墙无需设置？'), '已取消，未提交配置变更。')
    if shutil.which('ufw') and 'Status: active' in run(['ufw', 'status'], capture=True):
        need(confirm('本机 UFW 已启用，允许脚本放行这些新端口？'), '未放行本机防火墙，取消。')
        for p in sorted(ports):
            for proto in ('tcp', 'udp'):
                run(['ufw', 'allow', f'{p}/{proto}'])
        print('已增加新 UFW 规则；旧规则不自动删除，请确认旧端口停用后自行清理。')

def copy_item(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_symlink():
        dst.symlink_to(os.readlink(src))
    elif src.is_dir():
        shutil.copytree(src, dst, symlinks=True, copy_function=shutil.copy2)
    else:
        shutil.copy2(src, dst)

def exists(p):
    return p.exists() or p.is_symlink()

def remove_item(p):
    if p.is_dir() and not p.is_symlink():
        shutil.rmtree(p)
    else:
        p.unlink(missing_ok=True)

def snapshot(label):
    # Keep published subscription files stable while taking a local backup.
    with pause_sync():
        return snapshot_files(label)


def snapshot_files(label):
    BACKUPS.mkdir(mode=0o700, exist_ok=True)
    os.chmod(BACKUPS, 0o700)
    d = Path(tempfile.mkdtemp(prefix=time.strftime('%Y%m%d-%H%M%S')+'-'+label+'-', dir=BACKUPS))
    (d/'files').mkdir(mode=0o700)
    paths = []
    for p in SNAP_PATHS:
        if exists(p):
            copy_item(p, d/'files'/str(p).lstrip('/'))
            paths.append(str(p))
    dump(d/'manifest.json', {'version':1, 'machine':Path('/etc/machine-id').read_text().strip(),
                            'present': paths, 'active': [u for u in SNAP_UNITS if active(u)],
                            'enabled': [u for u in SNAP_UNITS if enabled(u)]})
    print('本机私有备份：' + str(d))
    return d

def restore_snapshot(d):
    m = readj(d/'manifest.json')
    need(m['version'] == 1 and m['machine'] == Path('/etc/machine-id').read_text().strip(),
         '只允许恢复同一台 VPS 的备份。')
    need(set(m['present']) <= {str(p) for p in SNAP_PATHS}, '备份文件清单异常。')
    for p in m['present']:
        need(exists(d/'files'/p.lstrip('/')), '备份文件缺失。')
    # No tar extraction, no arbitrary destinations from the manifest.
    for u in (*WATCH, SYNC, SERVICES[1], SERVICES[0], SERVICES[2]):
        system('stop', u, ok=False, quiet=True)
    for u in (*WATCH, SERVICES[1]):
        system('disable', u, ok=False, quiet=True)
    for p in SNAP_PATHS:
        if exists(p):
            remove_item(p)
        if str(p) in m['present']:
            copy_item(d/'files'/str(p).lstrip('/'), p)
    system('daemon-reload')
    if (BASE/'config.json').is_file():
        check(BASE/'config.json')
    if (LAND/'config.json').is_file():
        check(LAND/'config.json')
    if Path('/etc/caddy/Caddyfile').is_file() and shutil.which('caddy'):
        run(['caddy', 'validate', '--config', '/etc/caddy/Caddyfile'], quiet=True)
    for u in SNAP_UNITS:
        if u in m['enabled']:
            system('enable', u)
        if u in m['active']:
            system('start', u)
    print('本机配置恢复完成。防火墙、远端 B、软件二进制版本不在恢复范围内。')

def rotate():
    need_base()
    ensure_sync()
    has = landing_present()
    if has:
        need_land()
        need(active(SERVICES[1]), '落地服务未运行，请先修复。')
    b = readj(BASE/'config.json')
    e = (BASE/'ports.env').read_text()
    old_links = base_links()
    old_ports = {link_info(s)[1] for s in old_links}
    l = readj(LAND/'config.json') if has else None
    extra = extra_links() if has else []
    old_ports |= {link_info(s)[1] for s in extra}
    bm = portmap(b, choose_ports(20, 12000, 44999, old_ports))
    lm = portmap(l, choose_ports(10, 55000, 55099, old_ports | set(bm.values()))) if has else {}
    new_env = change_env_ports(e, bm)
    new_extra = [replace_port(s, lm) for s in extra]
    if has:
        need({link_info(s)[1] for s in new_extra} == set(lm.values()), '新落地链接校验失败。')
    need(confirm(f'将轮换 {20+len(lm)} 个入站端口，短暂重启代理服务。继续？'), '已取消。')
    allow_ports(set(bm.values()) | set(lm.values()))
    save = snapshot('before-rotate')
    files = [BASE/'config.json', BASE/'ports.env'] + ([LAND/'config.json', LAND/'nodes.txt'] if has else [])
    old = {p: p.read_bytes() for p in files}
    with pause_sync():
        try:
            dump(BASE/'config.json', change_config_ports(b, bm))
            atomic(BASE/'ports.env', new_env)
            if has:
                dump(LAND/'config.json', change_config_ports(l, lm))
                atomic(LAND/'nodes.txt', '\n'.join(new_extra)+'\n')
            check(BASE/'config.json')
            if has:
                check(LAND/'config.json')
            restart(SERVICES[0])
            if has:
                restart(SERVICES[1])
            verify_listeners(set(bm.values()) | set(lm.values()))
            need({link_info(s)[1] for s in base_links()} == set(bm.values()),
                 '原脚本输出端口未随配置变化。')
            sync(force=True)
        except BaseException:
            print('轮换失败，正在恢复原端口及配置；新防火墙规则需人工检查。')
            for p, data in old.items():
                atomic(p, data)
            restart(SERVICES[0])
            if has:
                restart(SERVICES[1])
            sync(force=True)
            raise
    print(f'端口轮换完成。旧配置备份：{save}')

def ss_client(outbound):
    # Select an unused loopback SOCKS test port; keep test listeners private.
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    o = copy.deepcopy(outbound)
    o['tag'] = 'probe'
    return {'log':{'level':'warn'},
            'inbounds':[{'type':'socks','tag':'test','listen':'127.0.0.1','listen_port':port}],
            'outbounds':[o], 'route':{'final':'probe'}}, port

def probe(outbound):
    cfg, port = ss_client(outbound)
    with tempfile.TemporaryDirectory(prefix='sbp-probe-') as tmp:
        p = Path(tmp)/'config.json'
        dump(p, cfg)
        check(p)
        proc = sp.Popen([binary(), 'run', '-c', str(p)], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        try:
            time.sleep(2)
            need(proc.poll() is None, '测试代理启动失败。')
            return ip4(run(['curl','-4fsS','--noproxy','','--proxy',f'socks5h://127.0.0.1:{port}',
                            '--max-time','25','https://api.ipify.org'], capture=True, timeout=35))
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except sp.TimeoutExpired:
                    proc.kill()
                    proc.wait()

def ss_inbound_out(config, links, group):
    ports = {link_info(s)[1] for s in links
             if (group == 'warp' and link_info(s)[0].endswith('-warp'))
             or (group == 'landing' and link_info(s)[0].endswith('-landing'))
             or (group == 'direct' and not link_info(s)[0].endswith(('-warp','-landing')))}
    for item in config['inbounds']:
        if item['listen_port'] in ports and item['type']=='shadowsocks' and item.get('method','').startswith('2022-'):
            return {'type':'shadowsocks','server':'127.0.0.1','server_port':item['listen_port'],
                    'method':item['method'],'password':item['password']}
    raise Failure('该组没有找到单用户 SS2022 入站。')

def test_exits():
    need_base()
    b = readj(BASE/'config.json')
    links = base_links()
    targets = [('Direct', b, links, 'direct'), ('WARP', b, links, 'warp')]
    if landing_present():
        need_land()
        targets.append(('Landing', readj(LAND/'config.json'), extra_links(), 'landing'))
    for title, cfg, ns, group in targets:
        try:
            print(title + ': ' + probe(ss_inbound_out(cfg, ns, group)))
        except Exception as e:
            print(f'{title}: 测试失败 ({type(e).__name__})')
    print('此处通过各组实际 SS2022 入站测试 TCP 出口，不代表所有协议及 UDP 均已验证。')

def link_configs(host, port, key):
    need(len(base64.b64decode(key, validate=True))==32, 'SS2022 密钥必须为32字节Base64。')
    method = '2022-blake3-aes-256-gcm'
    o = {'type':'shadowsocks','tag':'landing','server':host,'server_port':port,
         'method':method,'password':key}
    s = {'log':{'level':'warn'},'inbounds':[{'type':'shadowsocks','tag':'landing-in',
         'listen':'0.0.0.0','listen_port':port,'method':method,'password':key}],
         'outbounds':[{'type':'direct','tag':'direct'}], 'route':{'final':'direct'}}
    c = {'log':{'level':'warn'},'inbounds':[{'type':'socks','tag':'test-in',
         'listen':'127.0.0.1','listen_port':19080}], 'outbounds':[o], 'route':{'final':'landing'}}
    return s,c

def remote_install(host, sshport, server):
    target = 'root@'+host
    ssh = ['ssh','-p',str(sshport),'-o','ConnectTimeout=12',target]
    # Require verified SSH and a preconfigured provider firewall; never disable host-key checking.
    print('请核验 SSH 主机指纹，密码仅在 SSH 交互提示处输入。')
    run(ssh+['printf "SSH source: %s\\n" "$SSH_CONNECTION"'])
    need(confirm('已将 B 的 TCP/UDP 24443 限制为 A 实际公网来源地址？'), '未确认落地防火墙，取消部署。')
    remote = '/root/.sbpm-stage-'+secrets.token_hex(8)
    run(ssh+['install -d -m 700 '+remote])
    try:
        with tempfile.TemporaryDirectory(prefix='sbp-exit-') as tmp:
            f=Path(tmp)/'server.json'
            dump(f,server)
            run(['scp','-P',str(sshport),binary(),target+':'+remote+'/sing-box'], timeout=300)
            run(['scp','-P',str(sshport),f,target+':'+remote+'/server.json'])
            # Intentional stdin for remote script; no interactive SSH inside a heredoc.
            run(ssh+['bash -s -- '+remote], stdin=REMOTE_SCRIPT, timeout=180)
    finally:
        try:
            run(ssh+['rm -rf -- '+remote], ok=False, quiet=True, timeout=60)
        except Exception:
            print('请在 B 上清理本次私有临时上传目录：'+remote)
    print('B 端独立服务已安装。若后续 A 端操作失败，B 端服务仍需单独维护。')

def prepare_link():
    print('  1) 使用本机已准备的 /root/sbp-landing/test-client.json')
    print('  2) 接入已配置的 SS2022 落地服务（输入密钥）')
    print('  3) SSH 自动部署新的 B（root 权限，兼容 Linux/CPU）')
    mode = ask('选择', '1')
    if mode == '1':
        need((STAGE/'test-client.json').is_file(), '缺少已准备的测试配置。')
        o = readj(STAGE/'test-client.json')['outbounds'][0]
        need(o['type']=='shadowsocks' and o['method']=='2022-blake3-aes-256-gcm', '只支持已知 SS2022 链路格式。')
        host, port, key = ip4(o['server']), portnum(o['server_port']), o['password']
    else:
        need(mode in ('2','3'), '无效选项。')
        host = ip4(ask('B 的公网连接 IPv4'))
        port = 24443 if mode=='3' else portnum(ask('B 的 SS2022 端口','24443'))
        key = base64.b64encode(secrets.token_bytes(32)).decode() if mode=='3' else getpass.getpass('SS2022 Base64 密钥（不回显）: ').strip()
    need(host not in {link_info(s)[2] for s in base_links()}, 'B 不能与中转机分享地址相同。')
    expected = ip4(ask('预期 B 的实际公网出口 IPv4',host))
    server,client=link_configs(host,port,key)
    if mode=='3':
        sshport=portnum(ask('B 的 SSH 端口','22'))
        remote_install(host,sshport,server)
    actual=probe(client['outbounds'][0])
    need(actual==expected,'落地出口与预期不一致：'+actual)
    print('A→B 出口验证成功：'+actual)
    return server,client,key,expected

def save_stage(server,client,key):
    STAGE.mkdir(mode=0o700,exist_ok=True)
    os.chmod(STAGE,0o700)
    dump(STAGE/'server.json',server)
    dump(STAGE/'test-client.json',client)
    atomic(STAGE/'key.txt',key)

def add_landing():
    need_base()
    sync_ready()
    need(not landing_present(), '已有落地服务；请选择菜单8更换，而非重复安装。')
    ensure_sync()
    backup=snapshot('before-add')
    server,client,key,expected=prepare_link()
    save_stage(server,client,key)
    p=download('landing-install.py','/root/landing-install.py',python=True)
    with pause_sync():
        run(['python3',p,'--expect-ip',expected],timeout=600)
        try:
            ports={link_info(s)[1] for s in extra_links()}
            allow_ports(ports)
            verify_listeners(ports)
            sync(force=True)
        except BaseException:
            print('新增落地未完成，移除本次 A 端新增服务并保留 B 端链路配置供重试。')
            system('disable','--now',SERVICES[1])
            shutil.move(str(LAND),str(backup/'new-landing'))
            shutil.move(str(UNIT),str(backup/'new-landing.service'))
            system('daemon-reload')
            sync(force=True)
            raise

def switch_landing():
    need_base()
    need_land()
    need(active(SERVICES[1]),'落地入站服务未运行。')
    need(confirm('更换 B 的链路配置，保留原10个落地入站端口及凭据？'),'已取消。')
    ensure_sync()
    save=snapshot('before-switch')
    server,client,key,expected=prepare_link()
    p=LAND/'config.json'
    old=p.read_bytes()
    old_stage={q:q.read_bytes() for q in (STAGE/'server.json',STAGE/'test-client.json',STAGE/'key.txt') if q.is_file()}
    cfg=readj(p)
    cfg['outbounds']=[client['outbounds'][0]]
    cfg['route']['final']='landing'
    with pause_sync():
        try:
            dump(p,cfg)
            check(p)
            restart(SERVICES[1])
            need(probe(ss_inbound_out(cfg,extra_links(),'landing'))==expected,'新落地入站实际出口与预期不一致。')
            save_stage(server,client,key)
            sync(force=True)
        except BaseException:
            atomic(p,old)
            for q in (STAGE/'server.json',STAGE/'test-client.json',STAGE/'key.txt'):
                if q in old_stage:
                    atomic(q,old_stage[q])
                else:
                    q.unlink(missing_ok=True)
            restart(SERVICES[1])
            sync(force=True)
            raise
    print('落地 VPS 更换成功；原节点链接不变。旧 B 不会被远程卸载。备份：'+str(save))

def delete_landing():
    need_base()
    need_land()
    need(confirm('删除 A 上的10个落地节点并恢复20节点订阅？B 上的服务不会被删除。'),'已取消。')
    ensure_sync()
    old_host=ip4(readj(LAND/'config.json')['outbounds'][0]['server'])
    d=snapshot('before-remove')
    archived=d/'removed-live'
    archived.mkdir(mode=0o700)
    with pause_sync():
        moved=[]
        try:
            system('disable','--now',SERVICES[1])
            for src,dst in ((LAND,archived/'landing'),(UNIT,archived/'landing.service'),(STAGE,archived/'stage')):
                if exists(src):
                    shutil.move(str(src),str(dst))
                    moved.append((src,dst))
            system('daemon-reload')
            sync(force=True)
        except BaseException:
            for src,dst in reversed(moved):
                shutil.move(str(dst),str(src))
            system('daemon-reload')
            system('enable','--now',SERVICES[1])
            sync(force=True)
            raise
    print('A 已恢复20节点。备份：'+str(d))
    if confirm('是否另外通过 SSH 停用旧 B 的独立落地服务？仅适用于该服务专供本机，不删除 B 或其配置。'):
        sshport=portnum(ask('旧 B 的 SSH 端口','22'))
        try:
            run(['ssh','-p',str(sshport),'-o','ConnectTimeout=12','root@'+old_host,
                 'systemctl disable --now sing-box-landing-exit.service'],timeout=90)
            print('旧 B 的独立服务已停用，配置保留。')
        except Exception:
            print('A 的删除操作已经完成；B 的停用失败，请自行登录 B 检查。')
    else:
        print('B 服务未修改；必要时登录 B 执行：systemctl disable --now sing-box-landing-exit.service')

def install_base():
    if BASE.joinpath('config.json').exists():
        need_base()
        if TOKEN.is_file() and SUBURL.is_file() and WEB.is_dir():
            print('基础节点和订阅已存在，不重装；检查同步组件。')
            sync(force=True)
            return
    need(confirm('运行基础安装器（新部署或补建HTTPS订阅；可能写入Caddy配置）？'),'已取消。')
    if BASE.exists():
        snapshot('before-base-install')
    p=download('install.sh','/root/install-sbp.sh')
    run(['bash',p],timeout=1800)

def restart_all():
    need_base(require_active=False)
    check(BASE/'config.json')
    if landing_present():
        need_land()
        check(LAND/'config.json')
    need(confirm('重启现有代理服务，连接可能短暂中断？'),'已取消。')
    with pause_sync():
        restart(SERVICES[0])
        if landing_present():
            restart(SERVICES[1])
        sync()

def bbr():
    need(confirm('在当前中转 VPS 启用 BBR/fq？'),'已取消。')
    if shutil.which('modprobe'):
        run(['modprobe','tcp_bbr'],ok=False,quiet=True)
    avail=run(['sysctl','-n','net.ipv4.tcp_available_congestion_control'],capture=True)
    need('bbr' in avail.split(),'当前内核未提供 BBR。')
    p=Path('/etc/sysctl.d/99-sbp-manager-bbr.conf')
    old=p.read_bytes() if p.is_file() else None
    oldq=run(['sysctl','-n','net.core.default_qdisc'],capture=True)
    oldc=run(['sysctl','-n','net.ipv4.tcp_congestion_control'],capture=True)
    try:
        atomic(p,'net.core.default_qdisc = fq\nnet.ipv4.tcp_congestion_control = bbr\n',0o644)
        run(['sysctl','-p',p])
        need(run(['sysctl','-n','net.ipv4.tcp_congestion_control'],capture=True)=='bbr','BBR未生效。')
    except BaseException:
        if old is None: p.unlink(missing_ok=True)
        else: atomic(p,old,0o644)
        run(['sysctl','-w','net.core.default_qdisc='+oldq],ok=False)
        run(['sysctl','-w','net.ipv4.tcp_congestion_control='+oldc],ok=False)
        raise

def ipv6():
    need_base()
    print('原脚本 IPv6 分享链接仅包含基础节点。新增落地入站当前绑定 IPv4。')
    if confirm('显示基础 IPv6 私有分享链接？'):
        print(links_from_upstream(6))

def restore_menu():
    need(BACKUPS.is_dir(),'没有本机备份。')
    choices=sorted((p for p in BACKUPS.iterdir() if p.is_dir() and (p/'manifest.json').is_file()),reverse=True)
    need(choices,'没有有效备份。')
    for i,p in enumerate(choices[:30],1):
        print(i,p.name)
    idx=int(ask('选择备份编号','1'))
    need(1<=idx<=min(len(choices),30),'编号无效。')
    need(confirm('恢复本机配置会短暂停止代理和HTTPS；不恢复 B 或云防火墙。继续？'),'已取消。')
    rescue=snapshot('before-restore')
    try:
        restore_snapshot(choices[idx-1])
        if active(SERVICES[0]) and TOKEN.is_file():
            sync(force=True)
    except BaseException:
        print('恢复失败，尝试还原操作前备份。')
        restore_snapshot(rescue)
        raise

def update_manager():
    need(confirm('从当前 GitHub main 分支更新管理入口及核心程序？'),'已取消。')
    root=Path('/root')
    core=Path(__file__).resolve()
    entry=Path(os.environ.get('SBP_MANAGER_ENTRY','/root/sbp-manager.sh')).resolve()
    with tempfile.TemporaryDirectory(prefix='sbpm-update-',dir=root) as tmp:
        p=download('sbp-manager.py',Path(tmp)/'sbp-manager.py',python=True)
        q=download('sbp-manager.sh',Path(tmp)/'sbp-manager.sh')
        run(['python3',p,'--self-test'])
        atomic(core,p.read_bytes(),0o700)
        atomic(entry,q.read_bytes(),0o700)
    print('管理程序已更新；退出后重新运行。订阅组件可通过菜单12升级/同步。')

def sync_menu():
    if confirm('同时从 GitHub 更新订阅同步组件？（否：只同步现有版本）'):
        install_sync()
    sync(force=True)


def self_test():
    # Pure, synthetic inputs. No VPS paths, network or systemd access.
    old=[10001,10002]
    m={10001:30001,10002:30002}
    cfg={'inbounds':[{'listen_port':i} for i in old]}
    assert [i['listen_port'] for i in change_config_ports(cfg,m)['inbounds']]==[30001,30002]
    assert [i['listen_port'] for i in cfg['inbounds']]==old
    assert change_env_ports('PORT_A=10001\nPORT_B=10002\n',m)=='PORT_A=30001\nPORT_B=30002\n'
    try:
        change_env_ports('PORT_A=10001\n',m)
    except Failure:
        pass
    else:
        raise AssertionError('incomplete env accepted')
    for s in (
        'vless://id@example.com:10001?type=tcp#vless-landing',
        'ss://YWVzOnBhc3M=@example.com:10001#ss-landing',
        'tuic://id:pw@example.com:10001?alpn=h3#tuic-landing',
        'hy2://pw@[2001:db8::1]:10001?obfs-password=x%3D#hy2-landing',
        'vmess://'+base64.b64encode(json.dumps({'ps':'vmess-landing','port':'10001','add':'example.com','id':'x'}).encode()).decode(),
    ):
        new=replace_port(s,m)
        a,b=link_info(s),link_info(new)
        assert b==(a[0],30001,a[2])
    key=base64.b64encode(bytes(range(32))).decode()
    server,client=link_configs('203.0.113.20',24443,key)
    assert server['inbounds'][0]['password']==client['outbounds'][0]['password']
    assert server['route']['final']=='direct' and client['route']['final']=='landing'
    print('Self-test passed: port mapping, env validation, URI/VMess rewriting, link config.')

def main():
    if sys.argv[1:]==['--self-test']:
        self_test()
        return
    if sys.argv[1:]==['--version']:
        print(VERSION)
        return
    if sys.argv[1:]:
        raise Failure('仅支持 --version、--self-test 或直接启动菜单。')
    need(os.geteuid()==0,'请使用 root 运行。')
    os.umask(0o077)
    lock=open('/run/sbp-manager.lock','a')
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        raise Failure('另一个管理菜单正在运行。') from None
    actions={
        '1':('安装基础20节点及HTTPS订阅',install_base),
        '2':('查看全部IPv4节点分享链接',show_links),
        '3':('重启代理服务',restart_all),
        '4':('一键更换全部20/30个节点端口',rotate),
        '5':('开启当前VPS的BBR',bbr),
        '6':('查看基础IPv6分享链接',ipv6),
        '7':('添加落地 VPS',add_landing),
        '8':('更换落地 VPS（保留入口）',switch_landing),
        '9':('删除落地 VPS 扩展（本机）',delete_landing),
        '10':('测试 Direct/WARP/Landing 三组实际出口',test_exits),
        '11':('查看全部订阅及规则链接',show_urls),
        '12':('立即同步订阅 / 升级同步组件',sync_menu),
        '13':('检查服务状态及同步日志',lambda:(status(),run(['journalctl','-u',SYNC,'-n','20','--no-pager'],ok=False))),
        '14':('更新管理脚本',update_manager),
        '15':('备份本机配置及订阅密钥',lambda:snapshot('manual')),
        '16':('恢复本机配置',restore_menu),
    }
    while True:
        print('\n'+'='*62+'\n Sing-Box-Plus 增强管理系统 v'+VERSION+'\n'+'='*62)
        status()
        print('-'*62)
        for k,(label,_) in actions.items():
            print(f'{k:>2}) {label}')
        print(' 0) 退出\n'+'='*62)
        try:
            choice=input('选择: ').strip()
        except (EOFError,KeyboardInterrupt):
            break
        if choice=='0':
            break
        if choice not in actions:
            print('请输入有效菜单编号。')
            continue
        try:
            actions[choice][1]()
            if choice=='14':
                break
        except Failure as e:
            print('操作未完成：'+str(e))
        except KeyboardInterrupt:
            print('\n操作已中断；请检查状态及备份。')
        except Exception as e:
            print('操作未完成（'+type(e).__name__+'）；检查服务、日志与私有备份。')
        try:
            input('回车返回菜单...')
        except (EOFError,KeyboardInterrupt):
            break

if __name__=='__main__':
    try:
        main()
    except Failure as e:
        print(str(e),file=sys.stderr)
        sys.exit(1)
