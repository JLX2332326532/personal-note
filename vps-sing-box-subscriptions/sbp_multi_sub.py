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



def routing_rules():
    """v2rayN custom routing-rule array (separate from node subscription)."""
    return [
        {'remarks': '局域网域名直连', 'outboundTag': 'direct',
         'domain': ['geosite:private'], 'enabled': True},
        {'remarks': '局域网 IP 直连', 'outboundTag': 'direct',
         'ip': ['geoip:private'], 'enabled': True},
        {'remarks': '常用境外服务优先代理', 'outboundTag': 'proxy',
         'domain': ['domain:github.com', 'domain:githubusercontent.com',
                    'domain:openai.com', 'domain:chatgpt.com',
                    'domain:google.com', 'domain:youtube.com'], 'enabled': True},
        {'remarks': '中国大陆域名直连', 'outboundTag': 'direct',
         'domain': ['geosite:cn'], 'enabled': True},
        {'remarks': '中国大陆 IP 直连', 'outboundTag': 'direct',
         'ip': ['geoip:cn'], 'enabled': True},
        {'remarks': '其余流量代理', 'outboundTag': 'proxy',
         'port': '0-65535', 'enabled': True},
    ]


def shadowrocket_rules():
    """Import this .conf under Shadowrocket Configuration, nodes remain in .txt."""
    return """# CN direct / international proxy. Select a node in Shadowrocket.
[General]
bypass-system = true
skip-proxy = 192.168.0.0/16, 10.0.0.0/8, 172.16.0.0/12, localhost, *.local
ipv6 = true
prefer-ipv6 = false

[Rule]
IP-CIDR,127.0.0.0/8,DIRECT,no-resolve
IP-CIDR,10.0.0.0/8,DIRECT,no-resolve
IP-CIDR,172.16.0.0/12,DIRECT,no-resolve
IP-CIDR,192.168.0.0/16,DIRECT,no-resolve
IP-CIDR6,::1/128,DIRECT,no-resolve
IP-CIDR6,fc00::/7,DIRECT,no-resolve
DOMAIN-SUFFIX,github.com,PROXY
DOMAIN-SUFFIX,githubusercontent.com,PROXY
DOMAIN-SUFFIX,openai.com,PROXY
DOMAIN-SUFFIX,chatgpt.com,PROXY
DOMAIN-SUFFIX,google.com,PROXY
DOMAIN-SUFFIX,youtube.com,PROXY
DOMAIN-SUFFIX,cn,DIRECT
RULE-SET,https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/China/China.list,DIRECT
DOMAIN-SET,https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/China/China_Domain.list,DIRECT
GEOIP,CN,DIRECT
FINAL,PROXY
"""

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
        'rule-providers': {
            'cn-domain': {
                'type': 'http', 'behavior': 'domain', 'format': 'mrs',
                'path': './rule_provider/geosite-cn.mrs', 'interval': 86400,
                'proxy': '节点选择',
                'url': 'https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/meta/geo/geosite/cn.mrs',
            },
            'cn-ip': {
                'type': 'http', 'behavior': 'ipcidr', 'format': 'mrs',
                'path': './rule_provider/geoip-cn.mrs', 'interval': 86400,
                'proxy': '节点选择',
                'url': 'https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/meta/geo/geoip/cn.mrs',
            },
        },
        'rules': [
            'IP-CIDR,127.0.0.0/8,DIRECT,no-resolve',
            'IP-CIDR,10.0.0.0/8,DIRECT,no-resolve',
            'IP-CIDR,172.16.0.0/12,DIRECT,no-resolve',
            'IP-CIDR,192.168.0.0/16,DIRECT,no-resolve',
            'IP-CIDR6,::1/128,DIRECT,no-resolve',
            'IP-CIDR6,fc00::/7,DIRECT,no-resolve',
            'DOMAIN-SUFFIX,github.com,节点选择',
            'DOMAIN-SUFFIX,githubusercontent.com,节点选择',
            'DOMAIN-SUFFIX,openai.com,节点选择',
            'DOMAIN-SUFFIX,chatgpt.com,节点选择',
            'DOMAIN-SUFFIX,google.com,节点选择',
            'DOMAIN-SUFFIX,youtube.com,节点选择',
            'DOMAIN-SUFFIX,cn,DIRECT',
            'RULE-SET,cn-domain,DIRECT',
            'RULE-SET,cn-ip,DIRECT,no-resolve',
            'MATCH,节点选择',
        ],
    }
    raw = NODES.read_bytes()
    sub = base64.b64encode(raw)
    items = {
        f'{token}.txt': sub,
        f'{token}.shadowrocket.txt': sub,
        f'{token}.shadowrocket.conf': shadowrocket_rules().encode('utf-8'),
        f'{token}.v2rayn-routing.json': json.dumps(routing_rules(), ensure_ascii=False, indent=2).encode('utf-8'),
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
        print('Shadowrocket 规则配置: ' + prefix + '.shadowrocket.conf')
        print('v2rayN 路由规则: ' + prefix + '.v2rayn-routing.json')
    else:
        print('订阅文件已生成；原HTTPS链接信息缺失，请核实Caddy域名后组合URL')

if __name__ == '__main__':
    main()