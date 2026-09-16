# perf 深度手册：Linux 性能剖析专项（perf_events 全解）

> 本节目标：本文是 perf 的专项深潜手册，深入讲解 Linux perf_events 子系统的采样原理与 skid、调用栈三种回溯方式、动态插桩、调度与 off-CPU 分析、伪共享分析、容器与权限配置，以及 eBPF 时代 perf 的定位。学完后能够运用 perf 进行深度性能剖析与瓶颈定位。性能优化的方法论、工具选型与火焰图基本原理见总纲篇《04-性能分析与基准测试.md》。
> **环境**：perf 只在 Linux 上可用。Windows 本机请在 WSL2 或远程 Linux 服务器上练习本文命令（WSL2 的 PMU 限制见 2.5）。所有命令默认在 bash 下执行。

## 本章速览

- [1. 概述](#1-概述)
  - [1.1 perf 是什么](#11-perf-是什么)
  - [1.2 方法论位置：USE 方法与 60 秒分析](#12-方法论位置use-方法与-60-秒分析)
  - [1.3 与知识库的分工表](#13-与知识库的分工表)
- [2. 安装与权限【第一大坑】](#2-安装与权限第一大坑)
  - [2.1 安装：perf 与内核版本严格匹配](#21-安装perf-与内核版本严格匹配)
  - [2.2 perf_event_paranoid 分级【必须逐级理解】](#22-perf_event_paranoid-分级必须逐级理解)
  - [2.3 kptr_restrict：内核符号显示 \[unknown\] 的元凶](#23-kptr_restrict内核符号显示-unknown-的元凶)
  - [2.4 容器与云主机环境](#24-容器与云主机环境)
  - [2.5 虚拟机与 WSL2：没有 PMU 怎么办](#25-虚拟机与-wsl2没有-pmu-怎么办)
  - [2.6 验证环境三条命令](#26-验证环境三条命令)
- [3. 子命令总览大表](#3-子命令总览大表)
- [4. perf stat：精确计数](#4-perf-stat精确计数)
  - [4.1 基本用法与作用范围](#41-基本用法与作用范围)
  - [4.2 核心指标速览（详表见《04-性能分析与基准测试.md》4.3）](#42-核心指标速览详表见04-性能分析与基准测试md43)
  - [4.3 IPC 判断表](#43-ipc-判断表)
  - [4.4 事件分组、修饰符与多路复用](#44-事件分组修饰符与多路复用)
  - [4.5 详细模式与周期性输出](#45-详细模式与周期性输出)
  - [4.6 topdown 四分类【现代分析方法】](#46-topdown-四分类现代分析方法)
  - [4.7 常用事件速查：perf list 三类](#47-常用事件速查perf-list-三类)
- [5. perf record：采样原理【核心章节】](#5-perf-record采样原理核心章节)
  - [5.1 PMU 溢出采样原理](#51-pmu-溢出采样原理)
  - [5.2 -F 频率 vs -c 周期](#52--f-频率-vs--c-周期)
  - [5.3 精度与 skid：为什么热点会"偏移几条指令"](#53-精度与-skid为什么热点会偏移几条指令)
  - [5.4 采样开销经验表](#54-采样开销经验表)
  - [5.5 目标选择表](#55-目标选择表)
  - [5.6 常用附加参数表](#56-常用附加参数表)
  - [5.7 采样多少才够](#57-采样多少才够)
- [6. 调用栈：三种方式深对比【全文最重要】](#6-调用栈三种方式深对比全文最重要)
  - [6.1 为什么必须有调用栈](#61-为什么必须有调用栈)
  - [6.2 三种回溯方式大对比](#62-三种回溯方式大对比)
  - [6.3 选择决策表](#63-选择决策表)
  - [6.4 栈丢失（\[unknown\]）五大原因排查表](#64-栈丢失unknown五大原因排查表)
  - [6.5 --max-stack 与 JIT 程序](#65---max-stack-与-jit-程序)
- [7. perf report：解读热点](#7-perf-report解读热点)
  - [7.1 交互模式操作键速查](#71-交互模式操作键速查)
  - [7.2 --no-children 语义【高频坑】](#72---no-children-语义高频坑)
  - [7.3 --sort 字段与多维排序](#73---sort-字段与多维排序)
  - [7.4 C++ 符号与模板长名](#74-c-符号与模板长名)
  - [7.5 按 DSO 维度定位"这是谁的问题"](#75-按-dso-维度定位这是谁的问题)
  - [7.6 perf diff：优化前后对比](#76-perf-diff优化前后对比)
- [8. perf annotate：下钻到汇编行](#8-perf-annotate下钻到汇编行)
  - [8.1 使用与前提](#81-使用与前提)
  - [8.2 输出解读表](#82-输出解读表)
  - [8.3 与 gdb 反汇编的分工](#83-与-gdb-反汇编的分工)
- [9. tracepoint 与 perf probe：动态插桩【进阶高频】](#9-tracepoint-与-perf-probe动态插桩进阶高频)
  - [9.1 静态 tracepoint](#91-静态-tracepoint)
  - [9.2 perf trace：性能版 strace](#92-perf-trace性能版-strace)
  - [9.3 perf probe：函数/行/变量级动态插桩](#93-perf-probe函数行变量级动态插桩)
  - [9.4 典型场景组合表](#94-典型场景组合表)
  - [9.5 与 ftrace / eBPF 的一句话关系](#95-与-ftrace--ebpf-的一句话关系)
- [10. 调度与 off-CPU 分析【弥补采样盲区】](#10-调度与-off-cpu-分析弥补采样盲区)
  - [10.1 核心认知：CPU 剖析只看得见"在跑的"](#101-核心认知cpu-剖析只看得见在跑的)
  - [10.2 perf sched 子命令表](#102-perf-sched-子命令表)
  - [10.3 off-CPU 栈采法](#103-off-cpu-栈采法)
  - [10.4 用户态锁等待的观测路径表](#104-用户态锁等待的观测路径表)
- [11. 内存与缓存：perf mem / c2c](#11-内存与缓存perf-mem--c2c)
  - [11.1 perf mem：访存采样](#111-perf-mem访存采样)
  - [11.2 perf c2c：伪共享专治【C++ 高频】](#112-perf-c2c伪共享专治c-高频)
  - [11.3 cache-miss 三层定位法](#113-cache-miss-三层定位法)
  - [11.4 page-fault 高时的分析路径](#114-page-fault-高时的分析路径)
- [12. 火焰图与差异对比工作流](#12-火焰图与差异对比工作流)
  - [12.1 三连命令回顾](#121-三连命令回顾)
  - [12.2 深入参数](#122-深入参数)
  - [12.3 differential 火焰图【优化前后对比标准流程】](#123-differential-火焰图优化前后对比标准流程)
  - [12.4 优化闭环流程](#124-优化闭环流程)
- [13. eBPF 时代：perf 的现在与未来](#13-ebpf-时代perf-的现在与未来)
  - [13.1 关系定位](#131-关系定位)
  - [13.2 perf vs bpftrace vs BCC](#132-perf-vs-bpftrace-vs-bcc)
  - [13.3 bpftrace 两个经典单行](#133-bpftrace-两个经典单行)
  - [13.4 什么时候仍然用 perf](#134-什么时候仍然用-perf)
- [14. 实战案例集](#14-实战案例集)
  - [14.1 案例 1：线上服务 CPU 飙到 90%](#141-案例-1线上服务-cpu-飙到-90)
  - [14.2 案例 2：接口偶发 P99 毛刺（CPU 正常）](#142-案例-2接口偶发-p99-毛刺cpu-正常)
  - [14.3 案例 3：多线程程序多核扩展性差](#143-案例-3多线程程序多核扩展性差)
- [15. 快速参考卡片](#15-快速参考卡片)
- [16. 常见问题与坑](#16-常见问题与坑)

---

## 1. 概述

### 1.1 perf 是什么

perf 是 Linux 内核官方自带的性能分析工具（源码位于内核树 `tools/perf/`），底层依赖内核 **perf_events 子系统**（`perf_event_open()` 系统调用 + CPU 的 PMU 硬件性能计数器）。它的独特之处是一个工具同时覆盖**计数、采样、跟踪**三类观测：

| 观测模式 | 代表命令 | 原理 | 回答的问题 | 典型开销 |
|---|---|---|---|---|
| 计数 | `perf stat` | 直接读计数器，只做汇总，不逐条记录事件 | "发生了多少"（IPC / 缺页 / 切换数 / cache miss 总量） | 接近 0 |
| 采样 | `perf record` | 按频率/周期抓快照（当前指令指针 + 调用栈） | "CPU 时间花在哪些函数/指令上" | 1%~30%（取决于采样率与栈回溯方式） |
| 跟踪 | `perf trace`、`-e tracepoint`、`perf probe` | 事件全量逐条记录（含参数） | "每次事件何时发生、参数是什么"（每次系统调用、每次换出 CPU） | 与事件频率成正比 |

三者互补：先 `stat` 判断"症状类型"，再 `record` 找"是谁"，必要时 `trace`/`probe` 看"每一次"。命令入门速查见《04-性能分析与基准测试.md》4.2 命令大表。

### 1.2 方法论位置：USE 方法与 60 秒分析

USE 方法（Brendan Gregg：对每个资源检查 **U**tilization 利用率、**S**aturation 饱和度、**E**rrors 错误）决定"查什么资源"；perf 解决"怎么查"。上 perf 之前先做 60 秒快速体检，避免拿采样器去查一个其实是磁盘打满的问题：

| 命令 | 一句话用途（详细用法见《../08-网络与系统工具/01-Linux命令行速查.md》第 2 章） |
|---|---|
| `uptime` | 负载趋势：1/5/15 分钟是否持续上升 |
| `dmesg \| tail -20` | 内核报错：OOM kill、硬件/驱动错误 |
| `vmstat 1` | r 队列（CPU 饱和）、si/so（换页）、cs（切换） |
| `mpstat -P ALL 1` | 每核利用率与 `%soft`（软中断是否单核打满） |
| `pidstat 1` | 每进程 CPU：`%usr`/`%sys`/`%wait` 的结构 |
| `iostat -xz 1` | 磁盘 `%util`、`avgqu-sz`（IO 饱和） |
| `sar -n DEV 1` / `sar -n TCP,ETCP 1` | 网络吞吐、TCP 重传/主动连接数 |

CPU 高 → 第 5/6/7 章采样路线；CPU 不高但延迟高 → 第 10 章 off-CPU 路线；切换/缺页异常 → 第 4 章 `stat` 证据链。

### 1.3 与知识库的分工表

| 主题 | 所在笔记 |
|---|---|
| 优化总纲、测量黄金法则、工具全景 | 《04-性能分析与基准测试.md》第 1、2 章 |
| perf 入门：命令大表 / stat 指标表 / 常用事件 / 火焰图原理 | 《04-性能分析与基准测试.md》4.2、4.3、4.4、第 5 章（本文只回顾并深挖） |
| perf 专项深潜（本文） | 《03-perf性能剖析.md》 |
| `-O2 -g`、`-fno-omit-frame-pointer` 等编译选项 | 《../06-构建与版本控制/01-构建工具GCC与CMake.md》2.3 优化选项、2.4 调试与警告选项 |
| 静态反汇编 / 崩溃现场分析 | 《01-GDB程序调试.md》第 5 章（查看数据）、第 11 章（Core Dump） |
| C++ name mangling 与 c++filt | 《../02-系统原理/02-编译链接与加载原理.md》5.2 |
| 竞争检测（Helgrind/DRD、TSan） | 《02-Valgrind内存检测.md》4.4、《../06-构建与版本控制/01-构建工具GCC与CMake.md》2.4 |
| x86 与 ARM 架构差异（PMU 能力背景） | 《../02-系统原理/03-系统架构与选型.md》架构之争 |
| top / vmstat / pidstat 大盘命令 | 《../08-网络与系统工具/01-Linux命令行速查.md》第 2 章 |
| 优化前后提交与回归 | 《../06-构建与版本控制/03-Git版本控制.md》第 12 章常用工作流 |

## 2. 安装与权限【第一大坑】

perf 的命令本身不难，**九成的"入门失败"都发生在安装与权限上**——先过这一关。

### 2.1 安装：perf 与内核版本严格匹配

perf 解析内核符号、注册内核 tracepoint，因此必须与**正在运行的内核版本**严格匹配（严格程度高于一般用户态工具）。

| 现象 | 原因 | 解决 |
|---|---|---|
| `command not found` | 未安装 | 按下表安装对应发行版包 |
| `WARNING: perf not found for kernel 4.15.0-112` | 装了别的内核版本的 linux-tools | `sudo apt install linux-tools-$(uname -r)` |
| `perf` 存在但 `perf record` 大量事件缺失 | linux-tools 与内核小版本不匹配 | 安装 `linux-tools-$(uname -r)`（注意 `$()` 要在 shell 中展开） |
| 自编译内核 | 发行版仓库没有对应 tools 包 | `make -C tools/perf install`（或 `make tools/perf`） |

| 发行版 | 安装命令 | 包名说明 |
|---|---|---|
| Ubuntu / Debian | `sudo apt install linux-tools-common linux-tools-$(uname -r)` | 每个内核版本一个包；`linux-tools-generic` 是通用回退 |
| RHEL / CentOS / Rocky | `sudo dnf install perf` | 单一包，自动匹配内核 |
| Fedora | `sudo dnf install perf` | 同上 |
| Arch | `sudo pacman -S perf` | 官方仓库 |
| openEuler | `sudo dnf install perf` | 同 RHEL 系 |

### 2.2 perf_event_paranoid 分级【必须逐级理解】

`/proc/sys/kernel/perf_event_paranoid` 控制**非特权用户**（不持有 `CAP_PERFMON` / `CAP_SYS_ADMIN` 的用户）使用 perf_events 的范围。root 和持权进程**不受该值约束**。各级语义（依据内核文档 `Documentation/admin-guide/perf-security.rst` 与 `perf_event_open(2)` man page）：

| 值 | 非特权用户可以做什么 | 备注 |
|---|---|---|
| `-1` | 全部允许：进程级 + 系统级、用户态 + 内核态、raw tracepoint / ftrace 全开放（`perf_event_mlock_kb` 锁页上限也被忽略） | 最宽松也最危险，仅个人测试机 |
| `0` | 允许所有 CPU 事件（进程级 + 系统级会话，含内核态剖析），**但不含 raw tracepoint / ftrace 函数级跟踪** | |
| `1` | 允许进程级、用户态 + 内核态剖析；**不允许系统级（per-CPU 全机）会话**；raw tracepoint 仍被禁止 | Linux 4.6 之前的旧默认值 |
| `2` | **仅允许进程级、仅用户态事件**（内核态剖析被拒绝） | **主线内核默认值**；perf 报错时的提示也只列到本级 |
| `3` | 更严格：进一步禁止非特权用户剖析 | 发行版扩展级（Debian 系补丁引入），语义视发行版而定 |
| `4` | 完全禁止非特权 `perf_event_open()` | 发行版扩展级（Ubuntu 曾以 4 作为默认收紧值）；**注意：这并非主线 5.8 新特性** |

三条关键澄清（高频误解）：

| 误解 | 事实 |
|---|---|
| "4 级是内核 5.8 新增的" | 主线文档只正式定义到 2 级；perf 报错时自己打印的帮助也只列到 `>=2: Disallow kernel profiling`。3/4 是 **Debian（引入 3）/ Ubuntu（用 4）的发行版补丁**。内核 **5.8 真正的新增是 `CAP_PERFMON` capability**——持该能力的进程直接绕过 paranoid 限制（perf 报错提示会同时列出 CAP_PERFMON / CAP_SYS_PTRACE / CAP_SYS_ADMIN） |
| "默认值是 2" | 主线默认 2，但发行版各有取舍（Ubuntu/Debian 曾随安全更新把默认收紧到 3~4），**必须 `cat` 实测** |
| "设成 -1 才能用" | 只想采用户态热点时，`1`（进程级含内核）或 `2`（纯用户态）通常已够；`-1` 会放开 raw tracepoint 等高风险面，测试机之外不要用 |

查看与修改：

```bash
# 查看当前级别（每次排查第一步）
cat /proc/sys/kernel/perf_event_paranoid

# 临时放开到 1（允许非特权进程级剖析，含内核态；重启失效）
echo 1 | sudo tee /proc/sys/kernel/perf_event_paranoid

# 永久生效：写入 sysctl.d 并应用
echo 'kernel.perf_event_paranoid = 1' | sudo tee /etc/sysctl.d/99-perf.conf
sudo sysctl --system

# 或者不改 sysctl：给 perf 二进制授予 capability（5.8+）
sudo setcap cap_perfmon+ep "$(readlink -f "$(which perf)")"
```

### 2.3 kptr_restrict：内核符号显示 [unknown] 的元凶

即便 paranoid 放开了，另一个 sysctl `kernel.kptr_restrict` 会**隐藏内核地址**（`/proc/kallsyms` 里显示成全 0），导致 perf 把内核函数显示为 `[unknown]`，火焰图里内核栈一片空白。

| 值 | 行为 |
|---|---|
| `0` | 不限制，内核地址可读（配合特权） |
| `1` | 无 `CAP_SYSLOG` 特权的用户看到地址被替换为 0 → perf 报告 `[unknown]`（**常见默认值**） |
| `2` | 更严格，多数特权路径也难以拿到地址，排查时一般不要设为 2 |

```bash
cat /proc/sys/kernel/kptr_restrict          # 常见为 1
echo 0 | sudo tee /proc/sys/kernel/kptr_restrict   # 临时放开，内核符号恢复可解析
# 永久：echo 'kernel.kptr_restrict = 0' | sudo tee /etc/sysctl.d/99-perf.conf
```

替代方案（不改系统设置）：给 perf 报告工具传入与运行内核**完全同版本**的带调试信息 `vmlinux`（或 kallsyms 文件）解析内核符号——`perf report --kallsyms=<file>`，旧版本支持 `-k/--vmlinux=<file>`（选项名视 perf 版本而定，`make modules_install` 或 debuginfo 包提供该文件）。

### 2.4 容器与云主机环境

容器**共享宿主机内核**：容器内的 perf 看到的 tracepoint、kallsyms、paranoid 都是宿主内核的。常见的 `Permission denied` 三步排查：

| 步骤 | 检查 | 说明 |
|---|---|---|
| ① | 宿主 `perf_event_paranoid` | 容器改不了它（/sys 是只读挂载或映射的宿主值），需要在宿主放开 |
| ② | 容器运行时限制 | seccomp 默认配置可能拦截 `perf_event_open()`；cgroup/运行时未授予 perf 权限时直接 EPERM |
| ③ | capabilities | 容器需要 `CAP_PERFMON`（5.8+）或 `CAP_SYS_ADMIN`，或干脆 `--privileged`（仅调试用） |

```bash
# 容器内验证三条命令（第 16 章坑表还有完整版）
cat /proc/sys/kernel/perf_event_paranoid     # ① 看继承自宿主的级别
capsh --print | grep -i perf                 # ③ 看 CAP_PERFMON 是否在能力集里
perf stat -e cpu-clock taskset -c 0 true     # ② 能否打开事件（软件事件先试）
```

云主机注意：超分/邻居噪声会让绝对数值漂移；跨内核迁移后 perf.data 里的内核符号失效，需要 `perf archive`（见 3 章表）。

### 2.5 虚拟机与 WSL2：没有 PMU 怎么办

| 环境 | PMU 硬件计数器 | 后果与对策 |
|---|---|---|
| 物理机 | 可用 | 完整功能 |
| KVM/VMware/云 VM（未透传 PMU） | 常不可用（嵌套虚拟化尤其） | 硬件事件 cycles/cache-misses 打不开 → **退化为软件事件**：`perf record -e cpu-clock -F 99 -g ./myapp`；`perf stat` 换 `-e cpu-clock,page-faults,context-switches` |
| WSL2 | 硬件 PMU 通常不可用（视 WSL 内核与主机而定） | 同上，用 `cpu-clock` 兜底做学习与流程演练；结论性测量回物理机 |
| ARM 服务器 | 可用但事件名不同 | 事件名随架构变化，`perf list` 实查（背景见《../02-系统原理/03-系统架构与选型.md》架构之争） |

### 2.6 验证环境三条命令

```bash
perf version                                    # 1) perf 本体可用且版本匹配
perf stat -e cpu-clock,cycles,instructions true # 2) 计数能打开（cycles 失败说明无 PMU 或权限不足）
perf list | head -5                             # 3) 事件列表可枚举（tracepoint 能列出说明符号链路正常）
```

三条都通过，才继续往下走。

## 3. 子命令总览大表

| 子命令 | 用途 | 最小示例 | 频度 |
|---|---|---|---|
| `perf stat` | 精确计数（不采样） | `perf stat ./myapp` | ★★★ |
| `perf record` | 采样记录到 perf.data | `perf record -F 99 -g ./myapp` | ★★★ |
| `perf report` | 交互式解读 perf.data | `perf report --no-children` | ★★★ |
| `perf top` | 实时热点（类 top 到函数级） | `perf top -p 1234` | ★★★ |
| `perf script` | 导出原始采样记录（喂火焰图/后处理） | `perf script -i perf.data > out.perf` | ★★★ |
| `perf list` | 列出本机可用事件 | `perf list \| grep cache` | ★★★ |
| `perf annotate` | 热点下钻到汇编/源码行 | `perf annotate -l` | ★★ |
| `perf trace` | 性能版 strace（跟踪系统调用） | `perf trace -p 1234` | ★★ |
| `perf probe` | 动态插桩（函数/行/变量级） | `perf probe -x ./myapp my_func` | ★★ |
| `perf sched` | 调度行为与延迟分析 | `perf sched record -- sleep 10` | ★★ |
| `perf mem` | 访存采样（延迟/命中层级） | `perf mem record ./myapp` | ★★ |
| `perf c2c` | 伪共享/缓存行争用分析 | `perf c2c record ./myapp` | ★★ |
| `perf diff` | 两个 perf.data 差异对比 | `perf diff old.data new.data` | ★★ |
| `perf inject` | 后处理注入（JIT 符号等） | `perf inject --jit -i perf.data -o jit.data` | ★ |
| `perf archive` | 打包符号文件供跨机分析 | `perf archive perf.data` | ★ |
| `perf timechart` | 系统级行为时间线 SVG | `perf timechart record -- sleep 10` | ★ |
| `perf data` | perf.data 格式转换（JSON 等） | `perf data convert --to-json` | ★ |
| `perf version` | 版本信息 | `perf version` | ★ |

## 4. perf stat：精确计数

### 4.1 基本用法与作用范围

| 目标 | 命令 | 说明 |
|---|---|---|
| 新进程 | `perf stat ./myapp` | 最常用：启动并统计整个生命周期 |
| 已运行进程 | `perf stat -p 1234 -- sleep 10` | `-p PID` 附着，用 `-- sleep N` 控制统计时长 |
| 指定线程 | `perf stat -t 4567 -- sleep 10` | `-t TID` 只看某线程 |
| 系统级全机 | `sudo perf stat -a -- sleep 10` | `-a` 所有 CPU 上所有进程 |
| 指定 CPU | `sudo perf stat -C 0,1 -- sleep 10` | `-C` 限定核，便于与 taskset 绑核配合 |
| 指定用户 | `sudo perf stat --uid 1000 -- sleep 10` | 按用户过滤 |

`--` 之后跟的是"统计多久"的命令（惯用 `sleep N`），不是被测对象本身——这是 stat 的一个惯用套路。

### 4.2 核心指标速览（详表见《04-性能分析与基准测试.md》4.3）

| 指标 | 一句话 | 异常信号 |
|---|---|---|
| `task-clock` | 占用 CPU 时间 | 与墙钟比看并行度 |
| `context-switches` | 上下文切换次数 | 突高 → 线程过多/锁竞争/IO 阻塞 |
| `cpu-migrations` | 核间迁移次数 | 高 → 缓存反复失效，考虑绑核 |
| `page-faults` | 缺页次数 | 高 → 工作集超内存或分配模式差 |
| `cycles` / `instructions` | 周期数 / 指令数 | 算 IPC 的原料 |
| `branches` / `branch-misses` | 分支数 / 预测失败 | miss 占比高 → 数据排序/分支重构 |

完整"指标含义 + 异常信号 + 修法"详表见《04-性能分析与基准测试.md》4.3，本章不重复，专注下面的**判断与进阶用法**。

### 4.3 IPC 判断表

| IPC（insn per cycle） | 典型解读 | 下一步 |
|---|---|---|
| < 0.5 | 停顿主导：访存等待（cache/TLB miss）或长延迟指令 | `-d` 看 cache-misses；第 11 章 |
| 0.5 ~ 1.0 | 一般：混合负载 | 结合 branch-misses、page-faults 交叉判断 |
| 1.0 ~ 2.0 | 良好：指令级并行较好 | |
| > 2.0 | 数值密集计算（SIMD/向量命中好） | 若仍慢，看算法与数据量，而非微优化 |

单看 IPC 会误判（等待也分内存/分支/依赖链），新内核可上 topdown 四分类（4.6 节）综合判断。

### 4.4 事件分组、修饰符与多路复用

```bash
# 花括号成组：组内事件在同一时间窗读数，比值（如 IPC）才严格可信
perf stat -e '{cycles,instructions}' ./myapp

# 修饰符：只测用户态 / 只测内核态
perf stat -e cycles:u ./myapp     # 只统计用户态
perf stat -e cycles:k ./myapp     # 只统计内核态
```

| 修饰符 | 含义 |
|---|---|
| `:u` | 只计用户态 |
| `:k` | 只计内核态 |
| `:h` | 只计 hypervisor（虚拟化层） |
| `:G` / `:H` | 排除 guest / 只计 host（KVM 场景） |
| `:I` | 排除 idle（非空闲计数） |
| `:p/:pp/:ppp` | 采样精确级（见 5.3，仅对采样有意义） |
| `:P` | 使用本机检测到的最大精确级 |

**多路复用（multiplexing）与缩放**：CPU 的物理计数器有限（常见每核 4~8 个通用计数器），事件超过上限时内核分时轮换，perf 会按"实际启用时间占比"**缩放**计数——输出里出现 `(xx.xx% of time ... scaled)` 提示。缩放比例低（<80%）时数值不可靠，对策：减事件数、用 `{}` 分组保证关键比值同窗测量。

### 4.5 详细模式与周期性输出

```bash
perf stat -d ./myapp          # 加 L1-dcache / LLC 相关事件
perf stat -d -d ./myapp       # 再加 dTLB / iTLB 等
perf stat -d -d -d ./myapp    # 再加预取等（事件随版本与 CPU 而异）

perf stat -I 1000 ./myapp     # 每秒输出一行，观察抖动/阶段性
perf stat -x, -o stat.csv ./myapp   # CSV 输出写文件，供脚本解析
perf stat -r 3 ./myapp        # 重复 3 次看方差（--repeat，老版本写法 --repeat 3）
```

| 参数 | 用途 |
|---|---|
| `-d` / `-dd` / `-ddd` | 逐级增加缓存/TLB 事件（可叠加写 `-d -d`） |
| `-I <ms>` | 周期性输出（>=100ms），看随时间的波动 |
| `-x <sep>` | 指定分隔符的 CSV 化输出 |
| `-o <file>` | 输出重定向到文件 |
| `-r <n>` | 重复 n 次报告均值与方差，对抗噪声 |
| `--no-scale` | 关闭多路复用缩放显示 |

### 4.6 topdown 四分类【现代分析方法】

```bash
# 新内核 + 较新 CPU（如 Ice Lake 及以后完整支持；Skylake 为近似口径）
perf stat --topdown ./myapp
```

| 分类 | 含义 | 对应优化方向 |
|---|---|---|
| `Frontend Bound` | 取指/译码受限（icache miss、译码瓶颈） | 代码体积、对齐、避免过长函数 |
| `Bad Speculation` | 分支预测失败 / 流水线清空 | 分支友好的数据布局、`[[likely]]` |
| `Backend Bound` | 执行后端受限（访存、端口） | 缓存布局、SoA、指令选择（第 11 章） |
| `Retiring` | 正常退休指令占比 | 越高越好；异常低则看前三项 |

topdown 把"IPC 低"进一步归因到流水线阶段，比单看 IPC 精确。支持情况视 CPU/内核而定（`perf stat -M TopdownL1` 是等价的 metric 写法）。

### 4.7 常用事件速查：perf list 三类

`perf list` 把本机事件分为硬件 / 软件 / tracepoint 三大类（完整入门表见《04-性能分析与基准测试.md》4.4）：

| 类别 | 代表事件 | 一句话用途 |
|---|---|---|
| Hardware cache | `cycles`、`instructions`、`branches`、`branch-misses`、`cache-references`、`cache-misses`、`L1-dcache-load-misses`、`LLC-load-misses` | 计数器直接读，开销近零 |
| Software | `cpu-clock`、`task-clock`、`page-faults`、`context-switches`、`cpu-migrations`、`minor-faults`、`major-faults`、`swaps` | **无 PMU 也能用**（VM/WSL2 兜底） |
| Tracepoint | `sched:sched_switch`、`syscalls:sys_enter_read`、`block:block_rq_issue`、`kmem:mm_page_alloc` | 内核预埋观测点（第 9 章） |

```bash
perf list | grep -E 'cache|LLC'     # 按关键词过滤
perf list tracepoint | grep sched:  # 只看调度类 tracepoint
```

## 5. perf record：采样原理【核心章节】

### 5.1 PMU 溢出采样原理

CPU 的 PMU 有若干可编程计数器。内核把计数器**预置一个初值**，每发生一次被计数的事件计数器加一，**加满溢出触发中断**，中断处理程序把当时的指令指针（RIP）和调用栈记进环形缓冲区，perf 用户态进程定期搬走。这就是"采样"的全部原理：

```text
 计数器装初值 N                CPU 执行程序                    PMU 溢出中断
 ┌──────────────┐      ┌───────────────────────┐      ┌──────────────────────┐
 │ cycles = MAX-N│      │ 指令1 指令2 指令3 ...   │      │  计数器归零溢出        │
 │  每个cycle +1 │ ───> │  （程序毫不知情）      │ ───> │  中断打点:            │
 └──────────────┘      └───────────────────────┘      │   RIP = 0x4012a7     │
                                                      │   栈 = f()<-g()<-main│
      ↑ 重装初值，继续数 ←────────────────────────────┘  写入 mmap 环形缓冲
 热点 = 被打点次数最多的 RIP/函数（大数定律：N 次采样里落在某函数的比例 ≈ 该函数 CPU 占比）
```

没有 PMU 时（部分 VM/WSL2），内核用**软件事件兜底**：`cpu-clock` 每达到一个时间片触发一次采样（精度略低、看不到硬件 cache 事件，但流程一致）。软件事件兜底用法见《04-性能分析与基准测试.md》4.4。

### 5.2 -F 频率 vs -c 周期

| 参数 | 机制 | 行为 | 适用 |
|---|---|---|---|
| `-F 99` | 频率模式 | 内核**动态调整**采样周期，维持平均每秒 99 个样本（自适应：忙核多采、闲核少采） | 绝大多数场景默认选择 |
| `-c 1000000` | 周期模式 | 固定"每 N 个事件采一次"，各核周期一致 | 需要跨核/跨运行严格可比时；某些 PMU 分析 |

```bash
perf record -F 99 -g ./myapp       # 频率模式
perf record -c 1000000 -g ./myapp  # 周期模式：每一百万个周期采一次
```

**-F 99 这个梗**：Brendan Gregg 的惯例采样率。若采样率是 100 的整数倍，可能恰好与"每 100ms/100Hz 周期性醒来的任务"**锁步（lockstep）共振**——每次都采到同一个相位，把周期任务误判成稳定热点。99 与 100 不同步，错开相位降低共振概率。顺带澄清：常被叫"质数频率"，但 99 = 9×11 并不是质数，**要点是"非倍数关系"而非质数性**（《04-性能分析与基准测试.md》2.2 噪声源表说的就是这个现象，只是那里把 99 称作了质数）。默认频率是 4000 Hz（老版本 1000，视版本而定），排查用 99~997 足够，还能把开销降到 1% 级。

### 5.3 精度与 skid：为什么热点会"偏移几条指令"

**skid（滑移）**：事件真正发生 → PMU 溢出 → 中断被投递 → 处理器停在的指令，中间已经过去了若干条指令。所以不修正时，采样到的 RIP 是"事件点之后若干条"的位置，短函数的热点会漂移。修正手段是精确采样（PEBS on Intel / IBS on AMD），用事件修饰符控制（语义依据 `perf-list(1)`）：

| 修饰符 | 语义 | 支持 |
|---|---|---|
| 无 | SAMPLE_IP 允许任意滑移 | 全平台 |
| `:p` | 要求固定滑移（constant skid） | Intel PEBS / AMD IBS |
| `:pp` | 要求接近 0 滑移 | Intel PEBS 支持到本级 |
| `:ppp` | 要求 0 滑移或随机化规避采样阴影 | 仅部分 Intel 特殊场景 |

```bash
perf record -e cycles:pp -F 99 -g ./myapp   # 显式高精确级
```

perf record 采样默认的 cycles 事件会**自动协商本机支持的最高精确级**（相当于优先尝试较高 precise_ip，打不开时自动降级，具体默认值视 perf 版本与 CPU 而定）——所以正常情况下热点偏移是可控的；显式写 `cycles:pp` 是社区常见写法，确保高精确级。虚拟机无 PEBS 时，skid 会明显变大，短函数归因可信度下降。

### 5.4 采样开销经验表

| 配置 | 典型开销 | 说明 |
|---|---|---|
| `-F 99` + fp 栈 | ~1% | 生产可用量级 |
| `-F 4000`（默认）+ fp | ~3-8% | 快速粗查 |
| `-F 99` + dwarf 栈（8KB 栈拷贝） | ~5-15% | 每个样本拷贝栈内存，I/O 变大 |
| `-F 4000` + dwarf | 可到 20-30%+ | 生产慎用，先降频 |
| `-F 99` + lbr 栈 | <1% | 硬件记录，几乎零额外成本 |
| tracepoint 全量跟踪（高频事件） | 5-50%+ | 事件越多开销越大，限时段使用 |

数字是量级参考，实际取决于栈深、事件频率、磁盘写速；对延迟敏感服务建议 99Hz + fp/lbr。

### 5.5 目标选择表

| 目标 | 命令 | 备注 |
|---|---|---|
| 直接跑命令 | `perf record -F 99 -g ./myapp arg` | 最干净，可复现 |
| 挂运行中进程 | `perf record -F 99 -g -p 1234 -- sleep 30` | 线上排查主力；`-- sleep N` 控制时长 |
| 指定线程 | `perf record -t 4567 -- sleep 10` | 多线程程序单线程归因 |
| 指定 CPU 核 | `perf record -C 0,1 -a -- sleep 10` | 与 taskset 绑核配合验证缓存局部性 |
| 系统级全机 | `sudo perf record -a -g -- sleep 10` | 找"整机上到底谁在烧 CPU" |
| 指定用户 | `sudo perf record --uid 1000 -a -- sleep 10` | 多租户机器 |
| 固定时长惯用法 | `... -- sleep 30` | record 后面跟的命令是"采多久"，`-p` 场景必须配 sleep |

### 5.6 常用附加参数表

| 参数 | 说明 | 示例 |
|---|---|---|
| `-g` | 采集调用栈（等价 `--call-graph fp`，可用 `--call-graph dwarf` 覆盖，第 6 章） | `perf record -g ./myapp` |
| `--call-graph <mode>` | 指定栈回溯方式：fp / dwarf / lbr | `--call-graph dwarf,16384` |
| `-F <n>` | 采样频率（默认 4000 视版本） | `-F 99` |
| `-c <n>` | 采样周期（与 -F 互斥） | `-c 1000000` |
| `-e <event>` | 指定事件（默认 cycles） | `-e cycles:pp` / `-e cpu-clock` |
| `-o <file>` | 输出文件（默认 perf.data） | `-o app.data` |
| `-T` | 记录样本时间戳 | 配合 `perf report -D` 看时间分布 |
| `-D <msecs>` | 延迟启动毫秒数，跳过初始化阶段 | `-D 2000` |
| `-a` | 系统级全机采样 | 需 root/权限 |
| `-p/-t/-C` | 目标：进程/线程/CPU | 见 5.5 |
| `--all-user` | 只采用户态（排除内核） | 权限受限时的替代方案 |
| `--all-kernel` | 只采内核态 | |
| `--per-thread` | 按线程独立缓冲 | 多线程采样失真排查 |
| `-b` | 采集分支栈（LBR 数据） | 配合 Intel PT/LBR 分析 |
| `--max-stack <n>` | 限制栈深上限（默认 127） | 控制 dwarf 数据量（第 6 章） |
| `-W` | 启用权重采样（dwarf/c2c 用） | |

### 5.7 采样多少才够

样本数 = 采样率 × 时长 × 在核线程数。判断"够不够"看的是**热点占比的置信度**，二项分布的 95% 置信区间约为 `±1.96×sqrt(p(1-p)/n)`：

| 总样本数 n | 对 10% 热点的波动（95% CI） | 结论 |
|---|---|---|
| ~100 | ±6% | 只能看数量级 |
| ~1,000 | ±1.9% | top 热点（>10%）可信 |
| ~10,000 | ±0.6% | 可分辨 1% 级差异 |
| ~100,000 | ±0.19% | 可做优化前后回归对比 |

```bash
# 看样本量与热点分布
perf report -i perf.data --stdio | head -20
perf evlist -v -i perf.data      # 事件与周期配置回看
```

经验法则：低频采样（99Hz）跑长一点（几十秒~几分钟），比高频跑短更稳；对比实验要保证两次样本数同量级。

## 6. 调用栈：三种方式深对比【全文最重要】

### 6.1 为什么必须有调用栈

没有调用栈时，perf 只知道采样那一刻的 RIP——知道"在哪"，不知道"从哪来"。同一个 `operator new` 可能被 30 个业务路径调用，无栈报告无法归因；有栈才能把热点挂到具体业务路径上（火焰图的整个大厦都建立在栈上）。**栈质量直接决定报告质量**，这也是 perf 最常见的翻车点。

### 6.2 三种回溯方式大对比

| 维度 | fp（帧指针） | dwarf（DWARF 展开） | lbr（Last Branch Record） |
|---|---|---|---|
| 原理 | 沿 rbp 链逐帧回读 | 用 `.eh_frame`/`.debug_frame` 的 CFI 指令虚拟展开栈 | Intel CPU 硬件记录最近 N 层分支/调用 |
| 前置条件 | **编译加 `-fno-omit-frame-pointer`**（默认 -O2 会省略 rbp！见《../06-构建与版本控制/01-构建工具GCC与CMake.md》2.3） | 编译加 `-g` 即可（无需特殊选项） | **无需任何编译选项** |
| 对库的要求 | 所有被采样的库都要开 fp（发行版库通常没开 → unknown） | 库要有调试符号（发行版要装 `-dbgsym`/debuginfo 包） | 无要求（硬件记录） |
| perf.data 体积 | 小（每样本只存一串地址） | **巨大**（每次采样拷贝整块栈内存，几百 MB 级常见） | 小 |
| 采样开销 | 最低之一 | 最高（栈拷贝 + 后处理展开） | 极低 |
| 栈深 | 无限（链一直读下去） | 无限（受 `--max-stack` 与拷贝大小限制） | **上限 32 层（常见值，视 CPU 型号）** |
| 平台限制 | 全平台 | 全平台 | **仅 Intel**（AMD 有 IBS 但机制不同；ARM 无） |
| 内核栈 | 可见（权限允许时） | 可见 | **LBR 默认不记录内核分支 → 内核帧缺失** |
| 推荐场景 | 自家全链路代码可控制编译选项 | 发行版二进制/混合栈最完整 | Intel 高频生产采样 |

#### fp 原理：rbp 链表遍历

x86-64 约定：`rbp` 指向当前栈帧基址，`[rbp]` 存上一帧的 rbp，`[rbp+8]` 存返回地址——一条链表，沿链走即可还原调用栈：

```text
 高地址 ┌─────────────────────┐
        │ main 的栈帧          │
        │  ...                │
        ├─────────────────────┤ ← rbp_main
        │ g() 的返回地址        │
        │ f() 的返回地址        │
        ├─────────────────────┤ ← rbp_f    （当前 rbp 停在这）
        │ f() 局部变量          │
        │ RIP 热点打点在这 ──── │ ← rsp
 低地址 └─────────────────────┘
 回溯：RIP → [rbp+8]=f 返回地址 → [rbp]=rbp_g → [rbp+8]=g 返回地址 → ...
```

一旦某帧被 `-O2` 优化掉 rbp（`-fomit-frame-pointer` 是默认），链条断裂，其后全部变成 `[unknown]`。

#### dwarf 原理：CFI 虚拟展开

编译器在 `.eh_frame`/`.debug_frame` 里为每条指令区间生成 CFI（Call Frame Information）规则：如何找回上一帧的 CFA（栈指针寄存器）与返回地址。perf 采样时**把整块用户栈内存拷进 perf.data**，事后按二进制的 DWARF 信息逐帧模拟展开。所以：需要 `-g`、数据巨大（默认拷贝 8192 字节/样本，可调）、但**对优化后的代码也完整**。

```bash
# 指定 dwarf 并加大栈拷贝（默认 8192，深栈程序要调大，如 16384）
perf record --call-graph dwarf,16384 -F 99 -o app.data ./myapp
```

#### lbr 原理：硬件分支记录

Intel CPU 维护一组 LBR 寄存器，自动记录**最近 32 层（常见值，视型号）分支/调用**。perf 采样时直接把这批寄存器读出来，从 CALL 指令序列重建栈——零栈拷贝、开销极低、无需编译配合；代价是深度上限 32、只 Intel、默认不含内核帧（需要权限与配置，且常缺失）。

```bash
perf record --call-graph lbr -F 99 ./myapp   # 仅 Intel
```

### 6.3 选择决策表

| 场景 | 首选 | 理由 |
|---|---|---|
| 自家服务可控制编译选项 | **fp**（编译加 `-fno-omit-frame-pointer`） | 开销低、栈无限、数据小 |
| 发行版二进制/栈里 unknown 多 | **dwarf** | 不依赖编译选项，最完整 |
| Intel 生产环境高频低开销采样 | **lbr** | 硬件记录几乎免费（注意 32 层与内核帧缺失） |
| VM/WSL2（无 PEBS/LBR） | fp 或 dwarf | lbr 依赖硬件 |
| 深调用链（>32 层）的框架代码 | dwarf（fp 也行） | lbr 32 层不够 |
| 无符号剥离过的二进制 | 都难 → 先解决符号 | 见第 16 章坑表 |

### 6.4 栈丢失（[unknown]）五大原因排查表

| 原因 | 特征 | 对策 |
|---|---|---|
| fp 未开（`-fno-omit-frame-pointer` 缺失） | fp 模式下栈只有 1~2 帧 | 编译加选项（《../06-构建与版本控制/01-构建工具GCC与CMake.md》2.3）；或换 `--call-graph dwarf` |
| 库无符号 | unknown 集中在 libc/发行版库那几帧 | 装 debuginfo（Ubuntu：`xxx-dbg`/`-dbgsym`；RHEL：`debuginfo-install`） |
| 内联展开 | 报告里子函数"消失"，时间归给调用者 | 属正常优化语义；用 `perf report` 的 inline 相关选项/看注释确认 |
| dwarf 栈大小不足 | 深栈程序底部截断 | `--call-graph dwarf,16384`（或 65536） |
| JIT 代码（Java/V8/部分 runtime） | 解释执行帧全 unknown | 运行时启用 perf jitdump + `perf inject --jit`（6.6） |

### 6.5 --max-stack 与 JIT 程序

`--max-stack N`（默认 127）限制每样本采集的最大栈深：fp/lbr 模式直接影响数据量与开销；dwarf 模式还要配合栈拷贝字节数。深框架（一层中间件一层调度器）建议 64~128。

**JIT 程序**：JVM/V8 等运行时代码在内存里动态生成，perf 无从得知符号 → 满屏十六进制。解法是运行时侧输出 jitdump 符号文件，事后注入：

```bash
perf inject --jit -i perf.data -o perf.jit.data   # 把 JIT 符号合并进数据
perf report -i perf.jit.data
```

## 7. perf report：解读热点

### 7.1 交互模式操作键速查

| 按键 | 作用 |
|---|---|
| `↑` / `↓` | 上下移动 |
| `Enter` / `→` | 在热点行上展开 callees 调用树（进入子函数分布） |
| `E` | 展开全部调用链 |
| `c` | 折叠全部调用链 |
| `g` | 循环切换调用图视图（flat/graph/caller-callee 等） |
| `a` | 对当前符号下钻到汇编/源码（跳 perf annotate） |
| `+` | 放大（zoom）到当前 DSO/线程等上下文 |
| `-` | 退出放大 |
| `/` | 搜索符号（正则） |
| `P` | 把直方图打印到 stdio（顺手存档） |
| `q` / `ESC` | 退出 |

不同版本 TUI 快捷键略有增减，以界面上方提示与 `perf-report(1)` 手册为准。

### 7.2 --no-children 语义【高频坑】

perf report **默认带 Children（累计）列**：某函数的 Children 开销 = 它及其全部下游调用的总和。于是 main 的 Children 永远接近 100%——它"经过"所有代码。**Self 才是函数自身开销**。

默认视图（Children 含累计）：

| Children | Self | Command | Symbol |
|---|---|---|---|
| 98.2% | 0.1% | myapp | `main` ← 累计几乎全部，无信息量 |
| 71.4% | 0.0% | myapp | `RequestHandler::process` |
| 62.9% | **31.2%** | myapp | `Serializer::to_json` ← 真热点 |
| 40.1% | 0.0% | myapp | `std::vector<int>::push_back` |

`perf report --no-children` 视图（只看自身）：

| Overhead | Command | Symbol |
|---|---|---|
| **31.2%** | myapp | `Serializer::to_json` ← 一眼锁定 |
| 8.4% | myapp | `MemPool::allocate` |
| 6.0% | libc | `memcpy@plt` |

| 读法 | 结论 |
|---|---|
| 只看 Children 排序 | 容易把"路过大户"当热点，改了半天没收益 |
| 先 `--no-children` 找 Self 大头 | 定位"自身耗时代码" |
| 再回默认视图看该函数的 Children 结构 | 分析它的下游贡献 |

### 7.3 --sort 字段与多维排序

| 排序字段 | 含义 | 用途 |
|---|---|---|
| `symbol` | 函数名（默认） | 热点定位 |
| `dso` | 所属二进制/库 | "时间在自己代码还是 libc/内核" |
| `comm` | 进程名 | 多进程程序归因 |
| `pid` / `tid` | 进程/线程号 | 线程负载均衡问题 |
| `cpu` | 采到样本的核 | NUMA/绑核问题 |
| `srcline` | 源码行（需 `-g`） | 直接到行号 |
| `parent` | 调用者 | 辅助归因 |
| `symbol_dso` | 函数+库 | 混排 |

```bash
perf report --sort symbol,dso            # 函数维度但带库归属
perf report --sort dso                   # 先看库维度分布
perf report --sort srcline --no-children # 直接定位源码行
perf report --stdio --header -i app.data # 脚本化输出 + 会话头部信息（命令、内核、架构）
```

### 7.4 C++ 符号与模板长名

perf report 对用户态 C++ 符号**默认已做 demangle**（`Serializer::to_json()` 而非 `_ZN10Serializer7to_jsonEv`）；内核符号可用 `--demangle-kernel`。模板实例名极长时会撑爆列，对策：

```bash
perf report --stdio | c++filt            # 手动 demangle 残留的 mangled 名
# 极端长名用 --fields/--sort 组合裁剪列，或导出后处理
perf report --stdio --fields overhead,symbol | less -S
```

mangled 名的编解码原理与 `c++filt` 详见《../02-系统原理/02-编译链接与加载原理.md》5.2（name mangling）。

### 7.5 按 DSO 维度定位"这是谁的问题"

```bash
perf report -i perf.data --sort dso
```

| DSO 归属 | 解读 |
|---|---|
| 自家二进制 | 自己代码的问题，直接修 |
| libc / libstdc++ | 看 Self 大头的函数——是 libc 本身慢，还是自己的调用模式差（如高频小 memcpy → 改数据布局） |
| `[kernel.kallsyms]` | 内核态：系统调用/页错误/锁陷入多，结合第 9/10 章 trace |
| 驱动 so | 驱动或硬件侧问题，找对应团队 |

### 7.6 perf diff：优化前后对比

```bash
perf diff baseline.data optimized.data    # 输出 Baseline / Delta 列
```

| 列 | 含义 |
|---|---|
| Baseline | 基线文件中该符号占比 |
| Overhead | 新文件占比 |
| Delta | 差值（负数=优化生效；注意是**百分比差**不是绝对时间差） |

判断优化是否真实生效（结合《04-性能分析与基准测试.md》2.1 的"无提升则回滚"纪律），更直观的方式是差异火焰图（第 12 章）。

## 8. perf annotate：下钻到汇编行

### 8.1 使用与前提

```bash
perf annotate -i perf.data                # TUI：在热点函数上按 a 进入
perf annotate -i perf.data --stdio        # 脚本化输出
perf annotate -i perf.data -l             # 显示源码行（需要 -g 编译）
```

| 前提 | 说明 |
|---|---|
| 函数符号 | 二进制未 strip |
| 源码行 | 编译带 `-g`（RelWithDebInfo，见《../06-构建与版本控制/01-构建工具GCC与CMake.md》2.4） |
| 指令归因 | 采样精确级越高越准（5.3 skid） |

**-O2 下源码行会"乱跳"**：编译器重排、循环展开、跨基本块指令调度后，一条源码行对应的多条指令不再相邻，行级归因只是近似——指令级视图比源码行级可信。

### 8.2 输出解读表

```text
 Percent |   Source code & Disassembly of myapp
         :
         :   4011a0:  push   %rbp
   0.5   :   4011a1:  mov    %rsp,%rbp
  18.2   :   4011a4:  mov    (%rdi,%rax,8),%rcx   ← 热点：一次访存占 18.2%
  12.7   :   4011a8:  add    %rcx,%rdx
   3.1   :   4011ab:  jne    4011a4               ← 跳转指令标注
```

| 元素 | 含义 | 用法 |
|---|---|---|
| 每行左侧百分比 | **该指令**被采样命中的占比 | 找最热的几条指令 |
| `←` / 跳转箭头 | 分支跳转方向与目标 | 识别循环体边界 |
| 连续多行同热点 | 常为**循环展开**现象：同一源码行的多条展开实例都热 | 归因到该源码行 |
| 热点在 `mov (%reg),...` | 访存指令 → cache miss 嫌疑（用 stat/第 11 章证实） | 改数据布局 |
| 热点在 `jne`/`je` | 分支密集 → branch-misses 证实 | 数据预排序、分支重构 |

### 8.3 与 gdb 反汇编的分工

| 工具 | 视角 | 场景 |
|---|---|---|
| perf annotate | **动态**：采样告诉你"哪些指令真的热" | 定位热点指令 |
| gdb `x/i $pc` / `disas`（《01-GDB程序调试.md》第 5 章） | **静态**：看任意时刻的指令现场 | 崩溃点分析、看具体指令语义 |

配合流程：perf annotate 找到热指令 → gdb 反汇编看完整上下文/寄存器语义 → 修改。崩溃类问题的现场分析全流程见《01-GDB程序调试.md》第 11 章。

## 9. tracepoint 与 perf probe：动态插桩【进阶高频】

### 9.1 静态 tracepoint

tracepoint 是**内核预埋的观测点**（源码里 `trace_sched_switch()` 调用，编译期存在、运行期可开关），开销远低于 printk。用户态可观测的只有"内核边界上的事件"（调度、系统调用、块 IO、页分配）：

```bash
perf list tracepoint | head -30            # 枚举本机全部 tracepoint
perf list tracepoint | grep sched:         # 按子系统过滤
```

常用 10 个事件表：

| 事件 | 触发时机 | 用途 |
|---|---|---|
| `sched:sched_switch` | 任务换入换出 CPU | off-CPU 分析基石（第 10 章） |
| `sched:sched_wakeup` | 任务被唤醒 | 配合算调度延迟 |
| `sched:sched_process_fork` / `_exec` / `_exit` | 进程创建/加载/退出 | 进程生命周期审计 |
| `sched:sched_migrate_task` | 任务核间迁移 | 绑核失效分析 |
| `syscalls:sys_enter_*` / `sys_exit_*` | 任意系统调用进入/返回 | 系统调用审计 |
| `block:block_rq_issue` / `block:block_rq_complete` | 块 IO 发起/完成 | IO 延迟分解 |
| `net:net_dev_queue` / `net:netif_receive_skb` | 网络发送/接收 | 流量分析（配合《../08-网络与系统工具/02-tcpdump网络抓包.md》抓包） |
| `kmem:mm_page_alloc` / `kmem:mm_page_free` | 物理页分配/释放 | 页分配热点 |
| `timer:timer_expire_entry` | 定时器到期 | 周期任务审计（配合 5.2 的共振分析） |
| `irq:irq_handler_entry` / `irq:irq_handler_exit` | 硬中断进出 | 中断风暴排查 |

```bash
# 记录全机调度切换事件（off-CPU 原料）
sudo perf record -e sched:sched_switch -a -g -- sleep 10

# 过滤：只记录有意义的切换（排除 idle，prev_pid>0）
sudo perf record -e sched:sched_switch -a --filter 'prev_pid > 0' -- sleep 10

# 单个 tracepoint 计数
sudo perf stat -e sched:sched_switch -a -- sleep 10
```

### 9.2 perf trace：性能版 strace

| 维度 | strace（ptrace） | perf trace（tracepoint） |
|---|---|---|
| 机制 | ptrace 每次系统调用两次停下被跟踪进程 | tracepoint 内核侧记录，进程几乎不被打断 |
| 开销 | 高，可达 **10 倍以上减速** | 低约一个数量级 |
| 输出 | 每次调用的参数与返回值 | 同样有参数/耗时，可加统计汇总 |
| 附着 | `-p PID` | `-p PID`（同样支持） |
| 统计 | 无 | `-s` 直接给每次系统调用的 min/max/avg + 标准差汇总 |

```bash
perf trace ./myapp                    # 跟踪新进程的每次系统调用（含耗时）
perf trace -p 1234                    # 附着运行中进程
perf trace -s ./myapp                 # 只输出按线程的系统调用统计汇总（min/max/avg/stddev）
perf trace -S ./myapp                 # 逐条 + 结尾汇总
perf trace --call-graph dwarf -p 1234 # 系统调用加调用栈（谁发起的）
perf trace -e 'epoll_*' ./myapp       # 只看匹配的系统调用（glob）
```

strace 适合"精确看某一次调用的参数"；perf trace 适合"看整体系统调用行为与延迟分布"。注意 `perf trace` 默认跟踪系统调用（`--syscalls` 默认开），错误码分布用 `--errno-summary`。

### 9.3 perf probe：函数/行/变量级动态插桩

tracepoint 只有内核预埋的那些位置；`perf probe` 用 DWARF 信息**现场生成 kprobe/uprobe**，任意函数、任意行、任意变量都能插。

```bash
# --- 用户态程序（必须 -x 指定二进制）---
perf probe -x ./myapp my_func                  # 函数级：进入时触发
perf probe -x ./myapp 'my_func:23'             # 行级：第 23 行
perf probe -x ./myapp 'my_func:23 user_id size'   # 同时读取变量（需 DWARF）
perf probe -x ./myapp 'my_func%return rv'      # 返回点探针（拿返回值 rv）

# C++ 对象成员（名字长要加引号；mangled 名可用 c++filt 解码，见《../02-系统原理/02-编译链接与加载原理.md》5.2）
perf probe -x ./myapp 'Payment::process amount'

# --- 内核函数（不需要 -x，需 root）---
sudo perf probe -a schedule                    # 内核函数
sudo perf probe -a 'tcp_sendmsg:size'          # 内核函数+变量

# --- 记录、列出、删除 ---
sudo perf record -e probe_myapp:my_func -a -- sleep 10   # 事件名格式 probe_<bin>:<func>
perf probe -l                                  # 列出已注册探针
perf probe -d 'probe_myapp:*'                  # 删除（-d 可接通配）
```

| 规则 | 说明 |
|---|---|
| 依赖 DWARF | 被插桩对象必须带调试信息（`-g`）；行级/变量级强依赖 |
| `-x` 只用于用户态二进制 | 内核函数不要 `-x`，用 `sudo perf probe -a` |
| 事件命名 | 用户态：`probe_<二进制名>:<函数>`；上线前 `perf probe -l` 确认 |
| 开销 | 每次命中都要记录，热路径函数慎重（先想清楚采样 vs 探针） |
| 权限 | 内核探针需要 root；用户态 uprobe 也受 paranoid 影响 |

### 9.4 典型场景组合表

| 问题 | 事件/探针组合 |
|---|---|
| 某系统调用单次耗时分布 | `perf trace -s -e 'read' ./myapp`（min/max/avg/stddev） |
| 锁竞争（glibc mutex 走 futex 系统调用，内核侧可见） | `perf trace -e 'futex' -s -p PID` + `syscalls:sys_enter_futex` 计数；用户态精确归因仍需第 10 章 off-CPU 栈 |
| 调度延迟 | `sched:sched_switch` + `sched:sched_wakeup`（第 10 章） |
| 大量短时进程/泄漏进程 | `sched:sched_process_fork` 全量记录 |
| 页分配热点 | `kmem:mm_page_alloc -a` 计数分布 |
| 自家代码某函数调用频率与参数 | `perf probe -x ./myapp 'func:line var'` |

### 9.5 与 ftrace / eBPF 的一句话关系

ftrace（挂载于 `/sys/kernel/tracing`，旧路径 `/sys/kernel/debug/tracing`）是内核最早的跟踪框架，tracepoint 基础设施由它提供，perf 通过 perf_events 消费同一批事件——两者是**兄弟**而非上下游；kptr_restrict 与 paranoid 同时管着两边。eBPF 是建立在 tracepoint/kprobe 之上、**可编程的后处理层**（第 13 章）。

## 10. 调度与 off-CPU 分析【弥补采样盲区】

### 10.1 核心认知：CPU 剖析只看得见"在跑的"

perf record 采样的是"正在 CPU 上执行的代码"。**线程在等 IO / 等锁 / 等换页时不在 CPU 上，一次也采不到**——纯 CPU 剖析会把一个"80% 时间在阻塞"的服务看成岁月静好。这是采样法的天生盲区：

```text
 时间 ────────────────────────────────────────────────────>
 线程A  [══on══][     off-CPU:等IO      ][══on══][ off:等锁 ][══on══]
 线程B  [══on═══][══on═══][off:等IO][═══════on═══════][off]
                ↑ perf record 只采到 ═ 段（on-CPU）；空白的 off 段一个样本都没有
 诊断:  CPU 高、延迟高   → on-CPU 采样（第 5/6/7 章）
        CPU 不高、延迟高 → off-CPU 分析（本章）
```

判断口诀（同《04-性能分析与基准测试.md》5.3 的 on/off-CPU 分流）：**CPU 使用率高 → on-CPU 火焰图；CPU 使用率低但延迟高 → off-CPU 分析**。

### 10.2 perf sched 子命令表

| 子命令 | 用途 |
|---|---|
| `perf sched record` | 记录调度事件（`-- sleep N` 控时长） |
| `perf sched latency` | **每任务调度延迟统计**（就绪→上 CPU 的等待） |
| `perf sched timehist` | 逐事件时间线：wait time / sch delay / run time 三列 |
| `perf sched map` | ASCII 上下文切换图（每核一列，两个字母代号） |
| `perf sched replay` | 用 mock 线程复现录到的调度时序，测调度器行为 |
| `perf sched script` | 导出原始记录（等同 perf script） |

```bash
sudo perf sched record -a -- sleep 10     # 系统级录 10 秒调度事件
perf sched latency                        # 看延迟 Top 表
```

`perf sched latency` 输出（列名依 perf 版本）：

```text
 Task                  | Runtime ms | Count | Avg delay ms | Max delay ms | Max delay start | Max delay end
 myworker:1234         |  812.04    | 1203  | avg: 3.524   | max: 48.069  | max start: 254752.31 | max end: 254752.36
```

| 列 | 含义 | 用法 |
|---|---|---|
| Runtime | 该任务**实际在 CPU 上**的时间 | 算真实 CPU 消耗 |
| Count | 计算延迟的次数（≈被唤醒次数） | 高 count + 低延迟 = 频繁但健康 |
| Avg delay | 平均调度延迟：**就绪（被唤醒）→ 真正上 CPU** 的等待 | 高 → CPU 竞争或被低优先级任务挤压 |
| Max delay | 最大单次调度延迟 | 毛刺来源（P99 尾延迟的内核侧证据） |
| Max delay start/end | 最差一次发生的时刻 | 对齐业务日志时间点 |

同名进程（多线程）默认合并，合并数在 `name:(N)` 中给出。**Avg delay 高 ≠ 业务慢**——还要区分"在 CPU 上慢"（on-CPU 剖析）与"上不了 CPU/在等待"（off-CPU 深挖）。

### 10.3 off-CPU 栈采法

换出 CPU 的时刻抓调用栈，聚合出来的就是"阻塞时卡在哪"。社区沿用 Brendan Gregg 的 off-CPU 思路（经典采法）：

```bash
# 1) 系统级记录 sched_switch（每次切换即有人离场）并带调用栈
sudo perf record -e sched:sched_switch -a -g -o offcpu.data -- sleep 10

# 2) 导出原始事件，后处理（把"切换出去的任务栈"按时长加权聚合）
sudo perf script -i offcpu.data > offcpu.perf
# 3) 自行聚合或喂给火焰图工具（BCC offcputime 更现成，见第 13 章）
```

| 局限 | 说明 |
|---|---|
| 栈深度 | `-g`（fp/dwarf）抓到的是**切换点的栈**：内核切换路径清晰，用户态深度取决于栈方式（第 6 章三选一照旧适用） |
| 只有离场时刻 | 你知道它"从哪睡的"，不知道"等多久醒来"——时长需从 sched_wakeup/switch 配对算（timehist 已帮你算好） |
| 更完整的方案 | eBPF（BCC `offcputime`、bpftrace `offcputime.bt`）：内核态直接配对 sched_switch 与唤醒，输出阻塞时长直方图（第 13 章） |

### 10.4 用户态锁等待的观测路径表

| 路径 | 事件/工具 | 看什么 |
|---|---|---|
| futex 系统调用（glibc mutex 争用时才陷入内核） | `perf trace -e 'futex' -s -p PID` | futex_wait 频率与单次时长 |
| syscall tracepoint 计数 | `sudo perf stat -e 'syscalls:sys_enter_futex' -p PID` | 争用总量趋势 |
| 调度侧证据 | `perf sched latency`（Count 高、delay 高）+ sched_switch 栈 | 自愿/非自愿切换占比 |
| 锁的持有者是谁 | perf 采不到（纯用户态临界区） | 用 valgrind helgrind/DRD 或 TSan 定位竞争（《02-Valgrind内存检测.md》4.4、《../06-构建与版本控制/01-构建工具GCC与CMake.md》2.4） |

上下文切换本身有成本（寄存器/栈切换 + 缓存污染；CFS 公平调度器按 vruntime 排队），`perf stat` 里 `context-switches` 与 `cpu-migrations` 突增就是第一信号——概念细节可配合《../08-网络与系统工具/01-Linux命令行速查.md》第 2 章 `vmstat` 的 cs 列交叉观察。

## 11. 内存与缓存：perf mem / c2c

### 11.1 perf mem：访存采样

```bash
sudo perf mem record ./myapp            # 采样访存（默认 loads+stores，依赖 PEBS/SPE/IBS）
sudo perf mem report                     # 报告（列随版本而异）
sudo perf mem record -t 4567 -- sleep 10 # 只采某线程
```

| 输出要素 | 含义 |
|---|---|
| Overhead | 该访存指令的采样占比 |
| Latency | load 延迟（周期数）——硬件提供（Intel PEBS load latency） |
| Data Source | **这次访问命中在哪一层**：L1/L2/LLC/本地 DRAM/远端节点——比单纯 miss 计数更有归因力 |
| HITM | 命中的是别的核**处于 Modified 态**的缓存行（最贵的命中，见 11.2） |
| Symbol/Srcline | 访存指令归属 |

（访存事件依赖平台：Intel 需支持 PEBS Load Latency；AMD 用 IBS；Arm64 用 SPE；不满足时报"not supported"——见第 16 章坑表。）

### 11.2 perf c2c：伪共享专治【C++ 高频】

**伪共享（false sharing）**：两个线程各自写**不同变量**，但这两个变量落在**同一个 64 字节缓存行**——一致性协议按行为单位失效，互相把对方的行打无效，性能崩塌而代码"看起来毫无共享"：

```text
      同一个 64B cache line
 ┌────────────────────────────────────────────────────────┐
 │  线程1 的 counterA        │  线程2 的 counterB          │
 └────────────────────────────────────────────────────────┘
 线程1 写 counterA  →  行在核1 变 Modified
 线程2 写 counterB  →  要独占同一行 → 把核1 的行打失效 → 核1 下次写再打回来
 结果：无任何逻辑共享，却反复跨核失效（HITM 风暴），多线程反而变慢
```

```bash
sudo perf c2c record ./myapp     # 记录（自动配置 mem-loads/mem-stores + 物理地址）
sudo perf c2c report             # TUI 报告
sudo perf c2c report --stdio     # 文本输出
```

报告结构与关键列（依据 `perf-c2c(1)`）：

| 表 | 关键列 | 解读 |
|---|---|---|
| Shared Data Cache Line Table（总表） | `Index`、`Cacheline`（物理地址）、`Rmt/Lcl HITM%`、`Total Loads/Stores`、`LLC Load Hitm`、`RMT Load Hit`、`Load Dram (Lcl/Rmt)` | 按 **HITM 总量排序**的争用行榜单：**Remote HITM（跨 NUMA 节点）最贵，Local HITM 次之** |
| Shared Cache Line Distribution Pareto（行内分布） | 行内 **offset**（0~63）、每个 offset 的 `HITM%`、涉及 PID、`Symbol`、Source:Line | 把 64 字节切开到字段级——**offset 直接对上结构体字段**，凶手现形 |

读图三步：① 总表找 HITM% 高的行 → ② 行内 Pareto 看哪些 offset 在互相打 → ③ 对照结构体定义定位字段，用 `alignas(64)` 隔离：

```cpp
// 伪共享修复：让两个计数器各占一行
struct Counters {
    std::atomic<uint64_t> a;                 // 与 b 同行 → 伪共享
    std::atomic<uint64_t> b;
};
struct FixedCounters {
    alignas(64) std::atomic<uint64_t> a;     // 独占一行
    alignas(64) std::atomic<uint64_t> b;     // 独占一行
};
```

字段重排消 padding、SoA 等更广的布局优化清单见《04-性能分析与基准测试.md》6.3。注意部分 CPU 有相邻行预取（Adjacent Cacheline Prefetch），此时用 `perf c2c report --double-cl` 按双行粒度分析；Arm64 报告默认按 peer 模式展示。

### 11.3 cache-miss 三层定位法

| 层级 | 事件（以本机 `perf list` 实查为准） | 说明 |
|---|---|---|
| L1 | `L1-dcache-load-misses`（`perf stat -d` 自带） | 最便宜，命中率极高属正常 |
| LLC（末级） | `LLC-load-misses` / `LLC-loads` | 高 → 工作集超出 LLC，数据布局/分块优化 |
| 远端内存（NUMA） | offcore/uncore 事件（Intel `OFFCORE_RESPONSE.*`、节点级事件） | 高 → 跨 NUMA 访问，绑核/内存本地化（`numactl`） |

```bash
perf stat -d ./myapp                       # L1/LLC 一网打尽
sudo perf stat -e LLC-load-misses,LLC-loads ./myapp
perf list | grep -i offcore                # 本机支持的远端事件实查
```

### 11.4 page-fault 高时的分析路径

| 步骤 | 命令 | 判断 |
|---|---|---|
| 1 分主次 | `perf stat -e minor-faults,major-faults ./myapp` | major（走磁盘）才是真问题 |
| 2 看频率 | `perf stat -e page-faults -I 1000 ./myapp` | 阶段性 or 全程 |
| 3 找分配点 | `perf record -e page-faults -g` 或 `kmem:mm_page_alloc -a` | 栈归因到分配路径 |
| 4 TLB 视角 | `perf stat -e dTLB-load-misses ./myapp` | TLB miss 高 → 考虑 hugepage（2MB 页减少 TLB 项压力，一句话：`hugeadm`/madvise） |
| 5 关联 | malloc 大量小块 → 分配器行为，见《04-性能分析与基准测试.md》6.2 heaptrack | |

## 12. 火焰图与差异对比工作流

### 12.1 三连命令回顾

火焰图原理（宽度=CPU 时间占比、纵向=调用深度）与标准三连详见《04-性能分析与基准测试.md》第 5 章，此处只给命令：

```bash
git clone https://github.com/brendangregg/FlameGraph && cd FlameGraph
perf record -F 99 --call-graph dwarf -o app.data ./myapp
perf script -i app.data > out.perf
./stackcollapse-perf.pl out.perf > out.folded
./flamegraph.pl out.folded > flame.svg
```

### 12.2 深入参数

| 参数 | 作用 | 说明 |
|---|---|---|
| `--width 1600` | 输出像素宽度 | 宽度越大细节越多 |
| `--title "myapp @ F99"` | 标题 | **注明采样率/时长/commit**，对比时救命 |
| `--reverse` | **反转火焰图**（自底向上倒转） | 聚合图找"子树大"的平台更适合看调用层次结构 |
| `--flamechart` | **时间顺序版**（不做聚合，按采样先后排布） | 看阶段性行为（初始化/稳态/收尾），但失去宽度=占比语义 |
| `--minwidth 0.1` | 最小可见矩形宽度 | 滤掉噪声细条 |
| `--colors` 配合 `--cp` | 配色 | 无本质影响 |

| 对比 | 聚合火焰图（默认） | flamechart（--flamechart） |
|---|---|---|
| 语义 | 宽度 = 时间占比（全时段聚合） | 位置 = 时间顺序（保留先后） |
| 擅长 | 找"总体最热路径" | 找"阶段性变化"（毛刺、缓存冷启动） |
| 代价 | 时间信息丢失 | 形态可能非常宽 |

`--reverse` 只改绘制方向不改变聚合语义；配合 `--flamechart` 使用时即"时间线+反转"组合。

### 12.3 differential 火焰图【优化前后对比标准流程】

单张火焰图回答"哪热"，**两张的差异**回答"我改完有没有真的变好"。用 FlameGraph 仓库的 `difffolded.pl` 生成红蓝差异图（红=占比上升、蓝=下降，基准是第一个输入文件）：

```bash
# ---- 第 1 步：改前采样（固定条件：同负载、同频率、同时长）----
perf record -F 99 --call-graph dwarf -o before.data ./myapp

# ---- 第 2 步：修改代码、重编译后采样 ----
perf record -F 99 --call-graph dwarf -o after.data ./myapp

# ---- 第 3 步：分别折叠调用栈 ----
perf script -i before.data | ./stackcollapse-perf.pl > before.folded
perf script -i after.data  | ./stackcollapse-perf.pl > after.folded

# ---- 第 4 步：diff 折叠数据并渲染（红=变多/新问题，蓝=变少/已优化）----
./difffolded.pl before.folded after.folded > diff.folded
./flamegraph.pl --title "before vs after" diff.folded > diff.svg
```

| 读法 | 结论 |
|---|---|
| 目标函数变蓝 | 优化生效 |
| 别处变红 | 优化引入的新热点（被掩盖的问题浮出） |
| 全图几乎不变 | 优化无效（回滚，《04-性能分析与基准测试.md》2.1 纪律） |

### 12.4 优化闭环流程

```text
 基线采样(before) ──> 火焰图定位 ──> differential 确认假设 ──> 修改代码
      ↑                                                        │
      └────── 回归验证(after再对比，蓝=改善红=回归) ←── 重采样(after) ←┘
                     ↓ 每轮改动独立提交
                git commit（规范见《../06-构建与版本控制/03-Git版本控制.md》第 12 章工作流，perf.data 不入库）
```

每轮只改一个变量、独立提交，出问题可 git revert 定位到具体改动（《../06-构建与版本控制/03-Git版本控制.md》第 6、7 章）。

## 13. eBPF 时代：perf 的现在与未来

### 13.1 关系定位

| 层 | 角色 |
|---|---|
| 内核 perf_events 子系统 | **基础设施**：PMU 计数、采样、tracepoint/kprobe/uprobe 的数据通道 |
| perf 工具 | 官方前端：计数/采样/跟踪的通用分析器 |
| eBPF | 建立在 tracepoint/kprobe 上、**可编程的内核态后处理**：事件聚合、直方图、条件过滤都放进内核执行，省去全量导出 |
| bpftrace / BCC | eBPF 的前端（单行语言 / Python 库），大量"perf 要导出后处理"的场景一行搞定 |

### 13.2 perf vs bpftrace vs BCC

| 维度 | perf | bpftrace | BCC |
|---|---|---|---|
| 学习曲线 | 平缓（命令+参数） | 中（DSL，awk 风格） | 高（写 Python/C） |
| 一行上手 | `perf record -F 99 -g` | `bpftrace -e '...'` | 需写脚本 |
| 定制聚合 | 弱（perf script 导出后自处理） | 强（count/hist/lquantize 原生） | 最强 |
| 热点采样（PMU） | **独有**（eBPF 不做 PMU 采样） | 无 | 无 |
| 生产部署 | 随内核自带 | 需装 bpftrace + 内核 BTF/权限 | 需装 BCC |
| 典型用途 | CPU 剖析、计数、火焰图原料 | 快速回答"谁在做什么、等了多久" | 生产监控 agent（自定义指标） |

### 13.3 bpftrace 两个经典单行

```bash
# 1) 按进程统计系统调用次数（对应 perf trace -s 的聚合视图）
sudo bpftrace -e 'tracepoint:raw_syscalls:sys_enter { @[comm] = count(); }'

# 2) off-CPU 阻塞时长直方图（简化版：换出记时点，换回算差值）
sudo bpftrace -e 'tracepoint:sched:sched_switch {
  if (args->prev_pid > 0) { @start[args->prev_pid] = nsecs; }
  $t = @start[args->next_pid];
  if ($t) { @offcpu_us = hist((nsecs - $t) / 1000); delete(@start[args->next_pid]); }
}'
```

完整版（带进程名、按线程）是 BCC 的 `offcputime` 与 bpftrace 自带的 `offcputime.bt`。bpftrace 语法详见其官方手册（`bpftrace -l` 列探针、`bpftrace --info` 看环境）。

### 13.4 什么时候仍然用 perf

| 场景 | 为什么仍是 perf |
|---|---|
| 无 root 的快速用户态采样 | bpftrace/BCC 对权限要求更高（CAP_BPF），perf 配 paranoid=2 就能采用户态 |
| CPU 热点与火焰图标准工具链 | PMU 采样是 perf 独有；FlameGraph 工具链以 perf script 为默认前端 |
| 硬件事件分析（cache/分支/topdown） | PMU 事件计数/比值的成熟出口 |
| 微基准与端到端回归 | perf stat 的精确计数 + -r 重复方差，作为裁判很稳（配合《04-性能分析与基准测试.md》第 8 章 benchmark） |

## 14. 实战案例集

### 14.1 案例 1：线上服务 CPU 飙到 90%

| 环节 | 命令 | 输出特征 | 结论 |
|---|---|---|---|
| 现象 | `pidstat -p 1234 1` | `%usr` 90%+，持续 | CPU 型问题，走采样 |
| 第一步：分类 | `perf stat -p 1234 -- sleep 10` | IPC=0.4（insn/cycle） | 停顿主导——访存受限 |
| 第二步：采样 | `perf record -F 99 --call-graph dwarf -p 1234 -- sleep 30` | — | 发行版依赖多，直接 dwarf |
| 第三步：归因 | `perf report --no-children --sort symbol` | `Serializer::to_json` Self 31% | 单函数独占三成 |
| 第四步：下钻 | `perf annotate` | 热点集中在 `memcpy` 调用与字符串拼接指令 | 拷贝密集 |
| 修复 | 拼接前 `reserve()`、`string_view` 传参避免拷贝（清单见《04-性能分析与基准测试.md》第 9 章） | — | — |
| 验证 | 重采 + `perf diff`/差异火焰图 | 该函数变蓝，IPC 升至 0.9 | 闭环 |

### 14.2 案例 2：接口偶发 P99 毛刺（CPU 正常）

| 环节 | 命令 | 输出特征 | 结论 |
|---|---|---|---|
| 现象 | 监控 P99 偶发 200ms，CPU 仅 30% | on-CPU 采样（`perf record -F 99 -g -p PID`）无异常热点 | **不是算得慢，是在等** → 第 10 章 |
| 调度侧 | `sudo perf sched record -a -- sleep 30` → `perf sched latency` | 某 worker Max delay 48ms，Count 高 | 就绪后长时间上不了 CPU |
| 阻塞栈 | `sudo perf record -e sched:sched_switch -a -g -- sleep 30` + `perf script` | 栈大量停在 `futex_wait` | **等锁** |
| 锁频率 | `perf trace -e 'futex' -s -p PID` | futex_wait 次数高、单次耗时集中 | 争用型锁 |
| 修复 | 缩小临界区（copy 后再 unlock）、热点计数器 `alignas(64)` 隔离 | — | — |
| 交叉验证 | helgrind/TSan 扫竞争（《02-Valgrind内存检测.md》4.4）确认无逻辑竞争 | — | 闭环 |

### 14.3 案例 3：多线程程序多核扩展性差

| 环节 | 命令 | 输出特征 | 结论 |
|---|---|---|---|
| 现象 | 4 线程比 1 线程只快 1.8 倍 | — | 扩展性瓶颈 |
| 计数证据 | 逐线程数跑 `perf stat -a`（1/2/4 线程各一次） | `LLC-load-misses`、cache-misses 随线程数**暴涨**，IPC 随之跌 | 缓存一致性流量问题 |
| 定位 | `sudo perf c2c record ./myapp` → `perf c2c report` | 总表某 cache line HITM 占大头；行内 Pareto 显示 offset 0 和 offset 8 两个位置交替失效 | **伪共享**：两字段同行 |
| 修复 | 结构体字段 `alignas(64)` 隔离（11.2 示例） | — | — |
| 验证 | 修复后同命令重跑 c2c + stat | HITM 行消失，4 线程加速比 3.6 | 闭环 |

三案例的共同骨架：**stat 定性 → record 定位 → annotate/c2c 定点 → 修复 → diff 回归**，这也是第 15 章卡片的主线。

## 15. 快速参考卡片

| 症状 | 命令链（可整段复制） |
|---|---|
| CPU 高，不知热点在哪 | `perf stat -p $(pidof myapp) -- sleep 10` → `perf record -F 99 --call-graph dwarf -p $(pidof myapp) -- sleep 30` → `perf report --no-children --sort symbol,dso` → `perf annotate` |
| 想要火焰图 | `perf record -F 99 --call-graph dwarf -o app.data ./myapp` → `perf script -i app.data > out.perf` → `./stackcollapse-perf.pl out.perf > out.folded` → `./flamegraph.pl out.folded > flame.svg` |
| CPU 不高但延迟高（毛刺） | `sudo perf sched record -a -- sleep 30` → `perf sched latency` → `sudo perf record -e sched:sched_switch -a -g -- sleep 30` → `sudo perf script -i perf.data > off.perf`（或 BCC `offcputime`） |
| 怀疑锁竞争 | `perf stat -e 'syscalls:sys_enter_futex' -p $(pidof myapp) -- sleep 10` → `perf trace -e 'futex' -s -p $(pidof myapp)` → `perf record -e sched:sched_switch -a -g` 看阻塞栈 |
| 怀疑内存带宽/cache 受限 | `perf stat -d -r 3 ./myapp` → `perf stat -e LLC-load-misses,LLC-loads ./myapp` → `perf mem record ./myapp` → `perf mem report` |
| 怀疑伪共享（多线程扩展差） | `perf stat -a` 多线程数对比看 miss 涨幅 → `sudo perf c2c record ./myapp` → `sudo perf c2c report --stdio`（看 HITM 行 + offset） |
| 系统调用频繁/慢 | `perf trace -s ./myapp` → `perf trace --call-graph dwarf -e '感兴趣调用' ./myapp` → 自家代码 `perf probe -x ./myapp 'func:line'` + `perf record -e probe_myapp:func` |
| 调度延迟 / 换 CPU 慢 | `sudo perf sched record -a -- sleep 10` → `perf sched latency`（Avg/Max delay）→ `perf sched timehist` 看逐次 wait/sch delay/run |
| 优化前后对比 | `perf record -F 99 --call-graph dwarf -o b.data ./myapp` →（改代码）→ `perf record -F 99 --call-graph dwarf -o a.data ./myapp` → `perf script -i b.data \| ./stackcollapse-perf.pl > b.folded` → `perf script -i a.data \| ./stackcollapse-perf.pl > a.folded` → `./difffolded.pl b.folded a.folded > d.folded` → `./flamegraph.pl d.folded > diff.svg` |
| 权限不通先自查 | `cat /proc/sys/kernel/perf_event_paranoid` → `cat /proc/sys/kernel/kptr_restrict` → `perf stat -e cpu-clock true` |

## 16. 常见问题与坑

| 问题 | 原因与解决方案 |
|---|---|
| `WARNING: perf not found for kernel xxx` | linux-tools 与运行内核版本不匹配。`sudo apt install linux-tools-$(uname -r)`（注意让 `$(uname -r)` 在你的 shell 展开成实际版本）；RHEL 系装 `perf` 包 |
| `perf record` 报 Permission denied / Operation not permitted | paranoid 级别过高（2.2 分级表速查：2 只许用户态进程级、1 加内核、0 加系统级、-1 全开）或容器无 CAP_PERFMON。`echo 1 \| sudo tee /proc/sys/kernel/perf_event_paranoid`；容器按 2.4 三步查；退路：`--all-user` 只采用户态、`-e cpu-clock` 软件事件 |
| 内核函数全显示 `[unknown]` | kptr_restrict=1 隐藏了内核地址。`echo 0 \| sudo tee /proc/sys/kernel/kptr_restrict`，或给 perf 传同版本 vmlinux/kallsyms（2.3） |
| 调用栈大片 `[unknown]`/只有两三帧 | fp 模式下编译没加 `-fno-omit-frame-pointer`（发行版库基本都没加）。换 `--call-graph dwarf,16384`；自家代码则加编译选项（《../06-构建与版本控制/01-构建工具GCC与CMake.md》2.3） |
| 把 Children 当成自身开销 | perf report 默认 Children 列含**累计**占比。找热点必须 `--no-children` 看 Self（7.2 的双视图示例） |
| perf.data 巨大（几百 MB / GB） | dwarf 模式每次采样拷贝整块栈内存。降频 `-F 99`、`--max-stack` 限深、换 fp/lbr；分析机磁盘留足空间 |
| 采样让服务变慢（延迟上升） | 开销过高：默认 4000Hz 太猛。`-F 99` 起步；栈方式换 lbr（Intel）；限时长 `-- sleep 10`；生产环境先在预发验证 |
| VM/WSL2 上 cycles/cache 事件打不开 | 嵌套虚拟化无 PMU。兜底 `-e cpu-clock` 软件事件（流程不变，只是没有硬件 cache 视角）；结论性测量回物理机（2.5） |
| `perf c2c` 提示硬件不支持 | c2c 依赖访存采样能力：Intel 需 PEBS Load Latency、AMD 需 IBS（部分代际如 Zen3 不支持）、Arm64 需 SPE 且要内核使能（`perf-arm-spe`）。换机器或退回 `perf mem`/stat 的 LLC miss 层面证据 |
| 报告里 libc/memcpy 占比虚高 | FP 缺失或精确保留问题导致时间被归因到"看得见的最后几帧"。先修调用栈质量（dwarf），再看 DSO 分布（7.5）——别急着优化 libc |
| 容器里 perf 完全不可用 | 宿主 paranoid + 容器 seccomp 拦 perf_event_open + 无 capabilities 三连。宿主放开 → 容器加 CAP_PERFMON 或 `--privileged` 调试 → 或改在宿主侧用 `-p` 直接采容器进程 PID |
| `perf list` 里找不到教程提到的 tracepoint 名 | 版本/配置差异（部分需 `CONFIG_TRACEPOINTS`、内核模块）。用 `perf list tracepoint \| grep -i 关键词` 实查替代名；syscalls 类需要 `CONFIG_FTRACE_SYSCALLS` |
| 改完 paranoid 重启又失效 | `echo > /proc/...` 只改运行时。持久化写 `/etc/sysctl.d/99-perf.conf` 后 `sudo sysctl --system`（2.2） |
| 热点函数每次采样位置差几条指令（annotate 归因抖动） | skid（5.3）。用 `cycles:pp` 高精确级；注意 VM 无 PEBS 时无法避免 |
| 火焰图顶部一大片同色但很"碎" | 内联/短函数大量小矩形属正常；若宽度可疑，检查采样共振（换 `-F 99`/97）与样本量是否足够（5.7） |
| 跨机器分析 perf.data 符号缺失 | 采样机的二进制/库未带到分析机。采样机上 `perf archive perf.data` 打包符号文件，解压到分析机同路径再 `perf report` |
| 采样结果两次差很多 | 噪声（频率漂移/邻居/冷热页）。`perf stat -r 3` 看方差、taskset 绑核、预热后测量；详见《04-性能分析与基准测试.md》2.2 噪声源表 |

---

**衔接备忘**：方法论与工具全景 →《04-性能分析与基准测试.md》；编译选项（-g/-fno-omit-frame-pointer/sanitizer）→《../06-构建与版本控制/01-构建工具GCC与CMake.md》2.3/2.4；崩溃与反汇编现场 →《01-GDB程序调试.md》；mangled 符号 →《../02-系统原理/02-编译链接与加载原理.md》5.2；竞争检测 →《02-Valgrind内存检测.md》4.4；大盘命令 →《../08-网络与系统工具/01-Linux命令行速查.md》第 2 章；架构差异背景 →《../02-系统原理/03-系统架构与选型.md》；优化前后提交纪律 →《../06-构建与版本控制/03-Git版本控制.md》第 12 章。

---

上一篇：《02-Valgrind内存检测.md》　｜　下一篇：《04-性能分析与基准测试.md》　｜　模块索引：《../README.md》
