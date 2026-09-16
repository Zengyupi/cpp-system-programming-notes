# strace 系统调用跟踪

> 本节目标：讲解 strace 跟踪进程系统调用的方法——基本输出解读、`-e` 过滤、`-c` 汇总统计、时间戳定位、子进程跟踪与 attach 运行中进程。学完后能够回答"程序卡在哪、为什么慢、为什么报权限/文件错误、实际读了哪些文件、连了哪个地址"，并能在不改代码、不动线上进程的前提下排查问题。本篇输出均在 Ubuntu 24.04（strace 6.8）实跑验证。运行时下断点配合《../07-调试与测试/01-GDB程序调试.md》，内存错误配合《../07-调试与测试/02-Valgrind内存检测.md》，性能热点配合《../07-调试与测试/03-perf性能剖析.md》。

## 本章速览

- [0. strace 解决什么问题](#0-strace-解决什么问题)
- [1. 基本用法与输出解读](#1-基本用法与输出解读)
- [2. 过滤：只看关心的系统调用](#2-过滤只看关心的系统调用)
- [3. 汇总统计：时间花在哪](#3-汇总统计时间花在哪)
- [4. 时间戳与单次耗时](#4-时间戳与单次耗时)
- [5. 跟踪子进程](#5-跟踪子进程)
- [6. 附加到运行中进程](#6-附加到运行中进程)
- [7. 输出到文件与字符串截断](#7-输出到文件与字符串截断)
- [8. trace 集合速查](#8-trace-集合速查)
- [9. 实战工作流](#9-实战工作流)
- [10. 快速参考卡片](#10-快速参考卡片)
- [11. 常见问题与坑](#11-常见问题与坑)

---

测试样例（沿用《05-readelf工具.md》的 demo）：

```cpp
// demo.c
#include <stdio.h>
int g_counter = 42;
static int helper(int x){ return x * 2; }
int add(int a, int b){ return helper(a + b); }
int main(void){ printf("sum=%d\n", add(1, 2)); return 0; }
```
```bash
gcc -g -O0 -c demo.c -o demo.o
gcc demo.o -o demo_app
```

---

## 0. strace 解决什么问题

程序"行为不对"时，GDB 要下断点、perf 要跑采样，而 **strace 直接看程序与内核的每一次交互**：打开了哪个文件、读了哪个地址、写了多少字节、卡在哪个调用。它是三者的"第一现场"：

| 工具 | 回答的问题 | 代价 |
| --- | --- | --- |
| `strace` | 程序**做了什么系统调用**（I/O、网络、文件） | 慢 10~100 倍，只适合短时 |
| GDB | 程序**内部状态**（变量、调用栈、断点） | 需要符号、交互 |
| perf | 程序**时间花在哪**（CPU 热点） | 采样，低开销 |
| Valgrind | 内存**错误与泄漏** | 慢 10~50 倍 |

典型场景：报"文件不存在"但文件明明在、启动慢、服务卡住、权限拒绝、找不到 .so、"Address already in use"。

```bash
# 30 秒上手
strace ./demo_app          # 完整跟踪到程序退出
strace -c ./demo_app       # 只给汇总统计
strace -p 1234             # 附加到运行中的 PID
```

---

## 1. 基本用法与输出解读

```bash
strace [选项] 命令            # 启动并跟踪
strace [选项] -p PID         # 附加到运行中进程
```

输出格式固定：**`系统调用(参数) = 返回值`**，全部写到 **stderr**：

```bash
$ strace -e trace=write,openat,read ./demo_app
openat(AT_FDCWD, "/etc/ld.so.cache", O_RDONLY|O_CLOEXEC) = 3
openat(AT_FDCWD, "/lib/x86_64-linux-gnu/libc.so.6", O_RDONLY|O_CLOEXEC) = 3
read(3, "\177ELF\2\1\1\3\0\0\0\0\0\0\0\0\3\0>\0\1\0\0\0\220\243\2\0\0\0\0\0"..., 832) = 832
write(1, "sum=6\n", 6sum=6
)                  = 6
+++ exited with 0 +++
```

| 片段 | 含义 |
| --- | --- |
| `openat(AT_FDCWD, "/etc/ld.so.cache", O_RDONLY\|O_CLOEXEC) = 3` | 打开动态链接器缓存，返回 fd 3 |
| `read(3, "\177ELF..." , 832) = 832` | 从 fd 3 读 832 字节（libc 的 ELF 头），读到 832 |
| `write(1, "sum=6\n", 6)` | 向 fd 1（stdout）写 6 字节——`printf` 底层就是它 |
| `+++ exited with 0 +++` | 正常退出，退出码 0 |

> 程序刚启动就有一堆 openat：动态链接器在找 `ld.so.cache` 和各 `.so`。**"找不到 .so"、路径不对的问题，从最前面几行一眼看出它实际找的是哪个路径**。返回值 `-1` 才是错误，后面跟着 errno（如 `= -1 ENOENT (No such file or directory)`）。

---

## 2. 过滤：只看关心的系统调用

```bash
strace -e trace=openat ./demo_app          # 只看文件打开
strace -e trace=write,read,openat ./app    # 逗号分隔多个
strace -e trace=network ./app              # 分类集合：socket/connect/bind/accept...
strace -e trace=file ./app                 # openat/close/unlink/stat...
strace -e trace=process ./app              # fork/execve/exit...
strace -e trace=signal ./app               # 信号相关
strace -e trace=memory ./app               # mmap/brk/mprotect...
```

看程序**实际加载了哪些库**：

```bash
$ strace -e trace=openat ./demo_app 2>&1 | grep -E '\.so|ld-linux'
openat(AT_FDCWD, "/lib/x86_64-linux-gnu/libc.so.6", O_RDONLY|O_CLOEXEC) = 3
```

> 报 `error while loading shared libraries` 时，这条命令直接告诉你它找的是哪个路径、哪个 `.so` 没找到。生产环境排查"为什么这个文件没被读到"，先 `-e trace=openat` 跑一遍看路径拼对没有。

---

## 3. 汇总统计：时间花在哪

```bash
$ strace -c ./demo_app
sum=6
% time     seconds  usecs/call     calls    errors syscall
------ ----------- ----------- --------- --------- ----------------
 25.00    0.000019          19         1           munmap
 25.00    0.000019           6         3           brk
 23.68    0.000018          18         1           write
 14.47    0.000011           3         3           fstat
 11.84    0.000009           9         1           getrandom
  0.00    0.000000           0         1           read
  ...
------ ----------- ----------- --------- --------- ----------------
100.00    0.000076           2        34         1 total
```

| 列 | 含义 |
| --- | --- |
| `% time` | 该类调用累计耗时占比（**找热点看这一列**） |
| `seconds` / `usecs/call` | 总耗时 / 单次平均耗时 |
| `calls` | 调用次数 |
| `errors` | 出错次数（`= -1` 的调用） |
| 末行 `total` | 全部 34 次调用，1 次错误 |

- demo 太短，统计看不出热点；**换成真实服务**：`strace -c -p PID` 运行一段时间再 Ctrl-C，立刻看到哪类调用最耗时、哪类在大量报错（如 `errors` 列很高的 `openat`/`connect` 就是问题点）。
- "启动慢"排查：`strace -c ./app`，`% time` 高的类别再下钻到具体调用（第 4 节）。

---

## 4. 时间戳与单次耗时

```bash
$ strace -tt -T -e trace=write ./demo_app
10:19:44.187429 write(1, "sum=6\n", 6sum=6
)  = 6 <0.000030>
10:19:44.187720 +++ exited with 0 +++
```

| 选项 | 效果 |
| --- | --- |
| `-t` | 秒级时间戳 |
| `-tt` | 微秒级时间戳（更常用） |
| `-T` | **每次调用的耗时** `<微秒>` |

- 定位"卡在哪"：`strace -tt -T ./app`，找到 `<...>` 里耗时异常大的一行，那就是瓶颈调用。
- 服务"偶发变慢"：先 `-tt -T` 记录，慢的那次去看前后行，通常卡在 `read`（等网络/管道）、`connect`（对端不响应）或大量 `openat`。

---

## 5. 跟踪子进程

```bash
$ strace -f -e trace=clone,execve,write sh -c 'echo child-ok'
execve("/usr/bin/sh", ["sh", "-c", "echo child-ok"], 0x7ffdd9f65e38 /* 22 vars */) = 0
write(1, "child-ok\n", 9child-ok
)               = 9
+++ exited with 0 +++
```

- `-f`（`--follow-forks`）：同时跟踪 `fork`/`vfork`/`clone` 出来的子进程。**服务器 fork 子进程/多线程模型不带 `-f`，只能看到主进程的调用**。
- 跟踪由命令启动的一整棵进程树：`strace -f ./server`。
- 输出里每个进程的调用会交错出现，配合 `-o` 落盘后按行号区分。

---

## 6. 附加到运行中进程

线上排查不动进程、不加调试信息，直接挂上去看：

```bash
$ strace -p $(pgrep -f 'http.server 18084') -e trace=accept4,read,write -o /tmp/att.log &
$ curl -s -o /dev/null http://127.0.0.1:18084/    # 触发一次请求
$ cat /tmp/att.log
accept4(3, {sa_family=AF_INET, sin_port=htons(52872), sin_addr=inet_addr("127.0.0.1")}, [16], SOCK_CLOEXEC) = 4
```

stderr 侧会提示挂载成功/脱离：

```text
strace: Process 15328 attached
strace: Process 15328 detached
```

要点与坑：

- **权限**：普通用户只能 attach 自己的进程；attach 别人的进程或系统服务需要 `root`；Ubuntu 默认 `ptrace_scope=1` 会禁止跨用户 attach（报 `Operation not permitted`）。
- **性能影响**：每个系统调用都经过 ptrace，进程会慢 10~100 倍。**生产环境短时挂、复现完立即 kill strace**，不要长时间挂着。
- 排查流程：`ps` 找 PID → `strace -p PID -e trace=file,network -o /tmp/x.log` → 复现问题 → `kill $(pgrep strace)` → 分析日志。

---

## 7. 输出到文件与字符串截断

```bash
strace -o /tmp/trace.log ./app          # 默认写 stderr，-o 落盘
strace -s 200 -e trace=write ./app      # 字符串参数/返回值最大 200 字节（默认 32）
strace -o /tmp/t.log -e trace=openat ./app && grep ENOENT /tmp/t.log
```

- 默认字符串只显示前 32 字节，`read` 大块数据会被截断成 `"\177ELF\2\1..."`；看完整参数（如 write 的完整内容）加 `-s`。
- 大日志用 `-o` 落盘再 `grep`，避免刷屏丢信息。

---

## 8. trace 集合速查

| 集合 | 包含的典型调用 | 场景 |
| --- | --- | --- |
| `file` | openat、close、read、write、unlink、stat、mkdir | 文件 I/O、缺文件、权限 |
| `process` | fork、vfork、clone、execve、exit_group、wait4 | 子进程、启动流程 |
| `network` | socket、bind、listen、accept4、connect、sendto、recvfrom | 端口、连接、收发 |
| `signal` | rt_sigaction、rt_sigreturn、kill | 信号处理、崩溃信号 |
| `memory` | mmap、brk、mprotect、munmap | 内存布局、段错误 |
| `desc` | 所有 fd 相关 | 句柄泄漏旁证 |
| `ipc` | shmget、semop、msgget | 进程间通信 |

> 组合：`-e trace=file,network` 是排查"文件 + 网络"问题的最常用搭配。

---

## 9. 实战工作流

```bash
# 1) 报"文件不存在"但文件明明在 —— 看它实际找的路径
strace ./app 2>&1 | grep ENOENT

# 2) 找不到 .so
strace -e trace=openat ./app 2>&1 | grep -E '\.so|ENOENT'

# 3) 启动慢 —— 先汇总找类别，再下钻
strace -c ./app
strace -tt -T -e trace=openat,read ./app

# 4) 服务卡住 —— attach 看最后一行卡在哪
ps aux | grep app
strace -p <PID> -e trace=network,read,write -o /tmp/x.log
# 复现问题后：kill $(pgrep strace)；tail /tmp/x.log

# 5) 权限问题
strace ./app 2>&1 | grep -E 'EPERM|EACCES'

# 6) 端口被占的进程行为（bind 失败）
strace -e trace=bind,listen ./app
```

> 定位"卡在哪个调用"的三条线索：**卡在 `read`** 多半在等输入/网络数据；**卡在 `connect`** 是对端不响应（检查防火墙/对端）；**大量 `openat` + `read`** 是文件 I/O 密集（缓存策略问题）。这三类分别导向网络、文件、I/O 三个方向，配合《02-tcpdump网络抓包.md》看线上字节、《../07-调试与测试/03-perf性能剖析.md》看 CPU 热点。

---

## 10. 快速参考卡片

```bash
完整跟踪：            strace ./app
附加进程：            strace -p PID
汇总统计：            strace -c ./app          # -c 也可配 -p
只看某类：            strace -e trace=network ./app
只看某几个：          strace -e trace=openat,read ./app
时间戳+单次耗时：      strace -tt -T ./app
跟子进程：            strace -f ./app
落盘：                strace -o /tmp/x.log ./app
完整字符串参数：      strace -s 200 ./app
找 ENOENT/权限：      strace ./app 2>&1 | grep -E 'ENOENT|EPERM|EACCES'
```

---

## 11. 常见问题与坑

1. **输出刷屏**：先 `-e` 过滤，再 `-o` 落盘；不要裸 `strace ./big-server`。
2. **看不到子进程行为**：漏了 `-f`；服务器 fork/多线程必加。
3. **attach 报 `Operation not permitted`**：`ptrace_scope` 限制或跨用户；用 `root` 或 attach 自己的进程。
4. **字符串参数被截断**：`-s` 默认 32 字节，看全加 `-s 200`。
5. **输出在 stderr**：管道过滤要 `2>&1` 或直接 `-o` 文件。
6. **被 strace 的进程慢 10~100 倍**：性能测量别用 strace，用 perf；生产 attach 要短时。
7. **`strace -c` 看不到用户态热点**：它只统计系统调用；CPU 计算密集用 perf/火焰图。
8. **卡在 `poll`/`select`/`epoll_wait` 是正常的**：那是"等事件"而不是卡死；要等超时才异常。
9. **死锁排查 strace 帮不上忙**：系统调用都正常，但程序没进展；用 GDB attach + `thread apply all bt` 看调用栈。
10. **`-c` 对短程序统计不稳定**：demo 这种毫秒级程序分布无意义，拿真实服务跑足够时长。

---

上一篇：《05-readelf工具.md》　｜　下一篇：《07-curl网络调试.md》　｜　模块索引：《../README.md》
