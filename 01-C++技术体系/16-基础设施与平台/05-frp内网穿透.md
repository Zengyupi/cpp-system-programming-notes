# frp 内网穿透

> 本节目标：讲解 frp（fast reverse proxy）的架构原理、代理类型、配置与部署，学完后能够理解 frps/frpc 协作机制、掌握 tcp/udp/http/https/stcp/xtcp 代理配置、熟悉应用管理与端口分配、能够对比 ngrok/zerotier/wireguard 等方案并做出选型。对应岗位方向：运维开发、云原生、远程办公、物联网设备管理、内网服务暴露。

## 本章速览

- [1. frp 架构原理](#1-frp-架构原理)
  - [1.1 frps 与 frpc](#11-frps-与-frpc)
  - [1.2 TCPMUX 代理与 httpconnect 复用器](#12-tcpmux-代理与-httpconnect-复用器)
- [2. 支持的代理类型](#2-支持的代理类型)
- [3. 内网穿透流程](#3-内网穿透流程)
- [4. 配置文件详解](#4-配置文件详解)
  - [4.1 common 段](#41-common-段)
  - [4.2 代理配置段](#42-代理配置段)
  - [4.3 token 鉴权与 AuthServerConfig](#43-token-鉴权与-authserverconfig)
- [5. 应用管理](#5-应用管理)
  - [5.1 应用端口分配](#51-应用端口分配)
  - [5.2 配置生成与导出 yaml](#52-配置生成与导出-yaml)
- [6. 与其他内网穿透方案对比](#6-与其他内网穿透方案对比)
- [7. 安全考量](#7-安全考量)
- [8. 快速参考卡片](#8-快速参考卡片)
- [9. 常见问题与坑](#9-常见问题与坑)

---

## 1. frp 架构原理

frp 是一个开源的反向代理应用，专注于内网穿透，将内网服务暴露到公网。采用 C/S 架构，由服务端 frps 和客户端 frpc 组成。

### 1.1 frps 与 frpc

```text
                    公网
              ┌───────────────┐
   用户请求 ──→│   frps 服务端  │──→ 监听公网端口（如 7000 控制端口 + 业务端口）
              │  (有公网IP)    │
              └───────┬───────┘
                      │  frpc 主动建立长连接（控制连接 + 数据连接）
              ┌───────┴───────┐
              │   frpc 客户端  │──→ 连接内网本地服务
              │  (内网机器)    │
              └───────────────┘
                    内网
```

| 组件 | 角色 | 部署位置 |
| --- | --- | --- |
| **frps** | 服务端，监听公网端口，接收用户请求并转发 | 有公网 IP 的服务器 |
| **frpc** | 客户端，主动连接 frps，将请求转发到本地服务 | 内网机器（需穿透的设备） |

核心设计思想：**由内网侧 frpc 主动向外建立连接**，绕过 NAT/防火墙对入站连接的限制。frps 不主动连接 frpc，所有连接由 frpc 发起。

### 1.2 TCPMUX 代理与 httpconnect 复用器

frp v0.52+ 引入 **TCPMUX**（TCP Multiplexing）机制，在一条 TCP 连接上复用多个代理会话，减少连接建立开销：

```text
传统模式：每个代理请求建立一条独立 TCP 连接 frpc→frps
TCPMUX：  所有代理共享一条 TCP 连接，通过会话 ID 多路复用
```

**httpconnect 复用器**：frpc 通过 HTTP CONNECT 方法建立到 frps 的隧道，适用于需要通过 HTTP 代理服务器访问公网的环境（企业网络限制只能走 HTTP 代理）。frpc 配置 `httpProxy` 后，控制连接和数据连接都通过 HTTP CONNECT 隧道建立。

```ini
# frpc 通过 HTTP 代理连接 frps
[common]
server_addr = frps.example.com
server_port = 7000
httpProxy = http://proxy.company.com:8080
```

---

## 2. 支持的代理类型

| 类型 | 协议 | 说明 | 典型场景 |
| --- | --- | --- | --- |
| **tcp** | TCP | 最基础的 TCP 端口转发 | SSH、数据库、任意 TCP 服务 |
| **udp** | UDP | UDP 端口转发 | DNS、游戏服务器、VoIP |
| **http** | HTTP | HTTP 协议代理，支持虚拟主机、路由 | Web 服务、博客、API |
| **https** | HTTPS | HTTPS 协议代理（frps 做 TLS 终结或透传） | 加密 Web 服务 |
| **stcp** | Secret TCP | 加密 TCP 隧道，frps 不暴露公网端口，需另一个 frpc 访问 | 安全访问内网服务（不暴露公网端口） |
| **xtcp** | X TCP | P2P 穿透，尝试直连，失败回退 stcp | 大流量传输（减少 frps 带宽消耗） |

**stcp（Secret TCP）** 是 frp 的特色功能：frps 不为该代理开放公网监听端口，而是由访问方也运行一个 frpc（visitor 模式），通过 frps 做信令交换后建立加密隧道。相比普通 tcp 代理，stcp 不在公网暴露端口，安全性更高。

**xtcp** 尝试在两个 frpc 之间建立 P2P 直连（基于 UDP 打洞），成功后数据不经过 frps，节省服务器带宽；打洞失败时自动回退到 stcp 中继模式。

---

## 3. 内网穿透流程

以 TCP 代理为例，完整的请求转发流程：

```text
1. frpc 启动 → 主动连接 frps:7000（控制连接）
   → 注册代理信息（本地服务地址、远程端口）
   → frps 开始监听远程端口（如 6000）

2. 用户请求 → frps:6000
   → frps 接受连接，通过控制连接通知 frpc

3. frpc 收到通知 → 建立新的数据连接到 frps
   → 同时连接内网本地服务（如 127.0.0.1:22）

4. frps 将用户连接与 frpc 数据连接配对
   → 双向转发数据

5. 通信结束 → 连接关闭，frpc 保持控制连接等待下一个请求
```

```text
用户 ──→ frps:6000 ──(控制连接通知)──→ frpc
  ↑                                    │
  └──── 数据连接（frpc主动建立）←──────┘
       frpc ──→ 本地服务 127.0.0.1:22
```

关键点：
- 控制连接（frpc→frps:7000）是长连接，始终保持，用于信令；
- 每个用户请求触发一条新的数据连接（frpc→frps），与用户连接配对；
- TCPMUX 模式下，数据连接也复用控制连接。

---

## 4. 配置文件详解

frp 使用 INI 格式配置文件（frps.ini / frpc.ini），v0.52+ 也支持 TOML/YAML。

### 4.1 common 段

**frps.ini（服务端）：**

```ini
[common]
bind_port = 7000              # frpc 连接的控制端口
vhost_http_port = 8080        # HTTP 代理的监听端口
vhost_https_port = 8443       # HTTPS 代理的监听端口
dashboard_port = 7500         # 管理面板端口
dashboard_user = admin        # 面板用户名
dashboard_pwd = your_password # 面板密码
token = your_secret_token     # 鉴权令牌
max_pool_count = 5            # 连接池大小（预建数据连接）
subdomain_host = frps.example.com  # 子域名宿主（HTTP 代理用）
```

**frpc.ini（客户端）：**

```ini
[common]
server_addr = frps.example.com  # frps 公网地址
server_port = 7000              # frps 控制端口
token = your_secret_token       # 必须与 frps 一致
log_file = ./frpc.log
log_level = info
log_max_days = 3
```

### 4.2 代理配置段

每个代理以 `[代理名称]` 开头，名称在 frpc 内唯一：

```ini
# SSH 代理（TCP）
[ssh]
type = tcp
local_ip = 127.0.0.1
local_port = 22
remote_port = 6000              # frps 上暴露的端口

# Web 服务代理（HTTP）
[web]
type = http
local_port = 8080
custom_domains = web.example.com  # 虚拟主机域名
# 或使用子域名：subdomain = myapp → myapp.frps.example.com

# HTTPS 代理
[web_https]
type = https
local_port = 8443
custom_domains = secure.example.com

# UDP 代理（如 DNS）
[dns]
type = udp
local_port = 53
remote_port = 6053

# stcp 安全代理（不暴露公网端口）
[secret_ssh]
type = stcp
local_ip = 127.0.0.1
local_port = 22
sk = secret_key_for_stcp  # 访问方需使用相同的 sk

# xtcp P2P 代理
[p2p_file]
type = xtcp
local_ip = 127.0.0.1
local_port = 8000
sk = p2p_secret_key
```

**stcp 访问方配置（visitor 模式）：**

```ini
[common]
server_addr = frps.example.com
server_port = 7000
token = your_secret_token

[secret_ssh_visitor]
type = stcp
role = visitor          # 访问方角色
server_name = secret_ssh  # 对应服务端的代理名称
sk = secret_key_for_stcp  # 必须一致
bind_addr = 127.0.0.1
bind_port = 6001        # 本地监听端口，访问 127.0.0.1:6001 即连到内网 SSH
```

### 4.3 token 鉴权与 AuthServerConfig

frp 支持两种鉴权方式：

| 方式 | 配置 | 说明 |
| --- | --- | --- |
| **token** | `token = xxx` | 简单令牌，frpc 连接时携带，frps 校验 |
| **OIDC** | `authentication_method = oidc` | 基于 OpenID Connect，适合企业级统一认证 |

token 鉴权流程：
1. frpc 连接 frps 时，在握手阶段发送 token；
2. frps 校验 token 是否匹配；
3. 不匹配则拒绝连接。

> 生产环境必须设置 token，否则任何人都能连接 frps 注册代理，存在严重安全风险。

---

## 5. 应用管理

### 5.1 应用端口分配

在多租户或多应用场景下，需要管理 frps 上的远程端口分配，避免冲突：

```text
端口分配策略：
  固定端口段：为每个应用/用户分配一段端口范围（如 6000-6999）
  动态分配：frps 配置中不指定 remote_port，由 frps 自动分配空闲端口
  端口池：预分配端口池，应用启动时从池中获取，释放时归还

端口冲突检测：
  frps 启动时检查 remote_port 是否已被占用
  运行时新代理注册时检测端口冲突，冲突则拒绝并报错
```

frps Dashboard（默认端口 7500）提供 Web 界面查看当前代理列表、端口占用、流量统计。

### 5.2 配置生成与导出 yaml

在平台化管理中，通常通过 API 或模板动态生成 frpc 配置：

```yaml
# 应用配置模板（YAML 格式，由管理平台生成）
app:
  name: my-app
  frpc:
    common:
      server_addr: frps.example.com
      server_port: 7000
      token: ${FRP_TOKEN}
    proxies:
      - name: web
        type: http
        local_port: 8080
        custom_domains: my-app.example.com
      - name: ssh
        type: tcp
        local_port: 22
        remote_port: 6100
```

管理平台根据应用信息生成 frpc.ini 并下发到内网机器，支持：
- 模板变量替换（token、域名、端口）；
- 配置校验（端口范围、类型合法性）；
- 版本管理与回滚；
- 热更新（frpc 支持 `reload` 命令重新加载配置，无需重启）。

```bash
# 热更新 frpc 配置（不中断已有连接）
frpc reload -c ./frpc.ini
```

---

## 6. 与其他内网穿透方案对比

| 方案 | 架构 | 穿透方式 | P2P | 配置复杂度 | 适用场景 |
| --- | --- | --- | --- | --- | --- |
| **frp** | C/S 反向代理 | frpc 主动连 frps | xtcp 支持 | 低 | 通用内网服务暴露、TCP/UDP/HTTP |
| **ngrok** | C/S 反向代理 | 客户端主动连服务端 | 否 | 低 | 开发调试、Webhook 测试（官方服务付费） |
| **zerotier** | 虚拟局域网 | 组建虚拟二层网络 | 是（Planet 服务器辅助） | 中 | 多设备组网、远程办公、像在同一局域网 |
| **wireguard** | VPN | 加密隧道，需一端有公网IP | 否 | 中 | 站点间 VPN、高性能加密通道 |
| **Tailscale** | 虚拟局域网（基于 WireGuard） | 自动打洞+中继 | 是 | 低 | 零配置组网、企业远程访问 |
| **nps** | C/S 反向代理 | 类似 frp | 否 | 低 | 国产替代，功能类似 frp |

选型建议：
- **暴露单个内网服务到公网**：frp（灵活、开源、自托管）；
- **多设备像局域网一样互通**：zerotier / Tailscale；
- **站点间稳定 VPN 隧道**：wireguard；
- **开发临时调试**：ngrok（无需自己有公网服务器）。

---

## 7. 安全考量

| 风险 | 防护措施 |
| --- | --- |
| **未授权连接 frps** | 设置强 token，启用 OIDC；frps 控制端口限制来源 IP |
| **代理端口被扫描攻击** | stcp 替代 tcp（不暴露公网端口）；frps 前加防火墙白名单 |
| **数据明文传输** | frpc 与 frps 之间启用 TLS（`tls.enable = true`）；HTTP 代理用 HTTPS |
| **内网服务暴露面过大** | 只暴露必要端口；local_ip 绑定 127.0.0.1 而非 0.0.0.0 |
| **Dashboard 未授权访问** | 设置 dashboard_user/pwd；Dashboard 端口不暴露公网或加 IP 白名单 |
| **token 泄露** | token 定期轮换；使用配置管理工具加密存储；不同环境用不同 token |

frp v0.50+ 支持 TLS 配置：

```ini
# frpc.ini
[common]
tls.enable = true
tls.certFile = ./client.crt
tls.keyFile = ./client.key
tls.trustedCaFile = ./ca.crt
```

---

## 8. 快速参考卡片

```text
frps 配置模板：
  [common]
  bind_port = 7000
  vhost_http_port = 8080
  dashboard_port = 7500
  token = <强令牌>
  max_pool_count = 5

frpc 配置模板：
  [common]
  server_addr = <frps公网IP>
  server_port = 7000
  token = <与frps一致>
  [ssh] type=tcp local_port=22 remote_port=6000
  [web] type=http local_port=8080 custom_domains=<域名>

代理类型速查：
  tcp   → 任意TCP服务，remote_port 暴露公网
  udp   → UDP服务，remote_port 暴露公网
  http  → Web服务，custom_domains 虚拟主机
  https → 加密Web服务
  stcp  → 加密隧道，不暴露公网端口，需visitor端
  xtcp  → P2P直连（省带宽），失败回退stcp

启动命令：
  frps -c frps.ini          # 服务端
  frpc -c frpc.ini          # 客户端
  frpc reload -c frpc.ini   # 热更新配置
  frpc status -c frpc.ini   # 查看代理状态
```

## 9. 常见问题与坑

1. **frpc 连接 frps 超时**：检查 frps 的 `bind_port` 是否在防火墙/安全组放行；确认 server_addr 和 server_port 正确；frps 是否正常运行。
2. **HTTP 代理访问 404 / 路由到错误服务**：`custom_domains` 必须正确解析到 frps 公网 IP；多个 HTTP 代理的域名不能重复；确保访问的是 `vhost_http_port` 而非其他端口。
3. **remote_port 被占用**：frps 启动时报 "port already used"，更换端口或检查是否有其他进程占用；同一 frps 上多个代理不能使用相同 remote_port。
4. **stcp 连接失败**：visitor 端的 `server_name` 必须与服务端代理名称完全一致；`sk` 必须两端相同；visitor 端也需要能连接 frps。
5. **xtcp P2P 打洞成功率低**：xtcp 依赖 UDP 打洞，对称型 NAT 下基本失败，会自动回退 stcp；大流量场景建议评估带宽成本。
6. **frpc 断连后不自动重连**：frpc 默认有重连机制，但如果网络长时间中断，检查 `login_fail_exit`（设为 false 避免登录失败直接退出）；使用 systemd 等进程管理器保障运行。
7. **TCPMUX 导致连接异常**：部分旧版本 frps/frpc 不兼容 TCPMUX，可在 frpc 设置 `tcp_mux = false` 关闭；升级到最新版本通常解决。
8. **大流量时 frps 带宽瓶颈**：TCP 代理所有数据经过 frps，大文件传输会消耗服务器带宽；使用 xtcp 尝试 P2P，或部署多台 frps 负载均衡。
9. **HTTP 代理丢失客户端真实 IP**：frp 默认添加 `X-Forwarded-For` 头，后端服务需读取该头获取真实 IP；如果后端在 Nginx 后，需配置 `set_real_ip_from`。
10. **配置热更新不生效**：`frpc reload` 只能更新代理配置，不能修改 common 段（server_addr、token 等）；修改 common 段需重启 frpc。

---

上一篇：《04-P2P与NAT穿透.md》
下一篇：《06-RDMA高性能网络.md》
