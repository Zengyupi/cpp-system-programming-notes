# Reactor与高性能网络库

> 本节目标：从"会用 epoll"进阶到"能写网络库"——深入 epoll 内核结构（红黑树+就绪链表+回调）与 ET/LT 内核行为差异，掌握 Reactor 三形态取舍，手撕单 Reactor 回显框架（channel/event_loop/tcp_conn 分层、EPOLLOUT 按需注册、非阻塞收发、统一关闭出口），实现 HTTP 逐字节状态机解析，理解 one loop per thread 无锁设计与跨线程唤醒。前置《01-网络基础与TCP-IP.md》（Socket 与 epoll 基础）、《03-高性能服务器设计.md》（并发模型总纲），关联《02-百万并发与TCP栈优化.md》（内核调优）、《../13-并发异步与组件/01-协程框架原理与实现.md》（回调的同步化替代）、《../13-并发异步与组件/07-原子操作与无锁组件.md》（无锁缓冲区）。 课程模块 2.1：网络 IO 与 IO 多路复用 / 事件驱动 Reactor 的原理与实现 / HTTP 服务器的实现 / 异步网络库。本篇讲**框架设计与封装**，socket/tcp 基础 API 与 epoll 基本用法见 `../03-计算机网络编程/02-IO多路复用与Reactor模型.md`；线程池与同步原语见 `../04-并发与多线程编程/01-并发编程与线程同步.md`；缓冲区的无锁改造见 `13-原子操作与无锁组件.md`；百万并发调参见 `04-百万并发与TCP栈优化.md`。

## 本章速览

