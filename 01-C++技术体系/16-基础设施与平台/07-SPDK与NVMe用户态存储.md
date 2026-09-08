# SPDK 与 NVMe 用户态存储

> 本节目标：讲解 NVMe over PCIe 原理、SPDK（Storage Performance Development Kit）架构与核心组件，学完后能够理解 NVMe 队列对与 Doorbell 机制、掌握 SPDK 内核旁路与轮询模式设计、熟悉 bdev/blobstore/vfs 四层架构、了解 SPDK 异步改造 POSIX API 的实现思路、能够评估 SPDK 对数据库/存储业务的性能收益。对应岗位方向：分布式存储、数据库内核、云原生存储、全闪存储系统、高性能 IO 中间件。

> **硬件说明**：SPDK 需 NVMe SSD 及支持 VFIO 的内核环境，以下内容为原理与官方文档整理，无法在普通环境实跑。

## 本章速览

- [1. NVMe 与 PCIe 原理](#1-nvme-与-pcie-原理)
  - [1.1 NVMe over PCIe](#11-nvme-over-pcie)
  - [1.2 队列对与 Doorbell](#12-队列对与-doorbell)
- [2. SPDK 定位与设计理念](#2-spdk-定位与设计理念)
- [3. SPDK 架构](#3-spdk-架构)
  - [3.1 NVMe 驱动层](#31-nvme-驱动层)
  - [3.2 bdev（块设备层）](#32-bdev块设备层)
  - [3.3 blobstore 与 blob](#33-blobstore-与-blob)
  - [3.4 vfs（虚拟文件系统）](#34-vfs虚拟文件系统)
- [4. NVMe Controller 与 bdev 之间的 RPC](#4-nvme-controller-与-bdev-之间的-rpc)
- [5. vfs 四层结构：异步改造 POSIX 同步 API](#5-vfs-四层结构异步改造-posix-同步-api)
  - [5.1 open/write/read/close 实现](#51-openwritereadclose-实现)
- [6. 性能测试](#6-性能测试)
- [7. 应用场景](#7-应用场景)
- [8. 与传统内核 IO 栈对比、与 DPDK 的关系](#8-与传统内核-io-栈对比与-dpdk-的关系)
- [9. 快速参考卡片](#9-快速参考卡片)
- [10. 常见问题与坑](#10-常见问题与坑)

---

## 1. NVMe 与 PCIe 原理

### 1.1 NVMe over PCIe

NVMe（Non-Volatile Memory express）是专为非易失性存储（NAND Flash、3D XPoint 等）设计的主机控制器接口规范，运行在 PCIe 总线上：

```text
传统 SATA/AHCI 路径：
  应用 → 系统调用 → VFS → ext4 → block layer → SCSI 层 → AHCI 驱动
    → SATA 控制器 → SSD（单队列，深度 32）
  瓶颈：协议栈深、单队列、为 HDD 旋转延迟设计

NVMe 路径：
  应用 → 系统调用 → VFS → 文件系统 → block layer → NVMe 驱动
    → PCIe → NVMe SSD（多队列，深度 64K）
  优势：多队列并行、低延迟、高队列深度、专为 Flash 设计
```

NVMe 关键特性：
- **多队列**：最多 65535 个 I/O 队列，每个队列深度 65535；
- **低延迟**：协议层开销远低于 SCSI/AHCI；
- **并行性**：多核 CPU 可各自使用独立队列，无锁竞争；
- **MSI-X 中断**：每个队列可绑定独立中断，亲和到对应 CPU 核。

### 1.2 队列对与 Doorbell

NVMe 使用**提交队列（Submission Queue, SQ）**和**完成队列（Completion Queue, CQ）**组成队列对：

```text
主机内存                          NVMe 控制器
┌──────────────────┐            ┌──────────────┐
│ Submission Queue │  ←── 写入  │  控制器读取   │
│ (环形缓冲区)      │   SQE      │  (DMA)       │
├──────────────────┤            ├──────────────┤
│ Completion Queue │  写入 →    │  控制器写入   │
│ (环形缓冲区)      │   CQE      │  (DMA)       │
└──────────────────┘            └──────────────┘
       ↑
  Doorbell 寄存器（MMIO）
  主机写 SQ tail Doorbell → 通知控制器有新命令
  主机写 CQ head Doorbell → 通知控制器已处理完成
```

工作流程：
1. 主机在 SQ 中写入命令（SQE，Submission Queue Entry），更新 SQ tail；
2. 主机写 SQ tail Doorbell 寄存器（MMIO 写），通知控制器；
3. 控制器通过 DMA 读取 SQ 中的命令，执行；
4. 控制器完成后通过 DMA 写入 CQ（CQE，Completion Queue Entry），发中断；
5. 主机处理 CQE，更新 CQ head，写 CQ head Doorbell。

> SPDK 的核心优化之一：用**轮询（polling）**替代中断，避免中断上下文切换和延迟抖动；同时在用户态直接操作 Doorbell 寄存器，绕过内核。

---

## 2. SPDK 定位与设计理念

SPDK（Storage Performance Development Kit）是 Intel 开源的用户态存储开发套件，核心目标：**将存储 IO 路径从内核移到用户态，实现极低延迟和极高 IOPS**。

三大设计理念：

| 理念 | 说明 |
| --- | --- |
| **内核旁路（Kernel Bypass）** | NVMe 驱动运行在用户态，通过 VFIO/UIO 直接访问设备，无系统调用 |
| **轮询模式（Polled Mode）** | 用轮询替代中断，避免上下文切换，延迟更稳定（无中断抖动） |
| **无锁（Lockless）** | 每个线程绑定一个 NVMe 队列对，线程间无共享队列，无需锁 |

```text
SPDK 运行模型（Run-to-completion）：
  每个 CPU 核运行一个 SPDK 线程（reactor/poller）
  → 轮询自己的 NVMe 队列（检查 CQ 是否有完成）
  → 处理完成的 IO → 提交新 IO → 写 Doorbell
  → 无中断、无锁、无上下文切换
```

---

## 3. SPDK 架构

SPDK 采用分层架构，从底向上：

```text
┌─────────────────────────────────────────────┐
│              应用层（数据库/存储业务）          │
├─────────────────────────────────────────────┤
│  vfs（虚拟文件系统，异步 POSIX API）          │
├─────────────────────────────────────────────┤
│  blobstore / blob（blob 存储，分配/管理）     │
├─────────────────────────────────────────────┤
│  bdev（块设备抽象层，统一块设备接口）          │
├─────────────────────────────────────────────┤
│  NVMe 驱动（用户态，直接操作硬件）             │
├─────────────────────────────────────────────┤
│  VFIO / UIO（内核模块，提供设备访问通道）      │
└─────────────────────────────────────────────┘
```

### 3.1 NVMe 驱动层

用户态 NVMe 驱动，直接操作 NVMe 控制器寄存器和队列：

```c
// SPDK NVMe 初始化核心流程（简化）
#include "spdk/nvme.h"

// 1. 探测 NVMe 设备
spdk_nvme_probe(NULL, NULL, attach_cb, NULL, NULL);
// attach_cb 在发现每个 NVMe 控制器时调用

// 2. 在 attach_cb 中分配队列对
static bool attach_cb(void* cb_ctx, const struct spdk_nvme_transport_id* trid,
                      struct spdk_nvme_ctrlr* ctrlr,
                      const struct spdk_nvme_ctrlr_opts* opts) {
    // 为每个 CPU 核分配一个 IO 队列对
    qpair = spdk_nvme_ctrlr_alloc_io_qpair(ctrlr, NULL, 0);
    // qpair 绑定到当前线程，后续 IO 通过该 qpair 提交
    return true;
}

// 3. 提交读 IO
spdk_nvme_ns_cmd_read(ns, qpair, lba, buf, lba_count, complete_cb, cb_arg, 0);
// 异步提交，完成时回调 complete_cb

// 4. 轮询完成（在 reactor 循环中）
spdk_nvme_qpair_process_completions(qpair, 0);
// 检查该 qpair 的 CQ，处理所有完成的命令，调用回调
```

### 3.2 bdev（块设备层）

bdev（block device）是 SPDK 的块设备抽象层，统一不同后端存储的接口：

| bdev 类型 | 说明 |
| --- | --- |
| **nvme** | 直接访问 NVMe SSD（最高性能） |
| **malloc** | 内存模拟的块设备（测试用） |
| **aio** |  Linux 异步 IO（访问内核块设备，性能较低） |
| **iscsi** | iSCSI 目标端 |
| **nbd** | 网络块设备 |
| **raid** | RAID 0/1/5/concat |
| **split** | 将一个 bdev 分割为多个 |
| **delay** | 注入延迟（测试用） |

bdev 提供统一的异步 IO 接口：

```c
// bdev 读（异步）
spdk_bdev_read(desc, ch, buf, offset, length, complete_cb, cb_arg);
// desc: bdev 描述符，ch: I/O channel（每线程一个）

// bdev 写
spdk_bdev_write(desc, ch, buf, offset, length, complete_cb, cb_arg);

// 轮询完成（在 reactor 中）
spdk_for_each_channel(...) // 每个 channel 独立轮询
```

### 3.3 blobstore 与 blob

blobstore 是 SPDK 提供的**精简配置的 blob 存储层**，在 bdev 之上管理可变大小的 blob（类似文件）：

```text
blobstore 结构：
  bdev（底层块设备）
    └── blobstore（超级块 + 空闲区域管理）
         ├── blob 1（可变大小，由 cluster 组成）
         ├── blob 2
         └── ...

cluster：blobstore 的分配单元（默认 1MB），类似文件系统的 block
blob：一组 cluster 的集合，支持读写、resize、持久化
```

blobstore 特性：
- 精简配置（thin provisioning）：只在写入时分配 cluster；
- 持久化：blob 元数据存储在 bdev 上，重启可恢复；
- 异步 API：所有操作异步，符合 SPDK 轮询模型；
- 无文件系统开销：不维护目录结构、权限等，专注高性能 blob 存取。

### 3.4 vfs（虚拟文件系统）

vfs 是 SPDK 在 blobstore 之上实现的**类 POSIX 文件系统**，目的是让传统应用（使用 open/read/write/close）无需修改即可运行在 SPDK 上：

```text
应用（POSIX API: open/read/write）
    ↓ （LD_PRELOAD 或直接链接）
SPDK vfs（异步实现，内部转为 blobstore 异步操作）
    ↓
blobstore
    ↓
bdev → NVMe
```

vfs 的核心挑战：**POSIX API 是同步的，而 SPDK 是异步轮询模型**。解决方案见第 5 节。

---

## 4. NVMe Controller 与 bdev 之间的 RPC

SPDK 支持通过 JSON-RPC 管理 NVMe 控制器和 bdev，常用于动态配置和管理：

```bash
# 列出所有 NVMe 控制器
rpc.py bdev_nvme_get_controllers

# 附加 NVMe 设备（创建 bdev）
rpc.py bdev_nvme_attach_controller -b Nvme0 -t PCIe -a 0000:01:00.0

# 列出所有 bdev
rpc.py bdev_get_bdevs

# 创建 malloc bdev（测试用）
rpc.py bdev_malloc_create -b Malloc0 -s 1024 -b 512

# 创建 RAID bdev
rpc.py bdev_raid_create -z 64 -r 0 -b Nvme0n1 Nvme1n1 -n Raid0
```

RPC 框架允许在运行时动态添加/移除设备、创建/删除 bdev，无需重启应用。

---

## 5. vfs 四层结构：异步改造 POSIX 同步 API

SPDK vfs 的核心设计：将同步的 POSIX 文件操作转换为 SPDK 的异步操作，同时保持 API 兼容。

### 5.1 open/write/read/close 实现

```text
四层结构：
  Layer 1: POSIX API 包装层（open/read/write/close 签名兼容）
  Layer 2: 文件描述符管理层（fd → vfs_file 映射）
  Layer 3: 异步操作调度层（将同步调用转为异步 + 轮询等待）
  Layer 4: blobstore 操作层（实际的 blob 读写）
```

**open 实现**：

```c
// 简化的 vfs_open
int vfs_open(const char* path, int flags, mode_t mode) {
    // 1. 路径解析 → 找到对应的 blob
    struct spdk_blob* blob = lookup_blob_by_path(path);
    if (!blob && (flags & O_CREAT)) {
        // 异步创建 blob，同步等待完成
        spdk_blob_create(bs, NULL, 0, blob_create_cb, &ctx);
        wait_for_completion(&ctx);  // 内部轮询 reactor
        blob = ctx.blob;
    }
    // 2. 分配 fd，关联 blob
    int fd = alloc_fd();
    fd_table[fd].blob = blob;
    fd_table[fd].offset = 0;
    return fd;
}
```

**write 实现**：

```c
// 简化的 vfs_write
ssize_t vfs_write(int fd, const void* buf, size_t count) {
    struct vfs_file* f = &fd_table[fd];
    struct io_ctx ctx = { .done = false };

    // 提交异步写（blobstore → bdev → NVMe）
    spdk_blob_write(f->blob, f->ch, buf, f->offset, count,
                     io_complete_cb, &ctx);

    // 同步等待：在当前线程轮询 reactor，直到 IO 完成
    while (!ctx.done) {
        spdk_nvme_qpair_process_completions(f->qpair, 0);
        // 或调用 spdk_thread_poll() 处理所有 poller
    }

    f->offset += count;
    return count;
}
```

**read 实现**与 write 对称，提交异步读后轮询等待。

**关键设计点**：
- 同步 API 内部通过**轮询等待**实现同步语义，不使用条件变量/信号量（避免上下文切换）；
- 每个线程有独立的 I/O channel 和 qpair，无锁；
- `wait_for_completion` 本质是在当前 reactor 上轮询，直到回调被触发；
- 批量操作时可提交多个异步 IO 后统一轮询，提高队列深度和吞吐。

---

## 6. 性能测试

SPDK 提供 fio 插件（`spdk/fio_plugin`），可直接用 fio 测试 SPDK bdev 性能：

```bash
# 编译 fio 插件
cd spdk/examples/bdev/fio_plugin
make

# 运行 fio（使用 SPDK bdev 而非内核块设备）
fio --name=spdk-test --filename=trtype=PCIe traddr=0000.01.00.0 ns=1 \
    --ioengine=./spdk_fio_plugin --direct=1 --rw=randread \
    --bs=4k --iodepth=128 --numjobs=1 --runtime=60 --time_based

# 关键参数：
# --ioengine=spdk_fio_plugin  使用 SPDK 插件
# --filename=trtype=...        指定 NVMe 设备的 PCIe 地址
# --iodepth=128                队列深度（SPDK 可支持更深队列）
# --direct=1                   绕过页缓存
```

典型性能（Intel P4610 NVMe SSD，单盘）：

| 测试项 | 内核 NVMe 驱动 | SPDK 用户态驱动 |
| --- | --- | --- |
| 4K 随机读 IOPS | ~600K | ~800K+ |
| 4K 随机写 IOPS | ~200K | ~300K+ |
| 128K 顺序读带宽 | ~3.2 GB/s | ~3.2 GB/s（带宽受盘限制） |
| 4K 读平均延迟 | ~80μs | ~20μs |
| 4K 读尾延迟（p99） | ~200μs | ~50μs |
| CPU 利用率（每 100K IOPS） | ~1.5 核 | ~0.3 核 |

> SPDK 的优势在**高队列深度、高 IOPS、低延迟、低 CPU 开销**场景最明显；顺序带宽受 SSD 硬件限制，SPDK 与内核驱动差距不大。

---

## 7. 应用场景

| 场景 | 说明 |
| --- | --- |
| **MySQL/PostgreSQL** | 将数据文件放在 SPDK vfs 上，降低 IO 延迟，提升 TPS；需适配异步 IO 接口 |
| **pgvector** | 向量数据库，大量随机读，SPDK 低延迟显著提升查询性能 |
| **RocksDB** | LSM-Tree 存储引擎，compaction 和随机读密集，SPDK 可降低写放大和延迟 |
| **分布式存储（Ceph/Cassandra）** | 存储节点使用 SPDK bdev 替代内核块设备，提升单节点 IOPS |
| **zvfs** | 基于 SPDK vfs 的用户态文件系统，为数据库提供高性能存储抽象 |
| **全闪阵列** | 存储厂商用 SPDK 构建全闪存储系统的数据面 |

> 相关阅读：《../13-并发异步与组件/02-io_uring与异步IO.md》（在 `../../09-Linux高性能后台开发/`），io_uring 是内核异步 IO 的新接口，与 SPDK 用户态路线形成对比。

---

## 8. 与传统内核 IO 栈对比、与 DPDK 的关系

### 与传统内核 IO 栈对比

| 维度 | 内核 NVMe 驱动 | SPDK 用户态驱动 |
| --- | --- | --- |
| IO 路径 | 系统调用 → block layer → 驱动 → 硬件 | 用户态直接操作硬件寄存器 |
| 中断 | 中断通知完成 | 轮询完成 |
| 锁 | 多队列但 block layer 有锁 | 每线程独立队列，无锁 |
| 内存拷贝 | 无（O_DIRECT），但有页缓存路径 | 无，直接 DMA 到用户缓冲区 |
| 延迟 | 较高（系统调用+中断） | 极低 |
| CPU 开销 | 较高（中断处理、内核线程） | 极低（轮询占一个核） |
| 兼容性 | 所有应用可用 | 需适配 SPDK API 或使用 vfs |
| 易用性 | 高（文件系统即插即用） | 低（需绑定 CPU、大页、VFIO 配置） |

### 与 DPDK 的关系

SPDK 和 DPDK 是**互补关系**，共享底层技术：

| 维度 | DPDK | SPDK |
| --- | --- | --- |
| 领域 | 网络数据包处理 | 存储 IO 处理 |
| 硬件 | 网卡 | NVMe SSD |
| 内核旁路 | 是（UIO/VFIO） | 是（UIO/VFIO） |
| 轮询模式 | 是 | 是 |
| 大页内存 | 是 | 是（复用 DPDK 的内存管理） |
| CPU 绑定 | 是 | 是 |
| 共享组件 | - | SPDK 复用 DPDK 的 env 层（内存、CPU 亲和、大页） |

SPDK 早期依赖 DPDK 的环境抽象层（EAL），后来 SPDK 实现了独立的 env 层，但仍可与 DPDK 共存（同一应用同时处理网络和存储）。

---

## 9. 快速参考卡片

```text
SPDK 组件图：
  应用 → vfs(POSIX异步) → blobstore(blob分配) → bdev(块抽象) → NVMe驱动 → VFIO → SSD

NVMe 寄存器速查：
  SQ0TDBL   管理提交队列 tail doorbell
  CQ0HDBL   管理完成队列 head doorbell
  SQyTDBL   IO 提交队列 tail doorbell（y = qid*2）
  CQyHDBL   IO 完成队列 head doorbell
  写 SQ tail → 通知控制器取命令；写 CQ head → 通知已处理完成

性能测试命令：
  fio --ioengine=spdk_fio_plugin --filename=trtype=PCIe traddr=0000.01.00.0 ns=1
      --rw=randread --bs=4k --iodepth=128 --direct=1

SPDK 启动配置：
  大页：echo 4096 > /proc/sys/vm/nr_hugepages
  VFIO：modprobe vfio-pci；绑定设备：scripts/setup.sh
  CPU 绑定：--main-core 0 --core-mask 0xF（每个核一个 reactor）

bdev 类型：nvme(最高性能) / malloc(测试) / aio(内核设备) / raid / split / iscsi
```

## 10. 常见问题与坑

1. **VFIO 设备绑定失败**：内核未启用 VFIO（`CONFIG_VFIO`），或设备仍被内核驱动占用。需先用 `scripts/setup.sh` 解绑内核驱动并绑定 vfio-pci。
2. **大页内存不足**：SPDK 需大量大页内存（DMA 缓冲区），`nr_hugepages` 设置不足会导致初始化失败。根据设备数量和队列深度调整。
3. **轮询占满 CPU 核**：SPDK reactor 轮询会 100% 占用绑定的 CPU 核，这是正常的（用 CPU 换低延迟）。需合理规划 CPU 核，避免与应用线程竞争。
4. **IO 超时/完成队列空**：未在 reactor 循环中调用 `spdk_nvme_qpair_process_completions`，导致完成的 IO 未被处理。必须确保每个 qpair 定期被轮询。
5. **多线程访问同一 qpair 崩溃**：qpair 不是线程安全的，每个 qpair 只能由创建它的线程使用。多线程需各自分配 qpair 或使用 I/O channel。
6. **blobstore 元数据损坏**：异常断电可能导致 blobstore 元数据不一致，需使用 write-back cache 或定期 sync。生产环境建议有掉电保护（PLP）的 SSD。
7. **vfs 单线程性能瓶颈**：vfs 的同步 API 内部轮询等待，单线程队列深度低。应使用多线程/多 fd 并发，或直接使用异步 API。
8. **NVMe 设备被内核同时访问**：设备绑定 vfio-pci 后，内核不能再访问（如挂载文件系统），否则冲突。确保设备未被内核驱动持有。
9. **MSI-X 中断未生效**：SPDK 轮询模式下不使用中断，但某些场景（如事件通知）需配置。确认设备支持 MSI-X 且内核已启用。
10. **性能未达预期**：检查是否使用了 O_DIRECT、队列深度是否足够、CPU 是否绑定、是否有内核线程干扰。用 `spdk_top` 工具监控各 reactor 的 IOPS 和延迟。

---

上一篇：《06-RDMA高性能网络.md》
下一篇：《08-virtio与vhost虚拟化.md》
