# 网络基础与TCP-IP

> 本节目标：掌握后台开发必备的 TCP/IP 协议栈核心知识与 Socket 编程能力，理解三次握手/四次挥手状态机、TCP 可靠传输机制、IO 多路复用原理与粘包解决方案；select/poll/epoll 与 Reactor 详解见《04-Reactor与高性能网络库.md》，内核协议栈调优见《02-百万并发与TCP栈优化.md》。

## 本章速览

- [1. TCP/IP 四层模型](#1-tcpip-四层模型)
- [2. TCP 协议详解](#2-tcp-协议详解)
  - [2.1 TCP 首部结构（20 字节固定 + 选项）](#21-tcp-首部结构20-字节固定--选项)
  - [2.2 三次握手](#22-三次握手)
  - [2.3 四次挥手](#23-四次挥手)
  - [2.4 TCP 可靠传输机制](#24-tcp-可靠传输机制)
  - [2.5 拥塞控制四算法](#25-拥塞控制四算法)
- [3. UDP 协议](#3-udp-协议)
  - [3.1 UDP 首部（8 字节）](#31-udp-首部8-字节)
  - [3.2 TCP vs UDP](#32-tcp-vs-udp)
- [4. Socket 编程](#4-socket-编程)
  - [4.1 TCP 编程流程](#41-tcp-编程流程)
  - [4.2 关键 Socket 选项](#42-关键-socket-选项)
  - [4.3 listen 的 backlog](#43-listen-的-backlog)
- [5. IO 模型与多路复用](#5-io-模型与多路复用)
  - [5.1 五种 IO 模型](#51-五种-io-模型)
  - [5.2 select / poll / epoll 对比](#52-select--poll--epoll-对比)
- [6. 粘包与拆包](#6-粘包与拆包)
  - [6.1 三种解决方案](#61-三种解决方案)
  - [6.2 长度前缀协议实现](#62-长度前缀协议实现)
- [7. 半关闭与优雅断开](#7-半关闭与优雅断开)
- [8. DNS 解析过程](#8-dns-解析过程)
- [9. 快速参考卡片](#9-快速参考卡片)
- [10. 常见坑](#10-常见坑)

---

## 1. TCP/IP 四层模型

```text
┌─────────────────────────────────────────┐
│ 应用层    HTTP / HTTPS / FTP / DNS / RPC│
├─────────────────────────────────────────┤
│ 传输层    TCP / UDP / SCTP              │
├─────────────────────────────────────────┤
│ 网络层    IP / ICMP / ARP / OSPF        │
├─────────────────────────────────────────┤
│ 链路层    以太网 / Wi-Fi / PPP           │
└─────────────────────────────────────────┘
```

| 层 | 数据单位 | 核心协议 | 寻址 | 典型设备 |
| --- | --- | --- | --- | --- |
| 应用层 | 报文 | HTTP、DNS、FTP | 域名/URL | 网关、负载均衡 |
| 传输层 | 段(TCP)/数据报(UDP) | TCP、UDP | 端口 | 四层负载均衡 |
| 网络层 | 包 | IP、ICMP、ARP | IP 地址 | 路由器、三层交换机 |
| 链路层 | 帧 | 以太网 | MAC 地址 | 交换机、网卡 |

**封装与解封装**：发送时每层加首部（应用数据 → TCP 段 → IP 包 → 以太网帧），接收时逐层剥首部。MTU（最大传输单元）以太网默认 1500 字节，超过则 IP 层分片（TCP 用 MSS 避免分片）。

## 2. TCP 协议详解

### 2.1 TCP 首部结构（20 字节固定 + 选项）

| 字段 | 长度 | 作用 |
| --- | --- | --- |
| 源端口/目的端口 | 16bit×2 | 标识应用进程 |
| 序号 seq | 32bit | 本报文段数据第一个字节的序号 |
| 确认号 ack | 32bit | 期望收到对方下一个字节的序号，ack=N 表示 N-1 前都收到 |
| 数据偏移 | 4bit | 首部长度（单位 4 字节），即头部有多少个 32bit 字 |
| 标志位 | 6bit | URG/ACK/PSH/RST/SYN/FIN |
| 窗口大小 | 16bit | 接收窗口，流量控制（最大 65535，可通过窗口扩大选项扩展） |
| 校验和 | 16bit | 伪首部 + TCP 首部 + 数据，强校验 |
| 紧急指针 | 16bit | URG=1 时有效，指向紧急数据最后一字节 |

**标志位速记**：SYN=建立连接、FIN=关闭连接、ACK=确认、RST=复位（异常断开）、PSH=推送（立即上交应用层）、URG=紧急。

### 2.2 三次握手

```cpp
客户端                          服务端
  CLOSED                         LISTEN
    | --- SYN (seq=x) --------> |     1. 客户端请求建立，进入 SYN_SENT
    | <-- SYN+ACK(seq=y,ack=x+1) |   2. 服务端同意并应答，进入 SYN_RECV
    | --- ACK (ack=y+1) -------> |     3. 客户端确认，双方进入 ESTABLISHED
```

| 状态 | 出现端 | 含义 |
| --- | --- | --- |
| LISTEN | 服务端 | 监听连接请求 |
| SYN_SENT | 客户端 | 已发 SYN 等待应答 |
| SYN_RECV | 服务端 | 收到 SYN 已发 SYN+ACK，等待最终 ACK |
| ESTABLISHED | 双方 | 连接建立，可传输数据 |

**为什么是 3 次不是 2 次？**
1. **确认双方收发能力**：3 次握手后，客户端确认"我能发能收、服务端能发能收"；2 次握手服务端无法确认客户端的接收能力。
2. **防止失效连接请求**：客户端先发的 SYN 在网络中滞留，超时重发的 SYN 已建立连接并关闭后，旧 SYN 到达服务端——2 次握手会直接建立连接浪费资源，3 次握手客户端会忽略服务端的 SYN+ACK（因为自己没发 SYN）。
3. **同步初始序列号**：双方各自的 ISN（初始序号）需要交换确认，3 次是最小可行次数。

**SYN 洪水攻击**：攻击者发大量 SYN 不回 ACK，服务端半连接队列满后拒绝新连接。防御：`tcp_syncookies`（不分配半连接资源，用 cookie 编码）、增大 `tcp_max_syn_backlog`、缩短 `tcp_synack_retries`。

### 2.3 四次挥手

```cpp
客户端                          服务端
 ESTABLISHED                    ESTABLISHED
    | --- FIN (seq=u) --------> |     1. 主动方发 FIN，进入 FIN_WAIT_1
    | <-- ACK (ack=u+1) -------- |     2. 被动方确认，进入 CLOSE_WAIT；主动方进入 FIN_WAIT_2
    | <-- FIN (seq=w) ---------- |     3. 被动方发 FIN（数据发完后），进入 LAST_ACK
    | --- ACK (ack=w+1) -------> |     4. 主动方确认，进入 TIME_WAIT；被动方收到后 CLOSED
```

| 状态 | 出现端 | 含义 |
| --- | --- | --- |
| FIN_WAIT_1 | 主动方 | 已发 FIN 等待 ACK |
| FIN_WAIT_2 | 主动方 | 收到 ACK，等待对方 FIN |
| CLOSE_WAIT | 被动方 | 收到 FIN，等待应用层 close |
| LAST_ACK | 被动方 | 已发 FIN，等待 ACK |
| TIME_WAIT | 主动方 | 等待 2MSL（默认 60s）后关闭 |
| CLOSED | 双方 | 完全关闭 |

**为什么挥手 4 次？** 握手时 SYN+ACK 可合并（服务端没有数据要发）；挥手时被动方收到 FIN 后可能还有数据未发完，ACK 和 FIN 必须分开，故 4 次。被动方数据发完后才发 FIN。

**TIME_WAIT 作用（2MSL）**：
1. **保证最后的 ACK 可达**：主动方发的最后 ACK 可能丢失，被动方会重发 FIN，TIME_WAIT 期间能收到并重发 ACK。
2. **让旧连接的迟到报文消亡**：2MSL 足以让本次连接所有报文从网络中消失，避免新连接收到旧连接的报文。

**大量 TIME_WAIT 的危害与缓解**：占内存、占端口（客户端端口耗尽）。缓解：`SO_REUSEADDR`（允许绑定 TIME_WAIT 端口）、`net.ipv4.tcp_tw_reuse`（允许复用 TIME_WAIT 连接用于新连接，需配合时间戳）、`net.ipv4.tcp_max_tw_buckets`（限制总数）、`net.ipv4.tcp_fin_timeout`（缩短 FIN_WAIT_2 超时）。

**CLOSE_WAIT 过多**：被动方收到 FIN 但应用层没调 close()，连接卡在 CLOSE_WAIT。通常是代码 bug（忘记 close 或异常路径没 close），用 RAII/智能指针管理 fd。

### 2.4 TCP 可靠传输机制

| 机制 | 作用 | 实现 |
| --- | --- | --- |
| 序列号 + 确认应答 | 保证数据有序、不丢 | 每个字节有序号，接收方回 ACK |
| 超时重传 | 丢包恢复 | RTO（超时时间）内未收 ACK 则重传 |
| 滑动窗口 | 流量控制 | 接收方通告窗口大小，发送方不超过窗口 |
| 拥塞控制 | 网络拥塞时降速 | 慢启动、拥塞避免、快重传、快恢复 |
| 校验和 | 数据完整性 | 伪首部+首部+数据的 16bit 反码和 |

**滑动窗口**：发送方维护发送窗口（已发送未确认 + 可发送未发送），接收方维护接收窗口。窗口大小由接收方通告（TCP 首部窗口字段），实现流量控制——接收方处理不过来时缩小窗口，发送方减速。

**超时重传 RTO**：动态计算，基于 RTT（往返时间）的平滑估计（SRTT = α·SRTT + (1-α)·RTT，α=0.875），RTO = SRTT + 4·RTTVAR（偏差）。首次重传后 RTO 翻倍（指数退避）。

### 2.5 拥塞控制四算法

| 阶段 | 触发 | cwnd 变化 | 阈值 |
| --- | --- | --- | --- |
| 慢启动 | 连接建立/超时后 | 每收到一个 ACK 加 1（指数增长） | cwnd < ssthresh |
| 拥塞避免 | cwnd ≥ ssthresh | 每 RTT 加 1（线性增长） | cwnd ≥ ssthresh |
| 快重传 | 收到 3 个重复 ACK | 立即重传（不等超时） | — |
| 快恢复 | 快重传后 | ssthresh=cwnd/2, cwnd=ssthresh，进入拥塞避免 | — |

**超时 vs 3 个重复 ACK**：超时说明网络可能严重拥塞，ssthresh=cwnd/2 且 cwnd=1（重新慢启动）；3 个重复 ACK 说明个别包丢失但网络还通，只做快重传+快恢复，不回到慢启动。

## 3. UDP 协议

### 3.1 UDP 首部（8 字节）

| 字段 | 长度 | 作用 |
| --- | --- | --- |
| 源端口/目的端口 | 16bit×2 | 标识进程 |
| 长度 | 16bit | UDP 数据报总长度（首部+数据） |
| 校验和 | 16bit | 可选（IPv4 可 0 表示不校验，IPv6 强制） |

### 3.2 TCP vs UDP

| 特性 | TCP | UDP |
| --- | --- | --- |
| 连接 | 面向连接（三次握手） | 无连接 |
| 可靠性 | 可靠（确认+重传+排序） | 不可靠（可能丢、乱序、重复） |
| 顺序 | 有序 | 无序（应用层自己保证） |
| 流量控制 | 滑动窗口 | 无 |
| 拥塞控制 | 有 | 无 |
| 头部开销 | 20 字节（+选项最多 60） | 8 字节 |
| 传输方式 | 字节流 | 数据报（有消息边界） |
| 适用 | HTTP、FTP、SSH、邮件 | DNS、视频/语音直播、游戏、QUIC |

**UDP 为什么不可靠还在用？** 简单、头部小、无连接延迟低、不做拥塞控制（实时音视频宁可丢包也不要卡顿延迟）。需要可靠性时应用层自己实现（QUIC 就是 UDP 上实现可靠传输）。

## 4. Socket 编程

### 4.1 TCP 编程流程

```cpp
TCP 服务端                           TCP 客户端
socket()                             socket()
  |                                    |
bind()                               connect()  ←—— 三次握手 ——→ 服务端 accept
  |
listen()
  |
accept()  ←——— 三次握手完成 ————→     连接建立
  |                                    |
read/write() <———— 数据通信 ————>     read/write()
  |                                    |
close()                              close()
```

```c
// 服务端核心代码
int fd = socket(AF_INET, SOCK_STREAM, 0);          // 创建 TCP socket
int opt = 1;
setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt)); // 允许端口复用

struct sockaddr_in addr = {0};
addr.sin_family = AF_INET;
addr.sin_addr.s_addr = htonl(INADDR_ANY);           // 绑定所有网卡
addr.sin_port = htons(8080);
bind(fd, (struct sockaddr*)&addr, sizeof(addr));

listen(fd, 128);                                     // backlog=已完成连接队列上限

struct sockaddr_in caddr;
socklen_t clen = sizeof(caddr);
int cfd = accept(fd, (struct sockaddr*)&caddr, &clen); // 阻塞等待连接

char buf[4096];
ssize_t n = recv(cfd, buf, sizeof(buf), 0);          // 读数据
send(cfd, buf, n, 0);                                  // 写回
close(cfd);
close(fd);
```

```c
// 客户端核心代码
int fd = socket(AF_INET, SOCK_STREAM, 0);
struct sockaddr_in addr = {0};
addr.sin_family = AF_INET;
addr.sin_port = htons(8080);
inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr);    // 点分十进制转网络字节序
connect(fd, (struct sockaddr*)&addr, sizeof(addr));  // 发起三次握手
send(fd, "hello", 5, 0);
char buf[4096];
recv(fd, buf, sizeof(buf), 0);
close(fd);
```

### 4.2 关键 Socket 选项

| 选项 | 层级 | 作用 | 典型值 |
| --- | --- | --- | --- |
| SO_REUSEADDR | SOL_SOCKET | 允许绑定 TIME_WAIT 状态的端口 | 1 |
| SO_REUSEPORT | SOL_SOCKET | 多进程/线程绑定同一端口（内核负载均衡） | 1 |
| SO_RCVBUF | SOL_SOCKET | 接收缓冲区大小 | 默认 ~212992，可调大 |
| SO_SNDBUF | SOL_SOCKET | 发送缓冲区大小 | 默认 ~212992 |
| SO_KEEPALIVE | SOL_SOCKET | 开启 TCP 保活探测 | 1（默认 2 小时无数据才探测） |
| SO_ERROR | SOL_SOCKET | 获取 socket 错误并清除 | getsockopt 读取 |
| TCP_NODELAY | IPPROTO_TCP | 禁用 Nagle 算法（小包立即发） | 1（低延迟场景） |
| TCP_CORK | IPPROTO_TCP | 累积小包一起发（与 NODELAY 相反） | 1（批量发送） |
| TCP_KEEPIDLE | IPPROTO_TCP | 保活探测空闲时间 | 60（秒） |
| TCP_KEEPINTVL | IPPROTO_TCP | 保活探测间隔 | 10（秒） |
| TCP_KEEPCNT | IPPROTO_TCP | 保活探测次数 | 3 |

**Nagle 算法**：小包（小于 MSS）不立即发送，等 ACK 或攒够一个 MSS 再发。减少网络中小包数量，但增加延迟。交互场景（SSH、游戏）用 `TCP_NODELAY` 禁用。

**字节序**：网络字节序是大端，x86 是小端。`htons/htonl`（主机→网络）、`ntohs/ntohl`（网络→主机）。端口和 IP 必须转换，结构体内部多字节字段也要注意。

### 4.3 listen 的 backlog

`listen(fd, backlog)` 的 backlog 在现代 Linux（2.2+）中是**已完成连接队列**（ESTABLISHED 但未 accept）的上限。半连接队列（SYN_RECV）由 `tcp_max_syn_backlog` 单独控制。accept 从已完成队列取连接，队列满时新的三次握手最终 ACK 被丢弃（客户端重传）。

## 5. IO 模型与多路复用

### 5.1 五种 IO 模型

| 模型 | 等待数据 | 拷贝数据 | 说明 |
| --- | --- | --- | --- |
| 阻塞 IO | 阻塞 | 阻塞 | recv 一直等，最简单 |
| 非阻塞 IO | 立即返回 EAGAIN | 阻塞 | 轮询，CPU 浪费 |
| IO 多路复用 | select/poll/epoll 阻塞 | 阻塞 | 一个线程等多个 fd |
| 信号驱动 IO | SIGIO 通知 | 阻塞 | 少用 |
| 异步 IO（AIO） | 立即返回 | 内核拷贝完通知 | 真正异步，Linux 原生支持有限 |

**IO 两个阶段**：①等待数据就绪（数据从网络到内核缓冲区）②数据从内核缓冲区拷贝到用户空间。前四种模型阶段②都阻塞，只有 AIO 两个阶段都不阻塞。

### 5.2 select / poll / epoll 对比

| 维度 | select | poll | epoll |
| --- | --- | --- | --- |
| 描述符上限 | FD_SETSIZE（默认 1024） | 无上限（数组） | 无上限 |
| 数据结构 | 位图（fd_set） | pollfd 数组 | 红黑树 + 就绪链表 |
| 每次调用拷贝 | 全量拷贝 fd_set | 全量拷贝 pollfd 数组 | 事件注册一次，epoll_wait 只返回就绪 |
| 检测就绪 | O(n) 全量扫描 | O(n) 全量扫描 | O(1) 就绪链表 |
| 触发模式 | 水平触发 | 水平触发 | 水平触发(LT) / 边缘触发(ET) |
| 适用场景 | 连接少（<1024） | 连接中等 | 高并发（C10K+） |

```c
// epoll 核心三步
int epfd = epoll_create1(0);                          // 创建 epoll 实例
struct epoll_event ev;
ev.events = EPOLLIN | EPOLLET;                        // 读事件 + 边缘触发
ev.data.fd = listen_fd;
epoll_ctl(epfd, EPOLL_CTL_ADD, listen_fd, &ev);      // 注册监听 fd

struct epoll_event events[MAX_EVENTS];
int n = epoll_wait(epfd, events, MAX_EVENTS, -1);    // 阻塞等待就绪
for (int i = 0; i < n; ++i) {
    if (events[i].data.fd == listen_fd) {
        // accept 新连接，加入 epoll
    } else if (events[i].events & EPOLLIN) {
        // 读数据
    }
}
```

**LT vs ET**：
- **水平触发(LT)**：只要缓冲区有数据就一直通知，直到数据被读走。简单、不易丢事件。
- **边缘触发(ET)**：只在状态变化时通知一次（从无数据到有数据）。必须**循环读直到 EAGAIN**，否则剩余数据不会再通知，造成"丢事件"。
- ET 必须配合**非阻塞 IO**：如果阻塞读，循环读时缓冲区读完会阻塞在 recv 上，整个事件循环卡死。

## 6. 粘包与拆包

TCP 是**字节流协议**，没有消息边界。N 次 send 可能被对端 1 次 recv 读到（粘包），1 次 send 可能被对端多次 recv 读到（拆包）。根本原因：TCP 按 MSS/窗口/拥塞控制打包，不关心应用层消息边界。

### 6.1 三种解决方案

| 方案 | 说明 | 优点 | 缺点 |
| --- | --- | --- | --- |
| 定长包 | 每条消息固定长度 | 简单 | 浪费空间，不适合变长 |
| 分隔符 | 用特殊字符（\r\n、\0）分隔 | 人类可读 | 数据中不能含分隔符（需转义），扫描效率低 |
| 长度前缀 | 头部固定字节声明 body 长度 | 高效、灵活（最常用） | 需先读头再读体 |

### 6.2 长度前缀协议实现

```c
// 协议：4 字节大端长度 + body
// 发送
bool send_msg(int fd, const char* body, uint32_t len) {
    char head[4];
    head[0] = (len >> 24) & 0xFF;
    head[1] = (len >> 16) & 0xFF;
    head[2] = (len >> 8) & 0xFF;
    head[3] = len & 0xFF;
    // write 可能部分写，生产需循环写满
    if (write(fd, head, 4) != 4) return false;
    return write(fd, body, len) == (ssize_t)len;
}

// 接收：先读 4 字节头，再按长度读 body
bool recv_msg(int fd, char* out, uint32_t max_len, uint32_t* out_len) {
    char head[4];
    if (!readn(fd, head, 4)) return false;          // readn：循环读满 n 字节
    uint32_t len = ((uint8_t)head[0] << 24) | ((uint8_t)head[1] << 16) |
                   ((uint8_t)head[2] << 8) | (uint8_t)head[3];
    if (len == 0 || len > max_len) return false;     // 长度校验，防恶意大包
    if (!readn(fd, out, len)) return false;
    *out_len = len;
    return true;
}

// readn：循环 read 直到读满 n 字节（处理拆包）
ssize_t readn(int fd, char* buf, size_t n) {
    size_t total = 0;
    while (total < n) {
        ssize_t r = read(fd, buf + total, n - total);
        if (r < 0) {
            if (errno == EINTR) continue;             // 信号中断，重试
            return -1;
        }
        if (r == 0) return total;                      // 对端关闭
        total += r;
    }
    return total;
}
```

## 7. 半关闭与优雅断开

- `shutdown(fd, SHUT_WR)`：关闭写端，仍可读对端剩余数据。用于"我发完了但还想收"的场景。
- `shutdown(fd, SHUT_RD)`：关闭读端，后续到达的数据被 ACK 后丢弃，对端不会收到 RST。
- `shutdown(fd, SHUT_RDWR)`：读写全关，等同于 close（但引用计数不减）。
- `close(fd)`：减少引用计数，计数为 0 时真正关闭（发 FIN）。多进程共享 fd 时需注意。

**优雅断开流程**：应用层发完数据 → `shutdown(SHUT_WR)` 发 FIN → 继续读对端剩余数据 → 读到 0（对端也关了）→ `close()`。避免直接 close 导致对端数据没读完就 RST。

**心跳保活**：
- `SO_KEEPALIVE`：TCP 层保活，默认 2 小时无数据才探测，间隔 75 秒，9 次失败判定断开。太不灵敏，生产很少直接用。
- **应用层心跳**：业务自己定义心跳包（如每 30 秒发 Ping，90 秒未收到 Pong 断开），灵活可控，推荐。

## 8. DNS 解析过程

```text
应用程序 → 系统调用 getaddrinfo() → /etc/hosts 检查
  → 本地 DNS 缓存（nscd/systemd-resolved）
  → /etc/resolv.conf 指定的 DNS 服务器（递归查询）
    → 根域名服务器（.）→ 顶级域服务器（.com）→ 权威服务器（example.com）
  → 返回 IP 列表，应用按顺序尝试连接
```

**DNS 缓存**：浏览器缓存 → 操作系统缓存 → 本地 DNS 服务器缓存 → 权威服务器。TTL（生存时间）控制缓存有效期。DNS 解析可能阻塞，高并发服务用异步 DNS 或提前解析缓存 IP。

## 9. 快速参考卡片

```cpp
TCP 首部 20 字节：端口×2 + seq + ack + 偏移/标志 + 窗口 + 校验和 + 紧急
三次握手：SYN → SYN+ACK → ACK（确认双方能力 + 防失效连接 + 同步 ISN）
四次挥手：FIN → ACK → FIN → ACK（被动方可能还有数据，ACK/FIN 分开）
TIME_WAIT：2MSL，保证最后 ACK 可达 + 旧报文消亡；SO_REUSEADDR 缓解
拥塞控制：慢启动(指数) → 拥塞避免(线性) → 快重传(3 dup ACK) → 快恢复
UDP 首部 8 字节，无连接不可靠，适合实时音视频/DNS/游戏
Socket：socket→bind→listen→accept→读写→close
epoll：红黑树+就绪链表，ET 必须非阻塞+循环读到 EAGAIN
粘包：TCP 字节流无边界，长度前缀是标准解
字节序：网络大端，htons/htonl/ntohs/ntohl
```

---

## 10. 常见坑

1. 边缘触发(ET)下必须循环读直到 `EAGAIN`，否则剩余数据不再通知，造成"丢事件"。
2. `accept` 返回的新 fd 必须设置非阻塞（`fcntl(fd, F_SETFL, O_NONBLOCK)`），ET 模式下阻塞读会卡死事件循环。
3. 读写必须处理 `EINTR`（信号中断）和 `EAGAIN`（非阻塞无数据），前者重试后者等下一次事件。
4. 粘包问题不能只做一次 `read` 就当完整消息，必须用长度前缀/分隔符/定长协议 + 读半包缓冲。
5. `listen` 的 backlog 是已完成连接队列上限，半连接队列由 `tcp_max_syn_backlog` 控制；队列满时最终 ACK 被丢弃。
6. `close()` 只是减引用计数，多进程 fork 后父子各有一份 fd，必须都 close 才真正发 FIN。
7. `SO_KEEPALIVE` 默认 2 小时才探测，生产用应用层心跳（30s 间隔、90s 超时）。
8. `TCP_NODELAY` 禁用 Nagle 降低延迟，但会增加小包数量；批量传输场景用 `TCP_CORK` 攒包。
9. 大文件传输用 `sendfile` 零拷贝（详见《../15-中间件与微服务/04-性能分析与调优.md》），避免 read+write 的用户态拷贝。
10. connect 超时默认很长（~75 秒），非阻塞 connect + `epoll` 监听可自定义超时。

---

下一篇：《02-百万并发与TCP栈优化.md》　｜　模块索引：《../README.md》
