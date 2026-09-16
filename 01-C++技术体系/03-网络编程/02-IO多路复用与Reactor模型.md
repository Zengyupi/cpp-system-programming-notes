# IO 多路复用与 Reactor 模型

> 本节目标：本篇只讲一条主线——**select → poll → epoll（重点）→ Reactor**，把"一个线程如何同时看管成千上万条连接"讲透。线程/锁/线程池见《../04-并发编程/01-线程基础与生命周期.md》；百万连接内核调优、握手挥手内核视角见《../12-网络与服务器架构/02-百万并发与TCP栈优化.md》；Reactor 的工程化网络库、HTTP 解析、协程见《../12-网络与服务器架构/04-Reactor与高性能网络库.md》《../13-并发异步与组件/01-协程框架原理与实现.md》；下一代异步 I/O（io_uring/IOCP）见《../13-并发异步与组件/02-io_uring与异步IO.md》。示例基于 Linux，标注了可移植性差异。

## 本章速览

- [1. 背景：从阻塞 I/O 到多路复用](#1-背景从阻塞-io-到多路复用)
  - [1.1 先把概念分清：阻塞/非阻塞 × 同步/异步](#11-先把概念分清阻塞非阻塞--同步异步)
  - [1.2 为什么必须多路复用：C10K](#12-为什么必须多路复用c10k)
  - [1.3 一条演进主线](#13-一条演进主线)
  - [1.4 统一前置：非阻塞 fd 与 EAGAIN](#14-统一前置非阻塞-fd-与-eagain)
- [2. select](#2-select)
  - [2.1 原型与参数](#21-原型与参数)
  - [2.2 fd_set 位图原理](#22-fd_set-位图原理)
  - [2.3 完整可编译示例：select 版 echo server](#23-完整可编译示例select-版-echo-server)
  - [2.4 内核里发生了什么](#24-内核里发生了什么)
  - [2.5 select 的四个硬伤](#25-select-的四个硬伤)
- [3. poll](#3-poll)
  - [3.1 原型与 pollfd](#31-原型与-pollfd)
  - [3.2 完整示例（只看与 select 的差异）](#32-完整示例只看与-select-的差异)
  - [3.3 改进了什么、仍没解决什么](#33-改进了什么仍没解决什么)
- [4. epoll 深度剖析（重点）](#4-epoll-深度剖析重点)
  - [4.1 三个核心 API](#41-三个核心-api)
  - [4.2 事件标志全表](#42-事件标志全表)
  - [4.3 内核数据结构全景](#43-内核数据结构全景)
  - [4.4 一次事件到达的完整链路【高频】](#44-一次事件到达的完整链路高频)
  - [4.5 epoll_ctl / epoll_wait 内部在做什么](#45-epoll_ctl--epoll_wait-内部在做什么)
  - [4.6 LT vs ET【高频必考】](#46-lt-vs-et高频必考)
  - [4.7 惊群、EPOLLONESHOT、EPOLLEXCLUSIVE、SO_REUSEPORT](#47-惊群epolloneshotepollexclusiveso_reuseport)
  - [4.8 常见认知误区](#48-常见认知误区)
  - [4.9 生产级实战：LT echo server（含按需 EPOLLOUT 与发送缓冲）](#49-生产级实战lt-echo-server含按需-epollout-与发送缓冲)
- [5. select / poll / epoll 横向对比](#5-select--poll--epoll-横向对比)
  - [5.1 总表](#51-总表)
  - [5.2 跨平台与下一代](#52-跨平台与下一代)
- [6. Reactor 模式](#6-reactor-模式)
  - [6.1 定义与经典角色](#61-定义与经典角色)
  - [6.2 Reactor vs Proactor【高频辨析】](#62-reactor-vs-proactor高频辨析)
  - [6.3 三种线程模型【高频】](#63-三种线程模型高频)
  - [6.4 one loop per thread 与跨线程唤醒](#64-one-loop-per-thread-与跨线程唤醒)
  - [6.5 手撕精简 Reactor（可编译核心）](#65-手撕精简-reactor可编译核心)
  - [6.6 Reactor 编程铁律](#66-reactor-编程铁律)
  - [6.7 定时器如何接入 Reactor](#67-定时器如何接入-reactor)
  - [6.8 业界实现对照](#68-业界实现对照)
- [7. 快速参考卡片](#7-快速参考卡片)
- [8. 常见问题与坑](#8-常见问题与坑)

---

## 1. 背景：从阻塞 I/O 到多路复用

### 1.1 先把概念分清：阻塞/非阻塞 × 同步/异步

一次读操作在内核里分**两个阶段**，所有 I/O 模型的差异都在这两阶段上：

```text
阶段① 等待数据就绪（wait for data）：网卡数据到达 → 拷贝到内核 socket 接收缓冲区
阶段② 数据拷贝（copy data）：内核缓冲区 → 用户缓冲区（recv 的最后一步）
```

| 模型 | 阶段① 等待就绪 | 阶段② 拷贝 | 谁来做 read/write |
| --- | --- | --- | --- |
| 阻塞 I/O | 线程睡死 | 阻塞 | 用户线程 |
| 非阻塞 I/O | 立即返回 EAGAIN | 阻塞（瞬间） | 用户线程轮询 |
| **I/O 多路复用** | 睡在 select/poll/epoll 上，一批 fd 一起等 | 阻塞（瞬间） | 用户线程 |
| 信号驱动 I/O | 内核发 SIGIO 通知 | 阻塞（瞬间） | 用户线程 |
| 异步 I/O（AIO/io_uring） | 不等待 | **内核连拷贝一起做完再回调** | 内核 |

- **阻塞 vs 非阻塞**：阶段① 会不会把线程挂起。
- **同步 vs 异步**：阶段② 数据拷贝由谁完成。前四种都是"内核告诉你就绪、你自己 recv 拷贝"，属**同步 I/O**；只有异步 I/O 连拷贝都由内核完成，才是真正的**异步**。
- 多路复用本身**不会让单个 recv 变快**，它解决的是"一个线程同时等很多 fd，谁好了处理谁"。

### 1.2 为什么必须多路复用：C10K

thread-per-connection（每连接一线程）在万级连接下的成本是可量化的：

```text
1 万连接 × 每线程默认 8MB 栈（虚拟）= 80GB 虚拟地址空间
+ 线程调度/上下文切换（每次切换 μs 级，且刷 L1/L2 cache）
→ 线程数必须与连接数解耦：用少量线程 + 多路复用看管海量 fd
```

### 1.3 一条演进主线

```text
每连接一线程
   → select  ：能一次等多个 fd，但有 1024 上限、每次全量拷贝扫描
   → poll    ：去掉上限、输入输出分离，但仍每次全量拷贝扫描
   → epoll   ：注册一次 + 回调驱动，等待成本只与"就绪数"有关
   → Reactor ：把 epoll 封装成"事件循环 + 回调分发"的编程模型
   → Proactor/协程：内核做完 I/O 再通知（io_uring/IOCP），或用协程把回调写回同步风格
```

三者本质差异一句话：**select/poll 是"我每次把全部 fd 交给内核，你帮我查谁就绪"；epoll 是"我注册一次，谁有事件内核主动上报"**。

### 1.4 统一前置：非阻塞 fd 与 EAGAIN

后面所有高性能写法都建立在非阻塞 fd 上，先统一讲一次：

```cpp
#include <fcntl.h>
int set_nonblock(int fd) {
    int fl = fcntl(fd, F_GETFL, 0);
    return fcntl(fd, F_SETFL, fl | O_NONBLOCK);
}
```

非阻塞 `recv/send/accept` 在"暂时无事可做"时**不睡眠**，而是返回 -1 且 `errno=EAGAIN`（等价 `EWOULDBLOCK`）。这是非阻塞 I/O 的**正常状态**，不是错误：

| 返回 | 含义 | 处理 |
| --- | --- | --- |
| `> 0` | 实际读/写了 n 字节（可能少于请求值） | send 循环补发；recv 按实际长度处理 |
| `== 0` | **仅 recv**：对端发了 FIN，正常关闭 | 关闭连接 |
| `-1 / EAGAIN` | 非阻塞下暂时没数据/写缓冲满 | 本次结束，等下一次事件 |
| `-1 / EINTR` | 被信号打断 | 重试 |
| `-1 / 其他` | 真错误（ECONNRESET 等） | 关闭连接 |

---

## 2. select

### 2.1 原型与参数

```cpp
#include <sys/select.h>
#include <sys/time.h>

int select(int nfds,                    // 监视的【最大 fd 值 + 1】，不是 fd 个数！
           fd_set *readfds,            // 关心可读的 fd 集合（可传 NULL）
           fd_set *writefds,           // 关心可写
           fd_set *exceptfds,          // 关心异常（带外数据，几乎不用）
           struct timeval *timeout);   // NULL=永久阻塞；{0,0}=立即返回(轮询)；正数=超时
// 返回：就绪 fd 总数；0=超时；-1=出错(看 errno，EINTR 重试)
```

**为什么 nfds 是"最大 fd+1"**：内核从 0 开始线性检查位图，需要知道检查到第几号为止，所以传上界（最大 fd+1）而不是数量，能少扫无用位。

### 2.2 fd_set 位图原理

`fd_set` 本质是一个**位图（bitmask）**，每一位对应一个 fd：

```cpp
// glibc 内部（简化）：long 数组拼出一张位图
#define FD_SETSIZE  1024                       // 位图总位数，编译期写死
#define __NFDBITS   (8 * sizeof(long))         // 每个 long 管 64 位
// fd=37 → 第 37/64 个 long 的第 37%64 位
void FD_SET(int fd, fd_set *p) { p->fds_bits[fd/__NFDBITS] |=  (1UL << (fd%__NFDBITS)); }
void FD_CLR(int fd, fd_set *p) { p->fds_bits[fd/__NFDBITS] &= ~(1UL << (fd%__NFDBITS)); }
int  FD_ISSET(int fd, fd_set *p){ return p->fds_bits[fd/__NFDBITS] &   (1UL << (fd%__NFDBITS)); }
void FD_ZERO(fd_set *p)        { memset(p, 0, sizeof(*p)); }
```

### 2.3 完整可编译示例：select 版 echo server

```cpp
// select_echo.cpp —— 编译：g++ -std=c++17 -O2 select_echo.cpp -o select_echo
#include <arpa/inet.h>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <netinet/in.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <unistd.h>
#include <algorithm>
#include <vector>

int main() {
    int lfd = socket(AF_INET, SOCK_STREAM, 0);
    int on = 1;
    setsockopt(lfd, SOL_SOCKET, SO_REUSEADDR, &on, sizeof(on));
    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(8888);
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    bind(lfd, (sockaddr*)&addr, sizeof(addr));
    listen(lfd, 512);

    std::vector<int> clients;                 // 自己维护所有连接 fd
    for (;;) {
        fd_set rset;
        FD_ZERO(&rset);                       // ★ 每次循环必须重建
        FD_SET(lfd, &rset);
        int maxfd = lfd;
        for (int fd : clients) { FD_SET(fd, &rset); maxfd = std::max(maxfd, fd); }

        int n = select(maxfd + 1, &rset, nullptr, nullptr, nullptr);
        if (n < 0) { if (errno == EINTR) continue; perror("select"); break; }

        if (FD_ISSET(lfd, &rset)) {           // 新连接
            int cfd = accept(lfd, nullptr, nullptr);
            clients.push_back(cfd);
        }
        for (auto it = clients.begin(); it != clients.end(); ) {
            int fd = *it;
            if (FD_ISSET(fd, &rset)) {        // ★ select 不告诉你谁就绪，要自己逐个问
                char buf[4096];
                ssize_t r = recv(fd, buf, sizeof(buf), 0);
                if (r <= 0) { close(fd); it = clients.erase(it); continue; }
                send(fd, buf, r, MSG_NOSIGNAL);   // 简化：读后直接回写
            }
            ++it;
        }
    }
}
```

### 2.4 内核里发生了什么

```text
sys_select → do_select：
  第一轮：从 0 扫到 nfds-1，对每个 fd 调用其文件的 poll 方法（socket 即 sock_poll）查就绪掩码
        → 若有就绪，直接返回
        → 若一个都没有，把当前进程挂到【每个被监视 fd】的等待队列上，schedule() 睡眠
  某 fd 就绪 → 唤醒进程 → 第二轮再全量扫一遍收集结果 → 把结果位图拷回用户态
```

注意"**至少扫两遍 + 在每个 fd 上都挂等待项**"：这是 select 开销随 fd 数线性增长的根源。

### 2.5 select 的四个硬伤

| 硬伤 | 细节 |
| --- | --- |
| **fd 上限 1024** | `FD_SETSIZE` 编译期固定，改它要重编译 libc/程序，不可用于万级连接 |
| **每次全量拷贝** | 三张位图每次都从用户态拷进内核、结果再拷回 |
| **O(n) 扫描** | 内核线性扫，返回后用户还要 `FD_ISSET` 再线性遍历一遍找就绪者 |
| **集合被改写** | 返回后位图只剩就绪 fd，**下次必须 FD_ZERO + FD_SET 重建**，无法增量维护 |

适用：fd 很少（几十个以内）、需要跨平台（Windows/macOS/BSD 都支持）的简单场景。

---

## 3. poll

### 3.1 原型与 pollfd

```cpp
#include <poll.h>

struct pollfd {
    int   fd;        // 要监视的 fd；设为负数表示忽略该条目（revents 恒为 0）
    short events;    // 【输入】关注的事件位掩码
    short revents;   // 【输出】实际发生的事件，由内核填写
};

int poll(struct pollfd *fds, nfds_t nfds, int timeout_ms);
// 返回就绪条目数；0=超时；-1=出错(EINTR 重试)
```

常用事件位：`POLLIN`（可读）、`POLLOUT`（可写）、`POLLERR`（错误，仅 revents）、`POLLHUP`（挂断，仅 revents）、`POLLNVAL`（fd 未打开，仅 revents）。

### 3.2 完整示例（只看与 select 的差异）

```cpp
// poll_echo.cpp 核心循环 —— 编译：g++ -std=c++17 poll_echo.cpp -o poll_echo
struct pollfd fds[1024];
fds[0].fd = lfd; fds[0].events = POLLIN;
nfds_t nfds = 1;
for (;;) {
    int n = poll(fds, nfds, -1);                        // 不用每次重建数组
    if (n < 0 && errno == EINTR) continue;
    for (nfds_t i = 0; i < nfds; ++i) {
        if (fds[i].revents & POLLIN) {
            if (fds[i].fd == lfd) {                     // 新连接：追加到数组
                int cfd = accept(lfd, nullptr, nullptr);
                fds[nfds++] = {cfd, POLLIN, 0};
            } else {                                    // 读数据
                char buf[4096];
                ssize_t r = recv(fds[i].fd, buf, sizeof(buf), 0);
                if (r <= 0) { close(fds[i].fd); fds[i] = fds[--nfds]; --i; }  // 用末尾元素补洞
                else send(fds[i].fd, buf, r, MSG_NOSIGNAL);
            }
        }
    }
}
```

### 3.3 改进了什么、仍没解决什么

| 相比 select 的改进 | 仍未解决的根本问题 |
| --- | --- |
| **无 fd 上限**：pollfd 是动态数组，只受内存限制 | **每次仍要把整个数组拷进内核** |
| **events/revents 分离**：输入不被改写，无需重建集合 | **内核仍线性遍历全部条目**，O(n) |
| 事件类型更丰富（POLLERR/POLLNVAL 分离） | 返回后用户仍要遍历全部条目找就绪者 |
| 负数 fd 可作空槽，便于复用数组位置 | 每次仍要在每个 fd 上挂/摘等待项 |

内核实现 `do_poll` 与 `do_select` 几乎同源（都调用每个文件的 `poll` 方法、睡前睡后各扫一遍），所以 **poll 只是"去掉 1024 上限的 select"，算法复杂度没变**。适合几千 fd 的中小规模。

---

## 4. epoll 深度剖析（重点）

epoll 是 Linux 专属（2.6+）的事件通知机制：BSD/macOS 对应 **kqueue**，Windows 对应 **IOCP**。核心突破是**"注册"与"等待"分离**——fd 与关注事件通过 `epoll_ctl` 一次性注册进内核长期持有，`epoll_wait` 只取已经就绪的结果。

### 4.1 三个核心 API

```cpp
#include <sys/epoll.h>

int epoll_create1(int flags);
// 创建 epoll 实例，返回一个 fd（用完要 close）。flags：0 或 EPOLL_CLOEXEC(exec 时自动关闭)

int epoll_ctl(int epfd, int op, int fd, struct epoll_event *ev);
// 增删改监视关系。op：EPOLL_CTL_ADD / MOD / DEL，成功 0，失败 -1

int epoll_wait(int epfd, struct epoll_event *events, int maxevents, int timeout_ms);
// 阻塞等待，把【就绪事件】写入 events 数组，返回就绪个数（≤maxevents）；0 超时，-1 出错

union epoll_data { int fd; void *ptr; uint32_t u32; uint64_t u64; };
struct epoll_event {
    uint32_t     events;   // 事件位：EPOLLIN/EPOLLOUT/...（见 4.2）
    epoll_data_t data;     // 联合体：原样带回，常用 data.fd 或 data.ptr(指向连接/Channel 对象)
};
```

```cpp
// 固定三步：create → ctl 注册 → wait 取结果
int epfd = epoll_create1(EPOLL_CLOEXEC);
epoll_event ev{ EPOLLIN, { .fd = lfd } };     // C++ 聚合初始化；也可 ev.data.ptr = &channel
epoll_ctl(epfd, EPOLL_CTL_ADD, lfd, &ev);

epoll_event evs[1024];
for (;;) {
    int n = epoll_wait(epfd, evs, 1024, -1);  // 只返回就绪的 n 个
    for (int i = 0; i < n; ++i) { /* evs[i] 一定就绪，无需再问 */ }
}
```

### 4.2 事件标志全表

| 标志 | 方向 | 含义 |
| --- | --- | --- |
| `EPOLLIN` | 输入 | 可读（含对端 FIN 到达，此时 recv 返回 0） |
| `EPOLLOUT` | 输入 | 可写（发送缓冲区有空闲）。**必须按需注册**，见 4.9 |
| `EPOLLRDHUP` | 输入 | 对端关闭/半关闭（收到 FIN），Linux 2.6.17+，比 EPOLLHUP 更细 |
| `EPOLLPRI` | 输入 | 带外数据/紧急数据 |
| `EPOLLERR` | 输出 | 错误，wait **总会上报**，无需注册，处理时优先判断 |
| `EPOLLHUP` | 输出 | 挂断（双向都断），通常直接关连接 |
| `EPOLLET` | 输入 | 切到边沿触发（默认水平触发），见 4.6 |
| `EPOLLONESHOT` | 输入 | 事件只触发一次，触发后自动屏蔽，需 MOD 重新武装，见 4.7 |
| `EPOLLEXCLUSIVE` | 输入 | 惊群时只唤醒一个等待者，见 4.7 |

> 常见组合：监听 fd 注册 `EPOLLIN`；已连接 fd 注册 `EPOLLIN | EPOLLRDHUP`。

### 4.3 内核数据结构全景

`epoll_create1` 在内核分配一个 `struct eventpoll`，它是整套机制的中枢：

```cpp
struct eventpoll {
    struct rb_root_cached  rbr;       // 红黑树：所有【已注册】的 fd，节点是 epitem（键=file指针+fd）
    struct list_head       rdllist;   // 就绪链表：当前【已就绪】的 epitem
    struct wait_queue_head wq;        // 等待队列：epoll_wait 没事件时在此睡眠
    struct mutex           mtx;       // 保护上述结构
};
struct epitem {                        // 一个被监视 fd 的内核对象
    struct rb_node  rbn;              // 挂在红黑树上
    struct list_head rdllink;         // 就绪时挂进 rdllist
    struct epoll_filefd ffd;          // 指向被监视的 struct file + fd
    struct eventpoll *ep;
    struct list_head pwqlist;         // 挂到被监视 socket 等待队列上的入口
};
```

```text
注册关系（长期）：  红黑树 rbr  ← epoll_ctl ADD/MOD/DEL，增删 O(log n)、自动去重
就绪结果（瞬时）：  就绪链表 rdllist ← 数据到达时由回调挂入，epoll_wait 只摘这条链
睡眠/唤醒：        wq（epoll_wait 睡这）+ 每个 socket 自己的等待队列（回调挂这）
```

### 4.4 一次事件到达的完整链路【高频】

```text
① epoll_ctl(ADD) 时：epitem 插入红黑树，并通过 eppoll_entry 在【被监视 socket 的等待队列】
                     上注册一个回调 ep_poll_callback
② 网卡收包 → DMA → 硬中断 → 软中断(NAPI) → 协议栈(TCP) → 数据放进 socket 接收缓冲区
③ socket 状态变为可读 → 唤醒它等待队列上的所有项 → 调用 ep_poll_callback
④ ep_poll_callback：把对应 epitem 挂入 eventpoll.rdllist（已在链上则不重复挂）
⑤ 唤醒睡在 eventpoll.wq 上的 epoll_wait
⑥ epoll_wait 调 ep_send_events 遍历 rdllist，把就绪事件【只拷就绪的】到用户 events 数组
```

对比 select"每次把全部 fd 推进内核逐个查"，epoll 是"**注册一次，数据到了由回调主动推进就绪链表**"——这就是等待成本与总连接数无关、只与就绪数有关的根本原因。

### 4.5 epoll_ctl / epoll_wait 内部在做什么

| 调用 | 内核动作 | 复杂度 |
| --- | --- | --- |
| `epoll_ctl ADD` | 分配 epitem、插入红黑树、在 file 等待队列挂回调 | O(log n) |
| `epoll_ctl MOD` | 在红黑树找到 epitem，改关注事件 | O(log n) |
| `epoll_ctl DEL` | 从红黑树摘除、从 file 等待队列撤回调 | O(log n) |
| `epoll_wait` | rdllist 空则睡在 wq；非空则 `ep_send_events` 遍历就绪链拷给用户 | **O(就绪数)** |

> 注意：`epoll_ctl` 本身是一次系统调用，频繁 ADD/DEL 也有成本——所以连接建立后应长期注册、用 MOD 切换关注事件，而不是反复增删。

### 4.6 LT vs ET【高频必考】

| 维度 | LT 水平触发（默认） | ET 边沿触发 |
| --- | --- | --- |
| 触发条件 | 只要缓冲区**仍满足条件**（还有数据/还可写），每次 wait 都上报 | 仅在状态**发生跳变**（无→有新数据到达）那一刻上报一次 |
| 内核行为 | `ep_send_events` 后若 fd 仍就绪，把 epitem **重新放回** rdllist | 上报后**不放回**，直到下一次新的状态变化再次触发回调 |
| 读法 | 读多少随意，没读完下次还会通知 | **必须循环读到 EAGAIN**，否则剩余数据要等下一批新数据才通知（连接"假死"） |
| fd 要求 | 阻塞/非阻塞均可（推荐非阻塞） | **必须非阻塞**，否则"读到 EAGAIN"的最后一次 recv 会把线程睡死 |
| 事件次数 | 多（持续提醒） | 少（只提醒跳变），高吞吐场景系统调用/唤醒更少 |
| 编程容错 | 好，漏读也能自愈 | 差，漏读即卡死，对正确性要求极高 |

```cpp
// ET 模式读一个 fd 的标准写法：非阻塞 + 循环读到 EAGAIN
set_nonblock(fd);
uint32_t ev = EPOLLIN | EPOLLET | EPOLLRDHUP;     // ET 必配非阻塞
for (;;) {
    char buf[4096];
    ssize_t r = recv(fd, buf, sizeof(buf), 0);
    if (r > 0) { /* 处理/追加到接收缓冲 */ continue; }
    if (r == 0) { /* 对端关闭 */ close(fd); break; }
    if (errno == EINTR) continue;
    if (errno == EAGAIN) break;                   // ★ 读干净了，ET 下必须等到这里才能退出
    close(fd); break;                             // 其他错误
}
```

**listenfd 的 ET 陷阱**：若监听 socket 用 `EPOLLET`，一次可读事件代表"全连接队列来了一批新连接"，必须 `while(accept() > 0)` 循环取到 `EAGAIN`，否则剩余连接要等下一个新连接才被唤醒。LT 模式下取一个也能被再次提醒，但生产中同样建议一次取完。

### 4.7 惊群、EPOLLONESHOT、EPOLLEXCLUSIVE、SO_REUSEPORT

**惊群（thundering herd）**：多个进程/线程同时 `epoll_wait` 同一个 listenfd，一个新连接到达会唤醒**全部**等待者，最终只有一个 accept 成功，其余空跑浪费 CPU。

| 方案 | 机制 | 适用 |
| --- | --- | --- |
| 单点 accept | 只有一个线程/进程负责 accept，再把连接分发给 worker | 主从 Reactor（muduo/Netty） |
| `SO_REUSEPORT` | 每个 worker 各自 bind/listen 同一端口，内核为每个 socket 维护**独立连接队列**并做负载均衡 | nginx 多 worker |
| `EPOLLEXCLUSIVE` | 唤醒时只唤醒等待队列中的**一个**等待者（Linux 4.5+） | 多 worker 共享 listenfd |

**EPOLLONESHOT**：注册了它的 fd，一次事件上报后**自动屏蔽**（不再上报任何事件），直到你 `EPOLL_CTL_MOD` 重新武装。用途：多个线程共享一个 epfd 时，保证**同一连接的事件一次只被一个线程处理**，处理完再 MOD 放回去，实现连接级串行。muduo 用"one loop per thread（一个连接只属于一个 loop）"从结构上规避竞争，ONESHOT 是单 epfd 多线程方案的补丁。

### 4.8 常见认知误区

| 误区 | 正解 |
| --- | --- |
| "epoll 任何场景都比 select 快" | epoll 赢在**海量连接、少量活跃**。若 fd 很少（<几十）或所有 fd 每次都活跃，select/poll 的线性扫描并不慢，还省了 epoll_ctl 的系统调用开销 |
| "epoll 是异步 I/O" | epoll 仍是**同步** I/O：它只通知"就绪了"，recv/send 的数据拷贝仍由用户线程做。真异步是 io_uring/IOCP |
| "ET 一定比 LT 快" | ET 只减少事件次数，代价是必须非阻塞+读到 EAGAIN，写错就假死。没有正确压测数据前默认用 LT |
| "注册了 EPOLLOUT 就等可写事件" | socket 发送缓冲区**大多数时候都是空的（可写）**，常开 EPOLLOUT 会让 epoll_wait 立刻返回形成忙轮询、CPU 100%。必须"有数据待发才注册，发完立即注销" |
| "epoll_wait 返回的事件还要再判断一次就绪" | 不需要，返回数组里的就是就绪事件；要判断的是**事件类型**（IN/OUT/RDHUP/ERR） |

### 4.9 生产级实战：LT echo server（含按需 EPOLLOUT 与发送缓冲）

这个版本修正了"send 一次写不完"的真实问题：写不完的数据进发送缓冲并注册 EPOLLOUT，可写时继续发，发完注销。

```cpp
// epoll_echo.cpp —— 编译：g++ -std=c++17 -O2 epoll_echo.cpp -o epoll_echo
// 测试：./epoll_echo 后另开终端 nc 127.0.0.1 8888
#include <arpa/inet.h>
#include <cerrno>
#include <cstdio>
#include <fcntl.h>
#include <netinet/in.h>
#include <string>
#include <sys/epoll.h>
#include <sys/socket.h>
#include <unordered_map>
#include <unistd.h>

static int set_nonblock(int fd) {
    int fl = fcntl(fd, F_GETFL, 0);
    return fcntl(fd, F_SETFL, fl | O_NONBLOCK);
}

int main() {
    int lfd = socket(AF_INET, SOCK_STREAM, 0);
    int on = 1;
    setsockopt(lfd, SOL_SOCKET, SO_REUSEADDR, &on, sizeof(on));
    sockaddr_in addr{};
    addr.sin_family = AF_INET; addr.sin_port = htons(8888);
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    bind(lfd, (sockaddr*)&addr, sizeof(addr));
    listen(lfd, 512);
    set_nonblock(lfd);                                  // 非阻塞，配合循环 accept

    int ep = epoll_create1(EPOLL_CLOEXEC);
    epoll_event ev{ EPOLLIN, {.fd = lfd} };
    epoll_ctl(ep, EPOLL_CTL_ADD, lfd, &ev);

    struct Conn { std::string snd; };                  // 每连接发送缓冲
    std::unordered_map<int, Conn> conns;
    epoll_event evs[1024];

    auto mod = [&](int fd, uint32_t events) {          // 改关注事件
        epoll_event e{ events, {.fd = fd} };
        epoll_ctl(ep, EPOLL_CTL_MOD, fd, &e);
    };
    auto close_conn = [&](int fd) {                    // 唯一清理出口
        epoll_ctl(ep, EPOLL_CTL_DEL, fd, nullptr);
        conns.erase(fd);
        close(fd);
    };

    for (;;) {
        int n = epoll_wait(ep, evs, 1024, -1);
        if (n < 0) { if (errno == EINTR) continue; perror("wait"); break; }

        for (int i = 0; i < n; ++i) {
            int fd = evs[i].data.fd, e = evs[i].events;

            if (fd == lfd) {                          // ① 新连接：循环 accept 到 EAGAIN
                for (;;) {
                    int cfd = accept(lfd, nullptr, nullptr);
                    if (cfd < 0) break;               // EAGAIN：这批取完了
                    set_nonblock(cfd);
                    conns.emplace(cfd, Conn{});
                    epoll_event ce{ EPOLLIN | EPOLLRDHUP, {.fd = cfd} };
                    epoll_ctl(ep, EPOLL_CTL_ADD, cfd, &ce);
                }
                continue;
            }
            if (e & (EPOLLERR | EPOLLHUP)) { close_conn(fd); continue; }  // ② 错误优先

            if (e & (EPOLLIN | EPOLLRDHUP)) {         // ③ 可读 / 对端关闭
                char buf[4096];
                ssize_t r = recv(fd, buf, sizeof(buf), 0);
                if (r == 0 || (r < 0 && errno != EINTR && errno != EAGAIN)) {
                    close_conn(fd);                    // FIN 或真错误
                    continue;
                }
                if (r > 0) {                          // 收到数据 → 尝试立刻回写
                    auto& snd = conns[fd].snd;
                    snd.append(buf, (size_t)r);
                    while (!snd.empty()) {             // 尽量发
                        ssize_t s = send(fd, snd.data(), snd.size(), MSG_NOSIGNAL);
                        if (s > 0) { snd.erase(0, s); continue; }
                        if (errno == EINTR) continue;
                        if (errno == EAGAIN) break;    // 发送缓冲满：剩下的等 EPOLLOUT
                        close_conn(fd); break;         // EPIPE/RESET
                    }
                    if (conns.count(fd) && !conns[fd].snd.empty())
                        mod(fd, EPOLLIN | EPOLLRDHUP | EPOLLOUT);  // ④ 有积压才关心可写
                }
            }
            if (conns.count(fd) && (e & EPOLLOUT)) {  // ⑤ 可写：继续发积压
                auto& snd = conns[fd].snd;
                while (!snd.empty()) {
                    ssize_t s = send(fd, snd.data(), snd.size(), MSG_NOSIGNAL);
                    if (s > 0) { snd.erase(0, s); continue; }
                    if (errno == EINTR) continue;
                    if (errno == EAGAIN) break;
                    close_conn(fd); break;
                }
                if (conns.count(fd) && snd.empty())
                    mod(fd, EPOLLIN | EPOLLRDHUP);     // ⑥ 发完注销 EPOLLOUT，防忙轮询
            }
        }
    }
}
```

要点：非阻塞 fd、错误事件优先、`EPOLLOUT` 按需开关、发送缓冲兜底部分写、统一清理出口。ET 版本只需把注册事件加上 `EPOLLET`，并把 recv 改成 4.6 的"读到 EAGAIN"循环。

---

## 5. select / poll / epoll 横向对比

### 5.1 总表

| 维度 | select | poll | epoll |
| --- | --- | --- | --- |
| 操作方式 | 位图 | pollfd 数组 | 红黑树注册 + 就绪链表 |
| fd 上限 | FD_SETSIZE=1024 | 无硬上限 | 无硬上限（受内存/fd 上限） |
| fd 传递 | 每次三表全量拷贝，且被改写需重建 | 每次数组全量拷贝，输入不被改写 | **ctl 注册一次，内核长期持有** |
| 就绪发现 | 内核线性扫 + 用户再遍历 | 同左 | 回调挂就绪链，**wait 只取就绪的** |
| 单次等待复杂度 | O(n) | O(n) | **O(就绪数)**，与总连接数无关 |
| 增删一个 fd | 改位图（下次生效） | 改数组（下次生效） | O(log n)，立即生效 |
| 触发模式 | 仅水平 | 仅水平 | **水平 LT / 边沿 ET** |
| 事件精度 | 读/写/异常 | +ERR/HUP/NVAL | +RDHUP/ONESHOT/EXCLUSIVE 等 |
| 跨平台 | 全平台 | POSIX | Linux（BSD=kqueue，Win=IOCP） |
| 最佳场景 | 少量 fd、跨平台 | 几千 fd | 万级长连接、少量活跃 |

### 5.2 跨平台与下一代

| 平台/机制 | 多路复用 | 模型 |
| --- | --- | --- |
| Linux | epoll | 同步 Reactor |
| BSD/macOS | kqueue（设计更通用，还能监视文件/信号/定时器） | 同步 Reactor |
| Windows | IOCP | 异步 Proactor |
| Linux 新世代 | io_uring | 异步 Proactor（详见《../13-并发异步与组件/02-io_uring与异步IO.md》） |

成熟网络库（libevent/libuv/muduo/Netty）都把底层多路复用抽象成统一 dispatcher 接口，编译/运行期选择实现。

---

## 6. Reactor 模式

### 6.1 定义与经典角色

**Reactor（反应器）= I/O 事件的多路分发器**：一个事件循环阻塞在多路复用器上，事件到达后**分发给预先注册的处理器回调**；所有 I/O 非阻塞，业务逻辑写在回调里。它是观察者模式在 I/O 上的应用，POSA2 书里定义了 5 个标准角色：

| 经典角色 | 落地对应 |
| --- | --- |
| Handle（句柄） | fd（listenfd / connfd / timerfd / eventfd） |
| Synchronous Event Demultiplexer（同步事件分离器） | select / poll / epoll_wait |
| Initiation Dispatcher（初始分发器） | EventLoop：注册/移除 handler、跑循环、分发事件 |
| Event Handler（处理器接口） | 回调集合：onReadable/onWritable/onError |
| Concrete Event Handler | Acceptor（处理 listenfd）、TcpConnection（处理连接 fd）、业务 handler |

### 6.2 Reactor vs Proactor【高频辨析】

| 维度 | Reactor（反应器） | Proactor（前摄器） |
| --- | --- | --- |
| 谁做 I/O | 分离器只通知"**可以读/写了**"，**用户线程自己**调 recv/send | 用户发起异步请求，**内核做完整个 I/O（含拷贝）**后通知"**已完成**" |
| 通知语义 | 就绪事件（ready） | 完成事件（completion） |
| fd 模型 | 非阻塞 + 读到 EAGAIN | 发起时带好缓冲区，期间可干别的 |
| 典型实现 | epoll、kqueue、select | Windows IOCP、Linux io_uring、POSIX AIO |
| 编程复杂度 | 回调 + 自己管收发缓冲 | 回调拿到的就是成品数据，但异步生命周期更绕 |

> Boost.Asio 在 Linux 上用 epoll 模拟出 Proactor 风格的接口；协程则是在 Reactor 之上用"挂起/恢复"把回调写回同步顺序（见《../13-并发异步与组件/01-协程框架原理与实现.md》）。

### 6.3 三种线程模型【高频】

| 形态 | 结构 | 优点 | 缺点 | 代表 |
| --- | --- | --- | --- | --- |
| 单 Reactor 单线程 | accept + I/O + 业务全在一个线程 | 无锁、最简单、无竞态 | 一个慢回调卡死全部；吃不到多核 | Redis 6.0 前 |
| 单 Reactor 多线程 | Reactor 只做 I/O 分发，业务丢**线程池** | 业务耗时不卡 I/O | 单个 Reactor 的 wait+分发是吞吐天花板 | 多数教学实现 |
| 主从 Reactor 多线程 | **主** Reactor 只 accept，**从** Reactor 各管一批连接的 I/O | accept 与 I/O 分离，I/O 横向吃多核 | 连接分发/迁移更复杂 | muduo、Netty、memcached、Redis 6.0+ |

```text
形态1：单 Reactor 单线程                 形态3：主从 Reactor
 ┌──────────────────────┐               ┌─────────────────────────────┐
 │  Reactor 线程         │               │ mainReactor：epoll 只挂 lfd   │
 │   epoll_wait         │               │   accept → 按策略派发 connfd   │
 │    ├ accept         │               │             │ 轮询/最少连接   │
 │    ├ recv → 业务     │               │             ▼               │
 │    └ send           │               │ subReactor#1     subReactor#2 │
 └──────────────────────┘               │  epoll+连接集     epoll+连接集 │
                                        │   recv/send       recv/send  │
                                        │   (重业务再丢线程池)            │
                                        └─────────────────────────────┘
```

### 6.4 one loop per thread 与跨线程唤醒

工业级 C++ 网络库（muduo）的主流范式：**起 CPU 核数个 EventLoop 线程，每个连接只属于其中一个 loop，连接的所有 I/O 都在所属 loop 线程执行**——同一连接天然串行、无锁。

跨线程怎么把任务"递"给另一个 loop 的线程？用 **eventfd**：它是一个 8 字节计数器 fd，被目标 loop 注册进 epoll；别的线程向它 `write(8 字节)` 即可立刻唤醒其 `epoll_wait`，loop 醒来执行任务队列。

```text
main loop accept 到 connfd
   → 选一个 sub loop（轮询/最少连接）
   → 往该 loop 的任务队列 push "添加连接"，并 write(eventfd) 唤醒它
   → sub loop 的 epoll_wait 被 eventfd 唤醒，执行队列任务，把 connfd 加进自己的 epoll
此后该连接只在这个 sub loop 上读写 → 无数据竞争
```

### 6.5 手撕精简 Reactor（可编译核心）

三层抽象：**Channel（fd+事件+回调）→ EventLoop（epoll+分发循环）→ 具体处理器**。下面是可编译的核心，Acceptor/Connection 只演示如何复用它。

```cpp
// mini_reactor.cpp —— 编译：g++ -std=c++17 -O2 mini_reactor.cpp -o mini_reactor
#include <sys/epoll.h>
#include <unistd.h>
#include <functional>
#include <unordered_map>
#include <vector>
#include <cstdint>

struct Channel {                                   // 一个 fd 与它的事件/回调绑定
    int fd = -1;
    uint32_t events = 0;                          // EPOLLIN / EPOLLOUT ...
    std::function<void()> readCb, writeCb, errorCb;
};

class EventLoop {
public:
    EventLoop() { epfd_ = epoll_create1(EPOLL_CLOEXEC); }
    ~EventLoop(){ if (epfd_ >= 0) close(epfd_); }

    void update(Channel* ch) {                    // 新增或修改（不存在则 ADD，存在则 MOD）
        epoll_event ev{ ch->events, {} };
        ev.data.ptr = ch;                         // ★ 用 ptr 带回 Channel，事件到达即找回处理器
        int op = channels_.count(ch->fd) ? EPOLL_CTL_MOD : EPOLL_CTL_ADD;
        epoll_ctl(epfd_, op, ch->fd, &ev);
        channels_[ch->fd] = ch;
    }
    void remove(int fd) {
        epoll_ctl(epfd_, EPOLL_CTL_DEL, fd, nullptr);
        channels_.erase(fd);
    }
    void loop() {                                 // 事件循环：等待 → 分发
        std::vector<epoll_event> evs(1024);
        for (;;) {
            int n = epoll_wait(epfd_, evs.data(), (int)evs.size(), -1);
            if (n < 0) continue;                  // EINTR
            for (int i = 0; i < n; ++i) {
                auto* ch = static_cast<Channel*>(evs[i].data.ptr);
                uint32_t e = evs[i].events;
                int fd = ch->fd;                  // 先存 fd：回调可能 close 并移除 channel
                if (e & (EPOLLERR | EPOLLHUP)) { if (ch->errorCb) ch->errorCb(); continue; }
                if ((e & EPOLLIN)  && channels_.count(fd) == 1 && ch->readCb)  ch->readCb();
                if ((e & EPOLLOUT) && channels_.count(fd) == 1 && ch->writeCb) ch->writeCb();
            }
        }
    }
private:
    int epfd_ = -1;
    std::unordered_map<int, Channel*> channels_;
};
```

接入方式（伪代码，对照第 4.9 节真实收发逻辑）：

```cpp
main:
  EventLoop loop;
  Channel listenCh{ lfd, EPOLLIN, readCb = [&]{ while(accept>0) 建连接... } };
  loop.update(&listenCh);
  loop.loop();                                  // 永不返回

accept 回调里为每条新连接：
  auto* conn = new TcpConnection(cfd, &loop);   // 内部持有 Channel
  conn.ch.readCb  = [conn]{ conn->handleRead();  };  // 收数据→拼半包→交业务
  conn.ch.writeCb = [conn]{ conn->handleWrite(); };  // 写发送缓冲，写完注销 EPOLLOUT
  conn.ch.errorCb = [conn]{ conn->handleClose(); };
  loop.update(&conn->ch);
```

### 6.6 Reactor 编程铁律

| 铁律 | 原因 / 做法 |
| --- | --- |
| 所有 fd 非阻塞 | Reactor 前提；用 EAGAIN 判断"读完/写满"，绝不能让一个 fd 睡死整个 loop |
| EPOLLOUT 按需注册 | 缓冲区常年可写，常开=epoll_wait 立即返回=CPU 100%。有待发才注册、发完注销 |
| EAGAIN 是正常分支 | 不是错误，不能因此关连接 |
| recv()==0 / EPOLLRDHUP 即关闭 | 走唯一清理出口：先 EPOLL_CTL_DEL，再释放连接对象，最后 close，防 use-after-free |
| 回调里不做重活 | DB、磁盘、复杂计算丢业务线程池，否则一个慢回调拖垮整个 loop |
| 连接归属唯一 | 一个连接只在一个 loop 上处理（one loop per thread），避免跨线程数据竞争 |

### 6.7 定时器如何接入 Reactor

| 方案 | 做法 | 特点 |
| --- | --- | --- |
| `timerfd` | 定时器也是一个可读 fd，到期变可读，统一进 epoll | 与连接事件同一套机制，最简单 |
| 最小堆 | 按"下次到期时间"排序，epoll_wait 带最近超时 | 增删 O(log n)，取最近到期 O(1)，muduo 采用 |
| 时间轮 | 环形槽 + 指针每拍前进一格 | O(1) 增删，适合海量超时连接（Kafka/Netty HashedWheelTimer） |

典型用途：连接读空闲超时踢人、心跳、重试。定时器与 eventfd 一样，都是"把非网络事件也变成 epoll 能管的 fd/事件"。

### 6.8 业界实现对照

| 项目 | 模型 | 关键点 |
| --- | --- | --- |
| Redis <6.0 | 单 Reactor 单线程（ae 事件库） | 命令单线程串行，天然无锁；ae 是 epoll/select 的薄封装 |
| Redis 6.0+ | 主从 + 多 I/O 线程 | 多线程并行读协议/写回包，**命令执行仍单线程** |
| nginx | master/worker 多进程，每 worker 单 Reactor | 进程级隔离，worker 数≈核数；SO_REUSEPORT/accept_mutex 防惊群 |
| memcached | 主线程 accept + 分发，worker 各一个 event_base | 主从多线程变体，用管道唤醒 worker |
| muduo | 主从 Reactor + one loop per thread + 线程池 | C++ 教学/工程经典，连接只属一个 loop |
| Netty | 主从 Reactor（boss/worker EventLoopGroup） | Java 工业主流，EventLoop 即 one loop per thread |
| libevent / libev / libuv | 跨平台 dispatcher 抽象 | 编译期/运行期切换 epoll/kqueue/select；libuv 是 Node.js 底座 |

---

## 7. 快速参考卡片

| 要点 | 一句话 |
| --- | --- |
| 同步/异步分界 | 阶段②数据拷贝谁做：自己 recv=同步；内核做完回调=异步（epoll 是同步） |
| select | 位图、1024 上限、nfds=maxfd+1、每次重建集合、O(n)、跨平台 |
| poll | pollfd 数组无上限、events/revents 分离；仍全量拷贝 + O(n) |
| epoll 三接口 | create1 / ctl(ADD/MOD/DEL，O(log n)) / wait(O(就绪数)) |
| epoll 快的根源 | 红黑树管注册 + 回调 ep_poll_callback 挂就绪链表 + wait 只取就绪链 |
| LT vs ET | LT 看存量（有数据就报，容错好）；ET 看跳变（报一次，必须非阻塞+读到 EAGAIN） |
| listenfd ET | 必须 while(accept) 到 EAGAIN，否则漏掉已完成连接 |
| EPOLLOUT | 有待发才注册、发完注销；常开=忙轮询 CPU 100% |
| EPOLLRDHUP | 对端半关闭/关闭，常配 EPOLLIN |
| EPOLLONESHOT | 触发一次后自动屏蔽，MOD 重新武装；共享 epfd 时连接级串行 |
| 惊群 | 多 waiter 同监听一 fd；单点 accept / SO_REUSEPORT / EPOLLEXCLUSIVE |
| Reactor 五角色 | Handle / Demultiplexer / Dispatcher / EventHandler / ConcreteHandler |
| Reactor vs Proactor | 通知"可读写"自己做 I/O vs 内核做完通知"已完成"（IOCP/io_uring） |
| 三形态 | 单Re单线程(Redis<6) / 单Re+线程池 / 主从Re(muduo/Netty) |
| one loop per thread | 一个连接只属一个 loop；跨线程用 eventfd 唤醒 |
| 定时器 | timerfd 统一进 epoll；最小堆/时间轮管海量超时 |
| data.ptr | 事件带回 Channel/连接对象，是 Reactor 找回"这是谁"的关键 |

---

## 8. 常见问题与坑

| 坑 | 现象 | 正解 |
| --- | --- | --- |
| select 的 nfds 传成 fd 个数 | 漏事件（最大 fd 之后的没被检查） | nfds = 最大 fd + 1 |
| select 返回后没重建 fd_set | 后续连接"消失"、不再触发 | 返回会改写位图，每轮 FD_ZERO + FD_SET |
| 以为 poll 解决了性能问题 | fd 上万后 poll 仍随连接数变慢 | poll 只去上限，复杂度还是 O(n)，高并发换 epoll |
| ET 没循环读到 EAGAIN | 残留数据不再通知，连接假死 | 非阻塞 + while(recv) 到 EAGAIN |
| ET 用了阻塞 fd | 最后一次 recv 永久睡死整个线程 | ET 必须 O_NONBLOCK |
| listenfd 用 ET 却只 accept 一次 | 已完成握手的连接堆积、延迟到下个连接 | ET 下循环 accept 到 EAGAIN |
| 常开 EPOLLOUT | CPU 100%，epoll_wait 立刻返回 | 有待发数据才注册，发完 `&= ~EPOLLOUT` |
| 把 EAGAIN 当错误 | 高负载下连接被莫名关闭 | EAGAIN/EWOULDBLOCK 是正常分支，结束本轮等下次 |
| 不处理 EPOLLERR/EPOLLHUP | 异常连接不释放，fd 泄漏 | 错误事件优先于读写分发 |
| recv 返回 0 不当关闭 | CLOSE_WAIT 堆积、连接泄漏 | 0=对端 FIN，走统一关闭（DEL→释放→close） |
| 释放连接后本轮又分发到它 | use-after-free 崩溃 | 先 DEL 再释放；分发前用注册表确认该 fd 仍在 |
| 回调里做 DB/磁盘/重计算 | 单 Reactor 所有连接被拖卡 | 重活投线程池，或主从 Reactor 扩 I/O 线程 |
| 多线程共享 epfd 处理同一 fd | 同一连接被并发读写、数据竞争 | EPOLLONESHOT 串行，或 one loop per thread 让连接只属一个 loop |
| 频繁 epoll_ctl ADD/DEL | 系统调用开销累积 | 连接长期注册，用 MOD 切换 IN/OUT |
| send 不处理部分写、不加 MSG_NOSIGNAL | 数据缺尾；对端重置时 SIGPIPE 杀进程 | 循环 send + 发送缓冲；MSG_NOSIGNAL 或全局忽略 SIGPIPE |
| 以为 epoll 万能 | fd 很少/全部活跃时没优势 | 按连接规模与活跃度选型（见 5.1） |

---

上一篇：《01-计算机网络协议详解.md》　｜　下一篇：《03-网络安全与加密编程.md》　｜　模块索引：《../README.md》
