# RabbitMQ与消息队列

> 本节目标：掌握 RabbitMQ 的架构模型、交换机类型、消息可靠性机制、死信/延迟队列等核心特性，能够进行 RabbitMQ 与 Kafka 的选型对比，并识别常见坑与最佳实践；与「Kafka 原理」笔记互补，本篇聚焦 RabbitMQ（业务消息场景）。Kafka 深入见《02-Kafka消息队列原理.md》，MQ 选型全景见《01-中间件实战.md》。

## 本章速览

- [1. 架构模型](#1-架构模型)
  - [1.1 核心概念](#11-核心概念)
  - [1.2 消息流转流程](#12-消息流转流程)
- [2. 交换机类型【高频】](#2-交换机类型高频)
  - [2.1 Direct Exchange](#21-direct-exchange)
  - [2.2 Fanout Exchange](#22-fanout-exchange)
  - [2.3 Topic Exchange](#23-topic-exchange)
  - [2.4 Headers Exchange](#24-headers-exchange)
- [3. 消息可靠性【高频】](#3-消息可靠性高频)
  - [3.1 三环节可靠性](#31-三环节可靠性)
  - [3.2 生产端确认（Publisher Confirm）](#32-生产端确认publisher-confirm)
  - [3.3 持久化](#33-持久化)
  - [3.4 消费端确认](#34-消费端确认)
- [4. 死信队列与延迟队列](#4-死信队列与延迟队列)
  - [4.1 死信（DLX，Dead-Letter Exchange）](#41-死信dlxdead-letter-exchange)
  - [4.2 TTL（消息过期）](#42-ttl消息过期)
  - [4.3 延迟队列](#43-延迟队列)
- [5. RabbitMQ vs Kafka【高频】](#5-rabbitmq-vs-kafka高频)
- [6. 高可用与集群](#6-高可用与集群)
  - [6.1 集群模式](#61-集群模式)
  - [6.2 仲裁队列（Quorum Queue）](#62-仲裁队列quorum-queue)
- [7. C++ 客户端](#7-c-客户端)
- [8. 快速参考卡片](#8-快速参考卡片)
- [9. 常见坑](#9-常见坑)

---

## 1. 架构模型

### 1.1 核心概念

```text
生产者 Producer → 交换机 Exchange →(Binding 路由规则)→ 队列 Queue → 消费者 Consumer
```

| 概念 | 说明 |
| --- | --- |
| Producer | 生产者，发送消息到 Exchange |
| Exchange | 交换机，接收消息并按 Binding 规则路由到 Queue |
| Binding | 绑定，Exchange 与 Queue 之间的路由规则（含 routing key） |
| Queue | 队列，存储消息的缓冲，消费者从队列取消息 |
| Consumer | 消费者，从队列订阅/拉取消息 |
| Routing Key | 路由键，消息携带，Exchange 按此路由 |
| Virtual Host | 虚拟主机，逻辑隔离（类似数据库的 schema），独立的 Exchange/Queue/权限 |
| Channel | 信道，TCP 连接上的多路复用，减少连接开销 |

### 1.2 消息流转流程

```text
1. Producer 建立 Connection → 打开 Channel
2. Producer 发消息到 Exchange（带 routing key + properties）
3. Exchange 按 Binding 规则路由到一个或多个 Queue
4. 消息存入 Queue（持久化消息落盘）
5. Consumer 订阅 Queue（basic.consume）或拉取（basic.get）
6. Consumer 处理消息，发 ack（basic.ack）确认
7. Broker 删除已 ack 的消息
```

**Channel 的作用**：RabbitMQ 用 TCP 长连接，但每个线程一个 TCP 连接太浪费。Channel 是 Connection 内的逻辑通道，多个 Channel 复用一个 TCP 连接，每个 Channel 独立通信（带 channel id）。生产/消费都在 Channel 上操作。

## 2. 交换机类型【高频】

| 类型 | 路由规则 | 典型场景 |
| --- | --- | --- |
| Direct | 精确匹配 routing key | 指定队列投递、任务分发 |
| Fanout | 广播到所有绑定队列 | 发布订阅、广播通知 |
| Topic | 通配符匹配 routing key（`*` 和 `#`） | 灵活路由、日志分类 |
| Headers | 按消息头属性匹配 | 少用，复杂路由规则 |

### 2.1 Direct Exchange

消息的 routing key 与 Binding 的 routing key **完全相等**才投递。

```text
Exchange: direct_logs
Binding: direct_logs → queue_error (routing_key="error")
         direct_logs → queue_info  (routing_key="info")

Producer 发 routing_key="error" → 只到 queue_error
Producer 发 routing_key="info"  → 只到 queue_info
Producer 发 routing_key="debug" → 无匹配，丢弃（或返回给生产者）
```

### 2.2 Fanout Exchange

忽略 routing key，**广播到所有绑定的队列**。最快的交换机类型。

```text
Exchange: fanout_broadcast
Binding: fanout_broadcast → queue_A
         fanout_broadcast → queue_B
         fanout_broadcast → queue_C

Producer 发任意消息 → queue_A、queue_B、queue_C 都收到一份
```

适用：配置变更广播、实时通知、WebSocket 推送。

### 2.3 Topic Exchange

routing key 用 `.` 分隔成单词，Binding 用通配符匹配：
- `*`（星号）：匹配**一个**单词
- `#`（井号）：匹配**零个或多个**单词

```text
Exchange: topic_logs
Binding: topic_logs → queue_app    (routing_key="app.*")
         topic_logs → queue_error  (routing_key="*.error")
         topic_logs → queue_all    (routing_key="#")

Producer 发 routing_key="app.error"   → queue_app, queue_error, queue_all
Producer 发 routing_key="app.info"    → queue_app, queue_all
Producer 发 routing_key="db.error"    → queue_error, queue_all
Producer 发 routing_key="app.db.error"→ queue_all（app.* 只匹配一个单词）
```

适用：日志按级别/模块路由、新闻按分类订阅、多租户消息隔离。

### 2.4 Headers Exchange

不看 routing key，按消息的 headers 属性匹配。`x-match` 为 `all`（所有头匹配）或 `any`（任意头匹配）。灵活但性能差，很少用。

## 3. 消息可靠性【高频】

### 3.1 三环节可靠性

| 环节 | 丢失风险 | 解决方案 |
| --- | --- | --- |
| 生产端 | 消息发出去没到 Broker | Publisher Confirm（发布者确认）+ 事务 |
| 存储端 | Broker 收到未落盘就宕机 | 队列持久化 + 消息持久化 + 镜像队列 |
| 消费端 | 收到但处理失败/崩溃 | 手动 ack（处理完再确认）+ 死信队列 |

### 3.2 生产端确认（Publisher Confirm）

```cpp
// C++ 伪代码（AMQP-CPP 库）
channel->confirmSelect();                    // 开启 confirm 模式
channel->onAck([](uint64_t tag, bool multiple) {
    // 消息已被 Broker 接收
});
channel->onNack([](uint64_t tag, bool multiple) {
    // 消息被拒绝（如队列满），需重发或告警
});
channel->publish(exchange, routing_key, message);
// 等待确认或超时
if (!channel->waitForConfirms(5000)) { /* 超时处理 */ }
```

**Confirm 模式 vs 事务**：
- Confirm：异步确认，性能高（吞吐量是事务的 100+ 倍），推荐。
- 事务（txSelect/txCommit/txRollback）：强一致但性能极差，很少用。

### 3.3 持久化

三层持久化必须同时生效，否则宕机丢数据：

| 层级 | 配置 | 说明 |
| --- | --- | --- |
| Exchange 持久化 | `durable=true` 声明 | Exchange 元数据持久化 |
| Queue 持久化 | `durable=true` 声明 | Queue 元数据持久化 |
| 消息持久化 | `delivery_mode=2`（PERSISTENT） | 消息内容落盘 |

**注意**：持久化不保证 100% 不丢——消息到 Broker 后、落盘前宕机仍可能丢。需要 Publisher Confirm + 持久化 + 镜像队列三重保障。

### 3.4 消费端确认

| 确认模式 | 说明 | 风险 |
| --- | --- | --- |
| 自动 ack（autoAck=true） | 消息投递给消费者即确认 | 消费者处理失败/崩溃 → 消息丢失 |
| 手动 ack（autoAck=false） | 处理完后 `basic.ack` 确认 | 可靠，推荐 |
| 手动 nack/reject | 处理失败，`basic.nack`/`basic.reject` 拒绝 | 可选 requeue（重新入队）或进死信 |

```cpp
// 手动确认（C++ 伪代码）
channel->onMessage([&](const AMQP::Message& msg, uint64_t tag, bool redelivered) {
    try {
        process(msg);                    // 业务处理
        channel->ack(tag);               // 成功才确认
    } catch (const std::exception& e) {
        // 失败：不 requeue（避免无限循环），让消息进死信队列
        channel->reject(tag, false);     // requeue=false → 进死信（如果配置了 DLX）
    }
});
channel->consume(queue_name);           // 订阅队列，autoAck=false
```

**requeue 的坑**：nack 时 `requeue=true` 会把消息重新入队，如果消费端一直失败会无限循环（消息在队首反复被消费）。建议 `requeue=false` + 死信队列，或限制重试次数。

## 4. 死信队列与延迟队列

### 4.1 死信（DLX，Dead-Letter Exchange）

消息变成**死信**的条件：
1. 被消费者 `basic.reject` 或 `basic.nack` 且 `requeue=false`。
2. 消息 TTL 过期（在队列中存活时间超过 x-message-ttl）。
3. 队列达到最大长度（x-max-length），新消息被丢弃或队首被挤出。

```text
原队列（配置 x-dead-letter-exchange=dlx_exchange）
  → 消息变死信
  → 路由到 DLX（死信交换机）
  → 按 routing key 路由到死信队列
  → 人工处理/告警/定时重试
```

**配置方式**：声明队列时设置参数：
- `x-dead-letter-exchange`：死信交换机名
- `x-dead-letter-routing-key`：死信的 routing key（可选，默认用原 routing key）

### 4.2 TTL（消息过期）

| TTL 类型 | 配置 | 说明 |
| --- | --- | --- |
| 队列级 TTL | `x-message-ttl`（毫秒） | 队列中所有消息的最大存活时间 |
| 消息级 TTL | `expiration` 属性（毫秒） | 单条消息的过期时间，取队列级和消息级的较小值 |

**注意**：RabbitMQ 的 TTL 过期检测是**惰性的**——只有消息到达队首时才检查是否过期。如果队首有不过期的消息，后面过期的消息不会被及时移除（但不会被投递给消费者）。这导致**用 TTL 实现延迟队列时，延迟时间不准**（见 4.3）。

### 4.3 延迟队列

RabbitMQ **无原生延迟队列**，用 **TTL + 死信** 实现：

```text
延迟队列（设置 x-message-ttl=5000，x-dead-letter-exchange=dlx）
  → 消息进入延迟队列，5 秒后 TTL 过期
  → 变死信，路由到 DLX
  → DLX 路由到实际处理队列
  → 消费者从实际处理队列取消息执行
```

```cpp
// 声明延迟队列（C++ 伪代码）
AMQP::Table args;
args["x-message-ttl"] = 5000;                  // 5 秒 TTL
args["x-dead-letter-exchange"] = "dlx_exchange";
args["x-dead-letter-routing-key"] = "process";
channel->declareQueue("delay_queue", durable, false, false, args);

// 声明死信交换机和处理队列
channel->declareExchange("dlx_exchange", "direct");
channel->declareQueue("process_queue", durable);
channel->bindQueue("process_queue", "dlx_exchange", "process");
```

**TTL 延迟队列的问题**：
- 延迟时间不准：TTL 惰性检测，队首消息不过期则后面的不被检测。
- 不同延迟时间需要不同队列（每个 TTL 一个队列）。

**更好的方案**：RabbitMQ Delayed Message 插件（`rabbitmq_delayed_message_exchange`），支持任意延迟时间，基于 x-delayed-type 交换机，延迟更准确。生产环境推荐用插件而非 TTL+DLX。

## 5. RabbitMQ vs Kafka【高频】

| 维度 | RabbitMQ | Kafka |
| --- | --- | --- |
| 定位 | 消息代理（Message Broker） | 分布式提交日志（Commit Log） |
| 吞吐 | 万级（~1-5万/s） | 百万级（~100万+/s） |
| 延迟 | 亚毫秒~毫秒（无积压时极低） | 毫秒级（攒批） |
| 消息模型 | 队列（消费即删）+ 交换机路由 | 日志（可重复消费，pull 模式） |
| 路由能力 | 强（4 种交换机，灵活路由） | 弱（按分区+key，无复杂路由） |
| 顺序性 | 单队列单消费者有序 | 单分区内有序 |
| 消息追溯 | 消费即删，不可追溯 | 持久化保留，可按 offset 重放 |
| 协议 | AMQP（高级消息队列协议） | 自定义二进制协议 |
| 高可用 | 镜像队列/仲裁队列 | 多副本+ISR |
| 适用 | 业务消息、复杂路由、RPC、低延迟 | 日志、埋点、流处理、大数据、高吞吐 |

**选型一句话**：业务消息+复杂路由+低延迟选 RabbitMQ；日志/流处理+高吞吐+可追溯选 Kafka。很多公司两者都用（业务消息走 RabbitMQ，日志/埋点走 Kafka）。

## 6. 高可用与集群

### 6.1 集群模式

| 模式 | 说明 |
| --- | --- |
| 普通集群 | 队列元数据同步，消息只存一个节点，性能好但单点故障 |
| 镜像队列（Mirror Queue） | 队列消息复制到多个节点，高可用但写性能下降（已废弃，推荐仲裁队列） |
| 仲裁队列（Quorum Queue） | 基于 Raft 共识，多数派确认，高可用+数据安全，RabbitMQ 3.8+ 推荐 |
| 联邦插件（Federation） | 跨机房/跨集群消息转发，适合异地多活 |

### 6.2 仲裁队列（Quorum Queue）

基于 Raft 共识算法，写入需要多数派（N/2+1）确认，比镜像队列更安全（不会脑裂丢数据）。适合需要高可靠的业务队列。

```text
# 声明仲裁队列（policy 方式）
rabbitmqctl set_policy quorum "^quorum\." '{"queue-type":"quorum"}' --apply-to queues
```

## 7. C++ 客户端

| 库 | 特点 |
| --- | --- |
| AMQP-CPP | 纯 C++11，header-only，事件驱动，需自己集成事件循环 |
| SimpleAmqpClient | 基于 librabbitmq-c，简单易用，同步阻塞 |
| rabbitmq-c | C 语言库，最底层，其他库的基础 |

```cpp
// SimpleAmqpClient 示例
#include <SimpleAmqpClient/SimpleAmqpClient.h>
using namespace AmqpClient;

int main() {
    Channel::ptr_t ch = Channel::Create("localhost", 5672, "guest", "guest");
    ch->DeclareQueue("task_queue", false, true);  // durable
    ch->BasicPublish("", "task_queue", BasicMessage::Create("hello"));

    // 消费
    std::string consumer = ch->BasicConsume("task_queue", "", false, false);  // no_ack=false
    Envelope::ptr_t env;
    while (ch->BasicConsumeMessage(consumer, env)) {
        std::cout << "Received: " << env->Message()->Body() << std::endl;
        ch->BasicAck(env);  // 手动确认
    }
    return 0;
}
```

## 8. 快速参考卡片

```text
架构：Producer → Exchange →(Binding)→ Queue → Consumer
交换机：Direct(精确) / Fanout(广播) / Topic(通配符*#) / Headers(头匹配)
可靠性三段论：生产Confirm + 持久化(Exchange/Queue/消息三层) + 消费手动ack
死信DLX：reject/nack(requeue=false) / TTL过期 / 队列满 → DLX → 死信队列
延迟队列：TTL+死信实现（延迟不准）；推荐 Delayed Message 插件
RabbitMQ vs Kafka：RabbitMQ业务路由低延迟，Kafka高吞吐日志可追溯
高可用：仲裁队列(Quorum，Raft多数派)替代镜像队列
Channel：TCP连接内多路复用，减少连接开销
autoAck=false：必须手动ack，否则消费者崩溃消息丢失
```

---

## 9. 常见坑

1. 自动 ack（autoAck=true），消费者处理失败/崩溃消息丢失——必须 autoAck=false，处理成功后手动 ack。
2. 未做幂等，消息重复消费（网络重传、消费者重启）产生脏数据——消费端必须幂等（唯一 ID+去重表）。
3. 队列未持久化或消息未设 delivery_mode=2，重启丢数据——Exchange/Queue/消息三层都要持久化。
4. 交换机与队列绑定错误或 routing key 不匹配，消息丢失（无法路由）——Publisher Confirm + mandatory 标志检测无法路由的消息。
5. 延迟队列用 TTL 实现，消息堆积时延迟不准（TTL 惰性检测）——用 Delayed Message 插件或每个延迟时间一个队列。
6. nack 时 requeue=true 导致无限循环（消费端一直失败）——requeue=false + 死信队列，或限制重试次数。
7. 每个线程一个 Connection 导致连接数爆炸——用 Channel 多路复用，一个进程一个 Connection，多线程各用一个 Channel。
8. 消息体过大（> 1MB）导致 Broker 内存压力大——大消息存对象存储，MQ 只传引用/URL。
9. 消费者处理逻辑阻塞消费线程，导致 prefetch 占满无法消费新消息——处理逻辑放线程池，或调大 prefetch_count。
10. 忽略流控（flow control）——Broker 内存/磁盘告警时会阻塞 Producer，需监控并设置告警。

---

上一篇：《04-性能分析与调优.md》　｜　下一篇：《06-微服务治理.md》　｜　模块索引：《../README.md》
