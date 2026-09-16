# ZeroMQ消息模式（嵌入式网络库与无Broker架构）

> 本节目标：掌握 ZeroMQ 的定位与四种核心消息模式（REQ/REP、PUB/SUB、PUSH/PULL、ROUTER/DEALER），理解消息分帧与信封机制、中间层代理（Proxy）、高水位标记（HWM）与可靠性设计，能在 C++ 项目中用 ZeroMQ 构建无 Broker 的高性能消息通信，并对比 Kafka/RabbitMQ 选型。

## 本章速览

- [1. ZeroMQ 定位与核心思想](#1-zeromq-定位与核心思想)
- [2. 四种消息模式](#2-四种消息模式)
  - [2.1 REQ/REP（请求应答）](#21-reqrep请求应答)
  - [2.2 PUB/SUB（发布订阅）](#22-pubsub发布订阅)
  - [2.3 PUSH/PULL（管道）](#23-pushpull管道)
  - [2.4 ROUTER/DEALER（异步路由）](#24-routerdealer异步路由)
- [3. 消息分帧、多部分消息与信封机制](#3-消息分帧多部分消息与信封机制)
- [4. 中间层代理（Proxy/Device）](#4-中间层代理proxydevice)
- [5. 高水位标记（HWM）与消息丢失处理](#5-高水位标记hwm与消息丢失处理)
- [6. 无锁队列、零拷贝与可靠性设计](#6-无锁队列零拷贝与可靠性设计)
- [7. 与 Kafka / RabbitMQ 对比](#7-与-kafka--rabbitmq-对比)
- [8. 快速参考卡片](#8-快速参考卡片)
- [9. 常见问题与坑](#9-常见问题与坑)

---

## 1. ZeroMQ 定位与核心思想

ZeroMQ（ZMQ/0MQ）是一个**嵌入式网络库**，不是消息中间件。它以 socket 风格 API 提供多种消息模式，在应用进程内实现消息队列、路由和传输，**无需独立 Broker 进程**。

**核心思想：**

- **Socket 风格 API**：`zmq_socket()` / `zmq_bind()` / `zmq_connect()` / `zmq_send()` / `zmq_recv()`，与 BSD Socket 类似但语义更丰富
- **异步 IO**：后台 I/O 线程处理网络收发，用户线程只操作内存队列，非阻塞
- **多传输协议**：inproc（进程内）、ipc（Unix域套接字）、tcp、pgm/epgm（可靠多播）
- **自动重连**：connect 端自动重连，对端不在线时消息缓存在本地队列
- **零拷贝**：大消息使用 `zmq_msg_init_data()` 配合释放回调，避免内存拷贝

**与传统 Socket 的关键区别：**

| 维度 | BSD Socket | ZeroMQ Socket |
| --- | --- | --- |
| 通信模式 | 字节流（TCP）/ 数据报（UDP） | 消息模式（REQ/REP等） |
| 连接管理 | 手动 accept/connect | 自动，一个 socket 可多连接 |
| 消息边界 | TCP 无边界，需自行分帧 | 天然消息边界，多部分消息 |
| 队列 | 无 | 内置发送/接收队列（HWM限制） |
| 线程安全 | 一个连接一个线程 | 一个 socket 可被多线程使用（有约束） |

---

## 2. 四种消息模式

### 2.1 REQ/REP（请求应答）

经典的客户端-服务器请求应答模式，严格交替收发。

```text
客户端(REQ)                     服务器(REP)
   |--- 请求 --------------------->|
   |                                |  处理
   |<-- 响应 -----------------------|
   |--- 请求 --------------------->|  （必须先收再发，交替进行）
```

**约束：** REQ 端必须先发后收，REP 端必须先收后发，严格交替。违反会导致状态机错误。

**C++ 示例：**

```cpp
// server.cpp (REP)
#include <zmq.hpp>
int main() {
    zmq::context_t ctx(1);
    zmq::socket_t sock(ctx, ZMQ_REP);
    sock.bind("tcp://*:5555");
    while (true) {
        zmq::message_t req;
        sock.recv(req);                       // 先收
        std::string reply_str = "processed: " + req.to_string();
        zmq::message_t reply(reply_str.size());
        memcpy(reply.data(), reply_str.data(), reply_str.size());
        sock.send(reply, zmq::send_flags::none);  // 后发
    }
}

// client.cpp (REQ)
#include <zmq.hpp>
int main() {
    zmq::context_t ctx(1);
    zmq::socket_t sock(ctx, ZMQ_REQ);
    sock.connect("tcp://localhost:5555");
    zmq::message_t req(5);
    memcpy(req.data(), "hello", 5);
    sock.send(req, zmq::send_flags::none);       // 先发
    zmq::message_t rep;
    sock.recv(rep);                                // 后收
}
```

### 2.2 PUB/SUB（发布订阅）

一对多广播模式，发布者不关心订阅者，订阅者通过主题过滤接收。

```text
              PUB (发布者)
             /   |   \
            /    |    \
         SUB    SUB    SUB
       (主题A) (主题B) (主题A+B)
```

**关键特性：**
- **慢订阅者问题**：PUB 不缓存消息，订阅者不在线或处理慢时消息直接丢弃（"发完即忘"）
- **主题过滤**：SUB 端通过 `zmq_setsockopt(ZMQ_SUBSCRIBE, topic, len)` 设置订阅前缀，空字符串订阅所有
- **无连接感知**：PUB 不知道有多少订阅者，也不知道消息是否被接收

**适用场景：** 实时行情推送、配置变更广播、事件通知（允许丢失）。

### 2.3 PUSH/PULL（管道）

流水线/任务分发模式，PUSH 端公平轮询（round-robin）分发到所有 PULL 端，PULL 端公平轮询接收所有 PUSH 端。

```text
PUSH1 ---\
          \--> PULL1 (worker)
PUSH2 ---/
          \--> PULL2 (worker)
PUSH3 ---/
```

**关键特性：**
- **负载均衡**：PUSH 自动 round-robin 到所有已连接的 PULL
- **无主题过滤**：所有消息按顺序分发，不区分内容
- **背压**：PULL 端处理慢时，PUSH 端本地队列堆积，达到 HWM 后阻塞或丢弃

**典型架构：** ventilator（PUSH 分发任务）-> worker（PULL 收任务 + PUSH 发结果）-> sink（PULL 收结果）。

### 2.4 ROUTER/DEALER（异步路由）

ROUTER 和 DEALER 是异步、可扩展的高级 socket，是构建代理和复杂路由的基础。

**ROUTER（原 XREP）：**
- 接收消息时自动在消息前添加**对端身份帧**（envelope），标识消息来源
- 发送消息时根据第一帧（身份帧）路由到指定对端
- 可同时与多个对端通信，无需交替收发
- 是构建请求路由（broker）的核心

**DEALER（原 XREQ）：**
- 异步的 REQ，无交替收发约束，可随时收发
- round-robin 分发到所有已连接对端
- 常用于 worker 端与 ROUTER 通信

```text
客户端(DEALER)               代理(ROUTER-DEALER)            Worker(ROUTER)
   |--- 请求(无信封) ---------->|                                |
   |                             |--- 请求(身份帧+内容) -------->|
   |                             |                                |  处理
   |                             |<-- 响应(身份帧+内容) ---------|
   |<-- 响应(无信封) -----------|                                |
```

**ROUTER 的信封机制详解：**

```text
ROUTER 收到 DEALER 发来的消息 [body]，实际接收为：
  [dealer_identity_frame][empty_delimiter_frame][body]

ROUTER 发送时，第一帧必须是目标对端的 identity：
  send [target_identity][empty][body] -> 路由到 target，对端收到 [body]
```

身份帧默认是 UUID（ZMQ 自动生成），也可通过 `ZMQ_IDENTITY` 选项设置可读名称（最长 255 字节，不能以 0 开头）。

---

## 3. 消息分帧、多部分消息与信封机制

ZeroMQ 消息由一个或多个**帧（frame）**组成，帧之间有明确边界，接收端能完整还原。

**多部分消息发送：**

```cpp
// 发送三帧消息
zmq::message_t frame1(5);
memcpy(frame1.data(), "addr1", 5);
sock.send(frame1, zmq::send_flags::sndmore);  // 还有后续帧

zmq::message_t frame2(1);  // 空分隔帧
sock.send(frame2, zmq::send_flags::sndmore);

zmq::message_t frame3(5);
memcpy(frame3.data(), "hello", 5);
sock.send(frame3, zmq::send_flags::none);  // 最后一帧
```

**多部分消息接收：**

```cpp
while (true) {
    zmq::message_t frame;
    auto res = sock.recv(frame);
    bool more = frame.more();  // 是否还有后续帧
    // 处理 frame
    if (!more) break;
}
```

**信封（Envelope）机制：**

信封是 ROUTER/REQ 等 socket 自动维护的多帧结构，用于路由和请求-应答关联：

```text
REQ 发送: [empty_delimiter][body]
REP 接收: [empty_delimiter][body]（自动剥离信封）
REP 发送: [empty_delimiter][reply]（自动恢复信封）
REQ 接收: [reply]

ROUTER 接收: [source_identity][empty_delimiter][body]
ROUTER 发送: [target_identity][empty_delimiter][body]
```

空分隔帧（empty delimiter）是信封与正文的边界，REQ/REP 自动维护，ROUTER/DEALER 需手动处理。

---

## 4. 中间层代理（Proxy/Device）

ZeroMQ 提供内置代理函数 `zmq_proxy()`，在两个 socket 之间转发消息，用于构建无状态 Broker。

**常见代理拓扑：**

| 代理类型 | 前端 socket | 后端 socket | 用途 |
| --- | --- | --- | --- |
| Queue（请求路由） | ROUTER | DEALER | 请求-应答的负载均衡 Broker |
| Forwarder（发布订阅） | XSUB | XPUB | 发布订阅的汇聚转发 |
| Streamer（管道） | PULL | PUSH | 任务流水线的汇聚分发 |

**Queue 代理实现（请求-应答负载均衡）：**

```cpp
// broker.cpp
#include <zmq.hpp>
int main() {
    zmq::context_t ctx(1);
    zmq::socket_t frontend(ctx, ZMQ_ROUTER);  // 面向客户端
    zmq::socket_t backend(ctx, ZMQ_DEALER);   // 面向 worker
    frontend.bind("tcp://*:5555");
    backend.bind("tcp://*:5556");
    // 内置代理：自动转发，维护信封
    zmq::proxy(frontend, backend);
}
```

```text
客户端(REQ) --connect 5555--> ROUTER[代理]DEALER --bind 5556--> Worker(REP)
                                                          |
                                              Worker(REP)（多个，自动负载均衡）
```

代理是无状态的，可水平扩展；客户端和 worker 只知道代理地址，不需要知道彼此。

**XSUB/XPUB 代理（发布订阅转发）：**

```cpp
zmq::socket_t frontend(ctx, ZMQ_XSUB);  // 面向发布者
zmq::socket_t backend(ctx, ZMQ_XPUB);   // 面向订阅者
frontend.bind("tcp://*:5557");
backend.bind("tcp://*:5558");
zmq::proxy(frontend, backend);
```

XSUB/XPUB 支持订阅消息的转发，订阅者的 SUBSCRIBE 消息通过代理传到发布者端，实现端到端主题过滤。

---

## 5. 高水位标记（HWM）与消息丢失处理

**高水位标记（High Water Mark, HWM）** 是 socket 发送/接收队列的最大消息数，防止内存无限增长。

```cpp
// 设置发送 HWM（默认 1000）
int hwm = 5000;
sock.setsockopt(ZMQ_SNDHWM, &hwm, sizeof(hwm));
// 设置接收 HWM
sock.setsockopt(ZMQ_RCVHWM, &hwm, sizeof(hwm));
```

**不同 socket 的 HWM 行为：**

| Socket 类型 | 达到 HWM 时的行为 |
| --- | --- |
| PUSH | 阻塞（对端有连接时）或丢弃（对端不在线时） |
| PUB | 直接丢弃（永不阻塞） |
| REQ/DEALER | 阻塞 |
| ROUTER | 丢弃到特定对端的消息（ZMQ_ROUTER_MANDATORY=1 时返回错误） |

**消息丢失的场景与对策：**

| 场景 | 原因 | 对策 |
| --- | --- | --- |
| PUB 消息丢失 | 订阅者不在线或处理慢 | 用 PUSH/PULL 或 ROUTER/DEALER 替代；应用层 ACK |
| PUSH 队列满 | worker 处理速度跟不上 | 增加 worker；调大 HWM；用 ROUTER 实现有确认的分发 |
| 进程崩溃丢失 | 消息仅在内存队列 | 持久化到磁盘（ZMQ 不原生支持，需应用层实现） |
| 网络分区丢失 | 对端不可达时消息在本地队列，进程退出即丢 | 用有 Broker 的方案（Kafka/RabbitMQ）替代 |

**ZeroMQ 的可靠性边界：** ZeroMQ 保证**单条消息的完整传输**（不碎片化、不错序），但**不保证消息不丢失**。需要可靠投递时，必须在应用层实现 ACK/重传，或选择有 Broker 的消息队列。

---

## 6. 无锁队列、零拷贝与可靠性设计

### 6.1 无锁队列

ZeroMQ 内部使用无锁队列（lock-free queue）在用户线程和 I/O 线程之间传递消息，基于原子操作（CAS），避免互斥锁开销。

```text
用户线程 --send--> 无锁队列(yqueue) --> I/O线程 --网络发送-->
用户线程 <--recv-- 无锁队列(yqueue) <-- I/O线程 <--网络接收--
```

yqueue 是 ZeroMQ 实现的无锁队列，基于 chunk 分配（批量分配内存块），减少 malloc 次数，适合高吞吐场景。

### 6.2 零拷贝

大消息（如视频帧、大文件块）使用 `zmq_msg_init_data()` 直接引用用户缓冲区，I/O 线程直接从用户内存发送，不做拷贝。发送完成后通过释放回调通知用户释放内存。

```cpp
// 零拷贝发送
void free_buffer(void *data, void *hint) {
    free(data);
}
void send_large(zmq::socket_t &sock, const char *data, size_t len) {
    zmq::message_t msg(data, len, free_buffer, nullptr);
    sock.send(msg, zmq::send_flags::none);
    // data 缓冲区在发送完成后由 free_buffer 释放
}
```

**注意：** 零拷贝仅在 TCP 传输且消息大于一定阈值时生效；inproc/ipc 传输可能仍需拷贝。零拷贝要求用户缓冲区在发送完成前保持有效。

### 6.3 可靠性设计模式

**心跳（Heartbeat）：** ZeroMQ 4.2+ 内置 ZMQ_HEARTBEAT_IVL/TTL/TIMEOUT 选项，自动在应用层发送心跳，检测对端存活。

```cpp
int heartbeat_ivl = 5000;   // 每5秒发心跳
int heartbeat_ttl = 15000;   // 15秒无响应判定死亡
int heartbeat_timeout = 10000;
sock.setsockopt(ZMQ_HEARTBEAT_IVL, &heartbeat_ivl, sizeof(int));
sock.setsockopt(ZMQ_HEARTBEAT_TTL, &heartbeat_ttl, sizeof(int));
sock.setsockopt(ZMQ_HEARTBEAT_TIMEOUT, &heartbeat_timeout, sizeof(int));
```

**重连：** connect 端自动重连，通过 `ZMQ_RECONNECT_IVL`（初始重连间隔，默认100ms）和 `ZMQ_RECONNECT_IVL_MAX`（最大重连间隔，指数退避）控制。

**Linger（逗留）：** socket 关闭时，未发送完的消息在内存中逗留的时间（默认 30 秒）。设为 0 则立即丢弃，设为 -1 则无限等待。

```cpp
int linger = 0;  // 关闭时立即丢弃未发消息
sock.setsockopt(ZMQ_LINGER, &linger, sizeof(int));
```

---

## 7. 与 Kafka / RabbitMQ 对比

详见《../15-中间件与微服务/02-Kafka消息队列原理.md》和《../15-中间件与微服务/05-RabbitMQ与消息队列.md》，此处聚焦选型差异：

| 维度 | ZeroMQ | Kafka | RabbitMQ |
| --- | --- | --- | --- |
| 架构 | 无 Broker，嵌入式库 | 有 Broker，分布式集群 | 有 Broker，集群/镜像队列 |
| 消息持久化 | 不支持（纯内存） | 支持（磁盘日志） | 支持（磁盘/内存） |
| 消息可靠性 | 应用层自行实现 | 高（副本+ACK） | 高（确认+持久化） |
| 吞吐量 | 极高（百万级/秒，无Broker开销） | 极高（十万级/秒，批量+磁盘） | 中高（万级/秒，路由复杂） |
| 延迟 | 极低（微秒级） | 低（毫秒级，批量） | 低（毫秒级） |
| 消息顺序 | 单连接内有序 | Partition 内有序 | Queue 内有序 |
| 路由能力 | 简单（主题前缀/信封） | 强（Topic+Partition+ConsumerGroup） | 极强（Exchange四种路由） |
| 运维复杂度 | 无（库级） | 高（集群+ZK/KRaft+监控） | 中（集群+管理界面） |
| 典型场景 | 进程间通信、高性能内部服务、嵌入式 | 日志收集、流处理、事件溯源 | 业务消息、任务队列、RPC异步 |

**选型建议：**
- **服务内部/同机房高性能通信**：ZeroMQ（无Broker开销，延迟最低）
- **大数据/日志/事件流**：Kafka（持久化+高吞吐+消费者组）
- **业务消息/任务分发/复杂路由**：RabbitMQ（灵活路由+可靠投递+管理界面）
- **需要消息不丢失**：不要用 ZeroMQ，选 Kafka 或 RabbitMQ

---

## 8. 快速参考卡片

### 四种模型拓扑图

```text
REQ/REP:   REQ --请求--> REP --响应--> REQ（严格交替）

PUB/SUB:   PUB --广播--> SUB1, SUB2, ...（主题过滤，可能丢失）

PUSH/PULL: PUSH1,PUSH2 --round-robin--> PULL1,PULL2（负载均衡，背压）

ROUTER/DEALER:
  DEALER --异步--> ROUTER[信封路由]--异步--> DEALER（可多对多，无交替约束）
```

### Socket 类型对照表

```text
类型      模式      收发约束    队列满行为     典型用途
REQ       请求应答  先发后收    阻塞           客户端
REP       请求应答  先收后发    阻塞           服务器
PUB       发布订阅  只发        丢弃           发布者
SUB       发布订阅  只收        丢弃           订阅者
PUSH      管道      只发        阻塞/丢弃      任务分发
PULL      管道      只收        N/A            任务接收
ROUTER    异步路由  可收发      丢弃(可配)     Broker/路由
DEALER    异步路由  可收发      阻塞           Worker/异步客户端
XPUB/XSUB 发布订阅  代理专用    -              发布订阅代理
```

### 常用模式代码模板

```cpp
// 通用初始化
zmq::context_t ctx(io_threads);  // 通常 1，高吞吐设为 CPU核数
zmq::socket_t sock(ctx, ZMQ_XXX);
sock.bind("tcp://*:PORT");     // 服务端 bind
sock.connect("tcp://HOST:PORT"); // 客户端 connect

// 发送多帧
sock.send(frame, zmq::send_flags::sndmore);  // 非最后一帧
sock.send(frame, zmq::send_flags::none);      // 最后一帧

// 接收多帧
do { sock.recv(frame); } while (frame.more());

// 非阻塞收发
auto res = sock.send(frame, zmq::send_flags::dontwait);
if (!res) { /* 队列满，处理 */ }

// 关闭
int linger = 0;
sock.setsockopt(ZMQ_LINGER, &linger, sizeof(int));
sock.close();
ctx.close();
```

---

## 9. 常见问题与坑

| 问题 | 原因与解决 |
| --- | --- |
| REQ/REP 卡死 | 违反交替收发约束（REQ 连续发两次或 REP 连续收两次）；严格遵循一发一收，或改用 DEALER/ROUTER |
| PUB 消息订阅者收不到 | 订阅者未设置 SUBSCRIBE 或设置晚于发布；SUB 必须先 connect 并 setsockopt(ZMQ_SUBSCRIBE)，PUB 不缓存历史消息 |
| connect 后立即 send 消息丢失 | TCP 连接尚未建立，消息在本地队列，若进程退出则丢失；加短暂延迟或用连接事件监控 |
| ROUTER 发送失败 | 目标对端 identity 错误或对端已断开；设 ZMQ_ROUTER_MANDATORY=1 使发送返回 EHOSTUNREACH 而非静默丢弃 |
| 内存持续增长 | HWM 设置过大或消息消费速度慢；监控队列长度，调小 HWM，增加消费者 |
| 多线程使用 socket 崩溃 | ZeroMQ socket 不是线程安全的（除 ZMQ_THREAD_SAFE 的 socket）；每个线程用独立 socket，或用 inproc 传递 |
| 大消息发送慢 | 未用零拷贝；用 zmq_msg_init_data() 引用用户缓冲区，避免 memcpy |
| 进程退出时阻塞 | Linger 默认 30 秒，等待未发消息发送完；设 ZMQ_LINGER=0 立即关闭，或设合理值 |
| inproc 传输失败 | inproc 要求 connect 端在 bind 端之后连接，且必须在同一 context；确保 bind 先执行 |
| 消息顺序错乱 | 一个 socket 多连接时，不同对端的消息可能交错；单对端内有序，多对端间不保证全局有序 |

---

上一篇：《06-gRPC与RPC框架原理.md》　｜　下一篇：《08-etcd与Raft共识.md》　｜　模块索引：《../README.md》
