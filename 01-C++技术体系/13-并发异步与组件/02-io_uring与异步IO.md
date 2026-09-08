# io_uring与异步IO

> 本节目标：掌握 Linux 异步 IO 的下一代方案 io_uring——理解三系统调用（setup/register/enter）与 SQ/CQ 双环共享内存架构、内存屏障必要性、SQE/CQE 字段语义；能用 liburing 写出 echo 服务器与批量磁盘读写，掌握 SQPOLL 零 syscall、register 预注册、multishot 等高级特性；理解 Proactor 与 Reactor 的本质区别，了解 Windows IOCP 机制与跨平台抽象思路。前置《../12-网络与服务器架构/04-Reactor与高性能网络库.md》（epoll 与 Reactor 模型），关联《03-用户态协议栈与DPDK.md》（旁路内核方案）、《01-协程框架原理与实现.md》（异步编程的同步化封装）。 课程模块 2.5：高性能异步 IO 机制。本篇覆盖：与 epoll 媲美（并超越）的 io_uring、Windows 异步机制 IOCP。前置知识：`../03-计算机网络编程/02-IO多路复用与Reactor模型.md`（五种 IO 模型与 epoll）、`09-用户态协议栈与DPDK.md`（第 7 节手写 epoll，本篇的对照组）、`../04-并发与多线程编程/01-并发编程与线程同步.md`（内存序与共享内存）。

## 本章速览

