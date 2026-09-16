# MySQL 数据库精要

> 本节目标：C++ 进阶知识库「数据库」篇（一）。面向学过 C++ 网络编程（见《../03-网络编程/02-IO多路复用与Reactor模型.md》）、准备后台开发面试的读者。示例基于 MySQL 5.7 / 8.0，涉及底层实现处均标注「InnoDB 实现」；面试高频考点以【高频】标出。前置建议：先看《../03-网络编程/02-IO多路复用与Reactor模型.md》理解连接与协议，本篇第 12 节会从 C++ 视角谈连接池。

## 本章速览

- [1. 概述](#1-概述)
  - [1.1 MySQL 在 C++ 后台技术栈中的位置](#11-mysql-在-c-后台技术栈中的位置)
  - [1.2 版本演进（面试常考的版本差异）](#12-版本演进面试常考的版本差异)
  - [1.3 本文学习路线](#13-本文学习路线)
- [2. 基础架构【高频】](#2-基础架构高频)
  - [2.1 逻辑架构分层](#21-逻辑架构分层)
  - [2.2 Server 层与引擎层职责划分](#22-server-层与引擎层职责划分)
  - [2.3 一条 SELECT 的执行流程](#23-一条-select-的执行流程)
  - [2.4 一条 UPDATE 的执行流程（含日志，详细见第 10 章）](#24-一条-update-的执行流程含日志详细见第-10-章)
- [3. 存储引擎](#3-存储引擎)
  - [3.1 InnoDB vs MyISAM 对比](#31-innodb-vs-myisam-对比)
  - [3.2 为什么生产一律 InnoDB](#32-为什么生产一律-innodb)
- [4. 数据类型与表设计](#4-数据类型与表设计)
  - [4.1 常用类型选择](#41-常用类型选择)
  - [4.2 建表规范清单](#42-建表规范清单)
  - [4.3 隐式类型转换导致的索引失效（典型坑）](#43-隐式类型转换导致的索引失效典型坑)
- [5. SQL 进阶](#5-sql-进阶)
  - [5.1 JOIN 四类型对比](#51-join-四类型对比)
  - [5.2 子查询 vs JOIN 性能讨论](#52-子查询-vs-join-性能讨论)
  - [5.3 GROUP BY 与聚合](#53-group-by-与聚合)
  - [5.4 窗口函数（MySQL 8.0+，5.7 不支持）](#54-窗口函数mysql-8057-不支持)
  - [5.5 CTE 与递归（MySQL 8.0+）](#55-cte-与递归mysql-80)
  - [5.6 分页深翻页优化【高频】](#56-分页深翻页优化高频)
- [6. EXPLAIN 与执行计划【高频】](#6-explain-与执行计划高频)
  - [6.1 EXPLAIN 输出字段详解](#61-explain-输出字段详解)
  - [6.2 type 级别：从好到差](#62-type-级别从好到差)
  - [6.3 Extra 高频值](#63-extra-高频值)
  - [6.4 慢查询定位三步](#64-慢查询定位三步)
- [7. 索引原理【高频·最重要章节】](#7-索引原理高频最重要章节)
  - [7.1 B+ 树结构（InnoDB 实现）](#71-b-树结构innodb-实现)
  - [7.2 为什么选 B+ 树（对比表）](#72-为什么选-b-树对比表)
  - [7.3 聚簇索引 vs 二级索引与回表](#73-聚簇索引-vs-二级索引与回表)
  - [7.4 最左前缀原则（联合索引 idx(a,b,c)）](#74-最左前缀原则联合索引-idxabc)
  - [7.5 索引失效场景表](#75-索引失效场景表)
  - [7.6 索引设计准则速记](#76-索引设计准则速记)
- [8. 事务与 MVCC【高频】](#8-事务与-mvcc高频)
  - [8.1 ACID 及 InnoDB 实现手段](#81-acid-及-innodb-实现手段)
  - [8.2 隔离级别与并发问题对照](#82-隔离级别与并发问题对照)
  - [8.3 三种并发问题的时序](#83-三种并发问题的时序)
  - [8.4 MVCC 原理详解（InnoDB 实现）](#84-mvcc-原理详解innodb-实现)
  - [8.5 RC 与 RR 的本质区别【高频】](#85-rc-与-rr-的本质区别高频)
- [9. 锁体系（InnoDB 实现）](#9-锁体系innodb-实现)
  - [9.1 锁粒度分类](#91-锁粒度分类)
  - [9.2 行锁三种类型](#92-行锁三种类型)
  - [9.3 加锁规则要点](#93-加锁规则要点)
  - [9.4 死锁案例与排查](#94-死锁案例与排查)
- [10. 日志体系【高频】](#10-日志体系高频)
  - [10.1 三大日志职责](#101-三大日志职责)
  - [10.2 redo log](#102-redo-log)
  - [10.3 binlog](#103-binlog)
  - [10.4 redo log vs binlog 对比](#104-redo-log-vs-binlog-对比)
  - [10.5 两阶段提交（redo log 与 binlog 的一致性）](#105-两阶段提交redo-log-与-binlog-的一致性)
  - [10.6 一条 UPDATE 的完整链路（串联图）](#106-一条-update-的完整链路串联图)
- [11. 高可用与扩展](#11-高可用与扩展)
  - [11.1 主从复制原理【高频】](#111-主从复制原理高频)
  - [11.2 复制模式](#112-复制模式)
  - [11.3 主从延迟原因与应对](#113-主从延迟原因与应对)
  - [11.4 读写分离与中间件](#114-读写分离与中间件)
  - [11.5 分库分表](#115-分库分表)
- [12. 性能优化实践清单](#12-性能优化实践清单)
  - [12.1 连接与内存参数](#121-连接与内存参数)
  - [12.2 批量插入优化](#122-批量插入优化)
  - [12.3 大表 DDL 的坑](#123-大表-ddl-的坑)
  - [12.4 连接池为什么必要（C++ 视角）](#124-连接池为什么必要c-视角)
- [13. 常用运维命令速查表](#13-常用运维命令速查表)
- [14. 快速参考卡片](#14-快速参考卡片)
  - [14.1 这条 SQL 慢怎么排查（三步）](#141-这条-sql-慢怎么排查三步)
  - [14.2 索引怎么设计（准则清单）](#142-索引怎么设计准则清单)
  - [14.3 选 RC 还是 RR](#143-选-rc-还是-rr)
  - [14.4 面试被问 MVCC（三句话版本）](#144-面试被问-mvcc三句话版本)
- [15. 常见问题与坑](#15-常见问题与坑)

---

## 1. 概述

### 1.1 MySQL 在 C++ 后台技术栈中的位置

```text
      ┌────────────────────────────────────────────────┐
      │              C++ 业务服务进程                    │
      │   Reactor/epoll 事件循环 + 线程池 + 业务逻辑      │
      └──────────┬─────────────────────┬───────────────┘
                 │ MySQL 客户端协议      │ RESP 协议
                 │ (libmysqlclient)     │ (hiredis)
                 ▼                     ▼
        ┌────────────────┐      ┌────────────────┐
        │     MySQL      │      │     Redis      │
        │  磁盘持久化     │      │   内存缓存      │
        │  关系型/事务/   │      │   KV/非事务/    │
        │  行锁/崩溃恢复  │      │   单线程模型     │
        └───────┬────────┘      └────────────────┘
                ▼
   磁盘文件: 表数据(.ibd) + redo log + binlog + undo log
```

典型读写链路：请求到达 → 先查 Redis 缓存 → 未命中则回源 MySQL → 写请求落 MySQL 并失效缓存。C++ 侧通过 libmysqlclient / MySQL Connector/C++ 访问，长连接 + 连接池复用（第 12 节）。

### 1.2 版本演进（面试常考的版本差异）

| 版本 | 发布年 | 关键变化 | 面试要点 |
| --- | --- | --- | --- |
| 5.5 | 2010 | **默认存储引擎改为 InnoDB**（此前默认 MyISAM） | 「默认 InnoDB 是从 5.5 开始的，不是 5.7」——纠正这句常见错误说法本身就是考点 |
| 5.6 | 2013 | ICP 索引下推、GTID 复制、InnoDB 支持全文索引、查询缓存默认关闭 | 查询缓存 5.6 起默认关闭 |
| 5.7 | 2015 | JSON 类型、在线 DDL 增强、临时表改 InnoDB、基于组提交的并行复制、sys 库 | sql_mode 默认含 ONLY_FULL_GROUP_BY |
| 8.0 | 2018 | **默认字符集 utf8mb4**（utf8mb4_0900_ai_ci）、**窗口函数与 CTE**、**原子 DDL**、降序索引真正生效、隐藏索引、函数索引(8.0.13)、即时加列(8.0.12)、hash join(8.0.18)、**删除查询缓存**、数据字典 InnoDB 化、默认认证插件 caching_sha2_password、SET PERSIST | 问「8.0 相比 5.7 有什么新特性」可任举以上 3~5 条 |

### 1.3 本文学习路线

基础架构 → 存储引擎 → 类型与表设计 → SQL 进阶 → EXPLAIN → 索引原理（核心）→ 事务与 MVCC（核心）→ 锁 → 日志（核心）→ 高可用与分库分表 → 优化实践。前六章是「会用」，后五章是「懂原理」，面试深挖都在后五章。

---

## 2. 基础架构【高频】

### 2.1 逻辑架构分层

```text
┌───────────────────────────────────────────────────────────┐
│                      MySQL Server 层                       │
│                                                           │
│  连接器 ──→ 查询缓存(8.0已删除) ──→ 分析器 ──→ 优化器 ──→ 执行器 │
│  (TCP握手/  (5.6起默认关闭,      (词法/语法  (选索引/join  (校验权限后 │
│   认证/      8.0整体移除)         分析,生成   顺序/生成     调用引擎 │
│   权限快照)                        语法树)    执行计划)    接口取数) │
├───────────────────────────────────────────────────────────┤
│  Server 层内置功能: 内置函数/跨引擎 binlog/解析器/优化器        │
├───────────────────────────────────────────────────────────┤
│                    存储引擎接口 (Handler API)                │
├──────────────────────┬────────────────────────────────────┤
│       InnoDB         │             MyISAM / Memory / ...   │
│  (事务/行锁/MVCC/     │   (表锁/无事务, 基本只做历史兼容)        │
│   redo+undo log)     │                                    │
└──────────────────────┴────────────────────────────────────┘
        引擎层: 数据与索引的真实存储, 决定「怎么存、怎么锁、怎么恢复」
```

### 2.2 Server 层与引擎层职责划分

| 层 | 组件 | 职责 | 说明 |
| --- | --- | --- | --- |
| Server 层 | 连接器 | 建立 TCP 连接、challenge-response 认证、读取权限快照 | 权限在连接时确定，改权限对已建连接不生效（需重连） |
| Server 层 | 查询缓存 | 以 SQL 文本为 key 缓存结果集 | 表有任何更新即整表缓存失效，命中率低，8.0 已删除（5.6 起默认关闭） |
| Server 层 | 分析器 | 词法分析识别关键字、语法分析构建语法树 | `Unknown column` 在此阶段报错 |
| Server 层 | 优化器 | 选择索引、决定 join 顺序与驱动表、估算成本 | 选错索引时可 force index 干预 |
| Server 层 | 执行器 | 权限校验后调用引擎接口逐行取数/写入 | rows 统计发生在执行器 |
| Server 层 | binlog | 归档日志、复制 | 所有引擎共用，属 Server 层 |
| 引擎层 | InnoDB | 数据/索引存储、事务、MVCC、行锁、redo/undo log | 以下「底层实现」均指 InnoDB |

### 2.3 一条 SELECT 的执行流程

```sql
SELECT * FROM user WHERE id = 42;
```

1. **连接器**：TCP 三次握手 + 认证 + 读权限快照（长连接可跳过）。
2. **分析器**：词法分析识别 `SELECT`/表名/列名，语法分析建语法树；列不存在在此报错。
3. **优化器**：`id` 是主键，选择走 `PRIMARY` 聚簇索引（对比全表扫描成本）。
4. **执行器**：校验对该表的 SELECT 权限，调用引擎接口「取 id=42 这一行」。
5. **InnoDB**：先查 Buffer Pool，未命中则从磁盘 .ibd 文件读数据页，返回整行给执行器，最终回给客户端。

### 2.4 一条 UPDATE 的执行流程（含日志，详细见第 10 章）

```sql
UPDATE user SET age = 30 WHERE id = 42;
```

前四步同 SELECT；执行器调用引擎接口后，InnoDB 依次：读数据页到 Buffer Pool → **写 undo log**（旧值，用于回滚和 MVCC）→ 在内存中修改该行（成为脏页）→ **写 redo log buffer**（prepare 状态）→ 执行器生成 **binlog cache** 并落盘 → InnoDB 将 redo log 置为 commit 状态（两阶段提交）→ 返回客户端成功。脏页由后台线程择机刷盘。**update 语句是「当前读」**，走锁 + 最新数据，不走 MVCC 快照。

---

## 3. 存储引擎

### 3.1 InnoDB vs MyISAM 对比

| 维度 | InnoDB | MyISAM |
| --- | --- | --- |
| 事务 | 支持 ACID | 不支持 |
| 锁粒度 | 行锁（另有表锁/意向锁/MDL） | 只有表锁 |
| 外键 | 支持 | 不支持 |
| 索引结构 | **聚簇索引**：B+ 树叶子节点存整行数据 | 非聚簇：叶子节点存数据文件的地址偏移 |
| 崩溃恢复 | redo log 自动崩溃恢复，安全 | 崩溃后表易损坏，需 myisamchk 修复 |
| COUNT(*)（无 WHERE） | 需扫描（因 MVCC 下不同事务看到的行数不同，无法存全局计数） | 元数据中存了总行数，O(1) |
| 全文索引 | 5.6 起支持 | 支持（老优势已消失） |
| 压缩 | 页压缩（5.7+） | 只读压缩表 |
| 适用场景 | OLTP 默认选择：交易、订单、账户 | 只读、无事务的小场景，基本淘汰 |

### 3.2 为什么生产一律 InnoDB

事务保证资金类操作原子性；行锁支撑高并发写入（MyISAM 写时会锁整表）；崩溃后靠 redo log 自动恢复，宕机不丢已提交数据；基于 binlog(ROW) 的主从复制以事务为单位，一致性有保障。除非有明确的历史包袱，新表一律 `ENGINE=InnoDB`。

---

## 4. 数据类型与表设计

### 4.1 常用类型选择

| 类型 | 存储/范围 | 说明 | 典型用法 |
| --- | --- | --- | --- |
| TINYINT | 1 字节，UNSIGNED 0~255 | 状态/枚举字段用 TINYINT 不用 INT，省空间 | `status TINYINT UNSIGNED` |
| INT | 4 字节，约 ±21 亿 | 通用整数 | 计数、外键 |
| BIGINT | 8 字节，约 ±9.2×10^18 | 主键 ID；也可存毫秒时间戳 | `id BIGINT UNSIGNED` |
| DECIMAL(M,D) | 变长精确十进制 | **金额禁用 FLOAT/DOUBLE**：二进制浮点无法精确表示 0.1，累计误差不可接受 | `price DECIMAL(10,2)`；也可 BIGINT 存「分」 |
| CHAR(N) | 定长 N 字符 | 插入的尾部空格在取出时被移除；适合等长短字段 | `country CHAR(2)`、`md5 CHAR(32)` |
| VARCHAR(N) | 变长 + 1~2 字节长度前缀 | N 是**字符数**而非字节数；utf8mb4 下受行 65535 字节限制 | `name VARCHAR(64)` |
| TEXT | 最大 64KB（字节） | 大文本，不能设默认值，尽量不与热点字段同表 | `content TEXT` |
| BLOB | 最大 64KB 二进制 | 图片等大对象**别存数据库**，放对象存储存 URL | - |
| DATETIME | 8 字节，1000~9999 年 | 无时区语义，原样存取；5.6.4+ 可带小数秒 | `created_at DATETIME` |
| TIMESTAMP | 4 字节，上限 **2038-01-19 03:14:07 UTC** | 存 UTC，读写按 time_zone 自动转换，**有 2038 问题** | 时区相关场景 |
| JSON | 5.7 引入 | 二进制存储，8.0 支持部分更新；`->>` 提取 | 半结构化扩展字段 |

CHAR vs VARCHAR 细节：比较语义取决于排序规则是否 PAD SPACE——5.7 常用 utf8mb4_general_ci 是 PAD SPACE（`'a' = 'a '` 为真）；8.0 默认 utf8mb4_0900_ai_ci 是 **NO PAD**（不相等）。两版该领域为不同，别写依赖尾部空格比较的业务。

### 4.2 建表规范清单

- 所有字段 **NOT NULL 并给默认值**：NULL 使索引统计和比较复杂，`count(列)` 不统计 NULL 行。
- 数值确定非负就加 **UNSIGNED**，容量翻倍。
- **每表显式主键**（InnoDB 不设主键会选第一个非空唯一索引，都没有则生成隐藏的 6 字节 ROW_ID，且该 ROW_ID 全局共享、用完会复用，属于隐患）。
- 每个字段、每张表写 **COMMENT**。
- 库名表名字段名统一小写下划线；禁用保留字。

```sql
-- 规范建表示例（MySQL 8.0，utf8mb4 为 8.0 默认字符集，显式写出更稳妥）
CREATE TABLE `order_info` (
  `id`          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  `order_no`    VARCHAR(32)     NOT NULL DEFAULT '' COMMENT '业务订单号',
  `amount`      DECIMAL(10,2)   NOT NULL DEFAULT '0.00' COMMENT '金额,精确类型',
  `status`      TINYINT UNSIGNED NOT NULL DEFAULT '0' COMMENT '0待支付 1已支付 2已关闭',
  `created_at`  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_order_no` (`order_no`),
  KEY `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='订单表';
```

### 4.3 隐式类型转换导致的索引失效（典型坑）

```sql
-- phone 是 VARCHAR(20), 建了索引
SELECT * FROM user WHERE phone = 13800001111;   -- 错: MySQL 把每行的 phone 转成数字比较, 索引失效, 全表扫描
SELECT * FROM user WHERE phone = '13800001111'; -- 对: 常量类型与列一致, 走索引

-- 反向情况: id 是 BIGINT
SELECT * FROM user WHERE id = '42';             -- 常量 '42' 被转成数字, 索引不失效
```

规则：字符串与数字比较时，MySQL 把**字符串一侧转为数字**。列被转换，B+ 树就废了。详见 7.5 索引失效场景表。

---

## 5. SQL 进阶

### 5.1 JOIN 四类型对比

| 类型 | 语义 | MySQL 支持 |
| --- | --- | --- |
| INNER JOIN | 两表交集 | 支持 |
| LEFT JOIN | 左表全保留，右表不匹配列置 NULL | 支持 |
| RIGHT JOIN | 右表全保留 | 支持 |
| FULL OUTER JOIN | 两表并集 | **不支持**，需用 LEFT JOIN UNION RIGHT JOIN 等价实现 |

```sql
-- MySQL 等价实现 FULL JOIN（UNION 自带去重，注意成本）
SELECT a.id, a.name, b.order_no FROM user a LEFT JOIN orders b ON a.id = b.user_id
UNION
SELECT a.id, a.name, b.order_no FROM user a RIGHT JOIN orders b ON a.id = b.user_id;
```

### 5.2 子查询 vs JOIN 性能讨论

| 写法 | 说明 |
| --- | --- |
| `IN (子查询)` | MySQL 5.6+ 引擎做了**半连接（semijoin）优化**：只关心「存在与否」，EXPLAIN 会看到 Semi-join/FirstMatch/Materialize 等策略，通常性能不错；5.5 及以前的老版本不优化，IN 子查询可能退化为相关子查询逐行执行——这是「in 子查询性能陷阱」的来源（见第 15 章） |
| `EXISTS (相关子查询)` | 语义同为半连接，优化器常与 IN 互相改写；老版本上相关 EXISTS 有时优于 IN |
| JOIN | 注意一对多导致的**数据放大**（行数变多）与需要去重（DISTINCT）的场景；等值 JOIN 驱动表选小表、被驱动表连接列必须有索引 |

经验：8.0 下 `IN (子查询)` 与等价 JOIN 多数场景计划相同；真正要警惕的是 JOIN 的数据放大和被驱动表连接列无索引（EXPLAIN 出现 Block Nested Loop/hash join）。

### 5.3 GROUP BY 与聚合

- 5.7+ 默认 sql_mode 含 **ONLY_FULL_GROUP_BY**：SELECT 的非聚合列必须出现在 GROUP BY 中，否则报错（5.7+ 可用 `ANY_VALUE()` 豁免）。
- GROUP BY 列有索引时可利用索引有序性，避免 `Using temporary`。
- `WHERE` 在分组前过滤（可用索引下推），`HAVING` 在分组后过滤聚合结果。

### 5.4 窗口函数（MySQL 8.0+，5.7 不支持）

| 函数 | 作用 | 示例 |
| --- | --- | --- |
| ROW_NUMBER() | 连续唯一行号 1,2,3 | `ROW_NUMBER() OVER (PARTITION BY dept ORDER BY salary DESC)` |
| RANK() | 并列同名次、跳号 1,1,3 | `RANK() OVER (ORDER BY score DESC)` |
| DENSE_RANK() | 并列同名次、不跳号 1,1,2 | `DENSE_RANK() OVER (ORDER BY score DESC)` |
| LAG()/LEAD() | 取上一行/下一行的值 | `LAG(salary, 1, 0) OVER (ORDER BY hire_date)`（算环比/同比利器） |

```sql
-- 经典题: 每个部门薪资 Top2（8.0 写法, 5.7 要用自关联或变量模拟）
SELECT * FROM (
  SELECT name, dept, salary,
         ROW_NUMBER() OVER (PARTITION BY dept ORDER BY salary DESC) AS rn
  FROM employee
) t WHERE rn <= 2;
```

### 5.5 CTE 与递归（MySQL 8.0+）

```sql
-- 递归 CTE: 查组织架构树上某人的所有下属
WITH RECURSIVE sub(id, name, depth) AS (
  SELECT id, name, 1 FROM employee WHERE id = 1          -- 锚点: 起始行
  UNION ALL
  SELECT e.id, e.name, s.depth + 1
  FROM employee e JOIN sub s ON e.manager_id = s.id      -- 递归: 找下属
)
SELECT * FROM sub;
```

### 5.6 分页深翻页优化【高频】

```sql
-- 为什么慢: LIMIT 1000000,10 要在索引上顺序扫描并「取完/回表丢弃」前 1000010 行里的前 100 万行
SELECT * FROM orders ORDER BY id LIMIT 1000000, 10;

-- 方案一: 游标/书签翻页（上一页最大 id 已知, 且排序键有序唯一时最优雅）
SELECT * FROM orders WHERE id > 1000000 ORDER BY id LIMIT 10;

-- 方案二: 延迟关联（子查询只扫覆盖索引拿到目标主键, 只回表 10 行）
SELECT o.* FROM orders o
INNER JOIN (SELECT id FROM orders ORDER BY id LIMIT 1000000, 10) t ON o.id = t.id;
```

---

## 6. EXPLAIN 与执行计划【高频】

### 6.1 EXPLAIN 输出字段详解

```sql
EXPLAIN SELECT * FROM orders WHERE user_id = 100 AND status = 1;
```

| 字段 | 含义 | 关注点 |
| --- | --- | --- |
| id | 执行序号 | id 越大越先执行；相同 id 为同一组（join） |
| select_type | SIMPLE / PRIMARY / SUBQUERY / DERIVED | DERIVED 表示派生表（from 子查询） |
| table | 当前步骤操作的表 | `<derivedN>` 指向 id=N 的派生表 |
| type | 访问类型（决定性指标） | 见 6.2 |
| possible_keys | 优化器可选的索引 | 只看没用的意义不大 |
| key | 实际使用的索引 | NULL 即全表扫描 |
| key_len | 使用索引的字节数 | 据此判断联合索引用上了几列 |
| ref | 与索引比较的对象 | const / 字段名 |
| rows | 估算扫描行数 | 越小越好（基于索引统计，非精确值） |
| filtered | 经 WHERE 过滤后剩余比例 | rows × filtered ≈ 结果行数 |
| Extra | 附加信息 | 见 6.3 |

### 6.2 type 级别：从好到差

| 级别 | 含义 | 典型 SQL |
| --- | --- | --- |
| system | 系统表且仅一行（const 特例） | 极少见 |
| const | 主键或唯一索引**等值**命中，最多一行 | `WHERE id = 1` |
| eq_ref | join 时被驱动表走主键/唯一索引 | `JOIN t2 ON t2.id = t1.id` |
| ref | 普通二级索引等值匹配 | `WHERE name = 'tom'` |
| range | 索引范围扫描 | `WHERE id > 10`、`BETWEEN`、`LIKE 'ab%'` |
| index | 扫整棵索引树（比全表好：索引文件小） | 覆盖索引做 `COUNT(*)`、`MIN()` |
| ALL | 全表扫描 | **必须优化** |

口诀：生产查询至少到 range 级别；eq_ref/const 是理想状态。达到 index 不一定差（配合覆盖索引的统计类查询是正常形态），ALL 在小表或无法建索引时也可接受，要结合 rows 判断。

### 6.3 Extra 高频值

| 值 | 含义 | 评价 |
| --- | --- | --- |
| Using index | **覆盖索引**，免回表 | 好 |
| Using index condition | **索引下推 ICP**（5.6+），在引擎层用索引列条件先过滤 | 好 |
| Using where | Server 层再过滤（WHERE 里有非索引条件） | 中性，常见 |
| Using filesort | 内存/磁盘额外排序 | 差：让 ORDER BY 列命中索引 |
| Using temporary | 建临时表 | 差：GROUP BY/DISTINCT 列无索引时常出现 |
| Using join buffer (Block Nested Loop) | 被驱动表连接列无索引 | 差：给连接列加索引；8.0.18+ 优化器可用 hash join 缓解 |

### 6.4 慢查询定位三步

| 步骤 | 操作 | 要点 |
| --- | --- | --- |
| 1. 开慢日志 | `SET GLOBAL slow_query_log = ON;`<br>`SET GLOBAL long_query_time = 1;`（秒，生产常设 0.5~1）<br>`log_queries_not_using_indexes = ON` 记录无索引 SQL | 输出到 slow log 文件，含执行时间、锁时间、扫描行数 |
| 2. EXPLAIN 分析 | `EXPLAIN` + 慢 SQL | 看 type / key / rows / Extra 四件套 |
| 3. 针对性优化 | 加/改索引、改写 SQL、覆盖索引、避免回表 | 改完回归 EXPLAIN 对比 |

辅助工具：`pt-query-digest` 聚合慢日志找 TOP N；`SHOW PROFILE`（8.0 已废弃，用 performance_schema）看各阶段耗时。

---

## 7. 索引原理【高频·最重要章节】

### 7.1 B+ 树结构（InnoDB 实现）

```text
                              ┌──────────────┐
                              │    根节点     │
                              │   [15 | 56]  │        ← 非叶子节点只存「键 + 子节点指针」
                              └──┬────────┬──┘        （不存数据行）
              ┌─────────────────┘        └─────────────────┐
              ▼                                            ▼
     ┌────────────────┐                          ┌────────────────┐
     │   中间节点       │         ......           │   中间节点       │
     │    [7 | 12]    │                          │   [70 | 88]    │
     └──┬─────────┬───┘                          └──┬─────────┬───┘
        ▼         ▼                                 ▼         ▼
 ┌───────────┐┌───────────┐   ┌───────────┐   ┌───────────┐┌───────────┐
 │叶子: ≤7   ││叶子: 8~12 │.. │叶子: 15~30 │.. │叶子: 56~70 ││叶子: 71~88 │
 └───────────┘└───────────┘   └───────────┘   └───────────┘└───────────┘
   ▲◀──▶▲◀──────────────── 双向链表 ──────────────▶▲◀──▶▲
   叶子节点: 「键 + 完整数据行」(聚簇索引) 或 「键 + 主键值」(二级索引)
```

- 单页 16KB：非叶子节点只存键，一个页能放几百个键，扇出极大。
- 3~4 层 B+ 树即可支撑千万级数据：根节点常驻内存，一次主键查询通常只需 1~3 次磁盘 IO。
- 叶子层双向链表：范围查询 `BETWEEN`、`ORDER BY id` 沿链表顺序读即可。

### 7.2 为什么选 B+ 树（对比表）

| 对比对象 | B+ 树的优势 | 结论 |
| --- | --- | --- |
| B 树 | B 树非叶子节点也存数据 → 单页放的键少、扇出小、树更高；B+ 树数据全在叶子且叶子成链，范围查询不用中序回溯 | B+ 树更适合磁盘 |
| 哈希表 | 哈希等值查询 O(1) 但**不支持范围查询和排序**，且哈希冲突与 rehash 代价；B+ 树范围、排序、最左前缀通吃 | Memory 引擎用哈希，OLTP 主力用 B+ 树（InnoDB 内部有自适应哈希索引 AHI 做热点页加速） |
| 红黑树/跳表 | 二叉树树高 log2N 太高：1000 万行约 23 层，即 23 次磁盘 IO；B+ 树靠「矮胖」把 IO 压到 3~4 次 | 数据在磁盘，核心是**减少磁盘 IO 次数** |

### 7.3 聚簇索引 vs 二级索引与回表

```sql
    二级索引 idx_name(name)                聚簇索引 PRIMARY(id)
    ┌──────────────────┐                 ┌──────────────────────┐
    │  非叶子: name 键   │                 │  非叶子: id 键         │
    └────────┬─────────┘                 └──────────┬───────────┘
             ▼                                      ▼
    ┌──────────────────┐   ① 命中 name='tom'        ┌──────────────────────┐
    │ 叶子:             │      取出主键 id=42         │ 叶子:                 │
    │  name │ id(主键)   │ ──② 回表:拿 id 查────────▶ │  id=42 │ 完整行数据    │
    │  tom  │ 42        │     聚簇索引                │  name=tom age=...     │
    └──────────────────┘                            └──────────────────────┘

    SELECT * FROM user WHERE name = 'tom';
    路径: idx_name 定位 → 拿到 id=42 → 回聚簇索引取整行(回表) → 返回
```

| 概念 | 说明 | 面试表述 |
| --- | --- | --- |
| 聚簇索引 | InnoDB 主键索引，叶子存整行；每表只有一个；无主键则选非空唯一索引，再无则隐藏 ROW_ID | 「索引即数据，数据即索引」 |
| 二级索引（辅助索引） | 叶子存「索引列 + 主键值」，每表可多个 | 查询需要的列不在二级索引里就要回表 |
| 回表 | 用二级索引拿到主键，再去聚簇索引取整行，多一次树查找 | 回表次数多时优化器可能放弃索引直接全表 |
| 覆盖索引 | SELECT 的列全部包含在索引中，免回表，Extra=Using index | `SELECT id, name FROM user WHERE name='tom'` 命中 idx_name 即覆盖 |
| 索引下推 ICP（5.6+） | 联合索引中「未被用于定位的列」的条件**下推到引擎层**在索引里先过滤，减少回表次数，Extra=Using index condition | `idx(a,b)` 查 `a>1 AND b=2`：a 定位后，b 的判断在索引层完成，不满足就不回表 |

```sql
-- ICP 示例
SELECT * FROM t WHERE a > 100 AND b = 2;   -- idx(a,b): 无 ICP 时先回表再在 Server 层判 b;
                                             -- 有 ICP 时在索引上先判 b=2, 不满足直接跳过, 大幅减少回表
```

### 7.4 最左前缀原则（联合索引 idx(a,b,c)）

| WHERE / ORDER BY 条件 | 能否走索引 | 说明 |
| --- | --- | --- |
| `a = 1` | 能（ref） | 命中最左列 |
| `a = 1 AND b = 2` | 能（ref） | 连续两列 |
| `a = 1 AND b = 2 AND c = 3` | 能（ref） | 全列命中，key_len 最大 |
| `b = 2` | 不能 | 缺最左列 a，只能全表（除非为 b 单独建索引） |
| `b = 2 AND c = 3` | 不能 | 同上 |
| `a = 1 AND c = 3` | 部分（只走 a） | c 可参与 ICP/回表前过滤，但无法用于索引定位（中间断了 b） |
| `a > 1 AND b = 2` | 部分（range 走 a） | a 用了**范围**后，b 无法再用于索引定位（范围列之后的列失效） |
| `a = 1 AND b > 2 AND c = 3` | 部分（走 a、b） | b 是范围，c 无法定位 |
| `a = 1 ORDER BY b` | 能且免 filesort | 索引本身有序（a 定、b 有序） |
| `a LIKE 'ab%'` | 能（range） | 前缀模糊可走；`'%ab'` 不能 |

设计推论：把**最常单独出现的等值过滤列放最左**；范围列尽量放最后；`order by` 的列紧跟等值列可免 filesort。

### 7.5 索引失效场景表

| 场景 | 示例 | 原因/对策 |
| --- | --- | --- |
| 对索引列做函数/运算 | `WHERE YEAR(created_at)=2024`、`WHERE id+1=10` | 优化器无法用树定位；改写为范围条件，或 8.0.13+ 建函数索引 `INDEX((YEAR(created_at)))` |
| 隐式类型转换 | `WHERE phone = 13800001111`（phone 为 VARCHAR） | 列被转数字，全表；常量加引号 |
| 前导模糊 | `LIKE '%abc'` | B+ 树按前缀有序；可冗余一列反转串或用函数索引 |
| OR 连接无索引列 | `WHERE a=1 OR d=2`（d 无索引） | 必须扫 d；只有两侧都有索引才可能 index_merge |
| 不等号/NOT IN/NOT EXISTS | `WHERE a != 1` | 视选择性：优化器估算回表成本高于全表时弃用索引 |
| 非最左前缀 | `WHERE b=2`（idx(a,b)） | 联合索引最左前缀原则 |
| JOIN 两侧字符集/排序规则不一致 | utf8mb4 列 join latin1 列 | 发生隐式转换，索引失效；统一字符集 |
| 优化器成本估算 | `SELECT *` 大范围 | 回表成本 > 全表扫描时合理弃用，可 force index 验证 |

### 7.6 索引设计准则速记

区分度高（`count(distinct col)/count(*)` 接近 1）的列建索引；单表索引不超过 5~6 个；索引列 NOT NULL；自增主键避免页分裂；长字符串用前缀索引 `INDEX(name(20))`；8.0 可用隐藏索引（`INVISIBLE`）做删除前的灰度验证。设计清单详见 14.2。

---

## 8. 事务与 MVCC【高频】

### 8.1 ACID 及 InnoDB 实现手段

| 特性 | 含义 | InnoDB 实现手段 |
| --- | --- | --- |
| A 原子性 | 事务内操作全成或全不成 | **undo log**：回滚时反向补偿 |
| C 一致性 | 事务前后数据满足所有约束 | 由 A、I、D 共同保证（外键约束 + 应用逻辑） |
| I 隔离性 | 并发事务互不干扰 | **锁 + MVCC** |
| D 持久性 | 提交后永久生效，宕机不丢 | **redo log**（WAL，先写日志后刷数据页） |

### 8.2 隔离级别与并发问题对照

| 隔离级别 | 脏读 | 不可重复读 | 幻读 | InnoDB 关键实现 |
| --- | --- | --- | --- | --- |
| READ UNCOMMITTED | 可能 | 可能 | 可能 | 基本不用 |
| READ COMMITTED（RC） | 避免 | 可能 | 可能 | **每次快照读都生成新的 ReadView** |
| REPEATABLE READ（RR，**默认**） | 避免 | 避免 | 快照读靠 MVCC 不出现；**当前读靠 next-key lock 阻止新行插入** | **只在第一次快照读生成 ReadView 并复用** |
| SERIALIZABLE | 避免 | 避免 | 避免 | 读也加共享锁，并发退化为串行 |

RR 是否解决幻读（准确表述）：普通 SELECT 是**快照读**，读的是事务开始时的版本视图，其他事务新插入的行对它不可见，所以看不到「幻影行」；`SELECT ... FOR UPDATE / UPDATE / DELETE` 是**当前读**，通过 next-key lock（记录锁+间隙锁）锁住已有记录和间隙，阻止其他事务插入，从而在当前读下防止幻读。但两种读混用时（先快照读、再当前读）仍可能看到不一致，所以严格说 **RR 并没有彻底根除幻读，只是在两种读路径上分别规避**。

### 8.3 三种并发问题的时序

```sql
脏读（读到未提交的数据）:
  T1: BEGIN; UPDATE t SET a=10 WHERE id=1;      -- 未提交
  T2: BEGIN; SELECT a FROM t WHERE id=1;          -- 读到 10
  T1: ROLLBACK;                                   -- a 回到 1, T2 读到了"从未存在"的值

不可重复读（同一行两次读不同）:
  T1: BEGIN; SELECT a WHERE id=1;                 -- a=1
  T2: UPDATE t SET a=2 WHERE id=1; COMMIT;        -- 已提交
  T1: SELECT a WHERE id=1;                        -- a=2, 同一事务内两次结果不同

幻读（同条件两次查询行数不同）:
  T1: BEGIN; SELECT * WHERE age>10;               -- 2 行
  T2: INSERT INTO t VALUES(..., age=20); COMMIT;
  T1: SELECT * WHERE age>10;                      -- 3 行, 多出幻影行
```

### 8.4 MVCC 原理详解（InnoDB 实现）

三要素：**隐藏字段 + undo log 版本链 + ReadView**。

每行记录有两个隐藏列：`trx_id`（最后一次修改它的事务 id）、`roll_pointer`（指向 undo log 里的上一版本）。

```text
版本链（undo log）：
┌────────────────────────────────────┐
│ 当前行: id=1 │ name='C' │ trx_id=103 │ ──roll_pointer──┐
└────────────────────────────────────┘                  ▼
┌────────────────────────────────────┐
│ undo:   id=1 │ name='B' │ trx_id=102 │ ──roll_pointer──┐
└────────────────────────────────────┘                  ▼
┌────────────────────────────────────┐
│ undo:   id=1 │ name='A' │ trx_id=100 │ ──roll_pointer──→ NULL（链尾）
└────────────────────────────────────┘
```

ReadView 四要素：

| 要素 | 含义 |
| --- | --- |
| m_ids | 生成 ReadView 时**仍活跃（未提交）**的事务 id 集合 |
| min_trx_id | m_ids 中最小的事务 id |
| max_trx_id | 生成 ReadView 时系统**下一个**将分配的事务 id（不是 m_ids 最大值） |
| creator_trx_id | 当前事务自己的 id |

可见性判断（对版本链上某一版本的 trx_id）：

1. `trx_id == creator_trx_id`：自己改的 → **可见**。
2. `trx_id < min_trx_id`：生成 ReadView 前已提交 → **可见**。
3. `trx_id >= max_trx_id`：生成 ReadView 之后才开启的事务 → **不可见**。
4. `min_trx_id <= trx_id < max_trx_id`：在 m_ids 里说明当时还没提交 → **不可见**；不在 m_ids 里说明已提交 → **可见**。
5. 不可见就沿 roll_pointer 找上一版本，重复判断，直到可见或到链尾。

### 8.5 RC 与 RR 的本质区别【高频】

| 隔离级别 | ReadView 生成时机 | 效果 |
| --- | --- | --- |
| READ COMMITTED | **每次快照读都重新生成** ReadView | 能看到其他事务「最新提交」的数据 → 不可重复读 |
| REPEATABLE READ | **只在事务第一次快照读时生成**，之后复用 | 整个事务期间看到的数据版本一致 → 可重复读 |

一句话：**RC 与 RR 在 MVCC 上只差「ReadView 的复用策略」**。互联网公司不少核心交易库会用 RC（无间隙锁，锁冲突小，配合乐观业务重试），默认仍是 RR。

---

## 9. 锁体系（InnoDB 实现）

### 9.1 锁粒度分类

| 锁 | 粒度 | 命令/触发场景 | 说明 |
| --- | --- | --- | --- |
| 全局锁 | 整个实例 | `FLUSH TABLES WITH READ LOCK` | 全库只读，逻辑备份求一致性；InnoDB 用 `mysqldump --single-transaction`（一致性快照）替代，不锁表 |
| 表锁 | 表 | `LOCK TABLES t READ/WRITE` | 基本不用 |
| 元数据锁 MDL | 表（自动） | 查询/DML 自动加 MDL **读锁**，DDL 需要 MDL **写锁** | 经典事故：长事务持有 MDL 读锁 → DDL 拿不到写锁 → 后续所有请求（含 SELECT）排队，全表「卡死」；改表前先查 `information_schema.innodb_trx` 杀长事务 |
| 意向锁 IS/IX | 表（自动） | 行锁前自动加 | 让「表锁」不必逐行检查是否有人持有行锁 |
| 行锁 | 行（索引记录） | 自动/显式 | 见 9.2 |

### 9.2 行锁三种类型

| 类型 | 锁定对象 | 防什么 |
| --- | --- | --- |
| Record Lock（记录锁） | 单条索引记录 | 并发修改同一行 |
| Gap Lock（间隙锁） | 两条索引记录之间的**间隙**（不含记录本身） | 防止其他事务往间隙**插入**新行（幻读来源） |
| Next-Key Lock | 记录 + 前面的间隙（左开右闭区间） | RR 级别当前读下**同时**防修改与插入，是 RR 防幻读的主力 |

补充规则：唯一索引等值命中记录时 next-key lock 退化为纯记录锁；间隙锁只在 RR（及以上）生效，RC 下基本不用间隙锁（仅唯一键/外键检查例外），这也是 RC 锁冲突更少的原因；间隙锁之间不互斥（都是「不许插入」不冲突）。

### 9.3 加锁规则要点

- **行锁加在索引上**。`UPDATE t SET x=1 WHERE 非索引列=...` 走全表扫描，RR 下会对扫描过的所有记录和间隙加 next-key lock，等价于**锁全表**——「非索引列更新锁全表」的真相。
- 显式当前读：`SELECT ... FOR UPDATE`（排他锁）、`SELECT ... FOR SHARE`（共享锁；8.0 引入的写法，旧写法 `LOCK IN SHARE MODE` 仍兼容）。
- RR 下普通 SELECT 不加锁（MVCC 快照读）；`SERIALIZABLE` 下普通 SELECT 自动转为共享锁当前读。

### 9.4 死锁案例与排查

```sql
事务 A                                      事务 B
BEGIN;                                      BEGIN;
UPDATE t SET x=1 WHERE id=1;                -- 持有 id=1 的 X 锁
                                            UPDATE t SET x=2 WHERE id=2;   -- 持有 id=2 的 X 锁
UPDATE t SET x=3 WHERE id=2;                -- 等待 B 释放 id=2   ←─┐
                                            UPDATE t SET x=4 WHERE id=1;   -- 等待 A 释放 id=1
                                                               互相等待 → 死锁 ─┘
  InnoDB 死锁检测(默认开启)立即发现, 回滚「undo 量较小」的一方, 报错 1213 (ER_LOCK_DEADLOCK)
```

| 手段 | 命令/做法 |
| --- | --- |
| 查看最近死锁现场 | `SHOW ENGINE INNODB STATUS;` → `LATEST DETECTED DEADLOCK` 段，含两事务持有的锁与 SQL |
| 查当前事务与锁等待 | `SELECT * FROM information_schema.innodb_trx;`（长事务）<br>8.0：`performance_schema.data_locks / data_lock_waits`（5.7 是 `information_schema.innodb_locks/innodb_lock_waits`） |
| 预防 | 事务内按**相同顺序**访问多行；小事务、避免在事务里做 RPC/耗时操作；必要时降低隔离级别为 RC；`innodb_lock_wait_timeout`（默认 50 秒）控制等锁超时 |

---

## 10. 日志体系【高频】

### 10.1 三大日志职责

| 日志 | 所属层 | 核心职责 |
| --- | --- | --- |
| redo log | InnoDB 引擎层 | **崩溃恢复 + 持久性**（WAL：先写顺序日志，再异步刷随机数据页） |
| undo log | InnoDB 引擎层 | **回滚（原子性）+ MVCC 版本链**（存旧值，逻辑日志） |
| binlog | Server 层（所有引擎） | **归档、主从复制、按时间点恢复** |

### 10.2 redo log

- WAL（Write-Ahead Logging）思想：修改数据页前先把「页做了什么改动」顺序写入 redo log，宕机后重放即可恢复，把随机写转化为顺序写。
- InnoDB 特有，**固定大小、循环写**（写满则从头覆盖，此时必须推进 checkpoint 刷脏页）。
- 刷盘时机由 `innodb_flush_log_at_trx_commit` 决定：

| 取值 | 行为 | 可靠性/性能 |
| --- | --- | --- |
| 0 | 每秒由后台线程写并刷盘 | 宕机丢最近 1 秒事务，最快 |
| **1（默认）** | 每次提交都写并 fsync 落盘 | 不丢，最慢（「双 1」之一） |
| 2 | 每次提交写到 OS page cache，每秒 fsync | MySQL 进程崩溃不丢，**操作系统**崩溃丢 1 秒 |

### 10.3 binlog

- Server 层日志，追加写（写满切下一个文件，不覆盖），可设置过期清理。
- 三种格式：

| 格式 | 记录内容 | 优点 | 缺点 |
| --- | --- | --- | --- |
| STATEMENT | SQL 原文 | 量小 | `NOW()`/`UUID()`/`LIMIT` 无确定性 → 主从不一致 |
| **ROW（8.0 默认）** | 行镜像（修改前/后整行或变更列） | 主从一致性最好，复制安全 | 数据量大（可 `binlog_row_image=MINIMAL` 缓解） |
| MIXED | 有风险语句自动切 ROW | 折中 | 判断复杂，不推荐 |

- 生产推荐 ROW：复制语义确定，也是增量恢复工具与 CDC（如 canal）的基础。

### 10.4 redo log vs binlog 对比

| 维度 | redo log | binlog |
| --- | --- | --- |
| 层级 | InnoDB 引擎层 | Server 层 |
| 内容 | 物理日志：某页某处做了什么修改 | 逻辑日志：SQL 或行变更 |
| 写入方式 | 固定大小，**循环写会覆盖** | 追加写，写满换文件 |
| 用途 | 崩溃恢复（保证持久性） | 归档、主从复制、时间点恢复 |
| 事务 | 两阶段提交的 prepare/commit 两态 | 通过内部 XA 的 XID 与 redo 关联 |

### 10.5 两阶段提交（redo log 与 binlog 的一致性）

为什么需要：两个独立日志，若先写 redo 后宕机没写 binlog → 主库恢复出该事务、从库没有 → 主从不一致；反之先 binlog 后宕机 → 从库多一个事务。所以用内部 XA 协调：

```text
UPDATE 提交流程（两阶段提交）：
  ① redo log 写入, 状态 = prepare        （事务 id 即 XID, 记入 redo）
  ② 写 binlog 并落盘                     （同一 XID 写入 binlog）
  ③ redo log 状态 = commit                （本步很快, 崩溃恢复可补）

崩溃恢复判定（重启时扫描 redo）：
  redo=prepare 且 binlog 中该 XID 完整   → 提交（重放）
  redo=prepare 且 binlog 缺失/不完整      → 回滚（靠 undo log）
  redo=commit                            → 无需处理
```

### 10.6 一条 UPDATE 的完整链路（串联图）

```sql
UPDATE t SET a=2 WHERE id=1;
   │
   ▼
连接器(认证/权限快照) → 分析器(词法语法, 列是否存在) → 优化器(选 PRIMARY 索引)
   │
   ▼
执行器 → 调用 InnoDB 接口
   │
   ▼  InnoDB:
   ├─① 读 id=1 所在数据页进 Buffer Pool（命中则跳过磁盘读）
   ├─② 写 undo log（记录旧值 a=1：回滚 + MVCC 版本链）
   ├─③ 在 Buffer Pool 中修改该行 → 该页成为「脏页」
   ├─④ 写 redo log buffer（prepare）
   ├─⑤ 执行器写 binlog cache，提交时 binlog 落盘
   ├─⑥ redo log 置 commit → 返回客户端「成功」
   └─⑦ 后台线程择机把脏页刷回 .ibd（触发：redo 快写满/内存不足/空闲时刷盘）
```

---

## 11. 高可用与扩展

### 11.1 主从复制原理【高频】

```text
      主库 Master                              从库 Slave
┌──────────────────────┐               ┌───────────────────────────┐
│ 客户端写入             │               │                           │
│   ▼                   │               │  ┌─────────────────────┐  │
│ InnoDB(redo/数据页)    │               │  │ IO 线程              │  │
│   ▼                   │    binlog     │  │ (CHANGE REPLICATION  │  │
│ binlog ──dump 线程─────┼──(TCP 推送)──▶│  │  SOURCE TO 时创建)    │  │
│        (主库为每个从库  │               │  └──────────┬──────────┘  │
│         起一个 dump)   │               │             ▼             │
│                       │               │     relay log(中继日志)     │
│                       │               │             ▼             │
│                       │               │  ┌─────────────────────┐  │
│                       │               │  │ SQL 线程: 重放 relay  │  │
│                       │               │  │ log 中的事务, 写从库   │  │
│                       │               │  └─────────────────────┘  │
└──────────────────────┘               └───────────────────────────┘
```

三线程：主库 **dump 线程**推送 binlog；从库 **IO 线程**接收并写入 relay log；从库 **SQL 线程**重放。5.7+/8.0 用基于 LOGICAL_CLOCK（组提交）/WRITESET 的**并行复制**提升 SQL 线程重放速度；推荐用 GTID 定位事务位点。

### 11.2 复制模式

| 模式 | 机制 | 一致性 | 代价 |
| --- | --- | --- | --- |
| 异步（默认） | 主库提交即返回，不等从库 | 主库宕机可能丢最新事务 | 性能最好 |
| 半同步 | 至少 1 个从库 ACK 收到 binlog 才向客户端返回 | 明显降低丢数据概率 | 提交延迟增加；从库超时会退化为异步 |
| 组复制 MGR | 基于 Paxos 变体多数派共识 | 多数派存活即强一致，支持自动选主 | 运维复杂，节点数有限 |

### 11.3 主从延迟原因与应对

| 原因 | 应对 |
| --- | --- |
| 大事务（一条 delete 百万行） | 拆小批（每批几千行 + sleep） |
| 从库单线程重放（老版本） | 5.7 并行复制 / 8.0 WRITESET 并行 |
| 从库机器/磁盘差 | 硬件对齐，binlog 与数据分盘 |
| 从库上跑重查询（锁等待） | 读请求与重放争锁，隔离分析负载 |
| 「写后立读」读从库读不到 | 关键路径强制读主库；或按 GTID 等待追平（`WAIT_FOR_EXECUTED_GTID_SET`） |

### 11.4 读写分离与中间件

| 中间件 | 一句话定位 |
| --- | --- |
| MyCat | 老牌代理式分库分表中间件（独立部署，跨语言） |
| ShardingSphere | 生态最活跃：JDBC 客户端形态（Java）/Proxy 代理形态，分库分表 + 读写分离 |
| ProxySQL / MySQL Router | 专注读写分离与路由的代理 |

### 11.5 分库分表

```text
垂直分库：按业务域拆到不同实例
┌─────────┐  ┌─────────┐  ┌─────────┐
│ 订单库   │  │ 用户库   │  │ 商品库   │
└─────────┘  └─────────┘  └─────────┘

垂直分表：一张宽表按「冷热/长短」拆
┌─────────────────┐   ┌────────────────┐  ┌────────────────┐
│ 商品主表(短热字段) │   │ 商品详情(TEXT)   │  │ 商品统计(冷字段)  │
└─────────────────┘   └────────────────┘  └────────────────┘

水平分表：同构多表，按分片键路由
orders_0: id % 4 == 0      orders_1: id % 4 == 1
orders_2: id % 4 == 2      orders_3: id % 4 == 3
（水平分库 = 再把表散到多个实例，先垂直按业务分库，再水平扩容单业务）
```

什么时候才需要：**经验值**是单表约 2000 万行或 20GB（也有 500 万行的保守说法，取决于行宽、QPS 与硬件），B+ 树层数变高、缓冲池装不下热数据时性能开始劣化——**先做索引/SQL/架构优化，最后才分库分表**，它会把复杂度永久性地转嫁给业务。

| 分片带来的问题 | 说明 |
| --- | --- |
| 跨分片查询 | 非分片键条件要广播全部分片再聚合；冗余一份按另一键分片的表是常见解法 |
| 跨分片事务 | 分布式事务代价高，尽量用最终一致（消息表/TCC/SAGA） |
| 全局唯一 ID | 自增主键失效；**雪花算法**：64 位 = 1 符号 + 41 位毫秒时间戳（约 69 年）+ 10 位机器（1024 节点）+ 12 位序列（每毫秒 4096 个），趋势递增利于聚簇索引顺序写入 |
| 扩容数据迁移 | 一致性哈希/翻倍扩容 + 双写迁移 |

---

## 12. 性能优化实践清单

### 12.1 连接与内存参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| max_connections | 151 | 最大并发连接；C++ 服务用连接池后每实例持有几十条即可 |
| wait_timeout | 28800（8 小时） | 非交互空闲连接超时，长连接闲置被服务端踢掉会报 `MySQL server has gone away` |
| interactive_timeout | 28800 | 交互式客户端（mysql 命令行）的空闲超时 |
| innodb_buffer_pool_size | 128MB | **最影响性能的参数**，生产设物理内存 50%~70% |
| innodb_flush_log_at_trx_commit / sync_binlog | 1 / 1 | 「双 1」最安全；非核心业务可放宽换性能 |

### 12.2 批量插入优化

| 手段 | 说明 |
| --- | --- |
| 多值 INSERT | `INSERT INTO t VALUES(...),(...),(...);` 一条语句数百行，摊薄网络与语句解析开销 |
| 关闭自动提交 | 批量导入前 `SET autocommit=0;`（或显式 BEGIN/COMMIT 包整批），避免每行一次事务刷盘 |
| LOAD DATA INFILE | 大批量导 CSV 最快路径，绕过 SQL 层逐行解析 |
| 延后建二级索引 | 先删掉二级索引，导完数据再重建，比边插边维护索引快得多 |

### 12.3 大表 DDL 的坑

| 方式 | 说明 |
| --- | --- |
| 直接 ALTER | 8.0 多数操作支持 `ALGORITHM=INSTANT`（如 8.0.12+ 加列，秒级）或 INPLACE（在线执行，期间允许并发 DML，仅首尾短暂加锁）；改列类型等仍需重建全表 COPY，期间锁写 |
| gh-ost | GitHub 出品：建影子表 + 模拟从库消费 binlog 回放增量 + 原子 rename 切换，可随时暂停 |
| pt-online-schema-change | Percona Toolkit：建影子表 + 触发器同步增量 + rename；依赖触发器，对写入有一定放大 |

### 12.4 连接池为什么必要（C++ 视角）

短连接每次请求要付出：TCP 三次握手 + MySQL challenge-response 认证往返 + 服务端为每条连接创建处理线程 + TLS 握手（如启用），高 QPS 下握手开销与 `max_connections` 抖动会拖垮服务。做法：进程内维护 N 条长连接（复用即省去握手与建线程），后台心跳（`SELECT 1`）防 `wait_timeout` 踢连接，配合熔断防池耗尽。对应《../03-网络编程/02-IO多路复用与Reactor模型.md》的 epoll + 线程池模型：连接池本质是「到 MySQL 的长连接复用层」。C++ 注意：libmysqlclient 每线程需 `mysql_thread_init()`；每条连接一个独立 `MYSQL*` 句柄不可跨线程同时使用；可自研或评估 mysql-connector-cpp / 第三方池。

---

## 13. 常用运维命令速查表

| 场景 | 命令 | 说明 |
| --- | --- | --- |
| 连接 | `mysql -h127.0.0.1 -uroot -p -P3306 dbname` | 避免把密码直接拼在 -p 后（ps 可见），交互输入更安全 |
| 库表 | `SHOW DATABASES; USE db; SHOW TABLES; DESC t; SHOW CREATE TABLE t;` | DESC 看结构，SHOW CREATE 看完整 DDL 与索引 |
| 库表 CRUD | `CREATE/DROP DATABASE db;` `CREATE/ALTER/DROP TABLE` | 8.0 DROP TABLE 是原子 DDL |
| 用户与权限 | `CREATE USER 'app'@'10.0.%' IDENTIFIED BY '...';`<br>`GRANT SELECT,INSERT,UPDATE ON shop.* TO 'app'@'10.0.%';`<br>`SHOW GRANTS FOR 'app'@'10.0.%'; REVOKE ...;` | 8.0 必须先建用户再授权（GRANT 不再隐式建用户）；GRANT 后无需 FLUSH PRIVILEGES |
| 备份 | `mysqldump --single-transaction --master-data=2 --routines --triggers -B shop > shop.sql` | `--single-transaction`：InnoDB 一致性快照不锁表；`--master-data=2`：记录 binlog 位点（注释形式）；恢复：`mysql < shop.sql` |
| 导入 | `mysql -uroot -p shop < shop.sql` / `LOAD DATA INFILE` | LOAD DATA 是大批量导入最快路径（见 12.2） |
| 状态 | `SHOW STATUS LIKE 'Threads%';` `SHOW GLOBAL STATUS LIKE 'Slow_queries';` | Threads_connected/running 看连接与活跃 |
| 会话与慢 SQL | `SHOW PROCESSLIST;`（全量 `SHOW FULL PROCESSLIST;`） | State 列看在等什么；`KILL <id>` 终止 |
| 引擎状态 | `SHOW ENGINE INNODB STATUS;` | 死锁现场、锁等待、缓冲池统计 |
| 参数 | `SHOW VARIABLES LIKE 'innodb_buffer_pool_size';` `SET GLOBAL ...` / 8.0 `SET PERSIST` | SET PERSIST 重启不丢 |

---

## 14. 快速参考卡片

### 14.1 这条 SQL 慢怎么排查（三步）

| 步骤 | 动作 |
| --- | --- |
| 1 | 开慢日志（`slow_query_log`、`long_query_time=1`）+ pt-query-digest 找 TOP 慢 SQL |
| 2 | `EXPLAIN` 看 type / key / rows / Extra：ALL 全表？key 为 NULL？Using filesort/temporary？ |
| 3 | 对症：缺索引→建（区分度+最左前缀）；回表多→覆盖索引；深分页→游标或延迟关联；写错类型→改写 SQL |

### 14.2 索引怎么设计（准则清单）

区分度高、频繁出现在 WHERE/JOIN/ORDER BY 的列建索引；联合索引把最常用的等值列放最左、范围列放最后；索引列 NOT NULL；单表索引 ≤ 5~6 个；长文本用前缀索引；自增主键避免页分裂；删索引前用 8.0 隐藏索引灰度。

### 14.3 选 RC 还是 RR

| | RR（默认） | RC |
| --- | --- | --- |
| ReadView | 首次快照读生成并复用 | 每次快照读重新生成 |
| 间隙锁 | 有（锁范围大、死锁概率高） | 无（锁冲突小、并发好） |
| 适用 | 需要可重复读的一致性后台任务、批处理 | 互联网高并发交易（配合业务重试） |

### 14.4 面试被问 MVCC（三句话版本）

「InnoDB 每行记录带 trx_id 和 roll_pointer，roll_pointer 把 undo log 里的旧版本串成版本链；查询时生成 ReadView（活跃事务集合），按四条规则判断版本链上哪个版本对自己可见，不可见就回溯上一版本；RC 每次读都生成新 ReadView，所以能看到别人最新提交，RR 只在第一次读生成并复用，所以整个事务读到的数据一致——这就是两者的本质区别。」

---

## 15. 常见问题与坑

| 问题 | 原因与解决方案 |
| --- | --- |
| `COUNT(*)` vs `COUNT(1)` vs `COUNT(列)`【高频】 | `COUNT(*)` 与 `COUNT(1)` 在 InnoDB 下**无性能差异**（优化器都会选最小的可用索引扫描，且不取值判空）；`COUNT(列)` 只统计该列**非 NULL** 的行，需要取值判断，语义也不同——统计总行数就用 `COUNT(*)`。MyISAM 无条件 `COUNT(*)` 是 O(1)（元数据存了行数），InnoDB 因 MVCC 各事务可见行数不同无法存全局计数 |
| DELETE vs TRUNCATE vs DROP | DELETE 是 DML：逐行删、可 WHERE、可回滚、触发触发器、不重置自增；TRUNCATE 是 DDL：按页清空、重置 AUTO_INCREMENT、隐式提交不可回滚（8.0 起为原子 DDL，清空或不清空不会「半途」）；DROP 连表结构一起删（8.0 原子 DDL，崩溃不会留下半删除状态） |
| VARCHAR 超长：为什么有时报错有时截断 | 取决于 sql_mode：5.7/8.0 默认含 STRICT_TRANS_TABLES，超长直接报错；非严格模式才截断 + warning。生产保持严格模式，靠测试暴露问题而不是靠截断 |
| 建表用 utf8 存不了 emoji | MySQL 的 `utf8` 是历史命名，实为 **utf8mb3**（每字符最多 3 字节），emoji 等 4 字节字符报错或变问号；必须用 **utf8mb4**（8.0 已将其设为默认字符集）。存量库迁移要同时改字符集与排序规则 |
| DATETIME 与 TIMESTAMP 混用 | TIMESTAMP 存 UTC 自动按 time_zone 转换且 4 字节，但 **2038-01-19 上限**；DATETIME 8 字节无时区语义、范围到 9999 年。统一团队约定：与时区相关的展示时间用 TIMESTAMP（或干脆存 UTC 毫秒 BIGINT），纯业务时间点用 DATETIME |
| `WHERE col != NULL` 永远查不到数据 | NULL 与任何值比较结果都是 NULL（非真），`=`/`!=`/`<>` 都过滤不掉；必须用 `IS NULL / IS NOT NULL`，或安全等号 `<=>`，或 `IFNULL(col, x)` 先替换 |
| LEFT JOIN 的条件放 ON 还是 WHERE 结果不同 | 对**被驱动表**的条件：放 ON——左表行全部保留，不匹配的右表列补 NULL（`ON b.status=1 AND ...`）；放 WHERE——连接完成后整行过滤，`b.status=1` 对 NULL 行为 NULL/假，**左表不匹配的行也会被删掉**，LEFT JOIN 退化成 INNER JOIN。要「保留左表」就把右表条件写在 ON 里 |
| WHERE 里隐式类型转换索引失效 | 字符串列与数字比较时 MySQL 把**列**转成数字（`WHERE phone=13800001111`），索引失效全表扫描；数字列与字符串比较则只转常量不受影响。保持常量类型与列类型一致（加引号） |
| 批量 DELETE 几百万行打挂主从 | 一条大事务 DELETE：长事务撑大 undo / 阻塞 purge、binlog 单条巨大导致从库延迟、锁持有时间长。按主键分批删：`DELETE ... WHERE id BETWEEN x AND x+5000 LIMIT ...` 循环 + 小 sleep，或业务允许时 TRUNCATE 分区 |
| INT 自增主键用完 / UUID 做主键为什么差 | INT UNSIGNED 上限约 42 亿，高吞吐日志表可能触顶（报 Failed to read auto-increment value from storage engine），大表用 BIGINT；UUID **随机无序**，插入聚簇索引位置随机，触发大量**页分裂**与碎片、缓存命中率低；要全局 ID 用雪花算法（趋势递增，对 B+ 树友好） |
| `IN (子查询)` 性能陷阱 | 老版本（5.5-）不优化，IN 子查询可能对**外表每行**执行一次子查询（EXPLAIN 显示 DEPENDENT SUBQUERY）；5.6+ 半连接优化后通常没问题。仍要警惕：NOT IN 遇 NULL 的语义陷阱（结果为空）、in 列表过长（数千个）退化；复杂场景改写成 EXISTS 或 JOIN |
| 改表卡住，后续所有查询都卡住 | MDL 元数据锁排队：某长事务持有该表 MDL 读锁，DDL 等写锁，**其后所有新查询排队等读锁**（MDL 写锁请求会阻塞后续读锁）。改表前查 `information_schema.innodb_trx` 与 `SHOW PROCESSLIST` 清理长事务，用 `lock_wait_timeout` 控制等待上限 |
| `ORDER BY RAND()` 全表排序 | 为每行生成随机值再全排序，O(N logN) 且无法用索引；小表随意，大表先随机取主键（`WHERE id >= (随机下界) LIMIT n`）或应用层随机 |
| 长事务的隐性危害 | 长事务阻碍 undo log 版本链清理（表膨胀）、持有 MDL/行锁阻塞 DDL 与其他事务、主从延迟放大。用 `information_schema.innodb_trx` 监控 `trx_started`，业务里禁止事务内做 RPC、发消息等慢操作 |

---

下一篇：《02-Redis设计与数据结构.md》　｜　模块索引：《../README.md》
