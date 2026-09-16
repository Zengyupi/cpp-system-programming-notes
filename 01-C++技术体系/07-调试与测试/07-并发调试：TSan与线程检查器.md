# 并发调试：TSan 与线程检查器

> 本节目标：掌握多线程问题的系统化调试手段——gdb 多线程命令（线程切换、全线程栈、死锁现场试探）；深入使用 ThreadSanitizer（编译方式、环境变量、报告三要素解读、能力与局限）；会用 Valgrind helgrind / DRD 在无法重编译时排查数据竞争。学完本篇，在"疑似数据竞争 / 死锁"的故障现场应能选对工具并读懂报告。线程池与并发模式本身见《../04-并发编程/05-线程池与并发实战模式.md》。

## 本章速览

- [1. gdb 多线程命令](#1-gdb-多线程命令)
- [2. ThreadSanitizer（TSan）深度使用](#2-threadsanitizertsan深度使用)
  - [2.1 编译与运行](#21-编译与运行)
  - [2.2 典型报告解读](#22-典型报告解读)
  - [2.3 TSan 能检测的问题](#23-tsan-能检测的问题)
  - [2.4 TSan 的局限](#24-tsan-的局限)
- [3. Valgrind helgrind / DRD](#3-valgrind-helgrind--drd)
- [4. 工具选型速查](#4-工具选型速查)
- [5. 快速参考卡片](#5-快速参考卡片)
- [6. 常见坑](#6-常见坑)

---

## 1. gdb 多线程命令

gdb 多线程命令（详见《01-GDB程序调试.md》）：

| 命令 | 作用 |
| --- | --- |
| `info threads` | 列出所有线程及当前停在哪 |
| `thread 3` | 切到 3 号线程 |
| `thread apply all bt` | 所有线程都打印调用栈（死锁排查第一步） |
| `break work.cpp:42 thread 3` | 断点只对 3 号线程生效 |
| `set scheduler-locking on` | 单步时不让其他线程乱跑 |
| `p (int)pthread_mutex_trylock(&m)` | 死锁现场试探某把锁是否被持有（技巧） |

死锁排查的标准流程：`thread apply all bt` 打出全栈 → 找到多个线程都卡在 `__lll_lock_wait` → 对照各自栈帧里正要加的锁 → 画出锁持有/等待图 → 找到环。

## 2. ThreadSanitizer（TSan）深度使用

ThreadSanitizer 是基于编译期插桩的数据竞争检测器，是查找并发 bug 的首选工具。

### 2.1 编译与运行

```bash
# 编译：必须加 -fsanitize=thread，建议 -g -O1（-O0 太慢，-O2 可能优化掉竞争）
g++ -std=c++17 -fsanitize=thread -g -O1 -pthread main.cpp -o app

# 运行：直接执行，TSan 会在检测到竞争时打印报告
./app

# 常用环境变量
TSAN_OPTIONS="halt_on_error=1:report_batches=0:history_size=7" ./app
#   halt_on_error=1   首次检测到错误即退出（默认继续运行）
#   report_batches=0  不合并相似报告（每个竞争都完整打印）
#   history_size=7    记录更多栈帧历史（默认 4，最大 7）
```

### 2.2 典型报告解读

```text
==================
WARNING: ThreadSanitizer: data race (pid=12345)
  Write of size 4 at 0x7f8a1c000010 by thread T2:
    #0 increment() main.cpp:10:5   ← 线程 2 在第 10 行写
    #1 worker() main.cpp:20:3

  Previous write of size 4 at 0x7f8a1c000010 by thread T1:
    #0 increment() main.cpp:10:5   ← 线程 1 也在第 10 行写
    #1 worker() main.cpp:20:3

  Location is global 'counter' at 0x7f8a1c000010 (main.exe+0x000000409010)
  ← 竞争的变量是全局 counter

  Thread T2 (tid=12347, running) created by main thread at:
    #0 pthread_create ...
    #1 std::thread::_M_start_thread ...
    #2 main main.cpp:30:10

  Thread T1 (tid=12346, finished) created by main thread at:
    ...
==================
```

报告三要素：

1. **竞争位置**：哪个变量、哪个内存地址（`Location is global 'counter'`）
2. **两个访问点**：分别是哪个线程、哪行代码、读还是写（`Write` / `Read`）
3. **线程创建栈**：这两个线程是在哪里创建的（帮助定位）

### 2.3 TSan 能检测的问题

| 问题类型 | 报告关键词 | 说明 |
| --- | --- | --- |
| 数据竞争 | `data race` | 最常见，两个线程无同步访问同一内存 |
| 锁顺序倒置 | `lock-order-inversion` | 可能死锁：线程 A 锁 X 后锁 Y，线程 B 锁 Y 后锁 X |
| 误用 mutex | `mutex...wrong thread` | 在非加锁线程 unlock，或重复 unlock |
| 信号不安全 | `signal-unsafe-call` | 信号处理函数中调用了非异步信号安全的函数 |
| 内存泄漏 | 可选 | TSan 也能检测泄漏（但精度不如 ASan） |

### 2.4 TSan 的局限

| 局限 | 说明 |
| --- | --- |
| 性能开销 | 运行慢 5~15 倍，内存多 5~10 倍 |
| 只检测运行到的路径 | 没执行到的代码路径不会报竞争（需要好的测试覆盖） |
| 不检测原子操作内部 | `std::atomic` 的操作被认为是安全的（即使内存序选错也不报） |
| 不能与其他 sanitizer 同时用 | TSan 和 ASan/MSan 互斥（一次只能用一个） |
| 不支持 detach 线程的完整跟踪 | detach 线程的栈可能不完整 |

> TSan 与 ASan 的区别：TSan 查**数据竞争**（多线程并发问题），ASan 查**内存错误**（use-after-free、buffer overflow 等）。两者不能同时启用，需要分开编译运行。

## 3. Valgrind helgrind / DRD

Valgrind 提供两个线程错误检测器，无需重新编译（但需要带调试信息）。

**helgrind**：

```bash
# 编译（不需要特殊 flag，但需要 -g）
g++ -std=c++17 -g -pthread main.cpp -o app

# 运行 helgrind
valgrind --tool=helgrind ./app

# 常用选项
valgrind --tool=helgrind --history-level=full --track-lockorders=yes ./app
#   --history-level=full     记录完整的访问历史（更详细但更慢）
#   --track-lockorders=yes   检测锁顺序倒置（死锁风险）
```

**DRD（Data Race Detector）**：

```bash
valgrind --tool=drd ./app

# 常用选项
valgrind --tool=drd --check-stack-var=yes --exclusive-threshold=100 ./app
#   --check-stack-var=yes     也检查栈上变量的竞争（默认只查堆和全局）
#   --exclusive-threshold=100  持锁超过 100ms 时警告（可能的锁竞争热点）
```

**helgrind vs DRD 对比**：

| 维度 | helgrind | DRD |
| --- | --- | --- |
| 算法 | 基于 happens-before 向量时钟 | 基于 happens-before + 段（segment） |
| 数据竞争检测 | ✅ | ✅ |
| 锁顺序倒置检测 | ✅（`--track-lockorders`） | ❌（不检测） |
| 内存开销 | 较高（每个字节跟踪） | 较低 |
| 速度 | 慢 30~50 倍 | 慢 20~40 倍（比 helgrind 快） |
| 递归锁支持 | 有限 | 较好 |
| 典型用途 | 查数据竞争 + 死锁风险 | 快速筛查数据竞争 |

**helgrind 典型报告**：

```text
==12345== Possible data race during read of size 4 at 0x601040 by thread #2
==12345==    at 0x40095A: worker() (main.cpp:15)
==12345==  This conflicts with a previous write of size 4 by thread #1
==12345==    at 0x40095A: worker() (main.cpp:15)
==12345==  Address 0x601040 is 0 bytes inside data symbol "counter"
```

## 4. 工具选型速查

| 工具 | 编译要求 | 速度 | 竞争检测 | 死锁检测 | 适用场景 |
| --- | --- | --- | --- | --- | --- |
| TSan | `-fsanitize=thread` | 慢 5~15x | ✅ 精确 | ✅ 锁序倒置 | 首选，CI 集成 |
| helgrind | 仅 `-g` | 慢 30~50x | ✅ | ✅ 锁序倒置 | 不能重编译时 |
| DRD | 仅 `-g` | 慢 20~40x | ✅ | ❌ | 快速筛查 |
| gdb + `thread apply all bt` | `-g` | 手动 | 死锁现场 | ✅ 直接看持锁栈 | 事后分析 core / 线上卡死 |

> Valgrind 工具链的详细使用（memcheck/helgrind/callgrind 等）详见《02-Valgrind内存检测.md》。编译选项与 sanitizer 集成详见《../06-构建与版本控制/01-构建工具GCC与CMake.md》。

## 5. 快速参考卡片

| 需求 | 做法 |
| --- | --- |
| TSan 编译 | `g++ -fsanitize=thread -g -O1 -fno-omit-frame-pointer main.cpp` |
| TSan 运行 | `TSAN_OPTIONS="halt_on_error=0 second_deadlock_stack=1" ./a.out` |
| 报告解读 | `WARNING: ThreadSanitizer: data race` 给出两个栈 + 读写位置与行号 |
| 误报抑制 | `--suppressions=tsan.supp`（第三方库误报用） |
| helgrind | `valgrind --tool=helgrind ./a.out`（锁序、数据竞争） |
| DRD | `valgrind --tool=drd ./a.out`（侧重不同、误报更少） |
| gdb 多线程 | `info threads` / `thread apply all bt` / `set scheduler-locking on` |
| 现场死锁 | `gdb -p <pid> -ex "thread apply all bt"` 看各线程持锁/等锁 |
| 工具选型 | TSan 最快但需重编译；helgrind/DRD 慢但可跑现成二进制；线上用 eBPF/off-CPU |
| 常见坑 | TSan 与 ASan 不能同时开；`-O2` 下行号可能不准；未初始化读要用 MSan |

---

## 6. 常见坑

| 问题 | 原因与解决方案 |
| --- | --- |
| TSan 和 ASan 一起编译直接报错 | 两者互斥。解决：分开编译两次跑，或用 CI 矩阵分别跑 |
| `-O2` + TSan 跑不出竞争 | 优化可能消除竞争窗口。解决：TSan 构建统一用 `-O1 -g` |
| TSan 下程序内存翻几倍，CI 超时/被 OOM 杀 | TSan 内存开销 5~10 倍。解决：缩小压测规模、`TSAN_OPTIONS=history_size=4`、单独的并发测试目标 |
| TSan 报了一堆 `data race`，分不清哪个是真问题 | 先看 `Location is ...` 是否业务变量；库内部的一次性初始化竞争可白名单（`TSAN_OPTIONS=suppressions=tsan.supp`） |
| helgrind 对 `std::atomic`/`shared_ptr` 报误报 | helgrind 对自定义原子协议识别有限。解决：换 TSan 验证，或加 suppression |
| 死锁只在高并发压测偶现，gdb attach 时已恢复 | 死锁依赖时序。解决：加"锁等待超时 + core dump"（`pthread_mutex_timedlock` 或 watchdog 线程检测心跳超时后 `abort()`），保留现场再分析 |

---

上一篇：《06-静态分析与代码规范.md》　｜　模块索引：《../README.md》
