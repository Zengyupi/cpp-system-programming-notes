# 用户态协议栈与DPDK

> 本节目标：掌握内核旁路（kernel bypass）的原理与用户态协议栈的完整实现链路——理解内核协议栈四大开销，掌握 DPDK 五板斧（UIO/VFIO、大页、绑核、rte_ring、PMD 轮询）与 mbuf 结构；能手写二/三/四层协议头（以太网/ARP/ICMP/IP/UDP/TCP）与校验和计算，掌握 TCP 11 状态表驱动实现、滑动窗口与拥塞控制、RTO 计算与四定时器；理解用户态 fd 表与 POSIX API 复刻原理，能手写 epoll 核心（红黑树+就绪链表+LT/ET 回调）。前置《../12-网络与服务器架构/01-网络基础与TCP-IP.md》（TCP/IP 协议基础）、《../11-算法与数据结构/02-算法手撕与手写实现.md》（红黑树），关联《02-io_uring与异步IO.md》（另一种降开销方案）、《07-原子操作与无锁组件.md》（rte_ring 无锁队列剖析）。 课程模块 2.4：基于 DPDK 的用户态协议栈：协议栈设计实现、TCP 原理实现、应用层 POSIX API 实现、手写 epoll。前置：`../03-计算机网络编程/02-IO多路复用与Reactor模型.md`、`../04-并发与多线程编程/01-并发编程与线程同步.md`、`02-算法手撕与手写实现.md`（红黑树）、`13-原子操作与无锁组件.md`（rte_ring）。

## 本章速览

