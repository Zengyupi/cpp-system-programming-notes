# TCP 报文与三次握手四次挥手深度剖析

> 本节目标：这是本模块最重要的一篇。逐字段拆 TCP 首部与标志位，讲透**为什么握手是三次、挥手是四次**、11 种连接状态、TIME_WAIT/2MSL、半连接与全连接队列、RST 场景，并用真实抓包逐包验证。面试和工程（连接排障、高并发调优）都靠它。参数调优见《../01-C++技术体系/12-网络与服务器架构/02-百万并发与TCP栈优化.md》。

## 本章速览

- [1. TCP 首部（默认 20 字节，选项可变）](#1-tcp-首部默认-20-字节选项可变)
  - [1.1 六个控制位（标志位，抓包每包都看）](#11-六个控制位标志位抓包每包都看)
  - [1.2 常见 TCP 选项（Options，握手时协商）](#12-常见-tcp-选项options握手时协商)
- [2. 三次握手（建立连接）](#2-三次握手建立连接)
  - [2.1 过程与序号变化](#21-过程与序号变化)
  - [2.2 为什么是三次，不是两次/四次（高频面试）](#22-为什么是三次不是两次四次高频面试)
  - [2.3 半连接队列 / 全连接队列（工程排障关键）](#23-半连接队列--全连接队列工程排障关键)
- [3. 四次挥手（断开连接）与状态机](#3-四次挥手断开连接与状态机)
  - [3.1 过程（TCP 全双工，两个方向要分别关）](#31-过程tcp-全双工两个方向要分别关)
  - [3.2 为什么挥手是四次，而握手是三次](#32-为什么挥手是四次而握手是三次)
  - [3.3 十一种连接状态（务必能背+解释）](#33-十一种连接状态务必能背解释)
- [4. TIME_WAIT / 2MSL 与 CLOSE_WAIT（排障高频）](#4-time_wait--2msl-与-close_wait排障高频)
  - [4.1 为什么主动关闭方要有 TIME_WAIT 等 2MSL](#41-为什么主动关闭方要有-time_wait-等-2msl)
  - [4.2 大量 TIME_WAIT 怎么办](#42-大量-time_wait-怎么办)
  - [4.3 大量 CLOSE_WAIT = 应用代码有 bug](#43-大量-close_wait--应用代码有-bug)
- [5. RST：异常关闭与常见触发](#5-rst异常关闭与常见触发)
- [6. 可靠性机制串讲（理解 seq/ack 的意义）](#6-可靠性机制串讲理解-seqack-的意义)
- [7. 真实抓包对照（tcpdump / Wireshark）](#7-真实抓包对照tcpdump--wireshark)
- [8. 快速参考卡片](#8-快速参考卡片)
- [9. 常见问题与坑](#9-常见问题与坑)
- [10. 延伸阅读](#10-延伸阅读)

---

## 1. TCP 首部（默认 20 字节，选项可变）

```text
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|          Source Port (16)     |     Destination Port (16)     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    Sequence Number (32)                       |  序号 seq
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                Acknowledgment Number (32)                    |  确认号 ack
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|DataOff(4)|Reserved| 控制位 CWR..FIN (8/9) |     Window (16)    |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|      Checksum (16)            |   Urgent Pointer (16)         |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  Options (DataOffset>5, 0~40B) ...   | Padding                |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                          应用数据 ...                          |
```

| 字段 | 含义/要点 |
| --- | --- |
| Src/Dst Port | 源/目的端口，和 IP 一起唯一确定一条连接（四元组） |
| Sequence Number | 本报文段**第一个数据字节**的编号；SYN/FIN 也各占一个序号 |
| Ack Number | **期望收到的下一个字节序号**=已收到最后序号+1（累计确认） |
| Data Offset | 首部长度，单位 4 字节（同 IP 的 IHL），最小 5 |
| Window | 接收窗口（流量控制），告诉对方我还能收多少 |
| Checksum | 校验**首部+数据+伪首部**（含源/目 IP），比 IP 校验覆盖全 |
| Urgent Pointer | 带外数据，少用 |

### 1.1 六个控制位（标志位，抓包每包都看）

| 位 | 全称 | 含义 |
| --- | --- | --- |
| **SYN** | Synchronize | 请求建立连接、同步初始序号（握手用） |
| **ACK** | Acknowledgment | 确认号有效（连接建立后几乎所有包都带 ACK） |
| **FIN** | Finish | 请求关闭，我没数据要发了（挥手用） |
| **RST** | Reset | 异常复位/拒绝连接/强制中断 |
| PSH | Push | 提示尽快上交应用，别在缓冲区攒着 |
| URG | Urgent | 紧急指针有效（少用）；另有 CWR/ECE 用于拥塞通知 |

### 1.2 常见 TCP 选项（Options，握手时协商）

- **MSS**（最大报文段，一般 1460 = 1500-20IP-20TCP）：在源头避免 IP 分片；
- **Window Scale**：窗口缩放因子，让 16 位窗口能表示 >64KB（高并发高带宽必需）；
- **SACK**：选择性确认，丢一个包不必重传全部；
- **Timestamps**：RTT 测量、PAWS 防旧序号；
- 抓包里 SYN 带这些选项，SYN-ACK 回应达成一致。

## 2. 三次握手（建立连接）

### 2.1 过程与序号变化

```text
客户端(主动)                          服务端(被动监听 listen)
  CLOSED                                LISTEN
    │  ① SYN, seq=x (ISN随机)              │
    │ ───────────────────────────────────→ │  收到：服务端 SYN_RCVD，进半连接队列
    │        ② SYN,ACK seq=y, ack=x+1       │
    │ ←─────────────────────────────────── │
    │  ③ ACK, ack=y+1 (可携带数据)          │  收到：连接就绪，进全连接队列
    │ ───────────────────────────────────→ │  ESTABLISHED
  ESTABLISHED
```

- **ISN（初始序号）随机**：不是从 0 开始，防止历史残留报文/序号预测攻击；
- SYN、FIN 即使不带数据也**消耗一个序号**，所以确认号是 x+1、y+1；
- 第三次握手的 ACK **可以携带第一批数据**（TCP Fast Open 还能在 SYN 带数据）。

### 2.2 为什么是三次，不是两次/四次（高频面试）

- **两次不够**：服务器收到 SYN 就建立连接，但如果是一个迟到/伪造的旧 SYN，服务器会白白建立连接等数据，造成资源浪费；且客户端无法确认服务器的收发能力、双方 ISN 无法都确认。
- **三次刚好**：客户端发、服务端确认+发自己的（SYN+ACK 合并成一步，所以比挥手少一次）、客户端再确认。**双方都确认了"自己发的对方能收、对方发的自己能收"，并交换了彼此的 ISN**。
- **四次多余**：服务端的 ACK 和 SYN 可以合并在一个包里，没必要拆开。
- 一句话：**两次无法防止历史连接、无法双向确认序号；三次是理论最小值。**

### 2.3 半连接队列 / 全连接队列（工程排障关键）

```text
SYN 到达 → SYN_RCVD 放【半连接队列 syn backlog】，回 SYN+ACK，等最后 ACK
最后 ACK 到达 → 移入【全连接队列 accept queue】，等 accept() 取走
```

- 半连接队列溢出 → 丢弃 SYN 或回 RST（`tcp_max_syn_backlog`），是 **SYN Flood 攻击**打满的位置；
- 全连接队列溢出（应用 accept 太慢）→ 丢 ACK/重传，表现为**连接建立慢、握手丢包**（`ss -lnt` 看 Send-Q/Recv-Q 是否打满，backlog 由 listen 参数和 somaxconn 共同决定）；
- **SYN Cookie**：半连接队列被打满时用算法无状态验证，防 SYN Flood。

## 3. 四次挥手（断开连接）与状态机

### 3.1 过程（TCP 全双工，两个方向要分别关）

```text
主动关闭方 A                          被动关闭方 B
ESTABLISHED                           ESTABLISHED
   │ ① FIN,ACK seq=u                      │
   │ ──────────────────────────────────→ │  B: CLOSE_WAIT
   │      ② ACK ack=u+1                   │  A: FIN_WAIT_2
   │ ←────────────────────────────────── │
   │        （B 把剩余数据发完……）          │
   │       ③ FIN,ACK seq=w                 │
   │ ←────────────────────────────────── │  B: LAST_ACK
   │ ④ ACK ack=w+1                        │
   │ ──────────────────────────────────→ │  B 收到即 CLOSED
   │ A: TIME_WAIT，等 2MSL 后 CLOSED
```

### 3.2 为什么挥手是四次，而握手是三次

- 握手时服务端的 SYN 和 ACK **可以合并**成一个 SYN+ACK；
- 挥手时收到对方 FIN，只代表**对方没数据发了，但我可能还有数据要发**，所以先回 ACK（②），等自己数据发完再发自己的 FIN（③），ACK 和 FIN **通常不能合并**，于是四次。
- 若被动方也没数据要发，且开启了延迟确认之外的合并，可能出现 **FIN+ACK 同包**，抓包看到三次挥手也正常。

### 3.3 十一种连接状态（务必能背+解释）

| 状态 | 出现方 | 含义 |
| --- | --- | --- |
| LISTEN | 服务端 | 监听中，等待连接 |
| SYN_SENT | 客户端 | 已发 SYN，等 SYN+ACK |
| SYN_RCVD | 服务端 | 收到 SYN 发了 SYN+ACK，等最后 ACK |
| ESTABLISHED | 双方 | 连接已建立 |
| FIN_WAIT_1 | 主动方 | 已发 FIN |
| FIN_WAIT_2 | 主动方 | 对方已 ACK，等对方 FIN（半关闭） |
| **TIME_WAIT** | **主动方** | 收到对方 FIN 并回 ACK，等 2MSL |
| CLOSE_WAIT | 被动方 | 收到 FIN 回了 ACK，**等本地 close()** |
| LAST_ACK | 被动方 | 自己也发了 FIN，等最后 ACK |
| CLOSING | 主动方 | 双方同时关闭的罕见状态 |
| CLOSED | 双方 | 彻底关闭 |

状态迁移总图：

```text
主动方：ESTABLISHED → FIN_WAIT_1 →(收ACK)→ FIN_WAIT_2 →(收FIN)→ TIME_WAIT →(2MSL)→ CLOSED
被动方：ESTABLISHED →(收FIN)→ CLOSE_WAIT →(本地close)→ LAST_ACK →(收ACK)→ CLOSED
```

## 4. TIME_WAIT / 2MSL 与 CLOSE_WAIT（排障高频）

### 4.1 为什么主动关闭方要有 TIME_WAIT 等 2MSL

1. **保证最后一个 ACK 能到达**：若 ACK 丢了，对方会重发 FIN，主动方在 2MSL 内还能重发 ACK；若直接 CLOSED，对方重发 FIN 到达时只能回 RST，对方无法正常关闭。
2. **让本次连接的旧报文在网络中自然消亡**：避免延迟的旧数据包被复用了相同四元组的新连接误收。
- MSL 是报文最大生存时间，Linux 默认 60s（`tcp_fin_timeout` 影响相关等待），2MSL=120s（实现上 TIME_WAIT 默认约 60s）。

### 4.2 大量 TIME_WAIT 怎么办

- **谁主动 close 谁产生 TIME_WAIT**：高并发短连接里客户端/反向代理主动关闭会堆积大量 TIME_WAIT；
- 正常现象，TIME_WAIT 不占太多资源但占**四元组（本地端口）**，可能耗尽临时端口；
- 手段：长连接/连接池、`SO_REUSEADDR`/`tcp_tw_reuse`、增加端口范围、让服务端主动关（视架构）；**不要盲目开 `tcp_tw_recycle`（已在新内核移除且在 NAT 下有害）**。

### 4.3 大量 CLOSE_WAIT = 应用代码有 bug

CLOSE_WAIT 是**被动方收到 FIN 也回了 ACK，但应用层一直没调用 close()**。堆积 CLOSE_WAIT 几乎一定是：**忘了关连接、异常路径没释放 fd、线程池阻塞导致没处理关闭**。这是代码问题，不是调内核参数能解决的——排查应用的连接生命周期（呼应《../01-C++技术体系/01-语言基础/04-内存管理与智能指针.md》的 RAII、《../01-C++技术体系/03-网络编程/02-IO多路复用与Reactor模型.md》的连接管理）。

## 5. RST：异常关闭与常见触发

收到/发送 RST 表示**异常终止**（不是优雅的 FIN 挥手）。常见场景：

| 场景 | 说明 |
| --- | --- |
| 访问没人监听的端口 | 内核回 RST（connect 报 Connection refused） |
| 连接已关闭还收到数据 | 半开/对端已不在，回 RST |
| 收到不属于任何连接的包 | 回 RST |
| 应用设置 SO_LINGER 强制复位 | 跳过 TIME_WAIT 直接 RST（慎用） |
| 异常崩溃/重启 | 再收到数据回 RST |

抓包看到握手阶段就 RST：多为端口没监听、被防火墙 reject、backlog 满；数据传输中偶发 RST：半关闭处理、对端进程重启、空闲被中间设备清表（需要 keepalive）。

## 6. 可靠性机制串讲（理解 seq/ack 的意义）

- **累计确认 + 超时重传**：ack=N 表示 N 之前都收到了；定时器超时未确认就重传；
- **滑动窗口**：接收方通过 Window 字段做流量控制；
- **拥塞控制**：慢启动/拥塞避免/快重传/快恢复，靠丢包和 SACK 判断网络；
- **Nagle 与延迟 ACK**：Nagle 攒小包（`TCP_NODELAY` 关闭，交互/工业协议常关以降延迟），延迟 ACK 攒确认，两者叠加可能造成"请求卡 40ms"经典问题；
- **保活 keepalive**：长时间空闲探测对端是否存活（工业长连接、NAT 环境常用，应用层心跳更可靠）。

## 7. 真实抓包对照（tcpdump / Wireshark）

```bash
# 抓一次完整连接，看握手挥手（-S 绝对序号，-n 不解析名字）
tcpdump -i any -nn -S 'host 192.168.1.10 and tcp port 502'
```

```text
握手：
10:00:01.100 C.51002 > S.502  Flags [S],  seq 1000,        win 64240, options [mss 1460,sackOK,TS,wscale 7]
10:00:01.101 S.502  > C.51002 Flags [S.], seq 3000, ack 1001, win 65160, options [mss 1460,wscale 7]
10:00:01.101 C.51002 > S.502  Flags [.],  ack 3001                    # 第三次握手，[.] 表示纯ACK
数据：
10:00:01.120 C > S Flags [P.], seq 1001:1013, ack 3001, length 12     # PSH+ACK 发12字节(Modbus)
10:00:01.121 S > C Flags [.],  ack 1013
挥手：
10:00:02.000 C > S Flags [F.], seq 1013, ack 3001
10:00:02.001 S > C Flags [.],  ack 1014
10:00:02.030 S > C Flags [F.], seq 3001, ack 1014
10:00:02.030 C > S Flags [.],  ack 3002
```

Wireshark 里右键一条流 → Follow → TCP Stream 看完整请求/响应；Statistics → Flow Graph 看时序。过滤技巧见 08 篇与《../01-C++技术体系/08-网络与系统工具/02-tcpdump网络抓包.md》。

## 8. 快速参考卡片

```text
标志位：SYN建连 FIN关闭 ACK确认 RST复位 PSH速交 URG紧急
握手：SYN(x) → SYN+ACK(y,ack x+1) → ACK(ack y+1)；三次=双向确认ISN+防历史连接，理论最小
挥手：FIN → ACK → FIN → ACK；四次=全双工，对方ACK与FIN不能合并(没数据时可合并变三次)
队列：半连接(SYN_RCVD,防SYN Flood,cookie) → 全连接(accept,backlog/somaxconn)
TIME_WAIT：主动方，2MSL=保最后ACK可达+旧报文消亡；占端口，用长连接/reuse，别开recycle
CLOSE_WAIT 堆积=应用没close()，代码bug不是内核问题
RST：端口没监听/半开发数据/强制复位；握手RST查监听/防火墙/backlog
Nagle+延迟ACK 可能卡40ms，低延迟场景 TCP_NODELAY
```

## 9. 常见问题与坑

| 问题 | 根因/解决 |
| --- | --- |
| 握手第三次 ACK 丢了会怎样 | 服务端重传 SYN+ACK；客户端已 ESTABLISHED，发数据时会捎带 ACK |
| 为什么不是两次握手 | 防历史旧 SYN 建立无效连接、双方需互确认 ISN |
| TIME_WAIT 太多是不是故障 | 主动关闭的正常结果；占端口才需处理，优先长连接/连接池 |
| CLOSE_WAIT 大量堆积 | 应用异常路径没 close(fd)，查连接释放/阻塞 |
| connect 立刻 Connection refused | 对端端口无监听回 RST（区别于超时=丢包/防火墙 DROP） |
| 连接空闲一段时间后第一次请求失败 | NAT/防火墙清表；开 keepalive 或应用层心跳 |
| 小包交互延迟约 40ms | Nagle+延迟 ACK 叠加，设 TCP_NODELAY |
| seq 抓包显示很大随机值 | ISN 随机化防预测；Wireshark 默认显示相对序号，-S 看绝对 |

## 10. 延伸阅读

- TCP RFC 9293（现行，取代 RFC 793）：[datatracker.ietf.org/doc/html/rfc9293](https://datatracker.ietf.org/doc/html/rfc9293)
- Congestion Control RFC 5681；TIME_WAIT/2MSL 见 RFC 9293 相关章节
- Wireshark TCP 分析：[wiki.wireshark.org/TCP_Analyze_Sequence_Numbers](https://wiki.wireshark.org/TCP_Analyze_Sequence_Numbers)
- 内核参数调优见《../01-C++技术体系/12-网络与服务器架构/02-百万并发与TCP栈优化.md》；连接管理见《../01-C++技术体系/03-网络编程/02-IO多路复用与Reactor模型.md》；下一篇《05-UDP-DNS-DHCP报文.md》

---

上一篇：《03-IP-ARP-ICMP报文详解.md》　｜　下一篇：《05-UDP-DNS-DHCP报文.md》　｜　模块索引：《README.md》
