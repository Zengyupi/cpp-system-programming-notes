# Ceph 分布式存储

> 本节目标：系统讲解 Ceph 分布式存储系统的架构与核心概念。覆盖 MON/OSD/MDS/RGW 四大组件、CRUSH 算法、RADOS/RBD/CephFS/RGW 四种存储接口、PG 与 CRUSH map 的数据放置机制、副本与 EC 纠删码、对象→PG→OSD 的读写流程、集群部署与常用监控命令、性能调优与 benchmark、以及 Ceph 与 GlusterFS/FastDFS 的对比。学完后能理解 Ceph 的统一存储架构，掌握集群运维的基本命令，并能根据场景选择合适的存储接口。

## 本章速览

- [1. Ceph 概述与设计哲学](#1-ceph-概述与设计哲学)
- [2. Ceph 架构：四大组件](#2-ceph-架构四大组件)
  - [2.1 MON（Monitor）](#21-monmonitor)
  - [2.2 OSD（Object Storage Device）](#22-osdobject-storage-device)
  - [2.3 MDS（Metadata Server）](#23-mdsmetadata-server)
  - [2.4 RGW（Rados Gateway）](#24-rgwrados-gateway)
- [3. CRUSH 算法](#3-crush-算法)
  - [3.1 为什么需要 CRUSH](#31-为什么需要-crush)
  - [3.2 CRUSH 工作原理](#32-crush-工作原理)
  - [3.3 CRUSH map 结构](#33-crush-map-结构)
- [4. 存储模型：四种接口](#4-存储模型四种接口)
  - [4.1 RADOS：对象存储基础层](#41-rados对象存储基础层)
  - [4.2 RBD：块存储](#42-rbd块存储)
  - [4.3 CephFS：文件存储](#43-cephfs文件存储)
  - [4.4 RGW：对象存储网关](#44-rgw对象存储网关)
- [5. 数据放置：PG 与副本/EC](#5-数据放置pg-与副本ec)
  - [5.1 PG（Placement Group）](#51-pgplacement-group)
  - [5.2 副本模式（Replicated）](#52-副本模式replicated)
  - [5.3 纠删码（Erasure Coding）](#53-纠删码erasure-coding)
  - [5.4 PG 数量规划](#54-pg-数量规划)
- [6. 读写流程](#6-读写流程)
  - [6.1 对象→PG→OSD 映射](#61-对象pgosd-映射)
  - [6.2 写流程](#62-写流程)
  - [6.3 读流程](#63-读流程)
- [7. 集群部署与监控](#7-集群部署与监控)
  - [7.1 部署方式概述](#71-部署方式概述)
  - [7.2 常用监控命令](#72-常用监控命令)
- [8. 性能调优与 Benchmark](#8-性能调优与-benchmark)
  - [8.1 rados bench](#81-rados-bench)
  - [8.2 fio 测试 RBD](#82-fio-测试-rbd)
  - [8.3 性能调优要点](#83-性能调优要点)
- [9. Ceph vs GlusterFS vs FastDFS](#9-ceph-vs-glusterfs-vs-fastdfs)
- [10. 常见坑与最佳实践](#10-常见坑与最佳实践)
- [11. 快速参考卡片](#11-快速参考卡片)

---

## 1. Ceph 概述与设计哲学

Ceph 是一个开源的**统一分布式存储系统**，由 Sage Weil 于 2004 年开始开发（博士论文项目），2010 年正式开源。Ceph 的核心设计目标：

1. **统一存储**：一套系统同时提供对象存储（RGW）、块存储（RBD）、文件存储（CephFS）三种接口，底层共享同一套 RADOS 对象存储引擎。
2. **无中心架构**：没有单点故障的元数据服务器（对象存储层面），数据分布由 CRUSH 算法计算，客户端直接与 OSD 通信。
3. **高可靠**：数据多副本或纠删码，自动修复，无单点故障。
4. **高可扩展**：支持 PB 到 EB 级别，水平扩展，增加 OSD 节点即可扩容。
5. **自管理**：自动数据均衡、自动故障检测与恢复、自动集群映射更新。

Ceph 在云计算中广泛应用：OpenStack 的默认后端存储（Cinder 块存储、Glance 镜像、Swift 对象存储替代）、Kubernetes 的 RBD PV/CephFS PV、云平台的统一存储底座。

> 来源：Ceph 官方文档 ceph.io；《Ceph 分布式存储实战》。

---

## 2. Ceph 架构：四大组件

Ceph 集群由四种核心守护进程组成：

```text
┌─────────────────────────────────────────────────────┐
│                   客户端层                             │
│  RBD客户端  CephFS客户端  RGW(S3/Swift)  RADOS客户端 │
└──────────┬──────────┬──────────┬──────────┬─────────┘
           │          │          │          │
     ┌─────▼─────┐ ┌──▼───┐ ┌───▼────┐ ┌──▼──────┐
     │  MDS      │ │ MON  │ │  RGW   │ │  OSD    │
     │ (文件元数据)│ │(集群)│ │(对象网关)│ │(数据存储)│
     └───────────┘ └──────┘ └────────┘ └─────────┘
```

### 2.1 MON（Monitor）

- **职责**：维护集群的状态图（Cluster Map），包括 MON map、OSD map、PG map、CRUSH map、MDS map。
- **一致性**：多个 MON 节点通过 Paxos 算法（实际为改进版 Paxos）达成一致，通常部署 3 或 5 个（奇数）。
- **轻量**：MON 不存储实际数据，只维护集群元数据，资源消耗低。
- **客户端交互**：客户端启动时连接 MON 获取 Cluster Map，之后直接与 OSD 通信（不需要经过 MON）。

### 2.2 OSD（Object Storage Device）

- **职责**：存储实际数据对象，处理数据读写、复制、恢复、再平衡。
- **部署**：通常每个数据磁盘对应一个 OSD 进程（也支持目录模式，但生产环境用独立磁盘）。一个存储节点可以有多个 OSD。
- **通信**：OSD 之间互相通信（复制数据、心跳检测），OSD 与 MON 通信（上报状态、获取 map 更新）。
- **文件系统**：OSD 数据存储在本地文件系统上，推荐 XFS（也支持 ext4、btrfs，但 XFS 最稳定）。BlueStore 是 Ceph 12.2+ 的默认后端，直接管理裸盘（不经过本地文件系统），性能更好。

### 2.3 MDS（Metadata Server）

- **职责**：为 CephFS（文件存储）管理文件元数据（目录结构、文件属性、权限）。
- **特点**：MDS 不存储实际文件数据（数据存在 OSD 上），只管理元数据。MDS 可以水平扩展（Active-Active），通过子树分区实现元数据分片。
- **仅 CephFS 需要**：如果只用 RBD 或 RGW，不需要部署 MDS。

### 2.4 RGW（Rados Gateway）

- **职责**：提供 RESTful 对象存储网关，兼容 Amazon S3 API 和 OpenStack Swift API。
- **特点**：RGW 是一个 HTTP 服务，将 S3/Swift 请求转换为 RADOS 对象操作。支持多租户、桶策略、生命周期管理、版本控制等 S3 特性。
- **可扩展**：RGW 无状态，可部署多个实例，前面挂负载均衡器。

---

## 3. CRUSH 算法

### 3.1 为什么需要 CRUSH

传统分布式存储（如 HDFS）有一个中心元数据节点（NameNode）记录文件→块→节点的映射。这种架构的问题：
- 中心节点是单点瓶颈和单点故障。
- 元数据量随文件数增长，内存压力大。
- 客户端必须先问中心节点才能找到数据。

Ceph 用 **CRUSH（Controlled Replication Under Scalable Hashing）** 算法替代中心元数据节点：客户端根据对象名和 Cluster Map，**本地计算**出对象应该存储在哪些 OSD 上，不需要查询中心节点。

### 3.2 CRUSH 工作原理

CRUSH 是一种**伪随机确定性算法**：
1. 输入：对象名（或 PG ID）、Cluster Map（包含 CRUSH map）、副本数。
2. 计算：`hash(object_name) → PG ID`，然后 `CRUSH(PG ID, CRUSH map) → OSD 列表`。
3. 输出：对象应该存储的 OSD 列表（主 OSD + 副本 OSD）。

关键特性：
- **确定性**：相同输入总是得到相同输出，所有客户端和 OSD 计算结果一致。
- **伪随机分布**：数据均匀分布在所有 OSD 上，避免热点。
- **稳定映射**：集群变化（增删 OSD）时，只有少量数据需要迁移（约 1/N，N 为 OSD 数），而不是全部重分布。
- **拓扑感知**：CRUSH map 描述了物理拓扑（机架/机箱/节点/磁盘），可以配置故障域（如副本分布在不同机架），提高数据可靠性。

### 3.3 CRUSH map 结构

CRUSH map 是一个分层的树状结构，描述集群的物理拓扑和数据分布规则：

```text
root
├── rack1
│   ├── host1
│   │   ├── osd.0
│   │   └── osd.1
│   └── host2
│       ├── osd.2
│       └── osd.3
└── rack2
    ├── host3
    │   ├── osd.4
    │   └── osd.5
    └── host4
        ├── osd.6
        └── osd.7
```

CRUSH map 包含：
- **设备（Devices）**：OSD 列表，每个 OSD 有权重（weight，通常按容量）。
- **类型（Types）**：拓扑层级类型，如 osd、host、chassis、rack、row、room、datacenter、zone、region、root。
- **桶（Buckets）**：拓扑节点，每个桶有类型、名称、包含的子节点、权重、算法（straw2 是默认算法）。
- **规则（Rules）**：数据放置规则，定义副本数、故障域层级、使用的存储池。

```bash
# 查看和编辑 CRUSH map
ceph osd getcrushmap -o crushmap.bin
crushtool -d crushmap.bin -o crushmap.txt  # 反编译为文本
# 编辑 crushmap.txt
crushtool -c crushmap.txt -o crushmap-new.bin  # 编译
ceph osd setcrushmap -i crushmap-new.bin  # 应用
```

---

## 4. 存储模型：四种接口

### 4.1 RADOS：对象存储基础层

RADOS（Reliable Autonomic Distributed Object Store）是 Ceph 的底层对象存储引擎，所有上层接口（RBD/CephFS/RGW）都构建在 RADOS 之上。

核心概念：
- **对象（Object）**：RADOS 的基本存储单元，由对象名（OID）、数据、属性（key-value 元数据）组成。对象大小默认 4MB（可配置）。
- **存储池（Pool）**：对象的逻辑分组，类似命名空间。每个 Pool 有自己的副本数/EC 配置、PG 数量、CRUSH 规则。
- **PG（Placement Group）**：Pool 内的对象分片，每个 PG 包含一组对象，映射到一组 OSD。

RADOS 提供的 API：librados（C/C++/Python/Java 等），允许直接操作对象。

```bash
# rados 命令行工具
rados lspools                          # 列出存储池
rados -p mypool put myobj localfile   # 上传对象
rados -p mypool get myobj localfile   # 下载对象
rados -p mypool rm myobj              # 删除对象
rados -p mypool ls                     # 列出对象
```

### 4.2 RBD：块存储

RBD（RADOS Block Device）将块设备镜像存储为 RADOS 对象集合：
- 一个 RBD 镜像被切分为多个对象（默认 4MB/对象），对象名包含镜像 ID 和分片编号。
- 客户端（krbd 内核模块或 librbd 用户态库）将 RBD 镜像映射为本地块设备（如 `/dev/rbd0`），可以格式化、挂载、用作虚拟机磁盘。
- 支持快照、克隆（写时复制）、精简配置、增量备份。

```bash
# RBD 常用命令
rbd create mypool/myimage --size 10240  # 创建 10GB 镜像
rbd ls mypool                             # 列出镜像
rbd info mypool/myimage                   # 查看镜像信息
rbd map mypool/myimage                    # 映射为块设备（内核模块）
rbd unmap /dev/rbd0                       # 取消映射
rbd snap create mypool/myimage@snap1      # 创建快照
rbd snap ls mypool/myimage                # 列出快照
rbd clone mypool/myimage@snap1 mypool/newimage  # 克隆
```

RBD 是 OpenStack Cinder、Kubernetes 块存储 PV 的主流后端。

### 4.3 CephFS：文件存储

CephFS（Ceph File System）提供 POSIX 兼容的分布式文件系统：
- 文件数据以对象形式存储在 OSD 上（通过 RADOS）。
- 文件元数据（目录、inode、权限）由 MDS 管理，元数据也存储在 OSD 上（MDS 是缓存和协调者）。
- 支持 POSIX 语义、大目录、动态元数据分片（MDS 集群）、快照。

```bash
# CephFS 常用命令
ceph fs ls                              # 列出文件系统
ceph fs status cephfs                   # 查看文件系统状态
mkdir /mnt/cephfs
mount -t ceph mon1:6789:/ /mnt/cephfs -o name=admin,secret=xxx  # 挂载
# 或使用 ceph-fuse（用户态）
ceph-fuse /mnt/cephfs
```

CephFS 适合大规模文件共享、日志存储、媒体文件等场景。Kubernetes 支持 CephFS PV（ReadWriteMany）。

### 4.4 RGW：对象存储网关

RGW（Rados Gateway）提供兼容 S3 和 Swift 的 RESTful 对象存储接口：
- 客户端通过 HTTP/HTTPS 访问 RGW，RGW 将请求转换为 RADOS 对象操作。
- 支持 S3 API：桶（Bucket）、对象、ACL、桶策略、生命周期、版本控制、多部分上传、预签名 URL。
- 支持 Swift API：容器、对象、账户。
- 支持多站点（Multi-Site）：跨地域数据复制，实现异地灾备。

```bash
# RGW 常用操作（S3 API，使用 s3cmd 或 aws-cli）
s3cmd mb s3://mybucket                 # 创建桶
s3cmd put localfile s3://mybucket/     # 上传对象
s3cmd get s3://mybucket/remotefile .   # 下载对象
s3cmd ls s3://mybucket/                 # 列出对象
s3cmd rb s3://mybucket                  # 删除桶
```

---

## 5. 数据放置：PG 与副本/EC

### 5.1 PG（Placement Group）

PG（Placement Group，放置组）是 Ceph 中对象到 OSD 的中间映射层：

```text
对象 → hash(object) → PG ID → CRUSH(PG ID) → OSD 列表
```

为什么需要 PG 这一层？
- 如果直接将对象映射到 OSD，每个对象需要独立跟踪映射状态，元数据量太大。
- PG 将一组对象聚合在一起，统一管理映射、复制、恢复，减少元数据开销。
- PG 是数据复制和恢复的基本单位：一个 PG 的所有对象存储在同一组 OSD 上，PG 内的对象一起复制、一起恢复。

PG 状态：
- **Active+Clean**：正常状态，主 OSD 和副本 OSD 都在线，数据一致。
- **Active+Degraded**：有副本 OSD 故障，数据副本数不足，正在恢复。
- **Active+Remapped**：PG 被重新映射到新的 OSD（集群变化后），正在迁移数据。
- **Peering**：PG 正在进行对等连接（主 OSD 与副本 OSD 协商数据一致性）。
- **Inactive**：PG 不可用（没有足够的 OSD 提供服务）。

### 5.2 副本模式（Replicated）

副本模式是 Ceph 的默认数据冗余方式：每个对象存储 N 份副本（通常 3 副本），分布在不同 OSD 上（通过 CRUSH 故障域控制，可分布在不同主机/机架）。

- **写流程**：客户端写主 OSD，主 OSD 同步复制到副本 OSD，所有副本写入成功后返回客户端确认。
- **读流程**：客户端从主 OSD 读取（也可配置从副本读，降低主 OSD 压力）。
- **恢复**：OSD 故障后，PG 的其他副本 OSD 会将数据复制到新的 OSD，恢复副本数。
- **空间利用率**：3 副本的空间利用率为 1/3（3TB 原始空间存 1TB 数据）。

### 5.3 纠删码（Erasure Coding）

纠删码（EC）是一种更节省空间的数据冗余方式：将数据切分为 K 个数据块，计算 M 个校验块，总共 K+M 个块，存储在不同 OSD 上。只要有任意 K 个块可用，就能恢复全部数据。

- **常见配置**：K=2, M=1（可容忍 1 个 OSD 故障，空间利用率 2/3）；K=4, M=2（可容忍 2 个故障，利用率 4/6=2/3）；K=8, M=3（可容忍 3 个故障，利用率 8/11≈73%）。
- **空间利用率**：EC 的空间利用率为 K/(K+M)，远高于 3 副本的 33%。
- **性能代价**：写时需要计算校验码（CPU 开销），读时如果有块丢失需要解码恢复（CPU + 网络开销）。EC 适合冷数据、归档数据（写少读少），不适合高性能热数据。
- **Ceph EC 实现**：EC Pool 使用 Jerasure 或 ISA-L 库，支持多种 EC 算法（Reed-Solomon、Cauchy 等）。EC Pool 不支持部分写（RBD 等需要部分写的场景需用副本池做日志，即 EC 的 RBD 支持有限）。

### 5.4 PG 数量规划

PG 数量是 Ceph 集群的重要参数，影响数据分布均匀性和管理开销：

- **PG 太少**：数据分布不均，部分 OSD 负载高，恢复时粒度大。
- **PG 太多**：每个 PG 有元数据开销（内存、CPU），OSD 上 PG 过多导致管理开销大，peering 时间长。

官方推荐公式：
```text
PG 总数 = (OSD 总数 × 100) / 副本数
结果向上取整到最接近的 2 的幂
```

例如：100 个 OSD，3 副本 → (100×100)/3 ≈ 3333 → 取 4096 个 PG。

每个 Pool 的 PG 数 = 总 PG 数 × (该 Pool 容量占比)。Ceph 14+ 支持自动调整 PG 数（`pg_autoscale_mode = on`）。

```bash
# 查看 PG 状态
ceph pg stat
ceph pg dump
ceph osd pool get mypool pg_num
ceph osd pool get mypool pgp_num

# 调整 PG 数（需同时调整 pg_num 和 pgp_num）
ceph osd pool set mypool pg_num 1024
ceph osd pool set mypool pgp_num 1024
```

---

## 6. 读写流程

### 6.1 对象→PG→OSD 映射

客户端写一个对象时，映射过程：

```text
1. 对象名 (oid) = pool_id + object_name
2. PG ID = hash(oid) mod pg_num
3. CRUSH 算法输入：PG ID + CRUSH map + 副本数
4. CRUSH 输出：OSD 列表 [osd.5(主), osd.2(副本), osd.8(副本)]
```

客户端从 MON 获取 Cluster Map 后，本地计算映射，直接连接主 OSD。

### 6.2 写流程

1. 客户端计算对象的主 OSD，发送写请求到主 OSD。
2. 主 OSD 写入本地存储（BlueStore 先写 WAL/RocksDB，再写数据块）。
3. 主 OSD 并行将写请求转发给所有副本 OSD。
4. 每个副本 OSD 写入本地后，向主 OSD 发送确认。
5. 主 OSD 收到所有副本确认后，向客户端发送写入成功确认。

这是**同步复制**：所有副本都写入成功才返回，保证数据一致性。如果某个副本 OSD 故障，主 OSD 会记录该 PG 为 Degraded 状态，等新 OSD 加入后恢复。

**写一致性级别**：
- 默认：所有副本写入成功才返回（强一致）。
- 可配置 `min_size`：至少 N 个副本写入成功就返回（降低一致性要求提高可用性，默认 min_size = 副本数的一半向上取整，3 副本默认 min_size=2）。

### 6.3 读流程

1. 客户端计算对象的主 OSD，发送读请求到主 OSD。
2. 主 OSD 从本地存储读取对象数据。
3. 主 OSD 返回数据给客户端。

默认从主 OSD 读。可配置**读副本**（`rbd_read_from_replica` 或 Pool 级别的 `read_from_replica`），从最近的副本 OSD 读，降低主 OSD 压力和跨机架读延迟（适合多机架部署）。

---

## 7. 集群部署与监控

### 7.1 部署方式概述

- **cephadm**（Ceph 15+ 推荐）：基于容器的部署工具，通过 SSH 管理节点，支持服务发现、监控告警集成（Prometheus/Grafana）。
- **ceph-ansible**：Ansible playbook 部署，适合熟悉 Ansible 的团队。
- **手动部署**：逐个安装配置 MON/OSD/MDS/RGW，适合学习和定制化。
- **Rook**：Kubernetes 上的 Ceph  Operator，将 Ceph 作为 K8s 应用部署和管理。

生产环境基本要求：
- 至少 3 个 MON 节点（奇数，Paxos 多数派）。
- 至少 3 个 OSD 节点（3 副本需要至少 3 个 OSD，且分布在不同故障域）。
- 每个 OSD 节点推荐：独立系统盘 + 独立数据盘（BlueStore 用独立 DB/WAL 盘可提升性能，通常用 SSD/NVMe 做 DB/WAL，HDD 做数据）。
- 网络：前端网络（客户端↔集群）+ 后端网络（OSD 间复制/恢复）分离，万兆网络起步。

### 7.2 常用监控命令

```bash
# 集群整体状态
ceph -s                    # 集群状态摘要（health、mon、osd、pg、io）
ceph status                # 同 ceph -s
ceph health detail         # 健康详情（列出具体告警）

# OSD 状态
ceph osd status            # OSD 状态表
ceph osd tree              # OSD 拓扑树（按主机/机架分组）
ceph osd df                # OSD 容量使用情况
ceph osd perf              # OSD 性能（延迟）

# PG 状态
ceph pg stat               # PG 统计（总数、各状态数量）
ceph pg dump               # PG 详细列表
ceph pg map <pgid>         # 查看 PG 映射到哪些 OSD

# 存储池
ceph osd lspools           # 列出存储池
ceph osd pool stats        # 存储池 IO 统计
ceph df                     # 存储池容量使用（类似 df）

# 监控与日志
ceph mon stat              # MON 状态
ceph mds stat              # MDS 状态（CephFS）
ceph -w                     # 实时监控集群事件（类似 tail -f）
ceph log last 20           # 查看最近 20 条集群日志

# 配置管理
ceph config show osd.0     # 查看 OSD 运行时配置
ceph config set osd.0 debug_ms 1  # 动态设置配置
```

`ceph -s` 输出示例：
```text
  cluster:
    id:     1f2a3b4c-5d6e-7f8a-9b0c-1d2e3f4a5b6c
    health: HEALTH_OK

  services:
    mon: 3 daemons, quorum mon1,mon2,mon3 (age 2w)
    mgr: mon1(active, since 2w), standbys: mon2
    osd: 12 osds: 12 up (since 2w), 12 in (since 2w)

  data:
    pools:   5 pools, 128 pgs
    objects: 1.2M objects, 4.5 TiB
    usage:   13 TiB used, 20 TiB / 33 TiB avail
    pgs:     128 active+clean

  io:
    client:   1.2 MiB/s rd, 3.5 MiB/s wr, 120 op/s rd, 350 op/s wr
```

---

## 8. 性能调优与 Benchmark

### 8.1 rados bench

`rados bench` 是 Ceph 自带的基准测试工具，直接测试 RADOS 层的性能：

```bash
# 写测试：在 mypool 中持续写 60 秒，4MB 对象，并发 16
rados bench -p mypool 60 write -b 4194304 -t 16 --no-cleanup

# 读测试（需要先有数据，用上面写测试的 --no-cleanup 保留数据）
rados bench -p mypool 60 seq -t 16    # 顺序读
rados bench -p mypool 60 rand -t 16   # 随机读

# 清理测试数据
rados -p mypool cleanup
```

输出包含：带宽（MB/s）、IOPS、延迟（平均/最大/标准差）。

### 8.2 fio 测试 RBD

测试 RBD 块设备性能用 fio：

```bash
# 先创建并映射 RBD 镜像
rbd create mypool/testvol --size 10240
rbd map mypool/testvol  # 得到 /dev/rbd0

# fio 随机写测试
fio --name=randwrite --ioengine=libaio --iodepth=32 \
    --rw=randwrite --bs=4k --direct=1 --size=1G \
    --filename=/dev/rbd0 --numjobs=4 --group_reporting

# fio 随机读测试
fio --name=randread --ioengine=libaio --iodepth=32 \
    --rw=randread --bs=4k --direct=1 --size=1G \
    --filename=/dev/rbd0 --numjobs=4 --group_reporting
```

### 8.3 性能调优要点

1. **硬件层面**：
   - OSD 数据盘用 HDD，DB/WAL 盘用 SSD/NVMe（BlueStore 分离部署），显著提升写性能。
   - 万兆/25GbE 网络，前后端网络分离。
   - 足够的 CPU（每个 OSD 约 1 核，EC 和压缩更耗 CPU）。

2. **BlueStore 调优**：
   - `bluestore_cache_size`：BlueStore 缓存大小，默认 1GB，可适当增大。
   - `bluestore_compression_algorithm`：开启压缩（lz4/zstd），节省空间，CPU 换空间。
   - `bluestore_min_alloc_size_hdd`：HDD 最小分配单元（默认 64K），小对象多时可调小。

3. **PG 与 CRUSH**：
   - 合理的 PG 数（见 5.4 节）。
   - 配置故障域（rack/host），平衡可靠性和性能。
   - 开启 `pg_autoscale_mode` 自动调整。

4. **客户端调优**：
   - RBD 调优：`rbd_cache`（开启客户端缓存）、`rbd_cache_size`、`rbd_cache_max_dirty`。
   - 增加并发：`iodepth`、`numjobs`，充分利用并行。
   - 大对象/大 IO：顺序读写用大 block size（1M+）。

5. **通用**：
   - 关闭 THP（透明大页），避免延迟抖动。
   - 调整 CPU 调度器为 performance。
   - 磁盘队列深度 `nr_requests` 调大。
   - 监控 `ceph osd perf` 的延迟，识别慢 OSD。

---

## 9. Ceph vs GlusterFS vs FastDFS

| 维度 | Ceph | GlusterFS | FastDFS |
|------|------|-----------|---------|
| 存储类型 | 统一存储（对象/块/文件） | 分布式文件存储 | 分布式文件存储（对象级） |
| 架构 | 无中心（MON 仅存元数据） | 无中心（DHT 哈希） | 有中心（Tracker 调度） |
| 数据冗余 | 副本 / EC 纠删码 | 副本（AFR） / 分散（DHT） / 条带 | 副本（同组 Storage） |
| 元数据管理 | CRUSH 计算（对象）/ MDS（文件） | 无独立元数据，DHT 计算 | Tracker 管理（内存） |
| 接口 | S3/Swift/RBD/POSIX/NFS | POSIX/NFS/SMB | 私有 API / Nginx HTTP |
| 一致性 | 强一致（同步复制） | 最终一致（AFR 自愈） | 最终一致（binlog 同步） |
| 扩展性 | 极高（EB 级） | 高（PB 级） | 中（PB 级，Tracker 瓶颈） |
| 性能 | 高（块/对象），文件依赖 MDS | 中（小文件差） | 高（大文件上传下载） |
| 适用场景 | 云平台统一存储、块存储、对象存储 | 文件共享、媒体存储 | 图床、视频、附件存储 |
| 运维复杂度 | 高（概念多、调优复杂） | 中 | 低（架构简单） |
| 社区/生态 | 活跃（OpenStack/K8s 集成） | 一般（RedHat 维护） | 国内活跃（淘宝开源） |

选型建议：
- 需要块存储（虚拟机磁盘、K8s PV）或 S3 对象存储 → **Ceph**。
- 需要 POSIX 文件共享、媒体文件存储 → **GlusterFS** 或 CephFS。
- 简单的文件上传下载、图床、视频存储，追求简单高效 → **FastDFS**。

---

## 10. 常见坑与最佳实践

### 10.1 常见坑汇总

| 坑 | 现象 | 原因 | 解决方案 |
|----|------|------|----------|
| PG 数量不合理 | 数据分布不均 / OSD 内存高 | PG 太多或太少 | 按公式规划，开启 pg_autoscale |
| 近满 OSD | 集群告警、写入失败 | OSD 容量不均或全满 | 监控容量，`mon_osd_full_ratio` 调优，及时扩容 |
| 恢复风暴 | 扩容/故障后集群 IO 打满 | 恢复速度限制过高 | 调小 `osd_recovery_max_active`、`osd_recovery_sleep` |
| 慢 OSD | 集群延迟高、请求超时 | 磁盘坏道/性能差、网络问题 | `ceph osd perf` 定位，更换坏盘，检查网络 |
| MON 时钟漂移 | MON 无法形成 quorum | 节点时间不同步 | 配置 NTP/chrony，时钟偏差 <50ms |
| EC Pool 部分写 | RBD 在 EC Pool 上性能差 | EC 不支持部分写 | EC Pool 用于冷数据，RBD 用副本池 |
| 大对象性能差 | 单对象读写慢 | 对象大小设置不合理 | 调整 `rbd_obj_size`，大文件用大对象 |
| 网络瓶颈 | 跨机架读写延迟高 | 前后端网络未分离 | 分离网络，万兆以上，读副本配置 |

### 10.2 最佳实践

1. **部署**：
   - MON 至少 3 个，分布在不同物理节点。
   - OSD 节点至少 3 个，3 副本分布在不同主机/机架。
   - 系统盘与数据盘分离，BlueStore DB/WAL 用 SSD。
   - 前后端网络分离，万兆起步。

2. **存储池规划**：
   - 热数据用 3 副本池，冷数据用 EC 池。
   - 合理设置 PG 数，开启自动调整。
   - 不同业务用不同 Pool，便于配额和隔离。

3. **运维**：
   - 建立监控：Prometheus + Grafana（cephadm 自带），告警关键指标（OSD down、PG 异常、容量、延迟）。
   - 定期检查 `ceph health`，及时处理告警。
   - 扩容时控制恢复速度，避免影响业务。
   - 定期做数据恢复演练（拔盘测试）。

4. **性能**：
   - 写密集场景：BlueStore DB/WAL 用 NVMe，开启写缓存。
   - 读密集场景：开启读副本，增加客户端缓存。
   - 冷数据：EC + 压缩，节省空间。
   - 定期 benchmark，建立性能基线。

---

## 11. 快速参考卡片

### 11.1 架构组件表

| 组件 | 职责 | 是否必需 | 数量建议 |
|------|------|----------|----------|
| MON | 集群元数据、一致性 | 是 | 3 或 5（奇数） |
| MGR | 集群管理、监控、REST API | 是（14+） | 1 active + 1 standby |
| OSD | 数据存储、复制、恢复 | 是 | ≥3，按容量规划 |
| MDS | CephFS 元数据 | 仅 CephFS | ≥1，可多 active |
| RGW | S3/Swift 对象网关 | 仅对象存储 | ≥2，负载均衡 |

### 11.2 常用命令速查

```bash
# 集群状态
ceph -s / ceph status / ceph health detail
ceph -w  # 实时事件

# OSD
ceph osd tree / ceph osd df / ceph osd status / ceph osd perf
ceph osd in/out <id> / ceph osd up/down <id>

# PG
ceph pg stat / ceph pg dump / ceph pg map <pgid>

# 存储池
ceph osd lspools / ceph df / ceph osd pool stats
ceph osd pool create <name> <pg_num>
ceph osd pool set <name> <key> <value>

# RBD
rbd create <pool>/<image> --size <MB>
rbd ls <pool> / rbd info <pool>/<image>
rbd map/unmap <pool>/<image>
rbd snap create/clone/ls

# 配置
ceph config show <daemon> / ceph config set <daemon> <key> <value>
```

### 11.3 关键配置参数

```ini
# 全局
mon_host = mon1,mon2,mon3
public_network = 10.0.0.0/24
cluster_network = 10.0.1.0/24

# OSD
osd_pool_default_size = 3          # 默认副本数
osd_pool_default_min_size = 2      # 最小写入副本数
osd_recovery_max_active = 3         # 恢复并发数
osd_recovery_sleep = 0.1            # 恢复间隔
osd_max_backfills = 1               # 回填并发

# BlueStore
bluestore_cache_size = 4294967296  # 4GB 缓存
bluestore_compression_algorithm = lz4
bluestore_compression_mode = passive

# PG
osd_pool_default_pg_num = 128
osd_pool_default_pgp_num = 128
pg_autoscale_mode = on

# 网络
ms_bind_ipv4 = true
ms_public_iface = eth0
ms_cluster_iface = eth1
```

### 11.4 健康状态速查

| 状态 | 含义 | 处理 |
|------|------|------|
| HEALTH_OK | 集群正常 | 无需处理 |
| HEALTH_WARN | 警告（PG degraded、OSD near full 等） | 查看 `ceph health detail`，及时处理 |
| HEALTH_ERR | 错误（PG inactive、OSD full、MON 不足等） | 立即处理，可能影响服务 |

---

上一篇：《08-MySQL深入：事务锁与索引优化.md》　｜　下一篇：《10-FastDFS分布式文件系统.md》　｜　模块索引：《../README.md》
