# virtio 与 vhost 虚拟化

> 本节目标：讲解虚拟化 I/O 的三种模型、virtio 半虚拟化原理与 vring 机制、vhost 后端加速原理，学完后能够理解设备模拟/半虚拟化/设备直通的区别与取舍、掌握 virtqueue 三环结构与前后端通信流程、熟悉 vhost-net/vhost-user 架构、了解 GPA/GVA/HVA/HPA 地址转换、能够对比 virtio 与 SR-IOV/VFIO 直通的性能与灵活性。对应岗位方向：云计算虚拟化、KVM/QEMU 开发、云原生基础设施、网络功能虚拟化（NFV）、高性能虚拟机网络。

> **硬件说明**：virtio/vhost 需 KVM 虚拟化环境及 virtio 驱动，以下内容为原理与官方文档整理，无法在普通环境实跑。

## 本章速览

- [1. 虚拟化 I/O 模型](#1-虚拟化-io-模型)
  - [1.1 设备模拟（QEMU）](#11-设备模拟qemu)
  - [1.2 半虚拟化（virtio）](#12-半虚拟化virtio)
  - [1.3 设备直通（VFIO）](#13-设备直通vfio)
- [2. virtio 原理](#2-virtio-原理)
  - [2.1 virtqueue 与 vring](#21-virtqueue-与-vring)
  - [2.2 前后端通信流程](#22-前后端通信流程)
- [3. virtio 设备模型](#3-virtio-设备模型)
  - [3.1 setmem 与 vring 设置](#31-setmem-与-vring-设置)
  - [3.2 GPA/GVA/HVA/HPA 地址转换](#32-gpgvahvahpa-地址转换)
- [4. vhost 原理](#4-vhost-原理)
  - [4.1 vhost 与 qemu 通信协议](#41-vhost-与-qemu-通信协议)
  - [4.2 vhost/virtio 通信与 recvmsg](#42-vhostvirtio-通信与-recvmsg)
- [5. vhost 后端](#5-vhost-后端)
  - [5.1 内核 vhost-net](#51-内核-vhost-net)
  - [5.2 用户态 vhost-user](#52-用户态-vhost-user)
  - [5.3 vhost 多队列网卡](#53-vhost-多队列网卡)
- [6. tap/tun 设备创建](#6-taptun-设备创建)
- [7. 性能优化](#7-性能优化)
- [8. 与 SR-IOV/VFIO 直通的对比](#8-与-sr-iovvfio-直通的对比)
- [9. 快速参考卡片](#9-快速参考卡片)
- [10. 常见问题与坑](#10-常见问题与坑)

---

## 1. 虚拟化 I/O 模型

虚拟机的 I/O 虚拟化有三种主流模型，各有取舍：

### 1.1 设备模拟（QEMU）

QEMU 纯软件模拟一个真实硬件设备（如 e1000 网卡、IDE 磁盘）：

```text
Guest 驱动（以为操作真实硬件）
    ↓ 读写设备寄存器（VM Exit，陷入 KVM）
QEMU 模拟设备行为（读取数据、模拟中断）
    ↓
Host 真实设备（通过系统调用访问）
```

| 优点 | 缺点 |
| --- | --- |
| 无需 Guest 安装特殊驱动（兼容老系统） | 性能差（每次 IO 都 VM Exit + QEMU 模拟） |
| 设备型号丰富 | CPU 开销大 |

### 1.2 半虚拟化（virtio）

virtio 是一套标准化的半虚拟化 I/O 框架，Guest 安装 virtio 驱动，与 Host 的 virtio 后端通过共享内存（virtqueue）高效通信：

```text
Guest virtio 前端驱动
    ↓ 写 virtqueue（共享内存，无需 VM Exit）
    ↓ 写 kick 寄存器（通知后端，一次 VM Exit）
Host virtio 后端（QEMU 或 vhost）
    ↓ 处理 IO，访问真实设备
    ↓ 写完成到 used ring，注入中断
Guest 驱动处理完成
```

| 优点 | 缺点 |
| --- | --- |
| 性能远优于设备模拟 | 需 Guest 安装 virtio 驱动（主流 Linux/Windows 已内置） |
| 标准化，支持多种设备类型（net/blk/scsi/console...） | 仍有 VM Exit（kick 通知）和中断注入开销 |
| vhost 后端可进一步加速 | - |

### 1.3 设备直通（VFIO）

将 Host 的物理设备直接分配给 Guest，Guest 直接操作硬件，几乎无虚拟化开销：

```text
Guest 驱动直接操作物理设备（通过 IOMMU 映射）
    ↓ DMA 直接访问 Guest 内存（IOMMU 地址转换）
    ↓ 中断直接注入 Guest（MSI-X）
无 Host 参与数据路径
```

| 优点 | 缺点 |
| --- | --- |
| 性能接近裸机 | 设备专属于一个 VM，无法共享（SR-IOV 可解决） |
| 延迟极低 | 需硬件支持 IOMMU（VT-d/AMD-Vi） |
| CPU 近零开销 | 热迁移困难（设备状态需保存/恢复） |

---

## 2. virtio 原理

virtio 由 Rusty Russell 开发，是 OASIS 标准（Virtual I/O Device），定义了一套与设备类型无关的传输机制。

### 2.1 virtqueue 与 vring

virtqueue 是 virtio 的核心数据结构，用于前后端之间传递 IO 请求。vring 是 virtqueue 的环形缓冲区实现，由三部分组成：

```text
vring 结构（在 Guest 物理内存中，前后端共享）：

┌──────────────────────────────────────────────┐
│ 1. Descriptor Table（描述符表）                │
│    数组，每个元素描述一个数据缓冲区             │
│    { addr, len, flags, next }                 │
│    addr: 缓冲区 Guest 物理地址                 │
│    len:  缓冲区长度                            │
│    flags: NEXT(有后续描述符) / WRITE(设备可写)  │
│    next: 下一个描述符索引（链式描述符）         │
├──────────────────────────────────────────────┤
│ 2. Available Ring（可用环）                    │
│    Guest 前端写入，通知后端"有新请求可用"       │
│    { flags, idx, ring[0..n-1] }              │
│    ring[i] = 描述符表索引（指向一个请求链）     │
│    idx: 下一个可用位置                         │
├──────────────────────────────────────────────┤
│ 3. Used Ring（已用环）                         │
│    Host 后端写入，通知前端"请求已处理完成"      │
│    { flags, idx, ring[0..n-1] }              │
│    ring[i] = { id(描述符索引), len(写入长度) } │
│    idx: 下一个完成位置                         │
└──────────────────────────────────────────────┘
```

**请求流程**：
1. Guest 前端在描述符表中填充请求（一个或多个链式描述符）；
2. Guest 将描述符索引写入 Available Ring，更新 idx；
3. Guest 写 kick 寄存器（通知后端有新请求）；
4. Host 后端读取 Available Ring，处理请求（读/写描述符指向的缓冲区）；
5. Host 将完成信息写入 Used Ring，更新 idx；
6. Host 注入中断（vring interrupt）通知 Guest；
7. Guest 前端读取 Used Ring，处理完成。

### 2.2 前后端通信流程

```text
Guest（前端）                    Host（后端）
     │                              │
     │  写描述符表 + Available Ring  │
     │ ──────────────────────────→  │
     │  kick（VM Exit）             │
     │ ──────────────────────────→  │  读取请求，处理 IO
     │                              │  写 Used Ring
     │  中断注入（VM Entry）         │
     │ ←──────────────────────────  │
     │  读取 Used Ring，处理完成     │
     │                              │
```

virtio 支持的设备类型（通过 device ID 区分）：

| ID | 设备 | 说明 |
| --- | --- | --- |
| 1 | virtio-net | 网络设备 |
| 2 | virtio-blk | 块设备 |
| 3 | virtio-console | 控制台 |
| 4 | virtio-rng | 随机数生成器 |
| 5 | virtio-balloon | 内存气球（动态调整 Guest 内存） |
| 7 | virtio-scsi | SCSI 主机 |
| 9 | virtio-9p | 9p 文件系统共享 |
| 10 | virtio-gpu | GPU |
| 11 | virtio-input | 输入设备 |

---

## 3. virtio 设备模型

### 3.1 setmem 与 vring 设置

QEMU 中 virtio 设备的初始化流程：

```text
1. Guest 启动 → QEMU 创建 virtio 设备（virtio-net-pci 等）
2. Guest 内核 virtio 驱动探测设备 → 读取设备特性（features）
3. 协商特性（Guest 选择双方都支持的特性子集）
4. Guest 分配 virtqueue 内存 → 通过寄存器通知 QEMU vring 地址
5. QEMU 调用 setmem（设置 Guest 内存映射）→ 建立 GPA→HVA 映射
6. Guest 启动设备（DRIVER_OK）→ 前后端开始通信
```

QEMU 中关键的 virtio 操作函数：

```c
// 设置 Guest 物理内存映射（GPA → HVA）
void virtio_add_range(void* opaque, uint64_t gpa, uint64_t size,
                      void* hva, bool readonly);

// 设置 vring（Guest 通知 QEMU vring 的 GPA 和大小）
void virtio_queue_set_phys(VirtIODevice* vdev, int n, uint64_t vring_phys);
void virtio_queue_set_num(VirtIODevice* vdev, int n, int num);

// Guest kick 通知（有新请求）
void virtio_queue_notify(VirtIODevice* vdev, int n);

// 后端完成后注入中断
void virtio_irq(VirtIODevice* vdev);
```

### 3.2 GPA/GVA/HVA/HPA 地址转换

虚拟化环境中有四种地址空间，理解它们的关系是理解 virtio/vhost 的关键：

```text
Guest 虚拟地址（GVA, Guest Virtual Address）
    ↓ Guest 页表（CR3）转换
Guest 物理地址（GPA, Guest Physical Address）
    ↓ EPT/NPT（扩展页表，KVM 硬件辅助）转换
Host 物理地址（HPA, Host Physical Address）

Host 虚拟地址（HVA, Host Virtual Address）
    ↓ Host 页表转换
Host 物理地址（HPA）

关键映射：
  GPA → HVA：QEMU 通过内存注册建立映射（virtio_add_range）
  GPA → HPA：KVM 通过 EPT 建立映射（用于设备 DMA）
  HVA → HPA：Host 内核页表
```

| 地址 | 谁使用 | 转换到 | 转换机制 |
| --- | --- | --- | --- |
| **GVA** | Guest 应用/内核 | GPA | Guest 页表 |
| **GPA** | Guest 内核、virtio 描述符 | HPA | EPT/NPT（KVM） |
| **HVA** | QEMU/vhost 进程 | HPA | Host 页表 |
| **HPA** | 物理硬件、DMA | - | 最终物理地址 |

virtio 描述符中的 `addr` 是 GPA，后端（QEMU/vhost）需要将 GPA 转换为 HVA 才能访问数据：
- QEMU 后端：通过 `cpu_physical_memory_map` 将 GPA 映射为 HVA；
- vhost 后端：通过 `vhost_vring_addr` 中的 `user_addr`（HVA）直接访问，QEMU 预先将 GPA→HVA 映射传递给 vhost。

---

## 4. vhost 原理

vhost 是 virtio 后端的加速方案，将数据路径从 QEMU 移到内核（vhost-net）或独立用户态进程（vhost-user），减少 QEMU 参与，降低延迟和 CPU 开销。

### 4.1 vhost 与 qemu 通信协议

QEMU 与 vhost 后端通过 **ioctl（vhost-net）** 或 **Unix domain socket（vhost-user）** 通信，协议消息包括：

```text
vhost 协议消息类型：
  VHOST_GET_FEATURES     获取后端支持的特性
  VHOST_SET_FEATURES     设置协商后的特性
  VHOST_SET_OWNER        设置 vhost 设备所有者（当前进程）
  VHOST_RESET_OWNER      重置所有者
  VHOST_SET_MEM_TABLE    设置 Guest 内存映射表（GPA→HVA）
  VHOST_SET_VRING_NUM    设置 vring 大小
  VHOST_SET_VRING_ADDR   设置 vring 地址（描述符表/可用环/已用环的 HVA）
  VHOST_SET_VRING_BASE   设置 vring 起始索引
  VHOST_SET_VRING_KICK   设置 kick 事件 fd（Guest 通知后端）
  VHOST_SET_VRING_CALL   设置 call 事件 fd（后端通知 Guest 中断）
  VHOST_SET_VRING_ERR    设置错误事件 fd
  VHOST_NET_SET_BACKEND  设置网络后端（tap fd）
```

初始化流程：

```text
QEMU                              vhost 后端
  │  VHOST_SET_OWNER               │
  │ ────────────────────────────→  │
  │  VHOST_GET_FEATURES             │
  │ ←────────────────────────────  │
  │  VHOST_SET_FEATURES             │
  │ ────────────────────────────→  │
  │  VHOST_SET_MEM_TABLE（GPA→HVA） │
  │ ────────────────────────────→  │
  │  每个 vring：                    │
  │  SET_VRING_NUM/ADDR/BASE       │
  │  SET_VRING_KICK（eventfd）      │
  │  SET_VRING_CALL（eventfd）      │
  │ ────────────────────────────→  │
  │  VHOST_NET_SET_BACKEND（tap fd）│
  │ ────────────────────────────→  │
  │  数据路径开始（vhost 独立处理）   │
```

### 4.2 vhost/virtio 通信与 recvmsg

vhost 后端通过 **eventfd** 与 Guest/QEMU 通信：

- **kick fd**：Guest 写 kick 寄存器 → KVM 触发 eventfd → vhost 被唤醒，读取 Available Ring；
- **call fd**：vhost 完成 IO → 写 eventfd → KVM 注入中断到 Guest。

对于 vhost-user（用户态后端），控制消息通过 Unix domain socket 传递，使用 `sendmsg`/`recvmsg` 传递文件描述符（SCM_RIGHTS）：

```c
// vhost-user 接收消息（含 fd 传递）
struct msghdr msg = {0};
struct iovec iov = { .iov_base = &request, .iov_len = sizeof(request) };
char cmsg_buf[CMSG_SPACE(sizeof(int))];  // 用于接收 fd

msg.msg_iov = &iov;
msg.msg_iovlen = 1;
msg.msg_control = cmsg_buf;
msg.msg_controllen = sizeof(cmsg_buf);

recvmsg(sock_fd, &msg, 0);

// 解析附带的 fd（如 kick eventfd、tap fd）
struct cmsghdr* cmsg = CMSG_FIRSTHDR(&msg);
if (cmsg && cmsg->cmsg_level == SOL_SOCKET && cmsg->cmsg_type == SCM_RIGHTS) {
    int fd = *(int*)CMSG_DATA(cmsg);
    // 使用 fd
}
```

数据路径中，vhost 后端用 `epoll` 监听 kick eventfd，被唤醒后轮询 virtqueue 的 Available Ring，处理 IO，完成后写 call eventfd 通知 Guest。

---

## 5. vhost 后端

### 5.1 内核 vhost-net

vhost-net 是 Linux 内核模块，将 virtio-net 的数据路径移到内核线程：

```text
Guest virtio-net 前端
    ↓ kick（VM Exit → KVM → eventfd）
内核 vhost-net 线程（kthread）
    ↓ 读取 virtqueue Available Ring
    ↓ 处理网络包（从 Guest 内存读数据 → 写入 tap 设备）
    ↓ 写 Used Ring → call eventfd → KVM 注入中断
```

| 优点 | 缺点 |
| --- | --- |
| 减少 QEMU 上下文切换 | 内核模块，定制困难 |
| 与 tap 设备天然集成（内核态） | 无法支持自定义后端（如 DPDK） |
| 成熟稳定 | 仍有内核态/用户态切换（tap 设备） |

### 5.2 用户态 vhost-user

vhost-user 允许 virtio 后端运行在独立的用户态进程中，通过 Unix socket 与 QEMU 通信：

```text
QEMU（控制路径）←── Unix socket ──→ vhost-user 后端进程（数据路径）
     │                                    │
     │  传递 kick/call eventfd、tap fd    │
     │                                    │
Guest ←── kick/call eventfd ──→ vhost-user 直接处理 IO
```

典型 vhost-user 后端实现：

| 后端 | 说明 |
| --- | --- |
| **OVS-DPDK** | Open vSwitch with DPDK，用户态虚拟交换机，高性能网络 |
| **Snabb** | 用户态网络工具包，LuaJIT 实现 |
| **VPP** | FD.io 向量包处理，高性能网络栈 |
| **SPDK vhost-user** | SPDK 提供的 virtio-blk/scsi 后端，用户态存储加速 |
| **Cloud Hypervisor** | 轻量 VMM，内置 vhost-user 支持 |

vhost-user 的优势：
- 后端可完全定制（用 DPDK/SPDK 等用户态技术）；
- 数据路径完全在用户态，无内核参与；
- 与 QEMU 解耦，后端可独立升级。

### 5.3 vhost 多队列网卡

virtio-net 支持多队列（multiqueue），每个 vCPU 可绑定独立的 virtqueue：

```text
vCPU 0 → virtqueue 0（TX/RX）→ vhost 线程 0 → tap 队列 0
vCPU 1 → virtqueue 1（TX/RX）→ vhost 线程 1 → tap 队列 1
vCPU 2 → virtqueue 2（TX/RX）→ vhost 线程 2 → tap 队列 2
...
```

多队列的优势：
- 并行处理网络包，提升吞吐；
- 每个 vCPU 处理自己的队列，无锁竞争；
- 配合 RPS（Receive Packet Steering）/RSS 实现硬件级并行。

QEMU 启动参数：
```bash
qemu-system-x86_64 \
  -netdev tap,id=net0,vhost=on,queues=4 \
  -device virtio-net-pci,netdev=net0,mq=on,vectors=10
# queues=4: 4个队列；mq=on: 启用多队列；vectors=10: 中断向量数（2*queues+2）
```

---

## 6. tap/tun 设备创建

tap/tun 是 Linux 内核提供的虚拟网络设备，用户态程序可通过字符设备 `/dev/net/tun` 创建和读写：

```text
tap 设备：工作在二层（以太网帧），用于虚拟机网络（virtio-net 后端）
tun 设备：工作在三层（IP 包），用于 VPN（OpenVPN 等）
```

创建 tap 设备的代码：

```c
#include <linux/if.h>
#include <linux/if_tun.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <string.h>

int create_tap(const char* dev_name) {
    int fd = open("/dev/net/tun", O_RDWR);
    if (fd < 0) return -1;

    struct ifreq ifr = {};
    ifr.ifr_flags = IFF_TAP | IFF_NO_PI;  // TAP 设备，无额外包头
    strncpy(ifr.ifr_name, dev_name, IFNAMSIZ - 1);

    // ioctl 创建设备
    if (ioctl(fd, TUNSETIFF, &ifr) < 0) {
        close(fd);
        return -1;
    }

    // 设置设备所有者（可选，vhost-net 需要）
    ioctl(fd, TUNSETOWNER, getuid());

    // 启用 tap 设备（ip link set dev_name up）
    // 通常通过 ip 命令或 netlink 操作

    return fd;  // 返回的 fd 可读写以太网帧
}
```

```bash
# 命令行创建 tap 设备
ip tuntap add dev tap0 mode tap
ip link set tap0 up
ip addr add 192.168.100.1/24 dev tap0

# QEMU 使用 tap 网络
qemu-system-x86_64 -netdev tap,id=net0,ifname=tap0,script=no,downscript=no \
                    -device virtio-net-pci,netdev=net0
```

---

## 7. 性能优化

| 优化手段 | 说明 |
| --- | --- |
| **vhost 后端** | 数据路径从 QEMU 移到 vhost，减少上下文切换 |
| **多队列（mq）** | 多 vCPU 并行处理，提升吞吐 |
| **vhost-user + DPDK** | 用户态网络栈，完全绕过内核，线速处理 |
| **巨页（HugePage）** | Guest 内存使用 1G/2M 大页，减少 TLB miss，EPT 页表更小 |
| **vCPU 绑定** | 将 vCPU 绑定到固定物理核，避免调度迁移和缓存失效 |
| **中断亲和** | virtio 中断绑定到对应 vCPU 的物理核，减少跨核中断 |
| **零拷贝** | vhost-net 支持零拷贝（guest 内存直接 DMA 到网卡，需 guest 支持） |
| **合并缓冲区** | 大缓冲区减少描述符数量和 kick 次数 |
| **eventfd 轮询** | 高吞吐场景用轮询替代 eventfd 等待（vhost-user 可配置） |

---

## 8. 与 SR-IOV/VFIO 直通的对比

| 维度 | virtio-net（vhost） | SR-IOV VF 直通 |
| --- | --- | --- |
| 性能 | 高（~80-90% 线速） | 接近裸机（~99% 线速） |
| 延迟 | 较低（~20-50μs） | 极低（~5-10μs） |
| 设备共享 | 是（一个物理网卡可虚拟出任意多 virtio 设备） | 有限（取决于 VF 数量，通常 64/128 个） |
| 热迁移 | 支持（virtio 设备状态可保存/恢复） | 困难（需 VF 状态保存，需硬件支持） |
| 网络功能 | 灵活（OVS 可做防火墙、QoS、隧道） | 受限（VF 直接连物理网络，需交换机配合） |
| 硬件要求 | 普通网卡即可 | 需支持 SR-IOV 的网卡 |
| 配置复杂度 | 低 | 中（需在 Host 启用 SR-IOV，创建 VF） |
| 适用场景 | 通用云主机、需要网络功能虚拟化 | 高性能计算、低延迟交易、需要裸机性能 |

选型建议：
- **通用云环境**：virtio + vhost-user/DPDK（灵活性 + 足够性能）；
- **高性能/低延迟场景**：SR-IOV 直通（性能优先）；
- **需要热迁移 + 高性能**：virtio（热迁移友好），或 SR-IOV + 硬件辅助热迁移（如 Intel E810 的 ADQ）。

---

## 9. 快速参考卡片

```text
virtqueue 三环结构：
  Descriptor Table → {addr(GPA), len, flags, next} 描述数据缓冲区
  Available Ring   → Guest 写，通知后端有新请求（idx + ring[]）
  Used Ring        → 后端写，通知 Guest 完成（idx + ring[]{id,len}）

vhost 通信流程：
  QEMU ──ioctl/socket──→ vhost：SET_OWNER → GET/SET_FEATURES
    → SET_MEM_TABLE(GPA→HVA) → SET_VRING_NUM/ADDR/BASE
    → SET_VRING_KICK(eventfd) → SET_VRING_CALL(eventfd)
    → SET_BACKEND(tap fd) → 数据路径启动

地址空间映射：
  GVA ──Guest页表──→ GPA ──EPT──→ HPA
  HVA ──Host页表──→ HPA
  GPA ──QEMU内存映射──→ HVA（vhost 通过 user_addr 直接访问）

三种 I/O 模型：
  设备模拟(QEMU) → 兼容好，性能差
  半虚拟化(virtio) → 需驱动，性能高，vhost 加速
  设备直通(VFIO) → 性能近裸机，不共享，难热迁移

QEMU 启动参数：
  -netdev tap,id=net0,vhost=on,queues=4
  -device virtio-net-pci,netdev=net0,mq=on,vectors=10
  -drive file=disk.img,if=virtio  (virtio-blk)
```

## 10. 常见问题与坑

1. **vhost-net 模块未加载**：`modprobe vhost_net`，确认内核已启用 `CONFIG_VHOST_NET`。QEMU 启动时 `vhost=on` 但模块未加载会回退到 QEMU 模拟，性能下降。
2. **tap 设备权限不足**：QEMU 进程无权限访问 `/dev/net/tun` 或 tap 设备。使用 `vhost=on` 时 QEMU 需能创建 tap，或预先创建并设置 `ifname` + `script=no`。
3. **virtio 驱动未安装**：Guest 内核未启用 `CONFIG_VIRTIO_NET`/`CONFIG_VIRTIO_BLK`，或 Windows Guest 未安装 virtio-win 驱动。设备识别为未知设备。
4. **多队列不生效**：QEMU 启动参数 `mq=on` 但 Guest 未启用多队列（`ethtool -L eth0 combined N`），或 vectors 数量不足（需 `2*queues+2`）。
5. **vhost-user 连接失败**：QEMU 与后端进程的 socket 路径不匹配，或后端未启动。检查 `-chardev socket,path=/tmp/vhost.sock` 路径与后端监听路径一致。
6. **GPA→HVA 映射错误**：vhost 后端访问 Guest 内存时段错误，通常是内存表未正确设置或 Guest 内存未使用 MAP_SHARED。确认 QEMU 的 `-mem-prealloc` 和内存注册正确。
7. **性能瓶颈在 QEMU 而非 vhost**：即使启用 vhost，控制路径和中断注入仍经过 QEMU/KVM。高 PPS 场景下中断注入开销大，可用 vhost-user + DPDK 完全绕过。
8. **巨页未配置导致 TLB miss**：Guest 内存使用普通 4K 页，EPT 页表大，TLB miss 多。使用 `-mem-path /dev/hugepages` 配置巨页。
9. **vCPU 未绑定导致缓存抖动**：vCPU 在物理核间迁移，L1/L2 缓存失效，性能波动。用 `taskset` 或 libvirt 的 `vcpu_pin` 绑定 vCPU 到固定物理核。
10. **SR-IOV VF 数量不足**：网卡创建的 VF 数量有限（如 64 个），超量 VM 无法分配。需评估网卡 VF 上限，或混合使用 virtio 和 SR-IOV。

---

上一篇：《07-SPDK与NVMe用户态存储.md》
下一篇：《09-IOCPWindows完成端口.md》
