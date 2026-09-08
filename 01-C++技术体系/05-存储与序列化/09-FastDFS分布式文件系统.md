# FastDFS 分布式文件系统

> 本节目标：系统讲解 FastDFS 分布式文件系统的架构与核心机制。覆盖 Tracker Server / Storage Server / Client 三层架构、文件上传与下载流程、文件 ID 格式（group/磁盘/两级目录/文件名）、同内容去重机制、binlog 同步机制、水平扩容、集群部署配置、与 Nginx 集成提供 HTTP 访问、以及图床/短链服务等应用场景。学完后能理解 FastDFS 的轻量架构，掌握集群部署配置，能搭建基于 FastDFS + Nginx 的文件存储服务。

## 本章速览

- [1. FastDFS 概述与设计哲学](#1-fastdfs-概述与设计哲学)
- [2. FastDFS 架构：三层角色](#2-fastdfs-架构三层角色)
  - [2.1 Tracker Server（跟踪服务器）](#21-tracker-server跟踪服务器)
  - [2.2 Storage Server（存储服务器）](#22-storage-server存储服务器)
  - [2.3 Client（客户端）](#23-client客户端)
- [3. 文件上传流程](#3-文件上传流程)
- [4. 文件下载流程](#4-文件下载流程)
- [5. 文件 ID 格式详解](#5-文件-id-格式详解)
- [6. 同内容去重机制](#6-同内容去重机制)
- [7. binlog 同步机制](#7-binlog-同步机制)
- [8. 水平扩容与负载均衡](#8-水平扩容与负载均衡)
- [9. 集群部署配置](#9-集群部署配置)
  - [9.1 环境准备与安装](#91-环境准备与安装)
  - [9.2 Tracker 配置](#92-tracker-配置)
  - [9.3 Storage 配置](#93-storage-配置)
  - [9.4 启动与验证](#94-启动与验证)
- [10. 与 Nginx 集成提供 HTTP 访问](#10-与-nginx-集成提供-http-访问)
  - [10.1 fastdfs-nginx-module 模块](#101-fastdfs-nginx-module-模块)
  - [10.2 Nginx 配置](#102-nginx-配置)
  - [10.3 防盗链与访问控制](#103-防盗链与访问控制)
- [11. 应用场景：图床与短链服务](#11-应用场景图床与短链服务)
- [12. 常见坑与最佳实践](#12-常见坑与最佳实践)
- [13. 快速参考卡片](#13-快速参考卡片)

---

## 1. FastDFS 概述与设计哲学

FastDFS 是一个开源的轻量级分布式文件系统，由淘宝的余庆（happy_fish100）于 2008 年开发，用 C 语言实现。它解决了大容量文件存储和高并发访问的问题，特别适合以文件为载体的在线服务（如图片分享、视频网站、文档存储、下载站）。

**设计特点**：
1. **轻量简洁**：核心只有 Tracker 和 Storage 两个角色，没有复杂的元数据服务器，架构简单，运维成本低。
2. **分组存储**：Storage 按组（group）组织，同组内 Storage 存储相同数据（互为副本），组间存储不同数据（分片）。组内冗余、组间扩展。
3. **文件 ID 路由**：文件上传后返回文件 ID（包含 group 和路径），客户端通过文件 ID 直接访问 Storage，不需要查询元数据。
4. **同内容去重**：上传相同内容的文件时，通过文件哈希去重，只存一份，节省存储空间。
5. **无中心瓶颈**：Tracker 只做调度（不存文件、不存元数据），Storage 直接服务客户端，Tracker 压力小，可集群部署。

**适用场景**：
- 图片/视频/文档等文件的存储与访问
- 图床、附件存储、静态资源 CDN 源站
- 不适合：需要 POSIX 文件系统语义的场景、小文件海量存储（FastDFS 对小文件有合并存储优化但不如专门的小文件系统）、需要复杂目录结构的场景。

> 来源：FastDFS 官方文档 github.com/happyfish100/fastdfs；《FastDFS 分布式文件系统原理与实践》。

---

## 2. FastDFS 架构：三层角色

```text
┌──────────┐     ┌──────────┐     ┌──────────┐
│ Client   │────▶│ Tracker  │────▶│ Tracker  │  (Tracker 集群，对等)
│          │     └──────────┘     └──────────┘
│          │
│          │     ┌──────────────────────────────────┐
│          │────▶│ Group1                           │
│          │     │  ┌────────┐  ┌────────┐         │
│          │     │  │Storage │  │Storage │  (副本) │
│          │     │  └────────┘  └────────┘         │
│          │     └──────────────────────────────────┘
│          │
│          │     ┌──────────────────────────────────┐
│          │────▶│ Group2                           │
│          │     │  ┌────────┐  ┌────────┐         │
│          │     │  │Storage │  │Storage │  (副本) │
│          │     │  └────────┘  └────────┘         │
│          │     └──────────────────────────────────┘
└──────────┘
```

### 2.1 Tracker Server（跟踪服务器）

- **职责**：调度中心，负责管理所有 Storage Server，维护 Storage 的状态信息（在线/离线、容量、分组）。客户端上传/下载前先向 Tracker 查询可用的 Storage。
- **不存储**：Tracker 不存储文件数据，也不存储文件元数据（文件索引），只维护 Storage 的分组和状态信息（内存中）。
- **集群**：Tracker 之间是对等关系（无主从），多个 Tracker 独立运行，客户端可配置多个 Tracker 地址，轮询或随机选择。Tracker 之间不通信，各自从 Storage 的心跳中获取状态。
- **轻量**：Tracker 资源消耗极低，一台普通服务器可支撑大量 Storage 和客户端。

### 2.2 Storage Server（存储服务器）

- **职责**：实际存储文件数据，处理文件的上传、下载、删除、同步。
- **分组（group）**：Storage 按组组织，一个组内有多个 Storage 节点，存储相同的文件（互为副本，保证数据冗余）。不同组存储不同的文件（数据分片，水平扩展）。
- **存储路径**：每个 Storage 可配置多个存储路径（store_path），对应不同的磁盘，路径之间轮询存储（可配置负载策略）。
- **心跳**：Storage 定期向所有 Tracker 发送心跳，上报状态（容量、文件数、同步状态）。Tracker 根据心跳判断 Storage 是否在线。
- **同步**：同组内 Storage 之间通过 binlog 同步文件，保证数据一致。

### 2.3 Client（客户端）

- **职责**：与 Tracker 和 Storage 交互，执行文件上传、下载、删除等操作。
- **工作流程**：
  1. 上传：向 Tracker 请求可用的 Storage → 上传文件到 Storage → 获取文件 ID。
  2. 下载：向 Tracker 请求文件所在组的可用 Storage → 直接从 Storage 下载文件。
- **客户端库**：官方提供 C Client（libfastcommon），社区有 Java、Python、Go、PHP、C# 等客户端。

---

## 3. 文件上传流程

1. **客户端向 Tracker 发送上传请求**：`tracker_query_storage_store_without_group()` 或指定 group 的 `tracker_query_storage_store()`。
2. **Tracker 选择 Storage**：
   - 选择一个组（group）：根据组的剩余空间、文件数等策略选择（可配置 `store_lookup`：0=轮询组、1=指定组、2=剩余空间最大的组）。
   - 在组内选择一个 Storage 节点：根据 `store_server` 策略（0=轮询、1=按 IP 排序第一个、2=按优先级排序）。
   - 选择存储路径（store_path）：根据 `store_path` 策略（0=轮询、1=剩余空间最大）。
3. **Tracker 返回 Storage 信息**：IP、端口、存储路径索引。
4. **客户端上传文件到 Storage**：发送文件内容、文件扩展名、文件大小等。
5. **Storage 处理文件**：
   - 计算文件内容的哈希（MD5），检查是否已有相同内容的文件（去重）。
   - 如果去重命中，直接返回已有的文件 ID。
   - 如果未命中，生成文件 ID，写入文件到磁盘，记录 binlog。
6. **Storage 返回文件 ID**：格式如 `group1/M00/00/00/wKgBgV...jpg`。
7. **客户端保存文件 ID**：后续通过文件 ID 访问文件。

```text
Client                    Tracker                   Storage
  │                          │                          │
  │── query_storage_store ──▶│                          │
  │                          │── 选择 group/Storage ──▶│
  │◀── Storage IP:port ─────│                          │
  │                          │                          │
  │──────── upload file ──────────────────────────────▶│
  │                          │                          │── 写文件、记 binlog
  │◀────── file_id (group1/M00/00/00/xxx.jpg) ───────│
  │                          │                          │
```

---

## 4. 文件下载流程

1. **客户端向 Tracker 发送下载查询请求**：`tracker_query_storage_fetch()`，参数为文件 ID 中的 group 名。
2. **Tracker 选择 Storage**：在指定 group 中选择一个在线的 Storage 节点（根据 `download_server` 策略：0=轮询、1=按 IP 排序第一个）。
3. **Tracker 返回 Storage 信息**：IP、端口。
4. **客户端直接向 Storage 发送下载请求**：参数为文件 ID（group + 路径 + 文件名）。
5. **Storage 查找文件**：根据文件 ID 中的路径信息，在本地磁盘定位文件。
6. **Storage 返回文件内容**：将文件流发送给客户端。

```text
Client                    Tracker                   Storage
  │                          │                          │
  │── query_storage_fetch ──▶│                          │
  │                          │── 选择 group 内 Storage ─▶│
  │◀── Storage IP:port ─────│                          │
  │                          │                          │
  │──────── download file (file_id) ──────────────────▶│
  │                          │                          │── 定位文件、读取
  │◀────── file content stream ────────────────────────│
  │                          │                          │
```

注意：下载时客户端也可以**跳过 Tracker**，直接使用文件 ID 中的 group 信息和已知的 Storage 地址下载（如果客户端缓存了 Storage 列表）。但通常还是先查 Tracker 获取最新可用的 Storage，避免访问已下线的节点。

---

## 5. 文件 ID 格式详解

FastDFS 的文件 ID 格式：

```text
group1/M00/00/00/wKgBgV12345.jpg
└──┬──┘ └┬┘ └┬┘ └┬┘ └─────┬─────┘
   │     │    │    │         │
   │     │    │    │         └── 文件名（含扩展名）
   │     │    │    └──────────── 二级目录（00~FF，256个）
   │     │    └───────────────── 一级目录（00~FF，256个）
   │     └────────────────────── 存储路径标识（M00=第一个store_path，M01=第二个...）
   └──────────────────────────── 组名（group）
```

各字段说明：

| 字段 | 说明 | 示例 |
|------|------|------|
| group | 组名，文件所在的 Storage 组 | group1 |
| M00 | 存储路径标识，M00 对应第一个 store_path，M01 对应第二个 | M00 |
| 00/00 | 两级目录，每级 256 个（00~FF），共 65536 个目录，避免单目录文件过多 | 00/00 |
| 文件名 | 由 Storage 生成，包含时间戳、文件大小、随机数、源 Storage IP 等信息编码，加上原始扩展名 | wKgBgV12345.jpg |

**文件名生成规则**（FastDFS 5.x+）：
文件名是一个 base62 编码的字符串，解码后包含：
- 时间戳（4 字节）：文件上传时间
- 文件大小（4 或 8 字节）
- 随机数（2 字节）：防止文件名冲突
- 源 Storage IP（4 字节）：上传到的 Storage IP，用于同步溯源
- 校验码（1 字节）

这种设计保证文件名全局唯一，且包含溯源信息。两级目录（65536 个目录）将文件分散存储，避免单目录文件数过多导致的性能问题（ext4 单目录文件数过多时性能下降）。

---

## 6. 同内容去重机制

FastDFS 支持**同内容文件去重**（file content dedup），通过文件内容的哈希值判断是否重复：

1. 客户端上传文件时，Storage 计算文件内容的 MD5 哈希值。
2. Storage 在去重索引中查找该 MD5 是否已存在。
3. 如果已存在：不重复存储文件内容，直接返回已有的文件 ID（或创建一个新的文件 ID 指向同一份数据，取决于配置）。
4. 如果不存在：存储文件，记录 MD5 到去重索引。

**去重索引存储**：
- FastDFS 5.x 之前：去重索引存储在 Storage 本地的 Berkeley DB 或内置的 hash 表中。
- FastDFS 5.x+：推荐使用 FastDHT（分布式哈希表）存储去重索引，支持多 Storage 共享去重索引。
- 也可以用 Redis 等外部 KV 存储去重索引。

**去重的注意事项**：
- 去重只针对**文件内容完全相同**的文件（MD5 相同），文件名不同但内容相同也算重复。
- 去重会增加上传时的计算开销（MD5 计算）和索引查询开销。
- 删除文件时需要引用计数：多个文件 ID 指向同一份数据时，删除一个文件 ID 不应删除实际数据，直到引用计数为 0。
- 去重适合大量重复文件的场景（如用户上传相同的图片、视频），不适合文件内容几乎不重复的场景。

配置项：
```ini
# storage.conf
check_file_duplicate = 1          # 开启去重（0=关闭，1=开启）
file_distribute_path = /etc/fdfs/file_distribute.conf  # 去重索引配置
```

---

## 7. binlog 同步机制

同组内 Storage 之间通过 **binlog** 同步文件，保证数据一致性：

1. **写 binlog**：Storage 处理文件上传/删除/修改时，将操作记录到本地 binlog 文件中。binlog 记录操作类型（上传/删除）、文件名、文件路径、时间戳等。
2. **同步 binlog**：同组内的其他 Storage 节点定期（可配置同步间隔）向源 Storage 拉取 binlog，根据 binlog 中的操作在本地执行（上传文件则从源 Storage 拉取文件内容，删除文件则删除本地文件）。
3. **同步位点**：每个 Storage 记录已同步到的 binlog 位点（文件名 + 偏移量），下次同步从该位点继续，保证不丢不重。

**binlog 文件**：
- binlog 存储在 Storage 的数据目录下，如 `/data/fastdfs/storage/data/sync/`。
- binlog 按大小滚动（默认 100MB），命名如 `binlog.000001`、`binlog.000002`。
- binlog 保留一定时间后自动清理（可配置 `binlog_disk_space` 或保留天数）。

**同步的特点**：
- **异步同步**：文件上传到一个 Storage 后立即返回客户端，其他 Storage 异步同步，因此同组内 Storage 之间存在短暂的数据不一致窗口（通常毫秒到秒级）。
- **最终一致**：只要 Storage 在线，最终会同步到一致状态。
- **同步优先级**：可配置同步源的优先级，优先从最近的/负载低的 Storage 同步。
- **断点续传**：同步中断后恢复时，从上次位点继续，不需要全量同步。

配置项：
```ini
# storage.conf
sync_interval = 1                 # 同步间隔（秒）
sync_start_time = 00:00           # 同步开始时间
sync_end_time = 23:59             # 同步结束时间
sync_binlog_buff_size = 256KB     # binlog 缓冲区大小
```

---

## 8. 水平扩容与负载均衡

FastDFS 的水平扩容通过**增加组（group）**实现：

**增加新组**：
1. 部署新的 Storage 节点，配置新的组名（如 group2）。
2. 新组的 Storage 启动后向 Tracker 注册，Tracker 感知到新组。
3. 后续上传文件时，Tracker 的 `store_lookup=2`（剩余空间最大的组）策略会自动将新文件分配到空间充足的新组。
4. 旧组的文件不会自动迁移到新组（FastDFS 不支持自动再平衡），新组只存新上传的文件。

**组内增加副本**：
1. 在已有组中增加新的 Storage 节点，配置相同的组名。
2. 新 Storage 启动后，从同组其他 Storage 全量同步已有文件（通过 binlog + 文件拉取）。
3. 同步完成后，新 Storage 正常服务，组内副本数增加。

**负载均衡**：
- **上传负载**：Tracker 根据 `store_lookup` 和 `store_server` 策略选择组和 Storage，可配置轮询或剩余空间优先。
- **下载负载**：Tracker 根据 `download_server` 策略选择 Storage，可配置轮询。
- **Storage 多路径**：单个 Storage 配置多个 store_path（多块磁盘），路径间轮询或按剩余空间分配。
- **前端负载均衡**：Nginx + fastdfs-nginx-module 部署在每个 Storage 上，前面挂 LVS/HAProxy/Nginx 负载均衡，实现下载请求的负载均衡和高可用。

**扩容注意事项**：
- FastDFS 不支持自动数据再平衡，增加新组后旧组数据不会迁移。如果旧组空间不足，需要手动迁移或增加旧组的存储容量（增加 store_path 磁盘）。
- 组内增加 Storage 时，全量同步会占用大量带宽和 IO，建议在低峰期操作，并限制同步速度。
- 新增组后，客户端上传的文件可能分布在不同组，文件 ID 的 group 字段不同，客户端需正确处理（文件 ID 已包含 group 信息，下载时自动路由）。

---

## 9. 集群部署配置

### 9.1 环境准备与安装

```bash
# WSL Ubuntu 24.04 实跑：安装依赖
sudo apt-get update
sudo apt-get install -y build-essential libpcre3 libpcre3-dev zlib1g-dev openssl libssl-dev

# 下载并安装 libfastcommon（FastDFS 依赖的公共库）
git clone https://github.com/happyfish100/libfastcommon.git
cd libfastcommon
./make.sh
sudo ./make.sh install
cd ..

# 下载并安装 FastDFS
git clone https://github.com/happyfish100/fastdfs.git
cd fastdfs
./make.sh
sudo ./make.sh install
cd ..

# 安装 fastdfs-nginx-module（Nginx 集成模块）
git clone https://github.com/happyfish100/fastdfs-nginx-module.git
```

安装后配置文件在 `/etc/fdfs/`，可执行文件在 `/usr/bin/`，服务脚本在 `/etc/init.d/`。

### 9.2 Tracker 配置

```ini
# /etc/fdfs/tracker.conf
# 基础配置
disabled = false                    # 是否禁用（false=启用）
bind_addr = 0.0.0.0                 # 绑定地址（0.0.0.0=所有网卡）
port = 22122                         # Tracker 服务端口
connect_timeout = 30                 # 连接超时（秒）
network_timeout = 60                 # 网络超时（秒）

# 存储路径（Tracker 的数据和日志）
base_path = /data/fastdfs/tracker   # Tracker 数据目录（需提前创建）

# 日志
log_level = info                     # 日志级别
run_by_group = fastdfs              # 运行用户组
run_by_user = fastdfs               # 运行用户

# 存储服务器管理
store_lookup = 2                     # 上传选组策略：0=轮询, 1=指定组, 2=剩余空间最大
store_group = group1                 # store_lookup=1 时的指定组
store_server = 0                     # 组内选 Storage 策略：0=轮询, 1=IP排序第一, 2=优先级
store_path = 0                       # 选存储路径策略：0=轮询, 1=剩余空间最大
download_server = 0                  # 下载选 Storage 策略：0=轮询, 1=IP排序第一

# 保留空间
reserved_storage_space = 10%         # 保留存储空间（达到阈值后该组不再上传）

# 心跳与超时
storage_sync_file_max_delay = 86400  # Storage 同步最大延迟（秒）
storage_sync_file_max_time = 300     # 同步单个文件最大时间（秒）
storage_delayed_sync_file_max_delay = 86400

# 日志轮转
log_file_rotate = true               # 是否轮转日志
log_file_rotate_size = 200MB         # 日志轮转大小
log_file_rotate_time = 00:00         # 日志轮转时间
```

### 9.3 Storage 配置

```ini
# /etc/fdfs/storage.conf
# 基础配置
disabled = false
group_name = group1                   # 组名（同组 Storage 配置相同）
bind_addr = 0.0.0.0
client_bind = true                    # 是否绑定地址连接 Tracker
port = 23000                           # Storage 服务端口
connect_timeout = 30
network_timeout = 60

# 存储路径
base_path = /data/fastdfs/storage    # Storage 数据目录（日志、binlog 等）
store_path_count = 2                  # 存储路径数量（磁盘数）
store_path0 = /data/fastdfs/storage0 # 第一个存储路径
store_path1 = /data/fastdfs/storage1 # 第二个存储路径

# Tracker 地址（多个 Tracker 用逗号分隔或多行）
tracker_server = 192.168.1.10:22122
tracker_server = 192.168.1.11:22122

# 心跳
heart_beat_interval = 30              # 心跳间隔（秒）
stat_report_interval = 60             # 状态上报间隔（秒）

# 磁盘
disk_max_usage = 0.90                 # 磁盘最大使用率（超过后不再上传）
disk_min_free_space = 1GB             # 磁盘最小剩余空间

# 同步
sync_interval = 1                      # 同步间隔（秒）
sync_start_time = 00:00
sync_end_time = 23:59
sync_binlog_buff_size = 256KB

# 去重
check_file_duplicate = 0              # 是否开启去重（0=关闭）

# 文件路径
subdir_count_per_path = 256           # 每级目录数（256=00~FF）

# 日志
log_level = info
run_by_group = fastdfs
run_by_user = fastdfs
```

### 9.4 启动与验证

```bash
# 创建数据目录
sudo mkdir -p /data/fastdfs/tracker
sudo mkdir -p /data/fastdfs/storage
sudo mkdir -p /data/fastdfs/storage0
sudo mkdir -p /data/fastdfs/storage1
sudo chown -R fastdfs:fastdfs /data/fastdfs

# 启动 Tracker
sudo /etc/init.d/fdfs_trackerd start
# 或 sudo systemctl start fdfs_trackerd

# 启动 Storage
sudo /etc/init.d/fdfs_storaged start

# 验证进程
ps aux | grep fdfs

# 查看 Tracker 日志
tail -f /data/fastdfs/tracker/logs/trackerd.log

# 查看 Storage 日志
tail -f /data/fastdfs/storage/logs/storaged.log

# 查看集群状态（通过 monitor 工具）
fdfs_monitor /etc/fdfs/client.conf
# 输出包含所有 group 和 Storage 的状态、容量、同步状态
```

`fdfs_monitor` 输出示例：
```text
[2026-09-08 10:00:00] DEBUG - base_path=/data/fastdfs/tracker, connect_timeout=30, ...
tracker server count=2
storage server count=4
group count=2

group name: group1
disk total space=1000GB, disk free space=800GB, ...
storage server count=2
        storage 1:
                id=192.168.1.20
                ip_addr=192.168.1.20  ACTIVE
                ...
        storage 2:
                id=192.168.1.21
                ip_addr=192.168.1.21  ACTIVE
                ...

group name: group2
...
```

---

## 10. 与 Nginx 集成提供 HTTP 访问

FastDFS 原生使用私有协议（TCP），不直接提供 HTTP 访问。通过 **fastdfs-nginx-module** 模块，Nginx 可以直接从 FastDFS Storage 读取文件并提供 HTTP 下载服务。

### 10.1 fastdfs-nginx-module 模块

模块工作原理：
1. Nginx 收到 HTTP 请求（URL 路径为文件 ID，如 `/group1/M00/00/00/xxx.jpg`）。
2. fastdfs-nginx-module 解析文件 ID，判断文件是否在本地 Storage。
3. 如果在本地：Nginx 直接从本地磁盘读取文件返回。
4. 如果不在本地（请求落到了同组其他 Storage）：模块通过 FastDFS 协议从源 Storage 拉取文件，缓存到本地后返回（或直接代理转发）。

这样每个 Storage 节点上部署 Nginx + 模块，所有节点都能提供 HTTP 访问，前端挂负载均衡器即可。

### 10.2 Nginx 配置

```nginx
# 编译 Nginx 时添加模块
# ./configure --add-module=/path/to/fastdfs-nginx-module/src

# nginx.conf
user  fastdfs;
worker_processes  auto;

events {
    worker_connections  1024;
}

http {
    include       mime.types;
    default_type  application/octet-stream;

    sendfile        on;
    tcp_nopush      on;
    tcp_nodelay     on;
    keepalive_timeout  65;

    # FastDFS 模块配置
    fastdfs_tracker_server 192.168.1.10:22122;
    fastdfs_tracker_server 192.168.1.11:22122;
    fastdfs_connect_timeout 30;
    fastdfs_network_timeout 60;
    fastdfs_anti_steal_token no;       # 防盗链（见下节）
    fastdfs_secret_key FastDFS1234567890;
    fastdfs_url_have_group_name yes;    # URL 中是否包含 group 名

    server {
        listen       8888;
        server_name  _;

        # 根路径重定向或返回默认页
        location / {
            root   html;
            index  index.html index.htm;
        }

        # FastDFS 文件访问路径
        location ~/group([0-9])/M00 {
            ngx_fastdfs_module;          # 启用 fastdfs 模块
        }

        # 错误页
        error_page   500 502 503 504  /50x.html;
        location = /50x.html {
            root   html;
        }
    }
}
```

访问示例：
```text
http://192.168.1.20:8888/group1/M00/00/00/wKgBgV12345.jpg
```

模块配置文件 `/etc/fdfs/mod_fastdfs.conf`：
```ini
[mod_fastdfs]
connect_timeout=30
network_timeout=60
base_path=/data/fastdfs/nginx
load_fdfs_parameters_from_tracker=true
storage_sync_file_max_delay = 86400
use_storage_id = false
storage_ids_filename = storage_ids.conf
tracker_server=192.168.1.10:22122
tracker_server=192.168.1.11:22122
storage_server_port=23000
group_name=group1
url_have_group_name = true
store_path_count=2
store_path0=/data/fastdfs/storage0
store_path1=/data/fastdfs/storage1
log_level=info
```

### 10.3 防盗链与访问控制

FastDFS 支持基于 token 的防盗链：

```ini
# mod_fastdfs.conf
http.anti_steal.check_token = true    # 开启 token 校验
http.anti_steal.secret_key = your_secret_key  # 密钥
http.anti_steal.token_ttl = 600       # token 有效期（秒）
http.anti_steal.fail_url = /forbidden.html  # 校验失败跳转页
```

客户端生成带 token 的 URL：
```text
URL = http://host/group1/M00/00/00/xxx.jpg?token=xxx&ts=1234567890
token = md5(文件ID + secret_key + timestamp)
```

只有知道密钥的客户端才能生成有效 token，防止文件被恶意盗链。token 有有效期，过期后需重新生成。

其他访问控制方式：
- Nginx 层：IP 白名单、Referer 校验、限流（limit_req）。
- 前端 CDN：将文件缓存到 CDN，源站 FastDFS 只对 CDN 开放。
- 私有文件：不直接暴露 FastDFS URL，通过应用层鉴权后重定向或代理下载。

---

## 11. 应用场景：图床与短链服务

### 11.1 图床服务

基于 FastDFS 搭建图床的典型架构：

```text
用户 → 前端/APP → 上传服务 → FastDFS Storage → 返回文件 ID
                                              ↓
用户 → CDN → Nginx(fastdfs-module) → FastDFS Storage → 图片
```

- **上传**：用户上传图片到应用服务，应用服务调用 FastDFS Client 上传到 Storage，获取文件 ID，将文件 ID 和用户信息存入数据库。
- **访问**：图片 URL 为 `https://img.example.com/group1/M00/...jpg`，经过 CDN 缓存，回源到 Nginx + FastDFS。
- **缩略图**：可在 Nginx 层集成 image_filter 模块或 OpenResty + GraphicsMagick 实时生成缩略图，也可上传时由应用服务生成多尺寸图片分别上传。
- **去重**：开启 FastDFS 去重，相同图片只存一份，节省空间。
- **审核**：上传后调用内容审核服务（涉黄/涉政检测），审核不通过则删除文件。

### 11.2 短链服务

短链服务（URL 缩短）的文件存储部分可用 FastDFS：

- 短链跳转数据（短码→长 URL）存在 Redis/MySQL，不需要 FastDFS。
- 但短链服务常附带的**二维码图片、分享预览图、用户上传的文件**可存在 FastDFS。
- 短链访问统计的日志文件可归档到 FastDFS。

### 11.3 其他应用场景

- **附件存储**：OA/CRM/邮箱系统的附件存储，文件 ID 存在业务数据库。
- **视频存储**：短视频/在线教育的视频文件，配合 CDN 分发。FastDFS 适合大文件（视频），上传下载性能好。
- **静态资源源站**：JS/CSS/图片等静态资源的源站，前面挂 CDN。
- **备份归档**：数据库备份、日志归档等大文件的长期存储。

FastDFS 不适合的场景：
- 需要目录结构和文件重命名的场景（FastDFS 文件 ID 是生成的，不支持自定义路径和重命名）。
- 海量小文件（<10KB）场景（FastDFS 每个文件一个 inode，小文件多了 inode 占用大，可考虑合并存储或用其他小文件系统）。
- 需要 POSIX 语义的场景（如直接挂载为文件系统）。

---

## 12. 常见坑与最佳实践

### 12.1 常见坑汇总

| 坑 | 现象 | 原因 | 解决方案 |
|----|------|------|----------|
| Storage 启动失败 | 日志报连接 Tracker 超时 | 防火墙未开放端口、Tracker 地址错误 | 开放 22122/23000 端口，检查 tracker_server 配置 |
| 上传失败报空间不足 | 磁盘还有空间但拒绝上传 | `disk_max_usage` 或 `reserved_storage_space` 阈值达到 | 调整阈值或增加磁盘 |
| 下载 404 | 文件存在但 Nginx 返回 404 | `url_have_group_name` 配置不一致、store_path 配置错误 | 检查 mod_fastdfs.conf 的 url_have_group_name 和 store_path |
| 同组数据不一致 | 不同 Storage 下载到的文件不同 | 同步延迟、binlog 堆积、Storage 曾离线 | 检查同步状态，等待同步完成或手动触发同步 |
| 文件名乱码 | 中文文件名下载后乱码 | 编码问题，FastDFS 内部用 UTF-8 | 确保客户端和 Nginx 都用 UTF-8，Content-Disposition 正确编码 |
| 小文件性能差 | 大量小文件上传慢、磁盘 inode 不足 | 每个文件独立存储，inode 开销大 | 考虑合并小文件、增加磁盘 inode 数量（mkfs 时调整） |
| Tracker 单点 | Tracker 挂了上传下载都失败 | 只部署了一个 Tracker | 部署至少 2 个 Tracker，客户端配置多个地址 |
| 扩容后旧组满 | 新组有空间但旧组满了无法上传 | `store_lookup=0`（轮询）仍会选到满的组 | 用 `store_lookup=2`（剩余空间最大），或手动迁移 |

### 12.2 最佳实践

1. **部署**：
   - Tracker 至少 2 个，分布在不同物理节点，客户端配置所有 Tracker 地址。
   - 每个 group 至少 2 个 Storage（副本），分布在不同物理节点/机架。
   - Storage 用独立数据盘，不与系统盘混用；多块盘配置多个 store_path。
   - 生产环境用万兆网络，Storage 间同步流量大。

2. **配置**：
   - `store_lookup=2`（剩余空间最大的组），自动均衡各组空间。
   - `reserved_storage_space=10%`，保留空间防止磁盘写满。
   - 合理设置 `subdir_count_per_path=256`，两级目录共 65536 个，分散文件。
   - 开启日志轮转，防止日志占满磁盘。

3. **性能**：
   - 大文件上传用异步客户端，避免阻塞。
   - 下载走 CDN，减少回源 FastDFS 的压力。
   - Nginx 开启 sendfile、tcp_nopush，提升文件发送性能。
   - 多 Storage 前端挂负载均衡（LVS/HAProxy/Nginx），实现下载负载均衡。

4. **运维**：
   - 监控 Storage 磁盘使用率、同步状态、在线状态（`fdfs_monitor`）。
   - 定期检查 binlog 同步延迟，避免同步堆积。
   - 扩容在低峰期操作，限制同步速度避免影响业务。
   - 定期备份文件 ID 映射数据（业务数据库中的文件 ID 是访问入口，丢失则无法定位文件）。

5. **安全**：
   - 开启防盗链 token，防止恶意下载。
   - Storage 端口（23000）不对外网开放，只允许内网和 Nginx 访问。
   - Nginx 层配置 IP 白名单、限流、HTTPS。
   - 私有文件通过应用层鉴权，不直接暴露 FastDFS URL。

---

## 13. 快速参考卡片

### 13.1 架构图

```text
                    ┌─────────────┐
                    │   Client    │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌─────────┐  ┌─────────┐  ┌─────────┐
        │ Tracker │  │ Tracker │  │ Tracker │  (调度，对等集群)
        └────┬────┘  └────┬────┘  └────┬────┘
             │              │              │
     ┌───────┴──────────────┴──────────────┴───────┐
     │                                                │
     ▼                                                ▼
┌──────────────┐                              ┌──────────────┐
│   Group1     │                              │   Group2     │
│ ┌──────┐┌──────┐                            │ ┌──────┐┌──────┐
│ │Storage││Storage│  (副本，binlog同步)       │ │Storage││Storage│
│ │ +Nginx││ +Nginx│                            │ │ +Nginx││ +Nginx│
│ └──────┘└──────┘                            │ └──────┘└──────┘
└──────────────┘                              └──────────────┘
```

### 13.2 上传下载流程

**上传**：
```text
Client → Tracker: 查询可用 Storage
Tracker → Client: 返回 group + Storage IP:port + store_path
Client → Storage: 上传文件内容
Storage → Client: 返回 file_id (group1/M00/00/00/xxx.jpg)
Storage → 同组其他 Storage: binlog 异步同步
```

**下载**：
```text
Client → Tracker: 查询 group 内可用 Storage
Tracker → Client: 返回 Storage IP:port
Client → Storage(Nginx): HTTP GET /group1/M00/00/00/xxx.jpg
Storage → Client: 返回文件内容
```

### 13.3 配置项速查

| 配置文件 | 关键配置 | 默认值 | 说明 |
|----------|----------|--------|------|
| tracker.conf | port | 22122 | Tracker 端口 |
| tracker.conf | base_path | - | 数据目录 |
| tracker.conf | store_lookup | 2 | 选组策略（0轮询/1指定/2空间最大） |
| tracker.conf | store_server | 0 | 选 Storage 策略 |
| tracker.conf | reserved_storage_space | 10% | 保留空间 |
| storage.conf | group_name | group1 | 组名 |
| storage.conf | port | 23000 | Storage 端口 |
| storage.conf | base_path | - | 数据目录 |
| storage.conf | store_path_count | 1 | 存储路径数 |
| storage.conf | tracker_server | - | Tracker 地址 |
| storage.conf | heart_beat_interval | 30 | 心跳间隔 |
| storage.conf | sync_interval | 1 | 同步间隔 |
| storage.conf | check_file_duplicate | 0 | 去重开关 |
| mod_fastdfs.conf | tracker_server | - | Tracker 地址 |
| mod_fastdfs.conf | url_have_group_name | false | URL 是否含 group |
| mod_fastdfs.conf | store_path0 | - | 存储路径 |

### 13.4 常用命令

```bash
# 服务管理
/etc/init.d/fdfs_trackerd start/stop/restart
/etc/init.d/fdfs_storaged start/stop/restart

# 集群监控
fdfs_monitor /etc/fdfs/client.conf

# 文件操作（通过 fdfs_test 或 fdfs_upload_file）
fdfs_upload_file /etc/fdfs/client.conf localfile.jpg
# 输出：group1/M00/00/00/xxx.jpg

fdfs_download_file /etc/fdfs/client.conf group1/M00/00/00/xxx.jpg local.jpg
fdfs_delete_file /etc/fdfs/client.conf group1/M00/00/00/xxx.jpg
fdfs_file_info /etc/fdfs/client.conf group1/M00/00/00/xxx.jpg

# 测试
fdfs_test /etc/fdfs/client.conf upload localfile.jpg
fdfs_test /etc/fdfs/client.conf download group1/M00/00/00/xxx.jpg
fdfs_test /etc/fdfs/client.conf delete group1/M00/00/00/xxx.jpg
```

### 13.5 文件 ID 格式

```text
group1 / M00 / 00 / 00 / wKgBgV12345.jpg
  │      │     │    │       │
  │      │     │    │       └── 文件名（base62编码+扩展名）
  │      │     │    └────────── 二级目录（00~FF）
  │      │     └─────────────── 一级目录（00~FF）
  │      └───────────────────── 存储路径（M00=store_path0）
  └──────────────────────────── 组名
```

---

上一篇：《08-Ceph分布式存储.md》
