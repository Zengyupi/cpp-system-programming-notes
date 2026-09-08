# Redis 设计与数据结构

> 本节目标：C++ 求职知识库「数据库」篇第二篇。Redis 是后台面试必考重灾区：单线程为什么快、持久化取舍、缓存三大问题、分布式锁几乎是固定曲目。前置阅读：《../03-网络编程/02-IO多路复用与Reactor模型.md》（epoll / Reactor）；性能排查衔接《../07-调试与测试/04-性能分析与基准测试.md》，后台线程设计衔接《../04-并发编程/05-线程池与并发实战模式.md》。示例基于 Redis 6.x / 7.x，版本差异均已标注。

## 本章速览

- [1. 概述](#1-概述)
  - [1.1 Redis 是什么](#11-redis-是什么)
  - [1.2 为什么快：三根支柱](#12-为什么快三根支柱)
  - [1.3 单线程模型【高频】](#13-单线程模型高频)
  - [1.4 适用与不适用场景](#14-适用与不适用场景)
- [2. 数据类型与应用【高频】](#2-数据类型与应用高频)
  - [2.1 五大基本类型总览](#21-五大基本类型总览)
  - [2.2 String 与 SDS](#22-string-与-sds)
  - [2.3 Hash：对象存储](#23-hash对象存储)
  - [2.4 List：简单消息队列](#24-list简单消息队列)
  - [2.5 Set：去重与集合运算](#25-set去重与集合运算)
  - [2.6 ZSet：跳表与排行榜](#26-zset跳表与排行榜)
  - [2.7 四种高级类型](#27-四种高级类型)
  - [2.8 类型选择决策表](#28-类型选择决策表)
- [3. 常用命令速查](#3-常用命令速查)
  - [3.1 分类型命令表](#31-分类型命令表)
  - [3.2 通用命令（KEYS 禁用与 SCAN 替代【高频】）](#32-通用命令keys-禁用与-scan-替代高频)
  - [3.3 redis-cli 连接与诊断](#33-redis-cli-连接与诊断)
- [4. 持久化【高频】](#4-持久化高频)
  - [4.1 RDB：某时刻全量二进制快照](#41-rdb某时刻全量二进制快照)
  - [4.2 AOF：追加写命令日志](#42-aof追加写命令日志)
  - [4.3 RDB vs AOF](#43-rdb-vs-aof)
  - [4.4 混合持久化（4.0+）](#44-混合持久化40)
  - [4.5 生产建议](#45-生产建议)
- [5. 过期删除与内存淘汰【高频】](#5-过期删除与内存淘汰高频)
  - [5.1 过期删除：惰性 + 定期](#51-过期删除惰性--定期)
  - [5.2 八种内存淘汰策略（maxmemory-policy）](#52-八种内存淘汰策略maxmemory-policy)
  - [5.3 配置与选择建议](#53-配置与选择建议)
- [6. 主从与高可用【高频】](#6-主从与高可用高频)
  - [6.1 主从复制](#61-主从复制)
  - [6.2 哨兵 Sentinel](#62-哨兵-sentinel)
  - [6.3 Cluster 集群](#63-cluster-集群)
  - [6.4 三方案对比](#64-三方案对比)
- [7. 缓存三大问题【高频·最重要章节】](#7-缓存三大问题高频最重要章节)
  - [7.1 缓存穿透（不存在的 key 打到 DB）](#71-缓存穿透不存在的-key-打到-db)
  - [7.2 缓存击穿（热点 key 过期瞬间高并发打 DB）](#72-缓存击穿热点-key-过期瞬间高并发打-db)
  - [7.3 缓存雪崩（大量 key 同时过期或 Redis 宕机）](#73-缓存雪崩大量-key-同时过期或-redis-宕机)
  - [7.4 三者对比（考前必背）](#74-三者对比考前必背)
- [8. 缓存一致性【高频】](#8-缓存一致性高频)
  - [8.1 Cache Aside 标准模式【高频】](#81-cache-aside-标准模式高频)
  - [8.2 为什么"删缓存"而不是"更新缓存"](#82-为什么删缓存而不是更新缓存)
  - [8.3 为什么"先更 DB 再删缓存"（时序对比）](#83-为什么先更-db-再删缓存时序对比)
  - [8.4 延迟双删](#84-延迟双删)
  - [8.5 订阅 binlog（canal）异步删缓存](#85-订阅-binlogcanal异步删缓存)
  - [8.6 结论](#86-结论)
- [9. 分布式锁【高频】](#9-分布式锁高频)
  - [9.1 加锁标准命令](#91-加锁标准命令)
  - [9.2 解锁：唯一值 + Lua 原子"校验 + 删除"](#92-解锁唯一值--lua-原子校验--删除)
  - [9.3 看门狗续期](#93-看门狗续期)
  - [9.4 主从切换锁丢失与 RedLock 争议](#94-主从切换锁丢失与-redlock-争议)
  - [9.5 C++ 实现提示（hiredis）](#95-c-实现提示hiredis)
- [10. 内存与性能优化](#10-内存与性能优化)
  - [10.1 bigkey](#101-bigkey)
  - [10.2 hotkey](#102-hotkey)
  - [10.3 pipeline vs mget vs Lua](#103-pipeline-vs-mget-vs-lua)
  - [10.4 慢查询](#104-慢查询)
  - [10.5 内存碎片](#105-内存碎片)
- [11. 与 C++ 服务集成](#11-与-c-服务集成)
  - [11.1 hiredis 基础](#111-hiredis-基础)
  - [11.2 连接池要点](#112-连接池要点)
  - [11.3 RESP2 协议一眼速览](#113-resp2-协议一眼速览)
- [12. 快速参考卡片](#12-快速参考卡片)
- [13. 常见问题与坑](#13-常见问题与坑)

---

## 1. 概述

### 1.1 Redis 是什么

Redis（REmote DIctionary Server）：开源的**基于内存的 KV 数据库**，**C 语言实现**，数据结构丰富（String / Hash / List / Set / ZSet / BitMap / HyperLogLog / GEO / Stream），支持持久化（RDB/AOF）、主从、哨兵与集群，单机 10w+ QPS。版本节点：4.0 引入 LFU / UNLINK / 混合持久化；6.0 多线程 IO、ACL、RESP3；7.0 用 listpack 全面替代 ziplist、AOF 多文件；7.4 支持 Hash 字段级过期；2024 年许可证调整催生分支 Valkey，2025 年 Redis 8.0 以 AGPLv3 回归开源。

### 1.2 为什么快：三根支柱

| 支柱 | 说明 | 关键点 |
| --- | --- | --- |
| 纯内存操作 | 数据全在内存，读写百纳秒级 | 没有磁盘寻道 |
| IO 多路复用 | 一个线程用 epoll 监听上万连接 | 即《../03-网络编程/02-IO多路复用与Reactor模型.md》的 epoll Reactor 模型，Redis 封装为 ae 事件库 |
| 单线程执行 | 命令串行执行 | 无锁、无上下文切换、无竞态，每条命令天然原子（对比《../04-并发编程/01-线程基础与生命周期.md》） |
| 高效数据结构 | SDS / 跳表 / quicklist / listpack / 渐进式 rehash 的 dict | 为内存与 CPU 特化 |

### 1.3 单线程模型【高频】

"单线程"的准确含义：**命令执行线程只有一个**。

- **6.0 之前**：事件监听、协议解析、命令执行、结果写回全在主线程（bgsave / AOF 重写由 fork 出的子进程完成；fsync、关闭文件、异步删除在后台 BIO 线程，不参与命令执行）。
- **6.0 起**：引入多线程 IO（`io-threads`），**网络读写与协议解析可并行，但命令仍由主线程串行执行**——"单条命令原子、无需加锁"的结论不变。

```text
Redis < 6.0（单线程 Reactor，一条流水线干完所有事）：
  client1/2/N ─► epoll_wait ─► read ─► 解析 ─► 执行命令 ─► write ─► 回复
                  （任何一步慢，所有客户端一起排队等它）

Redis >= 6.0（IO 线程并行 + 命令仍然单线程串行执行）：
  epoll_wait（主线程）── 分发就绪连接
      ├─ IO线程1: read + 协议解析
      ├─ IO线程2: read + 协议解析
      └─ 主线程: 等 IO 线程完成后【串行执行】全部命令（保证原子性与顺序）
                 执行完再交给 IO 线程并行 writev 写回
```

| 常见追问 | 答案 |
| --- | --- |
| 命令执行为什么不做多线程 | 数据结构全局共享，多线程要加锁、有线程切换开销；单线程简单且命令天然原子，扩展靠多实例 |
| 什么时候开 io-threads | CPU 已成瓶颈且 QPS 高时（默认 1 = 关闭）；官方建议 4 核以上配 2~3 个；读并行需 `io-threads-do-reads yes` |
| 单线程的代价 | 一个慢命令（KEYS、大 key 操作、Lua 死循环）阻塞所有客户端 → 禁 KEYS、用 UNLINK、盯 slowlog |

### 1.4 适用与不适用场景

| 场景 | 做法 | 关键点 / 章节 |
| --- | --- | --- |
| 缓存（最核心） | 热点数据 + TTL + Cache Aside | 第 7、8 章 |
| 计数器 | `INCR` 原子自增 | 单线程天然原子，点赞 / 阅读 / 限流 |
| 排行榜 | ZSet | 见 2.6 |
| 分布式锁 | `SET NX EX` + Lua | 第 9 章 |
| 消息队列 | Stream（List 只做简单场景） | 消费者组 + ACK，见 2.7 |
| 会话共享 | String / Hash 存 session | 多机无状态部署基础 |

| 不适用 | 原因 | 替代 |
| --- | --- | --- |
| 大 Value / 文件存储 | 内存贵；单线程序列化大 value 阻塞 | 对象存储，只存 URL |
| 强一致持久化（记账/下单） | RDB/AOF 有丢失窗口，主从又是异步复制 | 关系型 DB |
| 复杂查询 / Join | 没有 SQL 引擎 | MySQL / ES |

---

## 2. 数据类型与应用【高频】

### 2.1 五大基本类型总览

| 类型 | 底层结构（编码） | 典型场景 | 核心命令 |
| --- | --- | --- | --- |
| String | SDS；小整数 `int`、≤44 字节 `embstr`、更长 `raw` | 缓存 JSON、计数器、分布式锁 | SET GET INCR |
| List | 3.2+ 为 quicklist（双向链表套 ziplist 节点，**7.0 起节点为 listpack**） | 消息队列、最新列表 | LPUSH RPOP LRANGE |
| Hash | 元素少且小 → `listpack`（7.0 前为 `ziplist`），超阈值 → `dict` | 对象存储、购物车 | HSET HGET HGETALL |
| Set | 全整数 → `intset`；否则 `dict`（7.2+ 小集合可用 `listpack`） | 去重、共同关注、抽奖 | SADD SINTER SRANDMEMBER |
| ZSet | 元素少且小 → `listpack`，超阈值 → **skiplist + dict 双结构** | 排行榜、延迟队列 | ZADD ZRANGE ZREVRANK |

阈值示例：`hash-max-listpack-entries 128`、`hash-max-listpack-value 64`、`zset-max-listpack-entries 128`；`OBJECT ENCODING key` 查看实际编码。

### 2.2 String 与 SDS

| 特性 | C 字符串 | SDS |
| --- | --- | --- |
| 取长度 | `strlen` O(N) 遍历 | 读 `len` 字段 **O(1)** |
| 二进制安全 | 以 `\0` 判结尾，存不了含 `\0` 的数据（protobuf/压缩数据） | 以 `len` 判长度，value 可含任意字节 |
| 缓冲区溢出 | `strcat` 不管目标空间，可能越界写 | 修改前检查剩余空间，不足先扩容再写 |
| 内存分配 | 每次修改都 realloc | **预分配**（修改后 <1MB 空间翻倍，≥1MB 每次 +1MB）+ **惰性释放**（缩短不立即归还） |
| 兼容性 | — | 末尾仍带 `\0`，可复用部分 `<string.h>` 函数 |

| 用法 | 命令 | 说明 |
| --- | --- | --- |
| 原子计数 | `INCR pv:1001` | 单线程串行执行天然原子，无需 CAS/锁 |
| 缓存对象 | `SET user:1001 '{"n":1}'` | JSON 可读好排查，protobuf 省带宽；SDS 二进制安全都能存 |
| 分布式锁 | `SET lock:1 <uuid> NX EX 10` | 第 9 章 |

### 2.3 Hash：对象存储

String 存整个 JSON vs Hash 按字段存（读写局部性是核心差异）：

| 维度 | String 存 JSON | Hash 按字段存 |
| --- | --- | --- |
| 读局部性 | 取一个字段也整体反序列化 | `HGET` 单字段，省带宽省 CPU |
| 写局部性 | 改一个字段 = 整读→改→整写 | `HSET` 只动一个字段 |
| 字段级原子计数 | GET+SET 非原子 | `HINCRBY` 原子 |
| 过期粒度 | 整 key | 整 key（**7.4 起才支持字段级 HEXPIRE**） |
| 内存 | 一个大 value 更省 | 元素多转 dict 后每字段一对 entry，更费 |
| 选择 | 字段少、总是整体读写 | 字段多、常单独读写（如购物车 `HINCRBY cart:uid g1 1`） |

### 2.4 List：简单消息队列

| 能力 | 命令 | 评价 |
| --- | --- | --- |
| 生产 / 消费 | `LPUSH` + `RPOP` / `BRPOP` | 先进先出可行 |
| 可靠消费 | `LMOVE src dst LEFT RIGHT`（6.2+） | 取出同时放入"处理中"列表，失败可搬回 |
| 最新列表 | `LPUSH` + `LRANGE 0 9` | 最新 N 条动态 |

**缺陷：无 ACK**——`RPOP` 弹出即删除，消费者拿到消息后崩溃消息就永久丢了；也没有消费者组与回溯。正经队列用 Stream（2.7）或专业 MQ。

### 2.5 Set：去重与集合运算

| 场景 | 命令 | 说明 |
| --- | --- | --- |
| 共同关注 / 好友 | `SINTERSTORE r a b` | 交集写入 r；另有 SUNION / SDIFF、7.0+ `SINTERCARD` 只取数量 |
| 抽奖 | `SRANDMEMBER pool 3` / `SPOP pool 3` | 前者抽样不删（count 为负允许重复），后者弹出即中奖并移除 |
| 标签去重 | `SADD` / `SCARD` / `SISMEMBER` | 天然去重，判存在 O(1) |

### 2.6 ZSet：跳表与排行榜

大 ZSet 底层是 **skiplist + dict 双结构共享元素**：dict 管 member → score O(1) 查分，跳表管按 score 排序与范围查询。

```text
跳表 = 多层有序链表（每层晋升概率 1/4，最高 32 层）

 层3  head ─────────────────────────► 50 ────────► NIL
 层2  head ─────────► 20 ────────────► 50 ────► 70 ─► NIL
 层1  head ─► 10 ───► 20 ─► 30 ─────► 50 ────► 70 ─► NIL
 层0  head ─► 10 ───► 20 ─► 30 ─► 40 ► 50 ────► 70 ─► NIL   ← 完整数据层

 查 40：从最高层向右走，遇到更大节点就下沉，平均 O(logN)
 层0 节点带 backward 指针 → 支持反向遍历（zrevrange 的基础）
```

| 为什么用跳表不用红黑树 | 说明 |
| --- | --- |
| **范围查询更强** | `ZRANGE` 定位起点后沿底层链表顺序走即可；红黑树中序遍历要栈回溯，实现繁琐 |
| **实现简单** | 插入删除只调前后指针；红黑树要旋转变色，代码量与出错率都高（antirez 的原始理由） |
| 性能同级 | 都平均 O(logN)；跳表每节点平均 1.33 个前向指针换简洁 |
| 内存 | 红黑树略省，但只差常数级 |

```bash
ZINCRBY rank:202608 5 "player:1001"     # 加分（不存在则从 0 加）
ZREVRANK rank:202608 "player:1001"      # 我的排名（0 起，第 1 名返回 0）
ZREVRANGE rank:202608 0 9 WITHSCORES    # Top10（分数从高到低）
ZCOUNT rank:202608 100 200              # 分数区间人数
ZRANGEBYSCORE delay 0 1725000000000     # 延迟队列：取已到期任务（score=执行时间戳）
```

### 2.7 四种高级类型

| 类型 | 原理 | 典型场景 | 命令 |
| --- | --- | --- | --- |
| BitMap | String 上的按位操作，1 亿用户一天签到约 12MB | 签到、活跃标记、布隆过滤器 | `SETBIT` `BITCOUNT` |
| HyperLogLog | 基数估算，固定约 12KB，**标准误差 0.81%** | 百万级 UV 去重计数 | `PFADD` `PFCOUNT` `PFMERGE` |
| GEO | 底层就是 ZSet（geohash 52bit 编码作 score） | 附近的人 / 店 | `GEOADD`、`GEOSEARCH ... BYRADIUS 1 km`（6.2+ 取代 georadius） |
| Stream | 持久化日志 + 消费者组 + pending 列表 | 可靠消息队列 | `XADD` `XREADGROUP` `XACK` |

```text
# Stream 最小可用消息队列
XADD mq * sensor 23 temp 40                     # * = 服务端生成 id（时间戳-序号），可回溯
XGROUP CREATE mq g1 0                           # 消费者组（0 从头，$ 只收新消息）
XREADGROUP GROUP g1 c1 COUNT 10 STREAMS mq >    # 消费者 c1 取 10 条
XPENDING mq g1                                  # 查看"已取出未确认"的消息
XACK mq g1 1725000000000-0                      # 处理成功后确认（ACK）
XAUTOCLAIM mq g1 c2 60000 0                     # 7.0+：超时未确认消息转移给 c2
```

### 2.8 类型选择决策表

| 需求 | 选型 |
| --- | --- |
| 计数、单值、锁、整体序列化缓存 | String |
| 对象字段常单独读写 | Hash |
| 最新列表、简单队列 | List |
| 去重、交并差、随机抽取 | Set |
| 排名、按分数范围取、延迟队列 | ZSet |
| 海量布尔位（签到 / 活跃） | BitMap |
| 海量去重计数且容忍 0.81% 误差 | HyperLogLog |
| LBS 附近的人 | GEO |
| 需要 ACK / 消费者组的队列 | Stream（别用 List 硬扛） |

---

## 3. 常用命令速查

### 3.1 分类型命令表

| 类型 | 增 / 改 | 删 | 查 | 批量 / 其他 |
| --- | --- | --- | --- | --- |
| String | `SET k v [EX s\|PX ms] [NX\|XX]`、`APPEND` | `DEL`/`UNLINK`、`GETDEL` | `GET`、`STRLEN`、`GETRANGE` | `MSET`/`MGET`、`INCR`/`INCRBY`/`INCRBYFLOAT` |
| Hash | `HSET k f v`（可多字段） | `HDEL k f [f...]` | `HGET`、`HMGET`、`HGETALL`、`HKEYS`、`HLEN`、`HEXISTS` | `HINCRBY`、`HSCAN`、`HRANDFIELD`（6.2+） |
| List | `LPUSH`/`RPUSH`、`LSET` | `LPOP`/`RPOP`（6.2+ 可带 count）、`LREM`、`LTRIM` | `LRANGE`、`LINDEX`、`LLEN` | `BLPOP`/`BRPOP`、`LMOVE`（6.2+） |
| Set | `SADD` | `SREM`、`SPOP` | `SMEMBERS`、`SISMEMBER`、`SCARD`、`SRANDMEMBER` | `SINTER`/`SINTERSTORE`、`SUNION`、`SDIFF`、`SSCAN` |
| ZSet | `ZADD`、`ZINCRBY` | `ZREM`、`ZREMRANGEBYRANK`/`BYSCORE` | `ZSCORE`、`ZRANK`/`ZREVRANK`、`ZRANGE`/`ZREVRANGE`、`ZRANGEBYSCORE`、`ZCOUNT` | `ZPOPMIN`/`ZPOPMAX`、`BZPOPMIN`、`ZUNIONSTORE`/`ZINTERSTORE`、`ZSCAN` |

### 3.2 通用命令（KEYS 禁用与 SCAN 替代【高频】）

| 命令 | 说明 | 示例 |
| --- | --- | --- |
| `KEYS pattern` | O(N) 遍历整个键空间，**阻塞唯一命令线程，生产禁用** | 只在测试库用 |
| `SCAN cursor [MATCH p] [COUNT n] [TYPE t]` | 游标增量遍历，每次只做少量工作**不阻塞**；可能返回重复 key，保证全程存在的 key 一定被遍历到 | `SCAN 0 MATCH user:* COUNT 100` |
| `EXPIRE key s` / `PEXPIRE` / `EXPIREAT` | 设过期（秒/毫秒/时间戳）；对聚合类型是**整个 key** | `EXPIRE k 60` |
| `TTL` / `PTTL` | 剩余时间；-1 永不过期，-2 不存在 | `TTL k` |
| `PERSIST key` | 移除过期 | `PERSIST k` |
| `TYPE` / `OBJECT ENCODING` | 值类型 / 底层编码 | `OBJECT ENCODING k` |
| `DEL key` | 同步删除，大 key 卡顿 | 小 key 才用 |
| `UNLINK key` | **4.0+ 异步删除**：主线程摘链，后台线程回收内存 | `UNLINK bigkey` |
| `EXISTS` / `RENAME` / `RANDOMKEY` | 存在 / 改名 / 随机 key | |
| `DBSIZE` / `SELECT n` | 当前库 key 数 / 切库（默认 16 个；**Cluster 下只有 db0**） | `SELECT 1` |
| `FLUSHDB` / `FLUSHALL` | 清当前库 / 全部库（支持 ASYNC） | `FLUSHDB ASYNC` |
| `MEMORY USAGE key` | 4.0+ 查看 key 实际内存 | `MEMORY USAGE bigkey` |

### 3.3 redis-cli 连接与诊断

```bash
redis-cli -h 127.0.0.1 -p 6379 -a '密码' -n 0    # -n 选库；-a 明文传密码有安全告警
redis-cli --bigkeys                              # 采样找各类最大 key（低峰执行）
redis-cli --hotkeys                              # 找热 key，需 maxmemory-policy 为 LFU 系
redis-cli --latency / --latency-history          # 客户端视角往返延迟（分桶看趋势）
redis-cli --scan --pattern 'user:*'              # SCAN 的命令行封装，替代 KEYS
redis-cli --pipe < batch.txt                     # 海量导入（管道模式）
redis-cli --eval unlock.lua key1 , arg1          # Lua：逗号前 KEYS，逗号后 ARGV
```

---

## 4. 持久化【高频】

内存数据库掉电即失，持久化 = 用可控代价换可靠性：RDB 快照 / AOF 日志，4.0 起可混合。

### 4.1 RDB：某时刻全量二进制快照

| 触发 | 行为 | 风险 |
| --- | --- | --- |
| `SAVE` | 主线程亲自生成快照，**阻塞所有命令** | 只在维护窗口用 |
| `BGSAVE` | fork 子进程写 RDB，主进程继续服务 | fork 瞬间卡顿 + COW 内存峰值 |
| 自动 | `save` 条件满足后自动 bgsave | 两次快照间数据丢失 |

自动触发条件：6.x 及更早默认 `save 900 1` / `save 300 10` / `save 60 10000`；7.0 默认 `save 3600 1 300 100 60 10000`。

```text
bgsave = fork + 写时复制（COW）：
  主进程(继续处理写命令) ──fork()──► 子进程(把快照写入 RDB 文件)
        两进程先共享同一批物理内存页（只读）
        │ 主进程要改页 A（X:1→2），内核此时才复制出新页：
        ▼
   子进程视角: 页A = X:1(旧值), 页B = Y:9(共享)   ← 快照 = fork 瞬间的一致性视图
   主进程视角: 页A = X:2(新页), 页B = Y:9(共享)   ← 只有被写的页才复制，写入量大时内存接近翻倍
```

| 优点 | 缺点 |
| --- | --- |
| 二进制紧凑，文件小 | 两次快照之间的数据会丢（分钟级窗口） |
| 恢复快（直接加载） | 大内存实例 fork 慢（复制页表）、COW 抬高内存 |
| 子进程生成，不影响主进程执行命令 | |

### 4.2 AOF：追加写命令日志

**写后日志**（先执行命令、成功后才 append）：① 先执行能校验语法正确，不会把运行出错的命令写进日志；② 不阻塞当前命令。代价：宕机时最后一条（或未 fsync 的一批）丢失。

| appendfsync 策略 | 行为 | 数据安全 | 性能 |
| --- | --- | --- | --- |
| `always` | 每条命令都 fsync | 最多丢 1 条 | 最差 |
| `everysec`（默认） | 后台线程每秒 fsync | 最多丢约 1 秒（fsync 卡顿时最长约 2 秒） | 折中，推荐 |
| `no` | 交给 OS 刷盘（约 30 秒） | 不可控 | 最好 |

AOF 重写：日志只追加会越来越大（100 次 `INCR` 等价 1 次 `SET`），重写 = fork 子进程**按当前内存状态**生成最小等价命令集，期间新命令存入重写缓冲最后追加。参数：`auto-aof-rewrite-percentage 100`、`auto-aof-rewrite-min-size 64mb`、`aof-rewrite-incremental-fsync`（每 32MB 刷盘）。7.0 起 AOF 拆为 base + incr 多文件。损坏用 `redis-check-aof --fix` 修复。

### 4.3 RDB vs AOF

| 维度 | RDB | AOF |
| --- | --- | --- |
| 文件大小 | 小（二进制压缩） | 大（文本命令追加） |
| 恢复速度 | 快（直接加载） | 慢（逐条重放） |
| 数据安全 | 丢秒级~分钟级 | everysec 最多丢约 1 秒 |
| 运行时影响 | 平时无感，fork 瞬间卡顿 + COW 内存 | always 拖慢每次写；everysec 影响小 |
| 可读性 | 不可读 | 文本可读（误 FLUSHALL 后可紧急截断恢复） |

### 4.4 混合持久化（4.0+）

`aof-use-rdb-preamble yes`（5.0 起默认开）。AOF 重写时子进程把**当前全量状态以 RDB 格式写入文件头**，之后的增量命令仍以 AOF 格式追加尾部。恢复 = 加载 RDB 头（快）+ 重放少量增量（安全）。**兼具恢复快与丢失少，生产默认推荐。**

### 4.5 生产建议

| 需求 | 方案 |
| --- | --- |
| 高可靠（缓存 + 重要状态） | 混合持久化 + everysec |
| 容忍分钟级丢失、追求恢复速度 | 纯 RDB |
| 纯缓存、数据可全量重建 | 可关持久化，省去 fork 与磁盘 IO |

---

## 5. 过期删除与内存淘汰【高频】

两件事别混淆：**过期删除**处理"设了 TTL 且已到期"的 key；**内存淘汰**处理"内存达到 maxmemory 后怎么办"。

### 5.1 过期删除：惰性 + 定期

| 策略 | 做法 | 优缺点 |
| --- | --- | --- |
| 定时删除（未采用） | 每 key 挂定时器到期即删 | CPU 不友好，海量定时器开销大 |
| 惰性删除 | 访问 key 时检查，过期才删 | CPU 友好；没人访问的过期 key 一直占内存 |
| 定期删除 | 后台任务（`hz` 默认 10，每秒 10 次）每次**随机抽 20 个**设 TTL 的 key 删掉其中已过期的，**过期占比超 25% 就继续抽**，循环带 CPU 时间上限 | 折中 |
| 实际方案 | **惰性 + 定期组合** | 互补；残留过期 key 由内存淘汰兜底 |

### 5.2 八种内存淘汰策略（maxmemory-policy）

内存达到 `maxmemory` 时（写命令执行前检查）按策略腾空间：

| 策略 | 范围 | 算法 | 说明 |
| --- | --- | --- | --- |
| `noeviction`（默认） | 不淘汰 | — | 内存满后写命令直接报 OOM |
| `allkeys-lru` | 全部 key | 近似 LRU | 纯缓存首选 |
| `volatile-lru` | 设了 TTL 的 key | 近似 LRU | 常驻 key（锁/队列）不受影响 |
| `allkeys-lfu` | 全部 key | LFU（4.0+） | 偶发批量扫描场景比 LRU 准 |
| `volatile-lfu` | 设 TTL 的 key | LFU（4.0+） | |
| `allkeys-random` | 全部 key | 随机 | 少用 |
| `volatile-random` | 设 TTL 的 key | 随机 | 少用 |
| `volatile-ttl` | 设 TTL 的 key | 剩余寿命越短越先淘汰 | |

实现细节（加分项）：**近似 LRU**——不维护全局链表（省指针），随机采样 `maxmemory-samples`（默认 5）个 key 淘汰其中最久未用的，3.0+ 用 16 个候选池提精度。**LFU**——复用对象头 24bit lru 字段（16bit 衰减时间 + 8bit 对数计数器），计数按 `lfu-log-factor`（默认 10）对数增长，长时间不访问按 `lfu-decay-time`（默认 1 分钟）衰减，解决"历史热 key 永远热"。

### 5.3 配置与选择建议

```bash
CONFIG SET maxmemory 4gb                  # 0 表示不限制（64 位系统）
CONFIG GET maxmemory-policy
INFO memory                               # used_memory（逻辑）/ used_memory_rss（物理）
```

| 场景 | 推荐 | 理由 |
| --- | --- | --- |
| 纯缓存（可全量重建） | `allkeys-lru` 或 `allkeys-lfu` | 所有 key 都可淘汰，优先剔冷数据 |
| 缓存 + 必须常驻数据（锁/队列） | `volatile-lru`，常驻 key 不设 TTL | 淘汰只发生在缓存 key 上 |
| Redis 里有不可丢数据 | `noeviction` + 告警 + 扩容 | 宁可写失败也别悄悄丢数据 |

---

## 6. 主从与高可用【高频】

单点 → 主从复制（冗余）→ 哨兵（自动故障转移）→ Cluster（分片扩展），这个演进本身就是三道面试题。

### 6.1 主从复制

配置 `replicaof <ip> <port>`（5.0+，旧名 slaveof）；`INFO replication` 看 role / 偏移量。

```text
全量复制（首次连接或断线太久）：

  从库                                        主库
   │ 1. PSYNC <replid> <offset>（首次 ? -1）   │
   │ ────────────────────────────────────────► │ 2. +FULLRESYNC <replid> <offset>
   │                                           │ 3. bgsave 生成 RDB；期间新写命令
   │ 4. 接收并加载 RDB（先清空旧数据）           │    暂存 replication buffer
   │ ◄──────────────────────────────────────── │ 5. 发送 buffer 中的增量命令
   │ 6. 之后进入命令传播（持续同步增量写命令）     │
```

| 机制 | 说明 |
| --- | --- |
| repl_backlog 环形缓冲区 | 主库维护的写命令环形缓冲（默认 1MB，`repl-backlog-size`）。**部分重同步条件**：从库断线重连时 offset 仍落在环内且 replid 匹配 → 回 `+CONTINUE` 只补差量；被覆盖则退化全量复制 |
| 全量复制风暴 | 网络抖动使大量从库同时重连 → 主库被迫多次 bgsave，CPU/内存/带宽被打爆。缓解：调大 backlog、级联复制（从库再挂从库）、无盘复制 `repl-diskless-sync` |
| 复制是异步的 | 主库不等从库确认就回客户端 OK → 主库刚写入即宕机会丢"已确认"数据；可用 `WAIT numreplicas timeout` 显式等待（半同步思想，会阻塞） |

### 6.2 哨兵 Sentinel

主从只冗余不会自动切换，哨兵解决"谁盯主库、挂了谁升主"。

| 职责 | 说明 |
| --- | --- |
| 监控 | 持续 ping 主库、从库、其他哨兵 |
| 选主（故障转移） | 判定主库下线后挑新主、指挥从库改挂新主 |
| 通知 | pub/sub（+switch-master 等）通知客户端新主地址 |

```text
主观下线 vs 客观下线：
  哨兵S1/S2/S3 各自 ping 超时 ─► 各自标记 sdown（主观：单方面认为挂了）
        └─ 判 sdown 的哨兵数 ≥ sentinel monitor 配置的 quorum
                 ──► odown（客观下线：大家都认为挂了）【高频】
                            │
                            ▼
  领导者哨兵选举（Raft 思想：发现 odown 的哨兵互相拉票，
  谁先拿到【哨兵总数的 majority】谁当 leader —— 注意不是 quorum）
                            │
                            ▼
  leader 挑新主：① 排除已下线/断线过久的从库
    ② replica-priority 小者优先（0 = 永不参选）
    ③ 复制偏移量 offset 大者优先（数据最全）
    ④ runid 字典序最小（前三项全相同才走到）
```

客户端感知：客户端连哨兵而非固定主库地址（`SENTINEL get-master-addr-by-name`），订阅 +switch-master 事件，切换后替换连接池里的主库连接（成熟客户端库内置）。

### 6.3 Cluster 集群

| 机制 | 说明 |
| --- | --- |
| 分片原理 | **16384 个 hash 槽**：`slot = CRC16(key) % 16384`，槽分配给各主节点，从库做冗余 |
| 为什么 16384 不是 65536 | ① 心跳包带本节点槽位 bitmap：16384 位 = 2KB，65536 位 = 8KB 太浪费集群总线带宽；② 官方建议主节点不超过 1000 个，16384 槽绰绰有余（CRC16 输出 16bit 上限 65536，取 1/4） |
| Gossip 协议 | 一句话：节点间经集群总线（端口 + 10000，默认 16379）周期性 PING/PONG 交换状态与槽位信息，完成故障检测与拓扑传播 |
| hash tag | `{user1}:order` 与 `{user1}:addr` 只按 `user1` 算槽 → **强制同槽**，让多 key 命令与 Lua 同节点执行 |
| 跨槽限制 | MSET/MGET/DEL 多 key、事务、Lua 的 KEYS 必须同槽，否则报 `CROSSSLOT` |

| 对比项 | MOVED 重定向 | ASK 重定向 |
| --- | --- | --- |
| 含义 | 槽已**永久**属于目标节点 | 槽**正在迁移**且该 key 已搬到目标节点（临时） |
| 客户端行为 | 更新本地槽位映射表，后续直达新节点 | 仅本次：先向目标节点发 `ASKING` 再重发命令，**不**更新映射 |
| 出现场景 | 槽位缓存过期、拓扑变化 | resharding（槽迁移）期间 |

```bash
cluster keyslot "user:1001"                                 # 算槽位
redis-cli --cluster create ip1:6379 ip2:6379 ip3:6379 --cluster-replicas 1
cluster nodes / cluster info
```

### 6.4 三方案对比

| 维度 | 主从复制 | 哨兵 | Cluster |
| --- | --- | --- | --- |
| 数据冗余 | 有 | 有 | 有 + 分片 |
| 故障转移 | 手动 | 自动（秒级） | 自动（内置选主） |
| 容量上限 | 单机内存 | 单机内存 | 水平扩展（TB 级） |
| 客户端复杂度 | 低（主写从读） | 中（感知哨兵拿主地址） | 高（智能客户端维护槽位映射） |
| 多 key / 事务限制 | 无 | 无 | 必须同槽（hash tag） |
| 适用规模 | 读写分离、读多写少 | 单机内存够用的中小规模 | 大数据量 / 大写入量 |

---

## 7. 缓存三大问题【高频·最重要章节】

一句话区分（千万别说反）：**穿透 = 缓存和 DB 里都不存在；击穿 = 单个热点 key 过期；雪崩 = 一大片 key 同时失效或 Redis 整个挂了**。

### 7.1 缓存穿透（不存在的 key 打到 DB）

```text
攻击/脏数据：id=-1 或随机串（缓存必 miss，DB 也查不到）
  请求 ─► 缓存 miss ─► 查 DB（也是空）─► 返回
   ▲                                      │
   └──── 空结果不缓存，下次继续打 DB ◄─────┘   → 高并发下 DB 被打挂
```

| 方案 | 做法 | 代价 / 注意 |
| --- | --- | --- |
| 缓存空值 | 查 DB 为空也 `SET key "" EX 60`（**短 TTL**） | 简单通用；空值占内存，必须短过期 |
| 布隆过滤器 | 启动时把全量合法 id 装入 BF，请求先问 BF | 只能"错杀"不能"漏判" → 残留少量误判穿透；标准 BF 不支持删除，需定期重建 |
| 接口层校验 | 参数合法性（id ≤ 0 / 格式非法直接拒）、鉴权、限流 | 成本最低的第一道闸门 |

```text
布隆过滤器 = 位数组 + k 个独立哈希函数
  key="id:1001" ├─ h1 ─► 下标2 置1  ├─ h2 ─► 下标7 置1  └─ h3 ─► 下标11 置1
  位数组: [ 0 0 1 0 0 0 0 1 0 0 0 1 0 ]
  查询：k 个哈希位全为 1 → "可能存在"（别的 key 置的位恰好重叠 → 误判）
        任何一位为 0    → "一定不存在"（绝无漏判，这才是能挡穿透的原因）
```

### 7.2 缓存击穿（热点 key 过期瞬间高并发打 DB）

秒杀商品这类热 key 恰好过期：海量并发同一瞬间全部 miss → 全部涌向 DB → DB 被打垮。

| 方案 | 做法 | 优缺点 |
| --- | --- | --- |
| 互斥锁重建 | miss 后 `SET lock:key 1 NX EX 10` 抢锁，抢到者查 DB 回填，其余稍后重试读缓存 | 简单可靠；未抢到者等待，吞吐降 |
| 逻辑过期 | key 永不设 TTL，过期时间写进 value；读到"已逻辑过期"就**返回旧值**并异步起线程重建 | 不阻塞；牺牲重建期间一致性 |
| 热点永不过期 + 主动刷新 | 运维定时任务提前更新 | 占内存；适合极热点 |

```bash
# 伪代码：互斥锁重建（防击穿）
value = GET key
if value == nil:
    if SET lock:key 1 NX EX 10:          # 只有抢到锁的去查库
        value = DB.query(key)
        SET key value EX 300             # 回填
        UNLINK lock:key                  # 释放（更严谨用唯一值+Lua，见第 9 章）
    else:
        sleep 0.05; 重新读缓存            # 没抢到：稍等再读（别人正在重建）
```

### 7.3 缓存雪崩（大量 key 同时过期或 Redis 宕机）

```text
触发一：一批 key 相同 TTL，同一秒集体过期（如活动结束整批缓存失效）
        1 万个 key 同时到期 ─► 缓存集体 miss ─► 全量流量砸 DB ─► DB 过载 ─► 服务不可用
触发二：Redis 实例宕机，所有请求绕过缓存直连 DB
```

| 触发 | 解决 |
| --- | --- |
| 大量 key 同时过期 | TTL 加随机抖动：`EXPIRE key 300 + random(0, 60)` 打散过期时间 |
| Redis 实例宕机 | 高可用（哨兵 / Cluster）+ 持久化保证快速恢复 |
| DB 被重建流量打垮 | 多级缓存（进程本地缓存 → Redis → DB）、限流 / 熔断 / 降级、预热 |

### 7.4 三者对比（考前必背）

| 问题 | 定义 | 触发条件 | 核心解法 | 一句话记忆 |
| --- | --- | --- | --- | --- |
| 穿透 | 查**不存在**的数据，缓存永远无法命中 | 恶意请求 / 脏参数 | 空值缓存 + 布隆 + 参数校验 | 没有的数据，造一个"没有" |
| 击穿 | **单个热点** key 过期瞬间高并发打 DB | 热点 + 恰好过期 + 高并发 | 互斥锁 / 逻辑过期 / 永不过期 | 热 key 别出现真空期 |
| 雪崩 | **大面积** key 同时失效或**整库**宕机 | 同批 TTL / 实例故障 | TTL 抖动 + 高可用 + 限流降级 | 别一起倒，倒了有兜底 |

---

## 8. 缓存一致性【高频】

### 8.1 Cache Aside 标准模式【高频】

| 读路径 | 写路径 |
| --- | --- |
| 读缓存 → 命中返回；miss → 读 DB → **回填缓存（带 TTL）** | **先更新 DB，再删除缓存** |

### 8.2 为什么"删缓存"而不是"更新缓存"

| 原因 | 说明 |
| --- | --- |
| 并发写互相覆盖 | A、B 并发写：DB 更新顺序 A→B，缓存更新若交错成 B→A，缓存长期存旧值 |
| 懒加载原则 | 缓存是按需加载的副本：更新了不一定有人读，白费计算与带宽；删了下次读自然回填最新值 |
| 惰性计算 | 更新缓存可能要聚合多张表，等有人读再算更划算 |

### 8.3 为什么"先更 DB 再删缓存"（时序对比）

```sql
方案一（反例）：先删缓存再更 DB —— 脏数据窗口大且持久
  时刻      写线程A                  读线程B
   t1    DEL 缓存
   t2                            读缓存 miss
   t3                            读 DB → 旧值 V1
   t4    UPDATE DB = V2
   t5                            SET 缓存 = V1  ← 旧值被回填，直到 TTL 到期才自愈！

方案二（推荐）：先更 DB 再删缓存 —— 窗口极小且罕见
  时刻      写线程A                  读线程B
   t1                            读缓存 miss
   t2                            读 DB → 旧值 V1
   t3    UPDATE DB = V2
   t4    DEL 缓存
   t5                            SET 缓存 = V1  ← 仅当 B 的 DB 读跨越整个写事务（读比写还慢）
                                                才会发生，概率极低且有 TTL 兜底
```

### 8.4 延迟双删

先更 DB 再删缓存仍留一个窗口：主从架构下读线程从**从库**读到旧值并回填。补救：

```text
UPDATE DB;  DEL cache;  sleep(读业务耗时 + 主从延迟，如 500ms);  DEL cache;
```

### 8.5 订阅 binlog（canal）异步删缓存

```text
MySQL(binlog) ─► canal（伪装成从库拉 binlog）─► MQ（Kafka/RocketMQ）
                                                    │ 消费失败可重试/回放 offset
                                                    ▼
                                              消费者执行 DEL Redis key
```

业务代码零侵入（解耦），可靠性靠 MQ 重试，大厂标配，最终一致。

### 8.6 结论

缓存与 DB 的**强一致做不到也不值得**：要么读写都加分布式锁串行化（性能归零），要么不用缓存。工程选择 = Cache Aside + TTL 兜底 + 延迟双删 / binlog 异步删，接受秒级**最终一致**——CAP 下的标准取舍。

---

## 9. 分布式锁【高频】

按演进式回答，每一步都是一次踩坑：

| 阶段 | 写法 | 问题 |
| --- | --- | --- |
| ① | `SETNX lock 1` 再 `EXPIRE lock 10` | **两步非原子**：SETNX 后进程崩溃，EXPIRE 没执行 → 死锁 |
| ② | `SET lock <uuid> NX EX 10` | 一条命令原子加锁（2.6.12+）✅【标准答案】；但锁超时自动释放后会**误删别人的锁** |
| ③ | 唯一 value + Lua 原子"校验并删除" | 解决误删 ✅；但业务耗时不可预估，TTL 设多短都可能提前失效 |
| ④ | 看门狗续期（Redisson watchdog） | 解决超时 ✅；主从切换仍可能丢锁 |
| ⑤ | RedLock / 换 ZooKeeper | 仍有争议（见 9.4） |

### 9.1 加锁标准命令

```bash
SET lock:order:1001 "uuid-7f3a" NX EX 10
# NX：不存在才设置（互斥）；EX 10：10 秒自动过期（防死锁）
# value 必须是唯一标识（uuid / uuid+线程id），是"这把锁是我的"凭证
```

### 9.2 解锁：唯一值 + Lua 原子"校验 + 删除"

```text
-- KEYS[1] = 锁 key，ARGV[1] = 加锁时写入的唯一标识
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])   -- 确实是我的锁才删
else
    return 0                              -- 不是我的（已被别人持有或已过期），不动
end
```

GET + DEL 必须放 Lua：Redis 执行脚本期间不允许插入其他客户端命令，"校验 + 删除"才是原子动作；拆成两条命令中间就可能插进别人的操作。

### 9.3 看门狗续期

TTL 是兜底不是精确控制。业务时长不可预估 → Redisson 思路：加锁不指定 leaseTime 时默认锁 30 秒，**后台线程每 10 秒（1/3 周期）检查**，业务未完成就重置 TTL；客户端崩溃则无人续期，锁到期自然释放不会死锁。C++ 可自实现：持锁线程 + 定时器线程（《../04-并发编程/02-互斥锁与死锁.md》），续期同样用 Lua"值匹配才 EXPIRE"。

### 9.4 主从切换锁丢失与 RedLock 争议

主从复制异步：锁写在主库、未同步到从库时主库宕机 → 新主上锁不存在 → 第二个客户端加锁成功 → **两个客户端同时持锁**。

- RedLock：向 N 个（通常 5 个）**相互独立**（非主从）的 Redis 实例依次加锁，**多数派（≥ N/2+1）成功且总耗时小于锁有效期**才算持锁。
- 争议：Martin Kleppmann（《DDIA》作者）指出 GC 停顿 / 时钟跳变会破坏安全性，antirez 反驳认为时钟可控。一句话结论：**绝大多数业务用"单实例 + 唯一值 + Lua + 看门狗"已够；金融级强正确性改用 ZooKeeper / etcd（CP 系统）或加 fencing token（递增令牌，下游拒绝旧令牌）**。

### 9.5 C++ 实现提示（hiredis）

```text
// 加锁（客户端细节见第 11 章）
redisReply* r = (redisReply*)redisCommand(ctx, "SET lock:%s %s NX EX 10", res_id, uuid);
// r->type == REDIS_REPLY_STATUS 且 strcmp(r->str, "OK") == 0 即成功
// 解锁：EVAL 执行 9.2 的 Lua（1 个 KEY + 1 个 ARGV）
// 要点：锁 key 带资源粒度（别全局一把）；失败指数退避重试；连接来自连接池
```

---

## 10. 内存与性能优化

### 10.1 bigkey

参考标准：String > 1MB、集合元素 > 5000~10000 即偏大（无官方硬标准，按业务定）。

| 危害 | 说明 |
| --- | --- |
| 网络与服务阻塞 | 单线程序列化/传输大 value 期间所有命令排队（Redis CPU 高先查大 key，衔接《../07-调试与测试/04-性能分析与基准测试.md》） |
| 删除卡顿 | `DEL` 大集合 O(N)，集中过期时定期删除也卡 |
| 迁移超时 | Cluster reshard / MIGRATE 大 key 易超时失败 |
| 数据倾斜 | Cluster 下某节点内存远超其他 |

排查：`redis-cli --bigkeys`（采样）、`MEMORY USAGE key`（精确）、SCAN 遍历、离线分析 RDB（rdb-tools 类工具）。治理：大 JSON 拆 Hash 字段或按业务拆 key；集合用 HSCAN/SCAN 分批读再分批删；删除一律 `UNLINK`。

### 10.2 hotkey

| 排查 | 应对 |
| --- | --- |
| `redis-cli --hotkeys`（需 LFU 策略）、低峰短暂 MONITOR、客户端/代理埋点统计 | 进程内本地缓存兜底、读写分离、key 加随机后缀打散到多节点 |

### 10.3 pipeline vs mget vs Lua

| 方式 | 原理 | 原子性 | 适用 |
| --- | --- | --- | --- |
| pipeline | 客户端攒一批命令一次网络往返，省 N-1 次 RTT | ❌ 非原子（中间可插入其他客户端命令） | 批量无依赖命令，RTT 占比高时收益最大 |
| `MGET` / `MSET` | 服务端原生批量命令 | ✅ 单命令原子 | 恰好是 String 的批量读写 |
| Lua（EVAL） | 服务端执行脚本期间不插入其他命令 | ✅ 原子 + 可写逻辑 | "读→判断→写"复合逻辑（解锁、滑动窗口限流） |

### 10.4 慢查询

```bash
CONFIG SET slowlog-log-slower-than 10000   # 微秒，默认 10000 = 10ms
CONFIG SET slowlog-max-len 1024            # 日志条数，默认 128
SLOWLOG GET 10    # 只统计命令执行耗时，不含网络与排队
SLOWLOG LEN / SLOWLOG RESET
```

### 10.5 内存碎片

`mem_fragmentation_ratio = used_memory_rss / used_memory`（INFO memory，物理/逻辑）：

| 比值 | 判断 | 处理 |
| --- | --- | --- |
| < 1 | 物理内存小于逻辑使用 → 有页被换到 **swap**（性能悬崖级警报） | 排查机器内存压力，避免 swap |
| 1 ~ 1.5 | 健康 | — |
| > 1.5 | 碎片偏高（频繁改值、大量增删留空洞） | 4.0+ 开 `activedefrag yes`（需 jemalloc），或低峰重启 / 主从切换重建 |

---

## 11. 与 C++ 服务集成

### 11.1 hiredis 基础

| API | 说明 |
| --- | --- |
| `redisConnect` / `redisConnectWithTimeout` | 建立 TCP 连接得到 `redisContext`（**单个 context 非线程安全**） |
| `redisCommand(ctx, "SET %s %b", k, v, len)` | printf 风格；`%b` 传二进制安全数据（指针+长度） |
| `redisAppendCommand` + `redisGetReply` | pipeline：批量入队后逐个取回复 |
| `freeReplyObject` / `redisFree` | 释放回复与连接（C++ 用 RAII 封装，参考《../01-语言基础/04-内存管理与智能指针.md》） |

| redisReply 类型 | 含义 | 常用字段 |
| --- | --- | --- |
| `REDIS_REPLY_STRING` | bulk 字符串 | `str` / `len` |
| `REDIS_REPLY_ARRAY` | 数组（可嵌套） | `elements` / `element[]` |
| `REDIS_REPLY_INTEGER` | 整数（INCR 的返回） | `integer` |
| `REDIS_REPLY_STATUS` | 状态（如 +OK） | `str` |
| `REDIS_REPLY_ERROR` | 错误（-ERR ...） | `str`，**必须检查否则静默失败** |
| `REDIS_REPLY_NIL` | 空值（GET 不存在的 key） | — |

### 11.2 连接池要点

| 要点 | 说明 |
| --- | --- |
| 为什么池化 | 每请求建连 = 三次握手 + AUTH + 断连，高 QPS 开销巨大（与《../03-网络编程/02-IO多路复用与Reactor模型.md》连接池同思路） |
| 容量估算 | 连接数 ≈ QPS × 平均命令耗时（Little 定律），留余量；上限受 `maxclients`（默认 10000）与 fd 限制 |
| 复用与超时 | 复用前检查 `ctx->err`；断连要有重建逻辑；显式设 connect / read / write 超时 |
| 线程安全 | context 不能跨线程共享 → 每线程独占连接，或池 + 互斥 / 无锁队列 |

### 11.3 RESP2 协议一眼速览

```text
客户端发送 SET foo bar（RESP 数组：* 元素个数，$ 每项字节数）：
  *3\r\n$3\r\nSET\r\n$3\r\nfoo\r\n$3\r\nbar\r\n

服务端回复：
  +OK\r\n            状态         GET foo → $3\r\nbar\r\n   bulk 字符串
  :1\r\n             整数(INCR)   GET nokey → $-1\r\n       nil
  -ERR ...\r\n       错误         数组      → *2\r\n...
```

文本协议、自描述、可 telnet 手敲调试；6.0 起可选 RESP3（`HELLO 3`，新增 map / set / push 等类型）。注意：`INCR` 回的是整数类型，同 key 用 `GET` 读出来却是字符串 `"1"`，客户端要自己转数字——RESP 不带 schema。

---

## 12. 快速参考卡片

| 场景 | 直接这么答 / 做 |
| --- | --- |
| 做排行榜 | `ZINCRBY` 加分 → `ZREVRANK` 查名次 → `ZREVRANGE 0 9 WITHSCORES` 取 Top10 → `ZCOUNT` 区间人数 |
| 做签到 | `SETBIT sign:uid:202608 天-1 1` → `BITCOUNT` 本月天数 → `BITPOS` 找漏签 |
| 统计 UV | `PFADD` → `PFCOUNT` → `PFMERGE` 合并月活（固定 12KB，误差 0.81%） |
| 做附近的人 | `GEOADD` 存坐标 → `GEOSEARCH FROMLONLAT ... BYRADIUS 1 km ASC COUNT 10` |
| 做消息队列 | Stream：`XADD` → `XREADGROUP` → `XACK`；别用 List（无 ACK，消费失败即丢） |
| 单线程为什么快 | 纯内存 + epoll 多路复用（单线程管万级连接）+ 无锁无切换 + 特化数据结构；6.0 只是 IO 线程并行，命令仍串行 |
| Redis 挂了怎么办（分层） | ① 实例重启：混合持久化快速恢复；② 主库故障：哨兵 / Cluster 自动切主；③ 整体不可用：客户端限流降级、DB 兜底 + 事后预热 |
| 缓存不一致怎么答（三句） | 写路径 Cache Aside"先更 DB 再删缓存"；强一致做不到，靠 TTL + 延迟双删 / binlog(canal) 异步删做最终一致；要求极高就别上缓存或读写都走 DB |
| 分布式锁怎么写（四步） | SETNX+EXPIRE 非原子死锁 → `SET NX EX` 原子加锁 → 唯一 value + Lua 校验删除防误删 → 看门狗续期；主从丢锁才考虑 RedLock / etcd |
| 三大缓存问题速记 | 穿透=数据不存在（空值+布隆）；击穿=热点 key 过期（互斥/逻辑过期）；雪崩=大面积失效或宕机（TTL 抖动+高可用+限流） |
| 为什么 16384 槽 | CRC16(key)%16384；心跳槽位 bitmap 65536 要 8KB 太大，且集群主节点上限约 1000，16384 足够 |
| Redis 变慢怎么查 | `SLOWLOG GET` → `--bigkeys` / `--hotkeys` / `--latency` → `INFO memory` 看碎片与淘汰 → perf 火焰图（《../07-调试与测试/04-性能分析与基准测试.md》） |
| 找 key / 删 key | 遍历用 SCAN（禁 KEYS）；删大 key 用 UNLINK + 分批 |

---

## 13. 常见问题与坑

| 问题 | 原因与解决方案 |
| --- | --- |
| 生产执行 `KEYS *` 全站卡顿【高频】 | O(N) 遍历且阻塞唯一命令线程。改用 `SCAN` 游标增量遍历，并限制扫描频率 |
| `DEL` 百万元素集合卡主线程几秒 | 同步删除 O(N)。改用 `UNLINK`（4.0+ 后台线程回收），或 SCAN/HSCAN 分批删 |
| `HGETALL` / `SMEMBERS` / `LRANGE 0 -1` 大集合超时 | 一次返回全部元素，序列化与传输阻塞。用 HSCAN/SSCAN 游标分页，业务侧限制集合规模 |
| `INCR` 的结果用 `GET` 读出字符串 "5" | RESP 无类型标记：INCR 返回整数类型，GET 返回 bulk 字符串。客户端自行转数字，或直接用 INCR 的返回值 |
| 给 Hash 某字段设过期没生效 | `EXPIRE` 作用于**整个 key**；7.4 前无字段级 TTL（7.4 起 HEXPIRE 支持 Hash 字段），List/Set/ZSet 元素至今无元素级过期——需拆 key 或业务搬移 |
| 配了 everysec 仍丢几秒数据 | everysec 的 fsync 在后台线程，磁盘慢时下一次 fsync 最长约 2 秒才阻塞写；极端宕机丢 1~2 秒属预期。要求更强用 always 或混合持久化 |
| 读写分离读到旧值 | 复制是异步的，从库有延迟。读己之写走主库；关键路径用 `WAIT numreplicas timeout` 显式等待 |
| Cluster 下 `MGET` 报 CROSSSLOT | 多 key 命令要求同槽。用 hash tag `{user1}:a` / `{user1}:b`，或客户端按槽分组请求再聚合 |
| 布隆过滤器说"存在"但 DB 查不到 | 误判是特性（只保证"不存在"必对）。残留穿透用空值缓存兜底；标准 BF 不支持删除，需定期全量重建（或换计数布隆 / 布谷鸟过滤器） |
| 报 `max number of clients reached` | 连接打满：连接池泄漏不归还、空闲连接不释放。`CLIENT LIST` 排查来源，设合理 maxclients 与 timeout，修泄漏 |
| `SETNX` 抢到锁后进程崩溃 → 死锁 | 加锁与设过期两条命令非原子。用 `SET key value NX EX n` 一条命令完成【高频】 |
| 锁超时业务没跑完，删了别人的锁 | 误删。value 存唯一 uuid，解锁用 Lua"GET 匹配才 DEL"，再加看门狗续期 |
| 缓存空值把内存撑爆 | 空值也占内存。短 TTL（30~120 秒）+ 布隆过滤器前置 + 非法参数直接拒 |
| 内存碎片率持续 > 2 且增长 | 频繁增删改留下空洞。4.0+ 开 activedefrag，或低峰重启 / 主从切换重建 |
| 主从频繁全量复制（复制风暴） | repl_backlog 太小或网络抖动致 offset 被覆盖。调大 `repl-backlog-size`、从库级联、开无盘复制 |
| 大 key 过期时周期性卡顿 | 定期删除同步释放大 key 内存。`lazyfree-lazy-expire yes`（4.0+）让过期回收走后台线程 |
| bgsave 后断电，恢复后丢数据 | RDB 只是快照，两次快照间必丢。开混合持久化用 AOF 增量兜底才能缩到秒级 |

---

上一篇：《01-MySQL数据库精要.md》
下一篇：《03-Protobuf序列化协议.md》
