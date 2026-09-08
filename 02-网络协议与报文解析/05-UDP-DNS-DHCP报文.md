# UDP / DNS / DHCP 报文

> 本节目标：讲清无连接的 UDP 首部，以及建立在 UDP 上最常见的两个协议——DNS（域名解析）和 DHCP（自动获取 IP）的报文结构与交互流程，并对比 TCP/UDP 选型。广播/多播在工业现场也常用。

## 本章速览

- [1. UDP 首部（只有 8 字节，极简）](#1-udp-首部只有-8-字节极简)
  - [1.1 TCP vs UDP 选型（面试与工程）](#11-tcp-vs-udp-选型面试与工程)
- [2. DNS 报文（域名 → IP，UDP 53，响应超 512B/区域传送用 TCP）](#2-dns-报文域名--ipudp-53响应超-512b区域传送用-tcp)
  - [2.1 报文结构](#21-报文结构)
  - [2.2 记录类型与解析流程](#22-记录类型与解析流程)
- [3. DHCP（自动获取 IP，UDP 客户端 68 / 服务端 67）](#3-dhcp自动获取-ipudp-客户端-68--服务端-67)
  - [3.1 DORA 四次交互（全是广播，因为客户端此时还没有 IP）](#31-dora-四次交互全是广播因为客户端此时还没有-ip)
- [4. 广播与多播（工业/音视频常用）](#4-广播与多播工业音视频常用)
- [5. 快速参考卡片](#5-快速参考卡片)
- [6. 常见问题与坑](#6-常见问题与坑)
- [7. 延伸阅读](#7-延伸阅读)

---

## 1. UDP 首部（只有 8 字节，极简）

```text
 0                  16                 31
┌──────────────┬──────────────┐
│ Source Port  │ Dest Port    │   各2字节
├──────────────┼──────────────┤
│ Length       │ Checksum     │   Length=首部+数据总长；Checksum 可全0(IPv4可选)
└──────────────┴──────────────┘
│              数据 ...
```

- **无连接**：不握手、不维护连接状态，发完即走；
- **不可靠**：不保证到达、不保证顺序、不重传、不流控——可靠性要应用自己做（如 QUIC、IEC 部分规约、音视频）；
- **面向报文**：一次 sendto 一个报文，保留边界（不像 TCP 是字节流，存在粘包半包）；
- 首部小、无握手开销，**延迟低、支持广播/多播**；
- Checksum 同样覆盖"伪首部（源/目IP）+UDP头+数据"，IPv6 下强制。

### 1.1 TCP vs UDP 选型（面试与工程）

| 维度 | TCP | UDP |
| --- | --- | --- |
| 连接 | 面向连接，三次握手 | 无连接 |
| 可靠性 | 保证有序到达、重传 | 不保证，应用自管 |
| 数据形态 | 字节流（粘包/半包，要自己分帧） | 报文，保留边界 |
| 开销/延迟 | 首部20B+、有握手和拥塞控制 | 首部8B、低延迟 |
| 广播多播 | 不支持 | 支持 |
| 典型 | HTTP/Modbus TCP/IEC104/数据库 | DNS/DHCP/视频/语音/游戏/部分工业实时规约、SNMP |

> 工业网关中：需要可靠采集的用 TCP（IEC104/Modbus TCP）；对实时性敏感、应用层自带重传或可容忍偶发丢失的（如 GOOSE/SV 在二层、部分组播采样）走无连接思路。

## 2. DNS 报文（域名 → IP，UDP 53，响应超 512B/区域传送用 TCP）

### 2.1 报文结构

```text
Header(12B 固定)
  ID(2) 标志(2: QR/Opcode/TC/RD/RA/RCODE) QDCOUNT ANCOUNT NSCOUNT ARCOUNT
Question  查询问题段：QNAME(变长,标签编码) QTYPE(2) QCLASS(2)
Answer    应答资源记录(RR)：NAME TYPE CLASS TTL RDLENGTH RDATA
Authority 权威 NS
Additional 附加（如 EDNS0、解析出的 IP）
```

- QNAME 不是 `www.a.com` 原样，而是**长度前缀标签**：`3www 1a 3com 0`（每段前一个字节是长度，末尾 0）；
- 标志位：QR(0问/1答)、TC(截断，超 512B 置位则改用 TCP)、RD(期望递归)、RCODE(0成功/3域名不存在)；
- 一次查询可在 Additional 里带回多条记录，减少往返。

### 2.2 记录类型与解析流程

| 类型 | 含义 |
| --- | --- |
| A / AAAA | IPv4 / IPv6 地址 |
| CNAME | 别名 |
| MX / TXT | 邮件 / 文本（校验、SPF） |
| NS / SOA | 域名服务器 / 起始授权 |
| PTR | 反查（IP→域名） |

递归查询流程：本机 → 递归解析器（运营商/公共 DNS）→ 根 → 顶级域(.com) → 权威服务器，结果逐级带回并缓存（受 TTL）。

```bash
dig +trace example.com      # 看逐级解析
nslookup -type=MX xx.com
dig @8.8.8.8 example.com A
# 抓 DNS：tcpdump -nn udp port 53
```

> 工程坑：服务偶发"卡住几百 ms~几秒"可能是**首次 DNS 解析慢/超时**，高并发服务应直接配 IP、做连接池或预解析、设置解析超时。

## 3. DHCP（自动获取 IP，UDP 客户端 68 / 服务端 67）

### 3.1 DORA 四次交互（全是广播，因为客户端此时还没有 IP）

```text
客户端(0.0.0.0:68)                    DHCP服务器(:67)
  │ ① Discover 广播（"有没有DHCP服务器？"，带MAC）
  │ ───────────────────────────────→
  │      ② Offer 广播/单播（提供 IP、租期、网关、DNS）
  │ ←───────────────────────────────
  │ ③ Request 广播（请求用某个 Offer，正式申请/续租）
  │ ───────────────────────────────→
  │      ④ ACK 广播（确认，含子网掩码/网关/DNS/租期）
  │ ←───────────────────────────────
```

记忆：**DORA = Discover / Offer / Request / Ack**（另有 Nak 拒绝、Release 释放、Renew 续租）。

- 为什么客户端没 IP 还用 UDP 广播：源 0.0.0.0、目的 255.255.255.255，链路层广播；
- 租期到 50% 单播续约（Renew），87.5% 广播重绑定（Rebind）；
- 现场问题：多台私接 DHCP 服务器导致终端拿到错误网关/DNS（DHCP 欺骗/冲突），工业网络要做 DHCP Snooping。

## 4. 广播与多播（工业/音视频常用）

| 方式 | 地址 | 特点 |
| --- | --- | --- |
| 单播 unicast | 指定 IP | 一对一 |
| 广播 broadcast | 255.255.255.255 / 子网广播 | 二层 ff:ff:ff:ff:ff:ff，同广播域全收，跨不过路由器 |
| 多播/组播 multicast | D 类 224.0.0.0~239.255.255.255 | 一对多，IGMP 管理成员，路由可转发；224.0.0.x 本地链路 |

```c
// UDP 组播发送/接收关键 setsockopt
int yes = 1; setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof yes);
// 接收方加入组播组
struct ip_mreq mreq; inet_pton(AF_INET, "239.1.2.3", &mreq.imr_multiaddr);
mreq.imr_interface.s_addr = htonl(INADDR_ANY);
setsockopt(fd, IPPROTO_IP, IP_ADD_MEMBERSHIP, &mreq, sizeof mreq);
```

## 5. 快速参考卡片

```text
UDP头8B：源端口|目的端口|长度|校验；无连接/不可靠/保留报文边界/可广播多播
选型：要可靠有序用TCP；低延迟/可丢/广播组播/应用自管重传用UDP
DNS：UDP53(大应答/TCP53)；QNAME=长度前缀标签；A/AAAA/CNAME/MX；RCODE=3不存在
DHCP=DORA：Discover→Offer→Request→Ack；客户端0.0.0.0:68 广播；50%续租
组播：224.0.0.0/4，IP_ADD_MEMBERSHIP 加入；广播不跨路由
```

## 6. 常见问题与坑

| 现象 | 排查 |
| --- | --- |
| UDP 丢包 | 内核接收缓冲区小、应用处理不过来；调 `SO_RCVBUF`、抓包看是否到达 |
| UDP "粘包"疑问 | UDP 保留报文边界，一次 recvfrom 一个报文，不存在 TCP 那种粘包 |
| DNS 偶尔解析很慢 | UDP53 丢包重传/超时；预解析、直连 IP、连接池、换解析器 |
| DNS 响应被截断(TC=1) | 超 512B，客户端应改用 TCP 或 EDNS0 |
| 终端拿到错误 IP/网关 | 私接/伪造 DHCP；查 DHCP Snooping、地址池冲突 |
| 组播收不到 | 没加入组、跨 VLAN 没开 PIM/IGMP Snooping、本地防火墙拦 |

## 7. 延伸阅读

- UDP RFC 768；DNS RFC 1034/1035；DHCP RFC 2131
- dig 手册：[bind9.readthedocs.io](https://bind9.readthedocs.io/)；Wireshark DNS/DHCP：[wiki.wireshark.org](https://wiki.wireshark.org/)
- 下一篇《06-HTTP与TLS应用层报文.md》

---

上一篇：《04-TCP报文与三次握手四次挥手深度剖析.md》
下一篇：《06-HTTP与TLS应用层报文.md》
