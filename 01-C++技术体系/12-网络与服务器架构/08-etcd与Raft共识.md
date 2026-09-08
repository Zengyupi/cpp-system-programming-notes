# etcd与Raft共识（分布式键值存储与一致性算法）

> 本节目标：掌握 etcd 的体系结构（gRPC网关/WAL/Snapshot/BoltDB/Raft），深入理解 Raft 共识算法的 Leader 选举与日志复制，掌握 etcd 的线性一致性读、Lease、Watch、事务机制，能实现服务发现与分布式锁，并对比 ZooKeeper/Consul 选型。

## 本章速览

- [1. etcd 定位与核心能力](#1-etcd-定位与核心能力)
- [2. etcd 体系结构](#2-etcd-体系结构)
- [3. Raft 共识算法](#3-raft-共识算法)
  - [3.1 Leader 选举（RequestVote）](#31-leader-选举requestvote)
  - [3.2 日志复制（AppendEntries）](#32-日志复制appendentries)
  - [3.3 安全性与任期号](#33-安全性与任期号)
- [4. 读写机制与一致性](#4-读写机制与一致性)
- [5. 存储原理：BoltDB / MVCC / Revision](#5-存储原理boltdb--mvcc--revision)
- [6. 服务发现：Lease / Watch / key 过期](#6-服务发现lease--watch--key-过期)
- [7. 分布式锁实现](#7-分布式锁实现)
- [8. 集群部署与运维](#8-集群部署与运维)
- [9. 与 ZooKeeper / Consul 对比](#9-与-zookeeper--consul-对比)
- [10. 快速参考卡片](#10-快速参考卡片)
- [11. 常见问题与坑](#11-常见问题与坑)

---

## 1. etcd 定位与核心能力

etcd 是一个**分布式、强一致的键值存储**，基于 Raft 共识算法，最初由 CoreOS 开发，现为 CNCF 毕业项目，是 Kubernetes 的核心数据存储。

**核心能力：**

| 能力 | 说明 |
| --- | --- |
| 键值存储 | 二进制安全的 key-value，支持层级 key（用 / 分隔） |
| 强一致性 | Raft 保证线性一致性读写 |
| Watch | 监听 key 或前缀的变更事件（创建/修改/删除） |
| Lease | 租约机制，key 绑定 TTL，过期自动删除 |
| 事务（Txn） | IF-THEN-ELSE 原子事务，支持条件判断 |
| 分布式锁 | 基于 Lease + Txn + Watch 实现 |
| 认证授权 | RBAC 权限控制，用户/角色/权限管理 |
| TLS | 客户端与节点间通信加密 |

**典型应用场景：**
- Kubernetes：所有集群状态（Pod/Service/ConfigMap 等）存在 etcd
- 服务发现：服务注册与发现，健康检查
- 配置中心：动态配置管理，变更通知
- 分布式锁：跨进程/跨机器互斥
- 选主（Leader Election）：分布式系统主节点选举

---

## 2. etcd 体系结构

```text
                    +-------------------+
                    |   客户端 (gRPC)   |
                    +---------+---------+
                              |
                    +---------v---------+
                    |   gRPC 网关层     |  (etcd v3 API，protobuf)
                    +---------+---------+
                              |
              +---------------+---------------+
              |                               |
    +---------v---------+           +---------v---------+
    |   Raft 共识层      |           |   MVCC 存储层     |
    |  (Leader选举/      |           |  (Revision/事务/  |
    |   日志复制/快照)   |           |   压缩)           |
    +---------+---------+           +---------+---------+
              |                               |
    +---------v---------+           +---------v---------+
    |   WAL（预写日志）  |           |   BoltDB (BBolt)  |
    |  (持久化日志条目)  |           |  (B+树，实际存储)  |
    +-------------------+           +-------------------+
              |
    +---------v---------+
    |   Snapshot（快照） |  (定期压缩，避免WAL无限增长)
    +-------------------+
```

**各层职责：**

| 层 | 职责 |
| --- | --- |
| gRPC 网关 | 接收客户端请求，protobuf 序列化，v3 API 入口。gRPC 原理详见《06-gRPC与RPC框架原理.md》（待创建） |
| Raft 共识层 | Leader 选举、日志复制、成员变更、快照管理 |
| WAL | 预写日志，所有写操作先写 WAL 再应用，崩溃恢复用 |
| Snapshot | Raft 日志快照，定期生成，压缩 WAL，加速新节点加入 |
| BoltDB | 嵌入式 KV 存储，B+ 树实现，etcd 实际数据存储引擎 |
| MVCC | 多版本并发控制，每个 key 维护历史版本，支持 Watch 和事务 |

**写请求流程：**
1. 客户端 gRPC 请求到 Leader（Follower 会转发或返回 Leader 地址）
2. Raft 层将操作封装为日志条目，追加到本地 WAL
3. Leader 并行向 Follower 发送 AppendEntries
4. 多数节点（quorum）确认后，日志提交（committed）
5. 应用到状态机（BoltDB + MVCC）
6. 返回客户端成功

---

## 3. Raft 共识算法

Raft 是一种**强一致、易理解**的分布式共识算法，核心思想是"先选 Leader，再由 Leader 复制日志"。

### 3.1 Leader 选举（RequestVote）

**节点角色：**

| 角色 | 说明 |
| --- | --- |
| Leader | 处理所有客户端请求，复制日志到 Follower |
| Follower | 被动接收 Leader 的日志，响应投票请求 |
| Candidate | 选举期间的候选者，发起投票请求 |

**选举流程：**

```text
初始状态: 所有节点为 Follower，启动随机选举超时(150-300ms)

超时未收到 Leader 心跳:
  Follower -> Candidate
  1. 任期号 term + 1
  2. 投自己一票
  3. 向所有节点发送 RequestVote(term, candidateId, lastLogIndex, lastLogTerm)

其他节点收到 RequestVote:
  - 若 term < 当前term: 拒绝
  - 若已投给别人且 term 相同: 拒绝
  - 若候选人日志不如自己新: 拒绝
  - 否则: 投票，重置选举超时

Candidate 获得多数票:
  -> 成为 Leader，立即向所有节点发送心跳(空 AppendEntries)

Candidate 未获多数票(分裂投票):
  -> 等待下一次选举超时，重新开始（随机超时降低冲突概率）

发现更高 term 的节点/消息:
  -> 立即降级为 Follower，更新 term
```

**RequestVote RPC 参数：**

| 参数 | 说明 |
| --- | --- |
| term | 候选人的任期号 |
| candidateId | 候选人 ID |
| lastLogIndex | 候选人最后一条日志的索引 |
| lastLogTerm | 候选人最后一条日志的任期号 |

**返回值：** term（当前任期，用于候选人更新）、voteGranted（是否投票）

**选举安全性：** 只有日志最新（lastLogTerm 更大，或 term 相同但 index 更大）的候选人才可能当选，保证 Leader 包含所有已提交日志。

### 3.2 日志复制（AppendEntries）

Leader 收到客户端写请求后，将操作追加为日志条目，复制到所有 Follower。

**日志条目结构：**

```text
+----------------+----------------+----------------+
|   log index    |     term       |    command     |
|  (连续递增)     |  (写入时Leader  |  (实际操作，    |
|                |   的任期号)     |   如 put k=v)  |
+----------------+----------------+----------------+
```

**复制流程：**

```text
Leader 收到写请求:
  1. 追加日志条目到本地 WAL (index=N, term=T)
  2. 并行向所有 Follower 发送 AppendEntries(term, prevLogIndex, prevLogTerm, entries[], leaderCommit)
  3. 等待多数 Follower 确认

Follower 收到 AppendEntries:
  1. 若 term < 当前term: 拒绝
  2. 检查 prevLogIndex/prevLogTerm 是否匹配本地日志
     - 不匹配: 拒绝，返回冲突信息（Leader 回退 nextIndex 重试）
     - 匹配: 追加 entries 到本地 WAL
  3. 更新 commitIndex（若 leaderCommit > 本地 commitIndex）
  4. 返回成功

Leader 收到多数确认:
  1. 日志条目标记为 committed（已提交）
  2. 应用到状态机（BoltDB）
  3. 更新 commitIndex
  4. 下一次 AppendEntries 心跳通知 Follower 提交进度
  5. 返回客户端成功
```

**AppendEntries RPC 参数：**

| 参数 | 说明 |
| --- | --- |
| term | Leader 任期号 |
| leaderId | Leader ID（Follower 可重定向客户端） |
| prevLogIndex | 新条目之前的日志索引 |
| prevLogTerm | prevLogIndex 对应条目的任期号 |
| entries[] | 要复制的日志条目（空数组为心跳） |
| leaderCommit | Leader 的 commitIndex |

**日志一致性保证：** 如果不同节点的日志在某个 index/term 处相同，则该位置之前的所有日志都相同（Log Matching Property）。

### 3.3 安全性与任期号

**任期（Term）：** 单调递增的逻辑时钟，每次选举开始新任期。一个任期内最多一个 Leader，任期号用于检测过期节点和消息。

**安全性保证（Raft 核心定理）：**

1. **选举安全**：一个任期内最多一个 Leader
2. **Leader 只追加**：Leader 只追加日志，不删除或修改已有日志
3. **日志匹配**：两个日志在相同 index/term 处相同，则之前所有日志相同
4. **Leader 完整性**：已提交的日志条目会出现在所有未来 Leader 的日志中
5. **状态机安全**：如果一个节点已将某日志应用到状态机，其他节点不会在相同 index 应用不同命令

**已提交 vs 已应用：**
- **已提交（committed）**：日志被多数节点复制，Raft 保证永不丢失
- **已应用（applied）**：日志被状态机（BoltDB）执行，客户端可见
- 已应用一定已提交，已提交不一定已应用（有延迟）

---

## 4. 读写机制与一致性

### 线性一致性读（Linearizable Read）

etcd 默认提供线性一致性读，保证读到的是最新已提交数据。

**实现方式（ReadIndex）：**
1. Leader 记录当前 commitIndex（readIndex）
2. Leader 向多数节点发送心跳确认自己仍是 Leader（防止脑裂）
3. 等待本地 appliedIndex >= readIndex
4. 读取本地状态机数据返回

**开销：** 一次线性一致性读需要一次 Raft 心跳轮询（多数节点确认），延迟约 1 个 RTT。

### Lease Read（租约读，低延迟读）

为了降低读延迟，etcd 提供 Lease Read（也叫 Serializable Read 的优化版）：

1. Leader 在选举成功后获得一个**读租约**（默认 5 秒，可配置）
2. 租约有效期内，Leader 无需心跳确认，直接读本地状态机
3. 租约快过期时，通过心跳续期

**权衡：** Lease Read 延迟更低（无 RTT），但在极端网络分区情况下可能读到旧数据（窗口极小，约等于选举超时）。生产环境默认开启 Lease Read。

```bash
# etcd 启动参数
--experimental-serializable-read-only=true  # 可串行化读（不保证线性一致，最快）
# 默认是 ReadIndex 线性一致读
```

### 事务（Txn）

etcd 支持 IF-THEN-ELSE 原子事务：

```bash
# 事务示例：如果 key 不存在则创建，存在则更新
etcdctl txn <<EOF
mod("key") = "0"
put key "new_value"
put key "existing_value"
EOF
# 示例输出:
# SUCCESS
# OK
```

**事务比较操作符：** `=`（等于）、`!=`（不等于）、`>`（大于）、`<`（小于）
**可比较字段：** `mod`（修改版本）、`create`（创建版本）、`value`（值）、`lease`（租约ID）

事务保证 ACID 中的原子性和隔离性（串行化隔离级别），所有操作要么全部成功要么全部失败。

---

## 5. 存储原理：BoltDB / MVCC / Revision

### BoltDB（BBolt）

BoltDB 是嵌入式 KV 存储，基于 B+ 树，支持 ACID 事务，mmap 读取，etcd 将其作为底层存储引擎。

```text
BoltDB 存储结构:
  bucket "key":  key -> keyIndex (元数据，包含所有版本的 revision 列表)
  bucket "meta": 元信息
  实际 value 存在 keyIndex 指向的 revision 位置
```

### MVCC（多版本并发控制）

etcd 不覆盖更新，每次修改都生成新版本，保留历史：

```text
key = "config" 的版本历史:
  revision=3: value="v1" (创建)
  revision=7: value="v2" (修改)
  revision=12: value="v3" (修改)
  (当前最新版本 revision=12)
```

**Revision（修订号）：** 全局单调递增的 64 位整数，每次写操作 +1，是 MVCC 的版本标识。

```text
Revision 结构:
  main: 主修订号（每次事务 +1）
  sub:  子修订号（同一事务内多次操作递增，通常为0）
```

### 压缩（Compaction）

历史版本无限增长会耗尽磁盘，etcd 支持压缩：

```bash
# 压缩到指定 revision，删除之前的历史版本
etcdctl compact 1000
# 自动压缩（每小时）
etcd --auto-compaction-mode=periodic --auto-compaction-retention=1
```

压缩后，Watch 从压缩前的 revision 开始会收到 "mvcc: required revision has been compacted" 错误，客户端需处理。

---

## 6. 服务发现：Lease / Watch / key 过期

### Lease（租约）

Lease 是 etcd 的 TTL 机制，key 绑定 Lease 后，Lease 过期时 key 自动删除。

```bash
# 创建租约（TTL=30秒），返回 lease ID
etcdctl lease grant 30
# 示例输出: lease 694d673f12345678 granted with TTL(30s)

# key 绑定租约
etcdctl put --lease=694d673f12345678 /services/user/192.168.1.10:8080 "alive"

# 续租（保持心跳）
etcdctl lease keep-alive 694d673f12345678

# 查看租约信息
etcdctl lease timetolive 694d673f12345678 --keys
```

### Watch（监听）

Watch 监听 key 或前缀的变更，通过 gRPC 流式推送事件，无需轮询。

```bash
# 监听单个 key
etcdctl watch /services/user/192.168.1.10:8080

# 监听前缀
etcdctl watch --prefix /services/user/

# 从指定 revision 开始监听（含历史）
etcdctl watch --prefix /services/user/ --rev=1000

# 示例输出（事件格式）:
# PUT
# /services/user/192.168.1.10:8080
# alive
# DELETE
# /services/user/192.168.1.10:8080
```

**Watch 事件类型：** PUT（创建/修改）、DELETE（删除）

### 服务发现完整流程

```text
服务启动:
  1. 创建 Lease (TTL=10s)
  2. 启动 keep-alive 协程（每 1/3 TTL 续租一次）
  3. put /services/{name}/{addr} -> 绑定 Lease

服务发现端:
  1. get --prefix /services/{name}/ -> 获取当前所有实例
  2. watch --prefix /services/{name}/ -> 监听变更
     - PUT 事件: 新实例上线，加入负载均衡列表
     - DELETE 事件: 实例下线（Lease过期或主动删除），移除列表

服务异常退出:
  - keep-alive 停止 -> Lease 过期 -> key 自动删除 -> Watch 推送 DELETE
  - 发现端自动移除故障实例
```

---

## 7. 分布式锁实现

etcd 分布式锁基于 **Lease + Txn + Watch** 实现，官方客户端库（concurrency package）已封装。

**核心原理：**

```text
加锁:
  1. 创建 Lease (TTL=10s)，启动 keep-alive
  2. 在锁路径下创建带 Lease 的 key: /locks/mylock/{leaseID} (PUT)
  3. get --prefix /locks/mylock/ -> 获取所有竞争者，按创建 revision 排序
  4. 若自己是最小 revision -> 获得锁
  5. 否则 -> watch 前一个 key（revision 比自己小的最大者），等待其 DELETE
     - 前一个 key DELETE（释放或Lease过期）-> 自己成为最小 -> 获得锁

解锁:
  1. 删除自己的 key (/locks/mylock/{leaseID})
  2. 撤销 Lease

锁持有者崩溃:
  - keep-alive 停止 -> Lease 过期 -> key 自动删除 -> 下一个竞争者获得锁
```

**为什么用前缀 + 有序 key 而非单个 key：**
- 单个 key 竞争会产生"惊群效应"：锁释放时所有竞争者同时抢，浪费资源
- 有序 key 实现公平锁（FIFO）：每个竞争者只 watch 前一个，避免惊群
- Lease 保证崩溃自动释放

```bash
# etcdctl 内置锁（v3.5+）
etcdctl lock mylock
# 获得锁后进入交互，Ctrl+D 释放
# 示例输出: mylock/694d673f12345678
```

**C++ 客户端使用：** 用 etcd-cpp-apiv3 或 etcd3-cpp 库，调用 `lock()` / `unlock()`，内部封装上述流程。

---

## 8. 集群部署与运维

### 集群部署

```bash
# 三节点集群（静态配置）
# 节点1
etcd --name node1 \
  --initial-advertise-peer-urls http://192.168.1.10:2380 \
  --listen-peer-urls http://192.168.1.10:2380 \
  --advertise-client-urls http://192.168.1.10:2379 \
  --listen-client-urls http://192.168.1.10:2379 \
  --initial-cluster node1=http://192.168.1.10:2380,node2=http://192.168.1.11:2380,node3=http://192.168.1.12:2380 \
  --initial-cluster-token etcd-cluster-1 \
  --initial-cluster-state new

# 节点2、节点3类似，修改 name 和 IP
```

**端口说明：** 2379（客户端通信）、2380（节点间 Raft 通信）

**集群规模：** 奇数节点（3/5/7），容忍 (n-1)/2 个节点故障。3 节点容忍 1 个故障，5 节点容忍 2 个。

### etcdctl 常用命令

```bash
# 基本操作
etcdctl put key value
etcdctl get key
etcdctl get --prefix /services/
etcdctl del key
etcdctl del --prefix /tmp/

# 集群管理
etcdctl member list
etcdctl endpoint status --cluster -w table
etcdctl endpoint health

# 租约
etcdctl lease grant 30
etcdctl lease keep-alive <leaseID>
etcdctl lease revoke <leaseID>

# 快照备份与恢复
etcdctl snapshot save backup.db
etcdctl snapshot restore backup.db --data-dir=/var/lib/etcd-restore

# 压缩与碎片整理
etcdctl compact <revision>
etcdctl defrag
```

### 扩容缩容

```bash
# 扩容：添加新节点
etcdctl member add node4 --peer-urls=http://192.168.1.13:2380
# 新节点以 --initial-cluster-state=existing 启动

# 缩容：移除节点
etcdctl member remove <memberID>
```

---

## 9. 与 ZooKeeper / Consul 对比

| 维度 | etcd | ZooKeeper | Consul |
| --- | --- | --- | --- |
| 共识算法 | Raft | ZAB（类 Paxos） | Raft |
| 数据模型 | KV（二进制安全） | ZNode（树形，有版本） | KV + 服务目录 |
| API | gRPC (HTTP/2) | 自定义 TCP（Java 为主） | HTTP REST + DNS |
| Watch | 流式 gRPC，支持前缀 | 一次性 Watch（需重新注册） | 长轮询 + 阻塞查询 |
| 租约/TTL | 原生 Lease | 临时节点（会话绑定） | 服务注册 TTL + 健康检查 |
| 事务 | IF-THEN-ELSE | 多操作原子（无条件） | KV 事务（CAS） |
| 认证 | RBAC + TLS | ACL + SASL | ACL + TLS |
| 性能 | 高（gRPC + B+树） | 中（Java，ZAB） | 中高（Go，Raft） |
| 运维 | 简单（单二进制） | 复杂（Java + JVM 调优） | 简单（单二进制） |
| 生态 | Kubernetes 原生 | Hadoop/Spark 生态 | HashiCorp 生态（Terraform/Vault） |
| 典型场景 | K8s、服务发现、配置中心 | 大数据集群协调、HBase | 服务网格、多数据中心、DNS |

**选型建议：**
- **Kubernetes 生态**：etcd（唯一选择）
- **新项目服务发现/配置中心**：etcd 或 Consul（etcd 更轻量，Consul 内置 DNS 和多数据中心）
- **大数据/Hadoop 生态**：ZooKeeper（生态绑定）
- **多数据中心服务发现**：Consul（原生支持跨数据中心）

---

## 10. 快速参考卡片

### Raft 状态机图

```text
         超时/未收到心跳
  +------------+  发起选举   +-----------+
  |  Follower  |------------>| Candidate |
  +------------+             +-----+-----+
       ^     ^                    |
       |     |    发现更高term     | 获得多数票
       |     +--------------------+
       |                          v
       |                    +-----------+
       +--------------------|  Leader   |
         发现更高term        +-----------+
                              持续发心跳
```

### etcdctl 命令速查

```text
KV:     put KEY VAL / get KEY [--prefix] / del KEY [--prefix]
事务:   txn (IF cond THEN ops ELSE ops)
租约:   lease grant TTL / lease keep-alive ID / lease revoke ID / lease timetolive ID
监听:   watch KEY [--prefix] [--rev N]
集群:   member list/add/remove / endpoint status/health
快照:   snapshot save FILE / snapshot restore FILE --data-dir=DIR
维护:   compact REV / defrag / alarm list/disarm
锁:     lock NAME [--ttl N]
```

### 分布式锁实现要点

```text
1. 创建 Lease (TTL) + keep-alive 协程
2. PUT /locks/{name}/{leaseID} 绑定 Lease
3. GET --prefix /locks/{name}/ 按 create revision 排序
4. 自己是最小 revision -> 获锁；否则 watch 前一个 key 等待 DELETE
5. 解锁: DELETE 自己的 key + revoke Lease
6. 崩溃自动释放: Lease 过期 -> key 删除 -> 下一个获锁
```

---

## 11. 常见问题与坑

| 问题 | 原因与解决 |
| --- | --- |
| etcd 集群无法启动 | initial-cluster 配置不一致或节点名重复；确保所有节点的 initial-cluster 完全一致，name 唯一 |
| Leader 频繁切换 | 网络抖动或磁盘 IO 慢（WAL fsync 超时）；用 SSD，调大 heartbeat-interval（默认100ms）和 election-timeout（默认1s） |
| 读请求延迟高 | 线性一致性读需要 Raft 心跳确认；开启 Lease Read（默认）或用 serializable 读（可接受旧数据时） |
| 磁盘空间告警 | 历史版本未压缩；配置自动压缩 `--auto-compaction-mode=periodic --auto-compaction-retention=1`，定期 `defrag` |
| Watch 事件丢失 | 客户端处理慢导致事件积压，或从已压缩的 revision 监听；Watch 处理逻辑要快，压缩后重新从当前 revision 监听 |
| 分布式锁死锁 | 持有者进程卡住但 keep-alive 正常（GC 或死循环）；Lease 只能检测进程崩溃，不能检测业务死锁；需业务层超时 |
| 扩容后数据不同步 | 新节点加入时数据量大，快照传输慢；确保网络带宽充足，新节点以 existing 状态启动并等待同步完成 |
| 客户端连不上 | 2379 端口未开放或 TLS 配置错误；检查 `--listen-client-urls` 是否绑定 0.0.0.0，证书是否匹配 |
| 事务失败 | 条件不满足（IF 为 false）走 ELSE 分支；事务返回 SUCCESS/FAILURE 表示 IF 条件结果，不是错误 |
| key 意外删除 | Lease 过期或被误 revoke；关键 key 不绑定 Lease，或用长 TTL + 监控续租状态 |

---

上一篇：《07-ZeroMQ消息模式.md》
下一篇：《09-OpenResty与WAF防护.md》
