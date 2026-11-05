# Sing-Box-Plus 20 nodes + three HTTPS subscriptions (Debian 13)

An installer for **your own Debian 13 VPS** based on the third-party [Sing-Box-Plus](https://github.com/Alvin9999-newpac/Sing-Box-Plus) v4.8.0 script. This project does not include a copy of your VPS credentials, UUID, subscriptions, tokens, or node links. This project is independent of upstream.

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

The systemd `sbp-sub-sync.path` service watches `/opt/sing-box/ports.env`, and `sbp-sub-sync.timer` checks every minute. It validates 20 inbound ports and regenerates subscriptions after changes. The subscriber must update the subscription inside their client to receive the new ports. Existing URLs remain unchanged on the **same VPS** unless its IP or subscription domain changes. A **new VPS gets a new URL**, by design.

## Operations

```bash
bash /root/sing-box-plus.sh         # menu 4: rotate all ports
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