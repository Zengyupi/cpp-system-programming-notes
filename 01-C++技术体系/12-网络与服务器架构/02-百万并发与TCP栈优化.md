# 百万并发与TCP栈优化

> 本节目标：打通"百万并发"从参数调优到内核原理的完整链路——掌握 fd 四层限制、sysctl 网络参数、conntrack、内存估算与压测方法；从内核视角理解三次握手双队列（半连接/全连接）溢出排查、四次挥手 11 状态机、TIME_WAIT/CLOSE_WAIT 根因与缓解、滑动窗口与拥塞控制四阶段。前置《01-网络基础与TCP-IP.md》（TCP 基础与 Socket），关联《04-Reactor与高性能网络库.md》（事件驱动框架）、《../13-并发异步与组件/02-io_uring与异步IO.md》（省 syscall）、《../13-并发异步与组件/03-用户态协议栈与DPDK.md》（旁路内核）。 课程模块 2.2：服务器百万并发实现（实操）/ Posix API 与网络协议栈。本篇两条主线：**调优实操**（内核参数、连接数上限、压测）+ **协议栈原理**（握手挥手的内核视角、11 状态机、滑动窗口与拥塞控制）。基础：`../03-计算机网络编程/02-IO多路复用与Reactor模型.md`（socket API）、`06-Reactor与高性能网络库.md`（事件驱动框架）；抓包验证见 `../06-工程化与工具链/12-tcpdump网络抓包.md`；再往上的用户态方案见 `09-用户态协议栈与DPDK.md`、`08-io_uring与异步IO.md`。

## 本章速览

