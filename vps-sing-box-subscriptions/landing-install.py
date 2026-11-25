#!/usr/bin/env python3
"""Install ten isolated landing inbounds using the existing, working SBP config.
No upstream config changes, no hard-coded credentials or server IPs.
Run on the relay VPS only, after the landing outbound has been tested.
"""
import argparse
import base64
import copy
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

ROOT = Path('/opt/sing-box-landing')
UNIT = Path('/etc/systemd/system/sing-box-landing.service')
SERVICE = UNIT.name
BASE = Path('/opt/sing-box/config.json')
SOURCE = Path('/root/sing-box-plus.sh')
OUT = Path('/root/sbp-landing/test-client.json')

def require(ok, msg):
    if not ok:
        raise RuntimeError(msg)

def b64(s):
    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))

def encode64(s):
    return base64.b64encode(s).decode()

def read_json(p):
    return json.loads(p.read_text())

def write_json(p, d):
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + '\n')
    p.chmod(0o600)

def metadata(link):
    if link.startswith('vmess://'):
        d = json.loads(b64(link[8:].split('#', 1)[0]))
        return d['ps'], int(d['port']), d['add'], 'vmess'
    u = urlsplit(link)
    return unquote(u.fragment), u.port, u.hostname, u.scheme

def extract_links():
    cmd = r"""set -o pipefail
printf '2\n' | SBP_SKIP_DEPS=1 bash <(sed '/^[[:space:]]*stty erase \^H/d' /root/sing-box-plus.sh)
"""
    p = subprocess.run(['bash', '-c', cmd], capture_output=True, text=True,
                       timeout=90)
    require(p.returncode == 0, '无法执行原脚本菜单2；请先检查基础节点。')
    links = re.findall(r'(?m)^[ \t]*((?:vless|trojan|hy2|hysteria2|vmess|ss|tuic|anytls)://[^\s]+)', p.stdout)
    require(len(links) >= 20, '原脚本没有返回20条节点。')
    links = links[:20]
    info = [metadata(x) for x in links]
    require(len({x[0] for x in info}) == len({x[1] for x in info}) == 20,
            '基础节点名称或端口重复。')
    require(all(not x[0].endswith('-warp') for x in info[:10]) and
            all(x[0].endswith('-warp') for x in info[10:]),
            '基础节点分组与已知格式不一致。')
    return links

