# Sing-Box-Plus 一键部署与三格式订阅（中文）

[English README](./README.md) | [项目主页](./)

> 本项目为独立部署辅助脚本，并非 [Sing-Box-Plus](https://github.com/Alvin9999-newpac/Sing-Box-Plus) 官方项目。用于在 **Debian 13** VPS 上部署 20 个节点，并生成 v2rayN、Clash/Mihomo、Shadowrocket 三种 HTTPS 订阅。上游脚本可能变化，首次使用请先审阅脚本；尚未在所有 VPS 环境中进行端到端验证。

## 1. 项目功能

| 功能 | 说明 |
| --- | --- |
| 新机部署 | 安装依赖、第三方 Sing-Box-Plus、Caddy、systemd 订阅同步任务 |
| 20 个节点 | 10 个直连 + 10 个 WARP 出口节点，具体以原脚本实际生成结果为准 |
| v2rayN | Base64 订阅，`.txt` |
| Clash Verge Rev / Mihomo | YAML 配置，`.clash.yaml` |
| Shadowrocket | Base64 订阅，`.shadowrocket.txt` |
| 自动更新 | 监听端口文件，外加每分钟定时核对并重建三份订阅 |
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

## 5. 更换全部端口后自动同步

像以前一样进入节点管理菜单：

```bash
bash /root/sing-box-plus.sh
```

选择 `4) 一键更换所有端口`。系统会：

1. 修改 `/opt/sing-box/ports.env` 并更新 Sing-Box 服务；
2. 使用 `sbp-sub-sync.path` 检测变化，由 `sbp-sub-sync.timer` 每分钟兜底；
3. 校验生成的 20 条节点与服务端端口一致后，更新三份订阅文件；
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

如果已经有 `/root/nodes.txt`（20 条节点）、`/root/sub-token.txt` 和 `/srv/sbp-sub/`，可只转换出三种文件：

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

两处预期均为 **20**。此检查只能证明订阅文件可访问并包含 20 条节点，**不能代替客户端实际连接、协议兼容性、节点延迟及 WARP 出口测试**。

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
| [`install.sh`](./install.sh) | 新 Debian 13 VPS 部署入口 |
| [`auto-sync-install.sh`](./auto-sync-install.sh) | 安装转换器与 systemd 监控 |
| [`sbp_multi_sub.py`](./sbp_multi_sub.py) | 可独立运行的三格式转换器 |
| `/root/sing-box-plus.sh` | 第三方 Sing-Box-Plus 管理脚本 |
| `/opt/sing-box/ports.env` | 当前 20 个节点端口 |
| `/opt/sing-box/config.json` | Sing-Box 服务配置 |
| `/root/nodes.txt` | 20 条原始节点链接（敏感） |
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
