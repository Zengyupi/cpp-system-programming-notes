# tcpdump 网络抓包

> 本节目标：系统讲解 tcpdump 网络抓包工具的核心命令与使用方法，包括接口与输出控制、BPF 过滤表达式语法、TCP 标志位过滤、常用抓包场景、保存与读取、输出解读与最佳实践，学完后能够运用 tcpdump 进行网络故障排查与协议调试。

## 本章速览

- [1. 概述](#1-概述)
- [2. 核心选项](#2-核心选项)
  - [2.1 接口与输出控制](#21-接口与输出控制)
  - [2.2 输出格式与控制](#22-输出格式与控制)
  - [2.3 包数量与控制](#23-包数量与控制)
- [3. 过滤表达式（BPF 语法）](#3-过滤表达式bpf-语法)
  - [3.1 类型过滤](#31-类型过滤)
  - [3.2 协议过滤](#32-协议过滤)
  - [3.3 TCP 标志位过滤](#33-tcp-标志位过滤)
  - [3.4 组合与逻辑运算符](#34-组合与逻辑运算符)
- [4. 常用命令示例](#4-常用命令示例)
  - [4.1 基础抓包](#41-基础抓包)
  - [4.2 保存与读取](#42-保存与读取)
  - [4.3 查看内容](#43-查看内容)
  - [4.4 常用过滤组合](#44-常用过滤组合)
- [5. 快速参考卡片](#5-快速参考卡片)
- [6. 常用组合命令（生产环境推荐）](#6-常用组合命令生产环境推荐)
  - [6.1 排查 HTTP 业务问题](#61-排查-http-业务问题)
  - [6.2 排查 HTTPS/TLS 连接问题（只看握手）](#62-排查-httpstls-连接问题只看握手)
  - [6.3 排查 DNS 解析问题](#63-排查-dns-解析问题)
  - [6.4 排查网络延迟（测量请求-响应间隔）](#64-排查网络延迟测量请求-响应间隔)
  - [6.5 背景抓包（持续运行，自动轮转）](#65-背景抓包持续运行自动轮转)
- [7. 输出解读](#7-输出解读)
  - [7.1 典型输出格式](#71-典型输出格式)
  - [7.2 TCP 数据包输出解读](#72-tcp-数据包输出解读)
- [8. 注意事项与最佳实践](#8-注意事项与最佳实践)

---

## 1. 概述

tcpdump 是 Linux 下最常用的网络抓包工具，基于 libpcap 库，可以捕获和分析网络流量。常用于网络故障排查、安全分析、协议调试等场景。

**基本调用格式：**

```bash
tcpdump [选项] [过滤表达式]
```

**常用启动方式：**

```bash
tcpdump -i eth0                    # 抓取指定网卡的数据包
tcpdump -i any                     # 抓取所有网卡的数据包
tcpdump -r capture.pcap            # 读取已保存的抓包文件
tcpdump -w capture.pcap            # 将抓包结果写入文件
tcpdump -n port 80                 # 抓取 80 端口的数据包
```

---

## 2. 核心选项

### 2.1 接口与输出控制

| 选项        | 说明                                         | 示例                |
| ----------- | -------------------------------------------- | ------------------- |
| `-i <接口>` | 指定监听的网络接口                           | `-i eth0`、`-i any` |
| `-D`        | 列出所有可用的网络接口                       | `tcpdump -D`        |
| `-w <文件>` | 将原始数据包写入文件（pcap 格式）            | `-w capture.pcap`   |
| `-r <文件>` | 从 pcap 文件读取数据包                       | `-r capture.pcap`   |
| `-C <大小>` | 与 `-w` 配合，每个文件大小达到指定 MB 时轮转 | `-C 100`（100MB）   |
| `-G <秒数>` | 与 `-w` 配合，每隔指定秒数轮转文件           | `-G 3600`（每小时） |
| `-W <数量>` | 与 `-C`/`-G` 配合，限制轮转文件的最大数量    | `-W 5`              |

### 2.2 输出格式与控制

| 选项                  | 说明                                        | 示例        |
| --------------------- | ------------------------------------------- | ----------- |
| `-n`                  | 不解析主机名（IP 不转域名）                 | `-n`        |
| `-nn`                 | 不解析主机名和端口名（IP 和端口均显示数字） | `-nn`       |
| `-N`                  | 不显示域名（只显示主机名）                  | `-N`        |
| `-v` / `-vv` / `-vvv` | 详细程度递增（显示更多细节）                | `-vv`       |
| `-e`                  | 显示链路层头部（如 MAC 地址）               | `-e`        |
| `-q`                  | 安静模式（输出更简洁）                      | `-q`        |
| `-t`                  | 不显示时间戳                                | `-t`        |
| `-tt`                 | 显示 Unix 原始时间戳（自 1970 起的秒.微秒） | `-tt`       |
| `-ttt`                | 显示与上一个包的时间间隔（微秒）            | `-ttt`      |
| `-tttt`               | 显示"日期 时间"格式的完整时间戳             | `-tttt`     |
| `-ttttt`              | 显示与第一个包的时间间隔（微秒）            | `-ttttt`    |
| `-l`                  | 行缓冲输出（便于实时查看，常与 `tee` 配合） | `-l \| tee` |
| `-S`                  | 显示 TCP 序列号的绝对值（非相对值）         | `-S`        |
| `-A`                  | 以 ASCII 格式打印数据包内容                 | `-A`        |
| `-X`                  | 以十六进制和 ASCII 格式打印数据包内容       | `-X`        |
| `-XX`                 | 包含链路层头部，以十六进制和 ASCII 打印     | `-XX`       |

### 2.3 包数量与控制

| 选项        | 说明                                            | 示例      |
| ----------- | ----------------------------------------------- | --------- |
| `-c <数量>` | 抓取指定数量的包后退出                          | `-c 100`  |
| `-s <长度>` | 截取每个包的前 N 个字节（snaplen），默认 262144 | `-s 96`   |
| `-B <大小>` | 设置操作系统捕获缓冲区大小（KB）                | `-B 4096` |
| `-P <方向>` | 指定抓包方向：`in`、`out`、`inout`              | `-P in`   |

---

## 3. 过滤表达式（BPF 语法）

tcpdump 使用 BPF（Berkeley Packet Filter）语法，可在命令行直接编写过滤规则。

### 3.1 类型过滤

| 过滤表达式                | 说明               | 示例                    |
| ------------------------- | ------------------ | ----------------------- |
| `host <IP>`               | 指定主机 IP        | `host 192.168.1.1`      |
| `src host <IP>`           | 源地址为指定 IP    | `src host 192.168.1.1`  |
| `dst host <IP>`           | 目的地址为指定 IP  | `dst host 192.168.1.1`  |
| `net <网段>`              | 指定网段           | `net 192.168.0.0/24`    |
| `src net <网段>`          | 源地址在指定网段   | `src net 10.0.0.0/8`    |
| `dst net <网段>`          | 目的地址在指定网段 | `dst net 172.16.0.0/16` |
| `port <端口>`             | 指定端口（源或目） | `port 443`              |
| `src port <端口>`         | 源端口             | `src port 80`           |
| `dst port <端口>`         | 目的端口           | `dst port 53`           |
| `portrange <起始>-<结束>` | 端口范围           | `portrange 8000-9000`   |
| `ether host <MAC>`        | 指定 MAC 地址      | `ether host 00:11:22:33:44:55` |
| `ether src <MAC>`         | 源 MAC 地址        | `ether src 00:11:22:33:44:55` |
| `ether dst <MAC>`         | 目的 MAC 地址      | `ether dst ff:ff:ff:ff:ff:ff` |

> 说明：`ip` / `ip6` / `tcp` / `udp` 等属于协议过滤（见 3.2），可与上述类型过滤组合使用，如 `ip host 1.2.3.4`（等价于 `src or dst host 1.2.3.4` 且要求是 IPv4 包）。

### 3.2 协议过滤

| 过滤表达式      | 说明             |
| --------------- | ---------------- |
| `ip`            | IPv4 协议        |
| `ip6`           | IPv6 协议        |
| `tcp`           | TCP 协议         |
| `udp`           | UDP 协议         |
| `icmp`          | ICMP 协议        |
| `icmp6`         | ICMPv6 协议      |
| `arp`           | ARP 协议         |
| `rarp`          | RARP 协议        |
| `vlan`          | 802.1Q VLAN 标签 |
| `vxlan`         | VXLAN 协议       |
| `tcp[tcpflags]` | 特定 TCP 标志位  |

### 3.3 TCP 标志位过滤

| 过滤表达式                                                | 说明                        |
| --------------------------------------------------------- | --------------------------- |
| `tcp[tcpflags] & tcp-syn != 0`                            | 含 SYN 标志的包             |
| `tcp[tcpflags] & tcp-ack != 0`                            | 含 ACK 标志的包             |
| `tcp[tcpflags] & tcp-fin != 0`                            | 含 FIN 标志（关闭连接）     |
| `tcp[tcpflags] & tcp-rst != 0`                            | 含 RST 标志（重置连接）     |
| `tcp[tcpflags] & tcp-push != 0`                           | 含 PSH 标志（携带数据）     |
| `tcp[tcpflags] & (tcp-syn\|tcp-ack) == tcp-syn`           | 仅 SYN（客户端建连请求）    |
| `tcp[tcpflags] & (tcp-syn\|tcp-ack) == (tcp-syn\|tcp-ack)` | SYN+ACK（服务端建连响应）   |

> 注意：比较"多个标志同时置位"时，`==` 右侧必须加括号。因为过滤表达式中 `==` 的优先级高于 `\|`，写成 `== tcp-syn\|tcp-ack` 会被解析为 `(xxx == tcp-syn) \| tcp-ack`，结果完全错误。

### 3.4 组合与逻辑运算符

| 运算符        | 说明     | 优先级 |
| ------------- | -------- | ------ |
| `and` / `&&`  | 与       | 高     |
| `or` / `\|\|` | 或       | 中     |
| `not` / `!`   | 非       | 低     |
| `()`          | 括号分组 | -      |

```bash
# 示例：抓取 192.168.1.100 的 80 或 443 端口流量
tcpdump 'host 192.168.1.100 and (port 80 or port 443)'

# 示例：抓取非 SSH 的流量
tcpdump 'not port 22'
```

---

## 4. 常用命令示例

### 4.1 基础抓包

```bash
# 抓取所有网卡的 HTTP 流量（端口 80）
tcpdump -i any -nn port 80

# 抓取指定 IP 的所有流量
tcpdump -i eth0 host 192.168.1.100

# 抓取两个 IP 之间的通信
tcpdump -i any host 192.168.1.100 and host 192.168.1.200

# 抓取 100 个 TCP SYN 包
tcpdump -i any -c 100 'tcp[tcpflags] & tcp-syn != 0'
```

### 4.2 保存与读取

```bash
# 抓包并保存到文件
tcpdump -i any -w capture.pcap

# 抓包并保存，每个文件 100MB，最多保留 5 个轮转文件
tcpdump -i any -w capture.pcap -C 100 -W 5

# 读取抓包文件并过滤
tcpdump -r capture.pcap -nn port 443

# 实时抓包并同时保存到文件（使用 tee）
tcpdump -i any -l -nn | tee capture.txt
```

### 4.3 查看内容

```bash
# 以 ASCII 查看 HTTP 请求内容
tcpdump -i any -A -s 0 port 80

# 以十六进制 + ASCII 查看数据包内容
tcpdump -i any -X -s 0 host 192.168.1.100

# 查看详细输出（带链路层头）
tcpdump -i any -vv -e host 1.2.3.4

# 查看完整日期时间（默认只有时分秒）
tcpdump -i any -tttt host 1.2.3.4

# 查看与上一个包的时间间隔（用于分析响应延迟）
tcpdump -i any -ttt host 1.2.3.4
```

### 4.4 常用过滤组合

```bash
# 抓取非本机 SSH 的流量（排除本地 SSH 干扰）
tcpdump -i any 'not port 22'

# 抓取 ICMP ping 包
tcpdump -i any icmp

# 抓取 DNS 查询包（UDP 53）
tcpdump -i any -nn 'udp port 53'

# 抓取 ARP 广播包
tcpdump -i any -e arp

# 抓取所有携带数据的 TCP 包（重传分析需抓全量后用 Wireshark 的
# tcp.analysis.retransmission 过滤，tcpdump 本身无法直接判断重传）
tcpdump -i any 'tcp[tcpflags] & tcp-push != 0'

# 抓取特定网卡、非广播、非多播的流量
tcpdump -i eth0 'not broadcast and not multicast'

# 抓取 HTTP GET 请求
tcpdump -i any -A 'tcp port 80 and (tcp[((tcp[12:1] & 0xf0) >> 2):4] = 0x47455420)'

# 抓取 HTTP POST 请求（"POST" 的十六进制）
tcpdump -i any -A 'tcp port 80 and (tcp[((tcp[12:1] & 0xf0) >> 2):4] = 0x504f5354)'

# 抓取 DHCP 请求（端口 67/68）
tcpdump -i any -v -n 'port 67 or port 68'
```

---

## 5. 快速参考卡片

| 场景                 | 命令                                     |
| -------------------- | ---------------------------------------- |
| 列出网卡             | `tcpdump -D`                             |
| 抓取所有网卡流量     | `tcpdump -i any`                         |
| 抓取指定网卡流量     | `tcpdump -i eth0`                        |
| 抓取指定 IP          | `tcpdump host 1.2.3.4`                   |
| 抓取指定端口（HTTP） | `tcpdump port 80`                        |
| 抓取两个 IP 通信     | `tcpdump host 1.2.3.4 and host 5.6.7.8`  |
| 排除 SSH 流量        | `tcpdump not port 22`                    |
| 只抓 100 个包        | `tcpdump -c 100`                         |
| 保存到文件           | `tcpdump -w capture.pcap`                |
| 读取文件             | `tcpdump -r capture.pcap`                |
| 显示十六进制+ASCII   | `tcpdump -X`                             |
| 显示 ASCII 内容      | `tcpdump -A`                             |
| 详细模式             | `tcpdump -vv`                            |
| 不解析主机名/端口    | `tcpdump -nn`                            |
| 只抓 SYN 包          | `tcpdump 'tcp[tcpflags] & tcp-syn != 0'` |
| 只抓 DNS             | `tcpdump 'udp port 53'`                  |
| 只抓 ICMP            | `tcpdump icmp`                           |

---

## 6. 常用组合命令（生产环境推荐）

### 6.1 排查 HTTP 业务问题

```bash
tcpdump -i any -nn -A -s 0 port 80 -c 1000
```

### 6.2 排查 HTTPS/TLS 连接问题（只看握手）

```bash
tcpdump -i any -nn -vv 'tcp port 443 and (tcp[tcpflags] & tcp-syn != 0 or tcp[tcpflags] & tcp-fin != 0)'
```

### 6.3 排查 DNS 解析问题

```bash
tcpdump -i any -nn -v 'udp port 53'
```

### 6.4 排查网络延迟（测量请求-响应间隔）

```bash
# -ttt 显示相邻包的间隔，可直观看到请求发出到响应返回的耗时
tcpdump -i any -nn -ttt host 192.168.1.1

# -tttt 显示完整日期时间，便于与业务日志对齐
tcpdump -i any -nn -tttt host 192.168.1.1
```

### 6.5 背景抓包（持续运行，自动轮转）

```bash
nohup tcpdump -i any -w /var/log/capture_%Y%m%d_%H%M%S.pcap -C 500 -W 48 -G 3600 &
```

---

## 7. 输出解读

### 7.1 典型输出格式

```text
12:34:56.789012 IP 192.168.1.100.54321 > 8.8.8.8.53: 12345+ A? example.com. (28)
└────┬────┘  └┬┘ └─────────┬─────────┘ └┬┘ └────────┬────────┘ └───────┬───────┘
  时间戳     协议     源IP.源端口    方向   目的IP.目的端口   内容摘要
```

### 7.2 TCP 数据包输出解读

```text
12:34:56.789012 IP 192.168.1.100.54321 > 192.168.1.200.80: Flags [S], seq 123456, win 64240, length 0
                                                    └──┬──┘  └───┬───┘  └───┬───┘ └───┬───┘
                                                   标志组合  序列号   窗口大小  数据长度
```

| 输出标识    | 含义                          |
| ----------- | ----------------------------- |
| `Flags [S]` | 仅 SYN（客户端发起建连）      |
| `Flags [S.]`| SYN+ACK（服务端响应建连）     |
| `Flags [.]` | 仅 ACK（纯确认，length 0）    |
| `Flags [P.]`| PSH+ACK（携带应用数据）       |
| `Flags [F.]`| FIN+ACK（请求关闭连接）       |
| `Flags [R]` | RST（异常重置连接）           |
| `Flags [R.]`| RST+ACK                       |

> 其他常见字段：`seq` 序列号、`ack` 确认号、`win` 接收窗口、`length` 数据长度（字节）、`mss` 最大报文段长度（SYN 包中）。

---

## 8. 注意事项与最佳实践

| 要点           | 说明                                                 |
| -------------- | ---------------------------------------------------- |
| 需要 root 权限 | 抓包需要 root 权限，使用 `sudo tcpdump`              |
| 降低权限       | 加 `-Z <用户>`，打开抓包接口后切换到普通用户运行（默认已启用 `-Z tcpdump`） |
| 性能影响       | 高流量环境抓包可能影响性能，建议使用过滤条件精确抓取 |
| snaplen 设置   | 默认 `-s 262144` 足够，如需完整负载可用 `-s 0`       |
| 缓冲区大小     | 高流量环境建议增大缓冲区 `-B 4096`                   |
| 校验和告警     | 网卡/驱动做了校验和卸载时会有 `incorrect` 误报，加 `-K` 忽略校验和验证 |
| 文件大小控制   | 生产环境长期抓包务必使用 `-C` 和 `-W` 控制文件大小   |
| 隐私保护       | 保存的 pcap 文件可能包含敏感数据，注意权限管理       |
| 与 tshark 配合 | 复杂协议分析可结合 Wireshark 的 `tshark` 使用        |

---

上一篇：《01-Linux命令行速查.md》　｜　下一篇：《03-二进制查看工具.md》　｜　模块索引：《../README.md》
