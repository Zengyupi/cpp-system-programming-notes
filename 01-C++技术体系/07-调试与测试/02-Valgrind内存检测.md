# Valgrind 内存检测

> 本节目标：系统讲解 Valgrind 工具集的使用方法，重点掌握 Memcheck 内存泄漏检测、未初始化内存追踪、文件描述符泄漏排查，以及 Cachegrind、Callgrind、Massif、Helgrind 等辅助工具的使用，学完后能够运用 Valgrind 进行内存问题诊断与性能分析。

## 本章速览

- [1. 基本调用格式](#1-基本调用格式)
- [2. 核心通用选项（适用于所有工具）](#2-核心通用选项适用于所有工具)
- [3. Memcheck 核心选项（默认工具）](#3-memcheck-核心选项默认工具)
- [4. 其他工具特有选项](#4-其他工具特有选项)
  - [4.1 Cachegrind（缓存分析）](#41-cachegrind缓存分析)
  - [4.2 Callgrind（调用图分析）](#42-callgrind调用图分析)
  - [4.3 Massif（堆内存分析）](#43-massif堆内存分析)
  - [4.4 Helgrind / DRD（线程竞争检测）](#44-helgrind--drd线程竞争检测)
- [5. 常用命令示例（代码块形式）](#5-常用命令示例代码块形式)
  - [5.1 基础内存检测（最常用）](#51-基础内存检测最常用)
  - [5.2 排查未初始化变量问题](#52-排查未初始化变量问题)
  - [5.3 检查文件句柄泄漏](#53-检查文件句柄泄漏)
  - [5.4 多进程程序，日志按 PID 分文件](#54-多进程程序日志按-pid-分文件)
  - [5.5 使用 XML 输出（便于 CI/CD 解析）](#55-使用-xml-输出便于-cicd-解析)
  - [5.6 指定调用栈深度（调试深层嵌套调用）](#56-指定调用栈深度调试深层嵌套调用)
  - [5.7 完整组合命令（日常开发推荐）](#57-完整组合命令日常开发推荐)
- [6. Memcheck 结果解读](#6-memcheck-结果解读)
  - [6.1 四类内存泄漏（LEAK SUMMARY）](#61-四类内存泄漏leak-summary)
  - [6.2 常见错误报告含义](#62-常见错误报告含义)
- [7. 辅助分析工具（结果文件的可视化）](#7-辅助分析工具结果文件的可视化)
- [8. 快速参考卡片（常用组合速查）](#8-快速参考卡片常用组合速查)

---

## 1. 基本调用格式

```bash
valgrind [核心选项] [工具选项] 你的程序 [程序参数]
```

## 2. 核心通用选项（适用于所有工具）

| 选项                | 取值         | 说明                                                         |
| ------------------- | ------------ | ------------------------------------------------------------ |
| `--tool`            | `<工具名>`   | 指定工具，默认 `memcheck`。可选：`cachegrind`、`callgrind`、`massif`、`helgrind`、`drd` |
| `--log-file`        | `<文件名>`   | 日志输出到文件，可用 `%p` 代表进程 ID                        |
| `-v` / `--verbose`  | 无           | 输出详细信息（共享库、调试信息等）                           |
| `-q` / `--quiet`    | 无           | 安静模式，仅打印错误信息                                     |
| `--trace-children`  | `yes` / `no` | 是否跟踪子进程（默认 `no`）                                  |
| `--time-stamp`      | `yes` / `no` | 每条信息前加时间戳（默认 `no`）                              |
| `--vgdb`            | `yes` / `no` | 内置 gdbserver 支持（默认 `yes`，配合 `--vgdb-error=0` 可立即用 GDB 连接） |
| `--xml`             | `yes` / `no` | 以 XML 格式输出报告（默认 `no`，需同时指定 `--xml-file`）    |
| `--xml-file`        | `<文件名>`   | XML 输出文件名                                               |
| `--num-callers`     | `<数字>`     | 显示调用栈的层数（默认 12）                                  |
| `--error-limit`     | `yes` / `no` | 达到错误上限后是否停止显示（默认 `yes`）                     |
| `--show-error-list` | `yes` / `no` | 程序结束后列出所有错误（默认 `yes`）                         |
| `--track-fds`       | `yes` / `no` | 跟踪打开的文件描述符并在退出时报告泄漏（默认 `no`，3.14+ 为核心选项） |

---

## 3. Memcheck 核心选项（默认工具）

| 选项                   | 取值                                                         | 说明                                                       |
| ---------------------- | ------------------------------------------------------------ | ---------------------------------------------------------- |
| `--leak-check`         | `no` / `summary` / `full`                                    | 内存泄漏检查级别（推荐 `full`）                            |
| `--show-leak-kinds`    | `definite` / `indirect` / `possible` / `reachable` / `all`   | 显示哪些类型的泄漏（可组合，如 `definite,indirect`）       |
| `--track-origins`      | `yes` / `no`                                                 | 跟踪未初始化内存的来源（默认 `no`，推荐开启）              |
| `--gen-suppressions`   | `yes` / `no` / `all`                                         | 生成错误抑制规则（默认 `no`）                              |
| `--suppressions`       | `<文件名>`                                                   | 加载抑制规则文件                                           |
| `--show-reachable`     | `yes` / `no`                                                 | 是否显示可到达的内存（已废弃，建议用 `--show-leak-kinds`） |
| `--undef-value-errors` | `yes` / `no`                                                 | 是否报告未定义值错误（默认 `yes`）                         |
| `--malloc-fill`        | `<十六进制值>`                                               | 分配时填充内存的字节值（调试用）                           |
| `--free-fill`          | `<十六进制值>`                                               | 释放时填充内存的字节值（调试用）                           |
| `--keep-stacktraces`   | `alloc` / `free` / `alloc-and-free` / `alloc-then-free` / `none` | 保留哪些操作的调用栈                                       |

---

## 4. 其他工具特有选项

### 4.1 Cachegrind（缓存分析）

| 选项                     | 取值                   | 说明                                               |
| ------------------------ | ---------------------- | -------------------------------------------------- |
| `--cachegrind-out-file`  | `<文件名>`             | 输出文件名，默认 `cachegrind.out.<pid>`            |
| `--I1` / `--D1` / `--LL` | `<大小,关联性,行大小>` | 手动指定一级指令缓存 / 一级数据缓存 / 最后一级缓存 |

### 4.2 Callgrind（调用图分析）

| 选项                   | 取值         | 说明                                   |
| ---------------------- | ------------ | -------------------------------------- |
| `--callgrind-out-file` | `<文件名>`   | 输出文件名，默认 `callgrind.out.<pid>` |
| `--dump-instr`         | `yes` / `no` | 包含每条指令的执行信息（默认 `no`）    |
| `--collect-atstart`    | `yes` / `no` | 是否从程序启动就开始收集（默认 `yes`） |
| `--toggle-collect`     | `<函数名>`   | 仅在指定函数执行时收集数据             |

### 4.3 Massif（堆内存分析）

| 选项                | 取值         | 说明                                |
| ------------------- | ------------ | ----------------------------------- |
| `--massif-out-file` | `<文件名>`   | 输出文件名，默认 `massif.out.<pid>` |
| `--heap`            | `yes` / `no` | 是否分析堆内存（默认 `yes`）        |
| `--heap-admin`      | `<大小>`     | 堆管理开销字节数（默认 8）          |
| `--stacks`          | `yes` / `no` | 是否分析栈内存（默认 `no`）         |
| `--threshold`       | `<百分比>`   | 忽略低于此比例的分配（默认 1.0%）   |

### 4.4 Helgrind / DRD（线程竞争检测）

| 选项                    | 取值                       | 说明                                             |
| ----------------------- | -------------------------- | ------------------------------------------------ |
| `--helgrind-out-file`   | `<文件名>`                 | Helgrind 输出文件名（默认 `helgrind.out.<pid>`） |
| `--history-level`       | `none` / `approx` / `full` | 记录冲突历史的详细程度（Helgrind 专用）          |
| `--exclusive-threshold` | `<毫秒>`                   | 报告锁持有时间超过此阈值（DRD 专用）             |
| `--shared-threshold`    | `<毫秒>`                   | 报告共享锁持有时间超过此阈值（DRD 专用）         |

---

## 5. 常用命令示例（代码块形式）

> 提示：编译程序时建议加 `-g`（保留符号信息）并使用 `-O0`（关闭优化，避免变量被优化掉），Valgrind 才能给出准确的函数名和行号。

### 5.1 基础内存检测（最常用）

```bash
valgrind --leak-check=full --show-leak-kinds=all ./your_program
```

### 5.2 排查未初始化变量问题

```bash
valgrind --track-origins=yes ./your_program
```

### 5.3 检查文件句柄泄漏

```bash
valgrind --track-fds=yes ./your_program
```

### 5.4 多进程程序，日志按 PID 分文件

```bash
valgrind --log-file=valgrind_%p.log --trace-children=yes ./your_program
```

### 5.5 使用 XML 输出（便于 CI/CD 解析）

```bash
valgrind --xml=yes --xml-file=valgrind_report.xml ./your_program
```

### 5.6 指定调用栈深度（调试深层嵌套调用）

```bash
valgrind --num-callers=20 ./your_program
```

### 5.7 完整组合命令（日常开发推荐）

```bash
valgrind --leak-check=full \
         --show-leak-kinds=all \
         --track-origins=yes \
         --track-fds=yes \
         --log-file=valgrind_%p.log \
         --num-callers=20 \
         ./your_program
```

---

## 6. Memcheck 结果解读

### 6.1 四类内存泄漏（LEAK SUMMARY）

| 泄漏类型                          | 含义                                                                 | 严重程度 |
| --------------------------------- | -------------------------------------------------------------------- | -------- |
| `definitely lost`（确定泄漏）     | 指向该内存的所有指针都已丢失，无法释放，**必须修复**                 | 高       |
| `indirectly lost`（间接泄漏）     | 泄漏的结构体内部还引用了其他泄漏内存，修复直接泄漏后会一并解决       | 高       |
| `possibly lost`（可能泄漏）       | 仅剩一个指向内存中间位置的指针（如数组内部偏移），通常需要检查       | 中       |
| `still reachable`（仍可达）       | 程序退出时仍有指针指向，未 free 但不算真正泄漏（常见于全局/静态缓冲区） | 低       |

### 6.2 常见错误报告含义

| 错误类型                    | 含义与典型原因                                             |
| --------------------------- | ---------------------------------------------------------- |
| `Invalid read of size N`    | 越界读（数组下标越界、指针悬空、读已释放内存）             |
| `Invalid write of size N`   | 越界写（缓冲区溢出，如 `strcpy` 目标空间不足）             |
| `Conditional jump or move depends on uninitialised value` | 使用了未初始化变量（如未置 `\0` 的字符串判断） |
| `Use of uninitialised value` | 未初始化值参与运算                                        |
| `Mismatched free() / delete / delete[]` | 分配与释放方式不匹配（如 `new` 的内存用 `free` 释放） |
| `Invalid free() / delete`   | 重复释放或释放非堆地址                                     |
| `Uninitialised value was created by a heap allocation` | 溯源信息（配合 `--track-origins`）        |
| `File descriptor N: N is still open` | 文件/套接字未关闭（配合 `--track-fds`）             |

```text
# 泄漏报告示例
==12345== 8 bytes in 1 blocks are definitely lost in loss record 1 of 1
==12345==    at 0x4C2FB0F: malloc (in /usr/lib/valgrind/vgpreload_memcheck.so)
==12345==    by 0x400544: main (test.c:10)        ← 泄漏发生的位置（malloc 调用处）
```

---

## 7. 辅助分析工具（结果文件的可视化）

| 工具               | 配套工具     | 用途                                             | 示例                                       |
| ------------------ | ------------ | ------------------------------------------------ | ------------------------------------------ |
| `cg_annotate`      | Cachegrind   | 逐行统计 CPU 指令数和缓存命中率                  | `cg_annotate cachegrind.out.12345`         |
| `callgrind_annotate` | Callgrind  | 命令行查看函数级调用耗时/指令数                  | `callgrind_annotate callgrind.out.12345`   |
| `kcachegrind`      | Callgrind    | 图形化查看调用图（推荐）                         | `kcachegrind callgrind.out.12345`          |
| `ms_print`         | Massif       | 命令行生成堆内存随时间变化的 ASCII 图            | `ms_print massif.out.12345`                |

```bash
# Callgrind 典型工作流
valgrind --tool=callgrind ./your_program     # 生成 callgrind.out.<pid>
callgrind_annotate callgrind.out.12345       # 查看哪个函数消耗指令最多
# KCachegrind（GUI）可直观展示调用关系与热点

# Massif 典型工作流
valgrind --tool=massif ./your_program        # 生成 massif.out.<pid>
ms_print massif.out.12345 | less             # 查看堆内存增长曲线
```

---

## 8. 快速参考卡片（常用组合速查）

| 需求场景         | 命令                                                         |
| ---------------- | ------------------------------------------------------------ |
| 内存泄漏检测     | `valgrind --leak-check=full --show-leak-kinds=all ./程序`    |
| 未初始化变量溯源 | `valgrind --track-origins=yes ./程序`                        |
| 文件句柄泄漏排查 | `valgrind --track-fds=yes ./程序`                            |
| 多进程调试       | `valgrind --trace-children=yes --log-file=log_%p.log ./程序` |
| XML 报告输出     | `valgrind --xml=yes --xml-file=report.xml ./程序`            |
| 缓存性能分析     | `valgrind --tool=cachegrind ./程序`                          |
| 函数调用分析     | `valgrind --tool=callgrind ./程序`                           |
| 堆内存快照分析   | `valgrind --tool=massif ./程序`                              |
| 线程竞争检测     | `valgrind --tool=helgrind ./程序`                            |

---

上一篇：《01-GDB程序调试.md》
下一篇：《03-perf性能剖析.md》