- [1. 概述](#1-概述)
  - [1.1 C10K → C100K → C10M 演进史](#11-c10k--c100k--c10m-演进史)
  - [1.2 本篇主线](#12-本篇主线)
- [2. 百万并发实操【高频】](#2-百万并发实操高频)
  - [2.1 连接数与文件描述符：四层限制](#21-连接数与文件描述符四层限制)
  - [2.2 sysctl 网络参数表](#22-sysctl-网络参数表)
  - [2.3 conntrack 原理分析与调优](#23-conntrack-原理分析与调优)
  - [2.4 内存估算表](#24-内存估算表)
  - [2.5 压测方法](#25-压测方法)
- [3. 三次握手源码视角【高频】](#3-三次握手源码视角高频)
  - [3.1 connect / listen / accept 各自触发什么](#31-connect--listen--accept-各自触发什么)
  - [3.2 半连接队列与全连接队列](#32-半连接队列与全连接队列)
  - [3.3 listen backlog 的本质](#33-listen-backlog-的本质)
  - [3.4 SYN 泛洪与 syncookies](#34-syn-泛洪与-syncookies)
  - [3.5 溢出观测](#35-溢出观测)
- [4. 四次挥手与 11 状态【高频】](#4-四次挥手与-11-状态高频)
  - [4.1 close() 触发 FIN 与全状态迁移图](#41-close-触发-fin-与全状态迁移图)
  - [4.2 大量 CLOSE_WAIT：根因与解决](#42-大量-close_wait根因与解决)
  - [4.3 大量 TIME_WAIT：根因与解决](#43-大量-time_wait根因与解决)
  - [4.4 SO_REUSEADDR vs SO_REUSEPORT](#44-so_reuseaddr-vs-so_reuseport)
- [5. keepalive 与心跳](#5-keepalive-与心跳)
  - [5.1 TCP keepalive（内核层）](#51-tcp-keepalive内核层)
  - [5.2 应用层心跳设计](#52-应用层心跳设计)
  - [5.3 为什么长连接服务必有应用层心跳【高频】](#53-为什么长连接服务必有应用层心跳高频)
- [6. 拥塞控制与滑动窗口](#6-拥塞控制与滑动窗口)
  - [6.1 滑动窗口原理](#61-滑动窗口原理)
  - [6.2 拥塞控制四阶段【高频】](#62-拥塞控制四阶段高频)
  - [6.3 BBR 与传统算法一句话](#63-bbr-与传统算法一句话)
  - [6.4 抓包验证](#64-抓包验证)
- [7. 快速参考卡片](#7-快速参考卡片)
- [8. 常见问题与坑](#8-常见问题与坑)

---

## 1. 概述

### 1.1 C10K → C100K → C10M 演进史

| 时代 | 目标 | 瓶颈 | 突破手段 |
|---|---|---|---|
| 1999~ | C10K（1 万并发） | select 的 1024 fd 上限、每次全量拷贝/遍历 | epoll/kqueue（Linux 2.6，2003）+ 非阻塞 IO + Reactor |
| 2000s | C100K | 每连接一线程的内存与调度；内核参数默认值 | 事件驱动 + 线程池 + 内核调优（fd/内存/队列） |
| 2010s~ | C10M（千万级） | 内核协议栈本身：syscall、中断、skb 拷贝、锁 | io_uring（省 syscall）、协程（省线程）、用户态协议栈/DPDK（旁路内核） |
| 当下 | 百万并发单机 | fd 上限、内存、端口、conntrack | 本篇第 2 章实操内容 |

一句话：C10K 时代问题是"怎么同时等一万件事"（epoll 解决）；C10M 时代问题是"内核是否还该管包"（旁路解决）。**百万并发处于中间：内核栈还能用，但每个默认参数都得改**。

### 1.2 本篇主线

| 主线 | 内容 | 对应章节 |
|---|---|---|
| 调优实操 | fd 四层限制、sysctl、conntrack、内存估算、压测 | 第 2 章 |
| 协议栈原理 | 握手/挥手的内核视角、11 状态、keepalive、窗口与拥塞 | 第 3~6 章 |

## 2. 百万并发实操【高频】

### 2.1 连接数与文件描述符：四层限制

Linux 下"打开的连接"占 fd，fd 有四层天花板，**从小到大层层压制**：

| 层级 | 参数/位置 | 含义 | 默认值（量级） | 调整方法 |
|---|---|---|---|---|
| ① 进程软限制 | `ulimit -n`（RLIMIT_NOFILE 软） | 当前 shell/进程实际生效上限 | 1024 | `ulimit -n 1048576` |
| ② 进程硬限制 | RLIMIT_NOFILE 硬 | 软限制能提到的高度；非 root 只能降不能升 | 4096 | `/etc/security/limits.conf` 两行 `nofile` |
| ③ 单进程上限 | `fs.nr_open` | 单进程 fd 的绝对上限（硬限制也不能越过它） | 1048576 | `sysctl -w fs.nr_open=10485760` |
| ④ 系统级上限 | `fs.file-max` | **全系统所有进程**合计打开文件上限 | 数十万~百万（与内存相关） | `sysctl -w fs.file-max=10000000` |

关系链：`进程实际生效 = min(软, 硬, nr_open)`；所有进程合计 ≤ file-max。

```bash
# /etc/security/limits.conf —— 对登录会话生效(服务由 systemd 管理则用 LimitNOFILE=)
*  soft  nofile  1048576
*  hard  nofile  1048576

# 立即生效(仅当前 shell) + 内核参数
ulimit -n 1048576
sysctl -w fs.nr_open=10485760        # 想要超过 1048576 必须先抬它
sysctl -w fs.file-max=10000000

# 观测
cat /proc/sys/fs/nr_open             # 单进程天花板
cat /proc/sys/fs/file-nr             # 已分配/未用/最大
ls /proc/<pid>/fd | wc -l            # 某进程当前 fd 数
```

| 坑 | 说明 |
|---|---|
| 只 `ulimit -n`，硬限制没动 | 软限制提不上去（软 ≤ 硬），还是几千 |
| 硬限制抬到 300 万但 nr_open 是 1048576 | setrlimit 直接失败；先抬 nr_open |
| systemd 服务不读 limits.conf | 在 unit 里写 `LimitNOFILE=1048576`，`systemctl daemon-reload` 重启 |
| 压到 fd 上限的现象 | `Too many open files`：accept/socket 返回 EMFILE |

### 2.2 sysctl 网络参数表

```text
# /etc/sysctl.conf 追加后 sysctl -p 生效
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 65535
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216
net.ipv4.ip_local_port_range = 1024 65535
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_max_tw_buckets = 1048576
```

| 参数 | 含义 | 建议值/说明 |
|---|---|---|
| net.core.somaxconn | **全连接队列**上限，listen backlog 的天花板 | 65535；nginx 默认 backlog 511，若 somaxconn=128 则实际只有 128 |
| net.ipv4.tcp_max_syn_backlog | **半连接队列**上限（SYN_RCVD 数量） | 65535，防 SYN 泛洪时也要够大 |
| net.core.rmem_max / wmem_max | SO_RCVBUF/SO_SNDBUF 单次可设的最大值（内核实际会翻倍分配） | 16MB，大流量传输用 |
| net.ipv4.tcp_rmem | 接收缓冲**自动调优三元组**：min default max | 空闲连接只占 min（4KB），繁忙自动涨到 max |
| net.ipv4.tcp_wmem | 发送缓冲自动调优三元组 | 同上 |
| net.ipv4.ip_local_port_range | 临时（客户端）端口范围 | 扩到 `1024 65535`；每目标`IP:port`组合受它限制 |
| net.ipv4.tcp_tw_reuse | 允许**客户端**复用 TIME_WAIT 端口发起连接（依赖 tcp_timestamps，默认开） | 1，缓解客户端端口耗尽 |
| net.ipv4.tcp_max_tw_buckets | TIME_WAIT 总数上限，超出直接销毁 | 不要太小 |
| net.core.netdev_max_backlog | 网卡收包→协议栈的积压队列 | 大流量调大 |

要点：百万**空闲/长**连接要把 `tcp_rmem/tcp_wmem` 的 min 调小（省内存），大吞吐才调大 max——两个诉求用自动调优三元组同时满足。

### 2.3 conntrack 原理分析与调优

开启 iptables/nftables/K8s 等基于 Netfilter 的功能后，每个连接在**连接跟踪表**里占一项（五元组 → 状态）：

| 项 | 说明 |
|---|---|
| 表项内容 | 源/目 IP、源/目端口、协议、状态、超时时间 |
| nf_conntrack_max | 表容量上限（默认 65536 或 262144，云上常见更小） |
| nf_conntrack_count | 当前表项数（`/proc/sys/net/netfilter/nf_conntrack_count`） |
| nf_conntrack_tcp_timeout_established | 已建立连接的表项超时，默认 432000s（5 天） |

| 打满的表现 | 原因 |
|---|---|
| dmesg刷 `nf_conntrack: table full, dropping packet` | 新建连接的 SYN/首包找不到空位被丢 |
| 新连接建不上、ping 不通（新会话），已建立连接正常 | 表项只影响新建会话 |
| 高并发压测 QPS 断崖 | 丢包重传 |

| 调优 | 命令 |
|---|---|
| 扩容 | `sysctl -w net.netfilter.nf_conntrack_max=1048576`（hashsize 建议 = max/4，`/sys/module/nf_conntrack/parameters/hashsize`） |
| 缩短 established 超时 | `sysctl -w net.netfilter.nf_conntrack_tcp_timeout_established=86400`（长连接业务按心跳周期配套） |
| 纯转发/压测机不跟踪 | iptables 规则加 `-j NOTRACK`（raw 表），或关闭防火墙相关模块 |

### 2.4 内存估算表

百万连接不能只算"一个 fd 4 字节"，逐项估：

| 项 | 单连接占用 | 100 万连接合计 |
|---|---|---|
| 内核 socket 结构 + 收发缓冲下限 | tcp_rmem/wmem min：4KB×2 + sk 结构 ≈ 8~10KB | 8~10 GB |
| 进程 fd 表 + 文件对象 | ~100B 量级 | ~100 MB |
| epoll 注册（epitem）+ 用户态事件数组 | ~128B + 事件 12B | ~150 MB |
| 应用连接对象（含 8KB×2 业务缓冲） | 16~20KB | 16~20 GB |
| conntrack 表项（若开启） | ~300B | ~300 MB |
| **合计** | —— | **约 25~30 GB（空闲连接口径）** |

结论：百万并发单机建议 **64GB 内存**起步；纯网关类（应用缓冲小）可压到 20GB 内。另一条路：把内核缓冲 min 调小、业务缓冲按需分配。

### 2.5 压测方法

| 侧 | 要做的事 |
|---|---|
| 服务端 | 全部 2.1/2.2 参数 + Reactor 框架（见 `06-Reactor与高性能网络库.md`） |
| 客户端 | 同样要抬 fd 上限；扩 `ip_local_port_range`；**单 IP 对同一目标最多约 6 万连接**（端口限制）→ 多个客户端 IP（别名/多网卡）或多台压测机 |
| 工具 | `wrk -t8 -c1000000 -d60s --latency http://ip:port/`；或自写 epoll 客户端批量 connect+周期发包 |
| 观测 | `ss -s`（连接总数）、`sar -n SOCK 1`、`watch -n1 'cat /proc/net/sockstat'`、`nstat -az | grep -i listen`（队列溢出）、`dmesg | grep conntrack` |

## 3. 三次握手源码视角【高频】

### 3.1 connect / listen / accept 各自触发什么

| API | 内核行为 | 关键点 |
|---|---|---|
| connect() | 构造 SYN 发出 → 进入 SYN_SENT → **阻塞等待 ACK**（阻塞 fd） | SYN 丢则重传 `tcp_syn_retries`（默认 6）次，指数退避后报 `Connection timed out` |
| listen() | 创建**半连接队列**（SYN 队列）与**全连接队列**（accept 队列）；进入 LISTEN | 握手完全不依赖应用进程参与 |
| accept() | 从全连接队列**取队头**的已建立连接，分配新 fd 返回 | 若队列空则阻塞（阻塞 fd）；accept 不参与握手 |

核心认知：**三次握手由内核协议栈独立完成**，accept 只是"收割"结果——所以应用卡顿不卡握手，但会撑爆全连接队列。

### 3.2 半连接队列与全连接队列

```text
客户端                     服务端内核                          服务端应用
  │ ── SYN ─────────────▶ │ 放入半连接队列(状态SYN_RCVD)          │
  │ ◀─ SYN+ACK ────────── │ (等ACK, 超时重传 tcp_synack_retries)  │
  │ ── ACK ─────────────▶ │ 校验通过: 从半连接队列摘除,            │
  │                       │ 创建完整 sock 放入全连接队列,          │
  │                       │ 唤醒 accept ──────────────────────▶ accept() 返回
  │                       │ (ESTABLISHED, 等待被取走)             │

 半连接队列(SYN queue): 收到SYN、还没收到ACK  →  上限: tcp_max_syn_backlog
 全连接队列(accept queue): 握手完成、还没被accept →  上限: min(backlog, somaxconn)
```

| 队列 | 存什么 | 上限 | 溢出行为 |
|---|---|---|---|
| 半连接队列 | request_sock（轻量半开连接） | min(tcp_max_syn_backlog, backlog派生值)，下限 8 | 丢 SYN 或开 syncookies |
| 全连接队列 | 完整 sock（ESTABLISHED） | min(listen backlog, somaxconn) | `tcp_abort_on_overflow=0`（默认）：丢弃 ACK，客户端视角已建立但发包被 RST；`=1`：直接发 RST 拒绝 |

### 3.3 listen backlog 的本质

`listen(fd, backlog)` 中 backlog 控制的是**全连接队列长度**，实际生效值：

```text
nr_table_entries = max( min(backlog, somaxconn), 8 )
```

所以 `listen(fd, 511)`（nginx 默认）在 `somaxconn=128` 的机器上**实际只有 128**——面试常考：两个值取小者生效。

### 3.4 SYN 泛洪与 syncookies

| 项 | 说明 |
|---|---|
| 攻击原理 | 伪造源 IP 狂发 SYN，占满半连接队列，真用户的 SYN 被丢弃 |
| 防御 syncookies | `tcp_syncookies=1`：半连接队列满时不再存状态，把连接信息（时间戳、MSS 等）**编码进 SYN+ACK 的初始序号 ISN**；收到第三次握手的 ACK 时反解校验，合法则直接建连进全连接队列 |
| 代价 | 无法使用部分 TCP 扩展选项（如 window scaling 受限）；属于"被动兜底"，平时仍应把队列调大 |

### 3.5 溢出观测

```bash
# 溢出计数(自启动累计, 持续增长说明当前在溢出)
nstat -az | grep -i listen
#   TcpExtListenOverflows  ← 全连接队列溢出(收到的ACK因队满被丢)
#   TcpExtListenDrops      ← 半连接队列溢出/其他丢弃

netstat -s | grep -i listen
#   "xx times the listen queue of a socket overflowed"   ← 全连接溢出
#   "xx SYNs to LISTEN sockets dropped"                  ← 半连接丢弃

# 实时看队列: LISTEN 状态下 Recv-Q=当前全连接队列长度, Send-Q=队列上限
ss -lnt
# State  Recv-Q  Send-Q  Local Address:Port
# LISTEN 0       511           0.0.0.0:8888
```

## 4. 四次挥手与 11 状态【高频】

### 4.1 close() 触发 FIN 与全状态迁移图

应用调 `close()`（或进程退出）→ 内核发 FIN；对端 ACK 后本端进入 FIN_WAIT_2；对端再发 FIN，本端 ACK 后进入 **TIME_WAIT 等 2MSL**。TCP 共 11 个状态：

```cpp
        ┌────────────────── 服务器(被动打开) ──────────────────┐
 CLOSED ──listen()──▶ LISTEN ──收SYN/回SYN+ACK──▶ SYN_RCVD
   ▲                    │                              │收ACK
   │                    │        客户端(主动打开)        ▼
   │                    │     CLOSED ──connect()──▶ (ESTABLISHED)
   │                    │        │发SYN                 ▲
   │                    │      SYN_SENT ──收SYN+ACK──┐   │
   │                    │            │发ACK           ▼   │
   │                    └───────────┴──────────▶ ESTABLISHED
   │                                                  │(数据传输)
   │  被动关闭                    主动关闭 close()       │
   │◀──────────────── FIN ─────────────────────────── │
 CLOSE_WAIT                                        FIN_WAIT_1
   │ 应用调 close()                                   │◀─ACK
   │──FIN▶                                          FIN_WAIT_2
 LAST_ACK                                             │◀─FIN
   │◀─ACK ────────────────────────ACK──────────▶ TIME_WAIT
   ▼                                                  │等2MSL(60s)
 CLOSED ◀─────────────────────────────────────────────┘

 同时关闭(罕见): 双方同时发FIN
   FIN_WAIT_1 ──收对端FIN/回ACK──▶ CLOSING ──收ACK──▶ TIME_WAIT ─▶ CLOSED
```

| 状态 | 谁处于 | 含义 | 排查关注 |
|---|---|---|---|
| LISTEN | 服务端 | 等连接 | `ss -lnt` |
| SYN_SENT | 客户端 | SYN 已发未收到 SYN+ACK | 防火墙/目标不通 |
| SYN_RCVD | 服务端 | 半连接 | SYN 泛洪征兆 |
| ESTABLISHED | 双方 | 数据传输 | 数量=当前活跃连接 |
| FIN_WAIT_1 | 主动关 | FIN 已发未收 ACK | 对端不回（网络丢/对端卡） |
| FIN_WAIT_2 | 主动关 | 收到 ACK 等对端 FIN | 对端 CLOSE_WAIT 不 close 会把本端卡在这（有 tcp_fin_timeout 兜底） |
| TIME_WAIT | 主动关 | 等 2MSL | 见 4.4 |
| CLOSE_WAIT | 被动关 | 收到 FIN 已 ACK，**等应用 close()** | 堆积=本端 bug |
| LAST_ACK | 被动关 | FIN 已发等最后 ACK | 正常短暂 |
| CLOSING | 双方 | 同时关闭 | 罕见 |
| CLOSED | —— | 初始/终态 | —— |

### 4.2 大量 CLOSE_WAIT：根因与解决

根因链条：**对端 FIN 已到达、本端内核已 ACK（进入 CLOSE_WAIT），但本端代码一直不调 close()**。内核自动完成了挥手的前半段，后半段必须应用自己走。

| 排查步骤 | 命令/动作 |
|---|---|
| ① 确认规模 | `ss -tan state close-wait \| wc -l`（增长趋势） |
| ② 定位进程/连接 | `ss -tanp state close-wait` 或 `lsof -nP -i \| grep CLOSE_WAIT` |
| ③ 代码审计 | 错误分支漏 close、fd 泄漏、业务回调阻塞导致永远走不到 close、连接对象被缓存未释放 |
| ④ 验证 | 修完观察 CLOSE_WAIT 是否随对端关闭同步归零 |

| 解决 | 说明 |
|---|---|
| 补齐关闭路径 | 所有 return/异常分支统一走"清理函数"；C++ 用 RAII（智能指针管连接） |
| 读写事件里处理 EOF | Reactor 的 recv()==0 → 立即 close（见 `06-Reactor与高性能网络库.md`） |
| 空闲超时踢连接 | 定时器扫描最后活跃时间，超时关闭 |

### 4.3 大量 TIME_WAIT：根因与解决

| 项 | 说明 |
|---|---|
| 为什么等 2MSL | ① 最后一个 ACK 若丢，对端会重传 FIN，本端必须还能应答；② 让旧连接的迟到报文在网络中自然过期，避免污染同四元组的新连接。Linux MSL=30s，共 60s（硬编码） |
| 谁产生 TIME_WAIT | **主动关闭方**。短连接 + 高频请求 → 每次都主动关 → 堆积 |
| 危害 | 作为客户端：临时端口耗尽，`connect: Cannot assign requested address`；占用内存与连接表 |
| 误区 | `tcp_fin_timeout` 是 **FIN_WAIT_2** 的超时（默认 60s），**不是** TIME_WAIT 时长——高频面试陷阱 |

| 解决 | 命理 |
|---|---|
| 长连接 / 连接池（首选） | 从源头减少握手挥手次数 |
| tcp_tw_reuse=1 | 仅对**客户端发起**的连接复用 TIME_WAIT 端口；依赖 tcp_timestamps；内核 4.x 起较安全 |
| 扩端口范围 | `ip_local_port_range = 1024 65535` |
| 多客户端 IP | 每个源 IP 对同一目标 6 万上限，加 IP 线性扩 |
| 严禁 tcp_tw_recycle | NAT 环境会丢连接，**内核 4.12 已删除该参数** |

### 4.4 SO_REUSEADDR vs SO_REUSEPORT

| 对比项 | SO_REUSEADDR | SO_REUSEPORT |
|---|---|---|
| 作用 | bind 时允许复用处于 **TIME_WAIT** 的本地地址端口 | 允许**多个 socket 同时 bind 同一地址端口** |
| 典型场景 | 服务器重启：旧连接 TIME_WAIT 未清、新进程要 bind 同端口（不设则 `Address already in use`） | 多进程/多线程各自建 listen socket，内核按四元组 hash 把新连接**分发**到不同队列 |
| 队列 | 共享语义，一个 socket 一条队列 | **每个 socket 独立**半/全连接队列 |
| 条件 | 必须在 bind 前设置 | 所有 socket 都要设置且同一 uid；nginx `reuseport` 用它消灭 accept 惊群 |

## 5. keepalive 与心跳

### 5.1 TCP keepalive（内核层）

| 参数 | 默认 | 含义 |
|---|---|---|
| tcp_keepalive_time | 7200s | 空闲多久后开始发探测包 |
| tcp_keepalive_intvl | 75s | 探测包间隔 |
| tcp_keepalive_probes | 9 次 | 连续失败多少次判定死亡 |

总检测时长 = 7200 + 75×9 ≈ **2 小时 11 分**。单连接粒度可用 setsockopt：`SO_KEEPALIVE` 开关 + `TCP_KEEPIDLE / TCP_KEEPINTVL / TCP_KEEPCNT` 三项覆盖。

### 5.2 应用层心跳设计

| 设计点 | 建议值/方案 |
|---|---|
| 心跳间隔 | 必须小于链路上所有中间设备的空闲回收时间（LB/NAT 常见 5 分钟）；一般 15~30s |
| 判死条件 | 连续 N 次（2~3）未收到响应 |
| 心跳内容 | 越轻越好：协议内置命令（Redis `PING`、WebSocket ping 帧、自定义 1 字节 opcode） |
| 断线重连 | 指数退避 + 随机抖动（防止雪崩式重连风暴），重连成功后重放订阅/会话恢复 |
| 与中间件心跳 | Redis 主从/哨兵自身有心跳；网关到后端、客户端到网关是两段，各自都要设计，参考 `../05-数据库与序列化/02-Redis设计与数据结构.md` |

### 5.3 为什么长连接服务必有应用层心跳【高频】

| TCP keepalive 的局限 | 应用层心跳的价值 |
|---|---|
| 默认 2 小时才探测，业务等不起 | 秒级感知 |
| 只探测到对端**主机/链路**是否存活 | 能探测**对端进程**是否假死（进程死锁/假死时内核协议栈仍会回 ACK，keepalive 完全发现不了） |
| 中间 NAT/LB 静默改写/回收连接，两端都不知道 | 心跳流量顺带"保活"路径上的中间设备表项 |
| 半开连接（拔网线/宕机）要等 2h+ 才清 | 及时踢死链，释放连接资源、触发切换 |

## 6. 拥塞控制与滑动窗口

### 6.1 滑动窗口原理

TCP 用**字节序号 + 窗口**做可靠传输与流量控制：

```text
发送方(以字节为单位):
 ┌────────┬─────────────────┬────────────────┬──────────────┐
 │已发送已ACK│  已发送未ACK     │  可发送未发送     │  窗口外(等ACK)  │
 └────────┴─────────────────┴────────────────┴──────────────┘
           │◀────── 发送窗口 = min(rwnd, cwnd) ──────▶│
 左沿: 最老的未确认字节   右沿: 左沿 + 窗口大小

接收方:
 ┌────────────┬────────────────┬──────────────────────┐
 │已读走(可覆盖) │ 已收到未交应用     │ 空闲(= 接收窗口 rwnd)   │
 └────────────┴────────────────┴──────────────────────┘
 每个 ACK 携带 window 字段通告 rwnd → 驱动发送窗口滑动
```

| 概念 | 说明 |
|---|---|
| rwnd 接收窗口 | 接收方在 ACK 里通告"我还能收多少"，做**流量控制**（不让接收方淹死） |
| cwnd 拥塞窗口 | 发送方自己估计"网络能扛多少"，做**拥塞控制** |
| 发送窗口 | `min(rwnd, cwnd)`，两个约束取小 |
| 窗口滑动 | 累积 ACK 到达 → 左沿推进 → 新字节可入窗 |
| 零窗口 | rwnd=0 时发送方停止发数据，启动**坚持定时器**周期发 1 字节**窗口探测**（防窗口恢复通知丢失导致死锁）；接收侧配合 Clark 算法避免糊涂窗口综合征，发送侧 Nagle 攒包 |

### 6.2 拥塞控制四阶段【高频】

| 阶段 | 触发 | cwnd 变化 | 图示 |
|---|---|---|---|
| 慢启动 | 连接建立/RTO 后 | 每 RTT **翻倍**（每收 1 个 ACK +1 MSS），直到 ≥ ssthresh | `1→2→4→8→16` |
| 拥塞避免 | cwnd ≥ ssthresh | 每 RTT **+1 MSS**（线性） | `/` 缓慢爬坡 |
| 快重传 | 收到 **3 个重复 ACK** | 不等 RTO 立即重传丢失段 | 丢包但网络还在传 |
| 快恢复 | 快重传后 | `ssthresh = cwnd/2`，`cwnd = ssthresh`，直接进入拥塞避免 | 减半后线性，不从 1 开始 |
| （对照）RTO 超时 | 定时器超时 | `ssthresh = cwnd/2`，`cwnd = 1`，重回慢启动 | 认为网络瘫痪 |

### 6.3 BBR 与传统算法一句话

| 算法 | 拥塞信号 | 一句话 |
|---|---|---|
| Reno/NewReno/CUBIC（传统） | **丢包** | 丢包=拥塞，减窗重来；深 buffer 网络会"填满缓冲区"反而增时延 |
| BBR（Google） | **带宽 + RTT 测量** | 周期探测瓶颈带宽与最小 RTT，把发送速率钉在带宽时延积（BDP）上，不靠丢包推断 |

### 6.4 抓包验证

| 想看什么 | 命令/指标 | 解读 |
|---|---|---|
| 三次握手 | `tcpdump -i eth0 'tcp[tcpflags] & tcp-syn != 0'` | SYN → SYN,ACK → ACK；注意握手在 accept 之前完成 |
| 重传 | `nstat -az \| grep -i retrans`（TcpRetransSegs）持续增长 | 网络丢包/缓冲不足 |
| 零窗口 | 抓包看 `win=0` 及后续 window probe | 接收方处理不过来 |
| 队列溢出 | `nstat -az \| grep -i listen` | 见 3.5 |
| 连接状态分布 | `ss -s` | TIME_WAIT/CLOSE_WAIT 异常堆积一眼可见 |

详细过滤表达式与 Wireshark 分析流程见 `../06-工程化与工具链/12-tcpdump网络抓包.md`。

## 7. 快速参考卡片

| 要点 | 一句话 |
|---|---|
| fd 四层 | 软 ≤ 硬 ≤ fs.nr_open（单进程）；fs.file-max（全系统） |
| limits.conf | soft/hard 两行 nofile；systemd 服务用 LimitNOFILE |
| backlog 生效值 | min(listen backlog, somaxconn)，下限 8 |
| 双队列 | 半连接=SYN_RCVD（tcp_max_syn_backlog）；全连接=ESTABLISHED 待 accept（backlog） |
| accept 语义 | 只从全连接队列取头，不参与握手 |
| 全连接溢出 | 默认丢 ACK（客户端误以为成功）；abort_on_overflow=1 则 RST |
| syncookies | 队列满时把连接信息编进 SYN+ACK 的 ISN，不存半开状态 |
| 观测命令 | nstat -az \| grep -i listen；ss -lnt（Recv-Q=当前全连接长度/Send-Q=上限） |
| TIME_WAIT | 主动关闭方等 2MSL（Linux 60s 硬编码）；tcp_fin_timeout 是 FIN_WAIT_2 的 |
| CLOSE_WAIT | 对端 FIN 已到、本端没 close() → 一定是本端 bug |
| 端口耗尽 | 单源 IP 对单目标 ≤ ~6 万；扩 range/复用 tw/加 IP/连接池 |
| REUSEADDR/REUSEPORT | 前者重启躲 TIME_WAIT；后者多 socket 同端口各队列分流防惊群 |
| keepalive 三参数 | 7200s / 75s / 9 次 ≈ 2h11m 才判死 → 业务必须自心跳 |
| 应用层心跳价值 | 探测进程假死 + 保活中间设备 + 秒级感知 |
| 发送窗口 | min(rwnd, cwnd)；ACK 的 window 字段通告 rwnd |
| 拥塞四阶段 | 慢启动指数 / 拥塞避免线性 / 快重传 3 重复 ACK / 快恢复减半 |
| BBR | 测带宽+RTT 逼近 BDP，不靠丢包 |
| conntrack | nf_conntrack_max 打满丢新建包，dmesg 有 "table full, dropping packet" |

## 8. 常见问题与坑

| 坑 | 现象 | 正解 |
|---|---|---|
| 只调 ulimit 没调 nr_open | 想设 200 万，setrlimit 失败或被压回 | 先 `fs.nr_open` 再抬硬限制 |
| systemd 服务读不到 limits.conf | 日志仍报 Too many open files | unit 里 `LimitNOFILE=`，daemon-reload 后重启 |
| listen(511) 但 somaxconn=128 | 突发流量全连接队列溢出，客户端偶发 RST | `net.core.somaxconn` 同步调大 |
| 把 tcp_fin_timeout 当 TIME_WAIT 时长 | 调了没用，TIME_WAIT 还是 60s | fin_timeout 管 FIN_WAIT_2；TIME_WAIT 是 2MSL 硬编码 |
| 想删 TIME_WAIT 用 tcp_tw_recycle | NAT 用户大面积掉线 | 4.12 起参数已删除；用 tw_reuse/长连接/扩端口 |
| 客户端短连接压测打满 | Cannot assign requested address | 连接池 + tw_reuse + 扩 port_range + 多源 IP |
| conntrack 打满丢包误判为网络故障 | dmesg 有 table full，新连接失败 | 扩 nf_conntrack_max、缩 established 超时、压测机关闭跟踪 |
| CLOSE_WAIT 堆积只重启进程 | 重启后照旧增长 | 审计 close 路径：recv()==0 必 close、异常分支统一清理、RAII |
| 只改了服务端 fd，压测客户端没改 | 客户端先报 EMFILE | 压测两端同规格调参，客户端还要考虑源端口 |
| 忽略内存只看连接数 | 百万连接 OOM | 按 2.4 估算表核内存；空闲连接调小 buffer min |
| 半连接/全连接混为一谈 | SYN 泛洪时误调 backlog | 泛洪调 tcp_max_syn_backlog + syncookies；队满溢出调 backlog/somaxconn |
| keepalive 当作心跳用 | 对端进程假死 2 小时才发现 | 必须应用层心跳（秒级 + 判死 + 重连策略） |
| 全连接队列溢出不知道怎么查 | 偶发连接失败无迹可寻 | `nstat -az \| grep -iE 'listen(overflows\|drops)'` 持续增长即溢出 |
| 零窗口当断连处理 | 慢消费客户端被误杀 | 坚持定时器会发探测；应用层配合读超时与背压（见 02 篇缓冲区） |
| SO_REUSEADDR 设在 bind 之后 | Address already in use 依旧 | setsockopt 必须在 bind 之前调用 |

---

上一篇：《01-网络基础与TCP-IP.md》
下一篇：《03-高性能服务器设计.md》
