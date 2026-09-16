# eBPF 可观测性技术

> 本节目标：建立 eBPF（extended Berkeley Packet Filter）的可观测性技术体系——理解 BPF 虚拟机与程序类型、掌握 bpftrace 一行命令与脚本编写、熟悉 BCC 工具集的常用排查工具、能够用 eBPF 做网络与应用层观测。与《../07-调试与测试/03-perf性能剖析.md》互补：perf 是采样型（每隔一段时间看一眼），eBPF 是事件驱动型（每次事件触发都记录），两者结合是现代 Linux 性能分析的标准组合。网络抓包基础见《02-tcpdump网络抓包.md》，性能分析方法论见《../15-中间件与微服务/04-性能分析与调优.md》。eBPF 需内核 4.9+，部分功能需 5.x+；WSL2 内核默认未开启完整 BPF 功能，以下命令标注来源，生产环境 Ubuntu 22.04+（内核 5.15+）可直接运行。

## 本章速览

- [0. eBPF 是什么](#0-ebpf-是什么)
- [1. eBPF 原理](#1-ebpf-原理)
- [2. bpftrace](#2-bpftrace)
- [3. BCC 工具集](#3-bcc-工具集)
- [4. 网络观测](#4-网络观测)
- [5. 应用层观测](#5-应用层观测)
- [6. eBPF 与 perf 的对比](#6-ebpf-与-perf-的对比)
- [7. 快速参考卡片](#7-快速参考卡片)
- [8. 常见问题与坑](#8-常见问题与坑)

---

## 0. eBPF 是什么

eBPF 是 Linux 内核中的一个**虚拟机**，允许用户在不修改内核源码、不加载内核模块的情况下，在内核中运行沙箱化的小程序。这些程序可以挂载到内核的各种事件点（函数调用、网络包、跟踪点等），在事件发生时执行自定义逻辑。

一句话概括：**eBPF = 内核中的 JavaScript**——安全、沙箱、事件驱动、热加载。

| 能力 | 传统方式 | eBPF 方式 |
| --- | --- | --- |
| 跟踪内核函数 | 加载内核模块（kprobe），有 panic 风险 | BPF 程序 + verifier 验证，安全 |
| 网络包处理 | 内核模块 / iptables / tcpdump（复制到用户态） | XDP（网卡驱动层）/ socket filter，零拷贝 |
| 应用函数跟踪 | gdb 附加（暂停进程）/ 插桩重新编译 | uprobe（运行时附加，不停进程） |
| 性能分析 | perf 采样（有采样误差） | 事件驱动（每次事件都记录，无遗漏） |

eBPF 的典型应用场景：可观测性（bcc/bpftrace）、网络（Cilium、Calico eBPF 数据面）、安全（Falco、Tracee）、性能分析（py-spy、parca）。

---

## 1. eBPF 原理

### 1.1 BPF 虚拟机与 verifier

eBPF 程序的执行流程：

```text
用户态 C/Rust/Python 代码
    │  编译为 BPF 字节码（clang -target bpf）
    ▼
BPF 字节码
    │  加载到内核（bpf() 系统调用）
    ▼
verifier（验证器）
    │  检查：不会崩溃、不会无限循环、有界内存访问、类型安全
    │  不通过 → 拒绝加载（返回错误）
    ▼
JIT 编译器
    │  字节码 → 原生机器码（x86_64/ARM64）
    ▼
挂载到探针点（kprobe/tracepoint/XDP...）
    │  事件触发时执行
    ▼
通过 map 与用户态通信
```

**verifier 是 eBPF 安全的核心**：它对 BPF 字节码做静态分析，确保程序：
- 不会访问非法内存（有界指针、空指针检查）
- 不会无限循环（所有循环有界，或 5.3+ 支持有界循环）
- 不会泄露内核地址（指针运算受限）
- 指令数有上限（早期 4096 条，5.2+ 提升到 100 万条）

### 1.2 map 数据结构

map 是 eBPF 程序与用户态通信的唯一方式，也是 BPF 程序之间共享数据的方式。map 是内核中的键值对存储，用户态通过 `bpf()` 系统调用读写。

| map 类型 | 用途 | 典型场景 |
| --- | --- | --- |
| `BPF_MAP_TYPE_HASH` | 哈希表 | 统计按 IP/端口/PID 的计数 |
| `BPF_MAP_TYPE_ARRAY` | 数组 | 计数器、配置参数 |
| `BPF_MAP_TYPE_PERCPU_HASH` | 每 CPU 哈希 | 无锁高性能统计（每个 CPU 独立计数，用户态汇总） |
| `BPF_MAP_TYPE_PERCPU_ARRAY` | 每 CPU 数组 | 高性能计数器 |
| `BPF_MAP_TYPE_RINGBUF` | 环形缓冲区 | 事件输出到用户态（替代 perf buffer，5.8+） |
| `BPF_MAP_TYPE_PERF_EVENT_ARRAY` | perf 事件数组 | 事件输出（传统方式） |
| `BPF_MAP_TYPE_STACK_TRACE` | 栈跟踪 | 存储调用栈 |
| `BPF_MAP_TYPE_LRU_HASH` | LRU 哈希 | 连接跟踪（自动淘汰旧条目） |

> **性能关键**：统计类场景用 `PERCPU` map 避免锁竞争；事件输出用 `RINGBUF`（5.8+）替代 `PERF_EVENT_ARRAY`，减少内存拷贝和丢失。

### 1.3 程序类型对照表

eBPF 程序必须指定类型，类型决定了程序能挂载到哪里、能访问什么数据、能调用哪些内核辅助函数。

| 程序类型 | 挂载点 | 触发时机 | 典型用途 |
| --- | --- | --- | --- |
| `BPF_PROG_TYPE_KPROBE` | 内核函数入口/返回 | 内核函数被调用 | 跟踪内核函数参数/返回值 |
| `BPF_PROG_TYPE_TRACEPOINT` | 内核静态跟踪点 | 跟踪点触发 | 稳定 ABI 的内核事件跟踪 |
| `BPF_PROG_TYPE_PERF_EVENT` | perf 事件 | 硬件/软件事件 | 性能采样（配合 perf） |
| `BPF_PROG_TYPE_XDP` | 网卡驱动收包路径 | 包到达驱动层 | 高性能包过滤/负载均衡/DDOS 防护 |
| `BPF_PROG_TYPE_SOCKET_FILTER` | socket | socket 收包 | 包过滤（tcpdump 底层） |
| `BPF_PROG_TYPE_SCHED_CLS` | TC（流量控制） | 包进入/离开网络栈 | 流量整形、网络观测 |
| `BPF_PROG_TYPE_CGROUP_SKB` | cgroup | cgroup 内网络包 | cgroup 级网络策略 |
| `BPF_PROG_TYPE_LSM` | LSM hook | 安全检查点 | 安全策略（替代部分 SELinux） |
| `BPF_PROG_TYPE_UPROBE` | 用户态函数 | 用户态函数被调用 | 跟踪应用函数（不需要重新编译） |
| `BPF_PROG_TYPE_RAW_TRACEPOINT` | 原始跟踪点 | 跟踪点触发 | 比 tracepoint 更低开销 |

> **kprobe vs tracepoint**：kprobe 挂载到任意内核函数，但函数名/参数可能随内核版本变化（不稳定）；tracepoint 是内核开发者预留的稳定跟踪点，ABI 稳定，优先用 tracepoint。

---

## 2. bpftrace

### 2.1 简介与安装

bpftrace 是 eBPF 的高级追踪语言，语法类似 awk/DTrace，一行命令就能完成复杂的内核跟踪。它是 BCC 工具的"前端简化版"，适合快速排查和一行命令。

```bash
# Ubuntu 22.04+
apt install bpftrace bpfcc-tools linux-headers-$(uname -r)

# 验证
bpftrace -e 'BEGIN { printf("bpftrace works\n"); }'
```

> WSL2 默认内核未开启 `CONFIG_BPF_KPROBE_OVERRIDE` 等选项，且缺少内核头文件，bpftrace 可能无法运行；以下命令来自 bpftrace 官方工具集（iovisor/bpftrace）和 BCC 文档，在原生 Ubuntu 22.04+（内核 5.15+）上可直接运行。

### 2.2 语法基础

bpftrace 程序结构：`探针类型:探针点:函数名 { 动作 }`

```bash
# 探针类型
kprobe:vfs_read          # 内核函数入口（kprobe）
kretprobe:vfs_read       # 内核函数返回（kretprobe）
tracepoint:syscalls:sys_enter_read   # 静态跟踪点
uprobe:/bin/bash:readline            # 用户态函数
profile:hz:99            # 定时采样（99Hz，避免与周期任务对齐）
interval:s:1             # 每 1 秒触发
BEGIN / END              # 程序开始/结束
```

常用内置变量：

| 变量 | 含义 |
| --- | --- |
| `pid` | 进程 ID |
| `tid` | 线程 ID |
| `comm` | 进程名 |
| `uid` | 用户 ID |
| `cpu` | CPU 核号 |
| `nsecs` | 当前时间（纳秒） |
| `arg0`-`arg8` | 函数参数（kprobe） |
| `retval` | 返回值（kretprobe） |
| `args` | tracepoint 的参数结构体 |

### 2.3 常用一行命令

```bash
# 1. 统计哪个进程在执行 vfs_read（按进程名计数）
bpftrace -e 'kprobe:vfs_read { @[comm] = count(); }'

# 2. 跟踪进程打开的文件（execsnoop 等价）
bpftrace -e 'tracepoint:syscalls:sys_enter_openat { printf("%s %s\n", comm, str(args->filename)); }'

# 3. 统计 TCP 发送字节数（按目标 IP）
bpftrace -e 'kprobe:tcp_sendmsg { @[arg1] = sum(arg3); } interval:s:5 { print(@); clear(@); }'

# 4. 采样 CPU 调用栈（99Hz，找 CPU 热点）
bpftrace -e 'profile:hz:99 { @[kstack] = count(); }'

# 5. 跟踪进程创建（execsnoop）
bpftrace -e 'tracepoint:sched:sched_process_exec { printf("%d %s\n", pid, comm); }'

# 6. 统计块设备 IO 延迟分布
bpftrace -e 'kprobe:blk_account_io_start { @start[arg0] = nsecs; } kretprobe:blk_account_io_done /@start[arg0]/ { @usecs = hist((nsecs - @start[arg0])/1000); delete(@start[arg0]); }'

# 7. 跟踪哪个进程在分配内存（kmalloc 按大小统计）
bpftrace -e 'kprobe:kmalloc { @[comm] = sum(arg1); } interval:s:5 { print(@); clear(@); }'

# 8. 跟踪 TCP 连接建立（按目标 IP:端口）
bpftrace -e 'kprobe:tcp_v4_connect { printf("%s -> %pI4:%d\n", comm, arg1+4, arg2); }'
```

### 2.4 脚本编写

复杂逻辑写成 `.bt` 脚本文件：

```bash
#!/usr/bin/env bpftrace
// tcpconnlat.bt — 统计 TCP 连接建立延迟（从 SYN 到 ESTABLISHED）

#include <net/sock.h>
#include <net/tcp.h>

kprobe:tcp_v4_connect
{
    @start[tid] = nsecs;
    @daddr[tid] = arg1;
    @dport[tid] = arg2;
}

kretprobe:tcp_v4_connect
/@start[tid]/
{
    $elapsed = (nsecs - @start[tid]) / 1000;  // 微秒
    @connlat_us = hist($elapsed);
    delete(@start[tid]);
    delete(@daddr[tid]);
    delete(@dport[tid]);
}

interval:s:10
{
    printf("TCP 连接建立延迟分布（微秒）:\n");
    print(@connlat_us);
    clear(@connlat_us);
}
```

运行：`bpftrace tcpconnlat.bt`

---

## 3. BCC 工具集

BCC（BPF Compiler Collection）是 eBPF 工具的标准库，包含几十个开箱即用的排查工具，安装后直接命令行调用。

```bash
apt install bpfcc-tools linux-headers-$(uname -r)
# 工具在 /usr/sbin/ 下，以 -bpfcc 后缀（如 execsnoop-bpfcc）
# 部分发行版有不带后缀的别名
```

### 3.1 进程与文件

| 工具 | 用途 | 典型场景 |
| --- | --- | --- |
| `execsnoop` | 跟踪新进程创建（exec） | 排查"谁在频繁创建短进程"、容器启动慢 |
| `opensnoop` | 跟踪文件打开（open/openat） | 排查"进程在打开哪些文件"、配置文件路径、权限错误 |
| `statsnoop` | 跟踪 stat 系统调用 | 排查频繁 stat 导致的性能问题 |
| `fsslower` | 跟踪慢文件系统操作（>阈值） | 找文件 IO 慢的源头 |
| `filetop` | 文件读写 TOP 排行 | 找读写最频繁的文件 |
| `dcstat` | 目录项缓存（dcache）统计 | 排查 dcache 命中率低 |

```bash
# 跟踪所有新进程（含参数）
execsnoop-bpfcc

# 跟踪某进程打开的文件
opensnoop-bpfcc -p $(pgrep -f my_server)

# 跟踪超过 10ms 的文件操作
fsslower-bpfcc -x 10
```

### 3.2 磁盘 IO

| 工具 | 用途 |
| --- | --- |
| `biosnoop` | 跟踪每个块设备 IO 请求（进程、扇区、大小、延迟） |
| `biolatency` | 块设备 IO 延迟分布直方图 |
| `biotop` | 块设备 IO TOP 进程 |
| `bitesize` | 按进程统计 IO 请求大小分布 |
| `writeback` | 跟踪页写回（flush）事件 |

```bash
# 每个 IO 的详细信息
biosnoop-bpfcc

# IO 延迟分布
biolatency-bpfcc -mF    # -m 毫秒，-F 含标志位

# IO TOP 进程
biotop-bpfcc
```

### 3.3 网络

| 工具 | 用途 |
| --- | --- |
| `tcplife` | TCP 连接生命周期（PID、本地/远端地址端口、字节数、持续时间） |
| `tcptop` | TCP 流量 TOP 进程（按发送/接收字节） |
| `tcpconnect` | 跟踪主动 TCP 连接（connect） |
| `tcpaccept` | 跟踪被动 TCP 连接（accept） |
| `tcpclose` | 跟踪 TCP 连接关闭 |
| `tcpretrans` | 跟踪 TCP 重传（哪个连接、重传原因） |
| `tcpsynbl` | TCP SYN backlog 统计（排查连接队列满） |
| `sofamily` | socket 创建统计（协议族分布） |

```bash
# 所有 TCP 连接的生命周期
tcplife-bpfcc

# TCP 流量 TOP（每 5 秒刷新）
tcptop-bpfcc -C 5

# 跟踪重传
tcpretrans-bpfcc

# SYN 队列溢出检测
tcpsynbl-bpfcc
```

### 3.4 内存与 CPU

| 工具 | 用途 |
| --- | --- |
| `memleak` | 内存泄漏检测（跟踪 malloc/free，找出未释放的分配） |
| `cachestat` | 页缓存命中率统计 |
| `cachetop` | 页缓存命中 TOP 进程 |
| `runqlat` | 运行队列延迟（进程等 CPU 的时间） |
| `runqlen` | 运行队列长度 |
| `cpudist` | CPU 上运行时间分布（每次调度运行多久） |
| `offcputime` |  off-CPU 时间栈跟踪（进程不在 CPU 上的时间，等锁/IO/睡眠） |
| `profile` | CPU 采样调用栈（类似 perf record） |

```bash
# 内存泄漏检测（跟踪某进程，5 秒间隔）
memleak-bpfcc -p $(pgrep -f my_server) -T 5

# 运行队列延迟分布
runqlat-bpfcc -m    # 毫秒

# off-CPU 栈跟踪（找等锁/IO 的瓶颈）
offcputime-bpfcc -df -p $(pgrep -f my_server) 30
```

> `offcputime` 是 eBPF 相比 perf 的独特优势：perf 擅长 on-CPU 分析（进程在跑什么），eBPF 的 offcputime 能分析 off-CPU（进程在等什么——锁、IO、睡眠），两者结合才能完整定位性能瓶颈。

---

## 4. 网络观测

### 4.1 TCP 连接全生命周期跟踪

用 BCC 工具组合跟踪 TCP 连接的完整生命周期：

```bash
# 1. 谁在主动连（connect）
tcpconnect-bpfcc -t    # -t 显示时间戳

# 2. 谁在被动接受（accept）
tcpaccept-bpfcc -t

# 3. 连接的完整生命周期（建立到关闭）
tcplife-bpfcc -t

# 4. 连接关闭细节
tcpclose-bpfcc -t

# 5. 重传
tcpretrans-bpfcc -l    # -l 显示监听端口
```

### 4.2 bpftrace 统计 TCP 连接

```bash
# 按目标 IP 统计主动连接数
bpftrace -e 'kprobe:tcp_v4_connect { @[arg1] = count(); } interval:s:10 { print(@); clear(@); }'

# 按进程统计 TCP 发送字节
bpftrace -e 'kprobe:tcp_sendmsg { @[comm, pid] = sum(arg3); } interval:s:10 { print(@); clear(@); }'

# TCP 重传计数（按原因）
bpftrace -e 'tracepoint:tcp:tcp_retransmit_skb { @[comm] = count(); } interval:s:5 { print(@); clear(@); }'

# SYN 队列溢出（连接被丢）
bpftrace -e 'tracepoint:tcp:tcp_drop { @[comm, args->state] = count(); } interval:s:5 { print(@); clear(@); }'
```

### 4.3 与 tcpdump 的分工

| 工具 | 视角 | 开销 | 适用场景 |
| --- | --- | --- | --- |
| `tcpdump`（《02-tcpdump网络抓包.md》） | 包级（每个包的完整内容） | 高（包复制到用户态） | 协议分析、内容排查、少量包 |
| eBPF `tcplife`/`tcpconnect` | 连接级（元数据统计） | 低（内核态聚合） | 连接统计、TOP 流量、全量观测 |
| eBPF `tcpretrans` | 事件级（重传事件） | 极低 | 重传定位、网络质量分析 |
| eBPF XDP | 驱动级（包到达即处理） | 极低（零拷贝） | 高性能过滤、DDOS 防护 |

> 排查思路：先用 eBPF 工具做全量统计（哪些连接、多少流量、有无重传），定位到具体连接/端口后，再用 tcpdump 抓少量包做协议级分析。

---

## 5. 应用层观测

### 5.1 uprobe — 用户态函数跟踪

uprobe 可以在不修改、不重新编译应用的情况下，跟踪用户态函数的调用。这是 eBPF 相比 gdb 的优势：gdb 附加会暂停进程，uprobe 运行时附加几乎无影响。

```bash
# 跟踪 bash 的 readline 函数（用户输入了什么命令）
bpftrace -e 'uprobe:/bin/bash:readline { printf("%s: %s\n", comm, str(retval)); }'

# 跟踪 libc 的 malloc（分配大小 + 调用栈）
bpftrace -e 'uprobe:/lib/x86_64-linux-gnu/libc.so.6:malloc { @[comm, ustack] = sum(arg0); } interval:s:10 { print(@); clear(@); }'

# 跟踪 OpenSSL 的 SSL_write（加密前的明文——安全审计场景）
bpftrace -e 'uprobe:/usr/lib/x86_64-linux-gnu/libssl.so.3:SSL_write { printf("%s bytes: %d\n", comm, arg2); }'
```

> uprobe 的函数名需要符号表：strip 过的二进制没有函数符号，uprobe 无法按函数名挂载，只能用偏移量（`uprobe:/path/to/bin:0x1234`）。生产环境的 release 版本通常 strip 了，需要保留符号的版本或调试信息包。

### 5.2 USDT — 用户态静态跟踪点

USDT（Userland Statically Defined Tracing）是应用开发者在代码中预埋的跟踪点，类似内核的 tracepoint。相比 uprobe（动态挂载任意函数），USDT 的优势是：
- ABI 稳定（开发者维护，不随编译器优化变化）
- 语义明确（参数有明确含义，不是函数调用约定的寄存器）
- 开销更低（nop 指令，启用时才替换）

应用中添加 USDT（C 代码示例）：

```c
#include <sys/sdt.h>
void handle_request(int req_id, int latency_ms) {
    STAP_PROBE2(myapp, request_done, req_id, latency_ms);
    // ...
}
```

用 bpftrace 跟踪 USDT：

```bash
# 列出二进制中的 USDT 探针
bpftrace -l 'usdt:/path/to/myapp:*'

# 跟踪特定 USDT 探针
bpftrace -e 'usdt:/path/to/myapp:myapp:request_done { printf("req=%d latency=%dms\n", arg0, arg1); }'
```

支持 USDT 的常见应用：MySQL（`DTRACE_PROBE`）、PostgreSQL、Node.js（`--trace-events`）、Python（SystemTap 集成）、Nginx（`--with-debug`）。

### 5.3 ringbuffer 输出

eBPF 程序产生的事件需要输出到用户态。传统方式是 `perf_event_array`（perf buffer），每个 CPU 一个环形缓冲区，事件通过内存映射输出。5.8+ 内核引入 `ringbuf`（`BPF_MAP_TYPE_RINGBUF`），优势：
- 跨 CPU 共享一个缓冲区（不需要每 CPU 一个，内存更省）
- 支持变长事件
- 无丢失模式（可阻塞等待空间）
- 输出顺序更自然（按时间顺序，而非按 CPU 分开）

bpftrace 默认使用 ringbuf（如果内核支持），BCC 工具在新版本中也逐步迁移到 ringbuf。

---

## 6. eBPF 与 perf 的对比

| 维度 | perf（《../07-调试与测试/03-perf性能剖析.md》） | eBPF |
| --- | --- | --- |
| 工作方式 | 采样（每隔 N 个事件/时间拍一次快照） | 事件驱动（每次事件都触发，无遗漏） |
| 开销 | 低（采样率可控，99Hz 几乎无影响） | 极低-中（取决于事件频率和程序复杂度） |
| 精度 | 有采样误差（低频率事件可能漏） | 精确（每次事件都记录） |
| on-CPU 分析 | 强（`perf record` / `perf top`） | 可（`profile` 探针，本质也是采样） |
| off-CPU 分析 | 弱（`perf sched` 有限） | 强（`offcputime`，精确跟踪每次阻塞） |
| 网络观测 | 弱（只能看 tracepoint） | 强（XDP/TC/socket filter，包级处理） |
| 应用层跟踪 | 需重新编译插桩（`-pg`）或 perf map | uprobe/USDT，运行时附加 |
| 自定义逻辑 | 有限（perf script 后处理） | 强（内核中运行任意 BPF 程序） |
| 内核版本要求 | 2.6+（基础功能） | 4.9+（基础），5.x+（完整功能） |
| 学习曲线 | 中等（命令行参数多） | 陡（需理解 BPF 程序、map、探针类型） |

**最佳实践**：
1. 先用 `perf top` / `perf record` 做 on-CPU 分析，找到 CPU 热点函数。
2. 如果 CPU 不高但延迟高（off-CPU 问题），用 eBPF `offcputime` 找阻塞点。
3. 网络问题用 eBPF `tcplife`/`tcpretrans`/`tcpconnect` 做全量统计，再用 tcpdump 抓包。
4. 应用层函数级跟踪用 eBPF uprobe/USDT，不需要重新编译。
5. 自定义统计逻辑（如"按用户 ID 统计请求延迟分布"）用 bpftrace 或 BCC 写 BPF 程序。

---

## 7. 快速参考卡片

### 7.1 常用 bpftrace 一行命令

```text
【进程】
新进程创建：       bpftrace -e 'tracepoint:sched:sched_process_exec { printf("%d %s\n", pid, comm); }'
进程退出：         bpftrace -e 'tracepoint:sched:sched_process_exit { printf("%d %s exit=%d\n", pid, comm, args->code); }'
CPU 采样栈：       bpftrace -e 'profile:hz:99 { @[kstack] = count(); }'
运行队列延迟：     bpftrace -e 'tracepoint:sched:sched_wakeup { @wake[tid]=nsecs; } tracepoint:sched:sched_switch /@wake[tid]/ { @lat=hist((nsecs-@wake[tid])/1000); delete(@wake[tid]); }'

【文件】
打开文件：         bpftrace -e 'tracepoint:syscalls:sys_enter_openat { printf("%s %s\n", comm, str(args->filename)); }'
文件删除：         bpftrace -e 'tracepoint:syscalls:sys_enter_unlinkat { printf("%s %s\n", comm, str(args->filename)); }'

【磁盘 IO】
IO 延迟分布：      bpftrace -e 'kprobe:blk_account_io_start { @s[arg0]=nsecs; } kretprobe:blk_account_io_done /@s[arg0]/ { @us=hist((nsecs-@s[arg0])/1000); delete(@s[arg0]); }'

【网络】
主动连接：         bpftrace -e 'kprobe:tcp_v4_connect { printf("%s -> %pI4:%d\n", comm, arg1+4, arg2); }'
发送字节统计：     bpftrace -e 'kprobe:tcp_sendmsg { @[comm]=sum(arg3); } interval:s:5 { print(@); clear(@); }'
重传统计：         bpftrace -e 'tracepoint:tcp:tcp_retransmit_skb { @[comm]=count(); } interval:s:5 { print(@); clear(@); }'

【内存】
malloc 统计：      bpftrace -e 'uprobe:/lib/x86_64-linux-gnu/libc.so.6:malloc { @[comm]=sum(arg0); } interval:s:5 { print(@); clear(@); }'
缺页异常：         bpftrace -e 'tracepoint:exceptions:page_fault_user { @[comm]=count(); } interval:s:5 { print(@); clear(@); }'
```

### 7.2 BCC 工具速查表

```text
【进程/文件】
execsnoop-bpfcc       新进程跟踪
opensnoop-bpfcc       文件打开跟踪
statsnoop-bpfcc       stat 调用跟踪
fsslower-bpfcc        慢文件操作（>ms）
filetop-bpfcc         文件读写 TOP

【磁盘 IO】
biosnoop-bpfcc        每个 IO 详情
biolatency-bpfcc      IO 延迟分布
biotop-bpfcc          IO TOP 进程
bitesize-bpfcc        IO 大小分布

【网络】
tcplife-bpfcc         TCP 连接生命周期
tcptop-bpfcc          TCP 流量 TOP
tcpconnect-bpfcc      主动连接跟踪
tcpaccept-bpfcc       被动连接跟踪
tcpretrans-bpfcc      重传跟踪
tcpsynbl-bpfcc        SYN 队列统计

【内存/CPU】
memleak-bpfcc         内存泄漏检测
cachestat-bpfcc       页缓存命中率
runqlat-bpfcc         运行队列延迟
offcputime-bpfcc      off-CPU 栈跟踪
profile-bpfcc         CPU 采样栈
```

### 7.3 程序类型与探针对照

```text
kprobe:func            内核函数入口（动态，可能不稳定）
kretprobe:func         内核函数返回
tracepoint:sys:call    内核静态跟踪点（稳定 ABI，优先）
uprobe:/path:func      用户态函数入口
uretprobe:/path:func   用户态函数返回
usdt:/path:prov:probe  用户态静态跟踪点（应用预埋）
profile:hz:99          定时采样（CPU 分析）
interval:s:N           每 N 秒触发（定时输出）
software:event          软件事件（ctx-switch、page-fault）
hardware:event          硬件事件（cache-miss、cycles）
```

---

## 8. 常见问题与坑

1. **内核版本不够**：eBPF 基础功能需 4.9+，CO-RE/BTF/ringbuf 需 5.x+；CentOS 7（3.10 内核）基本不可用，CentOS 8（4.18）部分可用，Ubuntu 22.04+（5.15+）功能完整。
2. **WSL2 不支持完整 eBPF**：WSL2 内核默认未开启 `CONFIG_BPF_KPROBE_OVERRIDE`、`CONFIG_BPF_LSM` 等选项，且缺少内核头文件；bpftrace/BCC 可能报 `ERROR: bpftrace attached to 0 probes`。生产环境用原生 Linux。
3. **CO-RE（Compile Once - Run Everywhere）**：传统 BCC 工具在目标机上用 clang 即时编译 BPF 程序，依赖内核头文件；CO-RE 预编译 BPF 程序 + BTF（BPF Type Format）运行时重定位，不需要内核头文件，是现代 eBPF 应用的标准做法（libbpf + CO-RE）。
4. **BTF 缺失**：`/sys/kernel/btf/vmlinux` 不存在说明内核未开启 `CONFIG_DEBUG_INFO_BTF`，CO-RE 工具无法运行；Ubuntu 20.10+ 默认开启，CentOS 需手动开启。
5. **kprobe 函数名随内核版本变化**：内核函数可能被重命名或内联优化掉，kprobe 挂载失败；优先用 tracepoint（稳定 ABI），其次用 kprobe 并做好版本兼容。
6. **uprobe 找不到函数**：strip 过的二进制没有符号表，uprobe 无法按函数名挂载；用 `nm` / `objdump -t` 检查符号，或用偏移量挂载（`uprobe:/path:0xoffset`）。
7. **verifier 拒绝程序**：BPF 程序被 verifier 拒绝通常是因为：无界循环、非法指针访问、指令数超限、未初始化变量；错误信息会指出具体指令，简化程序或拆分为多个程序。
8. **事件丢失**：高频事件（如每个网络包、每次 malloc）用 perf buffer/ringbuf 输出可能丢失；降低事件频率（采样而非全量）、增大 buffer 大小、用 PERCPU map 在内核态聚合后再输出。
9. **eBPF 不是万能的**：verifier 限制了程序复杂度（不能有无限循环、不能随意调用内核函数），某些场景仍需内核模块；eBPF 程序不能睡眠、不能调用可能阻塞的函数。
10. **权限要求**：加载 BPF 程序需要 `CAP_BPF`（5.8+）或 root；非 root 用户需配置 `CAP_BPF`、`CAP_PERFMON`、`CAP_SYS_ADMIN` 等能力。
11. **bpftrace 与 BCC 选型**：快速排查、一行命令用 bpftrace；复杂工具、需要 Python 后处理用 BCC；生产环境长期运行的工具用 libbpf + CO-RE（性能更好、不依赖内核头文件和 clang）。
12. **profile 采样率用 99Hz 而非 100Hz**：避免与系统周期任务（如 100Hz 时钟中断）对齐导致采样偏差；99Hz 是质数频率，不会与常见周期任务共振。

---

上一篇：《11-压测工具族.md》　｜　下一篇：《13-netfilter与iptables防火墙.md》　｜　模块索引：《../README.md》
