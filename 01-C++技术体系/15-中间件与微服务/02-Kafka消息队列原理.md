# Kafka消息队列原理

> 本节目标：掌握 Kafka 作为分布式提交日志的架构与存储原理——Broker/Topic/Partition/Replica/ISR/HW 核心概念、分区路由与并行消费、segment 存储（.log 数据 + .index 稀疏索引 + .timeindex 时间索引）与 offset 二分查找流程、生产者发送五步与可靠性三件套（acks/幂等/事务）、消费者组 rebalance 协议与位移提交语义、端到端不丢三环节配置；理解高吞吐四板斧（顺序写 + 页缓存 + sendfile 零拷贝 + 批量压缩），能手写 librdkafka 生产/消费代码，能排查 lag 积压与 rebalance 风暴。前置《01-中间件实战.md》（MQ 选型全景），关联《05-RabbitMQ与消息队列.md》（推模型与交换机路由对比）。 课程模块 4.3：Kafka 使用场景与设计原理、存储机制。 一句话定位：Kafka 是**分布式、可水平扩展、持久化的提交日志（commit log）**——只追加写，消费者自己 pull、自己管位移。

## 本章速览

- [1. 概述](#1-概述)
  - [1.1 消息队列的价值](#11-消息队列的价值)
  - [1.2 发布订阅 vs 点对点](#12-发布订阅-vs-点对点)
  - [1.3 定位](#13-定位)
- [2. 架构【核心】](#2-架构核心)
  - [2.1 整体架构](#21-整体架构)
  - [2.2 核心概念大表](#22-核心概念大表)
  - [2.3 分区的作用](#23-分区的作用)
  - [2.4 副本与 ISR 机制](#24-副本与-isr-机制)
  - [2.5 acks 三级语义【高频】](#25-acks-三级语义高频)
- [3. 存储机制【核心】](#3-存储机制核心)
  - [3.1 Partition 存储分布](#31-partition-存储分布)
  - [3.2 Segment 文件结构](#32-segment-文件结构)
  - [3.3 offset 查找 message 全流程【高频】](#33-offset-查找-message-全流程高频)
  - [3.4 高效存储设计四板斧](#34-高效存储设计四板斧)
- [4. 生产者](#4-生产者)
  - [4.1 发送五步流程](#41-发送五步流程)
  - [4.2 分区策略](#42-分区策略)
  - [4.3 可靠性三件套](#43-可靠性三件套)
- [5. 消费者](#5-消费者)
  - [5.1 消费组 rebalance【高频】](#51-消费组-rebalance高频)
  - [5.2 分区分配策略](#52-分区分配策略)
  - [5.3 位移提交](#53-位移提交)
  - [5.4 消费语义](#54-消费语义)
- [6. 高性能总结与消息不丢方案](#6-高性能总结与消息不丢方案)
- [7. 实战速查](#7-实战速查)
  - [7.1 常用命令](#71-常用命令)
  - [7.2 librdkafka 最小示例（C/C++）](#72-librdkafka-最小示例cc)
  - [7.3 横向对比](#73-横向对比)
- [8. 快速参考卡片](#8-快速参考卡片)
- [9. 常见问题与坑](#9-常见问题与坑)

---

## 1. 概述

### 1.1 消息队列的价值

| 价值 | 一句话案例 |
| --- | --- |
| 异步 | 用户注册后"发欢迎邮件/送积分"扔进队列立刻返回，注册接口耗时从 300ms 降到 20ms |
| 解耦 | 订单系统只管发 OrderCreated 事件，库存/物流/积分各自订阅，新增消费方不改订单代码 |
| 削峰 | 秒杀 10 万 QPS 打进来，队列当蓄水池，下游按 1 万 QPS 匀速消费，DB 不被打死 |

### 1.2 发布订阅 vs 点对点

```text
发布订阅（一份数据多人各取一份）          点对点（一条消息只被一个消费者处理）
   P ──► Topic ──┬──► 订阅者A              P ──► Queue ──► 消费者（竞争消费）
                 ├──► 订阅者B
                 └──► 订阅者C
```

Kafka 的实现：**Consumer Group**——同一个组内分区互斥（点对点），不同组之间各自独立消费全量（发布订阅）。两种语义一个机制全包了。

### 1.3 定位

| 特性 | 说明 |
| --- | --- |
| append-only 日志 | 消息只追加不可改，写满靠滚动 segment 文件 |
| 消费者 pull | 消费速率由消费者自己控制，天然按能力限流 |
| 持久化 + 常量时间读 | 消息落盘保留（按时间/大小清理），按 offset 随机定位 |

## 2. 架构【核心】

### 2.1 整体架构

```text
 Producer ──┐                        ┌──► Consumer Group1（3 成员）
            ▼                        │
      ┌─────────── Broker 集群 ───────────┐
      │  Topic T1 ─ P0[Leader B1│Follower B2]      │
      │          ├─ P1[Leader B2│Follower B3]  ────┼──► Consumer Group2（2 成员）
      │          └─ P2[Leader B3│Follower B1]      │
      └── 元数据/选主：ZooKeeper 或 KRaft（Raft，3.x 起替代 ZK，4.0 移除 ZK）
```

### 2.2 核心概念大表

| 概念 | 说明 | 关键点 |
| --- | --- | --- |
| Broker | 一个 Kafka 服务进程 | 无状态化：元数据放 ZK/KRaft |
| Topic | 逻辑消息分类 | 物理上由若干分区组成 |
| Partition | 分区，最小并行单位 | 有序性只保证**分区内** |
| Offset | 消息在分区内的递增编号 | 消费位置由消费者提交 |
| Replica | 副本：1 Leader + N Follower | 读写都走 Leader，Follower 只拉取同步 |
| AR / ISR | AR=全部副本；ISR=与 Leader 保持同步的副本子集 | OSR = AR − ISR（被踢出的） |
| Consumer Group | 消费组 | 组内一分区只给一个成员 |
| Coordinator | 组协调者（某个 Broker） | 管理 JoinGroup/心跳/位移提交 |
| __consumer_offsets | 内部位移主题（默认 50 分区，compact） | 保存消费位移 |

### 2.3 分区的作用

| 作用 | 说明 |
| --- | --- |
| 水平扩容 | 单分区写性能有限，分区分散到多 Broker 即可线性扩 |
| 并行消费 | 分区数 = 组内最大有效消费者数 |
| 有序性 | 只保证分区内有序；全局有序只能单分区（牺牲吞吐） |
| 路由 | Producer 按 key 路由：`(murmur2(key) & 0x7fffffff) % 分区数`，同 key 必进同分区（消息不乱序的前提） |

### 2.4 副本与 ISR 机制

| 机制 | 说明 |
| --- | --- |
| Leader 挂 | Controller 从 ISR 里选新 Leader |
| ISR 收缩 | Follower 落后超过 `replica.lag.time.max.ms`（默认 30s）没追上 → 踢出 ISR |
| ISR 扩张 | 落后者追上 Leader 的 LEO → 重新加入 ISR |
| LEO | Log End Offset：每个副本日志下一条待写入的 offset |
| HW（高水位） | ISR 中最小的 LEO；**消费者只能读到 HW 之前的消息**——保证"已消费的数据一定已充分复制" |
| min.insync.replicas | 与 acks=all 配合：ISR 少于该值时写入报 NotEnoughReplicas，宁可拒绝服务也不丢数据 |

### 2.5 acks 三级语义【高频】

| acks | 含义 | 丢失风险 |
| --- | --- | --- |
| 0 | 发出去就算成功，不等确认 | Leader 落盘前宕机 → 丢；网络抖动 → 丢 |
| 1 | 等 Leader 落盘确认 | Leader 确认后、Follower 复制前宕机，新 Leader 没这条 → 丢 |
| all / -1 | 等 ISR 全部落盘确认 | 只在"ISR 全体同时失效"才丢；配 min.insync.replicas≥2 + 副本数≥3 基本不丢 |

## 3. 存储机制【核心】

### 3.1 Partition 存储分布

每个分区每个副本一个目录：`Topic名-分区号/`，如 `order-log-0/`。目录内是**一组 segment 文件**，写满滚动。

### 3.2 Segment 文件结构

| 文件 | 作用 |
| --- | --- |
| `00000000000000000000.log` | 数据文件：消息本体，**只追加** |
| `00000000000000000000.index` | 偏移索引：offset → 物理位置，**稀疏索引**（每写 4096 字节才记一条，省空间） |
| `00000000000000000000.timeindex` | 时间索引：时间戳 → offset |
| 文件名 | 本 segment 起始 offset（20 位补零），天然有序、二分友好 |
| 滚动条件 | `segment.bytes`（默认 1GB）或 `segment.ms`（默认 7 天） |

### 3.3 offset 查找 message 全流程【高频】

查"分区 P 的 offset=368900"：

```text
① segment 列表按起始 offset 有序 ──二分──► 命中 0000000000000368800 段
② 在该段 .index 里二分找 ≤368900 的最大索引项（稀疏，只能逼近）
     如命中 368893 → 物理位置 1394
③ 从 .log 的 1394 处顺序扫描，跳过 7 条 ──► 命中 368900
   （稀疏索引换空间，兜底用小段顺序扫描，通常几条内命中）
```

| 步骤 | 数据结构 | 复杂度 |
| --- | --- | --- |
| 定位 segment | 有序文件名数组 | 二分 O(log n) |
| 定位物理位置 | 稀疏索引 | 二分 O(log n) + 顺序扫几条 |
| 消费连续读 | 消费是顺序 offset | 直接顺着 .log 读，零查找 |

### 3.4 高效存储设计四板斧

| 手段 | 说明 | 量化对比 |
| --- | --- | --- |
| 顺序写磁盘 | 日志只追加，磁盘顺序写接近内存随机写 | 顺序 ~600MB/s vs 机械盘随机 ~100KB/s（数量级差距） |
| 页缓存 page cache | 读写都优先走内核页缓存；Kafka 不自己 cache，重启进程缓存还在 | 热数据读取 0 磁盘 IO |
| 零拷贝 sendfile | 消费 fetch 走 sendfile：数据从页缓存直达网卡，不进用户态 | 4 次拷贝+4 次切换 → 0 次用户态拷贝（见 `../06-工程化与工具链/11-性能分析与基准测试.md` 零拷贝） |
| 批量 + 压缩 | Producer 攒批（linger.ms/batch.size）+ snappy/lz4/zstd 压缩后传输 | 网络与存储体积大幅下降 |

## 4. 生产者

### 4.1 发送五步流程

```text
拦截器(interceptors) → 序列化器(serializer) → 分区器(partitioner)
   → RecordAccumulator 批缓冲（按分区攒 batch）
   → Sender 线程把就绪 batch 按 broker 分组、建连发送，处理响应/重试
```

### 4.2 分区策略

| 策略 | 说明 |
| --- | --- |
| 指定分区 | record 里显式给 partition 则直投 |
| 有 key | `murmur2(key) % 分区数`（正数化后取模），同 key 同分区 |
| 无 key | 粘性轮询：一批尽量发同一分区，批满再换（减少小批，KIP-79） |
| 自定义 | 实现 Partitioner 接口（业务路由，如按机房） |

### 4.3 可靠性三件套

| 参数 | 说明 |
| --- | --- |
| acks=all | 见 2.5 |
| retries + delivery.timeout | 临时失败自动重试（leader 切换等），不中断业务 |
| enable.idempotence=true | **幂等**：Producer 启动领 PID，每条消息带"PID+分区+序号"，Broker 按序号去重——重试不会造成重复（要求 acks=all、max.in.flight≤5） |
| 事务 | `transactional.id` + begin/commit，**跨分区原子写**；配合 read_committed 消费实现端到端 exactly-once（consume-transform-produce） |

## 5. 消费者

### 5.1 消费组 rebalance【高频】

| 触发条件 | 说明 |
| --- | --- |
| 成员变化 | 新消费者加入 / 某成员退出（崩溃或正常离组） |
| 订阅变化 | 订阅的 topic 集合变化（正则订阅时新 topic 上线也算） |
| 分区数变化 | topic 扩分区 |

协议流程（Coordinator 主持）：

```text
① FindCoordinator：成员找本组的协调者 Broker
② JoinGroup：全员上报订阅信息；Coordinator 选一个成员当"组长"
③ SyncGroup：组长跑分配策略算出方案，交 Coordinator 下发给全员
④ 进入稳定态：各成员拉自己分到的分区，定时 Heartbeat 保活
   ——rebalance 期间(STABLE→PREPARING→COMPLETING) 全组停止消费
```

| 参数 | 说明 |
| --- | --- |
| session.timeout.ms | 心跳超时：超时未心跳视为掉线，触发 rebalance |
| heartbeat.interval.ms | 心跳间隔（经验值 = session 的 1/3） |
| max.poll.interval.ms | 两次 poll 最大间隔：**处理太慢**没按时 poll 也被踢出组 |
| group.instance.id | 静态成员：短暂重启不触发 rebalance |

### 5.2 分区分配策略

| 策略 | 说明 |
| --- | --- |
| range | 按 topic 逐个划分区间，前几组多拿——容易不均 |
| roundrobin | 全部分区排序后轮询分发，更均匀 |
| sticky | 尽量保持上次分配，减少分区大挪移 |
| cooperative-sticky | 增量协作式 rebalance：只挪需要挪的分区，其余**不停消费**（KIP-429，推荐） |

### 5.3 位移提交

| 方式 | 语义 | 丢/重窗口 |
| --- | --- | --- |
| 自动（默认） | enable.auto.commit=true，每 5s 在 poll 时顺带提交 | 先提交后处理则可能**丢**；处理完没来得及提交则**重复** |
| 手动 commitSync | 处理完再同步提交 | 崩溃在"处理完-提交前" → 重启重复消费（at-least-once） |
| 手动 commitAsync | 异步提交低延迟但可能乱序，配合 finally 里 commitSync 兜底 | 同上 |
| __consumer_offsets | 位移其实是一条普通消息写进内部主题（50 分区、compact） | key=组+topic+分区 → 永远保留最新位移 |

### 5.4 消费语义

| 语义 | 实现组合 |
| --- | --- |
| at-most-once 至多一次 | 先提交位移再处理（可能丢，很少用） |
| at-least-once 至少一次 | 先处理再提交 + 重试（默认推荐，要求业务幂等） |
| exactly-once 恰好一次 | 生产侧事务+幂等；消费侧 isolation.level=read_committed；或下游幂等去重 |

## 6. 高性能总结与消息不丢方案

| 高性能手段 | 一句话 |
| --- | --- |
| 顺序写 + 页缓存 | 写路径极致压榨磁盘与内核 |
| 零拷贝 sendfile | 读路径绕开用户态 |
| 批量 + 压缩 | 网络与存储双减负 |
| 分区并行 | 水平扩展无上限 |
| 稀疏索引 + 二分 | offset 定位 O(log n) |

端到端不丢三环节：

| 环节 | 配置 |
| --- | --- |
| 生产端 | acks=all + retries 大值 + enable.idempotence=true |
| Broker 端 | replication.factor≥3 + min.insync.replicas≥2 + unclean.leader.election=false |
| 消费端 | 先处理业务，成功后再手动 commitSync 提交 |

## 7. 实战速查

### 7.1 常用命令

| 命令 | 作用 |
| --- | --- |
| `kafka-topics.sh --bootstrap-server :9092 --create --topic t1 --partitions 3 --replication-factor 2` | 建主题 |
| `kafka-topics.sh --bootstrap-server :9092 --describe --topic t1` | 看分区/ISR/Leader |
| `kafka-console-producer.sh --bootstrap-server :9092 --topic t1` | 命令行生产 |
| `kafka-console-consumer.sh --bootstrap-server :9092 --topic t1 --from-beginning --group g1` | 命令行消费 |
| `kafka-consumer-groups.sh --bootstrap-server :9092 --describe --group g1` | 看 CURRENT-OFFSET / LOG-END-OFFSET / **LAG**（积压） |

### 7.2 librdkafka 最小示例（C/C++）

```c
// producer：gcc prod.c -o prod -lrdkafka
#include <librdkafka/rdkafka.h>

int main() {
    char err[256];
    rd_kafka_conf_t *conf = rd_kafka_conf_new();
    rd_kafka_conf_set(conf, "bootstrap.servers", "127.0.0.1:9092", err, sizeof(err));
    rd_kafka_t *rk = rd_kafka_new(RD_KAFKA_PRODUCER, conf, err, sizeof(err));
    rd_kafka_topic_t *rkt = rd_kafka_topic_new(rk, "test", NULL);

    char buf[256];
    for (int i = 0; i < 100; i++) {
        int n = snprintf(buf, sizeof(buf), "msg-%d", i);
        rd_kafka_produce(rkt, RD_KAFKA_PARTITION_UA, RD_KAFKA_MSG_F_COPY,
                         buf, n, NULL, 0, NULL);   // 异步投递，内部排队
        rd_kafka_poll(rk, 0);                       // 驱动回调（投递报告）
    }
    rd_kafka_flush(rk, 10 * 1000);                  // 阻塞等全部发出（同步收尾）
    rd_kafka_topic_destroy(rkt);
    rd_kafka_destroy(rk);
    return 0;
}
```

```c
// consumer：gcc cons.c -o cons -lrdkafka
#include <librdkafka/rdkafka.h>
#include <inttypes.h>
#include <stdio.h>

int main() {
    char err[256];
    rd_kafka_conf_t *conf = rd_kafka_conf_new();
    rd_kafka_conf_set(conf, "bootstrap.servers", "127.0.0.1:9092", err, sizeof(err));
    rd_kafka_conf_set(conf, "group.id", "g1", err, sizeof(err));          // 组内竞争消费
    rd_kafka_conf_set(conf, "enable.auto.commit", "true", err, sizeof(err));
    rd_kafka_t *rk = rd_kafka_new(RD_KAFKA_CONSUMER, conf, err, sizeof(err));

    rd_kafka_topic_partition_list_t *subs = rd_kafka_topic_partition_list_new(1);
    rd_kafka_topic_partition_list_add(subs, "test", RD_KAFKA_PARTITION_UA);
    rd_kafka_subscribe(rk, subs);                    // 订阅（参与组管理）
    rd_kafka_topic_partition_list_destroy(subs);

    for (;;) {
        rd_kafka_message_t *msg = rd_kafka_consumer_poll(rk, 1000);  // 拉取一条
        if (!msg) continue;
        if (msg->err == RD_KAFKA_RESP_ERR_NO_ERROR)
            printf("partition=%d offset=%" PRId64 " %.*s\n",
                   msg->partition, msg->offset,
                   (int)msg->len, (char *)msg->payload);
        rd_kafka_message_destroy(msg);               // 用完必 destroy
    }
    rd_kafka_consumer_close(rk);                     // 正常离组，避免误触发 rebalance
    rd_kafka_destroy(rk);
    return 0;
}
```

### 7.3 横向对比

| 维度 | Kafka | RabbitMQ | RocketMQ | Pulsar | Redis Stream |
| --- | --- | --- | --- | --- | --- |
| 吞吐 | 极高（百万级/s） | 中（万级） | 高（十万级） | 极高 | 中低 |
| 模型 | 拉、日志留存 | 推、队列路由（交换机） | 拉、日志留存 | 分层存储（计算/存储分离） | 拉最大特点轻量 |
| 延迟 | ms 级（攒批） | µs~ms | ms | ms | µs~ms |
| 功能 | 流处理生态最全 | 路由/优先级最灵活 | 事务消息/延迟消息 | 多租户/存算分离 | 见 `../05-数据库与序列化/02-Redis设计与数据结构.md` |
| 适用 | 日志/埋点/流平台 | 复杂路由业务 | 电商交易链 | 云原生多租户 | 已有 redis、量小 |

## 8. 快速参考卡片

| 主题 | 关键点 |
| --- | --- |
| 一分区分一消费者 | 组内分区互斥；分区多消费者少 → 有人闲着 |
| key 路由 | murmur2(key) % 分区数，同 key 同分区保有序 |
| ISR / HW | 同步副本集合 / 最小 LEO，消费者只能读到 HW 前 |
| acks | 0 丢 / 1 leader 落盘 / all 全 ISR 落盘 |
| 不丢三段论 | 生产 acks=all+幂等 / Broker 副本≥3+min.insync≥2 / 消费先处理后提交 |
| segment | .log + .index（稀疏，4096B 一条）+ .timeindex，1GB 或 7 天滚动 |
| 查消息 | 段二分 → 索引二分 → 顺序扫几条 |
| 四板斧 | 顺序写 / 页缓存 / sendfile 零拷贝 / 批量压缩 |
| rebalance 触发 | 成员增减 / 订阅变化 / 分区数变化 |
| rebalance 协议 | FindCoordinator → JoinGroup（选组长）→ SyncGroup（下发方案） |
| 位移主题 | __consumer_offsets：50 分区、compact、key=组+topic+分区 |
| lag 排查 | consumer-groups --describe 看 LAG；上涨→加消费者/查下游慢因 |

## 9. 常见问题与坑

| 坑 | 现象 | 规避 |
| --- | --- | --- |
| rebalance 风暴 | 成员反复进出组，全组消费停停走走 | session/heartbeat 参数匹配；max.poll.interval.ms 调大或拆小批；处理逻辑不能阻塞 poll 线程 |
| 消费组名冲突 | 测试组与线上组同名，互相踢对方分区 | 命名规范（环境前缀），上线前核对 |
| 自动提交丢消息 | poll 出来的还没处理完，下次 poll 顺带把位移提交了，随后崩溃 → 这批再也不会被消费 | 关自动提交，处理成功后 commitSync（at-least-once + 业务幂等） |
| 重复消费 | 处理完没来得及提交就崩溃，重启从旧位移重跑 | 同上属 at-least-once；下游按 key/seq 幂等去重 |
| 分区数 > 消费者数 | 多余消费者空转，扩容无效 | 消费者数 ≤ 分区数；想再扩先加分区（注意 key 路由变化） |
| 热点 key | 大客户 key 全打到一个分区，该分区 lag 飙升 | key 加盐/打散；或自定义分区器 |
| lag 告警与处置 | lag 突增不知该干嘛 | 先看是消费慢（加消费者/优化处理）还是生产突增（限流）；segment 磁盘满另查保留策略 |
| unclean 选举丢数据 | 落后副本被选为 Leader，已消费数据"消失" | unclean.leader.election.enable=false |
| ISR 收缩写入失败 | min.insync.replicas=2 但 ISR 只剩 1 | 副本≥3、监控 ISR 数、及时修复落后副本 |
| exactly-once 误解 | 只开幂等就宣称端到端不重 | 幂等只保证单分区单会话；跨分区/端到端要事务 + read_committed |

---

上一篇：《01-中间件实战.md》　｜　下一篇：《03-异步日志与Protobuf.md》　｜　模块索引：《../README.md》