- [1. 概述](#1-概述)
  - [1.1 内核协议栈的四大开销【高频】](#11-内核协议栈的四大开销高频)
  - [1.2 收发包路径对比](#12-收发包路径对比)
  - [1.3 内核旁路方案一览](#13-内核旁路方案一览)
- [2. DPDK 核心机制](#2-dpdk-核心机制)
  - [2.1 体系结构](#21-体系结构)
  - [2.2 mbuf 结构要点](#22-mbuf-结构要点)
  - [2.3 rte_ring 无锁环形队列](#23-rte_ring-无锁环形队列)
  - [2.4 netmap 与 DPDK 对比](#24-netmap-与-dpdk-对比)
  - [2.5 环境搭建速查](#25-环境搭建速查)
- [3. 二层协议实现](#3-二层协议实现)
  - [3.1 以太网帧格式](#31-以太网帧格式)
  - [3.2 ARP 实现](#32-arp-实现)
  - [3.3 ICMP 实现](#33-icmp-实现)
- [4. 三层与 UDP](#4-三层与-udp)
  - [4.1 IP 协议](#41-ip-协议)
  - [4.2 UDP 协议](#42-udp-协议)
- [5. TCP 实现【核心】](#5-tcp-实现核心)
  - [5.1 TCP 头格式](#51-tcp-头格式)
  - [5.2 11 状态与事件驱动状态机](#52-11-状态与事件驱动状态机)
  - [5.3 滑动窗口与慢启动实现要点](#53-滑动窗口与慢启动实现要点)
  - [5.4 四个定时器【高频】](#54-四个定时器高频)
- [6. 应用层 POSIX API 实现](#6-应用层-posix-api-实现)
  - [6.1 用户态 fd 表设计](#61-用户态-fd-表设计)
  - [6.2 各 API 的语义复刻](#62-各-api-的语义复刻)
  - [6.3 应用无感迁移原理](#63-应用无感迁移原理)
- [7. 手写 epoll【核心】](#7-手写-epoll核心)
  - [7.1 要复刻的三接口语义](#71-要复刻的三接口语义)
  - [7.2 数据结构设计](#72-数据结构设计)
  - [7.3 线程安全实现](#73-线程安全实现)
  - [7.4 协议栈 fd 就绪回调](#74-协议栈-fd-就绪回调)
  - [7.5 epoll_wait 语义](#75-epoll_wait-语义)
  - [7.6 LT / ET 语义实现要点【高频】](#76-lt--et-语义实现要点高频)
- [8. 开源参考](#8-开源参考)
- [9. 快速参考卡片](#9-快速参考卡片)
- [10. 常见问题与坑](#10-常见问题与坑)

---

## 1. 概述

### 1.1 内核协议栈的四大开销【高频】

| 开销 | 说明 | 量级 |
|---|---|---|
| 系统调用上下文 | 每次 send/recv 陷入内核：用户/内核态切换、寄存器保存恢复 | 单次约 1~5μs，高 PPS 下累计可观 |
| 硬中断 + 软中断 | 每包触发网卡硬中断打断业务线程；软中断在内核继续处理 | 10G 线速小包可达每秒千万级中断 |
| 协议栈通用处理无法裁剪 | 内核为通用性保留全部分支：分片重组、Netfilter 钩子、路由查表、socket 查找 | 业务用不到的处理一样不少 |
| 内核↔用户数据拷贝 | skb 拷到用户缓冲（copy_to_user），反之亦然 | 每包 1~2 次拷贝 + cache 污染 |

一句话：内核栈是通用实现，转发类业务只想榨干网卡，于是把协议栈整体搬进用户态——内核旁路（kernel bypass）。

### 1.2 收发包路径对比

```text
内核协议栈收包路径（慢）:
 网卡 → DMA到内核skb → 硬中断IRQ → 软中断net_rx_action
      → ip_rcv(Netfilter钩子) → tcp_v4_rcv → socket接收队列
      → 唤醒阻塞进程 → recvfrom系统调用 → copy_to_user → 应用

用户态协议栈收包路径（快）:
 网卡 → DMA直接到大页内存(rx ring的mbuf)
      → PMD轮询线程直接取包（零中断、零系统调用）
      → 用户态协议栈(eth→ip→tcp) → 应用直接读内存（零拷贝）
```

路径差异：中断 → PMD 轮询（代价：收包核空闲时也占满 CPU）；"系统调用+拷贝" → 直接读共享内存；协议处理可按业务裁剪；代价是集成 SDK、改造应用。

### 1.3 内核旁路方案一览

| 方案 | 定位 | 一句话特点 |
|---|---|---|
| netmap | 学术零拷贝框架 | 网卡收发 ring 直接映射到用户态，包槽批量交换，代码极简 |
| DPDK | 工业级用户态数据面框架 | 用户态 PMD 驱动 + 大页 + 无锁库 + CPU 亲和，生态最全 |
| XDP | 内核内快速路径 | eBPF 程序在驱动收包点执行，不离开内核，适合 DDoS 清洗 |
| io_uring | 异步系统调用接口 | 不旁路协议栈，只消灭 syscall 开销，见 `08-io_uring与异步IO.md` |

选型：要极致转发性能且能改造应用 → DPDK；包进协议栈前丢垃圾 → XDP；只省 syscall → io_uring。

## 2. DPDK 核心机制

### 2.1 体系结构

```text
+----------------------------------------------------------+
|                 应用 + 用户态协议栈                        |
|  (tcp/udp/icmp/arp)  (自研 epoll)  (POSIX API 复刻)      |
+----------------------------------------------------------+
|                     DPDK 库 (用户态)                      |
|  rte_ethdev(PMD驱动) rte_mbuf rte_ring rte_mempool      |
|  rte_eal(环境抽象) rte_timer rte_kni(与内核互通)          |
+----------------------------------------------------------+
|        UIO / VFIO (用户态驱动靠它访问设备寄存器)            |
+----+---------------------------+-------------------------+
     | mmap 设备寄存器/大页 DMA  | 少量管理面走内核
+----v-----------+       +------v----------+
|    网卡(NIC)    |       | 内核(不再处理它) |
+----------------+       +-----------------+
```

| 机制 | 说明 | 示例 |
|---|---|---|
| UIO | 精简内核模块只做 PCI 映射与中断通知，寄存器操作全在用户态 | igb_uio |
| VFIO | 依赖 IOMMU，设备 DMA 限制在授权内存，更安全 | 云环境首选 |
| 大页 | 2MB/1GB 替代 4KB 页，TLB 覆盖范围扩大，减少 miss | `/sys/kernel/mm/hugepages` |
| CPU 亲和 | 收包线程绑死某个核，避免迁移与缓存失效 | `rte_eal` 的 `-l` 参数 |
| 无锁队列 | rte_ring 纯原子操作 FIFO，跨核传递 mbuf | 见 2.3 与 `13-原子操作与无锁组件.md` |
| PMD 轮询 | 轮询模式驱动：`rte_eth_rx_burst()` 主动收包，取代中断 | ixgbe/i40e/virtio PMD |

### 2.2 mbuf 结构要点

mbuf 是 DPDK 的包载体：一块元数据（struct rte_mbuf）+ 一段数据缓冲。

| 字段 | 说明 | 用途 |
|---|---|---|
| buf_addr / buf_iova | 数据缓冲虚拟/物理地址 | DMA 用物理地址 |
| data_off | 数据起始偏移，初始为 headroom（128B） | 封包时往前 push 以太网/IP 头 |
| data_len / pkt_len | 本段长度 / 整包长度 | 多段（jumbo）时 pkt_len ≥ data_len |
| next / nb_segs | 下一段指针 / 段数 | 分散-聚集支持 |
| refcnt / ol_flags | 引用计数 / 硬件卸载标志 | 共享报文、校验和卸载 |

协议栈实现要点：解析报文用 `rte_pktmbuf_mtod(m, struct eth_hdr *)` 取头指针逐层剥；构造报文用 `rte_pktmbuf_prepend` 在 headroom 前加头。

### 2.3 rte_ring 无锁环形队列

PMD 核 → 协议栈核交接数据靠 rte_ring，不用锁、不用系统调用。

- 本质：容量恒为 2^n 的 void* 数组 + 掩码取模（`idx & mask` 代替 `%`）
- 四个索引：`prod.head/prod.tail` 与 `cons.head/cons.tail`，head 是"抢到位"，tail 是"已完成"
- CAS 原子抢占 slot，多生产者/多消费者安全；源码剖析见 `13-原子操作与无锁组件.md` 第 6 节
- 定位：进程内跨核队列；跨进程用共享内存模式创建

### 2.4 netmap 与 DPDK 对比

| 对比项 | netmap | DPDK |
|---|---|---|
| 数据路径 | 网卡 ring 与用户态共享，包槽零拷贝交换 | PMD 全用户态驱动 + 大页 mempool |
| 生态/库 | 极简，无协议栈无内存池 | mbuf/mempool/ring/timer 全家桶 |
| 适用 | 研究、教学、简单转发 | 生产级高性能转发/网关 |

### 2.5 环境搭建速查

```bash
meson setup build && ninja -C build install && ldconfig   # 1. 编译安装
echo 1024 > /sys/kernel/mm/hugepages/hugepages-2048kB/nr_hugepages   # 2. 大页
mkdir -p /mnt/huge && mount -t hugetlbfs nodev /mnt/huge
usertools/dpdk-devbind.py --bind=igb_uio 0000:03:00.0     # 3. 绑定网卡
testpmd -l 0-3 -n 4 -- -i --portmask=0x3                  # 4. 转发验证
testpmd> set fwd io && start && show port stats all
```

验证：编译成功 → `dpdk-devbind.py -s` 能看到 igb_uio → testpmd 有收发计数。

## 3. 二层协议实现

### 3.1 以太网帧格式

```text
0        6        12       14                60(最小帧长)  1514(常规最大)
+--------+--------+--------+-----------------+
|  dmac  |  smac  |  type  |     payload     |  (+末尾FCS, 硬件已剥离)
+--------+--------+--------+-----------------+
```

```c
// 以太网头：14 字节, 必须 packed 对齐线上格式
struct eth_hdr {
    uint8_t  dmac[6];   // 目的 MAC
    uint8_t  smac[6];   // 源 MAC
    uint16_t type;      // 0x0800 IPv4 / 0x0806 ARP / 0x86DD IPv6（网络字节序）
} __attribute__((packed));
```

type 分发：0x0800 → `ip_input()`，0x0806 → `arp_input()`，0x86DD 为 IPv6（本课程不实现）。

### 3.2 ARP 实现

ARP 头 28 字节：

```c
struct arp_hdr {
    uint16_t hw_type;    // 硬件类型：以太网=1
    uint16_t proto_type; // 上层协议：0x0800
    uint8_t  hw_len;     // 6
    uint8_t  proto_len;  // 4
    uint16_t opcode;     // 1=请求 2=应答
    uint8_t  smac[6];    // 发送方 MAC
    uint32_t sip;        // 发送方 IP
    uint8_t  dmac[6];    // 目标 MAC
    uint32_t dip;        // 目标 IP
} __attribute__((packed));
```

处理流程（状态驱动）：

| 收到的报文 | 条件 | 动作 |
|---|---|---|
| ARP 请求 | opcode=1 且 dip 是本机 IP | 填本机 MAC，opcode 改 2，收发对调，回应答 |
| ARP 应答 | opcode=2 且 sip 是发过请求的 IP | 更新缓存，唤醒等待该 IP-MAC 的发送流程 |
| 无关报文 | dip 非本机 / opcode 未知 | 丢弃 |

ARP 缓存表设计（用户态直接哈希表，替代内核 neighbor 子系统）：

```c
#define ARP_TABLE_SIZE 4096
struct arp_entry {
    uint32_t ip;              // key
    uint8_t  mac[6];
    uint64_t expire_tick;     // 过期时间(参考内核: 老化约 60s)
    struct arp_entry *next;   // 链地址法解决冲突
};
static struct arp_entry *g_arp_table[ARP_TABLE_SIZE];
// 哈希: ip * 2654435761u >> 20 & (SIZE-1)  (Knuth 乘法哈希)
// 未命中 → 发 ARP 请求 + 待发包挂 entry 等待队列, 应答到达后补发
```

### 3.3 ICMP 实现

ping 是协议栈验收第一关：收到 type=8（Echo Request）必须回 type=0（Echo Reply）。

```c
struct icmp_hdr {
    uint8_t  type;       // 8=请求 0=应答 3=不可达...
    uint8_t  code;       // 0
    uint16_t checksum;   // 覆盖整个 ICMP 报文
    uint16_t id;         // ping 进程标识
    uint16_t seq;        // 序号
} __attribute__((packed));

// ICMP echo 处理框架
void icmp_input(struct rte_mbuf *m, struct ip_hdr *iph) {
    struct icmp_hdr *ic = (struct icmp_hdr *)(iph + 1);
    if (icmp_checksum(ic, m->pkt_len - sizeof(*iph)) != 0) return; // 校验失败丢
    if (ic->type != 8) return;                 // 只处理 echo request
    // 应答: 反转收发 IP, type 改 0, 重算校验和
    swap(iph->sip, iph->dip);
    ic->type = 0;
    ic->checksum = 0;
    ic->checksum = icmp_checksum(ic, m->pkt_len - sizeof(*iph));
    ip_output(m, iph->dip);                    // 交三层发送路径(内部查 ARP)
}
```

要点：先验证校验和再处理；源目 IP 对调、type 8→0，id/seq/data 原样保留（ping 才对得上号）；只重算 ICMP 校验和（IP 头校验和由 ip_output 重算）；MAC 由发送路径查 ARP 决定。

## 4. 三层与 UDP

### 4.1 IP 协议

```text
 0        4        8              16      19             31
 +--------+--------+---------------+---------------------+
 | ver(4) | ihl(4) | tos(8)        | tot_len(16)         |   ← 每行32bit
 +--------+--------+---------------+----------+----------+
 | id(16)                | flags(3) | frag_off(13)       |
 +-----------------------+----------+--------------------+
 | ttl(8)  | proto(8)   | checksum(16)                  |
 +---------+------------+-------------------------------+
 | sip(32) / dip(32) / 选项(0~40B, ihl>5 时存在)           |
```

```c
struct ip_hdr {
    uint8_t  version_ihl;  // 高4位版本=4, 低4位头长(单位:4B), 无选项=5
    uint8_t  tos;
    uint16_t tot_len;      // 头+数据总长
    uint16_t id;           // 分片标识
    uint16_t frag_off;     // 标志+片偏移(单位8B)
    uint8_t  ttl;          // 每跳减1, 为0丢弃并回ICMP超时
    uint8_t  proto;        // 1=ICMP 6=TCP 17=UDP
    uint16_t checksum;     // 只覆盖头部的16位反码和
    uint32_t sip, dip;
} __attribute__((packed));
```

IP 头校验和计算（16 位反码和，fold 折叠）：

```c
uint16_t ip_checksum(const uint16_t *buf, int len) {
    uint32_t sum = 0;
    while (len > 1) { sum += *buf++; len -= 2; }
    if (len == 1) sum += *(uint8_t *)buf;      // 奇数字节补零
    while (sum >> 16) sum = (sum & 0xFFFF) + (sum >> 16); // 折叠进位
    return (uint16_t)(~sum);                   // 取反
}
// 验证: 对整个头算一遍结果应为 0
```

选项与分片：选项靠 ihl>5（本课程忽略）；分片在 MTU 以内不触发且网卡有 TSO/GRO，教学栈不支持——收带 MF/offset 的包即丢弃。

### 4.2 UDP 协议

```c
struct udp_hdr {
    uint16_t sport, dport;
    uint16_t len;       // UDP头+数据总长
    uint16_t checksum;  // 可为0(IPv4下"不校验")
} __attribute__((packed));

// 伪头部: 参与校验但不在线传输的"假头", 强制感知 IP 层信息
struct udp_pseudo {
    uint32_t sip, dip;
    uint8_t  zero;
    uint8_t  proto;     // 17
    uint16_t udp_len;
} __attribute__((packed));
```

| 要点 | 说明 |
|---|---|
| 伪头部 | 参与校验但不在线传输，防止 IP 层源目地址被篡改（UDP 无连接保护） |
| 无连接 | 按 (sport, dport) 哈希找 socket，直接塞入接收 ring，无握手无状态 |
| 收发路径 | 发：取数据 → 填 UDP 头 → 算伪头部校验和 → ip_output；收：recv 从 ring 取，空则 EAGAIN（配合 epoll）或阻塞 |

UDP 校验和：以伪头部+UDP 头+数据为区间做 16 位反码和，与 IP 头校验和同一函数、不同区间。

## 5. TCP 实现【核心】

### 5.1 TCP 头格式

```text
 0                    15 16                   31
 +---------------------+----------------------+
 | sport(16)           | dport(16)            |
 +--------------------------------------------+
 | seq(32) 序号: 本段第一个字节的编号            |
 | ack_seq(32) 确认号: 期望对方下一个字节编号       |
 +---------+-----------+----------+-------------+
 | doff(4)|res(4)      | flags(8) | window(16) |
 | checksum(16)        | urg_ptr(16)           |
 +----------------------+----------------------+
 | 选项(0~40B, MSS/窗口缩放/SACK/时间戳)          |
```

```c
struct tcp_hdr {
    uint16_t sport, dport;
    uint32_t seq, ack_seq;
    uint8_t  doff;      // 高4位数据偏移(头长,单位4B)——用位域或位运算取
    uint8_t  flags;     // FIN=0x01 SYN=0x02 RST=0x04 PSH=0x08 ACK=0x10 URG=0x20
    uint16_t window;    // 对方通告的接收窗口
    uint16_t checksum;  // 覆盖伪头部+TCP头+数据
    uint16_t urg_ptr;
} __attribute__((packed));
```

记忆要点：序号以字节为单位，ack = 对方 seq + len（SYN/FIN 各占一序号）；MSS 建连时协商；window 就是滑动窗口；状态机输入全靠 flags。

### 5.2 11 状态与事件驱动状态机

TCP 共 11 个状态：CLOSED、LISTEN、SYN_SENT、SYN_RCVD、ESTABLISHED、FIN_WAIT_1、FIN_WAIT_2、CLOSING、TIME_WAIT、CLOSE_WAIT、LAST_ACK。

事件驱动状态转移表（输入事件 = 报文 flags 归纳 + 本地应用调用）：

| 当前状态 | 输入事件 | 动作 | 新状态 |
|---|---|---|---|
| CLOSED | 应用 connect / listen | 发 SYN / 建监听 | SYN_SENT / LISTEN |
| LISTEN | 收到 SYN / 应用 close | 记录对端回 SYN+ACK / 释放监听 | SYN_RCVD / CLOSED |
| SYN_SENT | 收到 SYN+ACK / SYN（同时打开） | 回 ACK / 回 SYN+ACK | ESTABLISHED / SYN_RCVD |
| SYN_RCVD | 收到 ACK | 连接建立，移入 accept 队列 | ESTABLISHED |
| ESTABLISHED | 应用 close / 收到 FIN | 发 FIN / 回 ACK | FIN_WAIT_1 / CLOSE_WAIT |
| FIN_WAIT_1 | 收到 ACK / FIN+ACK / FIN（同时关闭） | —— / 回 ACK 起 2MSL / 回 ACK | FIN_WAIT_2 / TIME_WAIT / CLOSING |
| FIN_WAIT_2 | 收到 FIN | 回 ACK，启动 2MSL 定时器 | TIME_WAIT |
| CLOSING | 收到 ACK | 启动 2MSL 定时器 | TIME_WAIT |
| TIME_WAIT | 2MSL 超时 | 释放 TCB | CLOSED |
| CLOSE_WAIT | 应用 close | 发 FIN | LAST_ACK |
| LAST_ACK | 收到 ACK | 释放 TCB | CLOSED |

表驱动代码框架：

```c
enum tcp_state {
    TCP_CLOSED, TCP_LISTEN, TCP_SYN_SENT, TCP_SYN_RCVD, TCP_ESTABLISHED,
    TCP_FIN_WAIT_1, TCP_FIN_WAIT_2, TCP_TIME_WAIT, TCP_CLOSE_WAIT,
    TCP_LAST_ACK, TCP_CLOSING,
};
enum tcp_event {
    EV_APP_CONNECT, EV_APP_LISTEN, EV_APP_CLOSE,
    EV_RECV_SYN, EV_RECV_SYNACK, EV_RECV_ACK, EV_RECV_FIN, EV_RECV_FINACK,
    EV_TIMEOUT_2MSL,
};

typedef void (*tcp_action_t)(struct tcp_cb *);
struct state_entry {
    enum tcp_state cur;
    enum tcp_event ev;
    enum tcp_state next;
    tcp_action_t  act;      // 也可把 cur/ev 拼成 [STATE][EVENT] 二维表, 查 O(1)
};

static struct state_entry g_fsm[] = {
    {TCP_CLOSED,     EV_APP_CONNECT, TCP_SYN_SENT,   act_send_syn},
    {TCP_LISTEN,     EV_RECV_SYN,    TCP_SYN_RCVD,   act_send_synack},
    {TCP_SYN_RCVD,   EV_RECV_ACK,    TCP_ESTABLISHED, act_complete_accept},
    {TCP_ESTABLISHED,EV_APP_CLOSE,   TCP_FIN_WAIT_1, act_send_fin},
    {TCP_FIN_WAIT_2, EV_RECV_FIN,    TCP_TIME_WAIT,  act_send_ack_and_start_2msl},
    {TCP_TIME_WAIT,  EV_TIMEOUT_2MSL,TCP_CLOSED,     act_free_tcb},
    /* ...其余条目按上表补全 */
};

void tcp_input(struct tcp_cb *tcb, struct tcp_hdr *hdr) {
    // 1. 验 TCP 校验和(伪头部)
    // 2. 由 flags 归纳事件: SYN&&!ACK→EV_RECV_SYN 等
    enum tcp_event ev = classify_event(hdr);
    // 3. 查表执行: 命中则跑动作并迁移, 无匹配则丢弃或回 RST
    for (unsigned i = 0; i < ARRAY_SIZE(g_fsm); i++) {
        if (g_fsm[i].cur == tcb->state && g_fsm[i].ev == ev) {
            if (g_fsm[i].act) g_fsm[i].act(tcb, hdr);
            tcb->state = g_fsm[i].next;
            return;
        }
    }
}
```

### 5.3 滑动窗口与慢启动实现要点

| 变量 | 含义 | 变化规则 |
|---|---|---|
| snd_una | 最早的未确认序号 | 收到更大的 ack_seq 时右移 |
| snd_nxt | 下一个待发送字节号 | 发送新数据时右移 |
| snd_wnd | 对方通告的接收窗口 | 收到对方报文用其 window 字段更新 |
| cwnd | 拥塞窗口（自己估计的网络容量） | 见慢启动/拥塞避免 |
| ssthresh | 慢启动门限 | 拥塞事件时下调为 cwnd 一半 |
| 有效发送窗口 | min(snd_wnd, cwnd) | snd_nxt - snd_una ≥ 它则暂停发送 |

```c
// 拥塞控制核心（Reno 简化版）
if (cwnd < ssthresh)
    cwnd += acked_bytes;              // 慢启动: 每 RTT 翻倍(指数)
else
    cwnd += mss * mss / cwnd;         // 拥塞避免: 每 RTT +1MSS(线性)
// RTO 超时(最重惩罚): ssthresh=max(cwnd/2,2*MSS), cwnd=1MSS, 回退 snd_nxt=snd_una 重传
// 3 个重复 ACK(快速重传/恢复): ssthresh=cwnd/2, cwnd=ssthresh, 重传 snd_una
```

发送窗口模型：`[已确认 | snd_una..snd_nxt 已发未确认 | 可发（受 min(snd_wnd,cwnd) 限制）]`。

### 5.4 四个定时器【高频】

| 定时器 | 触发条件 | 到期动作 | 典型时长 |
|---|---|---|---|
| 重传定时器 | 存在已发未确认数据 | 重传 snd_una 起的段；RTO 指数退避；cwnd 重置 | 初值约 1s，×2 退避 |
| 坚持定时器 | 对方通告 window=0 | 发 1 字节窗口探测，逼对方重新通告 | 5s 起指数增长，上限 60s |
| TIME_WAIT 定时器 | 主动方进入 TIME_WAIT | 等 2MSL 后释放 TCB | 2MSL≈60s（MSL 30s） |
| keepalive 定时器 | 连接长时间空闲 | 发探测报文，无响应则断连 | 空闲 2h 后每 75s 探测 9 次 |

RTO 计算（RFC 6298）：

```c
// 首次测得 RTT=R:  SRTT=R, RTTVAR=R/2
// 之后每次测得 R':
RTTVAR = (3 * RTTVAR + |SRTT - R'|) / 4;   // beta = 1/4
SRTT   = (7 * SRTT + R') / 8;              // alpha = 1/8
RTO    = SRTT + MAX(G, 4 * RTTVAR);        // G=时钟粒度
// 超时一次: RTO *= 2 (指数退避), 直到上限(如64s)或收到ACK恢复
```

实现：主循环每 tick（10ms）调 `tcp_timer_tick()` 遍历带定时器的连接；工程化按到期时间分桶（时间轮）——选型见 `13-原子操作与无锁组件.md` 第 9 节。

TIME_WAIT 等 2MSL：① 让旧连接重复报文自然死亡；② 最后的 ACK 丢了还能收到对方重传 FIN 并再回 ACK。

## 6. 应用层 POSIX API 实现

### 6.1 用户态 fd 表设计

内核里 fd 是进程文件表下标；用户态自建一张表，`socket()` 返回的"fd"就是这张表的下标，从而骗过应用。

```c
#define MAX_FD 1024
struct user_socket {
    int      fd;               // 本表下标
    int      type;             // SOCK_STREAM / SOCK_DGRAM
    enum tcp_state state;
    uint32_t sip, dip;         // 四元组
    uint16_t sport, dport;
    struct ring      recv_ring;// 接收缓冲(应用从这读)
    struct ring      send_ring;// 发送缓冲(协议栈从这里取)
    struct waitq     wq;       // 阻塞线程 + epoll 回调都挂这
    struct tcp_cb   *tcb;
};
static struct user_socket *g_fd_table[MAX_FD];   // 用户态 fd 表
// alloc_fd: 找空下标(教学版线性扫, 工程上位图)
```

### 6.2 各 API 的语义复刻

| API | 操作的结构 | 用户态语义 |
|---|---|---|
| socket | g_fd_table 空位 | 分配 fd 与 socket 骨架，state=CLOSED |
| bind | 四元组本地半 | 填 sport/sip（IP 归属校验可省） |
| listen | 状态机 + 两个队列 | state→LISTEN；建半连接队列与 accept 队列 |
| accept | accept 队列 | 队列空则阻塞/EAGAIN；否则取已完成连接，分配新 fd |
| connect | 状态机 | CLOSED→SYN_SENT，投递 SYN，等握手完成 |
| recv | recv_ring | 有数据则拷给用户；空则阻塞或 EAGAIN |
| send | send_ring | 写入发送缓冲，唤醒协议栈发送流程；窗口满则阻塞/EAGAIN |
| close | 状态机 | 主动关：发 FIN 走 FIN_WAIT_1；被动侧触发 LAST_ACK |

接口层代码框架：

```c
int socket(int domain, int type, int protocol) {
    if (domain != AF_INET || type != SOCK_STREAM) { errno = EINVAL; return -1; }
    int fd = alloc_fd();
    struct user_socket *sk = calloc(1, sizeof(*sk));
    sk->fd = fd; sk->type = type; sk->state = TCP_CLOSED;
    ring_init(&sk->recv_ring, 4096); ring_init(&sk->send_ring, 4096);
    waitq_init(&sk->wq); g_fd_table[fd] = sk;
    return fd;
}

int accept(int listenfd, struct sockaddr *addr, socklen_t *addrlen) {
    struct user_socket *csk = acceptq_dequeue(g_fd_table[listenfd]); // 取已完成连接
    if (!csk) { errno = EAGAIN; return -1; }        // 非阻塞语义; 阻塞版挂 wq
    fill_addr(addr, addrlen, csk);                  // 回填对端地址
    int fd = alloc_fd();
    csk->fd = fd; g_fd_table[fd] = csk;
    return fd;
}

ssize_t recv(int fd, void *buf, size_t len, int flags) {
    ssize_t n = ring_pop(&g_fd_table[fd]->recv_ring, buf, len); // 从接收环取数据
    if (n == 0) { errno = EAGAIN; return -1; }      // 非阻塞语义
    return n;
}
// send 对称: 写 send_ring, 唤醒协议栈发送流程; 窗口满则 EAGAIN/阻塞
```

握手完成进 accept 队列：SYN_RCVD 收到 ACK 时 `act_complete_accept` 把 TCB 从半连接队列移入 accept 队列，并唤醒挂在 listen fd 上的等待者。

### 6.3 应用无感迁移原理

应用无感迁移两条路：① 编译期同名符号——链接自己的 `socket/connect/...` 实现，链接器优先取之（自家应用）；② 运行期 `LD_PRELOAD=./libustack.so ./app` 预载库覆盖 libc 同名符号（存量应用）。零改造要点：错误码、阻塞语义（EAGAIN/EINTR）、字节序 API 全部与 glibc 对齐。

## 7. 手写 epoll【核心】

### 7.1 要复刻的三接口语义

| 接口 | 内核语义 | 用户态复刻要点 |
|---|---|---|
| epoll_create | 建 eventpoll 对象返回 epfd | 分配 struct eventpoll，登记进 epfd 表 |
| epoll_ctl | 增删改监听项 O(log n) | 红黑树管理监听 fd；ADD 时注册协议栈回调 |
| epoll_wait | 取就绪事件，支持阻塞/超时 | 摘就绪链表拷给用户；空则条件变量等 |

### 7.2 数据结构设计

```c
struct epoll_item {                 // 对应内核 epitem
    int fd;
    uint32_t events;                // 用户关注的事件(EPOLLIN等)
    epoll_data_t data;              // 用户注册的 data, 完成时原样回传
    struct user_socket *sk;
    struct rb_node rb_node;         // 挂红黑树(按fd)
    struct list_head ready_link;    // 挂就绪链表
    struct eventpoll *ep;           // 反向指针
};

struct eventpoll {                  // 对应内核 eventpoll
    struct rb_root rbt;             // 监听集合: 增删改查 O(log n)
    struct list_head rdllist;       // 就绪链表: wait 摘取 O(1)
    pthread_mutex_t lock;           // 保护 rbt + rdllist
    pthread_cond_t  cond;           // epoll_wait 的休眠点
};
```

为什么红黑树 + 就绪链表【高频】：注册项可能百万级（树：log n 增删改）；就绪的只是少数（链表：摘取 O(就绪数)）。epoll 高效的本质是"回调驱动就绪链表"——不遍历所有 fd，数据到达时被动登记。红黑树手撕见 `02-算法手撕与手写实现.md`。

### 7.3 线程安全实现

| 路径 | 保护方式 |
|---|---|
| epoll_ctl 与协议栈回调并发操作 rdllist/rbt | 同一把互斥锁（临界区极短，可换自旋锁） |
| epoll_wait 与生产者并发 | 摘链表前持锁，拷贝到用户数组后放锁 |
| 多线程同时 wait 同一 epfd | 内核允许多 waiter；cond 广播 + 各自摘一段 |

### 7.4 协议栈 fd 就绪回调

这是 epoll 的灵魂：协议栈收到数据 → 调用注册的回调 → 入就绪链表 → 唤醒 wait。

```c
// epoll_ctl ADD 时: 把回调挂到 socket 的等待队列
int epoll_ctl(int epfd, int op, int fd, struct epoll_event *ev) {
    struct eventpoll *ep = epfd_lookup(epfd);
    pthread_mutex_lock(&ep->lock);
    if (op == EPOLL_CTL_ADD) {
        struct epoll_item *it = calloc(1, sizeof(*it));
        it->fd = fd; it->events = ev->events; it->data = ev->data; it->ep = ep;
        it->sk = g_fd_table[fd];
        rb_insert(&ep->rbt, it);                  // 红黑树插入 O(log n)
        sock_register_cb(it->sk, ep_poll_callback, it); // 关键: 注册就绪回调
    } else if (op == EPOLL_CTL_DEL) {          // 先摘就绪链(可能在链上)再删
        struct epoll_item *it = rb_find(&ep->rbt, fd);
        sock_unregister_cb(it->sk); list_del_init(&it->ready_link);
        rb_erase(&ep->rbt, it); free(it);
    } /* MOD: 改 events */
    pthread_mutex_unlock(&ep->lock);
    return 0;
}

// 协议栈收到数据后(在 recv_ring 入队处)调用
void ep_poll_callback(struct epoll_item *it) {
    struct eventpoll *ep = it->ep;
    pthread_mutex_lock(&ep->lock);
    if (list_empty(&it->ready_link)) {            // 防重复入队
        list_add_tail(&it->ready_link, &ep->rdllist);
        pthread_cond_broadcast(&ep->cond);        // 唤醒 epoll_wait
    }
    pthread_mutex_unlock(&ep->lock);
}
```

### 7.5 epoll_wait 语义

```c
int epoll_wait(int epfd, struct epoll_event *events, int maxevents, int timeout) {
    struct eventpoll *ep = epfd_lookup(epfd);
    pthread_mutex_lock(&ep->lock);
    for (;;) {
        int n = 0;                              // 1. 摘就绪节点拷给用户
        while (!list_empty(&ep->rdllist) && n < maxevents) {
            struct epoll_item *it = list_first_entry(&ep->rdllist, ...);
            list_del_init(&it->ready_link);
            events[n].events = compute_ready(it->sk);   // 由缓冲状态算就绪事件
            events[n].data = it->data;                   // 用户注册的 data 原样回传
            n++;
            if (!(it->events & EPOLLET) && has_remaining_data(it->sk))
                list_add_tail(&it->ready_link, &ep->rdllist); // LT: 还有数据就放回
            // ET: 不放回, 只等下一次"数据从无到有"的回调
        }
        if (n > 0) { pthread_mutex_unlock(&ep->lock); return n; }
        if (timeout == 0) { pthread_mutex_unlock(&ep->lock); return 0; } // 2. 空: 按策略
        int r = (timeout < 0)
              ? pthread_cond_wait(&ep->cond, &ep->lock)             // 无限等
              : pthread_cond_timedwait(&ep->cond, &ep->lock, &ts);  // 限时
        if (r == ETIMEDOUT) { pthread_mutex_unlock(&ep->lock); return 0; }
    }
}
```

### 7.6 LT / ET 语义实现要点【高频】

| 模式 | 通知时机 | 用户处理约定 | 实现差异 |
|---|---|---|---|
| LT 水平触发 | 只要有未读数据每次 wait 都报 | 一次不必读完 | 摘下后"仍有数据"则放回 rdllist |
| ET 边沿触发 | 仅数据从无到有报一次 | 必须循环读到 EAGAIN | 回调只在"ring 从空变非空"时触发；摘走不放回 |

ET 的回调细节：`ep_poll_callback` 里判断 `ring_empty_before && !ring_empty_now` 才入就绪链——这就是"边沿"；LT 则无条件入队。ET 减少重复回调，但必须配非阻塞 fd，否则最后那次"读到没数据"的 read 会永久阻塞。

## 8. 开源参考

| 项目 | 定位 | 特点 |
|---|---|---|
| NtyTcp | 课程同款教学栈 | 单线程参考实现，代码量小，含 epoll/POSIX API 复刻，最适合入门 |
| f-stack | 腾讯生产级 | DPDK + FreeBSD 内核栈移植，Nginx/Redis 适配版 |
| mTCP / VPP | 学术 / 思科 | 每线程独立栈 / 矢量处理+插件图节点 |

## 9. 快速参考卡片

| 要点 | 一句话 |
|---|---|
| 内核四大开销 | syscall 切换 / 硬中断 / 通用栈不可裁剪 / 内核用户拷贝 |
| DPDK 五板斧 | UIO/VFIO + 大页 + 绑核 + rte_ring + PMD 轮询 |
| 校验和 | IP 只覆盖头；UDP/TCP 覆盖伪头部+头+数据 |
| TCP 11 状态 | 表驱动：当前状态 × 输入事件 → 动作 + 新状态 |
| RTO 公式 | SRTT + max(G, 4×RTTVAR)；超时退避 ×2 |
| 四定时器 | 重传 / 坚持(零窗口探测) / TIME_WAIT(2MSL) / keepalive |
| 有效窗口 | min(snd_wnd, cwnd)；cwnd < ssthresh 走慢启动 |
| epoll 双结构 | 红黑树管注册 + 就绪链表管触发，回调驱动 |
| LT/ET | LT 看存量（有数据就报），ET 看增量（从无到有报一次） |

## 10. 常见问题与坑

| 坑 | 现象 | 正解 |
|---|---|---|
| 结构体没加 packed | 头解析错位，dmac 读出乱值 | 线上格式结构体一律 `__attribute__((packed))` |
| 字节序忘转换 | 端口号/长度莫名巨大 | 16/32 位字段统一走 ntohs/ntohl |
| ARP 未命中直接丢包 | 首包必丢，ping 不通 | 待发包挂 pending 队列，应答到达后补发 |
| SYN 没占序号 | 三次握手后 seq 对不齐 | SYN/FIN 各占一个序号：ack = seq + len + (SYN\|FIN ? 1 : 0) |
| TIME_WAIT 只等 1 个 MSL / 零窗口不探测 | 旧 FIN 被当新数据 / 连接假死 | 等 2MSL（1 去 1 回）/ 坚持定时器发 1 字节探测 |
| epoll 回调没防重复入队 | 同一 fd 重复上报 | 入队前判 `list_empty(&ready_link)` |
| ET 模式用阻塞 fd | 读到没数据时永久卡死 | ET 必须配非阻塞 fd + 循环读到 EAGAIN |
| EPOLL_CTL_DEL 忘摘就绪链 | use-after-free | DEL 先 `list_del_init` 再 free |
| 用户态 fd 与系统 fd 混用 | 传给真 read() 崩溃 | fd 表隔离，或编译期隔离命名空间 |
| PMD 让出 CPU / 忽略 mbuf 释放 | 吞吐骤降丢包 / mempool 耗尽 | 收包核绑核不 sleep / 所有路径（含丢弃）都 `rte_pktmbuf_free` |

---

上一篇：《02-io_uring与异步IO.md》
下一篇：《04-内存池与池化技术.md》