- [1. 概述](#1-概述)
  - [1.1 IO 模型四象限](#11-io-模型四象限)
  - [1.2 五种 IO 模型一句话回顾](#12-五种-io-模型一句话回顾)
  - [1.3 epoll 仍剩什么开销](#13-epoll-仍剩什么开销)
  - [1.4 io_uring 的目标](#14-io_uring-的目标)
- [2. io_uring 架构【核心】](#2-io_uring-架构核心)
  - [2.1 三个系统调用](#21-三个系统调用)
  - [2.2 SQ/CQ 双环结构](#22-sqcq-双环结构)
  - [2.3 SQE / CQE 字段表【必背】](#23-sqe--cqe-字段表必背)
  - [2.4 SQ 间接索引数组的设计原因](#24-sq-间接索引数组的设计原因)
- [3. liburing 使用【实战】](#3-liburing-使用实战)
  - [3.1 liburing 与裸接口的关系](#31-liburing-与裸接口的关系)
  - [3.2 标准流程完整代码](#32-标准流程完整代码)
  - [3.3 常用 prep 函数表](#33-常用-prep-函数表)
  - [3.4 SQPOLL 模式](#34-sqpoll-模式)
  - [3.5 io_uring_register 的收益](#35-io_uring_register-的收益)
  - [3.6 multishot](#36-multishot)
- [4. 网络与磁盘实战](#4-网络与磁盘实战)
  - [4.1 io_uring echo server 核心代码](#41-io_uring-echo-server-核心代码)
  - [4.2 磁盘异步读写](#42-磁盘异步读写)
  - [4.3 与 epoll 的性能对比](#43-与-epoll-的性能对比)
  - [4.4 内核版本要求与稳定性演进](#44-内核版本要求与稳定性演进)
- [5. Proactor 模式【高频】](#5-proactor-模式高频)
  - [5.1 Reactor vs Proactor 对比](#51-reactor-vs-proactor-对比)
  - [5.2 为什么 io_uring 与 IOCP 是 Proactor](#52-为什么-io_uring-与-iocp-是-proactor)
- [6. Windows IOCP](#6-windows-iocp)
  - [6.1 完成端口工作机制](#61-完成端口工作机制)
  - [6.2 并发度概念](#62-并发度概念)
  - [6.3 重叠 IO（Overlapped IO）](#63-重叠-iooverlapped-io)
  - [6.4 IOCP 处理连接与收发的流程](#64-iocp-处理连接与收发的流程)
  - [6.5 IOCP vs io_uring 对比](#65-iocp-vs-io_uring-对比)
- [7. 跨平台抽象层设计](#7-跨平台抽象层设计)
  - [7.1 统一接口思路](#71-统一接口思路)
  - [7.2 开源库一览](#72-开源库一览)
- [8. 快速参考卡片](#8-快速参考卡片)
- [9. 常见问题与坑](#9-常见问题与坑)

---

## 1. 概述

### 1.1 IO 模型四象限

```text
                     阻塞                      非阻塞
        +---------------------------+---------------------------+
        | read() 阻塞到数据就绪      | read() 立即返回 EAGAIN,   |
  同步   | (最简单, 一线程一连接)     | 配合 epoll 等"就绪通知"    |
        |                           | 由用户自己发起并完成 read   |
        +---------------------------+---------------------------+
        | (逻辑上不存在)             | 异步IO: 提交请求即返回,     |
  异步   |                           | 内核完成整个IO后才通知用户  |
        |                           | (io_uring / IOCP)          |
        +---------------------------+---------------------------+
```

判断口诀：**谁执行真正的 read/write**。内核只告知"可以读了"→ 同步（epoll）；内核将数据搬入缓冲区再告知"读完了"→ 异步（io_uring/IOCP）。

### 1.2 五种 IO 模型一句话回顾

| 模型 | 一句话 |
|---|---|
| 阻塞 IO | read 卡住直到有数据 |
| 非阻塞 IO | 轮询 read，EAGAIN 就再试，浪费 CPU |
| IO 多路复用 | select/poll/epoll 一次等一批 fd（详见 `../03-计算机网络编程/02-IO多路复用与Reactor模型.md`） |
| 信号驱动 IO | SIGIO 通知就绪，处理碎、极少用 |
| 异步 IO | 内核完成整个 IO 再通知（aio 家族 → io_uring / IOCP） |

### 1.3 epoll 仍剩什么开销

| 剩余开销 | 说明 |
|---|---|
| 每次读写仍是一次 syscall | epoll 只复用了"等待"，就绪后的每次 read/write 依旧单独陷入内核 |
| copy_to/from_user | 数据从内核 buffer 拷到用户 buffer，每次 IO 都要 |
| 唤醒路径长 | 数据到达 → 硬中断 → 软中断 → 唤醒 epoll_wait 线程 → 再发起 read |
| 不支持磁盘异步 | 普通文件在 epoll 上永远"就绪"（页缓存命中与否另说），毫无意义 |

### 1.4 io_uring 的目标

- **amortize（摊销）syscall**：一次 `io_uring_enter` 提交一批 SQE，一次收割一批 CQE，把 N 次 read/write 的 N 次 syscall 摊成 1 次
- **SQPOLL 模式消灭 syscall**：内核线程持续轮询提交队列，用户态写共享内存即完成提交，syscall 数为零
- **统一网络与磁盘**：同一套接口覆盖 socket、普通文件、甚至 timer / 文件系统操作

## 2. io_uring 架构【核心】

### 2.1 三个系统调用

| 系统调用 | 签名要点 | 作用 |
|---|---|---|
| io_uring_setup | `io_uring_setup(entries, params)` → 返回 ringfd | 创建实例；通过返回的 params（sq_off/cq_off 偏移）mmap 出 SQ/CQ 共享内存 |
| io_uring_register | `io_uring_register(fd, opcode, arg, nr_args)` | 预注册资源：缓冲区/文件表等，内核提前 pin 住，省去每次 IO 的固定开销 |
| io_uring_enter | `io_uring_enter(fd, to_submit, min_complete, flags, sigset)` | 提交 SQE / 等待 CQE / 唤醒 SQPOLL 内核线程 |

一个 io_uring 实例 = 一对环（SQ/CQ）+ 一个内核侧任务处理引擎；应用与内核通过 mmap 的共享内存交换"请求"与"结果"，中间唯一的内核交互点就是 io_uring_enter。

### 2.2 SQ/CQ 双环结构

```text
        io_uring_setup 后 mmap 得到的共享内存(用户态与内核态共享)
+------------------------------------------------------------------+
|  SQ(提交环)                          CQ(完成环)                  |
|  +-----------------------------+    +--------------------------+ |
|  | sq_array: [idx][idx][idx]…  |    | cqe: [user_data|res|flags]| |
|  |   ^head          ^tail      |    |   ^head        ^tail     | |
|  +------|--------------|-------+    +--------------------------+ |
|         |  间接索引      |             内核写CQE并推进cq_tail      |
|         v              |             用户读CQE并推进cq_head      |
|  +-----------------------------+                                  |
|  | SQE数组: sqe[0..N-1]         |   ← 用户填SQE, 推进sq_tail     |
|  +-----------------------------+     内核消费SQE, 推进sq_head    |
+------------------------------------------------------------------+
   单向发布: 生产者只写 tail, 消费者只写 head → 无需锁, 只需内存屏障
```

**为什么必须内存屏障**：SQE 的字段写入与 `sq_tail = new_tail` 是两次普通存储。在弱内存序 CPU（ARM）上，消费方（内核）可能先看到 tail 更新、后看到槽内数据（存储重排），于是读到一个半成品 SQE。因此：

| 方向 | 写方 | 读方 | 语义 |
|---|---|---|---|
| SQ | 用户 `smp_store_release(sq_tail)` | 内核 `smp_load_acquire(sq_tail)` | 保证内核看到完整 SQE 后才消费 |
| CQ | 内核 `smp_store_release(cq_tail)` | 用户 `smp_load_acquire(cq_tail)` | 保证用户看到完整 CQE 后才收割 |

x86 是强内存序（TSO），天然不易暴露；ARM 服务器上省掉屏障就是数据竞争。这正是 liburing 内部 `io_uring_smp_store_release` 存在的原因，详见 `../04-并发与多线程编程/01-并发编程与线程同步.md` 内存序一章。

### 2.3 SQE / CQE 字段表【必背】

SQE（submission queue entry，64 字节）核心字段：

| 字段 | 说明 | 示例 |
|---|---|---|
| opcode | 操作类型：IORING_OP_READ/WRITE/RECV/SEND/ACCEPT/CONNECT/POLL_ADD/TIMEOUT 等 | READ=8、WRITE=9、ACCEPT=13、RECV=21、SEND=20 |
| flags | SQE 级标志：IOSQE_FIXED_FILE（fd 是固定文件表索引）、IOSQE_IO_LINK（链接下一个）、IOSQE_IO_DRAIN（排空）、IOSQE_ASYNC（强制异步）、IOSQE_BUFFER_SELECT（从缓冲组取） | 链式读写两个文件 |
| fd | 目标文件描述符（或固定文件表索引，配合 FIXED_FILE） | conn->fd |
| addr | 数据缓冲区地址（READ/WRITE 语义）或目标地址 | buf 指针 |
| len | 缓冲区长度 | sizeof(buf) |
| off | 文件偏移（磁盘必填，socket 为 0/忽略） | offset += n |
| user_data | 透传字段：提交时写什么，完成时 CQE 原样带回 | 连接指针/编码 (类型,索引) |
| buf_index | 配合 BUFFER_SELECT 的缓冲组 id | 收包选 buffer |
| rw_flags 等联合 | 按 opcode 解释（如 recv 的 MSG_*） | MSG_DONTWAIT |

CQE（completion queue entry，16 字节）只有三个字段：

| 字段 | 说明 |
|---|---|
| user_data | 与对应 SQE 完全一致，据此路由到连接/上下文 |
| res | 结果：≥0 为成功（读写字节数/accept 的新 fd）；<0 为 -errno |
| flags | IORING_CQE_F_MORE（multishot 后续还有）、IORING_CQE_F_BUFFER（buffer id 在高 16 位） |

### 2.4 SQ 间接索引数组的设计原因

SQ 环本体存的不是 SQE，而是 **SQE 的下标数组（sq_array）**：`sq_array[sq_tail & mask]` 的值才是真正 SQE 的槽位号。原因有三：

1. **提交顺序与填槽顺序解耦**：应用可以在任意空闲槽填 SQE，再把该槽下标写进索引环的 tail 位——槽位乱填、顺序由环决定
2. **槽位高效复用**：一批 SQE 被消费后，同样的槽位可被下一批直接重写，无需搬移数据
3. **批量提交天然友好**：一次 enter 提交 K 个，就是往索引环追加 K 个下标，内核按序取用

CQ 不需要这层间接：完成事件只有 16 字节，直接在环里原地写 CQE 即可。

## 3. liburing 使用【实战】

### 3.1 liburing 与裸接口的关系

裸接口（自己 mmap、自己维护四个 head/tail 指针、自己打屏障）正确性极难保证；liburing 是官方薄封装：结构体 `io_uring`、`io_uring_sqe`、`io_uring_cqe` + 一批内联函数，并把"攒一批再 enter"的批处理策略做成了默认（`io_uring_submit` 会批量 flush），减少 enter 次数。

### 3.2 标准流程完整代码

```cpp
#include <liburing.h>
#include <unistd.h>
#include <cstring>
#include <cstdio>

int main() {
    struct io_uring ring;
    // 1. 初始化: 256 深度, 默认 flags
    io_uring_queue_init(256, &ring, 0);

    char buf[4096];
    // 2. 取一个空闲 SQE
    struct io_uring_sqe *sqe = io_uring_get_sqe(&ring);
    // 3. 填充操作: 对 stdin 读 128 字节(也可 prep_read 对任意 fd)
    io_uring_prep_read(sqe, STDIN_FILENO, buf, sizeof(buf), 0);
    io_uring_sqe_set_data(sqe, (void *)0x1234);      // user_data 透传
    // 4. 提交(可能批量 flush 多个 SQE)
    io_uring_submit(&ring);

    // 5. 阻塞等待一个完成
    struct io_uring_cqe *cqe;
    int ret = io_uring_wait_cqe(&ring, &cqe);
    if (ret == 0) {
        printf("res=%d data=%p\n", cqe->res, io_uring_cqe_get_data(cqe));
        // 6. 确认收割: 推进 cq_head, 否则 CQ 满后内核会阻塞/丢弃
        io_uring_cqe_seen(&ring, cqe);
    }
    io_uring_queue_exit(&ring);
    return 0;
}
```

| 步骤 | 函数 | 易错点 |
|---|---|---|
| 初始化 | io_uring_queue_init(entries, ring, flags) | entries 是 SQ 深度，CQ 默认 2× |
| 取 SQE | io_uring_get_sqe | 满了返回 NULL，忘判空就崩 |
| 填操作 | io_uring_prep_* | 参数顺序各不相同，见 3.3 |
| 提交 | io_uring_submit | 忘记提交 = 永远等不到 CQE |
| 等完成 | io_uring_wait_cqe / peek_cqe | peek 非阻塞，wait 阻塞 |
| 收割确认 | io_uring_cqe_seen | 忘调则 cq_head 不动，CQ 满 |

### 3.3 常用 prep 函数表

| 函数 | 对应 opcode | 语义 |
|---|---|---|
| io_uring_prep_read / write | READ / WRITE | 磁盘/任意 fd 读写，带 off 偏移 |
| io_uring_prep_readv / writev | READV / WRITEV | iovec 聚集读写 |
| io_uring_prep_read_fixed / write_fixed | READ_FIXED / WRITE_FIXED | 用注册的固定缓冲区，省 pin 开销 |
| io_uring_prep_recv / send | RECV / SEND | socket 收发 |
| io_uring_prep_accept | ACCEPT | 等价 accept4，res 为新 fd |
| io_uring_prep_connect | CONNECT | 等价 connect |
| io_uring_prep_poll_add | POLL_ADD | 等价 poll 单 fd |
| io_uring_prep_timeout | TIMEOUT | 定时器：超时后产生 res=-ETIME 的 CQE |
| io_uring_prep_multishot_accept | ACCEPT + MULTISHOT | 一次注册，多次派发新连接 |

### 3.4 SQPOLL 模式

| 项 | 默认模式 | SQPOLL 模式 |
|---|---|---|
| 提交方式 | 用户调 io_uring_enter | 内核线程（sqpoll 线程）持续轮询 SQ |
| 用户态 syscall | 每批一次 enter | **零**（写共享内存即可） |
| 空闲行为 | 无开销 | 内核线程要么自旋要么休眠（需 idle 超时配置） |
| 权限 | 普通用户 | 传统上需要特权/降低 sq_thread_idle |
| 适用 | 通用 | 超低延迟场景（交易/游戏服） |

代价：内核线程空转烧 CPU；必须设置合理的 `sq_thread_idle`，空闲后线程休眠，用 `io_uring_enter` 的 IORING_ENTER_SQ_WAKEUP 唤醒。

### 3.5 io_uring_register 的收益

| 注册项 | opcode | 收益 |
|---|---|---|
| 固定缓冲区 | IORING_REGISTER_BUFFERS | 内核一次性 pin 住用户内存页，后续 READ_FIXED/WRITE_FIXED 免去每次映射/pin，且可配合零拷贝 |
| 固定文件表 | IORING_REGISTER_FILES | 内核持有 file 引用，SQE 的 fd 字段变成小整数索引，省 fget/fput 原子开销，对高频 IO 收益明显 |

### 3.6 multishot

传统 accept：每来一个连接要重新提交一次 accept SQE。multishot（accept 的 `IORING_ACCEPT_MULTISHOT`、recv 的 `IORING_RECV_MULTISHOT`，需较新内核：accept 5.19+、recv 6.0+）让一个 SQE 持续产生多个 CQE：

| 要点 | 说明 |
|---|---|
| 触发 | 每次有新连接/新数据，就产出一条 CQE，无需重新注册 |
| 终止 | 出错（res<0）自动终止；主动取消走 IORING_OP_ASYNC_CANCEL |
| 识别 | CQE flags 带 IORING_CQE_F_MORE 表示"后面还有" |
| 陷阱 | 忘记识别终止 CQE 就继续等 → 卡死；重复注册 multishot 造成事件风暴 |

## 4. 网络与磁盘实战

### 4.1 io_uring echo server 核心代码

多连接管理要点：**用 user_data 编码"操作类型 + 连接索引"**，一条 CQE 回来就知道是哪个连接的哪一步。

```cpp
#include <liburing.h>
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
#include <cstdio>
#include <cstring>

enum { OP_ACCEPT = 0, OP_RECV = 1, OP_SEND = 2 };
struct conn { int fd; char buf[4096]; bool used; };
static conn g_conns[1024];

static inline uint64_t mk_ud(int op, int idx) {      // user_data 编码
    return (uint64_t)op << 32 | (uint32_t)idx;
}
static inline void ud_split(uint64_t ud, int &op, int &idx) {
    op = (int)(ud >> 32); idx = (int)(ud & 0xffffffffu);
}

static void prep_recv(io_uring *ring, int idx) {
    io_uring_sqe *sqe = io_uring_get_sqe(ring);
    io_uring_prep_recv(sqe, g_conns[idx].fd, g_conns[idx].buf,
                       sizeof(g_conns[idx].buf), 0);
    io_uring_sqe_set_data64(sqe, mk_ud(OP_RECV, idx));
}
static void prep_send(io_uring *ring, int idx, int len) {
    io_uring_sqe *sqe = io_uring_get_sqe(ring);
    io_uring_prep_send(sqe, g_conns[idx].fd, g_conns[idx].buf, len, 0);
    io_uring_sqe_set_data64(sqe, mk_ud(OP_SEND, idx));
}
static int alloc_conn() { for (int i = 0; i < 1024; i++)
    if (!g_conns[i].used) return i; return -1; }

int main() {
    int lfd = socket(AF_INET, SOCK_STREAM, 0);
    int one = 1;
    setsockopt(lfd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
    sockaddr_in addr{}; addr.sin_family = AF_INET;
    addr.sin_port = htons(8888); addr.sin_addr.s_addr = INADDR_ANY;
    bind(lfd, (sockaddr *)&addr, sizeof(addr));
    listen(lfd, 512);
    // socket 建议非阻塞, io_uring 本身对阻塞 fd 也强制走异步

    io_uring ring;
    io_uring_queue_init(1024, &ring, 0);

    io_uring_sqe *sqe = io_uring_get_sqe(&ring);     // 初始 accept
    io_uring_prep_accept(sqe, lfd, nullptr, nullptr, 0);
    io_uring_sqe_set_data64(sqe, mk_ud(OP_ACCEPT, 0));
    io_uring_submit(&ring);

    for (;;) {
        io_uring_cqe *cqe;
        io_uring_wait_cqe(&ring, &cqe);              // 阻等下一条完成
        int op, idx; ud_split(io_uring_cqe_get_data64(cqe), op, idx);
        int res = cqe->res;
        io_uring_cqe_seen(&ring, cqe);               // 立即确认收割

        if (op == OP_ACCEPT) {
            if (res >= 0) {
                int ci = alloc_conn();
                g_conns[ci] = {res, {}, true};
                prep_recv(&ring, ci);                // 新连接挂 recv
            }
            sqe = io_uring_get_sqe(&ring);           // 继续挂下一个 accept
            io_uring_prep_accept(sqe, lfd, nullptr, nullptr, 0);
            io_uring_sqe_set_data64(sqe, mk_ud(OP_ACCEPT, 0));
        } else if (op == OP_RECV) {
            if (res <= 0) {                          // 0=对端关闭 <0=出错
                close(g_conns[idx].fd); g_conns[idx].used = false;
            } else {
                prep_send(&ring, idx, res);          // 原样回写
            }
        } else {                                     // OP_SEND
            if (res < 0) { close(g_conns[idx].fd); g_conns[idx].used = false; }
            else prep_recv(&ring, idx);              // 回到收
        }
        io_uring_submit(&ring);                      // 批量提交本轮所有 SQE
    }
}
```

与 Reactor 的结构对照：epoll 版是"事件循环 + 每连接手动 read/write"；io_uring 版是"完成驱动"，每个回调就是一次完成的 IO，状态机只剩 ACCEPT→RECV→SEND 的三拍循环。

### 4.2 磁盘异步读写

epoll 管不了普通文件的"真异步"；io_uring 原生支持，且最能体现批量摊销：

| 方案 | 读 1000 个块 | syscall 次数 |
|---|---|---|
| pread 循环 | 逐个 pread，每次都陷入内核 | 1000 |
| 多线程 pread | 开 N 线程并行，线程数与并发度绑定 | 1000（分摊在多线程）+ 线程创建切换 |
| io_uring | 循环 `io_uring_prep_read` 攒 SQE → 一次 submit → wait/peek 批量收割 | 1 次提交 + 少量收割 |

```cpp
// 批量读文件的核心片段（对比 pread/pwrite 循环）
for (int i = 0; i < nblocks; i++) {
    io_uring_sqe *sqe = io_uring_get_sqe(&ring);
    io_uring_prep_read(sqe, fd, bufs[i], BLOCK, (off_t)i * BLOCK);
    io_uring_sqe_set_data64(sqe, i);            // 完成后知道是哪块
}
io_uring_submit(&ring);                         // 一次性提交
unsigned head, nr = 0;
io_uring_for_each_cqe(&ring, head, cqe) {       // 批量收割
    done[cqe->user_data] = cqe->res;            // res 即读到的字节数
    nr++;
}
io_uring_cq_advance(&ring, nr);                 // 一次性推进 cq_head
```

### 4.3 与 epoll 的性能对比

| 维度 | epoll | io_uring |
|---|---|---|
| syscall 次数 | epoll_wait 1 次 + 每连接 read/write 各 1 次 | 提交/收割各 1 次，可摊到一批连接 |
| 数据拷贝 | read/write 时 copy_to/from_user | 相同（非零拷贝），但固定缓冲可减少重复 pin |
| 唤醒路径 | 中断→软中断→唤醒等待线程 | 默认相同；SQPOLL 由内核线程轮询，进一步省唤醒 |
| 批量能力 | 无（就绪一批但读写仍逐个发起） | SQE 天然批量 |
| 磁盘异步 | 不支持 | 原生支持 |
| 适用场景 | 通用网络服务、长连接 | 高并发短 IO、磁盘密集（日志/存储）、超低延迟（SQPOLL） |

结论不是"io_uring 全面替代 epoll"：连接数适中、IO 较大的业务，epoll + read 已经够快且生态成熟；海量小 IO、磁盘异步、延迟敏感才显著获益。

### 4.4 内核版本要求与稳定性演进

| 版本 | 状态 |
|---|---|
| 5.1 | io_uring 首发（2019），仅基础 op |
| 5.5 | buffer select、registered files 完善、稳定性大改 |
| 5.10 | LTS，功能齐全、坑修掉大半，可视为"最低生产线" |
| 5.15 | LTS，推荐基线：各类 opcode、probe 机制成熟 |
| 5.19 / 6.0+ | multishot accept / recv（6.0）、后续零拷贝 send（6.0 zerocopy）、多持续增强 |

面试口径：io_uring 5.1 引入，5.10/5.15 之后才逐渐生产可用；用新内核 + liburing，并用 `io_uring_probe` 在运行时确认 opcode 支持，而不是赌内核版本。

## 5. Proactor 模式【高频】

### 5.1 Reactor vs Proactor 对比

| 维度 | Reactor（epoll/select/kqueue） | Proactor（io_uring/IOCP） |
|---|---|---|
| 通知内容 | **就绪通知**：fd 可读了 | **完成通知**：IO 已经做完了 |
| 谁执行 IO | 用户代码自己调 read/write | 内核/OS 执行（提前给定 buffer） |
| 用户回调时机 | 就绪后、读之前挂回调，回调里先 read 再处理 | 完成后挂回调，回调里数据已在 buffer，直接处理 |
| 典型接口 | epoll_wait → read → handle | 提交（buffer 交给内核）→ 等完成 → handle |
| 错误处理 | read 返回值当场看 | 结果在 CQE 的 res / 完成包里异步回来 |
| 适配异步磁盘 | 不行（就绪概念对文件无意义） | 天然支持 |

### 5.2 为什么 io_uring 与 IOCP 是 Proactor

用户提交 READ 请求时就把**接收缓冲区的指针和长度**交给了内核（SQE 的 addr/len）；内核把数据**搬完**才产出 CQE（res = 字节数）。也就是说"IO 动作本身由内核完成，用户拿到的是结果"——这正是 Proactor 的定义。epoll 则相反：它只报"可读"，搬数据这件事仍由用户的 read 完成。

一句话总结：**Reactor 等待的是"可以做"，Proactor 等待的是"已经做完"。**

## 6. Windows IOCP

### 6.1 完成端口工作机制

| 组件 | API | 作用 |
|---|---|---|
| 完成端口对象 | CreateIoCompletionPort | 创建（首次传 INVALID_HANDLE_VALUE）并把 socket 与端口关联（传 key 标识连接） |
| 发起异步 IO | WSARecv / WSASend + OVERLAPPED | 立即返回（WSA_IO_PENDING），完成后完成包入队 |
| 取完成包 | GetQueuedCompletionStatus | worker 线程阻塞等待：拿到 (bytes, key, OVERLAPPED*) |
| 手工投递 | PostQueuedCompletionStatus | 人为塞完成包（常用于通知 worker 退出） |

worker 线程模型图：

```text
+----------------+      +----------------------+      +---------------------+
| 主线程          |      |   完成端口(IOCP)      |      |  worker 线程池       |
| WSARecv 投递 ──┼─────►│  完成队列(FIFO)       │─────┼─► GQCS 阻塞等待      |
| (带OVERLAPPED)  |      │  并发度控制唤醒数量    │      │  处理→再投递下一个IO │
+----------------+      +----------------------+      +---------------------+
                          key = 连接标识, OVERLAPPED 里带本次 IO 的上下文
```

### 6.2 并发度概念

`CreateIoCompletionPort(..., NumberOfConcurrentThreads)` 的第四参数是**并发度**：完成端口尽量让不超过 N 个 worker 同时运行。

| 问题 | 答案 |
|---|---|
| 并发度设多少 | 通常 0（=CPU 核数）；IO 密集可略高 |
| 线程数必须等于 N 吗 | 不必，通常开 2×N：某 worker 阻塞在数据库/磁盘时，端口会放行下一个等待者顶上 |
| 并发度存在的意义 | 防止过多线程同时跑导致上下文切换与锁竞争反噬吞吐 |

### 6.3 重叠 IO（Overlapped IO）

```cpp
struct PER_IO_DATA {                 // 每次投递的上下文, 首成员必须是 OVERLAPPED
    OVERLAPPED ov{};                 // 内核回填完成状态
    int op;                          // RECV / SEND
    WSABUF wsabuf;                   // 指向数据的 {len, buf}
};
// 发起异步收: 第四参 recvbytes 无意义, 由重叠机制完成
DWORD flags = 0, n = 0;
int r = WSARecv(sock, &per->wsabuf, 1, &n, &flags, &per->ov, nullptr);
// r==SOCKET_ERROR && WSAGetLastError()==WSA_IO_PENDING → 正常, 等完成包
```

要点：OVERLAPPED 是"本次 IO 的凭证"，完成包回来时返回同一个指针；工程上总是把 OVERLAPPED 嵌在自定义结构首部（Rust 里的"继承式扩展"），据此还原是哪个连接的哪次操作——与 io_uring 的 user_data 完全同构。

### 6.4 IOCP 处理连接与收发的流程

| 步骤 | 动作 |
|---|---|
| 1 | accept（阻塞或 AcceptEx 异步）得到 client socket，CreateIoCompletionPort 关联到端口，key=连接指针 |
| 2 | 为连接投递首个 WSARecv（附 PER_IO_DATA） |
| 3 | worker 被 GQCS 唤醒：bytes=收到的字节数，key=连接，ov=本次操作上下文 |
| 4 | 处理数据 → 投递 WSASend 回写 → 再投递下一个 WSARecv |
| 5 | bytes==0 → 对端关闭 → 关 socket、回收连接对象 |

### 6.5 IOCP vs io_uring 对比

| 维度 | IOCP | io_uring |
|---|---|---|
| 平台 | Windows | Linux 5.1+ |
| 请求提交 | WSARecv/WSASend 等分散 API，每次一个 | SQE 环 + 批量 enter（或 SQPOLL 零 syscall） |
| 完成通知 | 完成队列 + 线程池唤醒 | CQ 环（共享内存，无唤醒开销读取） |
| 覆盖范围 | 网络 + 文件异步 | 网络 + 文件 + 定时器 + 大量文件系统操作 |
| 编程模型 | 面向句柄的回调风格 | 面向环的事件流 |
| 生态 | 成熟三十年 | 快速演进中 |

## 7. 跨平台抽象层设计

### 7.1 统一接口思路

```text
            +-----------------------------+
            |   统一连接对象 Conn          |
            |   (fd/handle, buffer, cb)   |
            +-----------------------------+
              | 适配器模式                  |
   +----------+-----------+-----------------+
   | ReactorAdapter        | ProactorAdapter |
   | Linux: epoll          | Linux: io_uring  |
   | 通用: select/poll     | Windows: IOCP    |
   +-----------------------+------------------+
```

| 设计点 | 做法 |
|---|---|
| IO 完成/就绪统一化 | Reactor 适配层在就绪回调里自动 read 再调完成回调，向上一层伪装成 Proactor（libuv 的思路） |
| 回调编码 | 连接指针放 key/user_data；操作类型放扩展结构首字段（PER_IO_DATA 或 user_data 高位） |
| 缓冲策略 | 连接对象持有接收缓冲，适配层负责"读到缓冲/通知缓冲已有数据"的差异抹平 |

### 7.2 开源库一览

| 库 | 定位 | 平台策略 |
|---|---|---|
| libuv | Node.js 底座 | Windows 用 IOCP、Linux 用 epoll，上层统一成 Proactor 风格 |
| asio | C++ 标准网络库候选 | 设计即 Proactor；Linux 上可选用 io_uring 后端 |
| glacio | 新兴 io_uring 原生 C++ 异步库 | 面向新内核直接吃 io_uring 红利 |

## 8. 快速参考卡片

| 要点 | 一句话 |
|---|---|
| 三个 syscall | setup 建环 / register 预注册资源 / enter 提交+收割 |
| 双环共享内存 | SQ/CQ 都 mmap，用户与内核只靠 head/tail 交接 |
| 屏障铁律 | 写数据→release 更新 tail；读 tail 用 acquire，再看数据 |
| SQE 三关键字段 | opcode、fd+addr/len、user_data（回程票） |
| CQE 三字段 | user_data、res（≥0 成功/-errno）、flags |
| SQ 间接索引 | 环存下标不存 SQE：槽位乱填、顺序由环定、槽位免搬移复用 |
| liburing 六步 | queue_init → get_sqe → prep_xxx → submit → wait_cqe → cqe_seen |
| SQPOLL | 内核线程轮询 SQ，用户态零 syscall，代价是空转烧 CPU |
| register | 固定缓冲区/固定文件表，省每 IO 的 pin 与 fget 开销 |
| multishot | 一个 SQE 多次完成（accept 5.19+ / recv 6.0+），看 CQE_F_MORE |
| Proactor 判据 | 内核完成 IO 才通知；epoll 是就绪通知（Reactor） |
| IOCP 四件套 | CreateIoCompletionPort / WSARecv+OVERLAPPED / GQCS / PostQueued |
| IOCP 并发度 | NumberOfConcurrentThreads，线程池可开 2×N 顶阻塞 |
| 版本口径 | 5.1 引入，5.10 起可生产，5.15 推荐基线，越新越全 |

## 9. 常见问题与坑

| 坑 | 现象 | 正解 |
|---|---|---|
| 填了 SQE 忘记 submit | 永远等不到 CQE，wait 卡死 | 每次 get_sqe + prep 后必须 submit；最好统一在循环末尾 submit |
| CQE 收割后不 cqe_seen / cq_advance | cq_head 不动，CQ 环写满后内核侧被阻塞（新完成进不来） | 每条处理完立即 seen；批量收割用 cq_advance |
| SQPOLL 空转 | 空闲时内核线程 100% CPU | 配置 sq_thread_idle 让其休眠；业务空闲期用 SQ_WAKEUP 唤醒 |
| multishot 重复注册 | 连接事件风暴、fd 泄漏 | 识别 res<0 的终止 CQE；已注册的不再注册，用 ASYNC_CANCEL 取消 |
| user_data 没编码连接信息 | CQE 回来不知道是谁的事件 | 编码 (op<<32 \| conn_idx)；或用指针做 data（注意生命周期） |
| 老内核跑新特性 | 运行时 -EINVAL/-ENOSYS | 用 io_uring_probe 运行时探测 opcode；文档注明最低内核版本 |
| res 语义搞错 | 把 -errno 当字节数用 | 统一宏：`res >= 0` 成功；磁盘读 0 才是 EOF，recv 0 是对端关闭 |
| 对阻塞 fd 期望立即返回 | 语义混乱偶发阻塞 | io_uring 场景统一用非阻塞 fd，让内核强制走异步路径 |
| SQ 满还硬塞 SQE | get_sqe 返回 NULL 解引用崩溃 | 判空；必要时先 submit 腾槽再继续填 |
| 链接/排空标志乱用 | 顺序错乱或意外串行 | IOSQE_IO_LINK 严格两两链接；跨批次的链依赖内核版本，谨慎使用 |
| 注册缓冲后用普通 read/write | 多余 pin、性能不升反降 | 固定缓冲必须配 READ_FIXED/WRITE_FIXED |
| Windows 下忽略 WSA_IO_PENDING | 把正常 pending 当错误关连接 | SOCKET_ERROR + WSA_IO_PENDING 是"已受理"，等完成包即可 |
| IOCP 线程数=并发度拍脑袋 | 频繁上下文切换吞吐反降 | 默认并发度=核数，线程池 2×N；实测调整 |
| io_uring 当银弹 | 简单业务改造后没提升还引入复杂度 | 高并发短 IO/磁盘异步/SQPOLL 低延迟才显著；通用长连接服务 epoll 足矣 |

---

上一篇：《01-协程框架原理与实现.md》
下一篇：《03-用户态协议栈与DPDK.md》