- [1. 概述](#1-概述)
  - [1.1 从 echo server 到网络库的演进](#11-从-echo-server-到网络库的演进)
  - [1.2 本篇与外层笔记的分工](#12-本篇与外层笔记的分工)
- [2. IO 多路复用再深入](#2-io-多路复用再深入)
  - [2.1 select / poll / epoll 回顾](#21-select--poll--epoll-回顾)
  - [2.2 内核视角：epoll 为什么快【高频】](#22-内核视角epoll-为什么快高频)
  - [2.3 ET / LT 内核行为差异【高频】](#23-et--lt-内核行为差异高频)
  - [2.4 EPOLLONESHOT](#24-epolloneshot)
- [3. Reactor 模式](#3-reactor-模式)
  - [3.1 定义](#31-定义)
  - [3.2 三种形态【高频】](#32-三种形态高频)
  - [3.3 Reactor 相对"每连接一线程"的优点](#33-reactor-相对每连接一线程的优点)
  - [3.4 名项目网络组件对照](#34-名项目网络组件对照)
- [4. 手撕 Reactor【核心】](#4-手撕-reactor核心)
  - [4.1 分层结构](#41-分层结构)
  - [4.2 完整精简版代码（单 Reactor，epoll 版）](#42-完整精简版代码单-reactorepoll-版)
  - [4.3 跨平台封装思路](#43-跨平台封装思路)
- [5. 网络缓冲区](#5-网络缓冲区)
  - [5.1 为什么必须有应用层 recvbuf / sendbuf](#51-为什么必须有应用层-recvbuf--sendbuf)
  - [5.2 设计要点（指引）](#52-设计要点指引)
- [6. HTTP 服务器实现](#6-http-服务器实现)
  - [6.1 协议格式](#61-协议格式)
  - [6.2 有限状态机解析 HTTP【高频】](#62-有限状态机解析-http高频)
  - [6.3 响应组装](#63-响应组装)
  - [6.4 WebSocket 握手与 TCP 文件传输（简表）](#64-websocket-握手与-tcp-文件传输简表)
- [7. 异步网络库设计](#7-异步网络库设计)
  - [7.1 同步处理与异步处理的数据差异](#71-同步处理与异步处理的数据差异)
  - [7.2 网络 IO 线程池：one loop per thread【高频】](#72-网络-io-线程池one-loop-per-thread高频)
  - [7.3 业界参考](#73-业界参考)
- [8. 快速参考卡片](#8-快速参考卡片)
- [9. 常见问题与坑](#9-常见问题与坑)

---

## 1. 概述

### 1.1 从 echo server 到网络库的演进

| 阶段 | 模型 | 问题 |
|---|---|---|
| 1. echo | 单线程 accept→recv→send 循环 | 一次只能服务一个连接 |
| 2. 多进程/每连接一线程 | accept 后 fork / pthread_create | 千级连接后线程爆炸：内存 + 上下文切换风暴 |
| 3. select/poll + 单线程 | 一个线程监听所有 fd | fd 数量上限/每次全量拷贝、全量遍历 |
| 4. epoll + 事件回调 = Reactor | 就绪事件驱动，回调处理 | 复杂度上来了 → 需要框架封装 |
| 5. 网络库 | Reactor + 缓冲区 + 连接管理 + 线程池 | 业务只写"数据到达后干什么" |

### 1.2 本篇与外层笔记的分工

| 主题 | `../03-计算机网络编程/02-IO多路复用与Reactor模型.md` | 本篇 |
|---|---|---|
| socket API | socket/bind/listen/accept/connect 全解 | 直接使用 |
| epoll | 三接口基本用法、LT 语义 | 内核数据结构、ET/LT 内核行为差异、EPOLLONESHOT、框架化封装 |
| 并发模型 | 线程/进程基础 | Reactor 三形态、one loop per thread |

## 2. IO 多路复用再深入

### 2.1 select / poll / epoll 回顾

| 对比项 | select | poll | epoll |
|---|---|---|---|
| fd 上限 | FD_SETSIZE 默认 1024 | 无硬上限 | 无硬上限（受 fd 限制） |
| fd 传递 | 每次全量拷贝进内核 | 同左 | 注册一次（epoll_ctl），之后内核持有 |
| 就绪检测 | 内核线性扫 + 用户再线性扫 | 同左 | 回调驱动，只返回就绪的 |
| 复杂度 | O(n) 每次调用 | O(n) | O(1)（相对活跃连接数） |
| 跨平台 | 全平台 | 类 Unix | Linux（BSD 用 kqueue） |

### 2.2 内核视角：epoll 为什么快【高频】

`epoll_create1()` 在内核创建 `struct eventpoll`，核心两件套：

```cpp
struct eventpoll {
    struct rb_root_cached rbr;      /* 红黑树: 管理所有注册的 fd(键=fd+file) */
    struct list_head      rdllist;  /* 就绪链表: 已发生事件的 epitem */
    struct wait_queue_head wq;      /* epoll_wait 在此睡眠 */
};

事件到达路径:
  网卡收到数据 → 协议栈处理 → socket 收包 → 唤醒该 socket 等待队列上的回调
  → ep_poll_callback(epoll 注册时挂上的) → 把对应 epitem 挂入 rdllist
  → 唤醒 epoll_wait 的睡眠 → 拷贝就绪列表给用户

对比: select 每次"把全部 fd 塞进内核逐个查", epoll 是"注册一次 + 事件回调主动上报"。
```

| 机制 | 说明 | 收益 |
|---|---|---|
| 红黑树管理注册 fd | epoll_ctl ADD/DEL/MOD 即树上增删改 | 重复注册去重，增删 O(log n) |
| 就绪链表 rdllist | 回调把就绪 epitem 挂链（判重：已挂则不重复） | epoll_wait 只处理就绪的，与总连接数无关 |
| 回调 ep_poll_callback | 注册时挂到 socket 的等待队列 | 数据到 → 内核主动"推"，不用轮询 |
| 等待队列 wq | epoll_wait 没事件则睡眠 | 无忙等 |

### 2.3 ET / LT 内核行为差异【高频】

| 模式 | 上报时机 | 用户约定 | 适用 |
|---|---|---|---|
| LT 水平触发 | 缓冲区**还有**未读数据就每次 wait 都报 | 一次不必读完 | 默认，容错好 |
| ET 边沿触发 | 仅状态**从无到有**（新数据到达）时报一次 | 必须**循环读到 EAGAIN**，且 fd 必须非阻塞 | 高吞吐，减少事件次数 |

内核行为：`ep_poll_callback` 里 ET 只在"加入时队列为空（首次）"有意义地触发一次；LT 则只要 rdllist 里有该 epitem 且 socket 仍有数据，每次 epoll_wait 都会返回它。ET 省了重复上报，代价是漏读一次就再也等不到通知（直到新数据到来），所以必须一次排空。

### 2.4 EPOLLONESHOT

| 场景 | 问题 | EPOLLONESHOT 行为 |
|---|---|---|
| 多线程 Reactor，两个线程都在 epoll_wait 同一 epfd 处理同一 fd | 同一连接的两个事件被分给两个线程并发处理 → 竞争 | 事件**只触发一次**，触发后 fd 自动被屏蔽，必须 `EPOLL_CTL_MOD` 重新武装 |

用途一句话：**让同一连接的多个事件串行化到一个线程**。muduo 用"每线程独立 loop"从结构上规避了这个问题，EPOLLONESHOT 是单 epfd 多线程方案的补丁。

## 3. Reactor 模式

### 3.1 定义

Reactor（反应器）= **IO 事件的多路分发器**：一个事件循环阻塞在 epoll_wait 上，事件到达后**分发给对应的回调**处理；所有 IO 都是非阻塞的，业务逻辑写进回调。别名：Dispatcher / Notifier（Observer 模式在 IO 上的应用）。

### 3.2 三种形态【高频】

| 形态 | 结构 | 优点 | 缺点 | 代表 |
|---|---|---|---|---|
| 单 Reactor 单线程 | acceptor + IO + 业务全在一个线程 | 无锁、无竞争、实现简单 | 一个回调卡全卡；不利用多核 | Redis 6.0 前 |
| 单 Reactor 多线程 | Reactor 只做 IO 事件分发，业务逻辑丢线程池 | 业务耗时不再卡 IO | 单 Reactor 是吞吐上限（epoll_wait+分发集中一个核） | 课程教学版 |
| 主从 Reactor 多线程 | 主 Reactor 只管 accept；从 Reactor 各管一批连接的 IO | accept 与 IO 分离，IO 横向扩展 | 实现与连接迁移复杂 | muduo / Netty |

```text
形态1: 单Reactor单线程              形态3: 主从Reactor(Redis 6.0/muduo/netty)
 ┌──────────────────┐               ┌─────────┐
 │  Reactor 线程     │               │ mainReactor(acceptor)      │
 │  epoll_wait       │               │  epoll 只挂 listenfd        │
 │   ├─ accept()     │               │   └─ accept → 派发 connfd   │
 │   ├─ recv() + 业务 │               │        │ (轮询/最少连接)      │
 │   └─ send()       │               │        ▼                   │
 └──────────────────┘               │ subReactor-1  subReactor-2 …│
                                    │ epoll+conn集    epoll+conn集 │
                                    │  ├─ recv         ├─ recv     │
                                    │  └─ send         └─ send     │
                                    │ (业务可再丢线程池)             │
                                    └────────────────────────────┘
```

### 3.3 Reactor 相对"每连接一线程"的优点

| 维度 | 每连接一线程 | Reactor |
|---|---|---|
| 线程数 | = 连接数（10 万连接 10 万线程） | = CPU 核数级别，可控 |
| 上下文切换 | 高并发下切换风暴（每次 μs 级） | 只在事件处理间切换，量级极小 |
| 内存 | 每线程默认 8MB 栈（虚拟内存） | 少量固定线程 + 每连接一个 conn 结构 |
| 阻塞模型 | 阻塞 IO，直观好写 | 非阻塞 + 回调，编码复杂 |
| 缓存友好 | 差（线程分散） | 好（单线程内连续处理） |
| 编程模型 | 同步顺序 | 事件驱动"状态机"思维 |

### 3.4 名项目网络组件对照

| 项目 | 网络模型 | 细节 |
|---|---|---|
| Redis 6.0 前 | 单 Reactor 单线程 | 所有命令在一个线程执行，避免锁 |
| Redis 6.0+ | 主从多 IO 线程 | 读协议/回包并行，命令执行仍单线程 |
| memcached | 主线程 accept + 分发（pipe 通知）到 worker 线程，每 worker 一个 event_base | 主从多线程变体 |
| nginx | master/worker 多进程，每 worker 单 Reactor（epoll），accept 用锁或 SO_REUSEPORT 防惊群 | 进程级隔离，worker 数=核数 |
| muduo | 主从 Reactor + 线程池（one loop per thread） | 本篇 4.2 代码的 C++ 工程化版本 |

## 4. 手撕 Reactor【核心】

### 4.1 分层结构

```text
┌────────────────────────────────────────────┐
│ 业务层: on_msg(完整报文) / on_close           │  ← 业务层只需实现这层
├────────────────────────────────────────────┤
│ tcp_conn: 连接对象 + recvbuf/sendbuf        │  ← 半包拼装/发送缓冲
├────────────────────────────────────────────┤
│ channel: fd + events + read/write/error回调 │  ← 事件与处理器的绑定
├────────────────────────────────────────────┤
│ event_loop(epoll dispatcher): epoll 三接口  │  ← poll/update 分发
│   ├─ acceptor(listenfd → accept_cb)         │
│   └─ timerfd/signalfd(可扩展)               │
├────────────────────────────────────────────┤
│ epoll(内核)                                  │
└────────────────────────────────────────────┘
```

### 4.2 完整精简版代码（单 Reactor，epoll 版）

```c
/* reactor.c —— 单 Reactor 事件驱动框架精简版（回显服务）
 * 编译: gcc -Wall -o reactor reactor.c
 * 测试: ./reactor 8888 ，另开 telnet 127.0.0.1 8888 输入任意字符回显
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <sys/epoll.h>

#define BUF_LEN    4096
#define MAX_EVENTS 1024
#define MAX_FD     65536

/* ========== 1. channel: fd + 关注事件 + 三类回调 ========== */
typedef int (*event_cb)(int fd, int events, void *priv);

typedef struct _channel {
    int       fd;
    int       events;                 /* 当前注册事件: EPOLLIN | EPOLLOUT */
    event_cb  read_cb;                /* fd 可读 */
    event_cb  write_cb;               /* fd 可写 */
    event_cb  error_cb;               /* EPOLLERR/EPOLLHUP/对端关闭 */
    void     *data;                   /* 回调私有数据(所属连接) */
} channel_t;

struct event_loop;

/* ========== 2. tcp_conn: 一条连接 = channel + 应用层缓冲 ========== */
typedef struct _tcp_conn {
    channel_t chan;
    struct event_loop *loop;          /* 回指调度器(更新注册用) */
    char recvbuf[BUF_LEN];  int rlen; /* 收: 边收边拼半包 */
    char sendbuf[BUF_LEN];  int slen; /* 发: slen==0 才注销 EPOLLOUT */
} tcp_conn_t;

/* ========== 3. event_loop: epoll 封装 + fd→channel 表 ========== */
typedef struct event_loop {
    int        epfd;
    channel_t *chans[MAX_FD];         /* fd 下标直接索引(教学用,生产换hash) */
} event_loop_t;

static int set_nonblock(int fd) {
    int fl = fcntl(fd, F_GETFL, 0);
    return fcntl(fd, F_SETFL, fl | O_NONBLOCK);
}

/* 更新注册: chan->events==0 表示注销; 否则 ADD 或 MOD */
static int loop_update(event_loop_t *loop, channel_t *chan) {
    struct epoll_event ev;
    memset(&ev, 0, sizeof(ev));
    ev.data.ptr = chan;                          /* 事件发生时带回 channel */
    ev.events   = chan->events;
    if (chan->events) {
        int op = loop->chans[chan->fd] ? EPOLL_CTL_MOD : EPOLL_CTL_ADD;
        if (epoll_ctl(loop->epfd, op, chan->fd, &ev) < 0) {
            perror("epoll_ctl"); return -1;
        }
    } else {                                     /* 注销 */
        epoll_ctl(loop->epfd, EPOLL_CTL_DEL, chan->fd, NULL);
    }
    loop->chans[chan->fd] = chan->events ? chan : NULL;
    return 0;
}

/* ========== 4. 事件循环主体: 等待 → 分发 ========== */
static int loop_run(event_loop_t *loop) {
    struct epoll_event evs[MAX_EVENTS];
    while (1) {
        int n = epoll_wait(loop->epfd, evs, MAX_EVENTS, -1);
        if (n < 0) {
            if (errno == EINTR) continue;        /* 被信号打断,重来 */
            perror("epoll_wait"); return -1;
        }
        for (int i = 0; i < n; i++) {
            channel_t *chan = evs[i].data.ptr;
            uint32_t   e    = evs[i].events;
            if (e & (EPOLLHUP | EPOLLERR)) {     /* 错误优先处理 */
                if (chan->error_cb) chan->error_cb(chan->fd, e, chan->data);
                continue;
            }
            int fd = chan->fd;                    /* 先存 fd: 回调可能释放 chan */
            if ((e & EPOLLIN)  && chan->read_cb)  /* 可读 */
                chan->read_cb(fd, e, chan->data);
            /* 读回调里可能已 close_cb 释放连接 → 用注册表校验再分发写事件 */
            if ((e & EPOLLOUT) && loop->chans[fd] == chan && chan->write_cb)
                chan->write_cb(fd, e, chan->data);
        }
    }
    return 0;
}

/* ========== 5. 关闭连接: 统一出口, 防 double free ========== */
static int close_cb(int fd, int events, void *priv) {
    (void)events;
    tcp_conn_t *conn = (tcp_conn_t *)priv;
    event_loop_t *loop = conn->loop;
    epoll_ctl(loop->epfd, EPOLL_CTL_DEL, fd, NULL);  /* 先摘注册 */
    loop->chans[fd] = NULL;
    close(fd);
    free(conn);                                      /* 连接对象唯一释放点 */
    return 0;
}

/* recv_cb/send_cb 定义在下方, 先前置声明给 accept_cb 用 */
static int recv_cb(int fd, int events, void *priv);
static int send_cb(int fd, int events, void *priv);

/* ========== 6. accept: 新连接入册 ========== */
static int accept_cb(int lfd, int events, void *priv) {
    event_loop_t *loop = (event_loop_t *)priv;
    (void)events;
    struct sockaddr_in cli; socklen_t len = sizeof(cli);
    int cfd = accept(lfd, (struct sockaddr *)&cli, &len);
    if (cfd < 0) {
        if (errno == EAGAIN || errno == EWOULDBLOCK) return 0; /* 理论少见 */
        perror("accept"); return -1;
    }
    set_nonblock(cfd);                          /* Reactor 的 fd 一律非阻塞 */

    tcp_conn_t *conn = calloc(1, sizeof(tcp_conn_t));
    conn->loop = loop;
    conn->chan.fd      = cfd;
    conn->chan.events  = EPOLLIN;               /* 新连接先只关心读 */
    conn->chan.read_cb = recv_cb;
    conn->chan.write_cb= send_cb;
    conn->chan.error_cb= close_cb;
    conn->chan.data    = conn;
    loop_update(loop, &conn->chan);
    printf("new conn fd=%d\n", cfd);
    return cfd;
}

/* ========== 7. 读: 收数据 → 业务 → 转写 ========== */
static int recv_cb(int fd, int events, void *priv) {
    tcp_conn_t *conn = (tcp_conn_t *)priv;

    int n = recv(fd, conn->recvbuf, BUF_LEN - 1, 0);
    if (n < 0) {
        if (errno == EAGAIN || errno == EWOULDBLOCK) return 0; /* 本轮读空 */
        if (errno == EINTR) return 0;
        return close_cb(fd, events, priv);      /* 真错误: 统一关闭 */
    }
    if (n == 0)                                 /* 返回0 = 对端正常关闭 */
        return close_cb(fd, events, priv);

    conn->rlen = n; conn->recvbuf[n] = '\0';
    /* ★ 业务层接入点: 这里应做协议解析/半包拼装(见第6章 FSM)。
       教学版直接回显: 收到什么就回什么 */
    memcpy(conn->sendbuf, conn->recvbuf, n);
    conn->slen = n;

    conn->chan.events |= EPOLLOUT;              /* 有数据待发 → 注册可写 */
    return loop_update(conn->loop, &conn->chan);
}

/* ========== 8. 写: 尽力写, 没写完留缓冲, 写完注销 ========== */
static int send_cb(int fd, int events, void *priv) {
    tcp_conn_t *conn = (tcp_conn_t *)priv;

    int n = send(fd, conn->sendbuf, conn->slen, MSG_NOSIGNAL);
    if (n < 0) {
        if (errno == EAGAIN || errno == EWOULDBLOCK) return 0; /* 内核发送缓冲满 */
        return close_cb(fd, events, priv);
    }
    if (n < conn->slen) {                       /* 只发了一部分 */
        memmove(conn->sendbuf, conn->sendbuf + n, conn->slen - n);
        conn->slen -= n;                        /* 剩余数据留在发送缓冲 */
        return n;                               /* 保持 EPOLLOUT, 下次继续 */
    }
    conn->slen = 0;                             /* 全部发完 */
    conn->chan.events &= ~EPOLLOUT;             /* ★ 按需注销, 否则可写死循环 */
    return loop_update(conn->loop, &conn->chan);
}

/* ========== 9. main: 监听 + 启动循环 ========== */
int main(int argc, char *argv[]) {
    int port = argc > 1 ? atoi(argv[1]) : 8888;

    event_loop_t loop;
    loop.epfd = epoll_create1(0);
    memset(loop.chans, 0, sizeof(loop.chans));

    int lfd = socket(AF_INET, SOCK_STREAM, 0);
    int on = 1;
    setsockopt(lfd, SOL_SOCKET, SO_REUSEADDR, &on, sizeof(on));
    struct sockaddr_in serv;
    memset(&serv, 0, sizeof(serv));
    serv.sin_family      = AF_INET;
    serv.sin_addr.s_addr = htonl(INADDR_ANY);
    serv.sin_port        = htons(port);
    bind(lfd, (struct sockaddr *)&serv, sizeof(serv));
    listen(lfd, 512);                    /* backlog 见 04-百万并发与TCP栈优化 详解 */
    set_nonblock(lfd);

    channel_t lchan;
    memset(&lchan, 0, sizeof(lchan));
    lchan.fd      = lfd;
    lchan.events  = EPOLLIN;
    lchan.read_cb = accept_cb;           /* listenfd 的"读"= 有新连接 */
    lchan.data    = &loop;
    loop_update(&loop, &lchan);

    return loop_run(&loop);              /* 事件循环永不返回 */
}
```

注：教学版每事件一次 recv/send；生产版会**循环收发直到 EAGAIN**，并配合 ET 模式。代码要点自检表：

| 要点 | 在代码哪里 | 为什么 |
|---|---|---|
| 非阻塞 fd | accept_cb 的 set_nonblock | Reactor 前提，配合 EAGAIN 判断 |
| 回调携带私有数据 | ev.data.ptr = chan，chan->data = conn | 事件发生时找回"这是谁" |
| 先 DEL 再 free | close_cb | 防 use-after-free（事件里还挂着野指针） |
| EPOLLOUT 按需注册 | recv_cb 打开、send_cb 写完关掉 | socket 缓冲区常年可写，常开=忙轮询 |
| EAGAIN 不是错误 | recv_cb/send_cb | 非阻塞语义的正常分支 |
| recv 返回 0 = 关闭 | recv_cb | 对端 FIN |

### 4.3 跨平台封装思路

把"等待事件 + 增改注册"抽象成 dispatcher 接口，编译期选择实现（libevent/sylar 同款思路）：

```c
/* dispatcher.h —— epoll/select/kqueue 统一抽象 */
typedef struct _dispatcher {
    const char *name;                                   /* "epoll"/"select" */
    int  (*init)    (event_loop_t *loop);               /* 创建内核对象 */
    int  (*poll)    (event_loop_t *loop, int timeout);  /* 等待+分发一次 */
    int  (*update)  (event_loop_t *loop, channel_t *c); /* 注册/修改/注销 */
    void (*destroy) (event_loop_t *loop);
} dispatcher_t;

#if   defined(__linux__)                 /* epoll 实现: 4.2 节拆出来即可 */
extern dispatcher_t epoll_dispatcher;
#elif defined(__APPLE__) || defined(__FreeBSD__)
extern dispatcher_t kqueue_dispatcher;   /* kqueue: EV_ADD/EV_DELETE/EV_ENABLE */
#else
extern dispatcher_t select_dispatcher;   /* select: FD_SET/FD_ZERO, 1024 上限 */
#endif

/* event_loop 持有: struct event_loop { dispatcher_t *dp; void *dp_priv; ... }; */
```

## 5. 网络缓冲区

### 5.1 为什么必须有应用层 recvbuf / sendbuf

| 缓冲 | 解决的问题 | 细节 |
|---|---|---|
| recvbuf | TCP 是**字节流没有消息边界**：一次 recv 可能收到半条/多条报文 | 收进 recvbuf，FSM 判断"够不够一条完整报文"，够了才交业务；不够留着等下次 |
| sendbuf | 非阻塞 send 可能**只写出一部分**（内核 socket 发送缓冲满） | 没写完的存 sendbuf 等下次 EPOLLOUT；**EPOLLOUT 触发条件 = 内核发送缓冲由满变有空闲** |

```text
EPOLLOUT 的正确姿势:
   sendbuf 非空 → 注册 EPOLLOUT → 事件来 → 写完/写不动 → sendbuf 空 → 注销 EPOLLOUT
   (内核缓冲区常态可写: 若常开 EPOLLOUT, epoll_wait 每次立刻返回 → CPU 100% 忙轮询)
```

### 5.2 设计要点（指引）

| 要点 | 方案 |
|---|---|
| 环形 or 线性 | muduo Buffer：`vector<char>` + reader/writer 下标，预留 8 字节头写长度；扩容 resize |
| 装配完整报文 | 读长度字段（TLV/HTTP Content-Length）→ 收够才解析 |
| 防膨胀 | sendbuf 设高水位（如 64MB），超了停止读对端（背压 backpressure），甚至断开 |
| 跨线程 | IO 线程只碰 buffer；业务线程通过任务队列投递（或 one loop per thread 干脆不跨线程），无锁化改造见 `13-原子操作与无锁组件.md` |

## 6. HTTP 服务器实现

### 6.1 协议格式

```text
请求(GET):
 +----------------+-----------------------------------+
 | GET /index.html HTTP/1.1\r\n        ← 请求行: 方法 URL 版本
 | Host: 127.0.0.1:8888\r\n            ← 请求头(0..n 行): k: v
 | Connection: keep-alive\r\n          |
 | \r\n                                ← 空行 = 头结束
 +----------------+-----------------------------------+
 | (GET 无包体)                                          |

请求(POST): 头部同上, 空行后跟包体:
 | POST /login HTTP/1.1\r\n
 | Content-Type: application/x-www-form-urlencoded\r\n
 | Content-Length: 27\r\n
 | \r\n
 | username=nty&password=123          ← 包体, 长度由 Content-Length 决定
```

| 部分 | 分隔规则 | 解析要点 |
|---|---|---|
| 请求行 | 空格分 3 段，行尾 \r\n | method / url / version 三元组 |
| 请求头 | 每行 `k: v\r\n`，冒号后可有空格 | 大小写不敏感（Content-Length/content-length 等价） |
| 空行 | `\r\n` | 头与体的分界 |
| 包体 | GET 一般无；POST 长度 = Content-Length | 长度未知才用 chunked（本篇不展开） |

### 6.2 有限状态机解析 HTTP【高频】

为什么逐字节状态机：①recv 到的数据可能**只有半条**（分包），状态机天然可"喂一个字节走一步"地增量解析；②粘包时解析完一条，剩余字节留给下一条；③坏输入只会卡在错误状态，不会内存越界。

```text
状态: PARSE_LINE → PARSE_HEADER → (有Content-Length?) → PARSE_BODY → PARSE_DONE
        │请求行            │逐行读k:v          │逐字节          │
        └──────\r\n 整行────┘空行结束            └────收满 len ────┘
```

```c
/* http_parser.c —— HTTP 请求逐字节 FSM */
#include <stdio.h>
#include <string.h>
#include <strings.h>          /* strcasecmp */
#include <ctype.h>

enum { PARSE_LINE = 0, PARSE_HEADER, PARSE_BODY, PARSE_DONE, PARSE_ERROR };

#define LINE_LEN 2048
typedef struct {
    int  state;                            /* 当前状态 */
    char line[LINE_LEN]; int llen;         /* 行缓冲(拼当前行) */
    char method[16], url[256], version[16];
    char key[64], val[256];                /* 当前头部字段 */
    int  content_len;                      /* Content-Length */
    char body[4096]; int body_len;
} http_req_t;

void http_req_init(http_req_t *r) { memset(r, 0, sizeof(*r)); r->state = PARSE_LINE; }

/* 喂入一个字节; 返回当前状态。调用方循环喂到 PARSE_DONE/PARSE_ERROR */
int http_parse_char(http_req_t *r, char c) {
    switch (r->state) {
    case PARSE_LINE:
    case PARSE_HEADER:
        if (c != '\n') {                   /* 行未结束: 累积(\r 丢弃) */
            if (c != '\r' && r->llen < LINE_LEN - 1)
                r->line[r->llen++] = c;
            break;
        }
        r->line[r->llen] = '\0';           /* 一行到齐 */
        if (r->state == PARSE_LINE) {      /* ---- 请求行 ---- */
            if (sscanf(r->line, "%15s %255s %15s",
                       r->method, r->url, r->version) != 3) {
                r->state = PARSE_ERROR; break;
            }
            r->state = PARSE_HEADER;
        } else {                           /* ---- 头部行 ---- */
            if (r->llen == 0) {            /* 空行: 头部结束 */
                if (strcasecmp(r->method, "POST") == 0 && r->content_len > 0)
                    r->state = PARSE_BODY;
                else
                    r->state = PARSE_DONE;
            } else {
                char *colon = strchr(r->line, ':');
                if (colon) {
                    *colon = '\0';
                    char *v = colon + 1;
                    while (*v == ' ') v++;  /* 跳过冒号后空格 */
                    snprintf(r->key, sizeof(r->key), "%s", r->line);
                    snprintf(r->val, sizeof(r->val), "%s", v);
                    if (strcasecmp(r->key, "Content-Length") == 0)
                        r->content_len = atoi(r->val);   /* 后面收体用 */
                }
            }
        }
        r->llen = 0;                       /* 行缓冲清零, 准备下一行 */
        break;
    case PARSE_BODY:
        if (r->body_len < (int)sizeof(r->body) - 1)
            r->body[r->body_len++] = c;
        if (r->body_len >= r->content_len) /* 收满即完整请求 */
            r->state = PARSE_DONE;
        break;
    case PARSE_DONE:
    case PARSE_ERROR:
        break;                             /* 剩余字节属于下一个请求(keep-alive) */
    }
    return r->state;
}
```

接入 Reactor：recv_cb 里把 recvbuf 逐字节喂 `http_parse_char`，直到 PARSE_DONE 才组装响应——这就是"半包拼装"的落地。外层 TCP 粘包问题详解见 `../03-计算机网络编程/02-IO多路复用与Reactor模型.md`。

### 6.3 响应组装

```c
/* 状态行 + 响应头 + 空行 + 包体; Content-Length 让客户端能判断包体边界 */
int build_response(char *out, int outsz, const char *body, int blen) {
    return snprintf(out, outsz,
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: text/html; charset=utf-8\r\n"
        "Content-Length: %d\r\n"          /* ★ 必须等于包体字节数 */
        "Connection: keep-alive\r\n"
        "\r\n"
        "%.*s",
        blen, blen, body);
}
/* keep-alive: 响应完不断开, 同一连接继续解析下一请求;
   Connection: close 则发完即 close_cb。 */
```

| 常见状态码 | 语义 |
|---|---|
| 200 OK | 成功 |
| 400 Bad Request | 语法错（FSM 进 PARSE_ERROR 时回它） |
| 404 Not Found | 资源不存在 |
| 500 | 服务端内部错误 |
| 101 Switching Protocols | 升级协议（websocket 握手成功） |

### 6.4 WebSocket 握手与 TCP 文件传输（简表）

| 场景 | 关键流程 |
|---|---|
| websocket 握手 | 客户端发 `Upgrade: websocket` + `Sec-WebSocket-Key: <随机base64>`；服务端算 `Accept = base64( SHA1( Key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11" ) )`，回 `101 Switching Protocols` + `Sec-WebSocket-Accept`；此后该连接改走 ws 帧协议（不再有 HTTP 语义） |
| 大文件传输（tcp） | 先发协议头（文件名+size），再 `while ((n = read(file)) > 0) 分块 send`（每块 64KB），配合 sendbuf 处理写不动的情况；对端按 size 收满为止。零拷贝可用 `sendfile()` 让内核直接从页缓存发网卡 |

```c
/* websocket Accept 计算（需 -lcrypto） */
#include <openssl/sha.h>
#include <openssl/bio.h>
#include <openssl/evp.h>

static void ws_accept(const char *key, char *out, int outsz) {
    static const char guid[] = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
    char src[128]; unsigned char md[20];
    snprintf(src, sizeof(src), "%s%s", key, guid);
    SHA1((const unsigned char *)src, strlen(src), md);   /* SHA1 摘要 */
    BIO *b64 = BIO_new(BIO_f_base64()), *mem = BIO_new(BIO_s_mem());
    BIO_set_flags(b64, BIO_FLAGS_BASE64_NO_NL);
    BIO_push(b64, mem);
    BIO_write(b64, md, sizeof(md));                      /* base64 编码 */
    BIO_flush(b64);
    BUF_MEM *bp = NULL;
    BIO_get_mem_ptr(b64, &bp);
    snprintf(out, outsz, "%.*s", (int)bp->length, bp->data);
    BIO_free_all(b64);
}
```

## 7. 异步网络库设计

### 7.1 同步处理与异步处理的数据差异

```text
同步(阻塞 recv):                  异步(事件回调):
 while(1){                         on_readable(fd):
   n = recv(fd);  ← 阻塞挂起         data = recv(fd);
   process(data);                   push(业务线程池, data);   ← 数据流向变了
 }                                 }
 数据流: 调用点即处理点              数据流: 事件源→回调→队列→消费者
 编程模型: 顺序思维                 编程模型: 控制反转(好莱坞原则)
```

| 维度 | 同步阻塞 | 异步事件驱动 |
|---|---|---|
| 线程占用 | 每连接占一个线程等数据 | 一个线程管 N 个连接，等=epoll_wait |
| 代码可读性 | 直观 | 回调拆碎逻辑（可读性差 → 引出协程，见 `07-协程框架原理与实现.md`） |
| 吞吐 | 受线程数限制 | 受 CPU/内存限制 |
| 排错 | 栈完整 | 栈被打散，需日志/上下文对象串联 |

### 7.2 网络 IO 线程池：one loop per thread【高频】

主线程 accept 后把连接**分发给**工作线程，每个工作线程一个独立 event_loop：

```text
 main thread                      thread-1            thread-2
 ┌────────────┐   connfd         ┌────────────┐      ┌────────────┐
 │ acceptor    │ ──(轮询选next)──▶│ event_loop │      │ event_loop │
 │ epoll只挂   │                  │  epoll     │      │  epoll     │
 │ listenfd    │                  │  该线程独享 │      │  该线程独享  │
 └────────────┘                  └────────────┘      └────────────┘
                                  自己的 conn 集合      自己的 conn 集合
  优点: 一个 fd 只属于一个 loop → 同一连接的事件天然串行 → 无锁
  唤醒: 主线程往目标 loop 投任务需唤醒它 epoll_wait → 用 eventfd/pipe 注册进 epoll
```

| 要点 | 说明 |
|---|---|
| fd 归属唯一 | 每个连接只在一个 loop 上注册/读写，杜绝数据竞争 |
| 唤醒机制 | 跨线程投递用 eventfd（Linux）写一个 8 字节唤醒 epoll_wait |
| 业务线程池 | 若业务重（DB/计算），loop 只做 IO，任务打包投递给 compute pool（muduo 做法可插拔） |

### 7.3 业界参考

| 库 | 语言/平台 | 模型 | 一句话 |
|---|---|---|---|
| libevent | C | 单 loop + event_base | 老牌，跨平台 dispatcher 抽象鼻祖（本篇 4.3 的原型） |
| libev | C | 单 loop | 更轻更快，API 更简洁 |
| libuv | C | 单 loop + 线程池 | Node.js 底座，IO + 异步文件/DNS |
| muduo | C++ | 主从 Reactor + one loop per thread | 教学经典，本篇 4.2 的工程化完全体 |
| sylar | C++ | 协程 + IO 调度 + worker | 国产教学框架，见 `07-协程框架原理与实现.md` |
| netty | Java | 主从 Reactor | 工业主流，NioEventLoopGroup 即 one loop per thread |

## 8. 快速参考卡片

| 要点 | 一句话 |
|---|---|
| epoll 快的根源 | 红黑树管注册 + 回调把就绪 epitem 挂 rdllist + wait 只取就绪链 |
| LT/ET | LT 看存量（有数据就报）；ET 看增量（从无到有报一次，必须读到 EAGAIN） |
| EPOLLONESHOT | 事件只触发一次，处理后需 MOD 重新武装；用于多线程单 epfd 串行化 |
| Reactor 定义 | IO 事件多路分发器：epoll_wait + 回调，业务写进回调 |
| 三形态 | 单Re单线程(Redis<6.0) / 单Re多线程(业务池) / 主从Re(muduo/netty) |
| vs 每连接一线程 | 线程数=核数、无切换风暴、缓存友好；代价是回调式编程 |
| channel | fd + events + read/write/error 三回调 + 私有数据 |
| EPOLLOUT 按需注册 | sendbuf 空则注销；常开 EPOLLOUT = 忙轮询打满 CPU |
| 两类应用缓冲 | recvbuf 拼半包；sendbuf 存没写完的数据 |
| recv 返回 0 | 对端关闭 → 走统一 close 路径（先 DEL 再 free） |
| EAGAIN | 非阻塞的正常分支，不是错误，绝不能当错误关连接 |
| HTTP FSM | LINE→HEADER→BODY→DONE 逐字节喂，天然抗粘包/半包/坏输入 |
| Content-Length | 请求体与响应体的边界依据；响应必带 |
| ws 握手 | Accept = base64(SHA1(Key + GUID))，回 101 |
| one loop per thread | 每线程独立 epoll；fd 只属一个 loop → 无锁 |
| 跨线程唤醒 | eventfd 写 8 字节，唤醒目标线程的 epoll_wait |

## 9. 常见问题与坑

| 坑 | 现象 | 正解 |
|---|---|---|
| EPOLLONESHOT 之外常注册 EPOLLOUT | CPU 100% 忙轮询，epoll_wait 立即返回 | sendbuf 有数据才 `events \|= EPOLLOUT`，写完立刻 `&= ~EPOLLOUT` |
| EAGAIN 当错误处理 | 高负载下连接被莫名关闭 | `errno==EAGAIN/EWOULDBLOCK` 是正常分支，return 等下次事件 |
| accept 惊群 | 多进程/线程同时 accept，惊醒后一个成功其余空跑 | 单点 accept；或 SO_REUSEPORT 各自队列；或 EPOLLEXCLUSIVE |
| 连接对象生命周期悬垂 | close_cb free 了 conn，但本次 epoll_wait 返回数组里还有它的旧事件指针再次分发 → use-after-free | 先 EPOLL_CTL_DEL 再 free；同轮多个事件按 EPOLLERR 优先、且 free 后跳过 |
| sendbuf 无限膨胀 | 慢客户端把服务器内存吃光 | 高水位限流：超过阈值停止读对端（背压）或断开 |
| ET 模式一次没读完 | 剩余数据永远不再通知，连接假死 | ET 必须 fd 非阻塞 + 循环 recv 直到 EAGAIN |
| 忘处理 recv()==0 | 连接泄漏、CLOSE_WAIT 堆积 | 0 = 对端 FIN，立刻走关闭流程 |
| 忘设非阻塞 | LT 偶发卡死、ET 必死 | accept 出来的 fd 与 listenfd 都 set_nonblock |
| send 无 MSG_NOSIGNAL | 对端重置连接时 SIGPIPE 直接杀进程 | 加 MSG_NOSIGNAL 或全局 `signal(SIGPIPE, SIG_IGN)` |
| 忽略 EPOLLHUP/EPOLLRDHUP | 对端异常关闭不清理 | 错误优先于读写分发；EPOLLRDHUP 单独处理半关闭 |
| channel 表用数组且 fd 超界 | fd > MAX_FD 越界崩溃 | 有限数组只做教学；生产用 hash/动态扩容 |
| FSM 状态卡死不报错 | 半包永远不完整也不超时 | 配合读空闲超时（定时踢连接），状态机给 PARSE_ERROR 出口 |
| 读写回调里做重活（DB 查询） | 单 Reactor 全部连接被卡住 | 重业务投线程池；或主从 Reactor 扩展 IO 线程 |

---

上一篇：《03-高性能服务器设计.md》
下一篇：《05-Nginx深度：反向代理与模块开发.md》
