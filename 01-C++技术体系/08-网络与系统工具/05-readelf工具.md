# readelf 工具：ELF 结构解析

> 本节目标：讲解 GNU readelf 对 ELF 文件结构的直接解析能力——文件头、段表、程序头、动态段、符号表、重定位与符号版本，并重点讲清它和 objdump 的分工（readelf 不经 BFD，直接读 ELF，更原始权威）。学完后能够用 readelf 判断文件类型与 PIE、查动态依赖与 rpath、排查 GLIBC 版本问题、检查 NX/RELRO 安全属性、在 strip 之后分析符号。本篇输出均在 Ubuntu 24.04（gcc 13 / binutils 2.42）上实跑验证。反汇编与综合查看见《04-目标文件分析.md》，原始字节查看配合《03-二进制查看工具.md》，ELF 格式原理见《../02-系统原理/02-编译链接与加载原理.md》。

## 本章速览

- [0. readelf 定位：与 objdump 怎么分工](#0-readelf-定位与-objdump-怎么分工)
- [1. 基本调用与选项总表](#1-基本调用与选项总表)
- [2. ELF 文件头逐字段解读](#2-elf-文件头逐字段解读)
  - [2.1 魔数与字节序](#21-魔数与字节序)
  - [2.2 Type 与入口点](#22-type-与入口点)
- [3. 段表 Section Headers](#3-段表-section-headers)
- [4. 程序头与安全属性](#4-程序头与安全属性)
- [5. 动态段与依赖](#5-动态段与依赖)
- [6. 符号表](#6-符号表)
  - [6.1 本地符号表](#61-本地符号表)
  - [6.2 动态符号表](#62-动态符号表)
  - [6.3 strip 之后](#63-strip-之后)
- [7. 重定位表](#7-重定位表)
- [8. 符号版本](#8-符号版本)
- [9. 段内容与字符串](#9-段内容与字符串)
- [10. readelf 与 objdump 对比](#10-readelf-与-objdump-对比)
- [11. 实战工作流](#11-实战工作流)
- [12. 快速参考卡片](#12-快速参考卡片)
- [13. 常见问题与坑](#13-常见问题与坑)

---

测试样例（沿用《04-目标文件分析.md》的 demo）：

```cpp
// demo.c
#include <stdio.h>
int g_counter = 42;
static int helper(int x){ return x * 2; }
int add(int a, int b){ return helper(a + b); }
int main(void){ printf("sum=%d\n", add(1, 2)); return 0; }
```
```bash
gcc -g -O0 -c demo.c -o demo.o      # 可重定位目标文件（未链接）
gcc demo.o -o demo_app              # 链接为可执行文件（现代发行版默认 PIE）
```

---

## 0. readelf 定位：与 objdump 怎么分工

`readelf` 直接解析 ELF 二进制结构，**不经过 BFD 库**，因此看到的字段是文件里的原始值；`objdump` 经 BFD 规整后展示，侧重反汇编。分工口诀：**反汇编用 objdump，ELF 装载与动态细节用 readelf**。

| 场景 | 用谁 | 理由 |
| --- | --- | --- |
| 反汇编看代码 | `objdump -d` | readelf 不能反汇编 |
| 判断类型/PIE/入口 | `readelf -h` | objdump `-f` 信息不全（无 Type 语义说明） |
| 看加载段/安全属性 | `readelf -l` | objdump 没有程序头视图 |
| 查动态依赖/rpath | `readelf -d` | objdump `-p` 内部同样来自动态段 |
| 查符号版本 GLIBC | `readelf -V` | objdump `-T` 只能看到符号上的版本标注 |
| strip 后分析 | `readelf --dyn-syms` | objdump `-t` 对 .symtab 同样失效 |

> 若 objdump 与 readelf 输出"对不上"，以 readelf 为准——它更接近文件真实结构（《04-目标文件分析.md》坑 9）。

```bash
# 30 秒上手
readelf -h app            # 文件头：类型/架构/入口
readelf -d app | grep NEEDED   # 依赖哪些 .so
readelf --dyn-syms app    # 动态符号（strip 后也能看）
```

---

## 1. 基本调用与选项总表

```bash
readelf [选项] ELF 文件（.o / 可执行文件 / .so / .a）
```

| 选项 | 作用 | 常用度 |
| --- | --- | --- |
| `-h` | **ELF 文件头**（类型、架构、入口、节表偏移） | ★★★★★ |
| `-S` | **段表**（所有 section，含调试段） | ★★★★ |
| `-l` | **程序头**（加载段、解释器、栈/RELRO 属性） | ★★★★ |
| `-d` | **动态段**（NEEDED/RPATH/RUNPATH/FLAGS） | ★★★★★ |
| `-s` | 符号表 `.symtab`（strip 后自动回退到动态符号） | ★★★ |
| `--dyn-syms` | **动态符号表** `.dynsym`（运行时真正用到的） | ★★★★ |
| `-r` / `-R` | 静态重定位 / 动态重定位 | ★★★ |
| `-V` | **符号版本**（VERDEF/VERNEED，GLIBC 版本） | ★★★★ |
| `-x 段名` | 十六进制 dump 指定段内容 | ★★★ |
| `-p 段名` | 打印字符串段（`.dynstr`/`.rodata`） | ★★★ |
| `-A` | 架构属性（ARM/RISC-V 特性扩展） | ★★ |
| `-n` | note 段（build-id、ABI 标记） | ★★ |
| `-e` | 全部头信息（≈ `-h -l -S`） | ★ |
| `-W` / `--wide` | **宽行输出**，符号名不截断 | ★★★★ |
| `--debug-dump` | DWARF 调试信息（配合 `-g` 编译） | ★ |

> `-W` 建议默认带上：不加时超长符号名会被截成 `_[...]`（见 6.2 节）。

---

## 2. ELF 文件头逐字段解读

```bash
$ readelf -h demo_app
ELF Header:
  Magic:   7f 45 4c 46 02 01 01 00 00 00 00 00 00 00 00 00
  Class:                             ELF64
  Data:                              2's complement, little endian
  Version:                           1 (current)
  OS/ABI:                            UNIX - System V
  ABI Version:                       0
  Type:                              DYN (Position-Independent Executable file)
  Machine:                           Advanced Micro Devices X86-64
  Version:                           0x1
  Entry point address:               0x1060
  Start of program headers:          64 (bytes into file)
  Start of section headers:          15112 (bytes into file)
  Flags:                             0x0
  Size of this header:               64 (bytes)
  Size of program headers:           56 (bytes)
  Number of program headers:         13
  Size of section headers:           64 (bytes)
  Number of section headers:         37
  Section header string table index: 36
```

### 2.1 魔数与字节序

`Magic` 是文件最前 16 字节，`readelf -h` 与 `hexdump -C -n 16` 看到的是同一份数据（《03-二进制查看工具.md》魔数表里的 ELF 正是 `7f 45 4c 46`）：

| 字节 | 值 | 含义 |
| --- | --- | --- |
| 0-3 | `7f 45 4c 46` | ELF 魔数（`.ELF`） |
| 4 | `02` | 位宽：`01`=ELF32，`02`=ELF64 |
| 5 | `01` | 字节序：`01`=小端（x86/ARM 默认），`02`=大端（网络/部分嵌入式） |
| 6 | `01` | ELF 版本（恒为 1） |
| 7-15 | 0 | OS/ABI 等（System V 默认全 0） |

> `Class: ELF64`、`Data: little endian` 是第 4、5 字节的翻译结果。交叉编译拿到板子固件后，先看这两行确认位宽与大小端是否匹配目标机。

### 2.2 Type 与入口点

| Type | 含义 | 典型来源 |
| --- | --- | --- |
| `REL (Relocatable file)` | 可重定位目标文件，未链接 | `gcc -c` 产生的 `.o` |
| `EXEC` | 传统可执行文件（**非 PIE**），入口固定 | 老发行版或 `-no-pie` |
| `DYN` | 位置无关可执行（**PIE**）或共享库 `.so` | 现代发行版默认；`gcc demo.o -o demo_app` 默认 PIE |

```bash
$ readelf -h demo.o | grep -E 'Type|Entry'
  Type:                              REL (Relocatable file)
  Entry point address:               0x0            # .o 未链接，入口为 0
```

- **判断 PIE**：`Type: DYN` 且 `Entry` 非 0 → PIE 可执行；`Type: EXEC` → 非 PIE。`.so` 也是 `DYN`，但入口地址为 0 且无 `PT_INTERP`（见第 4 节）。
- `Start of section headers: 15112` 给出节表在文件中的偏移；`.o` 因无调试段偏移小很多，可作"文件被改过/被 strip"的旁证。

---

## 3. 段表 Section Headers

`-S` 列出所有 section，比 objdump `-h` 更全（连 `.debug_*` 都显示），列含义与《04-目标文件分析.md》一致，但 Flags 用**字母缩写**：

```bash
$ readelf -S demo_app | grep -E '\.(text|data|bss|rodata|dynsym|debug_info)'
  [16] .text             PROGBITS         0000000000001060  00001060
       0000000000000152  0000000000000000  AX       0     0     16
  [18] .rodata           PROGBITS         0000000000002000  00002000
       000000000000000c  0000000000000000   A       0     0     4
  [25] .data             PROGBITS         0000000000004000  00003000
       0000000000000014  0000000000000000  WA       0     0     8
  [26] .bss              NOBITS           0000000000004014  00003014
       0000000000000004  0000000000000000  WA       0     0     1
  [29] .debug_info       PROGBITS         0000000000000000  00003071
       000000000000012b  0000000000000000           0     0     1
```

Flags 字母速查（输出末尾有 `Key to Flags` 完整清单）：

| 字母 | 含义 | 对应 objdump 标志 |
| --- | --- | --- |
| `W` | 可写 | `DATA` |
| `A` | 需要加载进内存（alloc） | `ALLOC, LOAD` |
| `X` | 可执行 | `CODE` |
| `M` / `S` | mergeable / 字符串段 | — |
| `I` | 含信息（如 `.rela.text` 的 Info 指向被重定位段） | `RELOC` |

要点：

- `.text` 是 `AX`（可读可执行不可写），`.data` 是 `WA`，`.bss` 是 `NOBITS`——**Size 4 但不占文件空间**（文件内偏移等于 `.data` 结束处），加载时清零。
- 带 `-g` 编译才出现的 `.debug_*` 段在这里一清二楚；发布版 strip 后这些段消失（`-S` 段数明显减少）。
- 段名被截断（如 `.note.gnu.pr[...]`）时加 `-W`。

---

## 4. 程序头与安全属性

`-l` 是 readelf 的独门优势：展示**加载器视角**的段（segment），直接对应文件在内存里怎么放、权限如何，还带 `Section to Segment mapping`。

```bash
$ readelf -l demo_app | grep -E 'Type|LOAD|INTERP|GNU_|Requesting'
  Type           Offset             VirtAddr           PhysAddr
                 FileSiz            MemSiz              Flags  Align
  INTERP         0x0000000000000318 0x0000000000000318 0x0000000000000318
                 0x000000000000001c 0x000000000000001c  R      0x1
      [Requesting program interpreter: /lib64/ld-linux-x86-64.so.2]
  LOAD           0x0000000000000000 0x0000000000000000 0x0000000000000000
                 0x0000000000000628 0x0000000000000628  R      0x1000
  LOAD           0x0000000000001000 0x0000000000001000 0x0000000000001000
                 0x00000000000001c1 0x00000000000001c1  R E    0x1000
  LOAD           0x0000000000002000 0x0000000000002000 0x0000000000002000
                 0x000000000000013c 0x000000000000013c  R      0x1000
  LOAD           0x0000000000002db8 0x0000000000003db8 0x0000000000003db8
                 0x000000000000025c 0x0000000000000260  RW     0x1000
  GNU_STACK      0x0000000000000000 0x0000000000000000 0x0000000000000000
                 0x0000000000000000 0x0000000000000000  RW     0x10
  GNU_RELRO      0x0000000000002db8 0x0000000000003db8 0x0000000000003db8
                 0x0000000000000248 0x0000000000000248  R      0x1
```

| 程序头 | 含义 |
| --- | --- |
| `PT_INTERP` | 动态链接器路径（`/lib64/ld-linux-x86-64.so.2`），静态链接的程序没有它 |
| `PT_LOAD` | 真正加载进内存的段；4 个依次为 R / R E / R / RW（只读元数据、代码、只读数据、可写数据） |
| `GNU_STACK` | 栈段；`RW` 无 `E` = **NX 开启**（不可执行栈）；出现 `RWE` 则栈可执行，是危险信号 |
| `GNU_RELRO` | 只读重定位区：GOT 前段加载后只读；配 `-d` 里的 `BIND_NOW` 才是 full RELRO |

安全属性速查（一行一个）：

```bash
readelf -l app | grep GNU_STACK      # RW = NX 正常；RWE = 可执行栈（危）
readelf -l app | grep GNU_RELRO      # 有 = partial RELRO（基础）
readelf -d app | grep -E 'BIND_NOW'  # 有 BIND_NOW = full RELRO（GOT 全只读）
readelf -h app | grep 'Type:'        # DYN = PIE；EXEC = 非 PIE
```

> `MemSiz` 大于 `FileSiz` 的 PT_LOAD 就是含 `.bss` 的段（本段 `0x260 > 0x25c`，多出的 4 字节正是 `.bss`）。程序头是排查"段权限不对导致段错误/只读数据被写"的第一现场。

---

## 5. 动态段与依赖

`-d` 展示 `.dynamic` 段——动态链接器的"配置表"：

```bash
$ readelf -d demo_app | grep -E 'NEEDED|RPATH|RUNPATH|FLAGS'
 0x0000000000000001 (NEEDED)             Shared library: [libc.so.6]
 0x000000000000001e (FLAGS)              BIND_NOW
 0x000000006ffffffb (FLAGS_1)            Flags: NOW PIE
```

| 条目 | 含义 |
| --- | --- |
| `NEEDED` | 依赖的共享库，等价 `ldd` 的第一列；`libc.so.6` 必在 |
| `RPATH` / `RUNPATH` | 编译期写死的库搜索路径（`-Wl,-rpath,` 生成） |
| `FLAGS BIND_NOW` | 启动即解析完所有符号（非延迟绑定），full RELRO 的直接证据 |
| `FLAGS_1 PIE` | PIE 可执行文件的标记 |

查依赖与 rpath 的标准姿势：

```bash
readelf -d ./app | grep -E 'NEEDED|RPATH|RUNPATH'
```

- 出现 `RPATH`/`RUNPATH` 说明程序"自带"库路径；发布时把依赖 .so 放进去即可，但注意 **RPATH 会优先于系统路径**，被注入同名恶意库的风险高于 RUNPATH（`LD_LIBRARY_PATH` 优先于 RUNPATH、低于 RPATH）。
- "部署到别的机器上 libxxx.so.1 not found"：先 `readelf -d` 确认依赖名与版本，再查目标机对应库是否存在。

---

## 6. 符号表

### 6.1 本地符号表

```bash
$ readelf -W -s demo.o
Symbol table '.symtab' contains 14 entries:
   Num:    Value          Size Type    Bind   Vis      Ndx Name
     0: 0000000000000000     0 NOTYPE  LOCAL  DEFAULT  UND
     1: 0000000000000000     0 FILE    LOCAL  DEFAULT  ABS demo.c
     2: 0000000000000000     0 SECTION LOCAL  DEFAULT    1 .text
     3: 0000000000000000    18 FUNC    LOCAL  DEFAULT    1 helper
     4: 0000000000000000     0 SECTION LOCAL  DEFAULT    5 .rodata
    10: 0000000000000000     4 OBJECT  GLOBAL DEFAULT    3 g_counter
    11: 0000000000000012    35 FUNC    GLOBAL DEFAULT    1 add
    12: 0000000000000035    52 FUNC    GLOBAL DEFAULT    1 main
    13: 0000000000000000     0 NOTYPE  GLOBAL DEFAULT  UND printf
```

与 objdump `-t` 同源，但列更规整（`Value`=地址、`Size`=符号字节数、`Bind`=`LOCAL/GLOBAL/WEAK`、`Ndx`=`UND/ABS/section 号`）：

- `helper` 是 `LOCAL FUNC`（static 函数，仅本文件可见），`add`/`main` 是 `GLOBAL FUNC`——**链接报 undefined reference 时，先看目标符号在这里是 UND 还是 LOCAL**。
- `g_counter` 是 `OBJECT` 且 `Size 4`（正好一个 int），地址 0（.o 未重定位）。
- `printf` 是 `UND`（undefined）：本文件引用但未定义，链接时从 libc 解析。

### 6.2 动态符号表

```bash
$ readelf -W --dyn-syms demo_app
Symbol table '.dynsym' contains 7 entries:
   Num:    Value          Size Type    Bind   Vis      Ndx Name
     0: 0000000000000000     0 NOTYPE  LOCAL  DEFAULT  UND
     1: 0000000000000000     0 FUNC    GLOBAL DEFAULT  UND __libc_start_main@GLIBC_2.34 (2)
     2: 0000000000000000     0 NOTYPE  WEAK   DEFAULT  UND _ITM_deregisterTMCloneTable
     3: 0000000000000000     0 FUNC    GLOBAL DEFAULT  UND printf@GLIBC_2.2.5 (3)
     4: 0000000000000000     0 NOTYPE  WEAK   DEFAULT  UND __gmon_start__
     5: 0000000000000000     0 NOTYPE  WEAK   DEFAULT  UND _ITM_registerTMCloneTable
     6: 0000000000000000     0 FUNC    WEAK   DEFAULT  UND _[...]@GLIBC_2.2.5 (3)
```

- `.dynsym` 是**运行时要用的动态符号**：只有被外部引用（`UND`）或本文件导出（`.so` 的 GLOBAL）的符号才会进来；本地 static 符号、普通全局变量通常不在。
- `printf@GLIBC_2.2.5`：符号名带**版本后缀**——这是 `-T` 的 objdump 也显示的同一信息，但 readelf `-V` 能给出完整版本依赖关系（第 8 节）。
- 名字带 `@` 后是版本号，`(2)`/`(3)` 是版本索引，对应 `-V` 输出的 Verneed 表。

### 6.3 strip 之后

```bash
$ strip demo_app -o demo_stripped
$ readelf -s demo_stripped | head -3
Symbol table '.dynsym' contains 7 entries:    # .symtab 已被删除，-s 自动回退到 .dynsym
```

发布版 strip 后本地符号全部消失，只剩 `.dynsym` 7 条。**排查线上崩溃地址但符号被 strip**：先确认发布版还留着带符号的版本（`-g` 编译 + 不 strip），或至少保留 `.dynsym`（`strip --strip-unneeded` 比全 strip 更保守）。

---

## 7. 重定位表

```bash
$ readelf -r demo.o | sed -n '/.rela.text/,/^$/p'
Relocation section '.rela.text' at offset 0x6f0 contains 3 entries:
  Offset          Info           Type           Sym. Value    Sym. Name + Addend
000000000048  000b00000004 R_X86_64_PLT32    0000000000000012 add - 4
000000000051  000400000002 R_X86_64_PC32     0000000000000000 .rodata - 4
00000000005e  000d00000004 R_X86_64_PLT32    0000000000000000 printf - 4
```

与 objdump `-r` 完全同源（《04-目标文件分析.md》已详解），但注意两点：

- 带 `-g` 编译的 `.o` 会有一大堆 `.rela.debug_*` 重定位（DWARF 调试信息的地址回填），**分析代码只关心 `.rela.text` 和 `.rela.data`**，用 `sed -n '/.rela.text/,/^$/p'` 或 `readelf -r demo.o | grep -v debug` 过滤。
- 类型含义同 objdump：`R_X86_64_PC32` 相对寻址、`R_X86_64_PLT32` 经 PLT 调外部、`R_X86_64_64` 绝对 64 位（全局变量地址，`.rela.data` 里常见）。

---

## 8. 符号版本

"编译机高版本 glibc、运行机低版本"报 `version GLIBC_2.34 not found` 的完整排查入口：

```bash
$ readelf -V demo_app
Version symbols section '.gnu.version' contains 7 entries:
  000:   0 (*local*)       2 (GLIBC_2.34)    1 (*global*)      3 (GLIBC_2.2.5)
  004:   1 (*global*)      1 (*global*)      3 (GLIBC_2.2.5)

Version needs section '.gnu.version_r' contains 1 entry:
  000000: Version: 1  File: libc.so.6  Cnt: 2
  0x0010:   Name: GLIBC_2.2.5  Flags: none  Version: 3
  0x0020:   Name: GLIBC_2.34  Flags: none  Version: 2
```

- 上段 `.gnu.version`：**每个动态符号需要的版本**（`__libc_start_main` → GLIBC_2.34，`printf` → GLIBC_2.2.5）。
- 下段 `.gnu.version_r`：**程序整体对 libc.so.6 的版本要求清单**——`GLIBC_2.34` 就是硬性最低 glibc。
- 目标机 glibc 低于 2.34 就起不来；对策：换老基线编译、静态链接、或在旧容器里构建（《04-目标文件分析.md》坑 8）。

快速判定最低 glibc：

```bash
readelf -V app | grep -A2 'File: libc' | grep 'Name:' | sort -V | tail -1
```

---

## 9. 段内容与字符串

`-x` dump 指定段原始字节，`-p` 直接打印字符串段（比 objdump `-s -j` 更适合找字符串）：

```bash
$ readelf -x .rodata demo_app
Hex dump of section '.rodata':
  0x00002000 01000200 73756d3d 25640a00          ....sum=%d..

$ readelf -p .dynstr demo_app
String dump of section '.dynstr':
  [     1]  __libc_start_main
  [    22]  printf
  [    29]  libc.so.6
  [    33]  GLIBC_2.2.5
  [    3f]  GLIBC_2.34
```

- `.rodata`：偏移 0x2000 起，`73 75 6d 3d 25 64 0a 00` = `"sum=%d\n\0"` 的 ASCII 存储，与《03-二进制查看工具.md》hexdump 互证；前 4 字节 `01 00 02 00` 是编译器生成的 32 位常量。
- `.dynstr` 是动态符号字符串表——**不想被 strip 清掉的字符串都在这里**（`printf`、`libc.so.6`、`GLIBC_*`），做版本/依赖排查最顺手。
- `.data` 段的 `2a000000` 即 `g_counter = 42` 的小端存储（`readelf -x .data demo_app`）。

---

## 10. readelf 与 objdump 对比

| 维度 | objdump | readelf |
| --- | --- | --- |
| 底层实现 | 经 BFD 库规整 | 直接解析 ELF 原始结构 |
| 最强项 | 反汇编（`-d -M intel`） | ELF 结构（头/段/程序头/动态） |
| 文件头 | `-f`（信息少） | `-h`（含 Type/PIE/字节序逐字段） |
| 段表 | `-h` | `-S`（连调试段都列出） |
| 程序头 | 无 | `-l`（LOAD/INTERP/STACK/RELRO） |
| 动态段/依赖 | `-p \| grep NEEDED` | `-d`（NEEDED/RPATH/RUNPATH/FLAGS） |
| 符号 | `-t` / `-T` | `-s` / `--dyn-syms`（列更规整） |
| 符号版本 | `-T` 看版本标注 | `-V`（完整 Verneed 依赖） |
| 段原始字节 | `-s -j 段` | `-x 段` / `-p 段`（字符串） |
| 一致性争议 | 展示层 | **以 readelf 为准** |

> 两者互补成对：`readelf -h` 判类型 → `readelf -l` 看布局 → `objdump -d -M intel` 看代码 → `readelf -V` 查版本。

---

## 11. 实战工作流

```bash
# 1) 拿到一个 ELF：先判类型与 PIE
readelf -h app | grep -E 'Type|Entry|Machine'
#    DYN + 非 0 入口 = PIE；EXEC = 非 PIE；.so 也是 DYN 但入口为 0

# 2) 依赖与 rpath（部署"not found"排查）
readelf -d app | grep -E 'NEEDED|RPATH|RUNPATH'

# 3) 最低 glibc 版本（"GLIBC_2.34 not found"）
readelf -V app | grep -A2 'File: libc' | grep 'Name:' | sort -V | tail -1

# 4) 安全检查（面试/自查加分项）
readelf -l app | grep -E 'GNU_STACK|GNU_RELRO'   # RWE = 可执行栈；有 GNU_RELRO = partial
readelf -d app | grep BIND_NOW                   # 有 = full RELRO
readelf -h app | grep 'Type:'                    # DYN = PIE

# 5) 崩溃地址对应符号（配合 addr2line，《04-目标文件分析.md》）
readelf --dyn-syms app | grep -E '0x4011a7|4011a7' || true   # 动态符号里找
addr2line -e app -f -C 0x4011a7

# 6) strip 后的线上版本只有动态符号
readelf -W --dyn-syms app | grep printf

# 7) 交叉架构（ARM/RISC-V 用交叉版，先 -h 核对 Machine）
aarch64-linux-gnu-readelf -h board.elf
aarch64-linux-gnu-readelf -A board.elf           # 架构特性扩展

# 8) .o 里函数/符号定位（undefined reference 排查）
readelf -W -s demo.o | grep -E 'FUNC|OBJECT'
```

---

## 12. 快速参考卡片

```bash
文件头/类型/PIE：    readelf -h app
段表（含调试段）：    readelf -S app
程序头/安全属性：     readelf -l app | grep -E 'GNU_STACK|GNU_RELRO'
依赖与 rpath：       readelf -d app | grep -E 'NEEDED|RPATH|RUNPATH'
full RELRO 判定：    readelf -d app | grep BIND_NOW
本地符号表：         readelf -W -s demo.o
动态符号（strip 后）： readelf -W --dyn-syms app
重定位：             readelf -r demo.o | grep -v debug
符号版本/glibc：     readelf -V app
段字节：             readelf -x .rodata app
字符串段：           readelf -p .dynstr app
宽输出防截断：        readelf -W ...
```

---

## 13. 常见问题与坑

1. **objdump 和 readelf "对不上"**：objdump 经 BFD 规整过，ELF 原始结构以 readelf 为准。
2. **`-s` 看不到符号**：文件被 strip 了，`.symtab` 已删，改用 `--dyn-syms`；`-s` 会自动回退显示 `.dynsym`。
3. **`Type: DYN` 别当共享库**：现代 PIE 可执行文件也是 DYN，区分看 `Entry` 是否非 0 和有没有 `PT_INTERP`。
4. **符号名被截成 `_[...]`**：忘了 `-W`/`--wide`，默认列宽截断长符号。
5. **`-d` 和反汇编无关**：readelf `-d` 是动态段（dynamic），不是 disassemble——看代码请去 objdump。
6. **`GLIBC_2.34 not found`**：`readelf -V` 看 Verneed，最低版本超标；换老基线编译或静态链接。
7. **`GNU_STACK` 出现 `E`**：可执行栈（NX 关闭），编译器/链接器选项问题，安全风险。
8. **分析交叉固件用错架构工具**：x86 的 readelf 也能读 ELF 头，但 `-A` 特性解析和部分字段需对应交叉版（`aarch64-linux-gnu-readelf`）。
9. **`-l` 输出太长**：grep `PT_LOAD`/`GNU_`/`Requesting` 只看关键行；`Section to Segment mapping` 用于把段归到加载段。
10. **`.rela.debug_*` 刷屏**：`-g` 编译导致，分析代码重定位用 `grep -v debug` 或只看 `.rela.text`。

---

上一篇：《04-目标文件分析.md》　｜　下一篇：《06-strace系统调用跟踪.md》　｜　模块索引：《../README.md》
