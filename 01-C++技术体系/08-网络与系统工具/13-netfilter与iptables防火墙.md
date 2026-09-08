# netfilter 与 iptables 防火墙

> 本节目标：建立 Linux 网络包过滤与地址转换的完整知识体系——理解 netfilter 的 5 个 hook 点与 iptables 四表五链的关系、掌握规则匹配与 target 动作、熟练配置状态检测与 NAT、能够写出常用防火墙规则模板。网络抓包验证配合《02-tcpdump网络抓包.md》，连接跟踪参数调优见《10-Linux系统监控命令族.md》的 sysctl 部分。命令均在 WSL Ubuntu 24.04（iptables 1.8.10，nftables 兼容模式）实跑验证；WSL2 网络为 NAT 模式，部分 FORWARD/NAT 规则需在原生 Linux 网关环境验证。

## 本章速览

- [0. netfilter 架构](#0-netfilter-架构)
- [1. iptables 四表五链](#1-iptables-四表五链)
- [2. 规则匹配](#2-规则匹配)
- [3. 状态检测与 conntrack](#3-状态检测与-conntrack)
- [4. NAT 地址转换](#4-nat-地址转换)
- [5. 常用规则模板](#5-常用规则模板)
- [6. nftables 与 iptables 的关系](#6-nftables-与-iptables-的关系)
- [7. 快速参考卡片](#7-快速参考卡片)
- [8. 常见问题与坑](#8-常见问题与坑)

---

## 0. netfilter 架构

netfilter 是 Linux 内核中的网络包处理框架，在 IP 栈的 5 个关键位置放置了 hook（钩子），内核模块可以注册回调函数在这些点拦截和处理数据包。iptables 就是最常用的 netfilter 客户端。

### 0.1 五个 hook 点

```text
                    ┌─────────────────────────────────────────┐
                    │              网络协议栈                    │
                    │                                           │
  网卡收包 ──→ PREROUTING ──→ 路由判断 ──→ INPUT ──→ 本机进程
                    │              │
                    │              └──→ FORWARD ──→ POSTROUTING ──→ 网卡发包
                    │
  本机进程发包 ──→ OUTPUT ──→ 路由判断 ──→ POSTROUTING ──→ 网卡发包
```

| hook 点 | 触发时机 | 典型用途 |
| --- | --- | --- |
| `PREROUTING` | 包刚到达网卡，路由判断之前 | DNAT（端口转发）、修改目的地址 |
| `INPUT` | 路由判断后，目标是本机 | 入站过滤（防火墙） |
| `FORWARD` | 路由判断后，目标不是本机（转发） | 转发过滤（路由器/网关防火墙） |
| `OUTPUT` | 本机进程产生的包，路由判断之前 | 出站过滤、本机产生包的 DNAT |
| `POSTROUTING` | 路由判断后，包即将离开网卡 | SNAT/MASQUERADE（源地址转换） |

### 0.2 包处理流程

一个数据包从进入到离开，经过的 hook 点顺序：

- **入站到本机**：`PREROUTING` → `INPUT` → 进程
- **转发（本机做路由器）**：`PREROUTING` → `FORWARD` → `POSTROUTING`
- **本机出站**：`OUTPUT` → `POSTROUTING` → 网卡

> 关键：`PREROUTING` 在路由判断之前，所以此时还不知道包是去本机还是去转发；`INPUT` 和 `FORWARD` 是路由判断后的分支。

---

## 1. iptables 四表五链

iptables 用"表（table）"组织规则，每张表有若干"链（chain）"，链是规则的有序列表。包到达链时按顺序匹配，命中即执行 target，不再继续匹配（除了某些非终止 target）。

### 1.1 四张表

| 表 | 优先级 | 用途 | 包含的链 |
| --- | --- | --- | --- |
| `raw` | 最高 | 关闭连接跟踪（NOTRACK）、PREROUTING/OUTPUT 早期处理 | PREROUTING、OUTPUT |
| `mangle` | 高 | 修改包头部（TTL、TOS、MARK）、通用修改 | 全部 5 链 |
| `nat` | 中 | 地址转换（SNAT/DNAT/MASQUERADE/REDIRECT） | PREROUTING、INPUT、OUTPUT、POSTROUTING |
| `filter` | 低（默认表） | 包过滤（ACCEPT/DROP/REJECT/LOG） | INPUT、FORWARD、OUTPUT |

> 表的优先级：raw > mangle > nat（DNAT）> filter > mangle（POSTROUTING）> nat（SNAT）。同一个链上多张表的规则按表优先级执行。

### 1.2 表与链的关系图

```text
           raw        mangle       nat        filter
PREROUTING   ✓           ✓          ✓（DNAT）    —
INPUT        —           ✓          ✓            ✓
FORWARD      —           ✓          —            ✓
OUTPUT       ✓           ✓          ✓            ✓
POSTROUTING  —           ✓          ✓（SNAT）    —
```

### 1.3 基本命令

```bash
iptables -t 表名 -A 链名 匹配条件 -j 目标动作
```

| 操作 | 命令 |
| --- | --- |
| 追加规则 | `iptables -A CHAIN ...` |
| 插入规则（指定位置） | `iptables -I CHAIN 规则号 ...` |
| 删除规则 | `iptables -D CHAIN 规则号` 或 `iptables -D CHAIN 匹配条件` |
| 替换规则 | `iptables -R CHAIN 规则号 ...` |
| 查看规则 | `iptables -L -n -v --line-numbers` |
| 清空链 | `iptables -F CHAIN`（清空所有链用 `iptables -F`） |
| 清空指定表 | `iptables -t nat -F` |
| 删除自定义链 | `iptables -X CHAIN` |
| 设置默认策略 | `iptables -P CHAIN ACCEPT/DROP` |
| 保存规则 | `iptables-save > /etc/iptables/rules.v4` |
| 恢复规则 | `iptables-restore < /etc/iptables/rules.v4` |

实跑查看当前规则（WSL Ubuntu 24.04 默认空规则）：

```bash
$ iptables -L -n -v --line-numbers
Chain INPUT (policy ACCEPT 0 packets, 0 bytes)
num   pkts bytes target     prot opt in     out     source               destination

Chain FORWARD (policy ACCEPT 0 packets, 0 bytes)
num   pkts bytes target     prot opt in     out     source               destination

Chain OUTPUT (policy ACCEPT 0 packets, 0 bytes)
num   pkts bytes target     prot opt in     out     source               destination
```

> `-n` 不解析 IP/端口为域名/服务名（更快更准），`-v` 显示包数和字节数计数器，`--line-numbers` 显示规则编号（删除/替换时用）。

---

## 2. 规则匹配

### 2.1 基本匹配条件

| 匹配条件 | 含义 | 示例 |
| --- | --- | --- |
| `-p protocol` | 协议（tcp/udp/icmp/all） | `-p tcp` |
| `-s address` | 源 IP（可加 `/mask`） | `-s 192.168.1.0/24` |
| `-d address` | 目的 IP | `-d 10.0.0.5` |
| `-i interface` | 入站网卡 | `-i eth0` |
| `-o interface` | 出站网卡 | `-o eth1` |
| `!` | 取反 | `! -s 192.168.1.0/24` |

### 2.2 扩展匹配（tcp/udp）

```bash
# 需要 -p tcp 或 -p udp 后才能使用
-p tcp --sport 1024:65535        # 源端口范围
-p tcp --dport 80                  # 目的端口
-p tcp --dport 80,443              # 多端口（需 -m multiport）
-p tcp --tcp-flags SYN,ACK,FIN SYN   # TCP 标志位（SYN=1, ACK=0, FIN=0）
-p tcp --syn                        # 等价于 --tcp-flags SYN,RST,ACK SYN（只匹配 SYN 包）
-p tcp --dport 22 --tcp-flags ALL NONE  # 匹配 NULL 扫描（无标志位）
```

`--tcp-flags` 语法：`--tcp-flags 检查的标志位列表 必须为1的标志位列表`。例如 `--tcp-flags SYN,ACK SYN` 表示检查 SYN 和 ACK 位，其中 SYN 必须为 1，ACK 必须为 0。

### 2.3 其他扩展匹配

| 扩展模块 | 用途 | 示例 |
| --- | --- | --- |
| `-m multiport` | 多端口匹配 | `-m multiport --dports 80,443,8080` |
| `-m iprange` | IP 范围 | `-m iprange --src-range 192.168.1.10-192.168.1.20` |
| `-m mac` | MAC 地址 | `-m mac --mac-source 00:11:22:33:44:55` |
| `-m string` | 包内容字符串匹配 | `-m string --string "admin" --algo bm` |
| `-m time` | 时间匹配 | `-m time --timestart 09:00 --timestop 18:00 --weekdays Mon-Fri` |
| `-m connlimit` | 连接数限制 | `-m connlimit --connlimit-above 10` |
| `-m limit` | 速率限制 | `-m limit --limit 10/min --limit-burst 20` |
| `-m state` | 连接状态（旧） | `-m state --state ESTABLISHED` |
| `-m conntrack` | 连接状态（新，推荐） | `-m conntrack --ctstate ESTABLISHED` |
| `-m mark` | 匹配包标记 | `-m mark --mark 0x1` |
| `-m owner` | 匹配进程属主（OUTPUT 链） | `-m owner --uid-owner 1000` |

### 2.4 target 动作

| target | 适用表 | 含义 |
| --- | --- | --- |
| `ACCEPT` | filter | 放行包 |
| `DROP` | filter | 丢弃包（不回应，对端超时） |
| `REJECT` | filter | 拒绝并回应（默认 ICMP port-unreachable，`--reject-with tcp-reset` 发 RST） |
| `LOG` | 任意 | 记录日志到 syslog（非终止 target，继续匹配后续规则） |
| `SNAT` | nat（POSTROUTING） | 源地址转换为指定 IP |
| `MASQUERADE` | nat（POSTROUTING） | 源地址转换为出站网卡 IP（动态 IP 场景） |
| `DNAT` | nat（PREROUTING/OUTPUT） | 目的地址转换 |
| `REDIRECT` | nat（PREROUTING/OUTPUT） | 重定向到本机端口（透明代理） |
| `MARK` | mangle | 给包打标记（供后续规则/路由使用） |
| `RETURN` | 任意 | 从自定义链返回调用链 |
| `自定义链名` | 任意 | 跳转到自定义链 |

> `DROP` vs `REJECT`：`DROP` 静默丢弃，对端会超时等待（通常 30s-2min），适合防火墙隐藏；`REJECT` 立即回应拒绝，对端快速失败，适合内部网络快速报错。对外防火墙通常用 DROP，内部服务不可用时用 REJECT。

---

## 3. 状态检测与 conntrack

### 3.1 连接跟踪状态

conntrack（连接跟踪）是 netfilter 的核心子系统，跟踪每个连接的状态，使 iptables 可以基于"连接状态"而非"单个包"做决策。

| 状态 | 含义 |
| --- | --- |
| `NEW` | 新连接的第一个包（如 TCP SYN） |
| `ESTABLISHED` | 已建立连接的包（双向都有流量后） |
| `RELATED` | 与已有连接相关的新连接（如 FTP 数据连接、ICMP 错误） |
| `INVALID` | 无法识别的包（不属于任何已知连接，或状态异常） |
| `UNTRACKED` | raw 表中用 `NOTRACK` 标记的包（不被 conntrack 跟踪） |

### 3.2 状态匹配规则

```bash
# 放行已建立连接的包（最常用的规则，放在最前面提高效率）
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# 丢弃无效包
iptables -A INPUT -m conntrack --ctstate INVALID -j DROP

# 只允许新的入站 SSH 连接
iptables -A INPUT -p tcp --dport 22 -m conntrack --ctstate NEW -j ACCEPT
```

> 状态检测的效率优势：`ESTABLISHED` 规则放在最前面，已建立连接的包直接命中放行，不需要遍历后续所有端口规则。高并发服务器上这能显著减少规则匹配开销。

### 3.3 conntrack 表管理

```bash
# 查看当前连接跟踪表
cat /proc/net/nf_conntrack | head -5
# 输出示例：
# ipv4     2 tcp      6 43199 ESTABLISHED src=192.168.1.10 dst=10.0.0.5 sport=54321 dport=80 src=10.0.0.5 dst=192.168.1.10 sport=80 dport=54321 [ASSURED] mark=0 zone=0 use=2

# 连接数统计
cat /proc/sys/net/netfilter/nf_conntrack_count

# 连接表最大条目
cat /proc/sys/net/netfilter/nf_conntrack_max

# 调大连接表（运行时）
sysctl -w net.netfilter.nf_conntrack_max=1048576

# 查看各状态超时
sysctl -a | grep nf_conntrack_tcp_timeout
```

conntrack 表条目结构解读：

```text
ipv4  2  tcp  6  43199  ESTABLISHED  src=... dst=... sport=... dport=...  [ASSURED]
│     │  │    │   │      │              │                                    │
│     │  │    │   │      │              │                                    └─ ASSURED=确认不会被淘汰
│     │  │    │   │      │              └─ 五元组（双向各一组）
│     │  │    │   │      └─ 连接状态
│     │  │    │   └─ 剩余超时时间（秒）
│     │  │    └─ 协议号（6=TCP）
│     │  └─ 传输层协议
│     └─ 协议族编号
└─ 网络层协议
```

> conntrack 表满是高频线上事故：`dmesg | grep "nf_conntrack: table full"`，表现为新连接建立失败或延迟。调大 `nf_conntrack_max`，或缩短 `nf_conntrack_tcp_timeout_established`（默认 432000 秒=5天，对短连接服务太长）。详见《10-Linux系统监控命令族.md》sysctl 部分。

---

## 4. NAT 地址转换

### 4.1 SNAT / MASQUERADE — 源地址转换

**SNAT**：把包的源 IP 改为指定 IP，用于内网机器通过网关访问外网（共享公网 IP）。

```bash
# 网关机器上：把来自 192.168.1.0/24 的包源地址改为公网 IP 1.2.3.4
iptables -t nat -A POSTROUTING -s 192.168.1.0/24 -o eth0 -j SNAT --to-source 1.2.3.4
```

**MASQUERADE**：把源 IP 改为出站网卡的 IP（自动获取），适用于拨号/动态 IP 场景（如家庭路由器、4G 网卡）。

```bash
# 动态公网 IP 场景：源地址改为 eth0 的当前 IP
iptables -t nat -A POSTROUTING -s 192.168.1.0/24 -o eth0 -j MASQUERADE
```

> SNAT vs MASQUERADE：SNAT 性能略好（不需要每次查网卡 IP），适合固定公网 IP；MASQUERADE 适合动态 IP，网卡断开时会自动清除连接跟踪。生产环境固定 IP 用 SNAT。

### 4.2 DNAT / REDIRECT — 目的地址转换

**DNAT**：把包的目的 IP/端口改为指定值，用于端口转发（外网访问内网服务）。

```bash
# 网关机器上：外网访问 1.2.3.4:8080 转发到内网 192.168.1.10:80
iptables -t nat -A PREROUTING -d 1.2.3.4 -p tcp --dport 8080 -j DNAT --to-destination 192.168.1.10:80

# 配合 FORWARD 链放行
iptables -A FORWARD -d 192.168.1.10 -p tcp --dport 80 -j ACCEPT
```

**REDIRECT**：把包重定向到本机的指定端口，用于透明代理（如把所有 80 端口流量重定向到代理程序的 3128 端口）。

```bash
# 把入站 80 端口流量重定向到本机 3128（透明代理）
iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-ports 3128

# 本机产生的包也重定向（OUTPUT 链）
iptables -t nat -A OUTPUT -p tcp --dport 80 -j REDIRECT --to-ports 3128
```

> DNAT 在 PREROUTING 链做（包刚到达，路由判断之前改目的地址），SNAT 在 POSTROUTING 链做（路由判断后，包离开前改源地址）。顺序不能反。

### 4.3 完整的端口转发示例

```bash
# 场景：网关有公网 IP 1.2.3.4，内网 Web 服务器 192.168.1.10:80
# 目标：外网访问 1.2.3.4:8080 → 内网 192.168.1.10:80

# 1. 开启 IP 转发（网关必须）
sysctl -w net.ipv4.ip_forward=1
echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf

# 2. DNAT：改目的地址
iptables -t nat -A PREROUTING -d 1.2.3.4 -p tcp --dport 8080 -j DNAT --to-destination 192.168.1.10:80

# 3. FORWARD 放行（默认策略如果是 DROP）
iptables -A FORWARD -d 192.168.1.10 -p tcp --dport 80 -j ACCEPT
iptables -A FORWARD -s 192.168.1.10 -p tcp --sport 80 -j ACCEPT
# 或者用状态检测一条搞定：
iptables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# 4. SNAT/MASQUERADE：内网回包的源地址改为网关 IP（如果内网机器网关不是本机则需要）
iptables -t nat -A POSTROUTING -s 192.168.1.0/24 -o eth0 -j MASQUERADE
```

---

## 5. 常用规则模板

### 5.1 防火墙初始配置（推荐基线）

```bash
#!/bin/bash
# /etc/iptables/firewall.sh

# 清空旧规则
iptables -F
iptables -t nat -F
iptables -t mangle -F
iptables -X

# 默认策略：全部 DROP（白名单模式）
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT ACCEPT    # 出站默认放行，如需管控改为 DROP

# 放行回环接口
iptables -A INPUT -i lo -j ACCEPT
iptables -A OUTPUT -o lo -j ACCEPT

# 放行已建立连接和相关连接
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# 丢弃无效包
iptables -A INPUT -m conntrack --ctstate INVALID -j DROP

# 放行 ICMP（ping，可选；生产环境可限制速率）
iptables -A INPUT -p icmp --icmp-type echo-request -m limit --limit 10/s --limit-burst 20 -j ACCEPT

# 放行 SSH（建议改非默认端口 + 限制源 IP）
iptables -A INPUT -p tcp --dport 22 -m conntrack --ctstate NEW -s 192.168.1.0/24 -j ACCEPT

# 放行 HTTP/HTTPS
iptables -A INPUT -p tcp --dport 80 -m conntrack --ctstate NEW -j ACCEPT
iptables -A INPUT -p tcp --dport 443 -m conntrack --ctstate NEW -j ACCEPT

# 记录被丢弃的包（日志量可能大，生产环境慎用或加采样）
iptables -A INPUT -m limit --limit 5/min -j LOG --log-prefix "iptables DROP: " --log-level 7

# 保存规则
iptables-save > /etc/iptables/rules.v4
```

### 5.2 限制连接速率（防 CC 攻击）

```bash
# 限制每个 IP 到 80 端口的新连接速率：每秒最多 20 个，突发 40
iptables -A INPUT -p tcp --dport 80 -m conntrack --ctstate NEW -m limit --limit 20/s --limit-burst 40 -j ACCEPT
iptables -A INPUT -p tcp --dport 80 -m conntrack --ctstate NEW -j DROP

# 限制每个 IP 的并发连接数（到 80 端口最多 50 个）
iptables -A INPUT -p tcp --dport 80 -m connlimit --connlimit-above 50 -j REJECT --reject-with tcp-reset

# 限制单个 IP 的总并发连接数（所有端口）
iptables -A INPUT -p tcp -m connlimit --connlimit-above 100 -j DROP
```

### 5.3 防止常见扫描

```bash
# 丢弃 NULL 扫描（无 TCP 标志位）
iptables -A INPUT -p tcp --tcp-flags ALL NONE -j DROP

# 丢弃 XMAS 扫描（FIN+URG+PUSH）
iptables -A INPUT -p tcp --tcp-flags ALL FIN,URG,PSH -j DROP

# 丢弃 SYN+FIN（非法组合）
iptables -A INPUT -p tcp --tcp-flags SYN,FIN SYN,FIN -j DROP

# 丢弃 SYN+RST（非法组合）
iptables -A INPUT -p tcp --tcp-flags SYN,RST SYN,RST -j DROP

# 限制 SYN 包速率（防 SYN Flood）
iptables -A INPUT -p tcp --syn -m limit --limit 100/s --limit-burst 200 -j ACCEPT
iptables -A INPUT -p tcp --syn -j DROP
```

### 5.4 端口转发模板

```bash
# 外网 8080 → 内网 192.168.1.10:80
iptables -t nat -A PREROUTING -p tcp --dport 8080 -j DNAT --to-destination 192.168.1.10:80
iptables -A FORWARD -d 192.168.1.10 -p tcp --dport 80 -j ACCEPT

# 本机 80 → 本机 8080（本地端口重定向）
iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-ports 8080
```

---

## 6. nftables 与 iptables 的关系

### 6.1 nftables 是什么

nftables 是 Linux 内核 3.13 引入的新一代网络包过滤框架，设计用来替代 iptables。它的优势：

| 特性 | iptables | nftables |
| --- | --- | --- |
| 命令行工具 | `iptables` / `ip6tables` / `arptables` / `ebtables`（4 套） | `nft`（统一一套） |
| 规则集更新 | 每次全量替换（`iptables-restore`） | 增量更新（原子操作） |
| 数据结构 | 固定的 match/target 扩展 | 通用的 set/map/ verdict map（更灵活） |
| IPv4/IPv6 | 分开维护（iptables + ip6tables） | 统一地址族（`ip` / `ip6` / `inet` / `bridge`） |
| 性能 | 每条规则线性匹配 | 集合查找（O(1)），大规则集性能更好 |
| 内核 API | 旧的 `getsockopt`/`setsockopt` | 新的 `netlink`（nf_tables） |

### 6.2 iptables-nft 兼容层

Ubuntu 20.04+ 和 Debian 11+ 默认使用 `iptables-nft`——iptables 命令的后端是 nftables 内核子系统。也就是说，输入的是 iptables 语法，内核执行的是 nftables。

```bash
# 查看当前 iptables 后端
$ iptables --version
iptables v1.8.10 (nf_tables)    # ← nftables 后端
# iptables v1.8.10 (legacy)      # ← 传统 xtables 后端

# 用 nft 查看当前规则（iptables-nft 模式下可以看到 iptables 生成的 nft 规则）
nft list ruleset
```

### 6.3 nftables 基础语法

```bash
# 查看规则集
nft list ruleset

# 新建表（inet = IPv4+IPv6 统一）
nft add table inet filter

# 新建链（hook 点 + 优先级 + 默认策略）
nft add chain inet filter input '{ type filter hook input priority 0 ; policy drop ; }'

# 添加规则
nft add rule inet filter input ct state established,related accept
nft add rule inet filter input iif lo accept
nft add rule inet filter input tcp dport 22 accept
nft add rule inet filter input tcp dport {80, 443} accept    # 集合（多端口）

# 保存/恢复
nft list ruleset > /etc/nftables.conf
nft -f /etc/nftables.conf
```

> 迁移建议：新系统可以直接学 nftables；但 iptables 语法在文档、教程、运维脚本中仍然广泛使用，且 iptables-nft 兼容层让 iptables 命令继续可用。掌握 iptables 四表五链模型后，迁移到 nftables 主要是语法变化，核心概念（hook 点、链、规则、状态检测、NAT）一致。

---

## 7. 快速参考卡片

### 7.1 表链关系图

```text
包流程：
  入站本机：  PREROUTING → INPUT → 进程
  转发：      PREROUTING → FORWARD → POSTROUTING
  本机出站：  OUTPUT → POSTROUTING

表 × 链：
           raw   mangle   nat(DNAT)   filter   nat(SNAT)
PREROUTING  ✓      ✓        ✓           —        —
INPUT       —      ✓        ✓           ✓        —
FORWARD     —      ✓        —           ✓        —
OUTPUT      ✓      ✓        ✓           ✓        —
POSTROUTING —      ✓        —           —        ✓

优先级（同链多表）：raw > mangle > nat > filter
```

### 7.2 常用命令速查

```bash
# 查看
iptables -L -n -v --line-numbers              # filter 表
iptables -t nat -L -n -v --line-numbers       # nat 表
iptables -t mangle -L -n                        # mangle 表

# 增删
iptables -A INPUT -p tcp --dport 80 -j ACCEPT    # 追加
iptables -I INPUT 1 -p tcp --dport 443 -j ACCEPT  # 插入到第1条
iptables -D INPUT 3                                  # 删除第3条
iptables -R INPUT 2 -p tcp --dport 8080 -j ACCEPT # 替换第2条

# 策略与清空
iptables -P INPUT DROP                          # 默认策略
iptables -F INPUT                                # 清空 INPUT 链
iptables -F                                      # 清空所有链（filter）
iptables -t nat -F                               # 清空 nat 表

# 保存恢复
iptables-save > /etc/iptables/rules.v4
iptables-restore < /etc/iptables/rules.v4

# conntrack
cat /proc/sys/net/netfilter/nf_conntrack_count   # 当前连接数
cat /proc/sys/net/netfilter/nf_conntrack_max     # 最大连接数
sysctl -w net.netfilter.nf_conntrack_max=1048576
```

### 7.3 常用规则模板

```bash
# 【基线防火墙】
iptables -P INPUT DROP
iptables -A INPUT -i lo -j ACCEPT
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A INPUT -m conntrack --ctstate INVALID -j DROP
iptables -A INPUT -p tcp --dport 22 -s 192.168.1.0/24 -j ACCEPT
iptables -A INPUT -p tcp --dport 80 -j ACCEPT
iptables -A INPUT -p tcp --dport 443 -j ACCEPT

# 【SNAT 共享上网】
sysctl -w net.ipv4.ip_forward=1
iptables -t nat -A POSTROUTING -s 192.168.1.0/24 -o eth0 -j MASQUERADE

# 【DNAT 端口转发】
iptables -t nat -A PREROUTING -p tcp --dport 8080 -j DNAT --to-destination 192.168.1.10:80
iptables -A FORWARD -d 192.168.1.10 -p tcp --dport 80 -j ACCEPT

# 【速率限制】
iptables -A INPUT -p tcp --dport 80 -m conntrack --ctstate NEW -m limit --limit 20/s --limit-burst 40 -j ACCEPT
iptables -A INPUT -p tcp --dport 80 -m connlimit --connlimit-above 50 -j REJECT

# 【透明代理】
iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-ports 3128
```

---

## 8. 常见问题与坑

1. **规则顺序很重要**：包按链中规则顺序匹配，命中即停（非终止 target 除外）。`ESTABLISHED,RELATED` 放行规则必须放在最前面，否则已建立连接的包会遍历所有规则浪费 CPU；`DROP` 规则要放在对应 `ACCEPT` 之前。
2. **默认策略 DROP 后把自己锁在外面**：配置远程服务器防火墙时，先确保 SSH 规则已添加再设置 `INPUT DROP`；或者用 `iptables-apply`（5 分钟未确认自动回滚）防止锁死。
3. **iptables 规则重启丢失**：`iptables` 命令修改的是运行时规则，重启后丢失；必须 `iptables-save` 保存到文件，并用 `iptables-persistent`（Debian/Ubuntu）或 `iptables-services`（CentOS）服务开机加载。
4. **FORWARD 链默认 ACCEPT 但转发不通**：转发需要同时满足：① `net.ipv4.ip_forward=1`（开启 IP 转发）；② FORWARD 链放行；③ POSTROUTING 有 SNAT/MASQUERADE（如果内网机器网关不是本机）。三者缺一不可。
5. **DNAT 后回包不通**：DNAT 只改了入站包的目的地址，内网服务器回包的源地址还是内网 IP；如果客户端在外网，回包路由不到客户端，需要在网关上做 SNAT/MASQUERADE，或者让内网服务器的网关指向本机。
6. **conntrack 表满**：高并发服务器上 `nf_conntrack_max` 默认值（通常 65536 或 262144）不够，新连接被丢；调大 `nf_conntrack_max` 并缩短 `nf_conntrack_tcp_timeout_established`。`dmesg | grep "nf_conntrack: table full"` 确认。
7. **`-m state` vs `-m conntrack`**：`state` 是旧模块，`conntrack` 是新模块，功能相同但 `conntrack` 更强大（支持更多状态和扩展）；新规则用 `conntrack`。
8. **REDIRECT 只对入站包生效**：`REDIRECT` 在 PREROUTING 链只改进入本机的包；本机进程产生的包要在 OUTPUT 链也加一条 REDIRECT 规则。
9. **iptables 不看域名**：`-s example.com` 会在规则添加时解析为 IP 并固化，之后域名 IP 变化规则不会更新；不要用域名做匹配条件，用 IP 或 CIDR。
10. **LOG target 不终止匹配**：`LOG` 只是记录日志，包会继续匹配后续规则；要记录并丢弃需要两条规则：先 `LOG` 再 `DROP`，或者用自定义链。
11. **大量端口规则性能差**：逐个端口写 `--dport` 规则，包要线性匹配；用 `-m multiport --dports 80,443,8080,8443` 一条规则匹配多端口，或迁移到 nftables 的集合（O(1) 查找）。
12. **WSL2 网络特殊**：WSL2 是 NAT 网络模式，Windows 主机做网关，WSL 内的 iptables FORWARD/NAT 规则不直接控制 Windows 主机的网络；需要在 Windows 端做端口转发（`netsh interface portproxy`）或用 WSL2 的 mirrored 网络模式。

---

上一篇：《12-eBPF可观测性技术.md》
下一篇：《14-Prometheus与Grafana监控告警.md》
