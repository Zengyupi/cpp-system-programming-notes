# RDMA 高性能网络

> 本节目标：讲解 RDMA（Remote Direct Memory Access）的原理、三种技术路线、核心概念与 libibverbs 编程接口，学完后能够理解零拷贝/内核旁路/CPU offload 的技术本质、区分 InfiniBand/RoCE/iWARP、掌握 QP/CQ/MR/PD 等核心对象、熟悉单边/双边操作语义、了解 perftest 性能测试方法。对应岗位方向：AI 训练集群网络、分布式存储、HPC 高性能计算、超低延迟交易、高速数据中心。

> **硬件说明**：RDMA 需特定硬件支持（InfiniBand 网卡或支持 RoCE 的以太网网卡 + 无损以太网），以下内容为原理与官方文档整理，无法在普通环境实跑。

## 本章速览

- [1. RDMA 原理](#1-rdma-原理)
  - [1.1 零拷贝、内核旁路、CPU offload](#11-零拷贝内核旁路cpu-offload)
  - [1.2 与传统 TCP/IP 栈对比](#12-与传统-tcpip-栈对比)
- [2. 三种 RDMA 技术](#2-三种-rdma-技术)
- [3. 核心概念](#3-核心概念)
  - [3.1 QP（Queue Pair）](#31-qpqueue-pair)
  - [3.2 CQ（Completion Queue）](#32-cqcompletion-queue)
  - [3.3 WR 与 WC](#33-wr-与-wc)
  - [3.4 MR（Memory Region）与 PD（Protection Domain）](#34-mrmemory-region与-pdprotection-domain)
- [4. libibverbs 编程接口](#4-libibverbs-编程接口)
  - [4.1 设备列表与上下文](#41-设备列表与上下文)
  - [4.2 创建 PD/MR/CQ/QP](#42-创建-pdmrcqqp)
- [5. 单边操作与双边操作](#5-单边操作与双边操作)
  - [5.1 单边操作：RDMA READ/WRITE](#51-单边操作rdma-readwrite)
  - [5.2 双边操作：SEND/RECV](#52-双边操作sendrecv)
- [6. QP 信息交换与 RoCEv2 配置](#6-qp-信息交换与-rocev2-配置)
- [7. 性能测试](#7-性能测试)
- [8. 与 TCP/DPDK 对比及适用场景](#8-与-tcpdpdk-对比及适用场景)
- [9. 快速参考卡片](#9-快速参考卡片)
- [10. 常见问题与坑](#10-常见问题与坑)

---

## 1. RDMA 原理

RDMA 允许一台计算机直接访问另一台计算机的内存，无需双方操作系统内核参与，实现极低延迟和极高吞吐。

### 1.1 零拷贝、内核旁路、CPU offload

```text
传统 TCP/IP 发送路径：
  应用 → write() → 内核 socket 缓冲区 → 协议栈处理(TCP/IP)
    → 网卡驱动 → DMA 到网卡 → 网络
  接收路径：
    网络 → 网卡 → DMA 到内核缓冲区 → 协议栈处理
      → 内核缓冲区 → copy_to_user → 应用缓冲区
  问题：多次内存拷贝、内核态/用户态切换、CPU 参与协议处理

RDMA 路径：
  应用注册内存(MR) → 提交 Work Request 到网卡
    → 网卡直接 DMA 读取应用缓冲区 → 网络
  接收：
    网络 → 网卡直接 DMA 写入对端应用缓冲区（已注册 MR）
    → 完成后写 CQ，应用轮询/事件通知
  优势：零拷贝、无内核参与、CPU 不处理协议
```

三大核心特性：

| 特性 | 说明 |
| --- | --- |
| **零拷贝（Zero Copy）** | 数据直接在应用缓冲区和网卡之间 DMA 传输，无需内核缓冲区中转 |
| **内核旁路（Kernel Bypass）** | 数据路径完全在用户态，无需系统调用，无上下文切换 |
| **CPU offload** | 协议处理（可靠传输、流控、乱序重排）由网卡硬件完成，CPU 零开销 |

### 1.2 与传统 TCP/IP 栈对比

| 维度 | TCP/IP（内核栈） | DPDK（用户态栈） | RDMA |
| --- | --- | --- | --- |
| 内核旁路 | 否 | 是 | 是 |
| 零拷贝 | 否（需 splice/mmap 优化） | 部分（用户态缓冲区直接 DMA） | 是（直接读写远端内存） |
| CPU 参与协议 | 是（内核处理 TCP） | 是（用户态进程处理） | 否（网卡硬件 offload） |
| 延迟 | ~10-50μs | ~5-20μs | ~1-3μs |
| 吞吐 | 受 CPU 限制 | 高（需 CPU 轮询） | 极高（线速，CPU 近零开销） |
| 编程模型 | socket API | 类似 socket + 轮询 | verbs API（内存语义） |
| 硬件要求 | 普通网卡 | 普通网卡 | RDMA 网卡（IB/RoCE/iWARP） |

> 相关阅读：《../13-并发异步与组件/03-用户态协议栈与DPDK.md》（在 `../../09-Linux高性能后台开发/`），DPDK 是用户态网络 IO 的另一条路线，与 RDMA 互补而非替代。

---

## 2. 三种 RDMA 技术

| 技术 | 物理层 | 网络层 | 传输层 | 说明 |
| --- | --- | --- | --- | --- |
| **InfiniBand (IB)** | IB 专用线缆/交换机 | IB 链路层 | IB 传输 | 原生 RDMA，性能最高，需专用 IB 网络设备 |
| **RoCEv1** | 以太网 | 以太网链路层（无 IP） | IB 传输（BTH） | RDMA over Converged Ethernet v1，仅二层，不可路由 |
| **RoCEv2** | 以太网 | IP/UDP | IB 传输（BTH） | RDMA over UDP/IP，可路由，数据中心主流 |
| **iWARP** | 以太网 | TCP/IP | TCP | RDMA over TCP，依赖 TCP 流控，可跨路由，但延迟较高 |

```text
RoCEv2 报文封装：
  以太网头(14B) + IP头(20B) + UDP头(8B) + BTH(12B) +  payload + ICRC(4B)
  UDP 目的端口固定为 4791（RoCEv2 标准端口）
  BTH（Base Transport Header）包含 QP Number、PSN、Opcode 等
```

RoCEv2 需要**无损以太网**（PFC 优先级流控 + ECN 拥塞通知），否则丢包会导致严重性能下降（IB 传输层的 Go-Back-N 重传效率低）。数据中心部署 RoCEv2 需交换机支持 DCQCN 拥塞控制。

---

## 3. 核心概念

### 3.1 QP（Queue Pair）

QP 是 RDMA 通信的基本端点，由一对队列组成：

```text
QP = Send Queue (SQ) + Receive Queue (RQ)

Send Queue：存放发送侧的 Work Request（SEND/RDMA_WRITE/RDMA_READ/ATOMIC）
Receive Queue：存放接收侧的 Work Request（RECV，用于接收 SEND 消息）
```

QP 有四种服务类型（Service Type）：

| 类型 | 可靠性 | 有序性 | 说明 |
| --- | --- | --- | --- |
| **RC（Reliable Connected）** | 可靠 | 有序 | 类似 TCP，一对一连接，最常用 |
| **UC（Unreliable Connected）** | 不可靠 | 有序 | 不保证送达，有序 |
| **UD（Unreliable Datagram）** | 不可靠 | 无序 | 类似 UDP，一对多，用于组播/广播 |
| **RD（Reliable Datagram）** | 可靠 | 无序 | 可靠数据报，较少用 |

QP 状态机：

```text
RESET → INIT → RTR（Ready To Receive）→ RTS（Ready To Send）
  ↑                                    ↓
  └────────── ERROR ←──────────────────┘
```

- **RESET**：刚创建，无资源；
- **INIT**：已分配资源，可投递 RECV；
- **RTR**：已配置对端 QP 信息，可接收数据；
- **RTS**：可发送数据；
- **ERROR**：发生致命错误，需重建。

### 3.2 CQ（Completion Queue）

CQ 是完成队列，存放 Work Completion（WC），通知应用 WR 已完成：

```text
应用提交 WR → SQ/RQ → 网卡处理 → 完成后写 CQ → 应用轮询 CQ 获取 WC
```

- 一个 CQ 可被多个 QP 共享（减少轮询开销）；
- CQ 有大小限制，溢出会导致 CQ overrun 错误；
- 完成通知方式：轮询（ibv_poll_cq，低延迟）或事件（ibv_get_cq_event，省 CPU）。

### 3.3 WR 与 WC

**WR（Work Request）**：应用提交给网卡的工作请求，描述要执行的操作。

**WC（Work Completion）**：网卡完成 WR 后写入 CQ 的完成通知，包含操作结果。

```text
WR 关键字段：
  opcode     → 操作类型（SEND/RDMA_WRITE/RDMA_READ/ATOMIC_CAS...）
  sg_list    → scatter/gather 列表（本地内存地址+长度+lkey）
  num_sge    → sg 数量
  wr_id      → 应用自定义 ID，完成时在 WC 中返回
  // RDMA 操作特有：
  remote_addr → 远端内存地址
  rkey        → 远端内存密钥
  imm_data    → 立即数（SEND 携带的 32 位数据）

WC 关键字段：
  wr_id      → 对应 WR 的 ID
  status     → 完成状态（IBV_WC_SUCCESS 等）
  opcode     → 操作类型
  byte_len   → 接收字节数（RECV 完成时）
  imm_data   → 对端 SEND 携带的立即数
  qp_num     → 来源 QP 编号（UD 模式）
```

### 3.4 MR（Memory Region）与 PD（Protection Domain）

**MR（Memory Region）**：注册到网卡的内存区域，网卡可直接 DMA 访问。注册时网卡获得该内存的物理页表映射（用于 DMA），并返回一个 **lkey/rkey**（本地/远程密钥）：

```text
注册 MR：
  应用调用 ibv_reg_mr(addr, length, access_flags)
  → 内核固定物理页（pin memory），防止换出
  → 网卡获得页表映射
  → 返回 lkey（本地访问用）和 rkey（远端 RDMA 访问用）

访问权限标志：
  IBV_ACCESS_LOCAL_WRITE  → 本地可写
  IBV_ACCESS_REMOTE_WRITE → 远端可 RDMA_WRITE
  IBV_ACCESS_REMOTE_READ  → 远端可 RDMA_READ
  IBV_ACCESS_REMOTE_ATOMIC→ 远端可原子操作
```

> 注册内存会被锁定（pin），不可交换到磁盘，大量注册 MR 会消耗物理内存。使用完需 `ibv_dereg_mr` 释放。

**PD（Protection Domain）**：保护域，是 QP、MR、CQ 的逻辑分组，同一 PD 内的资源可互相关联，提供隔离保护。

---

## 4. libibverbs 编程接口

libibverbs 是 RDMA 应用的标准用户态库（Linux 下为 `libibverbs`，由 rdma-core 提供）。

### 4.1 设备列表与上下文

```c
#include <infiniband/verbs.h>

// 1. 获取设备列表
int num_devices;
struct ibv_device** dev_list = ibv_get_device_list(&num_devices);
// dev_list[0..num_devices-1] 为可用 RDMA 设备

// 2. 打开设备，获取上下文（context）
struct ibv_context* ctx = ibv_open_device(dev_list[0]);
// ctx 是后续所有操作的基础

// 3. 查询设备属性
struct ibv_device_attr dev_attr;
ibv_query_device(ctx, &dev_attr);
// dev_attr.max_qp, max_cq, max_mr_size 等硬件能力

// 4. 查询端口属性（RoCEv2 需配置 GID）
struct ibv_port_attr port_attr;
ibv_query_port(ctx, 1, &port_attr);  // 端口 1
```

### 4.2 创建 PD/MR/CQ/QP

```c
// 创建 PD
struct ibv_pd* pd = ibv_alloc_pd(ctx);

// 注册 MR（应用缓冲区需已分配）
char* buf = aligned_alloc(4096, 1024 * 1024);  // 1MB 对齐缓冲区
struct ibv_mr* mr = ibv_reg_mr(pd, buf, 1024 * 1024,
    IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_WRITE | IBV_ACCESS_REMOTE_READ);
// mr->lkey 用于本地操作，mr->rkey 需交换给对端

// 创建 CQ
struct ibv_cq* cq = ibv_create_cq(ctx, 1024, NULL, NULL, 0);
// 1024 为 CQ 深度（最多存放的 WC 数量）

// 创建 QP
struct ibv_qp_init_attr qp_init_attr = {0};
qp_init_attr.send_cq = cq;
qp_init_attr.recv_cq = cq;
qp_init_attr.qp_type = IBV_QPT_RC;  // 可靠连接
qp_init_attr.cap.max_send_wr = 1024;
qp_init_attr.cap.max_recv_wr = 1024;
qp_init_attr.cap.max_send_sge = 4;
qp_init_attr.cap.max_recv_sge = 4;
struct ibv_qp* qp = ibv_create_qp(pd, &qp_init_attr);
```

QP 状态迁移（需逐步修改属性）：

```c
// RESET → INIT
struct ibv_qp_attr attr = {0};
attr.qp_state = IBV_QPS_INIT;
attr.pkey_index = 0;
attr.port_num = 1;
ibv_modify_qp(qp, &attr, IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT);

// INIT → RTR（需对端 QP 信息）
attr.qp_state = IBV_QPS_RTR;
attr.path_mtu = IBV_MTU_4096;
attr.dest_qp_num = remote_qpn;       // 对端 QP 编号
attr.rq_psn = 0;                      // 接收包起始序列号
attr.ah_attr.dlid = remote_lid;       // 对端 LID（IB）或 GID（RoCE）
attr.ah_attr.port_num = 1;
ibv_modify_qp(qp, &attr, IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU
    | IBV_QP_DEST_QPN | IBV_QP_RQ_PSN);

// RTR → RTS
attr.qp_state = IBV_QPS_RTS;
attr.sq_psn = 0;
ibv_modify_qp(qp, &attr, IBV_QP_STATE | IBV_QP_SQ_PSN);
```

---

## 5. 单边操作与双边操作

### 5.1 单边操作：RDMA READ/WRITE

单边操作中，**远端 CPU 完全不参与**，本地网卡直接读写远端已注册内存：

```text
RDMA WRITE：
  本地提交 WR（含远端地址 remote_addr + rkey + 本地数据）
  → 本地网卡 DMA 读本地数据 → 发送到远端网卡
  → 远端网卡直接 DMA 写入远端内存
  → 远端 CPU 无感知（无需提交 RECV）
  → 本地 CQ 收到完成通知

RDMA READ：
  本地提交 WR（含远端地址 + rkey + 本地接收缓冲区）
  → 本地网卡发送读请求 → 远端网卡 DMA 读远端内存
  → 数据返回 → 本地网卡 DMA 写入本地缓冲区
  → 远端 CPU 无感知
  → 本地 CQ 收到完成通知
```

单边操作需要预先通过带外通道（如 TCP socket）交换：对端 QP 编号、远端内存地址、rkey。

```c
// RDMA WRITE 示例
struct ibv_sge sge = {
    .addr = (uintptr_t)local_buf,
    .length = data_len,
    .lkey = mr->lkey
};
struct ibv_send_wr wr = {0};
wr.wr_id = 1;
wr.opcode = IBV_WR_RDMA_WRITE;
wr.sg_list = &sge;
wr.num_sge = 1;
wr.wr.rdma.remote_addr = remote_buf_addr;  // 对端内存地址
wr.wr.rdma.rkey = remote_rkey;              // 对端 MR 的 rkey
struct ibv_send_wr* bad_wr;
ibv_post_send(qp, &wr, &bad_wr);
```

### 5.2 双边操作：SEND/RECV

双边操作需要双方配合：发送方提交 SEND，接收方必须预先提交 RECV（提供接收缓冲区）：

```text
SEND/RECV 流程：
  接收方预先投递 RECV WR（指定接收缓冲区 + lkey）
  发送方投递 SEND WR（指定发送数据 + lkey）
  → 数据到达对端 → 对端网卡匹配 RECV → DMA 写入接收缓冲区
  → 双方 CQ 各收到一个完成通知
```

SEND 可携带 **立即数（imm_data）**，32 位数据随消息到达，接收方 WC 中可读取，常用于传递消息类型或元数据，无需额外通信。

SEND/RECV 类似传统 socket 的消息语义，适合请求/响应模式；RDMA READ/WRITE 适合大块数据传输（远端 CPU 零开销）。

---

## 6. QP 信息交换与 RoCEv2 配置

QP 创建后，双方需交换以下信息才能建立连接（RC 模式）：

```text
需交换的 QP 信息：
  - QP Number（qp_num）
  - LID（IB 网络）或 GID（RoCEv2 网络）
  - PSN（Packet Sequence Number，发送/接收起始序列号）
  - MR 的 rkey 和远端内存地址（RDMA 操作需要）

交换方式：带外 TCP socket、共享文件、或使用 rdma_cm（RDMA Connection Manager）
```

**RoCEv2 的 GID/MAC/IP 配置**：

RoCEv2 使用 GID（Global Identifier，128 位，类似 IPv6 地址）标识端口。每个 RoCE 端口有多个 GID 条目（对应不同 IPv4/IPv6 地址）：

```bash
# 查看 RoCE 端口的 GID 表
show_gids

# 输出示例：
# DEV   PORT  INDEX  GID                      IPv4        VER
# mlx5_0 1     0      fe80::ec0d:9a03:8b:1c2d  -           v1
# mlx5_0 1     1      0000:0000:0000:0000:...  192.168.1.10 v2
# mlx5_0 1     2      2001:db8::1              -           v2

# RoCEv2 必须使用 GID 类型 v2（基于 UDP/IP）
# 连接时需指定 GID 索引（gid_index）
```

RoCEv2 连接建立时，`ah_attr` 中需设置 `grh`（Global Route Header），包含对端 GID 和本端 GID 索引。

---

## 7. 性能测试

perftest 是 RDMA 标准性能测试工具集（由 OFA 提供）：

```bash
# 带宽测试（服务端）
ib_write_bw -d mlx5_0 -i 1 -F
# 客户端连接服务端 IP
ib_write_bw -d mlx5_0 -i 1 -F <server_ip>

# 常用参数：
# -d <device>   指定 RDMA 设备
# -i <port>     指定端口
# -F            不强制 CPU 频率（避免性能波动）
# -s <size>     消息大小（默认 65536）
# -a            遍历所有消息大小
# -n <iters>    迭代次数
# -q <qp_num>   QP 数量（多 QP 测试）

# 延迟测试
ib_write_lat -d mlx5_0 -i 1 <server_ip>
ib_read_lat  -d mlx5_0 -i 1 <server_ip>
ib_send_lat  -d mlx5_0 -i 1 <server_ip>

# 消息速率测试（小包 PPS）
ib_write_bw -s 64 -q 4  # 64字节小包，4个QP
```

典型性能指标（100Gbps RoCEv2，ConnectX-6）：

| 指标 | 值 |
| --- | --- |
| 带宽（64KB RDMA WRITE） | ~97 Gbps（接近线速） |
| 延迟（64B RDMA WRITE） | ~1.5μs |
| 消息速率（64B，多 QP） | ~100M ops/s |
| CPU 利用率 | <5%（轮询模式下一个核） |

---

## 8. 与 TCP/DPDK 对比及适用场景

| 场景 | 推荐技术 | 原因 |
| --- | --- | --- |
| **AI 训练集群（多机多卡）** | RDMA（RoCEv2/IB） | AllReduce 等集合通信需极低延迟、极高带宽、CPU 零开销 |
| **分布式存储（Ceph/对象存储）** | RDMA 或 DPDK | 高吞吐低延迟，RDMA 更优但硬件成本高 |
| **HPC 超算** | InfiniBand | MPI 点对点通信，IB 生态成熟 |
| **超低延迟交易** | RDMA（IB）或 Solarflare | 微秒级延迟，内核旁路 |
| **通用数据中心网络** | TCP/IP 或 DPDK | 硬件通用，成本低，兼容性好 |
| **跨地域/公网通信** | TCP/IP | RDMA 需无损网络，公网不可用 |

RDMA 的局限性：
- 硬件成本高（RDMA 网卡比普通网卡贵 3-10 倍）；
- RoCEv2 需无损以太网（交换机支持 PFC/ECN/DCQCN），部署运维复杂；
- 编程模型复杂（verbs API 学习曲线陡峭）；
- 内存注册开销大（pin memory），不适合频繁变化的缓冲区；
- 不适合公网/不可靠网络。

---

## 9. 快速参考卡片

```text
verbs API 速查：
  ibv_get_device_list     获取设备列表
  ibv_open_device         打开设备获取 context
  ibv_alloc_pd            创建保护域
  ibv_reg_mr              注册内存（返回 lkey/rkey）
  ibv_dereg_mr            注销内存
  ibv_create_cq           创建完成队列
  ibv_create_qp           创建队列对
  ibv_modify_qp           修改 QP 状态（RESET→INIT→RTR→RTS）
  ibv_post_send           提交发送 WR
  ibv_post_recv           提交接收 WR
  ibv_poll_cq             轮询完成队列
  ibv_req_notify_cq       请求完成事件通知
  ibv_destroy_qp/cq/pd    销毁资源

QP 状态机：RESET → INIT → RTR → RTS（ERROR 需重建）
操作类型：
  单边：RDMA_WRITE / RDMA_READ / ATOMIC_CAS / ATOMIC_FETCH_ADD
  双边：SEND / RECV（SEND 可带 imm_data）

perftest 命令：
  ib_write_bw  写带宽  ib_read_bw   读带宽
  ib_write_lat 写延迟  ib_send_lat  发送延迟
  参数：-d设备 -i端口 -s消息大小 -q QP数 -a遍历大小

三种技术：IB(专用) / RoCEv2(UDP/IP,主流) / iWARP(TCP,可路由)
```

## 10. 常见问题与坑

1. **CQ overrun（完成队列溢出）**：CQ 深度不足或应用未及时 poll_cq，新完成通知丢失。解决：增大 CQ 深度，及时轮询，或使用事件通知。
2. **MR 注册失败（ENOMEM）**：注册内存超过限制（`ulimit -l` 锁定内存限制），需调大 `max locked memory` 或减少注册量。
3. **RoCEv2 丢包导致性能骤降**：未配置无损以太网（PFC/ECN），IB 传输层 Go-Back-N 重传效率极低。必须在交换机配置 PFC 和 DCQCN。
4. **QP 进入 ERROR 状态**：通常因对端 QP 未就绪、PSN 不匹配、MR 权限不足。查看 `ibv_query_qp` 和 dmesg 中的 RDMA 错误，重建 QP。
5. **RDMA READ/WRITE 返回远程访问错误**：rkey 不匹配、远端地址越界、远端 MR 未注册对应权限（REMOTE_READ/REMOTE_WRITE）。检查带外交换的地址和 rkey。
6. **内存未对齐导致性能差**：MR 缓冲区应 4K 对齐，SG 列表地址也应对齐，否则网卡可能拆分操作。
7. **轮询 CQ 占满 CPU**：低延迟场景用轮询（独占一个核），高吞吐场景可用事件通知（`ibv_req_notify_cq`）省 CPU。
8. **多 QP 共享 CQ 导致饥饿**：一个 QP 的大量完成可能淹没 CQ，其他 QP 完成延迟。可按 QP 分组使用不同 CQ。
9. **RoCEv2 GID 索引错误**：连接时必须使用与对端 IP 匹配的 GID 条目（v2 类型），用 `show_gids` 确认。
10. **忘记释放资源**：MR 不注销会导致物理内存持续被锁定；QP/CQ/PD 不销毁会泄漏驱动资源。长期运行程序必须配对释放。

---

上一篇：《05-frp内网穿透.md》　｜　下一篇：《07-SPDK与NVMe用户态存储.md》　｜　模块索引：《../README.md》
