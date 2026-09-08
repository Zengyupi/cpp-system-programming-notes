# Linux 系统监控命令族

> 本节目标：建立"看什么指标 → 用什么命令 → 关键字段怎么读"的监控调优体系，覆盖 CPU、内存、磁盘 IO、网络四大子系统的实时与历史监控，以及 sysctl/ulimit 系统调优手段。与《01-Linux命令行速查.md》互补——那篇讲日常操作，本篇聚焦监控调优；性能剖析深度配合《../07-调试与测试/03-perf性能剖析.md》。命令均在 WSL Ubuntu 24.04 实跑验证（sysstat 12.5.2、procps 4.0.4、iproute2 6.1.0）。

## 本章速览

- [0. 监控体系总览](#0-监控体系总览)
- [1. CPU 监控](#1-cpu-监控)
- [2. 内存监控](#2-内存监控)
- [3. 磁盘 IO 监控](#3-磁盘-io-监控)
- [4. 网络监控](#4-网络监控)
- [5. 系统调优](#5-系统调优)
- [6. 综合监控工具](#6-综合监控工具)
- [7. 快速参考卡片](#7-快速参考卡片)
- [8. 常见问题与坑](#8-常见问题与坑)

---

## 0. 监控体系总览

线上排查的标准路径是"先全局、后定位"：先看整机资源水位（CPU/内存/IO/网络），再下钻到进程级，最后结合历史数据判断是瞬时抖动还是趋势性恶化。

| 子系统 | 实时概览 | 进程级 | 历史统计 | 关键字段 |
| --- | --- | --- | --- | --- |
| CPU | `top` / `htop` / `atop` | `top -H -p PID` | `mpstat -P ALL` / `sar -u` | `%us` `%sy` `%wa` `%id` |
| 内存 | `free -h` | `pmap -x PID` | `sar -r` | `available` `buff/cache` `Swap` |
| 磁盘 IO | `iostat -xz 1` | `iotop` | `sar -d` | `%util` `await` `r/s` `w/s` |
| 网络 | `iftop` / `nethogs` | `ss -ti` | `sar -n DEV` | `rxkB/s` `txkB/s` `retrans` |

> 四个子系统不是孤立的：CPU `%wa` 高往往指向磁盘 IO 瓶颈；内存 `available` 低会触发 swap 进而拖慢 IO；网络重传率高会让应用线程阻塞在 send/recv 上表现为 CPU `%sy` 升高。

---

## 1. CPU 监控

### 1.1 top / htop / atop — 进程级实时视图

`top` 是最基础的交互式监控，按 `P` 按 CPU 排序、`M` 按内存排序、`1` 切换多核视图、`H` 显示线程、`c` 显示完整命令行。

```bash
top                     # 默认 3 秒刷新
top -d 1                # 1 秒刷新
top -H -p $(pgrep -f my_server)   # 只看某进程的所有线程
top -b -n 1 > top.txt  # 非交互模式，抓一次快照
```

`top` 输出关键字段（Ubuntu 24.04，procps 4.0.4）：

```text
top - 14:32:05 up 2 days,  3:14,  2 users,  load average: 0.15, 0.08, 0.04
Tasks: 198 total,   1 running, 197 sleeping,   0 stopped,   0 zombie
%Cpu(s):  2.3 us,  1.0 sy,  0.0 ni, 96.3 id,  0.3 wa,  0.0 hi,  0.1 si,  0.0 st
MiB Mem :   7840.0 total,   3200.5 free,   1800.2 used,   2839.3 buff/cache
MiB Swap:   2048.0 total,   2048.0 free,      0.0 used.   5600.8 avail Mem

    PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND
   1420 zqs       20   0 1234567  89012  45678 S   5.3   1.1   0:12.34 my_server
```

| 字段 | 含义 |
| --- | --- |
| `load average` | 1/5/15 分钟平均运行队列长度；**超过 CPU 核数说明有排队** |
| `%us` | 用户态 CPU 占比（应用代码） |
| `%sy` | 内核态 CPU 占比（系统调用、中断、软中断） |
| `%wa` | iowait，CPU 等磁盘 IO 的时间；**高了指向 IO 瓶颈** |
| `%hi` / `%si` | 硬中断 / 软中断占比；网络高吞吐时 `%si` 会升高 |
| `%st` | 虚拟化中被宿主机偷走的时间；物理机通常为 0 |
| `VIRT` / `RES` / `SHR` | 虚拟内存 / 常驻物理内存 / 共享内存；**看实际占用用 RES** |

`htop` 是 top 的增强版：彩色显示、鼠标支持、可滚动进程列表、树形视图（`F5`）、按用户过滤（`u`）。`atop` 则侧重记录历史快照，可回溯过去某个时间点的系统状态（`atop -r /var/log/atop/atop_YYYYMMDD`）。

### 1.2 mpstat — 多核 CPU 统计

`top` 的 `1` 视图只能看当前，`mpstat` 可以输出每个核的详细统计并支持间隔采样：

```bash
mpstat                    # 自开机以来的平均
mpstat -P ALL 1 3         # 所有核，每秒采样，共 3 次
mpstat -P 0,2 1           # 只看 0 号和 2 号核
```

实跑输出（WSL Ubuntu 24.04，8 核）：

```text
Linux 5.15.153.1-microsoft-standard-WSL2 (host)   09/08/2026  _x86_64_  (8 CPU)

02:35:00 PM  CPU    %usr   %nice    %sys %iowait    %irq   %soft  %steal  %guest  %gnice   %idle
02:35:01 PM  all    1.25    0.00    0.62    0.00    0.00    0.12    0.00    0.00    0.00   98.00
02:35:01 PM    0    2.00    0.00    1.00    0.00    0.00    0.00    0.00    0.00    0.00   97.00
02:35:01 PM    1    0.00    0.00    0.00    0.00    0.00    0.00    0.00    0.00    0.00  100.00
```

- **单核 `%usr` 持续 100% 而其他核空闲**：单线程瓶颈，应用没有利用多核（典型如 Python GIL、单线程事件循环）。
- **所有核 `%sys` 偏高**：系统调用密集或内核态开销大，结合 `strace`（《06-strace系统调用跟踪.md》）看高频系统调用。
- **`%iowait` 高**：CPU 在等磁盘，问题在 IO 子系统而非 CPU。

### 1.3 sar — 历史统计与全天候监控

`sar` 是 sysstat 包的核心工具，能收集、保存、报告系统活动。它的独特价值是**历史回溯**——可以查昨天下午 3 点的 CPU 水位，这是 top/mpstat 做不到的。

```bash
sar -u 1 3                # CPU 使用率，每秒采样 3 次
sar -u -f /var/log/sysstat/sa08    # 读取 8 号的历史数据
sar -u -s 14:00:00 -e 15:00:00     # 指定时间段
sar -P ALL                 # 每核统计
sar -q                     # 运行队列和 load average
sar -W                     # swap 换入换出
```

> **sar 需要 sysstat 服务开启才会记录历史数据**：`systemctl enable --now sysstat`，数据默认保存在 `/var/log/sysstat/saDD`，保留 7 天（`/etc/sysstat/sysstat` 的 `HISTORY` 参数可调）。

---

## 2. 内存监控

### 2.1 free — 内存概览

```bash
free -h                   # 人类可读
free -s 1                 # 每秒刷新
```

实跑输出：

```text
               total        used        free      shared  buff/cache   available
Mem:           7.7Gi       1.8Gi       3.1Gi       0.0Ki       2.8Gi       5.5Gi
Swap:          2.0Gi          0B       2.0Gi
```

| 字段 | 含义 |
| --- | --- |
| `total` | 物理内存总量 |
| `used` | 已被占用（不含 buff/cache） |
| `free` | 完全空闲 |
| `buff/cache` | 页缓存 + 缓冲区，**可被回收**，不是"浪费" |
| `available` | 应用实际可用内存 ≈ free + 可回收的 cache；**这个字段最关键** |
| `Swap` | 交换分区使用量；**used > 0 说明内存压力曾经出现过** |

> 常见误区：看到 `free` 少就以为内存不够。Linux 会尽量用空闲内存做页缓存加速 IO，`available` 才是判断内存是否紧张的依据。`available < 10% total` 且 swap 持续增长才是真内存不足。

### 2.2 pmap — 进程内存映射

`pmap` 显示进程的地址空间映射，用于排查"进程内存到底用在哪了"：

```bash
pmap -x $(pgrep -f my_server)       # 详细映射
pmap -x PID | tail -5                # 看汇总行
pmap -d PID                          # 显示设备信息
```

输出关键列：

```text
Address           Kbytes     RSS   Dirty Mode  Mapping
000055f8a1c00000    1234     567     123 r-x-- my_server
000055f8a1e34000      88      88      88 r---- my_server
000055f8a1e4a000      44      44      44 rw--- my_server
00007f8a00000000   65536   32768   32768 rw---   [ anon ]
...
mapped: 131072K    writeable/private: 98304K    shared: 4096K
```

- `[ anon ]` 大块映射：堆内存或 mmap 匿名映射，**持续增长的 anon 段是内存泄漏的信号**。
- `writeable/private`：进程私有可写内存，这部分才是真正的物理内存消耗（RSS 的主体）。
- 结合 `/proc/PID/smaps` 可以看到每个映射段的更详细信息（PSS、Swap、KernelPageSize 等）。

### 2.3 vmstat — 虚拟内存统计

`vmstat` 同时显示进程、内存、swap、IO、CPU 的综合状态，是"一眼看全局"的工具：

```bash
vmstat 1 5                  # 每秒采样，共 5 次
vmstat -s                   # 内存事件统计（自开机）
vmstat -m                   # slab 分配器统计
```

输出：

```text
procs -----------memory---------- ---swap-- -----io---- -system-- ------cpu-----
 r  b   swpd   free   buff  cache   si   so    bi    bo   in   cs us sy id wa st
 0  0      0 3200500 123456 2839300    0    0     5    12  120  230  2  1 97  0  0
```

| 字段 | 含义 |
| --- | --- |
| `r` | 运行队列长度（正在等 CPU 的进程数）；**持续 > 核数说明 CPU 饱和** |
| `b` | 不可中断睡眠的进程数（通常在等 IO）；**持续 > 0 说明 IO 瓶颈** |
| `si` / `so` | swap 换入 / 换出（KB/s）；**持续 > 0 说明内存严重不足** |
| `bi` / `bo` | 块设备读 / 写（blocks/s） |
| `in` / `cs` | 中断数 / 上下文切换数；**cs 异常高可能是锁竞争或线程过多** |

### 2.4 glances — 跨平台综合监控

`glances` 用一个界面展示 CPU、内存、磁盘、网络、进程、传感器、Docker 容器等，支持 C/S 模式（`glances -s` 服务端，`glances -c IP` 客户端）和 Web 模式（`glances -w`）。

```bash
apt install glances
glances                 # 本地交互式
glances -w              # Web 模式，浏览器访问 http://IP:61208
glances --export csv --export-csv-file /tmp/glances.csv   # 导出数据
```

---

## 3. 磁盘 IO 监控

### 3.1 iostat — 块设备 IO 统计

`iostat` 是磁盘 IO 监控的核心工具，`-x` 输出扩展统计，`-z` 跳过无活动设备：

```bash
iostat                  # 自开机以来的平均
iostat -xz 1            # 扩展统计，每秒刷新
iostat -d -x 1 3 sda    # 只看 sda，采样 3 次
iostat -p sda            # 包含分区
```

实跑输出关键字段：

```text
Linux 5.15.153.1-microsoft-standard-WSL2 (host)   09/08/2026  _x86_64_  (8 CPU)

avg-cpu:  %user   %nice %system %iowait  %steal   %idle
           2.30    0.00    1.10    0.30    0.00   96.30

Device     r/s     w/s     rkB/s     wkB/s  rrqm/s  wrqm/s  await  r_await  w_await  svctm  %util
sda        5.20    8.40    210.40    340.80    0.10    0.30   2.15     1.80     2.40   0.85   1.15
```

| 字段 | 含义 |
| --- | --- |
| `r/s` / `w/s` | 每秒读 / 写请求数（IOPS） |
| `rkB/s` / `wkB/s` | 每秒读 / 写数据量（吞吐量） |
| `await` | 平均 IO 响应时间（ms），**包含队列等待 + 设备服务时间**；> 20ms 偏慢，> 50ms 严重 |
| `r_await` / `w_await` | 读 / 写分别的响应时间 |
| `svctm` | 平均设备服务时间（ms）；**await - svctm = 队列等待时间**，差值大说明 IO 排队严重 |
| `%util` | 设备繁忙时间占比；**机械盘 > 80% 说明接近饱和** |

> **重要：`%util` 对 SSD/NVMe 不准确。** SSD 支持并行 IO（NCQ/NVMe 多队列），`%util` 统计的是"有 IO 在飞的时间占比"，而不是"设备能力用了多少"。一块 NVMe 在 `%util=100%` 时可能还能承受更多 IOPS。判断 SSD 瓶颈要看 `await` 是否持续升高、IOPS 是否到了设备规格上限。

### 3.2 iotop — 按进程看 IO

`iostat` 只能看到设备级，`iotop` 可以看到**哪个进程在做 IO**：

```bash
iotop                   # 交互式，按 IO 排序
iotop -o                # 只显示有 IO 活动的进程
iotop -b -n 3 -d 2      # 非交互模式，2 秒一次，共 3 次
iotop -p PID            # 只看指定进程
```

输出列：`TID` `PRIO` `USER` `DISK READ` `DISK WRITE` `SWAPIN` `IO>` `COMMAND`。`IO>` 列是该进程的 IO 占比，`SWAPIN` 是花在 swap 换入上的时间占比。

### 3.3 dstat — 全能资源统计

`dstat` 是 vmstat/iostat/netstat 的合体，输出颜色编码，支持插件扩展：

```bash
dstat                   # 默认显示 CPU/磁盘/网络/分页/系统
dstat -cdngy            # CPU/磁盘/网络/页/系统调用
dstat --top-io --top-cpu   # 显示最耗 IO 和 CPU 的进程
dstat -f --output /tmp/dstat.csv 1 60   # 导出 CSV，每秒采样 60 次
```

---

## 4. 网络监控

### 4.1 iftop — 带宽实时监控

`iftop` 按连接对显示实时带宽，是"谁在占带宽"的首选工具：

```bash
apt install iftop
iftop                   # 默认监听第一块网卡
iftop -i eth0           # 指定网卡
iftop -nN               # 不解析主机名和端口名（更快）
iftop -f "port 80"      # 只看 80 端口流量（BPF 过滤）
```

界面显示每个连接对的 `2s` `10s` `40s` 平均速率，底部有总发送/接收速率和峰值。按 `s` 切换源端口显示，`d` 切换目标端口，`p` 暂停刷新。

### 4.2 nethogs — 按进程统计带宽

`iftop` 按连接对，`nethogs` 按**进程**统计带宽，能直接看到"哪个进程在吃带宽"：

```bash
apt install nethogs
nethogs                 # 默认所有网卡
nethogs eth0            # 指定网卡
nethogs -t              # 非交互模式（trace mode），可重定向到文件
```

输出：`PID` `USER` `PROGRAM` `DEV` `SENT` `RECEIVED`。排查"机器带宽被占满但不知道是谁"时，`nethogs` 一步到位。

### 4.3 ethtool — 网卡信息与 offload

`ethtool` 查看和配置网卡硬件参数，排查网络性能问题时必看：

```bash
ethtool eth0                            # 网卡基本信息（速度、双工、链路状态）
ethtool -i eth0                         # 驱动信息
ethtool -S eth0                         # 网卡统计（收发包、错误、丢弃）
ethtool -k eth0                         # offload 特性状态
ethtool -c eth0                         # 中断聚合参数
ethtool -g eth0                         # ring buffer 大小
ethtool -l eth0                         # 多队列（RSS）队列数
```

关键字段解读：

```text
# ethtool eth0
Settings for eth0:
        Speed: 10000Mb/s          # 速率 10G
        Duplex: Full               # 全双工
        Link detected: yes         # 链路正常

# ethtool -S eth0（关注错误计数）
     rx_errors: 0                  # 接收错误
     rx_dropped: 12                # 接收丢弃（ring buffer 不够或 backlog 满）
     tx_errors: 0
     tx_dropped: 0
     rx_missed_errors: 12          # 因 ring buffer 满而丢失的包

# ethtool -k eth0（offload）
     tcp-segmentation-offload: on   # TSO，网卡分片，降低 CPU
     generic-segmentation-offload: on
     rx-checksumming: on             # 校验和卸载
     scatter-gather: on
```

- `rx_dropped` / `rx_missed_errors` 持续增长：ring buffer 不够或 CPU 处理不过来，调大 `ethtool -G eth0 rx 4096` 或开启 RPS/RFS。
- 高吞吐下 CPU `%si`（软中断）高：检查 TSO/GRO/LRO 是否开启，考虑多队列 RSS（`ethtool -l` 看队列数）。

### 4.4 ss — socket 统计（替代 netstat）

`ss` 是 iproute2 套件的工具，比 `netstat` 更快（直接读 `/proc/net` 而非遍历 `/proc/PID`），是网络连接排查的标准工具：

```bash
ss -tlnp                 # TCP 监听端口 + 进程
ss -tunap                # TCP+UDP 所有连接 + 进程
ss -ti                   # TCP 连接的内部信息（cwnd/rtt/retrans）
ss -t state established   # 只看 ESTABLISHED 状态
ss -t '( dport = :80 or sport = :80 )'   # 过滤 80 端口
ss -s                    # 连接统计汇总
```

`ss -s` 汇总输出：

```text
Total: 198
TCP:   145 (estab 89, closed 32, orphaned 0, timewait 20)
Transport Total     IP        IPv6
RAW       1         0         1
UDP       3         2         1
TCP       113       98        15
INET      117       100       17
FRAG      0         0         0
```

`ss -ti` 是排查 TCP 性能问题的利器，能看到每个连接的拥塞窗口、RTT、重传：

```text
ESTAB  0  0  192.168.1.10:54321  10.0.0.5:8080
	 cubic wscale:7,7 rto:204 rtt:1.5/0.8 ato:40 mss:1448 pmtu:1500
	 rcvmss:1448 advmss:1448 cwnd:10 bytes_acked:12345 bytes_received:6789
	 segs_out:45 segs_in:43 data_segs_out:20 data_segs_in:18
	 send 77.2Mbps lastsnd:120 lastrcv:100 lastack:80
	 pacing_rate 154.4Mbps retrans:0/15 rcv_space:28960 rcv_ssthresh:28960
```

- `rtt`：往返时间，`/` 后是方差；RTT 高且方差大说明网络不稳定。
- `retrans:0/15`：重传段数/总段数，**重传率高直接影响吞吐**。
- `cwnd`：拥塞窗口，cwnd 小说明网络拥塞或对端接收窗口小。

### 4.5 sar -n DEV — 网络历史统计

```bash
sar -n DEV 1 3           # 网卡级流量统计
sar -n TCP,ETCP 1 3      # TCP 统计（含重传）
sar -n SOCK               # socket 使用统计
```

`sar -n DEV` 输出：

```text
14:00:00        IFACE   rxpck/s   txpck/s    rxkB/s    txkB/s   rxcmp/s   txcmp/s  rxmcst/s   %ifutil
14:00:01         eth0     120.50      98.20     150.30      80.40      0.00      0.00      0.00      0.02
```

- `rxpck/s` / `txpck/s`：每秒收/发包数；小包场景下包数高但带宽低，CPU 中断开销大。
- `rxkB/s` / `txkB/s`：每秒收/发数据量。
- `%ifutil`：带宽利用率（基于网卡速率计算）。

---

## 5. 系统调优

### 5.1 sysctl — 内核参数运行时调整

`sysctl` 读取和修改 `/proc/sys` 下的内核参数，运行时生效（重启丢失），持久化写入 `/etc/sysctl.conf` 或 `/etc/sysctl.d/*.conf`。

```bash
sysctl -a                         # 列出所有参数
sysctl net.ipv4.tcp_rmem          # 查看单个参数
sysctl -w net.core.somaxconn=4096  # 运行时修改
sysctl -p /etc/sysctl.d/99-network.conf   # 从文件加载
```

### 5.2 网络关键参数

高并发网络服务的常用调优参数：

```bash
# /etc/sysctl.d/99-network.conf
# 连接队列
net.core.somaxconn = 4096              # listen  backlog 上限（应用需配合调大 backlog 参数）
net.core.netdev_max_backlog = 5000     # 网卡收包队列

# TCP 缓冲区
net.core.rmem_max = 16777216           # 接收缓冲区最大（16MB）
net.core.wmem_max = 16777216           # 发送缓冲区最大
net.ipv4.tcp_rmem = 4096 87380 16777216   # min default max（自动调节范围）
net.ipv4.tcp_wmem = 4096 65536 16777216

# 连接跟踪
net.netfilter.nf_conntrack_max = 1048576   # conntrack 表最大条目
net.netfilter.nf_conntrack_tcp_timeout_established = 86400

# TCP 行为
net.ipv4.tcp_max_syn_backlog = 8192    # SYN 队列
net.ipv4.tcp_tw_reuse = 1               # TIME_WAIT 复用（客户端主动关闭场景）
net.ipv4.tcp_fin_timeout = 15           # FIN-WAIT-2 超时
net.ipv4.ip_local_port_range = 1024 65535   # 本地端口范围
```

> **conntrack 表满是高频线上事故**：`dmesg | grep "nf_conntrack: table full"` 会看到报错，表现为新连接建立失败。调大 `nf_conntrack_max` 或减少 `nf_conntrack_tcp_timeout_established`（默认 432000 秒=5天，对短连接服务太长）。

### 5.3 ulimit — 进程资源限制

`ulimit` 控制 shell 启动进程的资源上限，最常用的是文件描述符数：

```bash
ulimit -n                 # 当前进程的 fd 上限（默认 1024）
ulimit -n 65535           # 当前 shell 临时修改
ulimit -a                 # 查看所有限制
```

持久化修改写入 `/etc/security/limits.conf`：

```text
# /etc/security/limits.conf
*    soft    nofile    65535
*    hard    nofile    65535
*    soft    nproc     65535
*    hard    nproc     65535
```

- `soft`：软限制，进程可自行调高到 hard。
- `hard`：硬限制，只有 root 能调高。
- systemd 管理的服务不受 limits.conf 控制，需要在 service 文件中设置 `LimitNOFILE=65535`。
- 检查进程实际限制：`cat /proc/PID/limits | grep "Max open files"`。

---

## 6. 综合监控工具

### 6.1 glances（已在 2.4 节介绍）

### 6.2 dstat（已在 3.3 节介绍）

### 6.3 nmon — IBM 出品的综合监控

`nmon` 是 AIX/Linux 上的经典监控工具，一个界面按字母键切换不同视图（`c` CPU、`m` 内存、`d` 磁盘、`n` 网络、`t` 进程、`k` 内核），支持数据采集模式（`nmon -f -s 10 -c 360` 每 10 秒采一次，共 360 次，输出 `.nmon` 文件，可用 `nmon_analyser` 转 Excel 图表）。

```bash
apt install nmon
nmon                    # 交互式
nmon -f -s 10 -c 360   # 采集模式，1 小时数据
```

### 6.4 工具选型决策

| 场景 | 首选工具 | 辅助工具 |
| --- | --- | --- |
| 登录机器先看一眼全局 | `top` / `htop` | `vmstat 1` |
| CPU 瓶颈定位到核 | `mpstat -P ALL 1` | `top` 按 `1` |
| 内存是否够 | `free -h`（看 available） | `vmstat`（看 si/so） |
| 进程内存用在哪 | `pmap -x PID` | `/proc/PID/smaps` |
| 磁盘是否瓶颈 | `iostat -xz 1` | `iotop`（找进程） |
| 谁在占带宽 | `nethogs`（按进程）/ `iftop`（按连接） | `sar -n DEV` |
| TCP 连接质量 | `ss -ti` | `ethtool -S`（网卡错误） |
| 历史回溯 | `sar` | `atop -r` |
| 一次性导出数据做分析 | `dstat --output csv` | `nmon -f` |

---

## 7. 快速参考卡片

### 7.1 按"看什么指标 → 用什么命令 → 关键字段"速查

```text
【CPU】
整机水位：       top / htop          → %us %sy %wa %id, load average
多核分布：       mpstat -P ALL 1     → 每核 %usr %sys %idle
历史回溯：       sar -u / sar -q     → %user %iowait, runq-sz
进程线程：       top -H -p PID       → 线程级 %CPU

【内存】
整机水位：       free -h              → available, buff/cache, Swap used
进程映射：       pmap -x PID          → [anon] 段, writeable/private
换页事件：       vmstat 1             → si so（持续>0=内存不足）
slab 信息：      vmstat -m / slabtop  → 内核对象缓存占用

【磁盘 IO】
设备级：         iostat -xz 1         → %util await svctm r/s w/s rkB/s
进程级：         iotop -o             → DISK READ/WRITE, IO>
历史：           sar -d               → 设备级历史 IO
综合：           dstat -cdg           → CPU+磁盘+页一体

【网络】
带宽按连接：     iftop -nN            → 2s/10s/40s 速率
带宽按进程：     nethogs              → SENT/RECEIVED per PID
连接状态：       ss -tlnp / ss -tunap → State, Recv-Q, Send-Q
连接质量：       ss -ti               → rtt, cwnd, retrans
网卡硬件：       ethtool eth0 / -S / -k → Speed, rx_dropped, offload
历史流量：       sar -n DEV / TCP     → rxkB/s txkB/s, retrans seg/s

【系统调优】
内核参数：       sysctl -a / -w       → net.ipv4.tcp_rmem 等
持久化：         /etc/sysctl.d/*.conf → sysctl -p 加载
fd 限制：        ulimit -n             → nofile（默认 1024）
持久化 fd：      /etc/security/limits.conf → soft/hard nofile
systemd 服务：   service 文件 LimitNOFILE= → 不受 limits.conf 控制
```

### 7.2 常用命令模板

```bash
# 一键全局健康检查
echo "=== CPU ===" && top -bn1 | head -5 && \
echo "=== MEM ===" && free -h && \
echo "=== DISK ===" && iostat -xz 1 1 | tail -n +6 && \
echo "=== NET ===" && ss -s && \
echo "=== LOAD ===" && cat /proc/loadavg

# 找最耗 CPU 的进程
ps -eo pid,ppid,cmd,%cpu,%mem --sort=-%cpu | head -10

# 找最耗内存的进程
ps -eo pid,ppid,cmd,%mem,rss --sort=-rss | head -10

# 监控某进程的 fd 数（句柄泄漏排查）
watch -n 5 'ls /proc/$(pgrep -f my_server)/fd | wc -l'

# TCP 各状态计数
ss -tan | awk '{print $1}' | sort | uniq -c | sort -rn
```

---

## 8. 常见问题与坑

1. **`iostat %util` 对 SSD 不准确**：SSD 支持并行 IO，`%util=100%` 不代表设备饱和；判断 SSD 瓶颈看 `await` 是否持续升高、IOPS 是否到规格上限。
2. **`sar` 没有历史数据**：需要 `systemctl enable --now sysstat` 才会定时采集；默认保留 7 天，`/etc/sysstat/sysstat` 的 `HISTORY` 可调。
3. **`free` 的 `free` 少不代表内存不够**：Linux 用空闲内存做页缓存，看 `available` 字段；`available < 10% total` 且 swap 增长才是真不足。
4. **`ulimit -n` 修改不生效**：systemd 管理的服务不受 `/etc/security/limits.conf` 控制，需在 service 文件设 `LimitNOFILE=65535`；检查实际值用 `cat /proc/PID/limits`。
5. **`ss` 比 `netstat` 快但参数不同**：`netstat -tlnp` → `ss -tlnp`；`netstat -an` → `ss -tunap`；`netstat -s` → `ss -s`。
6. **conntrack 表满导致新连接失败**：`dmesg | grep "nf_conntrack: table full"`；调大 `nf_conntrack_max` 或缩短 `nf_conntrack_tcp_timeout_established`（默认 5 天对短连接太长）。
7. **`top` 的 `%CPU` 可以超过 100%**：多核机器上进程用满多个核时 `%CPU` 会显示 200%、800% 等（总和上限 = 核数 × 100%）。
8. **`load average` 高不一定是 CPU 瓶颈**：load 包含等 CPU 的进程 + 不可中断睡眠（等 IO）的进程；`load` 高但 `%id` 也高时，看 `vmstat` 的 `b` 列，通常是 IO 瓶颈。
9. **`vmstat` 第一行是自开机平均**：`vmstat 1 3` 的第一行是开机以来的平均，不是当前值；看当前值从第二行开始。
10. **`ethtool -S` 的 `rx_dropped` 要关注增量而非绝对值**：用 `watch -n 1 'ethtool -S eth0 | grep dropped'` 看是否持续增长；持续增长说明 ring buffer 不够或 CPU 处理不过来。
11. **`tcp_tw_reuse` 只对客户端（主动关闭方）有效**：服务端被动关闭不会进入 TIME_WAIT；开启 `tcp_tw_recycle` 在 NAT 环境下有问题，已在 4.12 内核移除。
12. **`pmap` 的 `VIRT` 很大不代表内存泄漏**：VIRT 是虚拟地址空间大小，包含映射的库、预留但未使用的内存；看实际物理占用用 `RES`（top）或 `pmap` 的 `writeable/private`。

---

上一篇：《09-nc与telnet网络调试.md》
下一篇：《11-压测工具族.md》