def port_free(port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as t, \
             socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as u:
            t.bind(('0.0.0.0', port))
            u.bind(('0.0.0.0', port))
        return True
    except OSError:
        return False

def rand_password():
    return secrets.token_urlsafe(32)

def copy_tls_paths(obj, workdir, cache):
    """Isolate on-disk TLS cert/key material from future SBP updates."""
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if k in ('certificate_path', 'key_path') and isinstance(v, str) and v:
                src = Path(v)
                if not src.is_absolute():
                    candidate = workdir / src
                    src = candidate if candidate.is_file() else BASE.parent / src
                src = src.resolve()
                require(src.is_file(), '缺少原入站的 TLS 文件，请检查原配置。')
                if src not in cache:
                    dest = ROOT / ('tls-' + str(len(cache)) + src.suffix)
                    shutil.copyfile(src, dest)
                    dest.chmod(0o600)
                    cache[src] = str(dest)
                obj[k] = cache[src]
            else:
                copy_tls_paths(v, workdir, cache)
    elif isinstance(obj, list):
        for value in obj:
            copy_tls_paths(value, workdir, cache)

def clone(link, source, port):
    name, oldport, host, scheme = metadata(link)
    require(ipaddress.ip_address(host).version == 4, '目前只处理 IPv4 分享链接。')
    expected = {'ss': 'shadowsocks', 'hy2': 'hysteria2'}.get(scheme, scheme)
    require(source['type'] == expected, '原节点协议与配置不一致。')
    inbound = copy.deepcopy(source)
    inbound['tag'] = name + '-landing'
    inbound['listen'] = '0.0.0.0'
    inbound['listen_port'] = port
    if scheme == 'ss':
        require(not inbound.get('users') and not inbound.get('destinations') and not inbound.get('managed'),
                '只支持单用户 Shadowsocks 入站。')
        method = inbound['method']
        lengths = {'2022-blake3-aes-128-gcm': 16,
                   '2022-blake3-aes-256-gcm': 32,
                   '2022-blake3-chacha20-poly1305': 32}
        if method.startswith('2022-'):
            require(method in lengths, '不支持的 SS2022 加密方式。')
            password = encode64(secrets.token_bytes(lengths[method]))
        else:
            require(method != 'none', '拒绝无认证 Shadowsocks 入站。')
            password = rand_password()
        inbound['password'] = password
        auth = base64.urlsafe_b64encode((method + ':' + password).encode()).decode().rstrip('=')
    else:
        users = inbound.get('users', [])
        require(len(users) == 1, '只支持原脚本的单用户入站结构。')
        user = users[0]
        if scheme in ('vless', 'vmess', 'tuic'):
            user['uuid'] = str(uuid.uuid4())
            auth = user['uuid']
        if scheme in ('trojan', 'hy2', 'hysteria2', 'tuic', 'anytls'):
            user['password'] = rand_password()
            auth = (user['uuid'] + ':' + user['password']) if scheme == 'tuic' else user['password']
    if scheme == 'vmess':
        d = json.loads(b64(link[8:].split('#', 1)[0]))
        d.update(ps=name + '-landing', port=str(port), id=inbound['users'][0]['uuid'])
        return inbound, 'vmess://' + encode64(json.dumps(d, separators=(',', ':')).encode())
    u = urlsplit(link)
    query = u.query
    if scheme in ('hy2', 'hysteria2') and inbound.get('obfs', {}).get('password'):
        pwd = rand_password()
        inbound['obfs']['password'] = pwd
        q = [(k, v) for k, v in parse_qsl(query, keep_blank_values=True) if k != 'obfs-password']
        q.append(('obfs-password', pwd))
        query = urlencode(q)
    encoded_auth = quote(auth, safe=':' if scheme == 'tuic' else '')
    newlink = urlunsplit((u.scheme, encoded_auth + '@' + host + ':' + str(port),
                          u.path, query, quote(name + '-landing', safe='-')))
    return inbound, newlink

def verify_exit(binary, config, expected):
    # Test a real newly deployed inbound, not only the A -> B uplink.
    ss = next(x for x in config['inbounds']
              if x['type'] == 'shadowsocks' and x['method'].startswith('2022-'))
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    test = {
        'log': {'level': 'warn'},
        'inbounds': [{'type': 'socks', 'tag': 'test-in', 'listen': '127.0.0.1', 'listen_port': port}],
        'outbounds': [{'type': 'shadowsocks', 'tag': 'test-out', 'server': '127.0.0.1',
                       'server_port': ss['listen_port'], 'method': ss['method'],
                       'password': ss['password']}],
        'route': {'final': 'test-out'},
    }
    with tempfile.TemporaryDirectory(prefix='sbp-landing-test-') as d:
        path = Path(d) / 'test.json'
        write_json(path, test)
        subprocess.run([binary, 'check', '-c', str(path)], check=True)
        p = subprocess.Popen([binary, 'run', '-c', str(path)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            time.sleep(2)
            require(p.poll() is None, '本地测试代理未能启动。')
            ip = subprocess.check_output(
                ['curl', '-4fsS', '--noproxy', '', '--proxy', 'socks5h://127.0.0.1:' + str(port),
                 '--max-time', '20', 'https://api.ipify.org'], text=True).strip()
            require(ipaddress.ip_address(ip).is_global, '未获得有效公网出口IP。')
            require(ip == expected, '落地出口IP与预期不一致：' + ip)
            print('新 SS2022 落地节点实测出口：' + ip)
        finally:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expect-ip', required=True, help='previously tested landing exit IP')
    args = parser.parse_args()
    ipaddress.IPv4Address(args.expect_ip)
    require(os.geteuid() == 0, '请以 root 执行。')
    os.umask(0o077)
    require(not ROOT.exists() and not UNIT.exists(), '已有落地服务；为防覆盖，本脚本拒绝重复部署。')
    binary = shutil.which('sing-box')
    require(binary and Path(binary).is_file(), '找不到原 Sing-Box 二进制文件。')
    require(BASE.is_file() and SOURCE.is_file() and OUT.is_file(), '缺少已验证的基础配置或落地测试配置。')
    subprocess.run(['systemctl', 'is-active', '--quiet', 'sing-box.service'], check=True)
    base = read_json(BASE)
    byport = {i['listen_port']: i for i in base['inbounds']}
    links = extract_links()
    require(len(base['inbounds']) == len(byport) == 20 and
            {metadata(x)[1] for x in links} == set(byport),
            '基础分享链接端口和实际配置不一致。')
    test_out = read_json(OUT)['outbounds']
    require(len(test_out) == 1 and test_out[0]['type'] == 'shadowsocks' and
            test_out[0]['method'].startswith('2022-'), '测试出站不是独立 SS2022 链路。')
    outbound = copy.deepcopy(test_out[0])
    outbound['tag'] = 'landing'
    ipaddress.ip_address(outbound['server'])
    ports = [p for p in range(55000, 55100) if p not in byport and port_free(p)][:10]
    require(len(ports) == 10, '55000–55099 中没有10个空闲端口。')
    wd = subprocess.check_output(['systemctl', 'show', 'sing-box.service',
                                  '-p', 'WorkingDirectory', '--value'], text=True).strip()
    workdir = Path(wd or '/')
    ROOT.mkdir(mode=0o700)
    unit_written = False
    try:
        inbounds, newlinks, tls_cache = [], [], {}
        for link, port in zip(links[:10], ports):
            inbound, newlink = clone(link, byport[metadata(link)[1]], port)
            copy_tls_paths(inbound, workdir, tls_cache)
            inbounds.append(inbound)
            newlinks.append(newlink)
        config = {'log': {'level': 'warn'}, 'inbounds': inbounds,
                  'outbounds': [outbound], 'route': {'final': 'landing'}}
        write_json(ROOT / 'config.json', config)
        subprocess.run([binary, 'check', '-c', str(ROOT / 'config.json')], check=True)
        UNIT.write_text(
            '[Unit]\nDescription=Sing-Box additional landing inbounds\n'
            'After=network-online.target\nWants=network-online.target\n\n'
            '[Service]\nType=simple\nWorkingDirectory=' + str(ROOT) + '\n'
            'ExecStart=' + binary + ' run -c ' + str(ROOT / 'config.json') + '\n'
            'Restart=on-failure\nRestartSec=3\nNoNewPrivileges=true\n\n'
            '[Install]\nWantedBy=multi-user.target\n')
        unit_written = True
        UNIT.chmod(0o644)
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', 'enable', '--now', SERVICE], check=True)
        time.sleep(2)
        subprocess.run(['systemctl', 'is-active', '--quiet', SERVICE], check=True)
        verify_exit(binary, config, args.expect_ip)
        # Publish links only after the service passes the end-to-end SS2022 test.
        (ROOT / 'nodes.txt').write_text('\n'.join(newlinks) + '\n')
        (ROOT / 'nodes.txt').chmod(0o600)
    except BaseException:
        if unit_written:
            subprocess.run(['systemctl', 'disable', '--now', SERVICE], check=False)
            UNIT.unlink(missing_ok=True)
            subprocess.run(['systemctl', 'daemon-reload'], check=False)
        shutil.rmtree(ROOT)
        raise
    print('成功：原20个节点不变，新增10个落地节点。')
    print('新增端口：' + ', '.join(str(x) for x in ports))
    print('请在云防火墙放行这些端口的实际 TCP/UDP 监听协议。')
    print('原脚本菜单4仅更换基础20节点端口；新增落地端口独立管理。')
    print('落地节点私有文件：' + str(ROOT / 'nodes.txt'))

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        # Do not dump credential-bearing configuration or share-link output.
        if isinstance(e, RuntimeError):
            print('部署未完成：' + str(e), file=sys.stderr)
        else:
            print('部署未完成（' + type(e).__name__ + '），请核对 systemd 状态及原配置。', file=sys.stderr)
        sys.exit(1)
