# MySQL 深入：事务锁与索引优化

> 本节目标：在《01-MySQL数据库精要.md》基础上深入 InnoDB 底层实现。覆盖 MVCC 的 Read View 与 undo log 版本链、四种隔离级别的实现差异、InnoDB 锁体系（S/X/IS/IX、记录锁/间隙锁/next-key/插入意向锁/自增锁）、死锁检测与排查、B+ 树索引的最左匹配与覆盖索引、EXPLAIN 执行计划字段深度解读、慢查询优化实战、缓存策略与双写一致性（延迟双删、canal 订阅 binlog）。学完后能从锁和 MVCC 层面理解并发事务行为，从执行计划层面优化 SQL，从工程层面设计缓存一致性方案。前置阅读：《01-MySQL数据库精要.md》《../14-内核云原生与分布式/05-检测组件与分布式锁.md》。

## 本章速览

- [1. MVCC 原理：Read View 与 undo log 版本链](#1-mvcc-原理read-view-与-undo-log-版本链)
  - [1.1 隐藏字段与 undo log](#11-隐藏字段与-undo-log)
  - [1.2 Read View 结构](#12-read-view-结构)
  - [1.3 可见性判断算法](#13-可见性判断算法)
  - [1.4 RC 与 RR 的 Read View 差异](#14-rc-与-rr-的-read-view-差异)
- [2. 事务隔离级别深入](#2-事务隔离级别深入)
  - [2.1 读未提交（Read Uncommitted）](#21-读未提交read-uncommitted)
  - [2.2 读已提交（Read Committed）](#22-读已提交read-committed)
  - [2.3 可重复读（Repeatable Read）](#23-可重复读repeatable-read)
  - [2.4 串行化（Serializable）](#24-串行化serializable)
  - [2.5 隔离级别与并发问题对照表](#25-隔离级别与并发问题对照表)
- [3. InnoDB 锁机制深入](#3-innodb-锁机制深入)
  - [3.1 锁的粒度与模式：S/X/IS/IX](#31-锁的粒度与模式sxix)
  - [3.2 记录锁（Record Lock）](#32-记录锁record-lock)
  - [3.3 间隙锁（Gap Lock）](#33-间隙锁gap-lock)
  - [3.4 Next-Key Lock](#34-next-key-lock)
  - [3.5 插入意向锁（Insert Intention Lock）](#35-插入意向锁insert-intention-lock)
  - [3.6 自增锁（AUTO-INC Lock）](#36-自增锁auto-inc-lock)
  - [3.7 加锁规则总结](#37-加锁规则总结)
- [4. 死锁检测与锁等待](#4-死锁检测与锁等待)
  - [4.1 死锁产生条件](#41-死锁产生条件)
  - [4.2 InnoDB 死锁检测机制](#42-innodb-死锁检测机制)
  - [4.3 死锁排查：SHOW ENGINE INNODB STATUS](#43-死锁排查show-engine-innodb-status)
  - [4.4 锁等待与 innodb_lock_wait_timeout](#44-锁等待与-innodb_lock_wait_timeout)
  - [4.5 死锁预防策略](#45-死锁预防策略)
- [5. 索引原理深入](#5-索引原理深入)
  - [5.1 B+ 树结构与 InnoDB 实现](#51-b-树结构与-innodb-实现)
  - [5.2 聚集索引与辅助索引](#52-聚集索引与辅助索引)
  - [5.3 最左匹配原则详解](#53-最左匹配原则详解)
  - [5.4 覆盖索引与回表](#54-覆盖索引与回表)
  - [5.5 索引失效条件详解](#55-索引失效条件详解)
  - [5.6 索引下推（ICP，5.6+）](#56-索引下推icp56)
  - [5.7 变更缓冲（Change Buffer）](#57-变更缓冲change-buffer)
- [6. EXPLAIN 执行计划深度解读](#6-explain-执行计划深度解读)
  - [6.1 EXPLAIN 输出字段总览](#61-explain-输出字段总览)
  - [6.2 type 字段：访问类型从优到劣](#62-type-字段访问类型从优到劣)
  - [6.3 key / key_len / ref 字段](#63-key--key_len--ref-字段)
  - [6.4 rows 与 filtered](#64-rows-与-filtered)
  - [6.5 Extra 字段高频值解读](#65-extra-字段高频值解读)
  - [6.6 优化器索引选择过程](#66-优化器索引选择过程)
- [7. SQL 优化实战](#7-sql-优化实战)
  - [7.1 慢查询日志配置与分析](#71-慢查询日志配置与分析)
  - [7.2 SHOW PROFILE 分析](#72-show-profile-分析)
  - [7.3 JOIN 优化](#73-join-优化)
  - [7.4 ORDER BY 优化](#74-order-by-优化)
  - [7.5 GROUP BY 优化](#75-group-by-优化)
  - [7.6 分页深翻页优化](#76-分页深翻页优化)
  - [7.7 优化 checklist](#77-优化-checklist)
- [8. 缓存策略](#8-缓存策略)
  - [8.1 Cache-Aside（旁路缓存）](#81-cache-aside旁路缓存)
  - [8.2 Read Through / Write Through](#82-read-through--write-through)
  - [8.3 Write Behind（异步写回）](#83-write-behind异步写回)
  - [8.4 策略对比与选型](#84-策略对比与选型)
- [9. 缓存一致性深入](#9-缓存一致性深入)
  - [9.1 双写一致性问题分析](#91-双写一致性问题分析)
  - [9.2 延迟双删](#92-延迟双删)
  - [9.3 canal 订阅 binlog 异步删缓存](#93-canal-订阅-binlog-异步删缓存)
  - [9.4 go-mysql-transfer 等工具](#94-go-mysql-transfer-等工具)
  - [9.5 最终一致性方案选型](#95-最终一致性方案选型)
- [10. 常见坑与最佳实践](#10-常见坑与最佳实践)
- [11. 快速参考卡片](#11-快速参考卡片)

---

## 1. MVCC 原理：Read View 与 undo log 版本链

MVCC（Multi-Version Concurrency Control，多版本并发控制）是 InnoDB 实现隔离级别（RC、RR）的核心机制。它通过保存数据的多个版本，让读操作不加锁、读写不阻塞，大幅提升并发性能。

### 1.1 隐藏字段与 undo log

InnoDB 每行数据除了用户定义的列，还有三个隐藏字段：

| 隐藏字段 | 大小 | 说明 |
|----------|------|------|
| `DB_TRX_ID` | 6 字节 | 最后一次插入/更新该行的事务 ID |
| `DB_ROLL_PTR` | 7 字节 | 回滚指针，指向 undo log 中的上一个版本 |
| `DB_ROW_ID` | 6 字节 | 行 ID（仅当没有定义主键时使用，作为聚集索引） |

**undo log 版本链**：每次 UPDATE 操作，InnoDB 会将旧值写入 undo log，然后通过 `DB_ROLL_PTR` 指向旧版本。多次更新形成一条版本链：

```text
当前行 (trx_id=10, roll_ptr→) → undo v2 (trx_id=8, roll_ptr→) → undo v1 (trx_id=5, roll_ptr=null)
```

SELECT 时，沿着版本链找到第一个对当前事务"可见"的版本。

undo log 分为两类：
- **insert undo log**：INSERT 操作产生，事务提交后可直接删除（因为其他事务不需要这个版本）。
- **update undo log**：UPDATE/DELETE 操作产生，需要等没有事务引用这些旧版本时，由 purge 线程清理。

### 1.2 Read View 结构

Read View 是事务在某个时间点生成的"数据快照"，用于判断版本链中哪个版本对当前事务可见。Read View 包含四个关键字段：

| 字段 | 说明 |
|------|------|
| `m_ids` | 生成 Read View 时，当前系统中活跃的（未提交的）事务 ID 列表 |
| `min_trx_id` | m_ids 中的最小事务 ID |
| `max_trx_id` | 生成 Read View 时，系统下一个要分配的事务 ID（即当前最大事务 ID + 1） |
| `creator_trx_id` | 创建该 Read View 的事务 ID |

### 1.3 可见性判断算法

对于版本链中的某个版本（其 `DB_TRX_ID` 记为 `trx_id`），可见性判断规则：

1. **`trx_id == creator_trx_id`**：该版本是当前事务自己修改的 → **可见**。
2. **`trx_id < min_trx_id`**：该版本的事务在生成 Read View 时已经提交 → **可见**。
3. **`trx_id >= max_trx_id`**：该版本的事务在生成 Read View 之后才启动 → **不可见**。
4. **`min_trx_id <= trx_id < max_trx_id`**：需要判断 `trx_id` 是否在 `m_ids` 中：
   - 在 m_ids 中：该版本的事务在生成 Read View 时还活跃（未提交）→ **不可见**。
   - 不在 m_ids 中：该版本的事务在生成 Read View 时已经提交 → **可见**。

如果当前版本不可见，沿 `DB_ROLL_PTR` 找到上一个版本，重复判断，直到找到可见版本或遍历完版本链（返回空）。

### 1.4 RC 与 RR 的 Read View 差异

这是 RC（读已提交）和 RR（可重复读）的**本质区别**：

| 隔离级别 | Read View 生成时机 | 效果 |
|----------|-------------------|------|
| **RC** | 每次 SELECT 都生成新的 Read View | 每次查询都能看到其他事务已提交的最新数据 → 不可重复读 |
| **RR** | 事务中第一次 SELECT 时生成 Read View，后续 SELECT 复用同一个 | 整个事务期间看到的数据一致 → 可重复读 |

**RR 下的幻读问题**：
RR 通过 Read View 解决了"快照读"（普通 SELECT）的不可重复读和幻读。但"当前读"（`SELECT ... FOR UPDATE`、`SELECT ... LOCK IN SHARE MODE`、INSERT/UPDATE/DELETE）读取的是最新版本，并加锁。RR 下当前读可能出现幻读吗？

InnoDB 在 RR 下通过 **Next-Key Lock（记录锁+间隙锁）** 防止当前读的幻读：当执行 `SELECT * FROM t WHERE id > 10 FOR UPDATE` 时，不仅锁定 id>10 的记录，还锁定这些记录之间的间隙，防止其他事务插入新行。因此 InnoDB 的 RR 实际上解决了幻读问题（这是 InnoDB 对标准 SQL 隔离级别的增强）。

> 来源：《高性能MySQL》第 3 版 第 1 章；MySQL 官方文档 InnoDB Multi-Versioning。

---

## 2. 事务隔离级别深入

### 2.1 读未提交（Read Uncommitted）

- **实现**：SELECT 不加锁，直接读取最新版本（不生成 Read View，不做可见性判断）。
- **问题**：脏读——可以读到其他事务未提交的数据。如果该事务回滚，读到的就是脏数据。
- **性能**：最高（读完全不加锁）。
- **使用场景**：几乎不用。仅在对数据一致性要求极低、追求极致读性能的场景（如统计估算）可能使用。

### 2.2 读已提交（Read Committed）

- **实现**：每次 SELECT 生成新的 Read View，只能看到已提交事务的数据。
- **解决**：脏读。
- **问题**：不可重复读——同一事务内两次 SELECT 之间，其他事务提交了修改，两次结果不同。
- **锁**：SELECT 是快照读（不加锁）；UPDATE/DELETE 加记录锁（Record Lock），**不加间隙锁**（因此 RC 下可能出现幻读）。
- **使用场景**：Oracle、PostgreSQL、SQL Server 的默认隔离级别。互联网应用中常用，因为并发性能好，不可重复读通常可接受。

### 2.3 可重复读（Repeatable Read）

- **实现**：事务第一次 SELECT 时生成 Read View，后续复用。
- **解决**：脏读、不可重复读。InnoDB 通过 Next-Key Lock 进一步解决了当前读的幻读。
- **锁**：UPDATE/DELETE 加 Next-Key Lock（记录锁+间隙锁），防止幻读。
- **性能**：比 RC 略低（间隙锁增加了锁冲突概率）。
- **使用场景**：MySQL InnoDB 的**默认隔离级别**。金融、账务等对一致性要求高的场景。

### 2.4 串行化（Serializable）

- **实现**：所有 SELECT 自动转为 `SELECT ... LOCK IN SHARE MODE`（共享锁），读写互相阻塞。
- **解决**：所有并发问题（脏读、不可重复读、幻读）。
- **性能**：最低（读也加锁，并发度极低）。
- **使用场景**：极少使用。仅在对数据一致性要求极高、并发量低的场景（如月末结账）。

### 2.5 隔离级别与并发问题对照表

| 隔离级别 | 脏读 | 不可重复读 | 幻读 | 读锁 | 间隙锁 |
|----------|------|-----------|------|------|--------|
| 读未提交 | ✗ 可能 | ✗ 可能 | ✗ 可能 | 无 | 无 |
| 读已提交 | ✓ 解决 | ✗ 可能 | ✗ 可能 | 无（快照读） | 无 |
| 可重复读 | ✓ 解决 | ✓ 解决 | ✓ 解决（InnoDB） | 无（快照读） | 有（当前读） |
| 串行化 | ✓ 解决 | ✓ 解决 | ✓ 解决 | 有（共享锁） | 有 |

> 注：标准 SQL 定义中 RR 不能解决幻读，但 InnoDB 通过 Next-Key Lock 在 RR 下解决了幻读。

```sql
-- 查看当前隔离级别
SELECT @@transaction_isolation;
-- REPEATABLE-READ

-- 设置隔离级别
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
```

---

## 3. InnoDB 锁机制深入

### 3.1 锁的粒度与模式：S/X/IS/IX

InnoDB 支持多种锁粒度和模式：

**锁模式**：

| 锁模式 | 名称 | 说明 | 兼容性 |
|--------|------|------|--------|
| S | 共享锁（读锁） | 多个事务可同时持有 S 锁 | S 与 S 兼容，与 X 互斥 |
| X | 排他锁（写锁） | 只有一个事务能持有 X 锁 | X 与所有锁互斥 |
| IS | 意向共享锁 | 事务打算给行加 S 锁，先给表加 IS | IS 与 IS/IX 兼容，与 X 互斥 |
| IX | 意向排他锁 | 事务打算给行加 X 锁，先给表加 IX | IX 与 IS/IX 兼容，与 S/X 互斥 |

**意向锁的作用**：意向锁是表级锁，用于快速判断表中是否有行锁。如果没有意向锁，要判断表中是否有行锁需要遍历所有行。有了意向锁，加表锁前只需检查表上的意向锁是否冲突。

兼容性矩阵：

|   | S | X | IS | IX |
|---|---|---|----|----|
| S | ✓ | ✗ | ✓ | ✗ |
| X | ✗ | ✗ | ✗ | ✗ |
| IS | ✓ | ✗ | ✓ | ✓ |
| IX | ✗ | ✗ | ✓ | ✓ |

**自动加锁**：
- 普通 SELECT（快照读）：不加锁。
- `SELECT ... LOCK IN SHARE MODE`：加 S 锁。
- `SELECT ... FOR UPDATE`：加 X 锁。
- INSERT/UPDATE/DELETE：加 X 锁。

### 3.2 记录锁（Record Lock）

记录锁是对**索引记录**的锁定，不是对数据行本身。InnoDB 的行锁是通过锁定索引项实现的。

```sql
-- 假设 id 是主键
BEGIN;
SELECT * FROM users WHERE id = 10 FOR UPDATE;
-- 锁定聚集索引中 id=10 的索引项
```

如果查询条件没有索引，InnoDB 会锁定**所有记录**（因为没有索引可锁定，只能全表扫描并逐行加锁），效果接近表锁。这也是"没有索引会导致锁表"的原因。

### 3.3 间隙锁（Gap Lock）

间隙锁锁定索引记录之间的"间隙"，防止其他事务在间隙中插入新记录。间隙锁是 InnoDB 在 RR 隔离级别下为防止幻读而引入的。

```text
索引中有记录：id=5, id=10, id=15
间隙：(-∞,5), (5,10), (10,15), (15,+∞)
```

```sql
-- RR 隔离级别下
SELECT * FROM users WHERE id BETWEEN 10 AND 20 FOR UPDATE;
-- 锁定 id=10, id=15 的记录，以及 (10,15), (15,20] 的间隙
-- 其他事务无法在 id=11~20 之间插入新记录
```

间隙锁的特点：
- **只在 RR 隔离级别下生效**（RC 下关闭间隙锁，除了外键检查和唯一键检查）。
- 间隙锁之间**互相兼容**：多个事务可以同时锁定同一个间隙（因为间隙锁的目的是阻止插入，而不是阻止其他间隙锁）。
- 间隙锁与**插入意向锁**互斥。

### 3.4 Next-Key Lock

Next-Key Lock = 记录锁 + 间隙锁，锁定一个**左开右闭区间**。这是 InnoDB RR 下默认的行锁算法。

```text
索引记录：id=5, id=10, id=15
Next-Key Lock 区间：(-∞,5], (5,10], (10,15], (15,+∞]
```

当执行 `SELECT * FROM users WHERE id > 10 FOR UPDATE` 时：
- 锁定 (10,15] 和 (15,+∞] 两个 Next-Key Lock 区间。
- 即锁定 id=15 的记录，以及 (10,15) 和 (15,+∞) 的间隙。
- 其他事务无法插入 id>10 的新记录，也无法修改 id=15 的记录。

**特殊情况**：
- 唯一索引上的等值查询（如 `WHERE id = 10`，id 是唯一索引）：Next-Key Lock 退化为**记录锁**（只锁 id=10 的记录，不锁间隙），因为唯一索引保证不会有重复值，不需要间隙锁防幻读。
- 唯一索引上的等值查询且记录不存在：锁定该值所在的间隙（Gap Lock）。

### 3.5 插入意向锁（Insert Intention Lock）

插入意向锁是一种**特殊的间隙锁**，在 INSERT 操作时设置。它表示"我打算在这个间隙插入一条记录"。

- 插入意向锁之间**互相兼容**：多个事务可以同时在同一个间隙插入不同位置的记录（只要不冲突）。
- 插入意向锁与**普通间隙锁**互斥：如果一个事务已经锁定了某个间隙（Gap Lock），其他事务无法在该间隙插入（需要等待间隙锁释放）。

这就是间隙锁防止幻读的机制：间隙锁阻止插入意向锁，从而阻止新记录插入。

```sql
-- 事务 A（RR）
BEGIN;
SELECT * FROM users WHERE id BETWEEN 10 AND 20 FOR UPDATE;
-- 持有 (10,20] 的 Next-Key Lock

-- 事务 B
INSERT INTO users (id, name) VALUES (15, 'test');
-- 尝试在 (10,20) 间隙插入，需要插入意向锁
-- 与事务 A 的间隙锁冲突 → 阻塞等待
```

### 3.6 自增锁（AUTO-INC Lock）

自增锁是一种特殊的**表级锁**，用于保证 AUTO_INCREMENT 列的值连续且唯一。

`innodb_autoinc_lock_mode` 控制自增锁模式：

| 模式 | 值 | 行为 | 并发性能 |
|------|-----|------|----------|
| traditional | 0 | 所有 INSERT 都加表级自增锁，语句结束后释放 | 最低，自增值连续 |
| consecutive | 1（默认） | 简单 INSERT（能确定插入行数）提前分配自增值，不加锁；批量 INSERT（INSERT...SELECT、LOAD DATA）加锁 | 中等 |
| interleaved | 2 | 所有 INSERT 都不加表锁，并发分配自增值 | 最高，但自增值可能不连续（回滚或批量插入时） |

MySQL 8.0 默认 `innodb_autoinc_lock_mode=2`（interleaved），因为基于语句的复制（SBR）已不是默认，不连续的自增值不影响数据一致性。

### 3.7 加锁规则总结

InnoDB RR 隔离级别下的加锁规则（简化版）：

1. **唯一索引等值查询，记录存在**：加记录锁（Record Lock），不加间隙锁。
2. **唯一索引等值查询，记录不存在**：加间隙锁（Gap Lock），锁定该值所在间隙。
3. **唯一索引范围查询**：加 Next-Key Lock，扫描到的每个记录和间隙都加锁。
4. **非唯一索引等值查询**：加 Next-Key Lock（记录锁+间隙锁），因为非唯一索引可能有重复值，需要间隙锁防幻读。
5. **非唯一索引范围查询**：加 Next-Key Lock。
6. **无索引查询**：全表扫描，所有记录加 X 锁，所有间隙加 Gap Lock（效果接近表锁）。
7. **INSERT**：加插入意向锁，与已有的 Gap Lock 冲突时阻塞。
8. **DELETE/UPDATE**：与 SELECT FOR UPDATE 加锁规则相同。

> 来源：《高性能MySQL》第 3 版；MySQL 官方文档 InnoDB Locking。

---

## 4. 死锁检测与锁等待

### 4.1 死锁产生条件

死锁是两个或多个事务互相等待对方持有的锁，导致都无法继续执行。死锁产生的四个必要条件：
1. **互斥**：锁不能共享。
2. **持有并等待**：持有一个锁的同时等待另一个锁。
3. **不可剥夺**：锁不能被强制剥夺，只能主动释放。
4. **循环等待**：事务 A 等事务 B 的锁，事务 B 等事务 A 的锁。

### 4.2 InnoDB 死锁检测机制

InnoDB 自动检测死锁：
- 维护一个**等待图（wait-for graph）**：节点是事务，边表示"事务 A 等待事务 B 持有的锁"。
- 当有事务等待锁时，检测等待图中是否有环。
- 发现环（死锁）后，选择**回滚代价最小**的事务（通常是更新行数最少、undo log 最少的事务）进行回滚，打破死锁。
- 被回滚的事务收到错误 `1213: Deadlock found when trying to get lock`。

死锁检测有性能开销：高并发下大量事务等待锁时，死锁检测的 O(N²) 复杂度可能成为瓶颈。可通过 `innodb_deadlock_detect=OFF` 关闭死锁检测（不推荐，关闭后死锁只能靠 `innodb_lock_wait_timeout` 超时解除）。

### 4.3 死锁排查：SHOW ENGINE INNODB STATUS

```sql
-- 查看最近一次死锁信息
SHOW ENGINE INNODB STATUS\G
```

输出中的 `LATEST DETECTED DEADLOCK` 部分包含：
- 死锁发生时间
- 事务 1：正在执行的 SQL、持有的锁、等待的锁
- 事务 2：正在执行的 SQL、持有的锁、等待的锁
- 回滚了哪个事务

```text
------------------------
LATEST DETECTED DEADLOCK
------------------------
2026-09-08 10:30:00 0x7f1234567890
*** (1) TRANSACTION:
TRANSACTION 12345, ACTIVE 5 sec starting index read
mysql tables in use 1, locked 1
LOCK WAIT 3 lock struct(s), heap size 1136, 2 row lock(s)
MySQL thread id 10, OS thread handle 0x7f..., query id 100 localhost root updating
UPDATE accounts SET balance = balance - 100 WHERE id = 1
*** (1) WAITING FOR THIS LOCK TO BE GRANTED:
RECORD LOCKS space id 10 page no 5 n bits 72 index PRIMARY of table `test`.`accounts`
Record lock, heap no 3 PHYSICAL RECORD: n_fields 4; ...
*** (2) TRANSACTION:
TRANSACTION 12346, ACTIVE 3 sec starting index read
mysql tables in use 1, locked 1
3 lock struct(s), heap size 1136, 2 row lock(s)
MySQL thread id 11, OS thread handle 0x7f..., query id 101 localhost root updating
UPDATE accounts SET balance = balance - 100 WHERE id = 2
*** (2) HOLDS THE LOCK(S):
RECORD LOCKS space id 10 page no 5 n bits 72 index PRIMARY of table `test`.`accounts`
Record lock, heap no 3 PHYSICAL RECORD: n_fields 4; ...
*** (2) WAITING FOR THIS LOCK TO BE GRANTED:
RECORD LOCKS space id 10 page no 5 n bits 72 index PRIMARY of table `test`.`accounts`
Record lock, heap no 4 PHYSICAL RECORD: n_fields 4; ...
*** WE ROLL BACK TRANSACTION (2)
```

分析：事务 1 更新 id=1，等待 id=1 的锁；事务 2 更新 id=2，持有 id=1 的锁（可能之前更新过 id=1），等待 id=2 的锁。循环等待 → 死锁。

### 4.4 锁等待与 innodb_lock_wait_timeout

不是所有锁等待都是死锁。如果事务 A 持有锁，事务 B 等待，没有循环等待，则 B 会一直等待直到：
- A 提交/回滚释放锁，B 获取锁继续执行。
- 等待时间超过 `innodb_lock_wait_timeout`（默认 50 秒），B 超时回滚，返回 `1205: Lock wait timeout exceeded`。

```sql
-- 查看锁等待信息
SELECT * FROM information_schema.innodb_lock_waits;
SELECT * FROM performance_schema.data_lock_waits;  -- MySQL 8.0+

-- 查看当前持有的锁
SELECT * FROM performance_schema.data_locks;  -- MySQL 8.0+
```

### 4.5 死锁预防策略

1. **固定加锁顺序**：所有事务按相同顺序访问资源（如按 ID 从小到大更新），避免循环等待。
2. **缩短事务**：事务尽量短，减少锁持有时间。避免在事务中进行网络调用、用户交互等耗时操作。
3. **低隔离级别**：RC 比 RR 锁冲突少（无间隙锁），如果业务允许可考虑 RC。
4. **合理索引**：确保查询走索引，避免全表扫描导致大量行锁。
5. **避免大事务批量操作**：大批量更新拆分为小事务，减少锁范围和持有时间。
6. **使用乐观锁**：对于并发冲突少的场景，用版本号或 CAS 替代悲观锁。
7. **重试机制**：捕获死锁异常（1213）后重试，死锁通常是偶发的，重试可成功。

---

## 5. 索引原理深入

### 5.1 B+ 树结构与 InnoDB 实现

InnoDB 使用 B+ 树作为索引结构。B+ 树的特点：
- 非叶子节点只存储键值和子节点指针，不存储数据。
- 叶子节点存储所有键值和数据（或主键值），叶子节点之间用双向链表连接。
- 所有查询都要走到叶子节点（查询路径长度固定 = 树高）。

InnoDB 页大小默认 16KB（`innodb_page_size`）。一棵 B+ 树能存储多少数据？

假设：
- 主键 BIGINT（8 字节）+ 指针（6 字节）= 14 字节/索引项
- 非叶子节点一页可存：16384 / 14 ≈ 1170 个索引项
- 叶子节点一页可存：假设一行数据 1KB，一页存 16 行

则：
- 2 层 B+ 树：1170 × 16 ≈ 18,720 行
- 3 层 B+ 树：1170 × 1170 × 16 ≈ 21,902,400 行（约 2200 万行）

因此**千万级数据的表，B+ 树高度通常只有 3 层**，一次查询最多 3 次 IO（如果根节点和非叶子节点在内存中，则只需 1 次 IO）。

### 5.2 聚集索引与辅助索引

**聚集索引（Clustered Index）**：
- 表数据按主键顺序存储在 B+ 树的叶子节点中。
- 一个表只能有一个聚集索引（因为数据只能按一种顺序物理存储）。
- 如果定义了主键，主键就是聚集索引。
- 如果没有主键，InnoDB 选择第一个非空唯一索引作为聚集索引。
- 如果都没有，InnoDB 自动生成一个 6 字节的隐藏主键 `DB_ROW_ID` 作为聚集索引。

**辅助索引（Secondary Index，二级索引/非聚集索引）**：
- 叶子节点存储的是**索引列值 + 主键值**，不是完整行数据。
- 通过辅助索引查询时，先找到主键值，再到聚集索引中查找完整行数据——这个过程叫**回表**。
- 一个表可以有多个辅助索引。

```text
辅助索引 idx(name) 的 B+ 树叶子节点：
[name='Alice', id=10] → [name='Bob', id=5] → [name='Charlie', id=15]
（按 name 排序，每个节点附带主键 id）

查询 SELECT * FROM users WHERE name = 'Bob'：
1. 在 idx(name) 中找到 name='Bob'，得到 id=5
2. 到聚集索引中找到 id=5 的完整行数据（回表）
```

### 5.3 最左匹配原则详解

联合索引 `idx(a, b, c)` 的 B+ 树按 a、b、c 的顺序排序：先按 a 排序，a 相同则按 b 排序，b 相同则按 c 排序。

**最左匹配原则**：查询条件必须从索引的最左列开始，且不能跳过中间列。

| 查询条件 | 是否使用索引 | 使用的索引列 | 说明 |
|----------|-------------|-------------|------|
| `WHERE a = 1` | ✓ | a | 匹配最左列 |
| `WHERE a = 1 AND b = 2` | ✓ | a, b | 连续匹配 |
| `WHERE a = 1 AND b = 2 AND c = 3` | ✓ | a, b, c | 全匹配 |
| `WHERE b = 2` | ✗ | 无 | 跳过了最左列 a |
| `WHERE a = 1 AND c = 3` | 部分 | a | 匹配 a，但跳过 b，c 无法用索引 |
| `WHERE a > 1 AND b = 2` | 部分 | a | a 是范围查询，b 无法用索引（范围查询后的列不能用索引） |
| `WHERE a = 1 AND b > 2 AND c = 3` | 部分 | a, b | b 是范围查询，c 无法用索引 |

**范围查询后的列不能用索引**：这是最左匹配的重要推论。因为 B+ 树在 a 确定后按 b 排序，如果 b 是范围（b>2），则 b 值不唯一，c 在这些 b 值中不是有序的，无法用二分查找定位 c。

**优化技巧**：将等值查询列放在联合索引前面，范围查询列放在后面。例如经常查询 `WHERE a=? AND b>?`，索引应建为 `idx(a,b)` 而非 `idx(b,a)`。

### 5.4 覆盖索引与回表

**覆盖索引（Covering Index）**：如果查询需要的所有列都包含在索引中，则不需要回表，直接从辅助索引中返回数据。

```sql
-- 联合索引 idx(name, age)
SELECT name, age FROM users WHERE name = 'Bob';
-- 索引中包含 name 和 age，不需要回表 → 覆盖索引
-- EXPLAIN Extra: Using index

SELECT * FROM users WHERE name = 'Bob';
-- 需要所有列，索引中没有其他列 → 需要回表
```

覆盖索引的性能提升：避免回表的随机 IO（辅助索引是顺序的，回表到聚集索引是随机的）。对于高频查询，考虑将需要的列加入联合索引以实现覆盖索引。

### 5.5 索引失效条件详解

| 失效场景 | 示例 | 原因 |
|----------|------|------|
| 函数/运算作用于索引列 | `WHERE YEAR(create_time) = 2026` | 函数改变了索引列的值，B+ 树无法直接定位 |
| 隐式类型转换 | `WHERE varchar_col = 123` | 字符串列与数字比较，MySQL 将列转为数字，相当于函数 |
| 模糊查询前缀通配 | `WHERE name LIKE '%bob'` | 前缀不确定，无法用 B+ 树前缀匹配；`LIKE 'bob%'` 可以用索引 |
| OR 连接非索引列 | `WHERE name = 'bob' OR age = 20`（age 无索引） | 只要有一个条件无索引，就需要全表扫描 |
| 不符合最左匹配 | `WHERE b = 2`（索引 idx(a,b)） | 跳过最左列 |
| 索引列上使用 NOT != <> | `WHERE age != 20` | 优化器认为范围扫描+回表不如全表扫描 |
| 索引列上使用 IS NOT NULL | `WHERE name IS NOT NULL` | 优化器可能选择全表扫描（取决于选择性） |

**隐式类型转换的典型坑**：
```sql
-- phone 是 VARCHAR 类型
SELECT * FROM users WHERE phone = 13800138000;
-- 索引失效！因为 phone 是字符串，与数字比较时 MySQL 将 phone 转为数字
-- 正确写法：
SELECT * FROM users WHERE phone = '13800138000';
```

### 5.6 索引下推（ICP，5.6+）

索引下推（Index Condition Pushdown，ICP）是 MySQL 5.6 引入的优化：在存储引擎层（InnoDB）利用索引中的列过滤数据，减少回表次数。

```sql
-- 联合索引 idx(name, age)
SELECT * FROM users WHERE name LIKE '张%' AND age = 20;
-- 没有 ICP：InnoDB 根据 name LIKE '张%' 找到所有匹配的索引项，逐个回表，
--           然后在 Server 层过滤 age=20。
-- 有 ICP：InnoDB 在索引中同时检查 age=20（因为 age 在索引中），
--         只回表满足两个条件的行，减少回表次数。
-- EXPLAIN Extra: Using index condition
```

ICP 默认开启（`optimizer_switch='index_condition_pushdown=on'`）。

### 5.7 变更缓冲（Change Buffer）

变更缓冲（旧称插入缓冲 Insert Buffer）是 InnoDB 对**辅助索引**的写优化：

- 当 INSERT/UPDATE/DELETE 操作修改辅助索引页时，如果该页不在内存（Buffer Pool）中，InnoDB 不立即加载该页（避免随机 IO），而是将变更记录到 Change Buffer 中。
- 后续查询访问该页时，再将 Change Buffer 中的变更合并（merge）到页中。
- 后台线程也会定期 merge Change Buffer。

Change Buffer 适用条件：
- 只适用于**非唯一辅助索引**（唯一索引需要检查唯一性，必须加载页）。
- 适用于写多读少的场景（如果写完立即读，merge 会马上发生，没有收益）。

`innodb_change_buffer_max_size` 控制 Change Buffer 占 Buffer Pool 的比例（默认 25，最大 50）。

---

## 6. EXPLAIN 执行计划深度解读

### 6.1 EXPLAIN 输出字段总览

```sql
EXPLAIN SELECT * FROM users WHERE name = 'Bob';
```

| 字段 | 说明 |
|------|------|
| id | 查询中 SELECT 或操作表的顺序标识 |
| select_type | 查询类型（SIMPLE/PRIMARY/SUBQUERY/DERIVED/UNION 等） |
| table | 输出行对应的表 |
| partitions | 匹配的分区 |
| type | 访问类型（最重要，从优到劣） |
| possible_keys | 可能使用的索引 |
| key | 实际使用的索引 |
| key_len | 使用的索引字节数（可判断用了索引的哪些列） |
| ref | 与索引比较的列或常量 |
| rows | 预估需要检查的行数 |
| filtered | 按表条件过滤的行百分比 |
| Extra | 额外信息（Using index/Using where/Using filesort 等） |

### 6.2 type 字段：访问类型从优到劣

| type | 说明 | 性能 |
|------|------|------|
| system | 表只有一行（系统表） | 最优 |
| const | 主键或唯一索引等值查询，最多匹配一行 | 极优 |
| eq_ref | 联表查询中，使用主键或唯一索引关联，每行最多匹配一行 | 优 |
| ref | 非唯一索引等值查询，可能匹配多行 | 良 |
| fulltext | 全文索引 | 良 |
| ref_or_null | 类似 ref，但额外查询 NULL 值 | 中 |
| index_merge | 索引合并（多个索引合并使用） | 中 |
| unique_subquery | IN 子查询中使用唯一索引 | 中 |
| index_subquery | IN 子查询中使用非唯一索引 | 中 |
| range | 索引范围查询（BETWEEN/IN/>/</LIKE 'prefix%'） | 中 |
| index | 全索引扫描（扫描整个索引树，比 ALL 快因为索引通常比数据小） | 差 |
| ALL | 全表扫描 | 最差 |

**优化目标**：至少达到 `range` 级别，理想是 `ref` 或 `eq_ref`。`ALL`（全表扫描）需要优化。

### 6.3 key / key_len / ref 字段

- **key**：实际使用的索引名。`NULL` 表示没有使用索引。
- **key_len**：使用的索引字节数。通过 key_len 可以推断用了联合索引的哪些列：
  - INT NOT NULL：4 字节
  - INT NULL：5 字节（多 1 字节 NULL 标记）
  - VARCHAR(10) NOT NULL（utf8mb4）：10×4 + 2 = 42 字节（2 字节长度）
  - VARCHAR(10) NULL（utf8mb4）：10×4 + 2 + 1 = 43 字节
  - DATETIME：5 字节（MySQL 5.6+）
  - TIMESTAMP：4 字节

例如联合索引 `idx(a INT, b VARCHAR(10))`，key_len=4 表示只用了 a 列，key_len=46 表示用了 a 和 b 两列。

- **ref**：与索引列比较的对象。`const` 表示常量，`db.table.column` 表示联表中的列。

### 6.4 rows 与 filtered

- **rows**：优化器预估需要扫描的行数。这是预估值，不是实际值。rows 越大，查询越慢。
- **filtered**：经过 WHERE 条件过滤后，剩余行占扫描行的百分比。filtered 越低，说明大量扫描的行被过滤掉了，索引效率不高（可能需要更好的索引）。

例如 rows=10000, filtered=10.00，表示扫描了 10000 行，只有 1000 行满足条件，90% 被浪费。

### 6.5 Extra 字段高频值解读

| Extra | 说明 | 性能影响 |
|-------|------|----------|
| Using index | 覆盖索引，不需要回表 | 好 |
| Using where | 在 Server 层用 WHERE 过滤（存储引擎返回的行不满足条件） | 正常 |
| Using index condition | 索引下推（ICP） | 好 |
| Using filesort | 需要额外的排序操作（无法用索引排序） | 差，需优化 |
| Using temporary | 使用临时表（GROUP BY/DISTINCT 等） | 差，需优化 |
| Using join buffer (Block Nested Loop) | 联表使用了连接缓冲区（被驱动表无索引） | 差，需加索引 |
| Impossible WHERE | WHERE 条件永远为 false | 提示 |
| Select tables optimized away | 聚合函数（MIN/MAX）直接从索引获取 | 好 |
| No tables used | 没有 FROM 的查询（如 SELECT 1） | 正常 |

**Using filesort** 不代表一定用磁盘文件排序，可能在内存中排序（sort buffer）。但无论如何，额外排序都有性能开销，应尽量让 ORDER BY 的列走索引。

### 6.6 优化器索引选择过程

MySQL 优化器选择索引的过程：
1. 根据 WHERE 条件找出所有可能使用的索引（possible_keys）。
2. 对每个可能的索引，估算使用该索引的成本（扫描行数 + 回表次数 + 排序成本）。
3. 选择成本最低的索引。
4. 如果所有索引的成本都高于全表扫描，则选择全表扫描（ALL）。

优化器可能选错索引的原因：
- **统计信息不准确**：`innodb_stats_persistent_sample_pages` 控制采样页数，默认 20。数据分布变化大时统计信息可能过时。可执行 `ANALYZE TABLE` 更新统计信息。
- **回表成本估算偏差**：优化器假设回表是随机 IO，成本高。但如果数据在内存中，实际成本低。
- **强制索引**：当优化器选错时，可用 `FORCE INDEX(idx_name)` 强制使用指定索引。

```sql
-- 查看索引统计信息
SHOW INDEX FROM users;
-- Cardinality 列表示索引的基数（唯一值数量的估算值），基数越高选择性越好

-- 更新统计信息
ANALYZE TABLE users;

-- 强制使用索引
SELECT * FROM users FORCE INDEX(idx_name) WHERE ...;
```

---

## 7. SQL 优化实战

### 7.1 慢查询日志配置与分析

```sql
-- 查看慢查询配置
SHOW VARIABLES LIKE 'slow_query%';
SHOW VARIABLES LIKE 'long_query_time';

-- 开启慢查询日志
SET GLOBAL slow_query_log = 'ON';
SET GLOBAL long_query_time = 1;  -- 超过 1 秒的查询记录
SET GLOBAL log_queries_not_using_indexes = 'ON';  -- 记录未使用索引的查询
```

慢查询日志文件分析工具：
```bash
# mysqldumpslow：MySQL 自带
mysqldumpslow -s t -t 10 /var/log/mysql/slow.log
# -s t：按总时间排序，-t 10：显示前 10 条

# pt-query-digest：Percona Toolkit，功能更强
pt-query-digest /var/log/mysql/slow.log
```

### 7.2 SHOW PROFILE 分析

```sql
-- 开启 profiling
SET profiling = 1;

-- 执行查询
SELECT * FROM users WHERE name = 'Bob';

-- 查看查询列表
SHOW PROFILES;

-- 查看具体查询的各阶段耗时
SHOW PROFILE FOR QUERY 1;
-- 输出：starting、checking permissions、Opening tables、init、System lock、
--       optimizing、statistics、preparing、executing、Sending data、end 等阶段耗时

-- 查看 CPU/IO 等资源
SHOW PROFILE CPU, BLOCK IO FOR QUERY 1;
```

`Sending data` 阶段耗时高通常表示扫描行数多或网络传输量大。

### 7.3 JOIN 优化

MySQL JOIN 使用**嵌套循环连接（Nested Loop Join）**：驱动表（外层）逐行扫描，每行到被驱动表（内层）查找匹配行。

优化原则：
1. **小表驱动大表**：驱动表扫描行数少，外层循环次数少。MySQL 优化器会自动选择小表作为驱动表。
2. **被驱动表的关联列必须有索引**：否则每次关联都全表扫描（Block Nested Loop）。
3. **避免超过 3 张表的 JOIN**：多表 JOIN 优化器选择执行计划的空间大，容易选错。
4. **同类型同字符集关联**：关联列类型不同会导致隐式转换，索引失效。

```sql
-- 被驱动表关联列无索引时，EXPLAIN 会显示：
-- Extra: Using join buffer (Block Nested Loop)
-- 解决：给被驱动表的关联列加索引
```

### 7.4 ORDER BY 优化

ORDER BY 有两种排序方式：
1. **索引排序**：ORDER BY 的列是索引列，且符合最左匹配，直接按索引顺序返回，无需额外排序。
2. **文件排序（filesort）**：无法用索引排序时，将结果集取出后在内存/磁盘中排序。

优化方法：
- ORDER BY 的列加入联合索引，且放在 WHERE 条件列之后。
- 例如 `WHERE a = ? ORDER BY b`，索引 `idx(a,b)` 可以利用索引排序。
- 避免 `ORDER BY 表达式` 或 `ORDER BY 函数(col)`。
- 多列排序时，升降序必须一致（`ORDER BY a ASC, b DESC` 无法用索引排序，MySQL 8.0 支持降序索引可解决）。

### 7.5 GROUP BY 优化

GROUP BY 默认会排序（等效 ORDER BY），可能产生临时表和 filesort。

优化方法：
- GROUP BY 的列走索引，避免临时表。
- 如果不需要排序，加 `ORDER BY NULL` 禁止排序（MySQL 8.0 已默认不排序）。
- 使用 `SQL_BIG_RESULT` 或 `SQL_SMALL_RESULT` 提示优化器选择合适的临时表。
- 超大数据量的 GROUP BY 考虑用汇总表或预计算。

### 7.6 分页深翻页优化

```sql
-- 深翻页问题：LIMIT 1000000, 10 需要扫描 1000010 行
SELECT * FROM orders ORDER BY id LIMIT 1000000, 10;

-- 优化1：延迟关联（覆盖索引先定位 id，再回表）
SELECT o.* FROM orders o
INNER JOIN (SELECT id FROM orders ORDER BY id LIMIT 1000000, 10) t
ON o.id = t.id;

-- 优化2：书签方式（记录上一页最后一个 id，用 WHERE 过滤）
SELECT * FROM orders WHERE id > 1000000 ORDER BY id LIMIT 10;
-- 适用于 id 连续递增的场景，性能最优
```

### 7.7 优化 checklist

1. □ 查询是否走了索引？（EXPLAIN type 非 ALL）
2. □ 联合索引是否符合最左匹配？
3. □ 是否有隐式类型转换？
4. □ ORDER BY/GROUP BY 是否走了索引？（无 Using filesort/temporary）
5. □ 被驱动表关联列是否有索引？
6. □ 是否有 SELECT *？只查询需要的列，可能实现覆盖索引。
7. □ 深翻页是否用了延迟关联或书签方式？
8. □ 索引列是否避免了函数/运算？
9. □ 统计信息是否最新？（ANALYZE TABLE）
10. □ 是否有大事务/长事务导致锁持有时间过长？

---

## 8. 缓存策略

### 8.1 Cache-Aside（旁路缓存）

最常用的缓存模式，应用层同时管理缓存和数据库：

**读流程**：
1. 先读缓存，命中则返回。
2. 缓存未命中，读数据库。
3. 数据库结果写入缓存。
4. 返回数据。

**写流程**：
1. 更新数据库。
2. 删除缓存（不是更新缓存）。

```cpp
// Cache-Aside 读
Data read(const std::string& key) {
    Data d = cache.get(key);
    if (d.valid()) return d;
    d = db.read(key);
    cache.set(key, d, ttl);
    return d;
}

// Cache-Aside 写
void write(const std::string& key, const Data& d) {
    db.update(key, d);
    cache.del(key);  // 删除而非更新
}
```

为什么写时**删除缓存**而不是**更新缓存**：
- 并发写时，更新缓存可能导致旧值覆盖新值（写 A 更新 DB→写 B 更新 DB→写 B 更新缓存→写 A 更新缓存，缓存是 A 的旧值）。
- 删除缓存更简单，下次读时再加载最新值。
- 有些缓存值计算成本高，写时更新浪费（可能这个缓存近期不会被读）。

### 8.2 Read Through / Write Through

**Read Through**：缓存层封装了读逻辑，应用只与缓存交互。缓存未命中时，缓存层自己从数据库加载并写入缓存。

**Write Through**：缓存层封装了写逻辑，应用只写缓存。缓存层同步写入数据库和缓存，两者都成功才返回。

特点：
- 应用层简单，只与缓存交互。
- Write Through 同步写 DB，写延迟较高。
- 适合缓存作为主要数据访问层的场景（如 Caffeine + 自研缓存层）。

### 8.3 Write Behind（异步写回）

Write Behind（Write Back）：应用写缓存后立即返回，缓存层异步批量写入数据库。

特点：
- 写性能极高（写内存即返回）。
- 数据可能丢失（缓存宕机时未刷盘的数据丢失）。
- 数据库与缓存可能长时间不一致。
- 适合写密集、可容忍少量数据丢失的场景（如计数器、点赞数），通常配合定时刷盘和日志持久化。

### 8.4 策略对比与选型

| 策略 | 一致性 | 写性能 | 读性能 | 实现复杂度 | 适用场景 |
|------|--------|--------|--------|-----------|----------|
| Cache-Aside | 最终一致 | 中 | 高 | 低 | 绝大多数业务场景 |
| Read/Write Through | 强一致（写时同步） | 中低 | 高 | 中 | 缓存作为统一访问层 |
| Write Behind | 弱一致 | 极高 | 高 | 高 | 写密集、可容忍丢失 |

互联网应用几乎都用 **Cache-Aside**，配合缓存一致性方案（见下节）。

---

## 9. 缓存一致性深入

### 9.1 双写一致性问题分析

Cache-Aside 模式下，"先更新 DB 再删除缓存"是标准方案，但在并发场景下仍有极小概率不一致：

```text
时序：
1. 缓存刚好失效（或被删除）
2. 线程 A 读缓存，未命中 → 读 DB，得到旧值 v1
3. 线程 B 写 DB，更新为 v2 → 删除缓存
4. 线程 A 将旧值 v1 写入缓存
→ 缓存中是 v1（旧值），DB 中是 v2（新值），不一致！
```

这个时序需要满足：读 DB（步骤2）比写 DB（步骤3）慢，且写操作比读操作先完成删缓存。实际中写操作通常比读操作慢（写要加锁、刷 redo log），所以这个时序发生概率极低，但理论上存在。

### 9.2 延迟双删

延迟双删：写操作时，先删缓存 → 更新 DB → 延迟一段时间（如 500ms）→ 再删一次缓存。

```cpp
void writeWithDelayDoubleDelete(const std::string& key, const Data& d) {
    cache.del(key);           // 第一次删
    db.update(key, d);         // 更新 DB
    std::thread([key]() {      // 异步延迟删
        std::this_thread::sleep_for(std::chrono::milliseconds(500));
        cache.del(key);        // 第二次删，清除可能的旧值
    }).detach();
}
```

延迟时间应大于一次读业务的耗时（确保读线程已完成写缓存）。延迟双删能解决上述并发不一致问题，但：
- 增加了复杂度。
- 延迟时间难以精确设定。
- 异步删除失败需要重试机制。

### 9.3 canal 订阅 binlog 异步删缓存

更可靠的方案：通过订阅 MySQL binlog，异步删除缓存。

**架构**：
```text
应用 → 写 MySQL → binlog → canal（模拟 MySQL 从节点，解析 binlog）→ MQ → 消费者 → 删缓存
```

**canal** 是阿里巴巴开源的 MySQL binlog 增量订阅组件：
- canal 伪装成 MySQL 从节点，向主节点发送 `COM_BINLOG_DUMP` 请求。
- MySQL 主节点推送 binlog 给 canal。
- canal 解析 binlog（ROW 模式），得到每行数据的变更（before image / after image）。
- canal 将变更数据推送到 MQ（RocketMQ/Kafka）或直接通过 TCP 推送。

**消费者**：
- 监听 binlog 变更消息。
- 根据表名和主键，删除对应的缓存 key。
- 保证最终一致性（DB 变更后，缓存最终会被删除）。

优点：
- 与业务解耦，业务代码只写 DB，不需要关心缓存。
- 可靠性高，binlog 持久化，canal 支持位点持久化，不会丢消息。
- 支持多缓存消费者（同一个 binlog 变更可同时删 Redis、清本地缓存、更新 ES 等）。

缺点：
- 架构复杂，需要部署 canal 和 MQ。
- 有一定延迟（通常毫秒到秒级）。

```yaml
# canal 配置示例（instance.properties）
canal.instance.master.address=127.0.0.1:3306
canal.instance.dbUsername=canal
canal.instance.dbPassword=canal
canal.instance.defaultDatabaseName=test
canal.instance.filter.regex=test\\.orders,test\\.users  # 只订阅这两张表
```

### 9.4 go-mysql-transfer 等工具

除了 canal，还有其他 binlog 订阅工具：

| 工具 | 语言 | 特点 |
|------|------|------|
| canal | Java | 阿里开源，功能最全，支持 HA、MQ、多数据源 |
| go-mysql-transfer | Go | 轻量级，支持直接将 binlog 变更写入 Redis/MongoDB/ES，无需 MQ |
| Maxwell | Java | Zendesk 开源，输出 JSON 到 Kafka/Kinesis |
| Debezium | Java | RedHat 开源，支持 MySQL/PostgreSQL/MongoDB，基于 Kafka Connect |
| mysql-replication-listener | C++ | 轻量 C++ 库，适合 C++ 项目集成 |

**go-mysql-transfer** 适合中小团队：配置规则后，binlog 变更自动同步到 Redis（如 `UPDATE users SET name=? WHERE id=?` → `DEL cache:user:{id}`），不需要写消费者代码。

### 9.5 最终一致性方案选型

| 方案 | 一致性 | 复杂度 | 延迟 | 适用场景 |
|------|--------|--------|------|----------|
| 先更 DB 再删缓存 | 最终一致（极小概率不一致） | 低 | 实时 | 大多数业务 |
| 延迟双删 | 最终一致 | 中 | 实时+延迟 | 对一致性要求稍高 |
| canal 订阅 binlog | 最终一致（可靠） | 高 | 秒级 | 大规模、多缓存、多下游 |
| 分布式锁串行化 | 强一致 | 高 | 实时 | 金融级强一致 |
| 不缓存（直接读 DB） | 强一致 | 低 | 实时 | 数据量小、并发低 |

生产实践：通常用"先更 DB 再删缓存"作为基础方案，对一致性要求高的关键数据（如余额、库存）配合"延迟双删"或"canal + 重试"，极端场景用分布式锁或乐观锁兜底。

---

## 10. 常见坑与最佳实践

### 10.1 常见坑汇总

| 坑 | 现象 | 原因 | 解决方案 |
|----|------|------|----------|
| 隐式类型转换 | 索引失效，全表扫描 | 字符串列与数字比较 | 比较时类型一致，字符串加引号 |
| 深翻页慢 | LIMIT 越翻越慢 | 扫描大量不需要的行 | 延迟关联、书签方式 |
| 间隙锁死锁 | 并发 INSERT 死锁 | RR 下间隙锁冲突 | 降低隔离级别为 RC、固定插入顺序 |
| 大事务 | 锁持有时间长、undo log 膨胀 | 事务中包含大量操作或外部调用 | 拆分事务、缩短事务 |
| 连接泄漏 | 连接池耗尽 | 未关闭 ResultSet/Statement/Connection | 使用 try-with-resources、连接池监控 |
| 索引过多 | 写性能下降、优化器选错 | 每个查询都加索引，不考虑合并 | 合并联合索引、删除无用索引 |
| 字符集不一致 | 联表索引失效 | 两表字符集不同（utf8 vs utf8mb4） | 统一字符集为 utf8mb4 |
| ORDER BY NULL | GROUP BY 慢 | 默认排序产生 filesort | 显式 ORDER BY NULL（MySQL 8.0 已优化） |
| 长事务导致主从延迟 | 从节点延迟越来越大 | 大事务在从节点重放耗时 | 避免大事务、拆分批量操作 |

### 10.2 最佳实践

1. **表设计**：
   - 必须有主键（推荐自增 BIGINT 或雪花 ID），避免使用 UUID 作为聚集索引（随机写入导致页分裂）。
   - 字段定义 NOT NULL，NULL 会占用额外空间且影响索引优化。
   - 用 DECIMAL 存储金额，不用 FLOAT/DOUBLE（精度丢失）。
   - 用 TINYINT 代替 ENUM（ENUM 修改需要 DDL）。
   - 字符集统一 utf8mb4（支持 emoji）。

2. **索引设计**：
   - 联合索引遵循"等值在前、范围在后、高频列优先"。
   - 单表索引数控制在 5 个以内，避免过多索引影响写性能。
   - 定期用 `sys.schema_unused_indexes` 检查未使用的索引并删除。
   - 避免在低选择性列（如性别、状态）上单独建索引。

3. **SQL 编写**：
   - 避免 SELECT *，只查需要的列。
   - 避免在索引列上使用函数/运算。
   - 批量操作用批量 INSERT/UPDATE，减少网络往返和事务次数。
   - 分页用 LIMIT + 书签，避免深翻页。
   - 用 EXISTS 代替 IN（子查询结果集大时）。

4. **事务管理**：
   - 事务尽量短，不在事务中做外部调用（HTTP、RPC）。
   - 避免在事务中混合 InnoDB 和 MyISAM 操作（MyISAM 不支持事务，回滚时数据不一致）。
   - 监控长事务：`information_schema.innodb_trx` 中 `trx_started` 超过一定时间的事务。
   - 死锁后重试，不要忽略死锁异常。

5. **运维监控**：
   - 开启慢查询日志，定期分析。
   - 监控连接数、QPS、TPS、主从延迟、锁等待。
   - 定期 `ANALYZE TABLE` 更新统计信息。
   - 备份策略：全量 + 增量（binlog），定期恢复演练。

---

## 11. 快速参考卡片

### 11.1 EXPLAIN 字段速查表

| 字段 | 关键值 | 含义 |
|------|--------|------|
| type | system/const/eq_ref/ref/range/index/ALL | 访问类型，越左越好 |
| key | 索引名 / NULL | 实际使用的索引 |
| key_len | 字节数 | 用了索引的哪些列 |
| rows | 数字 | 预估扫描行数 |
| Extra | Using index | 覆盖索引，好 |
| Extra | Using where | Server 层过滤 |
| Extra | Using index condition | 索引下推，好 |
| Extra | Using filesort | 额外排序，需优化 |
| Extra | Using temporary | 临时表，需优化 |
| Extra | Using join buffer | 联表无索引，需优化 |

### 11.2 锁类型对照表

| 锁类型 | 粒度 | 模式 | 说明 |
|--------|------|------|------|
| 记录锁 | 行 | X/S | 锁定索引记录 |
| 间隙锁 | 间隙 | - | 锁定索引间隙，防插入（RR） |
| Next-Key Lock | 行+间隙 | X/S | 记录锁+间隙锁，左开右闭 |
| 插入意向锁 | 间隙 | - | INSERT 时设置，与间隙锁互斥 |
| 自增锁 | 表 | - | AUTO_INCREMENT 列，表级 |
| 意向锁(IS/IX) | 表 | IS/IX | 表示打算加行锁，表级协调 |

### 11.3 索引优化 checklist

- [ ] 查询条件列有索引
- [ ] 联合索引符合最左匹配
- [ ] 索引列无函数/运算/隐式转换
- [ ] ORDER BY/GROUP BY 走索引（无 filesort/temporary）
- [ ] 覆盖索引避免回表
- [ ] 深翻页用延迟关联/书签
- [ ] 被驱动表关联列有索引
- [ ] 统计信息最新（ANALYZE TABLE）
- [ ] 索引数量合理（≤5个/表）

### 11.4 事务隔离级别速查

| 级别 | 脏读 | 不可重复读 | 幻读 | 锁 |
|------|------|-----------|------|-----|
| RU | ✗ | ✗ | ✗ | 无 |
| RC | ✓ | ✗ | ✗ | 记录锁 |
| RR | ✓ | ✓ | ✓(InnoDB) | Next-Key Lock |
| SERIALIZABLE | ✓ | ✓ | ✓ | 全加锁 |

### 11.5 常用配置

```ini
# 事务与锁
transaction_isolation = REPEATABLE-READ
innodb_lock_wait_timeout = 50
innodb_deadlock_detect = ON

# 索引与优化
innodb_buffer_pool_size = 70% 物理内存
innodb_page_size = 16K
optimizer_switch = 'index_condition_pushdown=on'

# 慢查询
slow_query_log = ON
long_query_time = 1
log_queries_not_using_indexes = ON

# 二进制日志
log_bin = mysql-bin
binlog_format = ROW
expire_logs_days = 7
sync_binlog = 1
innodb_flush_log_at_trx_commit = 1
```

---

上一篇：《06-Redis深入：协议存储与集群.md》
下一篇：《08-Ceph分布式存储.md》
