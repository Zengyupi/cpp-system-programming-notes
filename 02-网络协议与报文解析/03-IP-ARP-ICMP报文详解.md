# IP / ARP / ICMP 报文详解

> 本节目标：逐字节拆 IPv4 首部，讲清分片重组、ARP 如何把 IP 解析成 MAC、ICMP（ping/Traceroute）报文长什么样。这些是看懂抓包、排查"不通/丢包/MTU 问题"的基础。

## 本章速览

- [1. IPv4 首部（默认 20 字节，有选项时更长，IHL 决定）](#1-ipv4-首部默认-20-字节有选项时更长ihl-决定)
- [2. IP 分片与重组（MTU/MSS 问题根源）](#2-ip-分片与重组mtumss-问题根源)
- [3. ARP：IP 地址 → MAC 地址（二层找人）](#3-arpip-地址--mac-地址二层找人)
- [4. ICMP：控制与差错报文（ping / traceroute 原理）](#4-icmp控制与差错报文ping--traceroute-原理)
- [5. IPv6 简介（差异点，不展开）](#5-ipv6-简介差异点不展开)
- [6. 快速参考卡片](#6-快速参考卡片)
- [7. 常见问题与坑](#7-常见问题与坑)
- [8. 延伸阅读](#8-延伸阅读)

---

## 1. IPv4 首部（默认 20 字节，有选项时更长，IHL 决定）

```text
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|Version(4)| IHL(4) |   DSCP/ECN(8) |      Total Length(16)       |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|   Identification(16)          |Flags(3)|  Fragment Offset(13)   |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|   TTL(8)      |  Protocol(8)  |     Header Checksum(16)        |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                     Source Address (32)                        |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                  Destination Address (32)                      |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  Options (if IHL>5, 0~40B)  ...        | Padding               |
```

| 字段 | 长度 | 含义与排查价值 |
| --- | --- | --- |
| Version | 4b | 4=IPv4，6=IPv6 |
| IHL | 4b | 首部长度，**单位是 4 字节**，最小 5(=20B)，取数据起点要用 `IHL*4` |
| Total Length | 16b | **整个 IP 包长度（含首部）**，大端 |
| Identification | 16b | 同一原始包的所有分片共享一个 ID |
| Flags | 3b | 位：保留/DF(Don't Fragment)/MF(More Fragment) |
| Frag Offset | 13b | 分片在原包的位置，**单位 8 字节** |
| TTL | 8b | 每经一跳 -1，到 0 丢弃（防环路）；初始常见 64/128/255，可用来粗判跳数 |
| Protocol | 8b | **上层协议号：1=ICMP 6=TCP 17=UDP** |
| Header Checksum | 16b | **只校验 IP 首部**，每跳 TTL 变就要重算 |
| Src/Dst Addr | 32b | 源/目的 IP |

真实抓包逐字节读：

```text
45 00 00 3c 1a 2b 40 00 40 06 b1 e6 c0 a8 01 0a c0 a8 01 01
└Ver=4,IHL=5(20B) 总长=0x003c=60  ID=0x1a2b Flags=010(DF) Offset=0
                  TTL=0x40=64 Proto=6(TCP) 校验=b1e6 源=192.168.1.10 目=192.168.1.1
```

## 2. IP 分片与重组（MTU/MSS 问题根源）

当 IP 包超过出接口 MTU（以太网 1500），且 DF=0，就分片：

```text
原始 4000B 数据，MTU=1500 → IP 载荷每片最多 1480(1500-20)
 片1: ID=X, MF=1, Offset=0    载荷1480
 片2: ID=X, MF=1, Offset=185  (1480/8=185)
 片3: ID=X, MF=0, Offset=370  剩余
```

- 接收端靠 **相同 ID + 源/目/协议 + Offset + MF** 还原；
- **任一分片丢失，整个包作废**（IP 层不重传，靠 TCP 重传）；分片还易被防火墙丢弃、有安全风险；
- 实践中 TCP 用 **MSS 协商**在源头避免分片（见 03 篇），UDP 超 MTU 才会分片；
- `ping -M do -s 1472`（Linux）可探测路径 MTU（PMTUD）；"能 ping 通但大包丢/建立慢"常是 MTU/MSS 钳制问题。

## 3. ARP：IP 地址 → MAC 地址（二层找人）

同一网段发帧需要对方 MAC，ARP 负责解析。报文在以太网帧里 EtherType=0x0806。

```text
ARP 报文(28B)：HTYPE(1=以太网) PTYPE(0x0800) HLEN=6 PLEN=4 OPER(1请求/2应答)
              发送方MAC 发送方IP 目标MAC(请求时填0) 目标IP
```

工作过程（抓包能看到一问一答）：

```text
A(192.168.1.10,aa) 要找 192.168.1.1 的MAC：
  ARP 请求(广播 ff:ff:ff:ff:ff:ff)："谁是 192.168.1.1？请告诉 .10"
  ARP 应答(单播回 aa)："192.168.1.1 在我这，MAC=bb:..:.."
  A 写入 ARP 缓存；查看：arp -n / ip neigh
```

- 跨网段时，A 解析的是**网关 MAC**（帧发给网关，IP 始终是最终目的）；
- **免费 ARP(gratuitous ARP)**、**ARP 欺骗**（伪造应答做中间人，工业网络安全隐患，见《../01-C++技术体系/03-网络编程/03-网络安全与加密编程.md》）要知道；
- 多网口/双 IP 设备场景，ARP 表和路由表错配会导致"网口不通"。

## 4. ICMP：控制与差错报文（ping / traceroute 原理）

ICMP 封装在 IP 里（Protocol=1），用于报错与探测，不传输用户数据。

| Type | 名称 | 用途 |
| --- | --- | --- |
| 0 / 8 | Echo Reply / Echo Request | **ping**：8 请求、0 应答 |
| 3 | Destination Unreachable | 主机/端口/网络不可达 |
| 11 | Time Exceeded | TTL 耗尽——**traceroute 靠它** |
| 5 | Redirect | 路由器让你换网关 |

ping 报文结构简单：Type/Code/Checksum/Identifier/Sequence + 时间戳数据。

**traceroute 原理**（面试常问）：从 TTL=1 开始发 UDP/ICMP，每跳路由器 TTL 减到 0 回 Type=11，从而逐跳暴露路径；目的端口不可达回 Type=3 表示到达。`mtr` 结合 ping+traceroute 做持续丢包定位。

> ICMP 被防火墙禁时会"ping 不通但 TCP 业务正常"——**ping 不通 ≠ 网络不通**，别误判。

## 5. IPv6 简介（差异点，不展开）

- 首部固定 40B、字段精简（去掉首部校验和、分片改为源端负责），扩展头部链式拼接；
- 不再有广播，用**组播**；地址解析用 **NDP（ICMPv6）**替代 ARP；
- 128 位地址、冒号十六进制；工业现场仍以 IPv4 为主，知道这些差异即可。

## 6. 快速参考卡片

```text
IPv4头：IHL*4=头长；Total Length含头；Proto 1 ICMP/6 TCP/17 UDP；校验只覆盖首部
分片：同ID+Offset(单位8)+MF；丢一片全废；TCP靠MSS源头避免
ARP：同网段解析MAC，广播请求单播应答；跨网段解析网关MAC；防ARP欺骗
ICMP：ping=8请求/0应答；不可达=3；TTL耗尽=11(traceroute原理)；ping不通≠业务不通
IPv6：固定40B头、无广播用组播、NDP替代ARP
```

## 7. 常见问题与坑

| 现象 | 排查方向 |
| --- | --- |
| 取 IP 头长度错、后续字段全偏 | 用 IHL*4 而非固定 20（可能有选项） |
| 小包通、大包卡/丢 | MTU/PMTUD/MSS，`ping -M do` 探路径 MTU |
| 同网段 ARP 不全、时通时断 | IP 冲突、ARP 欺骗、双网卡 flux；查 `ip neigh` |
| traceroute 中间显示 `* * *` 但最终可达 | 中间节点禁回 ICMP，正常现象 |
| TTL 一直减、环路 | 路由配置环，TTL 归零回 ICMP 11 |
| 误把 ping 不通当断网 | ICMP 被策略丢弃，用 TCP 端口探测(tcping/nc) |

## 8. 延伸阅读

- IPv4 RFC 791：[datatracker.ietf.org/doc/html/rfc791](https://datatracker.ietf.org/doc/html/rfc791)；ARP RFC 826；ICMP RFC 792
- Wireshark IPv4/ARP/ICMP：[wiki.wireshark.org/ProtocolReference](https://wiki.wireshark.org/ProtocolReference)
- 上一篇《02-CAN与车载工业总线.md》；下一篇（核心）《04-TCP报文与三次握手四次挥手深度剖析.md》

---

上一篇：《02-CAN与车载工业总线.md》
下一篇：《04-TCP报文与三次握手四次挥手深度剖析.md》
