# Redis 深入：复制、哨兵、集群与分布式锁

> 本节目标：掌握 Redis 高可用与分布式工程实践。覆盖主从复制与 psync 细节、Sentinel 故障转移与脑裂防护、Cluster 16384 槽位与 gossip 通信及重新分片、缓存三兄弟（击穿/穿透/雪崩）的工程级方案、分布式锁的 SET NX EX + Lua 原子性与 Redlock 争议及看门狗续期 C++ 实现。学完后能从复制与槽位角度理解集群架构、设计缓存防护方案、并在 C++ 中实现可靠的分布式锁。协议与存储原理见《06-Redis深入：协议与存储原理.md》；前置阅读：《02-Redis设计与数据结构.md》《../14-内核云原生与分布式/05-检测组件与分布式锁.md》。

## 本章速览

- [1. 主从复制深入](#1-主从复制深入)
- [2. Sentinel 哨兵深入](#2-sentinel-哨兵深入)
- [3. Cluster 集群深入](#3-cluster-集群深入)
- [4. 缓存三兄弟：工程级解决方案](#4-缓存三兄弟工程级解决方案)
- [5. 分布式锁深入](#5-分布式锁深入)
- [6. 快速参考卡片](#6-快速参考卡片)
- [7. 常见坑与最佳实践](#7-常见坑与最佳实践)

---

## 1. 主从复制深入

### 1.1 全量复制与增量复制

Redis 主从复制分为两个阶段：

**全量复制（Full Resynchronization）**：
1. 从节点执行 `SLAVEOF`（或 `REPLICAOF`），向主节点发送 `PSYNC ? -1`（首次复制，不知道 runid 和 offset）。
2. 主节点返回 `+FULLRESYNC <runid> <offset>`。
3. 主节点执行 `BGSAVE` 生成 RDB 文件，期间的写命令写入复制积压缓冲区。
4. RDB 生成完毕后发送给从节点，从节点清空本地数据并加载 RDB。
5. 主节点将积压缓冲区中的写命令发送给从节点执行。
6. 全量复制完成，进入增量复制阶段。

**增量复制（Partial Resynchronization）**：
网络闪断后重连时，从节点发送 `PSYNC <runid> <offset>`（携带上次复制的主节点 runid 和已同步到的偏移量）：
- 如果 runid 匹配且 offset 之后的数据仍在复制积压缓冲区中：主节点返回 `+CONTINUE`，发送积压的写命令，增量复制完成。
- 否则：返回 `+FULLRESYNC`，触发全量复制。

### 1.2 psync 命令与 runid/offset

`PSYNC` 是 Redis 2.8 引入的命令，替代旧版 `SYNC`（只支持全量复制）。

- **runid**：每个 Redis 节点启动时生成的唯一 40 字符随机 ID（类似 `1d8d7f6a...`）。从节点记录主节点的 runid，重连时比对。如果主节点重启过（runid 变化），必须全量复制。
- **offset（复制偏移量）**：主节点维护 `master_repl_offset`，每发送一个字节的写命令就累加。从节点维护 `slave_repl_offset`，每接收并执行一个字节就累加。两者差值表示从节点落后的字节数。

```bash
# WSL Ubuntu 24.04 实跑：查看复制信息
redis-cli INFO replication
# 示例输出：
# # Replication
# role:master
# connected_slaves:1
# slave0:ip=127.0.0.1,port=6380,state=online,offset=12345,lag=0
# master_replid:1d8d7f6a5b4c3d2e1f0a9b8c7d6e5f4a3b2c1d0e
# master_replid2:0000000000000000000000000000000000000000
# master_repl_offset:12345
# second_repl_offset:-1
# repl_backlog_active:1
# repl_backlog_size:1048576
# repl_backlog_first_byte_offset:11000
# repl_backlog_histlen:1346
```

`master_replid2` 和 `second_repl_offset` 用于故障转移后：旧主节点降级为从节点时，记录之前的 replid 和 offset，让从节点能增量同步到新主节点。

### 1.3 复制积压缓冲区（repl backlog）

复制积压缓冲区是主节点维护的一个**固定大小环形缓冲区**，存储最近的写命令。默认大小 1MB（`repl-backlog-size`）。

工作机制：
- 主节点每执行一个写命令，就将命令追加到 backlog 中，同时记录每个字节对应的 offset。
- backlog 是环形的，写满后覆盖最旧的数据。
- 从节点重连时请求 offset，如果该 offset ≥ `repl_backlog_first_byte_offset`（backlog 中最旧数据的 offset），则可以增量复制。

**backlog 大小的选择**：
- 太小：网络闪断稍久就需要全量复制，开销大。
- 太大：浪费内存。
- 估算公式：`backlog_size > 平均重连时间 × 主节点平均写带宽`。例如主节点每秒写 100KB，通常闪断 10 秒内恢复，则 backlog 至少 1MB，建议设为 2-4MB 留余量。

`repl-backlog-ttl` 控制没有从节点时 backlog 保留多久后释放（默认 3600 秒）。

### 1.4 复制偏移量与心跳

主从节点之间通过心跳维持连接和同步状态：

- **从节点 → 主节点**：每秒发送 `REPLCONF ACK <offset>`，告知主节点自己的同步进度。主节点据此：
  - 计算从节点延迟（`lag`）。
  - 发现从节点 offset 落后，补发数据（如果在 backlog 中）。
  - `min-replicas-to-write` / `min-replicas-max-lag` 配置：如果从节点数量不足或延迟过大，主节点拒绝写入，防止脑裂。

- **主节点 → 从节点**：默认每 10 秒发送 `PING`（`repl-ping-slave-period`），检测从节点存活。

**复制超时**：`repl-timeout`（默认 60 秒），如果主节点超过该时间未收到从节点的 REPLCONF ACK，或从节点未收到主节点的 PING/数据，则认为连接断开，触发重连。

---

## 2. Sentinel 哨兵深入

### 2.1 故障发现：主观下线与客观下线

Sentinel 是 Redis 的高可用方案，由一组 Sentinel 节点（通常 3 个，奇数）监控主从集群。

**主观下线（Subjectively Down，SDOWN）**：
单个 Sentinel 节点向主节点发送 `PING`，如果在 `down-after-milliseconds` 内未收到有效回复（+PONG / -LOADING / -MASTERDOWN），则该 Sentinel 单方面认为主节点主观下线。

SDOWN 是单个 Sentinel 的判断，可能是网络分区导致的误判，需要多个 Sentinel 共识。

**客观下线（Objectively Down，ODOWN）**：
Sentinel 节点之间通过 `SENTINEL is-master-down-by-addr` 命令交换对主节点状态的判断。当收到 `quorum` 个（通常配置为 `quorum = N/2 + 1`）Sentinel 节点都认为主节点 SDOWN 时，主节点被标记为客观下线。

ODOWN 是集群共识结果，触发故障转移。

> 注意：SDOWN 用于主节点，从节点和 Sentinel 节点的故障检测只需 SDOWN（不需要客观下线），因为从节点故障不需要故障转移。

### 2.2 故障转移：选举与切换

ODOWN 后，进入故障转移流程：

**第一步：选举领头 Sentinel（Leader Election）**：
- 每个认为主节点 ODOWN 的 Sentinel 向其他 Sentinel 发送 `SENTINEL is-master-down-by-addr` 命令，携带自己的 `runid`，请求投票。
- 收到请求的 Sentinel 如果还没投给别人，就投给第一个请求者（先到先得）。
- 获得超过半数（`quorum`）投票的 Sentinel 成为领头 Sentinel，负责执行故障转移。
- 如果选举失败（没有获得足够票数），等待 `sentinel failover-timeout * 2` 后重新选举。

这是 Raft 算法的简化版：每个 term（纪元）内每个 Sentinel 只能投一票，先到先得，多数派胜出。

**第二步：从从节点中选举新主节点**：
领头 Sentinel 按以下优先级选择新主：
1. 过滤掉：已下线、断线 5 秒以上（`down-after` 的 5 倍）、与原主节点断开连接超过 `down-after * 10` 的从节点（数据可能太旧）。
2. 按 `slave-priority`（`replica-priority`）排序，优先级值越小越优先（0 表示永远不选为主）。
3. 优先级相同则按复制偏移量 `slave_repl_offset` 排序，offset 越大（数据越新）越优先。
4. offset 也相同则按 `runid` 字典序排序（最小的胜出，保证确定性）。

**第三步：执行故障转移**：
1. 领头 Sentinel 向选中的从节点发送 `SLAVEOF NO ONE`，使其升级为主节点。
2. 领头 Sentinel 向其他从节点发送 `SLAVEOF <new_master_ip> <new_master_port>`，让它们复制新主节点。
3. 原主节点恢复后，Sentinel 会让它成为新主节点的从节点（`SLAVEOF`）。
4. 更新 Sentinel 集群的配置，广播新主节点信息。

### 2.3 配置中心与客户端发现

Sentinel 同时充当**配置中心**：客户端连接 Sentinel 节点，通过 `SENTINEL get-master-addr-by-name <master-name>` 获取当前主节点地址。

客户端典型工作流程：
1. 启动时连接 Sentinel 节点列表（配置多个，防止单点）。
2. 向任意可用 Sentinel 查询主节点地址。
3. 连接主节点进行读写。
4. 订阅 Sentinel 的 `+switch-master` 频道（Pub/Sub），主节点切换时收到通知，自动重连到新主。

Sentinel 节点本身也会故障，客户端应配置至少 3 个 Sentinel 地址。Sentinel 节点之间通过 gossip 协议互相发现和同步状态。

### 2.4 脑裂问题与 min-replicas

**脑裂（Split Brain）**：网络分区导致原主节点与 Sentinel 集群和从节点隔离，但原主节点仍在运行并接受客户端写入。此时 Sentinel 选举了新主节点，分区恢复后出现两个主节点，数据不一致。

防护措施：
1. **`min-replicas-to-write`**：主节点必须至少有 N 个从节点连接，否则拒绝写入。默认 0（不限制）。
2. **`min-replicas-max-lag`**：从节点延迟（lag）必须小于该值（秒），否则不算有效连接。默认 10。

例如配置 `min-replicas-to-write 1` + `min-replicas-max-lag 10`：主节点至少有 1 个延迟 <10 秒的从节点才接受写入。网络分区后原主节点与从节点断开，不满足条件，拒绝写入，避免脑裂数据。

代价：如果所有从节点都故障，主节点也无法写入，可用性降低。生产环境建议至少 2 个从节点，配置 `min-replicas-to-write 1`。

---

## 3. Cluster 集群深入

### 3.1 16384 槽位与 key 路由

Redis Cluster 采用**数据分片**而非主从复制来扩展。整个 key 空间被划分为 **16384 个哈希槽（hash slot）**，每个节点负责一部分槽位。

**key → 槽位映射算法**：
```text
slot = CRC16(key) mod 16384
```

CRC16 是 16 位循环冗余校验，输出 0~65535，对 16384 取模得到 0~16383。

**为什么是 16384（2^14）个槽位**：
- 槽位信息在节点间通过 gossip 消息传播，消息头中用 bitmap 表示节点负责的槽位：16384 bit = 2KB。如果用 65536 个槽位则是 8KB，gossip 消息过大，网络开销高。
- 16384 个槽位对于通常的集群规模（最多 1000 节点）足够，每个节点平均 16 个槽位，迁移粒度合适。
- 官方说明：集群节点数通常不超过 1000，16384 是合理上限。

**客户端路由**：
- 客户端计算 key 的槽位，发送到负责该槽位的节点。
- 如果发送到错误节点，节点返回 `MOVED <slot> <ip:port>`，客户端缓存槽位映射并重试。
- 槽位迁移过程中，节点返回 `ASK <slot> <ip:port>`，客户端需发送 `ASKING` 命令后再重试（ASK 不更新本地缓存，因为迁移未完成）。

### 3.2 gossip 通信与节点握手

Cluster 节点之间通过 **gossip 协议**交换集群状态信息，使用专门的集群总线端口（客户端端口 + 10000，如客户端 6379，总线 16379）。

**gossip 消息类型**：
- `PING`：节点每秒随机向几个其他节点发送 PING，携带自己的状态和已知的其他节点状态（gossip 信息）。
- `PONG`：对 PING 的回复，也携带 gossip 信息。
- `MEET`：新节点加入时发送，通知其他节点有新节点加入。
- `FAIL`：节点判定另一个节点故障时广播。
- `PUBLISH`：Pub/Sub 消息在集群总线传播。

**节点握手流程**：
1. 新节点启动（配置 `cluster-enabled yes`），但还不知道其他节点。
2. 客户端执行 `CLUSTER MEET <ip> <port>`，让新节点与已有节点握手。
3. 两个节点互发 PING/PONG，交换 gossip 信息，新节点逐渐通过 gossip 发现所有其他节点。
4. 所有节点互相认识后，集群进入正常状态，但需要分配槽位才能处理命令。

**gossip 的最终一致性**：节点状态传播是异步的，可能存在短暂不一致（如一个节点刚加入，部分节点还不知道）。最终所有节点状态会收敛一致。

### 3.3 故障转移与故障检测

Cluster 的故障检测与 Sentinel 类似，但由集群节点自身完成（不需要独立的 Sentinel 进程）。

**故障检测**：
- 每个节点定期向其他节点发送 PING，未在 `cluster-node-timeout` 内收到 PONG 则标记为 **PFAIL**（Possible Failure，主观下线）。
- 节点通过 gossip 收集其他节点对某节点的 PFAIL 报告。如果一个节点收到超过半数**主节点**对某节点的 PFAIL 报告，则将其标记为 **FAIL**（客观下线），并广播 FAIL 消息。

**故障转移**（仅针对主节点）：
1. 故障主节点的从节点中，复制偏移量最大的（数据最新的）触发故障转移。
2. 从节点向所有其他主节点请求投票（`FAILOVER_AUTH_REQUEST`）。
3. 获得超过半数主节点投票的从节点升级为主节点。
4. 新主节点广播 PONG 通知集群，接管原主节点的槽位。
5. 其他从节点复制新主节点。

与 Sentinel 的区别：Cluster 的投票者是其他主节点（而非 Sentinel 节点），从节点既是数据副本也是故障转移参与者。

### 3.4 hash tag 与多 key 命令

默认情况下，多 key 命令（如 `MGET`、`SUNION`、事务）要求所有 key 在同一个槽位，否则返回 `CROSSSLOT Keys in request don't hash to the same slot`。

**hash tag** 机制允许控制 key 的槽位：如果 key 中包含 `{...}`，则只对 `{}` 内的字符串计算 CRC16。

```text
user:{1001}:profile  → CRC16("1001") mod 16384
user:{1001}:orders   → CRC16("1001") mod 16384
user:{1001}:messages → CRC16("1001") mod 16384
```

这三个 key 都路由到同一个槽位，可以安全地使用多 key 命令或事务。

**hash tag 的使用场景**：
- 用户维度的数据聚合：同一用户的 profile、orders、messages 放同一槽位。
- 计数器与数据关联：`count:{article_id}` 和 `article:{article_id}` 放同一节点。
- 避免 hash tag 滥用：如果所有 key 都用同一个 tag，所有数据集中到一个槽位，失去分片意义。

### 3.5 重新分片与迁移

集群扩容时需要将部分槽位从旧节点迁移到新节点：

```bash
# WSL Ubuntu 24.04 实跑：使用 redis-cli --cluster 管理
# 查看集群槽位分布
redis-cli --cluster check 127.0.0.1:6379

# 重新分片：将 1000 个槽位从节点迁移到新节点
redis-cli --cluster reshard 127.0.0.1:6379 \
  --cluster-from <old_node_id> \
  --cluster-to <new_node_id> \
  --cluster-slots 1000 \
  --cluster-yes
```

**迁移过程**（在线迁移，不阻塞服务）：
1. 标记槽位为迁移中（migrating），源节点标记 importing（目标节点）。
2. 逐个迁移 key：源节点对每个 key 执行 `DUMP` + `DEL`，目标节点执行 `RESTORE`。
3. 迁移过程中，客户端访问 key：
   - key 还在源节点：正常处理。
   - key 已迁移到目标节点：源节点返回 `ASK` 重定向。
4. 所有 key 迁移完成后，发送 `CLUSTER SETSLOT <slot> NODE <new_node>` 完成槽位所有权转移。

大 key 迁移会阻塞源节点（DUMP/RESTORE 大 key 耗时），生产环境应避免 bigkey，或在低峰期迁移。

---

## 4. 缓存三兄弟：工程级解决方案

《02-Redis设计与数据结构.md》第 7 章已介绍缓存三兄弟的基本概念，本节深入工程级实现方案。

### 4.1 缓存击穿：热点 key 过期

**场景**：某个热点 key（如秒杀商品库存）过期瞬间，大量并发请求同时穿透到数据库，数据库压力骤增。

**方案一：互斥锁（Mutex Key）**：

```cpp
// C++ 伪代码
std::string getWithMutex(const std::string& key) {
    std::string val = redis.get(key);
    if (!val.empty()) return val;

    // 尝试加锁
    std::string lockKey = "lock:" + key;
    bool locked = redis.set(lockKey, "1", SET_NX | SET_EX, 10); // 10秒过期
    if (locked) {
        // 拿到锁，查 DB 并回写缓存
        val = db.query(key);
        redis.set(key, val, EX, 300);
        redis.del(lockKey);
        return val;
    } else {
        // 没拿到锁，等待重试
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
        return getWithMutex(key); // 递归重试，需加最大重试次数
    }
}
```

注意：锁必须有过期时间（防止持有者崩溃导致死锁）；重试需有最大次数和退避策略。

**方案二：逻辑过期（Logical Expiration）**：

不设置 Redis 物理过期时间，而是在 value 中嵌入逻辑过期时间：

```cpp
struct CacheData {
    std::string data;
    std::chrono::system_clock::time_point expireAt; // 逻辑过期时间
};

std::string getWithLogicalExpire(const std::string& key) {
    CacheData cd = redis.get<CacheData>(key); // 反序列化
    if (cd.data.empty()) return ""; // key 不存在

    if (cd.expireAt > std::chrono::system_clock::now()) {
        return cd.data; // 未过期，直接返回
    }

    // 已过期，异步重建缓存（不阻塞当前请求）
    std::string lockKey = "lock:" + key;
    if (redis.set(lockKey, "1", SET_NX | SET_EX, 10)) {
        std::thread([key]() {
            std::string newVal = db.query(key);
            CacheData newCd{newVal, now() + 300s};
            redis.set(key, serialize(newCd));
            redis.del(lockKey);
        }).detach();
    }

    return cd.data; // 返回旧数据（可接受短暂不一致）
}
```

优点：请求永远不阻塞（返回旧数据）；缺点：内存中 key 永不过期（需要主动清理或设置很长的物理过期兜底），存在短暂数据不一致。

**方案三：热点 key 永不过期 + 主动更新**：
对于确定的热点 key（如首页配置），不设过期时间，由后台定时任务主动更新缓存。

### 4.2 缓存穿透：不存在的 key

**场景**：查询一个数据库和缓存中都不存在的 key（如恶意攻击构造不存在的用户 ID），每次请求都打到数据库。

**方案一：缓存空值（Cache Null）**：

```cpp
std::string getWithNullCache(const std::string& key) {
    std::string val = redis.get(key);
    if (val == "__NULL__") return "";      // 缓存的空值
    if (!val.empty()) return val;            // 正常缓存

    std::string dbVal = db.query(key);
    if (dbVal.empty()) {
        redis.set(key, "__NULL__", EX, 60); // 缓存空值，短过期
        return "";
    }
    redis.set(key, dbVal, EX, 300);
    return dbVal;
}
```

空值过期时间要短（通常 30-120 秒），防止数据新增后长时间不可用。

**方案二：布隆过滤器（Bloom Filter）**：

在缓存前加一层布隆过滤器，将所有存在的 key 的哈希值存入布隆过滤器。查询时先过布隆过滤器：
- 布隆过滤器说不存在 → 一定不存在，直接返回，不查缓存和 DB。
- 布隆过滤器说存在 → 可能存在（有误判率），继续查缓存和 DB。

```cpp
// C++ 伪代码：使用 RedisBloom 模块或自研布隆过滤器
class BloomCache {
    BloomFilter bf; // 启动时从 DB 加载所有合法 key
public:
    std::string get(const std::string& key) {
        if (!bf.mightContain(key)) return ""; // 一定不存在
        std::string val = redis.get(key);
        if (!val.empty()) return val;
        return db.query(key);
    }
};
```

布隆过滤器的优点是省内存（1 亿 key 只需约 100MB，误判率 1%），缺点是存在误判（可能放过不存在的 key）且删除困难（需要计数布隆过滤器）。

**方案三：接口层参数校验**：
对明显非法的请求（如 ID 为负数、格式不对）在接口层直接拒绝，从源头减少穿透。

### 4.3 缓存雪崩：大量 key 同时过期

**场景**：大量缓存 key 在同一时刻过期（如批量设置了相同的过期时间），或 Redis 节点宕机，导致大量请求同时打到数据库。

**方案一：过期时间加随机偏移**：

```cpp
// 设置过期时间时加随机值，避免集中过期
int baseTTL = 300; // 5 分钟
int jitter = rand() % 120; // 0~120 秒随机偏移
redis.set(key, value, EX, baseTTL + jitter);
```

这是最简单有效的方案，将过期时间打散在 5~7 分钟范围内，避免同时过期。

**方案二：多级缓存**：

```text
请求 → 本地缓存（Caffeine/自研 LRU） → Redis 分布式缓存 → DB
```

本地缓存作为一级缓存，即使 Redis 中的 key 过期，本地缓存可能还有数据（本地缓存过期时间设得更长或用不同的过期策略），减少穿透到 DB 的请求。本地缓存容量有限，只存热点数据。

**方案三：Redis 高可用集群**：

避免 Redis 单点故障导致雪崩：
- 主从 + Sentinel：主节点故障自动切换。
- Cluster：多节点分片，单节点故障只影响部分槽位。
- 客户端熔断降级：Redis 不可用时，本地缓存兜底或返回默认值，不直接打 DB。

**方案四：限流降级**：
在数据库前加限流（如令牌桶），超过阈值的请求直接返回降级数据（如默认值、缓存的旧数据），保护数据库不被打垮。

### 4.4 三者对比与方案选型表

| 问题 | 触发原因 | 核心方案 | 辅助方案 |
|------|----------|----------|----------|
| 缓存击穿 | 单个热点 key 过期 | 互斥锁 / 逻辑过期 | 热点 key 永不过期 |
| 缓存穿透 | 查询不存在的 key | 缓存空值 / 布隆过滤器 | 参数校验 |
| 缓存雪崩 | 大量 key 同时过期 / Redis 宕机 | 过期时间随机偏移 / 高可用集群 | 多级缓存 / 限流降级 |

组合使用：生产环境通常同时部署"过期时间随机偏移 + 缓存空值 + 互斥锁（热点 key）+ Redis 高可用"，形成纵深防御。

---

## 5. 分布式锁深入

### 5.1 SET NX EX 基础锁

分布式锁的基础实现：

```bash
# 加锁：SET key value NX EX seconds
# NX = 不存在才设置（互斥），EX = 过期时间（防死锁）
SET lock:order:123 "unique_token" NX EX 30
```

- `NX` 保证互斥：只有一个客户端能设置成功。
- `EX 30` 保证锁不会永久持有：持有者崩溃后 30 秒自动释放。
- `value` 必须是唯一值（如 UUID + 线程 ID），用于释放锁时校验持有者身份，防止误删别人的锁。

**错误示范**：
```bash
# 错误1：先 SETNX 再 EXPIRE，非原子，中间崩溃导致锁永不过期
SETNX lock:order:123 1
EXPIRE lock:order:123 30

# 错误2：释放锁时不校验 value，可能删除别人的锁
DEL lock:order:123
```

### 5.2 Lua 脚本保证原子性

释放锁必须"校验 value + 删除"原子执行，用 Lua 脚本：

```lua
-- unlock.lua
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
```

```cpp
// C++ 调用
std::string unlockScript = R"(
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
)";

bool unlock(const std::string& key, const std::string& token) {
    redisReply* reply = (redisReply*)redisCommand(c,
        "EVAL %s 1 %s %s", unlockScript.c_str(), key.c_str(), token.c_str());
    bool success = reply && reply->type == REDIS_REPLY_INTEGER && reply->integer == 1;
    freeReplyObject(reply);
    return success;
}
```

Redis 执行 Lua 脚本是原子的：脚本执行期间不处理其他命令，保证"校验+删除"不会被打断。

### 5.3 Redlock 算法与争议

**问题**：单节点 Redis 分布式锁在主从切换时可能丢失锁：
1. 客户端 A 在主节点获取锁。
2. 主节点宕机，锁数据还未同步到从节点。
3. 从节点升级为主节点。
4. 客户端 B 在新主节点获取同一个锁。
5. A 和 B 同时持有锁 → 锁失效。

**Redlock 算法**（Redis 作者 antirez 提出）：
假设部署 N 个（通常 5 个）独立的 Redis 主节点（无主从关系）：
1. 客户端记录当前时间戳。
2. 依次向 N 个节点请求加锁（相同 key 和 value，短超时，如 5-50ms，防止单个节点慢阻塞）。
3. 计算成功加锁的节点数。如果 ≥ N/2 + 1（如 5 节点中 ≥3 个），且总耗时 < 锁过期时间，则认为加锁成功。
4. 加锁失败则向所有节点发送解锁命令（包括加锁失败的节点，因为可能加锁成功但回复丢失）。

**争议**（Martin Kleppmann 等学者批评）：
1. **依赖时间假设**：Redlock 假设各节点时钟同步且进程调度延迟可控。如果某个节点发生 GC pause 或时钟跳变，可能导致锁过期判断错误。
2. **性能开销大**：每次加锁需要访问 N 个节点，延迟高。
3. **实际场景中主从切换锁丢失概率极低**：配合 `min-replicas-to-write` 和合理的复制配置，单节点锁已足够。

**工程实践**：
- 大多数业务场景用单节点 `SET NX EX` + Lua 解锁即可，配合看门狗续期。
- 对锁安全性要求极高的场景（如金融扣款），建议用 etcd/ZooKeeper 的分布式锁（基于 Raft/ZAB 共识，不依赖时钟），或在数据库层面用乐观锁/唯一索引兜底。
- Redlock 在实际生产中使用较少，更多是学术讨论。

> 来源：《Redis设计与实现》黄健宏；antirez 博客 "Redlock: Is this algorithm actually safe?"；Martin Kleppmann "How to do distributed locking"。

### 5.4 看门狗续期与 C++ 实现

**问题**：锁的过期时间难以设置：
- 太短：业务逻辑还没执行完锁就过期了，其他客户端获取锁，并发问题。
- 太长：持有者崩溃后，锁要等很久才释放，影响可用性。

**看门狗（Watchdog）续期**：
加锁成功后，启动一个后台定时任务（看门狗），每隔锁过期时间的 1/3（如锁 30 秒，每 10 秒）检查锁是否仍被当前线程持有，如果是则续期（延长过期时间）。业务执行完释放锁时停止看门狗。

```cpp
class DistributedLock {
    std::string key_;
    std::string token_;
    int ttlSeconds_;
    std::atomic<bool> locked_{false};
    std::thread watchdog_;

    // Lua 续期脚本：校验 value 后延长过期时间
    static constexpr const char* kRenewScript = R"(
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('expire', KEYS[1], ARGV[2])
else
    return 0
end
)";

public:
    bool tryLock(const std::string& key, int ttlSeconds = 30) {
        key_ = key;
        ttlSeconds_ = ttlSeconds;
        token_ = generateUUID(); // 唯一标识

        redisReply* r = (redisReply*)redisCommand(redisCtx_,
            "SET %s %s NX EX %d", key.c_str(), token_.c_str(), ttlSeconds);
        bool ok = r && r->type == REDIS_REPLY_STATUS && std::string(r->str) == "OK";
        freeReplyObject(r);
        if (!ok) return false;

        locked_ = true;
        startWatchdog();
        return true;
    }

    void unlock() {
        locked_ = false;
        if (watchdog_.joinable()) watchdog_.join();
        // Lua 原子解锁
        evalLua(kUnlockScript, {key_}, {token_});
    }

private:
    void startWatchdog() {
        watchdog_ = std::thread([this]() {
            int interval = ttlSeconds_ / 3; // 1/3 过期时间续期一次
            while (locked_) {
                std::this_thread::sleep_for(std::chrono::seconds(interval));
                if (!locked_) break;
                // 续期
                evalLua(kRenewScript, {key_}, {token_, std::to_string(ttlSeconds_)});
            }
        });
    }
};
```

看门狗机制是 Redisson（Java Redis 客户端）的核心特性，C++ 中需自行实现。注意：
- 看门狗线程必须在 `unlock()` 时正确停止，避免线程泄漏。
- 续期失败（如 Redis 连接断开）应记录日志，锁可能已过期。
- 可重入锁需要维护持有计数，续期时也要考虑计数。

---

## 6. 快速参考卡片

| 需求 | 做法 / 要点 |
| --- | --- |
| 建立主从 | `replicaof <host> <port>`；`replica-read-only yes` |
| 复制流程 | 全量 `psync` + RDB 传输，之后按 offset 增量传播；`repl-backlog-size` 决定断连重同步窗口 |
| 复制风暴 | 树状级联复制、`repl-diskless-sync yes`（免落盘）缓解 |
| Sentinel 部署 | `sentinel monitor mymaster <ip> 6379 2`（quorum=2）；SDOWN/ODOWN 判定 |
| Sentinel 选主 | 多 sentinel 达成 quorum 后选举 leader 执行故障转移（类 Raft） |
| Sentinel 客户端 | 先连 sentinel 取 master 地址；订阅 `+switch-master` 事件刷新 |
| Cluster 分片 | 16384 个 slot；`cluster create`；CRC16 映射 key→slot |
| 重定向 | `MOVED`（槽已迁移）/ `ASK`（迁移中）由客户端处理 |
| Cluster 限制 | 多 key 操作需同 slot（用 `{tag}` hash tag）；仅支持 db0 |
| 缓存穿透 | 空值缓存 / 布隆过滤器 |
| 缓存击穿 | 互斥锁重建 / 逻辑过期 |
| 缓存雪崩 | 过期时间加随机抖动 |
| 分布式锁 | `SET key val NX PX 30000` + 唯一 value + Lua 脚本比对删除 |
| 锁续期 | Redisson 看门狗自动续期；Redlock 在强一致场景有争议 |
| 常见坑 | 主从延迟读到旧数据；故障转移期间写失败；跨 slot 报 `CROSSSLOT` |

---

## 7. 常见坑与最佳实践

### 6.1 常见坑汇总

| 坑 | 现象 | 原因 | 解决方案 |
|----|------|------|----------|
| 缓存与 DB 不一致 | 读到旧数据 | 并发读写时序问题 | 延迟双删、订阅 binlog |
| 分布式锁误删 | 并发问题 | 解锁不校验 value | Lua 脚本原子解锁 |
| 主从切换数据丢失 | 锁失效、数据回退 | 异步复制，主宕机时数据未同步 | `min-replicas-to-write`、半同步 |
| Cluster 多 key 报错 | `CROSSSLOT` | 多 key 不在同一槽位 | hash tag `{prefix}` |

### 6.2 缓存问题解决方案表

| 问题 | 首选方案 | 备选方案 |
|------|----------|----------|
| 击穿（热点 key 过期） | 互斥锁 | 逻辑过期 / 永不过期 |
| 穿透（不存在 key） | 缓存空值 | 布隆过滤器 / 参数校验 |
| 雪崩（大量同时过期） | 过期时间随机偏移 | 多级缓存 / 高可用集群 / 限流 |

---

上一篇：《06-Redis深入：协议与存储原理.md》　｜　下一篇：《08-MySQL深入：事务锁与索引优化.md》　｜　模块索引：《../README.md》
