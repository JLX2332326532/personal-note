# Sing-Box-Plus 20/30 nodes + three HTTPS subscriptions (Debian 13)

An installer for **your own Debian 13 VPS** based on the third-party [Sing-Box-Plus](https://github.com/Alvin9999-newpac/Sing-Box-Plus) v4.8.0 script. This project does not include a copy of your VPS credentials, UUID, subscriptions, tokens, or node links. This project is independent of upstream.

[中文说明](./README_zh.md)

The base installer deploys 20 nodes; the optional dual-VPS extension below adds ten independent landing nodes (30 total).

## Fresh VPS installation

Review `install.sh` and `auto-sync-install.sh` before running any remote shell script. As root:

```bash
apt-get update && apt-get install -y curl ca-certificates
curl -fL https://raw.githubusercontent.com/JLX2332326532/personal-note/main/vps-sing-box-subscriptions/install.sh -o /root/install-sbp-sub.sh
bash /root/install-sbp-sub.sh
```

For a domain you own, set `SUB_DOMAIN=sub.example.com` when running the installer and point its DNS A record at your VPS first. Without this, the installer uses `<IPv4-with-dashes>.sslip.io` (a third-party DNS service); its availability, TLS issuance and certificate limits are outside our control.

The installer installs third-party Sing-Box-Plus, configures Caddy on 80/443, generates an independent random URL token, publishes:

- `https://HOST/TOKEN.txt` — v2rayN Base64
- `https://HOST/TOKEN.clash.yaml` — Clash Verge Rev/Mihomo YAML
- `https://HOST/TOKEN.shadowrocket.txt` — Shadowrocket Base64

Files live in `/srv/sbp-sub`. The URLs/tokens persist under `/root/sub-token.txt` and `/root/subscription-url.txt`, with permissions 0600. Subscription URLs are bearer credentials; **do not commit, expose or share them**.

The systemd `sbp-sub-sync.path` service watches `/opt/sing-box/ports.env` plus optional landing config/link files, and `sbp-sub-sync.timer` checks every minute. It validates 20 base inbound ports and, when deployed, ten additional landing inbounds before regenerating subscriptions. The subscriber must update the subscription inside their client to receive the new ports. Existing URLs remain unchanged on the **same VPS** unless its IP or subscription domain changes. A **new VPS gets a new URL**, by design.

## Operations

```bash
bash /root/sing-box-plus.sh         # menu 4: rotate base 20 ports only
systemctl status sbp-sub-sync.path sbp-sub-sync.timer
journalctl -u sbp-sub-sync.service -n 30 --no-pager
cat /root/subscription-url.txt     # sensitive: keep private
systemctl status caddy
```

## Requirements / caveats

- Debian 13 + systemd + root access, public IPv4, Internet access, TCP 80/443 free, cloud firewall permits inbound TCP 80/443 plus required proxy-node TCP/UDP ports.
- The repository's conversion logic follows the linked upstream v4.8.0 format. Upstream upgrades may require adapting it.
- Script may overwrite the stock Caddy sample config. It refuses to overwrite an obviously non-default Caddyfile; review first.
- WARP requires a working `cloudflare-warp` proxy; verify it is healthy after installation.
- Original upstream Hysteria2 links may use `skip-cert-verify`; this has TLS security implications. Certain Xray versions need certificate-pinned variants instead.
- Most proxy clients do not share one universal subscription format; test connection in each actual client.
- No centralized API or third-party subscription converter receives node credentials. Credentials reside on VPS and are exposed to anyone who knows your subscription URL.
- Never paste node links/UUIDs/passwords into issues or Git commits. Rotate credentials if exposed.

**Sources:** https://github.com/Alvin9999-newpac/Sing-Box-Plus (third-party script); https://caddyserver.com/docs/automatic-https
## China-direct / international-proxy routing (2026 update)

The Mihomo `.clash.yaml` subscription includes CN-domain/CN-IP remote **MRS** rule providers maintained by [MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat). Private networks are DIRECT, common international services are explicitly routed to the selectable proxy group, CN domains/IPs are DIRECT, and the final MATCH uses the proxy group. Rule-provider refresh interval is 24h, independent from VPS port changes. A rule-provider download may fail if GitHub Raw is unreachable from the client; check the app's rule provider status.

Node-only Base64 subscriptions cannot reliably change per-client routing, so the same HTTPS site now publishes **additional** configuration files:
- `https://HOST/TOKEN.shadowrocket.conf`: Shadowrocket routing config referencing [blackmatrix7 China rules](https://github.com/blackmatrix7/ios_rule_script/tree/master/rule/Shadowrocket/China); **import as a configuration**, not as a node subscription. Continue using `.shadowrocket.txt` for nodes and select a proxy node.
- `https://HOST/TOKEN.v2rayn-routing.json`: v2rayN custom routing rules array following its [official format](https://github.com/2dust/v2rayN/wiki/Description-of-custom-routing-rules); **import/copy into the client's routing settings** separately from the `.txt` node subscription. Ensure routing geo-data are installed/up-to-date.
- `https://HOST/TOKEN.txt` and `TOKEN.shadowrocket.txt`: remain node lists with unchanged URL and format.

The additional configuration URLs contain the same private URL token. As before, do **not** publish actual URLs. International traffic defaults to proxy, not to DIRECT. Rules do not override proxy functionality, DNS leaks, or client service mode; verify routing from the specific client and network.

## Optional dual-VPS deployment: 20 base + 10 landing nodes

### Architecture and requirements

```text
Client -> VPS A (relay and subscriptions)
          |-- 10 base direct nodes -> A public exit
          |-- 10 WARP nodes -> Cloudflare WARP exit
          +-- 10 -landing nodes -> encrypted SS2022 link -> VPS B -> B public exit
```

| Item | VPS A (relay) | VPS B (landing exit) |
| --- | --- | --- |
| System | Debian 13, working base deployment and HTTPS subscriptions | Compatible Linux with systemd and root access; Debian 11 x86_64 ran Sing-Box 1.13.7 in the tested setup, but ordinary Debian 11 LTS has ended |
| Services | `sing-box.service`, `sing-box-landing.service`, Caddy, subscription sync | `sing-box-landing-exit.service` |
| Ports | Existing base ports, TCP 80/443, ten free landing inbound ports selected from 55000–55099 | TCP/UDP 24443, restricted to A's actual public source IP |
| Credentials | Existing 20 unchanged; independent credentials for the ten new nodes and A-to-B link | Shared A-to-B SS2022 key |
| Subscription | All client node addresses point to A; original URLs/token remain unchanged | No subscription server required |

Complete the base installation on A first. Ensure B can be reached by SSH from A and can run A's Sing-Box binary (matching CPU architecture and compatible OS). B's SSH address and actual Internet exit IPv4 can differ. **203.0.113.20 is a documentation-only address; replace it before running the following commands.** Verify the SSH host key; never include a root password in repository files.

### Step 1 — A: verify connectivity

```bash
# Replace this documentation-only address before executing.
LAND_HOST=203.0.113.20
LAND_SSH_PORT=22
ping -c 4 "$LAND_HOST"
ssh -p "$LAND_SSH_PORT" root@"$LAND_HOST"
# Exit the landing VPS to return to the relay VPS:
exit
```

### Step 2 — A: generate the SS2022 link and upload files

Run on A, with Python 3, Sing-Box and the SSH client installed. An existing link key is preserved, but staging configuration files are regenerated. Do not blindly repeat this procedure on an already deployed landing service.

```bash
umask 077
install -d -m 700 /root/sbp-landing

python3 - "$LAND_HOST" <<'PY'
import base64, ipaddress, json, secrets, sys
from pathlib import Path

host = str(ipaddress.IPv4Address(sys.argv[1]))
assert ipaddress.ip_address(host).is_global, "Set the real landing IPv4 first"
d = Path('/root/sbp-landing')
keyfile = d / 'key.txt'
if not keyfile.exists():
    keyfile.write_text(base64.b64encode(secrets.token_bytes(32)).decode())
key = keyfile.read_text().strip()
assert len(base64.b64decode(key, validate=True)) == 32
method = '2022-blake3-aes-256-gcm'
server = {
    'log': {'level': 'warn'},
    'inbounds': [{'type': 'shadowsocks', 'tag': 'landing-in',
                  'listen': '0.0.0.0', 'listen_port': 24443,
                  'method': method, 'password': key}],
    'outbounds': [{'type': 'direct', 'tag': 'direct'}],
    'route': {'final': 'direct'},
}
client = {
    'log': {'level': 'warn'},
    'inbounds': [{'type': 'socks', 'tag': 'test-in',
                  'listen': '127.0.0.1', 'listen_port': 19080}],
    'outbounds': [{'type': 'shadowsocks', 'tag': 'landing',
                   'server': host, 'server_port': 24443,
                   'method': method, 'password': key}],
    'route': {'final': 'landing'},
}
for path, data in [(d/'server.json', server), (d/'test-client.json', client)]:
    path.write_text(json.dumps(data, indent=2) + '\n')
    path.chmod(0o600)
keyfile.chmod(0o600)
print('Landing configuration generated.')
PY

# These are separate commands, not an SSH command inside a Bash heredoc.
ssh -n -p "$LAND_SSH_PORT" root@"$LAND_HOST" \
  'install -d -m 700 /root/sbp-landing-stage'
scp -P "$LAND_SSH_PORT" "$(command -v sing-box)" \
  root@"$LAND_HOST":/root/sbp-landing-stage/sing-box
scp -P "$LAND_SSH_PORT" /root/sbp-landing/server.json \
  root@"$LAND_HOST":/root/sbp-landing-stage/server.json

ssh -p "$LAND_SSH_PORT" root@"$LAND_HOST"
```

### Step 3 — B: install the landing exit

You should now be logged in to B. Check the upload and determine the actual public source IP of A:

```bash
echo "$SSH_CONNECTION" | awk '{print $1}'
ls -lh /root/sbp-landing-stage/
```

Restrict B's TCP/UDP 24443 in its provider/local firewall to that source IP. Preserve management access and do not flush the existing firewall. The following is for a **fresh landing service**; it copies the binary from A instead of depending on B's package repositories. If the binary is incompatible, use an appropriate official build before continuing.

```bash
bash <<'BASH'
set -euo pipefail
test ! -e /etc/systemd/system/sing-box-landing-exit.service || {
    echo "Landing service already exists; inspect it instead of overwriting."
    exit 1
}
install -d -m 700 /opt/sing-box-landing-exit
install -m 755 /root/sbp-landing-stage/sing-box \
  /usr/local/bin/sing-box-landing-exit
install -m 600 /root/sbp-landing-stage/server.json \
  /opt/sing-box-landing-exit/config.json

/usr/local/bin/sing-box-landing-exit version
/usr/local/bin/sing-box-landing-exit check \
  -c /opt/sing-box-landing-exit/config.json

cat > /etc/systemd/system/sing-box-landing-exit.service <<'EOF'
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

systemctl daemon-reload
systemctl enable --now sing-box-landing-exit.service
systemctl is-active sing-box-landing-exit.service
ss -lntup | grep 24443
BASH

# Return to relay VPS A.
exit
```

Expected: service active, TCP 24443 LISTEN and UDP 24443 UNCONN. A listening UDP socket is not a verified UDP forwarding test.

### Step 4 — A: verify the landing exit

```bash
bash <<'BASH'
set -euo pipefail
if [ -n "$(ss -H -lnt 'sport = :19080')" ]; then
    echo "Local test port 19080 is occupied."
    exit 1
fi
echo 'Relay direct IPv4:'
curl -4fsS --noproxy '*' --max-time 15 https://api.ipify.org
echo
sing-box check -c /root/sbp-landing/test-client.json
sing-box run -c /root/sbp-landing/test-client.json \
  > /root/sbp-landing/test.log 2>&1 &
pid=$!
trap 'kill "$pid" 2>/dev/null || true' EXIT
sleep 2
kill -0 "$pid"
echo 'Landing exit IPv4:'
curl -4fsS --noproxy '' --max-time 20 \
  --proxy socks5h://127.0.0.1:19080 https://api.ipify.org
echo
BASH
```

The second address must be B's actual public exit IPv4. Record it for the next step (it need not equal B's SSH address). If it fails, check A-to-B port access, B's service journal and A's private test log.

### Step 5 — A: add ten isolated landing inbounds

[`landing-install.py`](./landing-install.py) clones the ten base-direct protocol configurations, creates independent inbound authentication credentials, selects ten free ports, starts a separate service and checks the actual exit IP through one newly created SS2022 inbound. It rolls back the newly created service if deployment fails. It does not alter the base 20 nodes or install the B-side service. Existing landing directories/service units cause the installer to refuse to overwrite them.

```bash
cd /root
BASE=https://raw.githubusercontent.com/JLX2332326532/personal-note/main/vps-sing-box-subscriptions
curl -fL "$BASE/landing-install.py" -o /root/landing-install.py
# Replace with the actual IPv4 observed in the previous proxy test.
python3 /root/landing-install.py --expect-ip 203.0.113.20

systemctl is-active sing-box.service sing-box-landing.service
wc -l /opt/sing-box-landing/nodes.txt
```

Expect both services active and ten lines in the private landing node file. Permit the exact printed inbound ports/protocols in the provider and local firewall; use 55000–55009 only if those were actually allocated. Never expose the link key or generated node URLs.

### Step 6 — A: upgrade and verify subscriptions

```bash
BASE=https://raw.githubusercontent.com/JLX2332326532/personal-note/main/vps-sing-box-subscriptions
curl -fL "$BASE/auto-sync-install.sh" -o /root/sbp-sub-auto-install.sh
bash /root/sbp-sub-auto-install.sh

systemctl is-active sbp-sub-sync.path sbp-sub-sync.timer
journalctl -u sbp-sub-sync.service -n 30 --no-pager
```

The current sync installer detects the optional landing service and publishes 20 or 30 nodes without changing the existing URL/token. It monitors the base port file and the landing configuration/link files, with a one-minute fallback check. Invalid or incomplete landing files, a stopped landing service, or conflicting ports prevent publication; existing subscription files are retained until the problem is fixed.

```bash
python3 - <<'PY'
from pathlib import Path
from urllib.request import urlopen
import base64, yaml

url = Path('/root/subscription-url.txt').read_text().strip()
assert url.endswith('.txt')
for label, ext in [('v2rayN', '.txt'), ('Mihomo', '.clash.yaml'),
                   ('Shadowrocket', '.shadowrocket.txt')]:
    with urlopen(url[:-4] + ext, timeout=20) as r:
        raw = r.read()
    if label == 'Mihomo':
        data = yaml.safe_load(raw)
        names = [p['name'] for p in data['proxies']]
        assert sum(n.endswith('-landing') for n in names) == 10
        assert sum(n.endswith('-warp') for n in names) == 10
        count = len(names)
    else:
        count = len(base64.b64decode(raw, validate=True).decode().splitlines())
    print(label, count)
    assert count == 30
PY
```

Expect 30 for all three clients. Refresh existing subscriptions; no new subscription URL is necessary. Mihomo adds separate manual selectors for base direct, WARP and landing nodes (Chinese display labels: 直连节点, WARP节点, 住宅落地). The existing automatic URL-test group still contains only the original 20 nodes. Selecting the landing group does not fail over to A or WARP. Client-local DIRECT routing rules remain in effect; only traffic assigned to the proxy group uses the selected landing exit.

The A-to-B TCP connection and one new SS2022 landing inbound have been tested successfully in an existing deployment. Other protocols, UDP forwarding, client compatibility and full clean-server installation still require testing.

## Dual-VPS management reference

### Upstream management menu on A

Run `bash /root/sing-box-plus.sh`. This is the original upstream v4.8.0 menu; **no landing options have been added to it**.

| Option | Scope |
| --- | --- |
| 1 | Install/deploy the original 20 nodes |
| 2 | Show the original IPv4 node links, not the extra ten |
| 6 | Show base IPv6 links; the merged subscriptions currently use IPv4 |
| 3 | Restart the base service only |
| 4 | Rotate the base 20 ports only; the ten landing ports stay unchanged |
| 5 | Enable BBR on the current machine |
| 8 | Uninstall upstream base deployment, not the complete dual-VPS stack; may break landing dependencies/subscriptions |
| 0 | Exit |

There is currently no integrated menu for adding/replacing/removing B, automatic landing-port rotation, or one-command dual-VPS removal.

### Script and service responsibilities

| Script/service | Run on | Responsibility |
| --- | --- | --- |
| `install.sh` | A | Base Debian 13, Sing-Box-Plus, HTTPS and subscription setup |
| `landing-install.py --expect-ip <observed-exit-IP>` | A | One-time installation of ten landing inbounds; refuses overwrite |
| `auto-sync-install.sh` | A | Install/upgrade 20/30-node converter and sync units |
| `sbp_multi_sub.py` | A | Convert a prepared 20/30-node file; does not query active services or replace automatic sync |
| `/usr/local/sbin/sbp-sub-sync` | A | Synchronization worker; trigger through systemd |
| `sing-box.service` | A | Original 20 inbounds |
| `sing-box-landing.service` | A | Ten optional landing inbounds |
| `sing-box-landing-exit.service` | B | SS2022 landing exit |

On A:
```bash
systemctl status sing-box sing-box-landing caddy --no-pager
systemctl status sbp-sub-sync.path sbp-sub-sync.timer --no-pager
journalctl -u sing-box-landing.service -n 30 --no-pager
journalctl -u sbp-sub-sync.service -n 30 --no-pager
sing-box check -c /opt/sing-box-landing/config.json &&
  systemctl restart sing-box-landing.service
systemctl start sbp-sub-sync.service
```

On B:
```bash
systemctl status sing-box-landing-exit.service --no-pager
journalctl -u sing-box-landing-exit.service -n 30 --no-pager
/usr/local/bin/sing-box-landing-exit check -c /opt/sing-box-landing-exit/config.json &&
  systemctl restart sing-box-landing-exit.service
ss -lntup | grep 24443
```

Changing the landing server or shared link key requires coordinated changes to B's inbound, A's landing outbound and A's test-client configuration. Back up private configs and retest the exit before applying changes. Changing an extra inbound port requires consistent edits to A's landing config and link file (VMess stores the port inside Base64 JSON), firewall updates, a service restart and subscription sync. These changes are not automated by the current installer.

### Files and troubleshooting

| Host | Path | Purpose |
| --- | --- | --- |
| A | `/root/sbp-landing/key.txt` | Private A-to-B link key |
| A | `/root/sbp-landing/server.json` | Private staging config for B |
| A | `/root/sbp-landing/test-client.json` | Private test client config |
| A | `/opt/sing-box-landing/config.json` | Private ten-inbound/landing-outbound config |
| A | `/opt/sing-box-landing/nodes.txt` | Private extra ten node links |
| A | `/etc/systemd/system/sing-box-landing.service` | Landing inbound unit |
| B | `/root/sbp-landing-stage/` | Uploaded binary and private staging config |
| B | `/opt/sing-box-landing-exit/config.json` | Private exit config |
| B | `/usr/local/bin/sing-box-landing-exit` | Independent binary |
| B | `/etc/systemd/system/sing-box-landing-exit.service` | Exit service unit |

| Problem | Check |
| --- | --- |
| SSH hostname empty | Assign the actual landing IP to LAND_HOST; a read prompt is not a variable assignment |
| Uploaded binary missing | Run ssh -n and scp separately on A; interactive SSH can consume a Bash heredoc |
| AddressValueError | Ensure --expect-ip is a valid IPv4 with no stray characters |
| B service active but forwarding fails | A-to-B TCP/UDP 24443, firewall, SS2022 method/key and service logs |
| New clients cannot connect | A's actual landing inbound ports and firewall, refreshed subscription and client protocol support |
| Subscription still has 20 nodes | Install the latest sync script; inspect A's landing service, link file and sync journal |
| Subscription validation fails | Compare both sets of node names, addresses, ports and configs; retain validation rather than bypassing it |
| Landing selected but wrong exit | Select the landing group and a landing node, verify traffic actually matches a proxy rule, and avoid the base automatic group |

This guide uses only documentation example addresses. Production node links, passwords, UUIDs and tokens must remain private.
