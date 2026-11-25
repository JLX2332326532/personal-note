# Sing-Box-Plus 20/30 节点一键部署与三格式订阅（中文）

[English README](./README.md) | [项目主页](./)

> 本项目为独立部署辅助脚本，并非 [Sing-Box-Plus](https://github.com/Alvin9999-newpac/Sing-Box-Plus) 官方项目。用于在 **Debian 13** VPS 上部署基础 20 个节点（双 VPS 扩展后 30 个），并生成 v2rayN、Clash/Mihomo、Shadowrocket 三种 HTTPS 订阅。上游脚本可能变化，首次使用请先审阅脚本；尚未在所有 VPS 环境中进行端到端验证。

## 1. 项目功能

| 功能 | 说明 |
| --- | --- |
| 新机部署 | 安装依赖、第三方 Sing-Box-Plus、Caddy、systemd 订阅同步任务 |
| 基础 20 个节点 | 10 个直连 + 10 个 WARP 出口节点，具体以原脚本实际生成结果为准 |
| 可选双 VPS 扩展 | 独立新增 10 个住宅落地节点，原有节点保留，合计 30 个；见第 12、13 节 |
| 统一管理 | `sbp-manager.sh` 提供 16 项操作，支持双 VPS 生命周期与 20/30 节点端口轮换；见第 14 节 |
| v2rayN | Base64 订阅，`.txt` |
| Clash Verge Rev / Mihomo | YAML 配置，`.clash.yaml` |
| Shadowrocket | Base64 订阅，`.shadowrocket.txt` |
| 自动更新 | 监听基础端口及可选落地配置/节点文件，每分钟定时核对，支持 20/30 节点 |
| 固定地址 | **同一台 VPS** 更换节点端口时，原来的订阅 URL/Token 保持不变 |

请注意：三种订阅格式指向同一组节点，并不意味着所有协议都兼容所有客户端。Clash 配置针对 Mihomo 内核，旧版 Clash 可能不支持 Reality、Hysteria2、TUIC、AnyTLS 等。

## 2. 部署前准备

- 系统：**Debian GNU/Linux 13 (Trixie)**，systemd、root 权限。
- 公网 IPv4 可用，能访问 Debian 软件仓库、GitHub Raw 和所需软件下载源。
- 服务商安全组与本机防火墙允许 TCP 80/443 入站；还要放行 Sing-Box 实际使用的 TCP、UDP 节点端口。
- TCP 80/443 未被其他网站或程序占用，便于 Caddy 自动申请 HTTPS 证书。
- 新 VPS 优先；已有自定义 Caddy 配置的 VPS 需手动合并站点配置，安装脚本会拒绝覆盖检测到的自定义配置。
- 默认通过 `<公网IPv4使用连字符>.sslip.io` 生成主机名，不必购买域名。但 sslip.io 为第三方 DNS 服务，其解析和 HTTPS 证书申请不保证永远成功。长期使用更建议自有域名。

## 3. 新 VPS 一键部署

使用 Xshell/SSH 以 root 登录 VPS，依次执行：

```bash
apt-get update && apt-get install -y curl ca-certificates

curl -fL \
  https://raw.githubusercontent.com/JLX2332326532/personal-note/main/vps-sing-box-subscriptions/install.sh \
  -o /root/install-sbp.sh

# 推荐先审阅脚本
less /root/install-sbp.sh

bash /root/install-sbp.sh
```

安装器会下载并执行第三方 Sing-Box-Plus 安装脚本，搭建 Sing-Box 服务、Caddy HTTPS 站点，并生成随机订阅 Token。随后自动安装节点提取与订阅转换同步服务。

**已有域名：** 提前将 DNS A 记录指向 VPS 公网 IPv4，然后运行：

```bash
SUB_DOMAIN=sub.example.com bash /root/install-sbp.sh
```

将 `sub.example.com` 换成自己的域名。HTTPS 申请需要 DNS 解析正确，以及 TCP 80/443 能从公网访问。部署日志可能包含节点凭据，**不要发布** `/root/sbp-deploy.log`。

## 4. 查看订阅地址

一键部署成功后，用下面的命令显示三个地址：

```bash
python3 - <<'PY'
from pathlib import Path
url = Path('/root/subscription-url.txt').read_text().strip()
assert url.endswith('.txt')
prefix = url[:-4]
print('v2rayN:       ', url)
print('Clash/Mihomo: ', prefix + '.clash.yaml')
print('Shadowrocket: ', prefix + '.shadowrocket.txt')
PY
```

形式示例（非真实订阅链接）：

```text
https://sub.example.com/随机密钥.txt
https://sub.example.com/随机密钥.clash.yaml
https://sub.example.com/随机密钥.shadowrocket.txt
```

导入方式：

1. **v2rayN：** 订阅分组 → 添加订阅 → 粘贴 `.txt` 地址 → 更新订阅。
2. **Clash Verge Rev：** 订阅/Profiles → 导入 URL → 粘贴 `.clash.yaml` 地址，选择配置。
3. **Shadowrocket：** 点击右上角加号 → 类型选择 Subscribe → 粘贴 `.shadowrocket.txt` 地址。

界面名称会随客户端版本变化。**Base64 不是加密**；任何拿到订阅 URL 的人都可能取得节点认证信息，订阅地址应视为敏感凭据。

## 5. 更换基础 20 个端口后自动同步

像以前一样进入节点管理菜单：

```bash
bash /root/sing-box-plus.sh
```

选择 `4) 一键更换所有端口`（上游菜单，仅更换基础 20 个端口；新增落地端口不变）。系统会：

1. 修改 `/opt/sing-box/ports.env` 并更新 Sing-Box 服务；
2. 使用 `sbp-sub-sync.path` 检测变化，由 `sbp-sub-sync.timer` 每分钟兜底；
3. 校验基础 20 条节点，并在启用落地扩展时校验新增 10 条节点，更新三份订阅文件；
4. **保持订阅域名和 Token 不变**。

然后在 v2rayN、Clash Verge Rev 或 Shadowrocket 中执行**更新订阅**。这不是服务端主动推送节点给客户端；客户端仍需更新才能获取新端口。

查看自动同步状态与日志：

```bash
systemctl is-active sbp-sub-sync.path
systemctl is-active sbp-sub-sync.timer
journalctl -u sbp-sub-sync.service -n 30 --no-pager
```

如需立即运行一次同步：

```bash
systemctl start sbp-sub-sync.service
journalctl -u sbp-sub-sync.service -n 30 --no-pager
```

**固定 URL 的范围：** 在同一台 VPS 上更新端口时不变。如果重装系统、换新 VPS、公网 IP 变更、域名变化，URL 不一定保持不变；新部署默认生成新 Token。

## 6. 已部署节点的 VPS 如何补装自动同步

仅当 VPS 已有以下路径时使用：

```text
/root/sing-box-plus.sh
/opt/sing-box/ports.env
/opt/sing-box/config.json
/root/sub-token.txt
/root/subscription-url.txt
/srv/sbp-sub/
```

运行：

```bash
curl -fL \
  https://raw.githubusercontent.com/JLX2332326532/personal-note/main/vps-sing-box-subscriptions/auto-sync-install.sh \
  -o /root/sbp-sub-auto-install.sh

bash /root/sbp-sub-auto-install.sh
```

该脚本**不重装节点，也不重新生成订阅网址**；需要你已搭建好 HTTPS 订阅发布环境。

### 单独使用转换器

如果已经有 `/root/nodes.txt`（20 或 30 条节点）、`/root/sub-token.txt` 和 `/srv/sbp-sub/`，可只转换出三种文件：

```bash
apt-get install -y python3 python3-yaml
curl -fL \
  https://raw.githubusercontent.com/JLX2332326532/personal-note/main/vps-sing-box-subscriptions/sbp_multi_sub.py \
  -o /root/sbp_multi_sub.py
python3 /root/sbp_multi_sub.py
```

`sbp_multi_sub.py` **只做格式转换**，不会安装 Caddy、监控任务或更换节点端口。需要持续自动更新时，应安装上面的 `auto-sync-install.sh`。

## 7. 验证订阅是否正常

```bash
systemctl status sing-box --no-pager
systemctl status caddy --no-pager
systemctl status sbp-sub-sync.path sbp-sub-sync.timer --no-pager
```

验证在线 v2rayN 订阅解码后的节点数量：

```bash
URL=$(cat /root/subscription-url.txt)
curl -fsS "$URL" | base64 -d | grep -c '://'
```

验证 Clash YAML 节点数量：

```bash
python3 - <<'PY'
from pathlib import Path
from urllib.request import urlopen
import yaml
u = Path('/root/subscription-url.txt').read_text().strip()
with urlopen(u[:-4] + '.clash.yaml', timeout=15) as r:
    data = yaml.safe_load(r.read())
print(len(data['proxies']))
PY
```

两处预期均为 **20（基础部署）或 30（双 VPS 扩展）**。此检查只能证明订阅文件可访问并包含预期节点数，**不能代替客户端实际连接、协议兼容性、节点延迟及 WARP 出口测试**。

## 8. 故障排查

| 现象 | 处理方法 |
| --- | --- |
| `curl: command not found` | `apt-get update && apt-get install -y curl ca-certificates` |
| `Could not get lock /var/lib/dpkg/lock-frontend` | 用 `ps` 检查 APT/dpkg 进程，等待已有任务完成；**不要直接删除锁文件** |
| HTTPS 证书申请失败或订阅打不开 | 检查 DNS、TCP 80/443、云防火墙，以及 `journalctl -u caddy -n 50 --no-pager` |
| 自动同步失败 | 查看 `journalctl -u sbp-sub-sync.service -n 50 --no-pager`；确认端口文件与配置一致 |
| 换端口后客户端无法连接 | 检查 Sing-Box 状态、TCP/UDP 节点端口放行，并在客户端更新订阅 |
| Clash 导入失败 | 确认使用支持对应节点协议的 Mihomo 版本 |
| WARP 出口不可用 | 分别测试直连/WARP，检查 Sing-Box-Plus 的 WARP SOCKS5 出口 |
| 新 VPS URL 与旧 VPS 不同 | 正常：公网 IP、订阅 Token 都可能不同 |

## 9. 主要脚本与文件

| 文件/路径 | 作用 |
| --- | --- |
| [`install.sh`](./install.sh) | 新 Debian 13 VPS 基础部署入口 |
| [`landing-install.py`](./landing-install.py) | A→B 链路验证后首次新增 10 个落地入站 |
| [`sbp-manager.sh`](./sbp-manager.sh) | 统一管理入口，自动加载本机 Python 核心 |
| [`sbp-manager.py`](./sbp-manager.py) | 统一管理核心，支持菜单 1–16 |
| [`auto-sync-install.sh`](./auto-sync-install.sh) | 安装转换器与 systemd 监控 |
| [`sbp_multi_sub.py`](./sbp_multi_sub.py) | 可独立运行的三格式转换器 |
| `/root/sing-box-plus.sh` | 第三方 Sing-Box-Plus 管理脚本 |
| `/opt/sing-box/ports.env` | 当前 20 个节点端口 |
| `/opt/sing-box/config.json` | Sing-Box 服务配置 |
| `/root/nodes.txt` | 20/30 条聚合节点链接（敏感） |
| `/root/sub-token.txt` | 随机订阅密钥（敏感） |
| `/root/subscription-url.txt` | 默认 HTTPS 订阅 URL（敏感） |
| `/srv/sbp-sub/` | Caddy 发布订阅的目录 |
| `/usr/local/sbin/sbp-sub-sync` | 自动同步执行脚本 |
| `/etc/systemd/system/sbp-sub-sync.{service,path,timer}` | systemd 自动同步服务单元 |

## 10. 安全说明

- 本仓库不应包含真实节点链接、UUID、密码、Token 或私有配置。**不要把生产订阅文件提交到公开仓库**。
- 已泄露节点认证信息需要轮换；**仅换端口不能撤销旧密码**。
- 部分原始 Hysteria2、TUIC、AnyTLS 节点设置了跳过证书校验，存在安全风险；支持时应使用有效证书或证书指纹校验。
- 订阅发布与格式转换均在自己的 VPS 上进行，不必上传节点凭据至第三方订阅转换网站。
- 上游安装脚本可能变更功能、目录或参数名。升级后应重新测试自动提取、端口校验及所有订阅格式。
- VPS 应及时更新软件、配置 SSH 密钥和防火墙，并遵守当地法律和云服务商条款。

---

参考：[Sing-Box-Plus 原项目](https://github.com/Alvin9999-newpac/Sing-Box-Plus) · [Caddy 自动 HTTPS](https://caddyserver.com/docs/automatic-https) · [English README](./README.md)

## 11. 大陆直连、境外代理分流规则（新增）

规则原则：**局域网直连 → 常用境外服务代理 → 中国大陆域名及 IP 直连 → 其余流量代理**。不同客户端的节点订阅格式不同，因此采用两种配置方式：

| 客户端 | 节点订阅 | 分流规则如何使用 |
| --- | --- | --- |
| Clash Verge Rev / Mihomo | 原有 `.clash.yaml` | **规则已内置**，客户端更新订阅后使用“规则”模式即可 |
| Shadowrocket | 原有 `.shadowrocket.txt` | **额外导入** `.shadowrocket.conf` 作为配置，再选择一个代理节点 |
| v2rayN | 原有 `.txt` | **额外导入** `.v2rayn-routing.json` 作为自定义路由规则（不是节点订阅）；确保 geosite/geoip 数据可用 |

**为什么不是把规则直接写进三个节点订阅？** v2rayN、Shadowrocket 的 Base64 节点列表只包含节点数据，不是路由策略文件。简单地在 Base64 文本里混入路由规则会破坏兼容性。本项目保留原来的三个订阅链接不变，并对这两个客户端提供独立的规则配置链接。

### 查看全部五个地址

```bash
python3 - <<'PY'
from pathlib import Path
url = Path('/root/subscription-url.txt').read_text().strip()
base = url.removesuffix('.txt')
for name, extension in [
    ('v2rayN 节点', '.txt'),
    ('Mihomo 节点+分流', '.clash.yaml'),
    ('Shadowrocket 节点', '.shadowrocket.txt'),
    ('Shadowrocket 分流配置', '.shadowrocket.conf'),
    ('v2rayN 自定义路由', '.v2rayn-routing.json'),
]:
    print(f'{name}: {base}{extension}')
PY
```

**规则来源：** Mihomo 使用 [MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat) 的 CN 域名及 CN IP 的 MRS 规则（客户端每24小时刷新一次）；Shadowrocket 使用 [blackmatrix7/ios_rule_script](https://github.com/blackmatrix7/ios_rule_script/tree/master/rule/Shadowrocket/China) 的 China.list 与 China_Domain.list；v2rayN 使用官方[自定义路由 JSON 规则格式](https://github.com/2dust/v2rayN/wiki/Description-of-custom-routing-rules)，包含 `geosite:cn`、`geoip:cn` 等条目。

**更新当前 VPS 的安装：** 从仓库重新下载并执行 `auto-sync-install.sh`，然后运行 `systemctl start sbp-sub-sync.service`；新 VPS 的 `install.sh` 会拉取最新版同步脚本。此操作保留原 Token 和原三个节点订阅地址，新增两份配套规则文件。

**使用限制：** 国内规则并不能保证所有网站的最终链路或 DNS 都完全按预期；需要客户端工作在支持规则的模式下。Mihomo 的远程规则从 GitHub Raw 下载，可能需要代理连接。v2rayN 自定义规则需手动导入，不能通过普通 Base64 节点订阅自动更新；Shadowrocket 配置也需要单独导入。规则源与内核协议可能变化，更新后请在实际客户端验证。

## 12. 双 VPS 部署：保留原 20 节点，新增 10 个住宅落地节点

### 12.1 拓扑、环境及端口

```text
客户端 → VPS A（中转 / HTTPS 订阅）
          ├─ 10 个基础直连节点 → A 的公网出口
          ├─ 10 个 WARP 节点 → Cloudflare WARP 出口
          └─ 10 个 -landing 节点 → SS2022 加密链路 → VPS B（住宅落地）→ B 的公网出口
```

| 项目 | VPS A：中转 | VPS B：落地 |
| --- | --- | --- |
| 系统 | Debian 13，已部署基础 20 节点及订阅 | 兼容的 Linux + systemd；Debian 11 x86_64 曾验证可运行 Sing-Box 1.13.7，但已结束常规 LTS，建议支持中的系统 |
| 服务 | `sing-box.service`、`sing-box-landing.service`、Caddy、同步组件 | `sing-box-landing-exit.service` |
| 入口端口 | 基础节点现有端口、HTTPS 80/443；新增 10 个端口从 55000–55099 选取 | TCP/UDP 24443（仅允许 A 的实际公网来源 IP 访问） |
| 凭据 | 原 20 节点不变；落地节点独立生成认证 UUID/密码；另有 A→B 密钥 | A→B 共享 SS2022 密钥 |
| 订阅 | 所有节点分享链接指向 A；原 URL/Token 不变 | 无需 Caddy 或订阅站点 |

先在 A 完成第 3 节部署。B 必须具有 root 权限、同 A 兼容的 CPU/运行环境，并允许 A 连接。B 的公网 SSH 地址与实际互联网出口地址可能不同。下文 `203.0.113.20` 为保留的文档示例 IP，**必须替换**，不是可以连接的服务器。先确认 SSH 主机指纹再登录；不需要把 root 密码写进命令。

### 12.2 A：检查连通性

```bash
# Replace this documentation-only address before executing.
LAND_HOST=203.0.113.20
LAND_SSH_PORT=22
ping -c 4 "$LAND_HOST"
ssh -p "$LAND_SSH_PORT" root@"$LAND_HOST"
# Exit the landing VPS to return to the relay VPS:
exit
```

### 12.3 A：生成独立 SS2022 链路并上传

仍在 A 上执行以下命令；不要在 B 上运行生成脚本。假定 A 已安装 Python 3、Sing-Box 和 SSH 客户端。重复执行会保留原有 `key.txt`，但会重新写入阶段配置；若已有正在运行的落地服务，不应未经检查重跑整个部署。

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

### 12.4 B：部署独立落地出口

现在终端应在 B。先确认文件已上传，查看 A 的实际 SSH 来源地址：

```bash
echo "$SSH_CONNECTION" | awk '{print $1}'
ls -lh /root/sbp-landing-stage/
```

在 B 的云防火墙/本机防火墙中，仅允许该来源 IPv4 访问 TCP/UDP 24443；保留 SSH 管理权限，不要直接清空防火墙规则。以下为**首次安装**，不会依赖 B 的旧 APT 软件源；复制的 Sing-Box 二进制必须兼容 B。若版本检查失败，应更换适配 B 的官方二进制，勿继续。

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

预期 `active`，且 TCP 24443 为 LISTEN、UDP 24443 为 UNCONN。UDP 监听成功不等于 UDP 转发已通过测试。

### 12.5 A：实测落地出口

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

第二个 IPv4 应为 B 的实际公网出口；记下它，下一步使用实测值，而不是盲目使用 SSH IP。若测试失败，检查 B 的 TCP/UDP 24443 防火墙、`journalctl -u sing-box-landing-exit.service -n 30 --no-pager`，以及 A 的 `/root/sbp-landing/test.log`（不要公开可能包含敏感信息的日志）。

### 12.6 A：安装 10 个落地节点

[landing-install.py](./landing-install.py) 读取 A 的基础直连入站及分享链接，克隆 10 种协议并生成独立认证凭据，选择 10 个空闲端口、建立独立服务。它保留原有 20 个节点，并通过新 SS2022 入站进行 TCP 出口 IP 实测；失败时回滚本次新增服务。该脚本**不是 B 的安装器**，也不是更新/重装工具；已有落地目录或服务单元时会拒绝覆盖。

```bash
cd /root
BASE=https://raw.githubusercontent.com/JLX2332326532/personal-note/main/vps-sing-box-subscriptions
curl -fL "$BASE/landing-install.py" -o /root/landing-install.py
# Replace with the actual IPv4 observed in the previous proxy test.
python3 /root/landing-install.py --expect-ip 203.0.113.20

systemctl is-active sing-box.service sing-box-landing.service
wc -l /opt/sing-box-landing/nodes.txt
```

预期两个服务均为 `active`，落地节点文件为 10 行。按脚本输出放行 A 的实际新增端口和监听协议；仅在确实分配 55000–55009 时才使用该范围。服务商安全组也需设置。不要将 B 的 SS2022 密钥或节点链接复制到公开仓库。原管理脚本更换端口时只修改基础 20 节点。

### 12.7 A：升级并验证三种订阅

```bash
BASE=https://raw.githubusercontent.com/JLX2332326532/personal-note/main/vps-sing-box-subscriptions
curl -fL "$BASE/auto-sync-install.sh" -o /root/sbp-sub-auto-install.sh
bash /root/sbp-sub-auto-install.sh

systemctl is-active sbp-sub-sync.path sbp-sub-sync.timer
journalctl -u sbp-sub-sync.service -n 30 --no-pager
```

新版同步程序会自动识别 20/30 节点，不重新生成订阅 URL 或 Token；同时监控基础端口、落地配置和落地节点文件，并在每分钟定时检查时校验。落地配置不完整、服务停止或端口冲突时拒绝发布，保留旧订阅，修复后再同步。

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

三个结果均应为 30。在客户端重新更新原订阅即可。Mihomo 新增「直连节点」「WARP节点」「住宅落地」三个手动策略组：住宅组只有落地节点，不会自动切换至 A/WARP；原「自动选择」仍仅包含基础 20 节点。国内直连规则仍优先生效，只有进入代理策略的流量才会使用所选落地出口。v2rayN 和 Shadowrocket 继续使用第 11 节独立路由配置。

已验证过 A→B 的 TCP 出口及新增 SS2022 入站的实际出口；其他协议、UDP 实际转发、全新环境的一键部署和客户端兼容性仍需逐项验证。

## 13. 管理脚本与服务操作（双 VPS）

### 13.1 原管理菜单的作用范围

在 A 执行 `bash /root/sing-box-plus.sh`。下列为原 Sing-Box-Plus v4.8.0 菜单，**未修改上游菜单**：

| 选项 | 操作及限制 |
| --- | --- |
| 1 | 安装/部署基础 20 节点；不负责 B 或新增落地服务 |
| 2 | 查看基础 20 个 IPv4 节点；不显示新增 10 个落地节点 |
| 6 | 查看基础 IPv6 节点；本项目合并订阅目前按 IPv4 处理 |
| 3 | 重启基础服务；落地服务需独立重启 |
| 4 | 仅更换基础 20 个端口；新增 10 个落地端口保持不变，订阅自动同步 |
| 5 | 开启 BBR（当前机器） |
| 8 | 上游基础服务卸载；**不是**整个双 VPS 项目的卸载程序，可能使落地依赖和订阅失效 |
| 0 | 退出 |

以上仅为**上游原菜单**。新增的独立统一管理器已实现落地添加、更换、删除和20/30节点端口轮换；请参阅第14节。原版菜单本身不变。

### 13.2 常用管理命令

| 脚本 / 服务 | 执行位置 | 功能 |
| --- | --- | --- |
| `install.sh` | A | Debian 13 基础节点、Caddy、订阅同步部署；不负责 B |
| `landing-install.py --expect-ip <实测出口IP>` | A | 首次新增 10 个落地节点，拒绝覆盖已有安装 |
| `auto-sync-install.sh` | A | 安装/升级 20/30 节点订阅转换器、监控和定时器 |
| `sbp_multi_sub.py` | A | 独立转换已提取的 20/30 条节点；不检查运行状态，不替代自动同步 |
| `/usr/local/sbin/sbp-sub-sync` | A | 自动同步执行器；推荐通过 systemd 手动触发 |
| `sing-box.service` | A | 基础 20 节点 |
| `sing-box-landing.service` | A | 新增 10 个落地入站 |
| `sing-box-landing-exit.service` | B | SS2022 落地出口 |

在 A：
```bash
systemctl status sing-box sing-box-landing caddy --no-pager
systemctl status sbp-sub-sync.path sbp-sub-sync.timer --no-pager
journalctl -u sing-box-landing.service -n 30 --no-pager
journalctl -u sbp-sub-sync.service -n 30 --no-pager

# 仅重启新增落地服务，先校验配置
sing-box check -c /opt/sing-box-landing/config.json &&
  systemctl restart sing-box-landing.service

# 手动同步，不更换订阅地址
systemctl start sbp-sub-sync.service
```

在 B：
```bash
systemctl status sing-box-landing-exit.service --no-pager
journalctl -u sing-box-landing-exit.service -n 30 --no-pager
/usr/local/bin/sing-box-landing-exit check -c /opt/sing-box-landing-exit/config.json &&
  systemctl restart sing-box-landing-exit.service
ss -lntup | grep 24443
```

更换 B 或链路密钥需要同时更新 B 入站及 A 的落地出站，并更新 A 的 `/root/sbp-landing/test-client.json`；更改前备份私有配置、校验并测试新出口，不能只改客户端订阅。若更换新增落地入站端口，需同步更新 `/opt/sing-box-landing/config.json` 与 `nodes.txt`（VMess 端口位于 Base64 JSON 内），检查防火墙并重启落地服务，再运行同步。现在可使用第14节的独立增强菜单执行端口轮换及落地切换；本段保留为手动维护参考。

### 13.3 新增文件路径及故障排查

| 机器 | 路径 | 说明 |
| --- | --- | --- |
| A | `/root/sbp-landing/key.txt` | 独立链路密钥（敏感） |
| A | `/root/sbp-landing/server.json` | B 的入站阶段配置（敏感） |
| A | `/root/sbp-landing/test-client.json` | 测试链路配置（敏感） |
| A | `/opt/sing-box-landing/config.json` | 10 个落地入站和落地出站（敏感） |
| A | `/opt/sing-box-landing/nodes.txt` | 新增 10 条分享链接（敏感） |
| A | `/etc/systemd/system/sing-box-landing.service` | 落地入站服务单元 |
| B | `/root/sbp-landing-stage/` | SCP 上传的二进制及阶段配置（配置敏感） |
| B | `/opt/sing-box-landing-exit/config.json` | SS2022 服务端入站配置（敏感） |
| B | `/usr/local/bin/sing-box-landing-exit` | 独立 Sing-Box 二进制 |
| B | `/etc/systemd/system/sing-box-landing-exit.service` | 落地出口服务单元 |

| 现象 | 排查方向 |
| --- | --- |
| SSH 报空主机名 | 将 IP 正确赋值给 LAND_HOST；read 的提示文字不是变量值 |
| SCP 文件缺失 | 回到 A，分别执行 ssh -n 和 scp；不要在 Bash heredoc 中混用会读取标准输入的 SSH 命令 |
| AddressValueError | 检查 --expect-ip 是否为合法 IPv4，删除粘贴时额外的 ~ 等字符 |
| B 服务已运行但链路失败 | 检查 A→B 的 24443 TCP/UDP、防火墙、SS2022 密钥与加密方式 |
| A 落地服务正常但客户端连不上 | 检查新增入站监听和 A 的云/本机防火墙，更新订阅并测试对应协议 |
| 订阅仍为 20 条 | 检查是否安装最新版同步脚本、A 的落地服务状态和 10 条节点文件；查看同步日志 |
| 订阅校验拒绝发布 | 核查两组节点名称、地址、端口与各自配置的一致性；不要强行删除校验 |
| 选择落地后 IP 仍是 A/WARP | 在 Mihomo 中选择住宅落地组和具体节点，确认流量命中代理规则；检查是否使用原自动选择组 |

所有示例均不包含真实服务器地址、认证密钥或订阅 Token。生产凭据留在各自 VPS，不提交 GitHub。

## 14. 统一增强管理菜单 v1.0

本项目提供独立的 `sbp-manager.sh` + `sbp-manager.py`。**不替换第三方 Sing-Box-Plus 菜单**，在 A（中转 VPS）运行；兼容原有 20/30 节点。启动菜单本身不会重装节点或改变订阅 Token。新部署的 `install.sh` 会尝试自动安装入口脚本。

### 14.1 已有 VPS 快速使用

```bash
curl -fL \
  https://raw.githubusercontent.com/JLX2332326532/personal-note/main/vps-sing-box-subscriptions/sbp-manager.sh \
  -o /root/sbp-manager.sh
# 执行前建议先阅读脚本及 Python 核心文件
bash /root/sbp-manager.sh
```

首次启动下载核心至 `/root/.sbp-manager/sbp-manager.py`，进行语法检查和离线自检，后续启动使用本地版本。检查版本、运行不修改节点的基础自检：

```bash
bash /root/sbp-manager.sh --version
bash /root/sbp-manager.sh --self-test
```

### 14.2 完整菜单

```text
Sing-Box-Plus 增强管理系统 v1.0.0
 1) 安装基础20节点及HTTPS订阅
 2) 查看全部IPv4节点分享链接
 3) 重启代理服务
 4) 一键更换全部20/30个节点端口
 5) 开启当前VPS的BBR
 6) 查看基础IPv6分享链接
 7) 添加落地 VPS
 8) 更换落地 VPS（保留入口）
 9) 删除落地 VPS 扩展（本机）
10) 测试 Direct/WARP/Landing 三组实际出口
11) 查看全部订阅及规则链接
12) 立即同步订阅 / 升级同步组件
13) 检查服务状态及同步日志
14) 更新管理脚本
15) 备份本机配置及订阅密钥
16) 恢复本机配置
 0) 退出
```

| 菜单 | 具体行为及注意事项 |
| --- | --- |
| 1 | 基础部署或补装 HTTPS 订阅。已有正常基础服务与订阅时不重装，改为同步现有配置。 |
| 2 | 从原脚本提取并校验基础 20 条 IPv4 链接，合并可选 10 条落地链接；确认后在本机终端显示敏感内容。 |
| 3 | 校验并重启 A 上基础、可选落地入站服务，再同步订阅。 |
| 4 | 为所有已部署的 20/30 个入站生成空闲新端口（基础 12000–44999，落地 55000–55099）。同步修改基础配置与 ports.env，更新落地配置与 URI/VMess 链接；备份、校验、重启、检查实际监听并同步。 |
| 5 | 在 A 启用 BBR/fq 并写入持久 sysctl 配置；不改变 B。 |
| 6 | 调用原脚本显示基础 IPv6 链接；落地入站目前只绑定 IPv4，合并订阅仍为 IPv4。 |
| 7 | 新增 10 个独立落地节点，保留基础 20 个。支持复用已准备的 test-client.json、输入现有 SS2022 落地服务密钥，或通过 SSH 自动在 B 安装独立 SS2022 服务。 |
| 8 | 先验证新 B 链路及预期出口，再更新 A 的落地出站；原 10 个入站端口、认证凭据、链接不变。测试或同步失败时尝试回滚 A 的配置。旧 B 默认继续运行，不会自动卸载。 |
| 9 | 备份并停用 A 的落地扩展，订阅恢复为 20 条；可另外确认通过 SSH 停用旧 B 上专用的落地出口服务，不删除 VPS、系统或配置。 |
| 10 | 通过各组真实 SS2022 入站访问公网 IP 查询服务，输出实际 Direct/WARP/Landing 出口；不代表全部协议或 UDP 已通过测试。 |
| 11 | 确认后展示三个节点订阅 URL 及 Shadowrocket/v2rayN 两个规则配置 URL。 |
| 12 | 强制重新生成订阅；可选择下载最新自动同步安装器。 |
| 13 | 查看代理、Caddy、同步组件状态和最近同步日志。 |
| 14 | 从 GitHub main 下载管理入口及 Python 核心，校验并执行离线自检后替换，退出菜单后重新运行生效；同步组件通过菜单 12 更新。 |
| 15 | 暂停订阅监控、等待同步结束，将本机项目配置、订阅文件/Token、选定的 systemd 单元和服务状态备份到 /root/sbp-backups/（仅 root 可访问）。 |
| 16 | 恢复同一台 VPS 的已有备份；恢复前生成救援备份，校验配置后启动相应服务，失败时尝试恢复救援备份。可能短暂中断代理及 HTTPS。 |

### 14.3 新增/更换 B 的操作

在 A 进入菜单 7 或 8，选择已有链路、已配置的 SS2022 服务、或 SSH 自动部署三种模式。现有测试配置位于 `/root/sbp-landing/test-client.json`。SSH 模式要求 B 具有 root 权限、兼容的 Linux/CPU 架构及 systemd；需要先核验主机指纹，并在 B 防火墙中仅允许 A 的实际来源 IP 访问 TCP/UDP 24443。脚本会提示输入 B 的公网连接 IPv4、实际出口 IPv4 和 SSH 端口；SSH 密码仅由 SSH 客户端交互读取，已有 SS2022 密钥使用不回显输入。新密钥随机生成，不写入 GitHub。

B 已存在独立服务时，自动部署模式拒绝覆盖；如要复用请选已有服务模式。新 B 的 SSH 部署成功而 A 的后续操作失败时，B 可能仍在运行，需要另行处理。更换落地时，旧 B 默认保留以便回退。删除操作默认只移除 A 上的落地扩展；明确确认后才会通过 SSH 停用 B 的独立服务，绝不删除租用的 VPS。

### 14.4 端口轮换、备份与恢复的边界

**请区分两个菜单：** 原 `sing-box-plus.sh` 的选项4只换基础20端口；增强管理器的选项4才换全部已安装的20/30个入站。管理器根据已知 v4.8.0 格式直接修改基础配置与 ports.env，检查原脚本分享链接是否一致；未知格式拒绝修改。端口轮换前会展示新端口并要求确认云防火墙已经放行。如果本机 UFW 启用，明确确认后会放行新 TCP/UDP 端口；旧规则不会自动删除。失败时尝试恢复原配置与订阅，但新增防火墙规则仍需人工检查。

备份仅面向 A，包含敏感节点凭据和 Token，放在本机 `/root/sbp-backups/`。**不要上传公开仓库。** 不包括 B 的远程状态、云/本机防火墙规则、Sing-Box/Caddy 软件二进制版本或 Caddy ACME 证书存储。恢复只适用于同一台机器；可能恢复旧订阅 Token、URL 和旧端口，需确认这些端口及 B 仍可用。备份不是可移植的全系统镜像。

管理脚本采用 GitHub main 作为更新源，首次运行和菜单14更新时执行语法检查及离线自检；生产环境的 SSH、端口轮换、恢复、客户端协议兼容性仍需实际测试。建议首次使用时先执行菜单13、10、15，确认状态、出口及备份，再进行菜单4或8等变更。
