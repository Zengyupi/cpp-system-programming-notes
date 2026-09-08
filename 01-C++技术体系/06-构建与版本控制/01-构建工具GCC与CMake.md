# 构建工具：GCC / G++ / Make / CMake

> 本节目标：系统讲解 GCC/G++ 编译器、Make 构建工具与 CMake 跨平台构建系统的核心命令与使用方法，学完后能够独立完成 C/C++ 项目的编译、构建与配置。

## 本章速览

- [1. 概述](#1-概述)
- [2. GCC 命令](#2-gcc-命令)
  - [2.1 基本调用格式](#21-基本调用格式)
  - [2.2 编译阶段选项](#22-编译阶段选项)
  - [2.3 优化选项](#23-优化选项)
  - [2.4 调试与警告选项](#24-调试与警告选项)
  - [2.5 库与链接选项](#25-库与链接选项)
  - [2.6 标准版本选项](#26-标准版本选项)
  - [2.7 预处理定义](#27-预处理定义)
  - [2.8 常用 GCC 命令示例](#28-常用-gcc-命令示例)
  - [2.9 GCC 常用选项速查表](#29-gcc-常用选项速查表)
- [3. G++ 命令](#3-g-命令)
  - [3.1 基本调用格式](#31-基本调用格式)
  - [3.2 GCC 与 G++ 的区别](#32-gcc-与-g-的区别)
  - [3.3 C++ 特有选项](#33-c-特有选项)
  - [3.4 G++ 常用示例](#34-g-常用示例)
- [4. Make 命令](#4-make-命令)
  - [4.1 基本调用格式](#41-基本调用格式)
  - [4.2 常用选项](#42-常用选项)
  - [4.3 Makefile 基础语法](#43-makefile-基础语法)
  - [4.4 Makefile 常用内置变量](#44-makefile-常用内置变量)
  - [4.5 Makefile 常用函数](#45-makefile-常用函数)
  - [4.6 条件判断与循环](#46-条件判断与循环)
- [5. CMake 命令](#5-cmake-命令)
  - [5.1 基本调用格式](#51-基本调用格式)
  - [5.2 常用命令](#52-常用命令)
  - [5.3 常用生成器](#53-常用生成器)
  - [5.4 CMakeLists.txt 基础语法](#54-cmakeliststxt-基础语法)
  - [5.5 CMake 常用变量](#55-cmake-常用变量)
  - [5.6 CMake 常用命令](#56-cmake-常用命令)
  - [5.7 编译数据库生成](#57-编译数据库生成)
  - [5.8 完整 CMake 项目示例](#58-完整-cmake-项目示例)
  - [5.9 预设文件（CMakePresets.json）](#59-预设文件cmakepresetsjson)
- [6. 快速参考卡片](#6-快速参考卡片)
  - [6.1 GCC/G++ 速查](#61-gccg-速查)
  - [6.2 Make 速查](#62-make-速查)
  - [6.3 CMake 速查](#63-cmake-速查)
- [7. 常见编译错误与解决方案](#7-常见编译错误与解决方案)
- [8. 推荐构建流程](#8-推荐构建流程)
  - [8.1 简单项目（单文件）](#81-简单项目单文件)
  - [8.2 中型项目（多文件，手动 Makefile）](#82-中型项目多文件手动-makefile)
  - [8.3 大型项目（CMake + 构建工具）](#83-大型项目cmake--构建工具)

---

## 1. 概述

本文档涵盖 C/C++ 编译工具链的核心命令：**GCC**（C 编译器）、**G++**（C++ 编译器）、**Make**（构建自动化工具）和 **CMake**（跨平台构建系统生成器）。

| 工具      | 说明                     | 输入                           | 输出                                      |
| --------- | ------------------------ | ------------------------------ | ----------------------------------------- |
| **GCC**   | GNU C 编译器             | `.c` 源文件                    | 可执行文件 / `.o` 目标文件                |
| **G++**   | GNU C++ 编译器           | `.cpp` / `.cc` / `.cxx` 源文件 | 可执行文件 / `.o` 目标文件                |
| **Make**  | 基于 Makefile 的构建工具 | `Makefile`                     | 根据规则生成目标文件                      |
| **CMake** | 跨平台构建系统生成器     | `CMakeLists.txt`               | Makefile / Ninja / Visual Studio 项目文件 |

---

## 2. GCC 命令

### 2.1 基本调用格式

```text
gcc [选项] [源文件] [-o 输出文件]
```

### 2.2 编译阶段选项

| 选项        | 说明                                   | 示例                      |
| ----------- | -------------------------------------- | ------------------------- |
| `-E`        | 仅执行预处理（不编译、不汇编、不链接） | `gcc -E main.c -o main.i` |
| `-S`        | 编译到汇编代码（不汇编、不链接）       | `gcc -S main.c -o main.s` |
| `-c`        | 编译到目标文件（不链接）               | `gcc -c main.c -o main.o` |
| `-o <文件>` | 指定输出文件名                         | `gcc main.c -o program`   |
| `-v`        | 显示详细的编译过程                     | `gcc -v main.c`           |

```bash
# 编译分步示例
gcc -E main.c -o main.i      # 预处理
gcc -S main.i -o main.s      # 编译生成汇编
gcc -c main.s -o main.o      # 汇编生成目标文件
gcc main.o -o program        # 链接生成可执行文件

# 一步到位
gcc main.c -o program
```

### 2.3 优化选项

| 选项     | 说明                                | 示例                |
| -------- | ----------------------------------- | ------------------- |
| `-O0`    | 无优化（默认）                      | `gcc -O0 main.c`    |
| `-O1`    | 基本优化                            | `gcc -O1 main.c`    |
| `-O2`    | 推荐优化级别（速度优先）            | `gcc -O2 main.c`    |
| `-O3`    | 激进优化（可能增大体积）            | `gcc -O3 main.c`    |
| `-Os`    | 优化体积（嵌入式环境常用）          | `gcc -Os main.c`    |
| `-Ofast` | O3 + 激进浮点优化（不保证标准兼容） | `gcc -Ofast main.c` |
| `-Og`    | 调试友好的优化（兼顾调试和性能）    | `gcc -Og -g main.c` |

### 2.4 调试与警告选项

| 选项                       | 说明                              | 示例                                 |
| -------------------------- | --------------------------------- | ------------------------------------ |
| `-g`                       | 生成调试信息（供 GDB 使用）       | `gcc -g main.c -o program`           |
| `-ggdb`                    | 生成 GDB 专用调试信息（更详细）   | `gcc -ggdb3 main.c`                  |
| `-p` / `-pg`               | 生成性能分析信息（`-p` 供 prof，`-pg` 供 gprof 使用） | `gcc -pg main.c -o program`  |
| `-Wall`                    | 启用大部分警告                    | `gcc -Wall main.c`                   |
| `-Wextra`                  | 启用额外警告（比 -Wall 更多）     | `gcc -Wall -Wextra main.c`           |
| `-Werror`                  | 将所有警告视为错误                | `gcc -Werror main.c`                 |
| `-Wpedantic` / `-pedantic` | 严格遵循 C 标准                   | `gcc -Wall -pedantic main.c`         |
| `-Wshadow`                 | 警告变量名遮蔽                    | `gcc -Wshadow main.c`                |
| `-Wunused`                 | 警告未使用的变量/函数             | `gcc -Wunused main.c`                |
| `-Wconversion`             | 警告隐式类型转换                  | `gcc -Wconversion main.c`            |
| `-fsanitize=address`       | 启用地址消毒剂（ASan）            | `gcc -fsanitize=address -g main.c`   |
| `-fsanitize=undefined`     | 启用未定义行为消毒剂（UBSan）     | `gcc -fsanitize=undefined -g main.c` |
| `-fsanitize=thread`        | 启用线程消毒剂（TSan）            | `gcc -fsanitize=thread -g main.c`    |

```bash
# 调试信息 + 警告 + 优化
gcc -Wall -Wextra -O2 -g main.c -o program

# 启用 ASan 检测内存错误
gcc -fsanitize=address -g -O1 main.c -o program
```

### 2.5 库与链接选项

| 选项         | 说明                              | 示例                                   |
| ------------ | --------------------------------- | -------------------------------------- |
| `-l<库名>`   | 链接指定库（如 `-lm` 链接数学库） | `gcc main.c -lm -o program`            |
| `-L<路径>`   | 添加库搜索路径                    | `gcc main.c -L/usr/local/lib -lmylib`  |
| `-I<路径>`   | 添加头文件搜索路径                | `gcc -I./include main.c`               |
| `-static`    | 静态链接（不使用共享库）          | `gcc -static main.c -o program`        |
| `-shared`    | 生成共享库（.so）                 | `gcc -shared -fPIC -o libmylib.so *.o` |
| `-fPIC`      | 生成位置无关代码（共享库必需）    | `gcc -fPIC -c file.c`                  |
| `-Wl,<选项>` | 传递选项给链接器                  | `gcc -Wl,-Map=out.map main.c`         |
| `-Wl,-rpath,<路径>` | 指定运行时库搜索路径（注意：GCC 没有 `-rpath` 直接选项，必须通过 `-Wl` 转发） | `gcc main.c -Wl,-rpath,/opt/lib -L/opt/lib -lmylib` |
| `-no-pie`    | 禁用 PIE（位置无关可执行文件）    | `gcc -no-pie main.c -o program`        |

```bash
# 链接数学库（-lm）
gcc main.c -lm -o program

# 链接自定义库
gcc main.c -L./lib -lmylib -I./include -o program

# 创建共享库
gcc -fPIC -c file1.c file2.c
gcc -shared -o libmylib.so file1.o file2.o

# 创建静态库（ar：r 替换/新增成员，c 创建库，s 建索引）
gcc -c file1.c file2.c
ar rcs libmylib.a file1.o file2.o

# 使用静态库
gcc main.c -L. -lmylib -o program

# 使用共享库（指定运行时路径）
gcc main.c -L. -lmylib -Wl,-rpath,. -o program
```

### 2.6 标准版本选项

| 选项                    | 说明           | 示例                    |
| ----------------------- | -------------- | ----------------------- |
| `-std=c89` / `-std=c90` | C89/C90 标准   | `gcc -std=c89 main.c`   |
| `-std=c99`              | C99 标准       | `gcc -std=c99 main.c`   |
| `-std=c11`              | C11 标准       | `gcc -std=c11 main.c`   |
| `-std=c17` / `-std=c18` | C17/C18 标准   | `gcc -std=c17 main.c`   |
| `-std=gnu99`            | C99 + GNU 扩展 | `gcc -std=gnu99 main.c` |
| `-std=gnu11`            | C11 + GNU 扩展 | `gcc -std=gnu11 main.c` |

### 2.7 预处理定义

| 选项              | 说明               | 示例                               |
| ----------------- | ------------------ | ---------------------------------- |
| `-D<宏>[=<值>]`   | 定义宏             | `gcc -DDEBUG -DVERSION=1.0 main.c` |
| `-U<宏>`          | 取消宏定义         | `gcc -UDEBUG main.c`               |
| `-include <文件>` | 在编译前包含头文件 | `gcc -include config.h main.c`     |

```bash
# 定义 DEBUG 宏，代码中可用 #ifdef DEBUG
gcc -DDEBUG main.c -o program

# 定义多个宏
gcc -DDEBUG -DVERSION=\"1.0.0\" main.c
```

### 2.8 常用 GCC 命令示例

```bash
# 编译单个源文件
gcc main.c -o program

# 编译多个源文件
gcc main.c utils.c math.c -o program

# 编译 + 调试信息 + 警告 + 优化
gcc -Wall -Wextra -O2 -g main.c -o program

# 编译共享库
gcc -fPIC -c *.c
gcc -shared -o libmylib.so *.o

# 静态链接
gcc -static main.c -o program

# 使用 AddressSanitizer 调试
gcc -fsanitize=address -g -O1 main.c -o program

# 交叉编译（ARM 平台示例）
arm-linux-gnueabihf-gcc main.c -o program_arm
```

### 2.9 GCC 常用选项速查表

| 分类   | 选项                                         |
| ------ | -------------------------------------------- |
| 基本   | `-c`、`-S`、`-E`、`-o`、`-v`                 |
| 优化   | `-O0`、`-O1`、`-O2`、`-O3`、`-Os`、`-Og`     |
| 调试   | `-g`、`-ggdb`、`-p`、`-pg`                   |
| 警告   | `-Wall`、`-Wextra`、`-Werror`、`-pedantic`   |
| 路径   | `-I`、`-L`、`-l`、`-Wl,-rpath`               |
| 链接   | `-static`、`-shared`、`-fPIC`                |
| 标准   | `-std=c99`、`-std=c11`、`-std=gnu11`         |
| 预处理 | `-D`、`-U`、`-include`                       |
| 消毒剂 | `-fsanitize=address`、`-fsanitize=undefined` |

---

## 3. G++ 命令

### 3.1 基本调用格式

```text
g++ [选项] [源文件] [-o 输出文件]
```

### 3.2 GCC 与 G++ 的区别

| 区别       | GCC                      | G++                                 |
| ---------- | ------------------------ | ----------------------------------- |
| 默认语言   | C                        | C++                                 |
| 自动链接   | 不自动链接 C++ 标准库    | 自动链接 `libstdc++`                |
| 文件扩展名 | `.c` 视为 C              | `.c` 也视为 C++（可用 `-x c` 指定） |
| 兼容性     | 可编译 C++，但需手动链接 | 可编译 C，但使用 C++ 语义           |

```text
# 相同选项在 g++ 中同样有效
g++ main.cpp -o program
g++ -Wall -O2 -g main.cpp -o program
```

### 3.3 C++ 特有选项

| 选项                  | 说明                        | 示例                                    |
| --------------------- | --------------------------- | --------------------------------------- |
| `-std=c++98`          | C++98 标准                  | `g++ -std=c++98 main.cpp`               |
| `-std=c++11`          | C++11 标准                  | `g++ -std=c++11 main.cpp`               |
| `-std=c++14`          | C++14 标准                  | `g++ -std=c++14 main.cpp`               |
| `-std=c++17`          | C++17 标准（推荐）          | `g++ -std=c++17 main.cpp`               |
| `-std=c++20`          | C++20 标准                  | `g++ -std=c++20 main.cpp`               |
| `-std=gnu++17`        | C++17 + GNU 扩展            | `g++ -std=gnu++17 main.cpp`             |
| `-fno-exceptions`     | 禁用 C++ 异常               | `g++ -fno-exceptions main.cpp`          |
| `-fno-rtti`           | 禁用运行时类型信息（RTTI）  | `g++ -fno-rtti main.cpp`                |
| `-Weffc++`            | 警告违反 Effective C++ 建议 | `g++ -Weffc++ main.cpp`                 |
| `-fvisibility=hidden` | 隐藏符号（共享库优化）      | `g++ -fvisibility=hidden -shared *.cpp` |

```text
# C++11 标准 + 所有警告
g++ -std=c++11 -Wall -Wextra main.cpp -o program

# C++17 标准 + 调试 + 优化
g++ -std=c++17 -O2 -g main.cpp -o program

# 禁用异常（嵌入式场景）
g++ -fno-exceptions -fno-rtti main.cpp -o program
```

### 3.4 G++ 常用示例

```text
# 编译单个 C++ 文件
g++ main.cpp -o program

# 编译多个 C++ 文件
g++ main.cpp utils.cpp class.cpp -o program

# 编译 + 调试 + 优化 + 标准
g++ -std=c++17 -O2 -g -Wall -Wextra main.cpp -o program

# 链接 C++ 库（如 Boost）
g++ main.cpp -lboost_system -lboost_filesystem -o program

# 编译共享库
g++ -fPIC -std=c++17 -c *.cpp
g++ -shared -o libmycpplib.so *.o
```

---

## 4. Make 命令

### 4.1 基本调用格式

```bash
make [选项] [目标]
```

### 4.2 常用选项

| 选项            | 说明                                  | 示例                       |
| --------------- | ------------------------------------- | -------------------------- |
| `-f <文件>`     | 指定 Makefile 文件（默认 `Makefile`） | `make -f MyMakefile`       |
| `-j <数量>`     | 并行执行（`-j$(nproc)` 使用所有核心） | `make -j4`                 |
| `-k`            | 遇到错误继续构建（而非停止）          | `make -k`                  |
| `-n`            | 模拟运行（只打印命令，不执行）        | `make -n`                  |
| `-B`            | 强制重新构建所有目标                  | `make -B`                  |
| `-C <目录>`     | 切换到目录再执行 make                 | `make -C /build`           |
| `-d`            | 显示调试信息                          | `make -d`                  |
| `-s`            | 安静模式（不输出命令）                | `make -s`                  |
| `-q`            | 检查目标是否需要重建（0=最新，1=需重建，2=出错） | `make -q program`          |
| `--dry-run`     | 同 `-n`                               | `make --dry-run`           |
| `--always-make` | 同 `-B`                               | `make --always-make`       |
| `VAR=value`     | 在命令行设置变量                      | `make CC=clang CFLAGS=-O3` |

```bash
# 默认构建（第一个目标）
make

# 指定目标构建
make clean
make install

# 并行构建（4 线程）
make -j4

# 使用所有 CPU 核心
make -j$(nproc)

# 清理并重新构建
make clean && make -j$(nproc)

# 指定编译器
make CC=clang CXX=clang++

# 调试模式，查看执行内容
make -n -j4
```

### 4.3 Makefile 基础语法

```makefile
# ==================================================
# Makefile 示例
# ==================================================

# 变量定义
CC = gcc
CXX = g++
CFLAGS = -Wall -Wextra -O2 -g -MMD -MP   # -MMD -MP 自动生成头文件依赖
CXXFLAGS = -std=c++17 -Wall -Wextra -O2 -g -MMD -MP
LDFLAGS = -lm
TARGET = program
SRCS = main.c utils.c math.c
OBJS = $(SRCS:.c=.o)          # 将 .c 替换为 .o
DEPS = $(OBJS:.o=.d)          # 依赖文件（由 -MMD 生成）

# 默认目标（第一个目标）
all: $(TARGET)

# 链接目标
$(TARGET): $(OBJS)
	$(CC) $^ -o $@ $(LDFLAGS)

# 编译规则（模式规则）
%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

# 引入依赖文件（头文件变化时自动触发重编译）
-include $(DEPS)

# 清理
clean:
	rm -f $(OBJS) $(TARGET) $(DEPS)

# 伪目标
.PHONY: all clean install debug

# 安装
install: $(TARGET)
	cp $(TARGET) /usr/local/bin/

# 调试目标
debug:
	@echo "SRCS: $(SRCS)"
	@echo "OBJS: $(OBJS)"
```

### 4.4 Makefile 常用内置变量

| 变量    | 说明                         |
| ------- | ---------------------------- |
| `$@`    | 当前目标名称                 |
| `$<`    | 第一个依赖文件               |
| `$^`    | 所有依赖文件（去重）         |
| `$+`    | 所有依赖文件（含重复）       |
| `$*`    | 目标文件的主干（不带扩展名） |
| `$?`    | 所有比目标新的依赖文件       |
| `$(@D)` | 目标所在的目录               |
| `$(@F)` | 目标的文件名（不含目录）     |

```makefile
# 变量使用示例
%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@
# $< 表示当前正在处理的 .c 文件
# $@ 表示当前目标 .o 文件
```

### 4.5 Makefile 常用函数

| 函数                          | 说明            | 示例                           |
| ----------------------------- | --------------- | ------------------------------ |
| `$(wildcard 模式)`            | 查找匹配的文件  | `$(wildcard *.c)`              |
| `$(patsubst 模式,替换,文本)`  | 模式替换        | `$(patsubst %.c,%.o,$(SRCS))`  |
| `$(notdir 路径)`              | 提取文件名      | `$(notdir /path/to/file.c)`    |
| `$(dir 路径)`                 | 提取目录        | `$(dir /path/to/file.c)`       |
| `$(shell 命令)`               | 执行 shell 命令 | `$(shell pwd)`                 |
| `$(foreach 变量,列表,表达式)` | 循环            | `$(foreach f,$(FILES),$(f).o)` |
| `$(if 条件,真值,假值)`        | 条件判断        | `$(if $(DEBUG),-g,-O2)`        |
| `$(addprefix 前缀,列表)`      | 添加前缀        | `$(addprefix src/,$(FILES))`   |
| `$(addsuffix 后缀,列表)`      | 添加后缀        | `$(addsuffix .o,$(FILES))`     |

```text
# 示例：自动收集源文件
SRC_DIR = src
SRCS = $(wildcard $(SRC_DIR)/*.c)
OBJS = $(patsubst $(SRC_DIR)/%.c, build/%.o, $(SRCS))

# 示例：条件编译
ifeq ($(DEBUG),1)
    CFLAGS += -g -DDEBUG
else
    CFLAGS += -O2
endif
```

### 4.6 条件判断与循环

```text
# 条件判断
ifeq ($(OS),Windows_NT)
    TARGET = program.exe
    RM = del
else
    TARGET = program
    RM = rm -f
endif

ifdef DEBUG
    CFLAGS += -g -DDEBUG
endif

# 循环（使用 foreach）
FILES = file1 file2 file3
OBJS = $(foreach f,$(FILES),$(f).o)
```

---

## 5. CMake 命令

### 5.1 基本调用格式

```text
cmake [选项] [源目录] -B [构建目录]
```

### 5.2 常用命令

| 命令                            | 说明               | 示例                                        |
| ------------------------------- | ------------------ | ------------------------------------------- |
| `cmake -B <目录>`               | 指定构建目录       | `cmake -B build`                            |
| `cmake -S <目录>`               | 指定源目录         | `cmake -S . -B build`                       |
| `cmake --build <目录>`          | 构建项目           | `cmake --build build`                       |
| `cmake --install <目录>`        | 安装项目           | `cmake --install build --prefix /usr/local` |
| `cmake -D<变量>=<值>`           | 设置 CMake 变量    | `cmake -DCMAKE_BUILD_TYPE=Release`          |
| `cmake -G <生成器>`             | 指定构建系统生成器 | `cmake -G "Ninja"`                          |
| `cmake --build --target <目标>` | 构建指定目标       | `cmake --build build --target clean`        |
| `cmake -E`                      | 跨平台命令工具     | `cmake -E copy file1 file2`                 |
| `cmake --help`                  | 显示帮助           | `cmake --help`                              |
| `cmake --help-command-list`     | 列出所有命令       | `cmake --help-command-list`                 |

```bash
# 标准构建流程（推荐）
mkdir build && cd build
cmake ..
cmake --build .
sudo cmake --install . --prefix /usr/local

# 一行命令（CMake 3.13+）
cmake -B build -S .
cmake --build build -j$(nproc)

# 指定构建类型
cmake -B build -DCMAKE_BUILD_TYPE=Release

# 指定安装路径
cmake -B build -DCMAKE_INSTALL_PREFIX=/opt/myapp

# 使用 Ninja 生成器
cmake -B build -G Ninja
ninja -C build

# 清理构建
cmake --build build --target clean
rm -rf build  # 完全清理
```

### 5.3 常用生成器

| 生成器                  | 说明                     | 示例                               |
| ----------------------- | ------------------------ | ---------------------------------- |
| `Unix Makefiles`        | Unix/Linux 默认 Makefile | `cmake -G "Unix Makefiles"`        |
| `Ninja`                 | 快速构建系统（推荐）     | `cmake -G "Ninja"`                 |
| `Visual Studio 17 2022` | Visual Studio 2022       | `cmake -G "Visual Studio 17 2022"` |
| `Xcode`                 | macOS Xcode 项目         | `cmake -G "Xcode"`                 |
| `MinGW Makefiles`       | Windows MinGW            | `cmake -G "MinGW Makefiles"`       |

### 5.4 CMakeLists.txt 基础语法

```cmake
# ==================================================
# CMakeLists.txt 示例
# ==================================================

# 最低 CMake 版本要求
cmake_minimum_required(VERSION 3.10)

# 项目名称和版本
project(MyProject VERSION 1.0.0 LANGUAGES C CXX)

# 设置 C++ 标准
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# 设置构建类型（若未指定）
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# 添加可执行文件
add_executable(myapp main.c utils.c math.c)

# 添加头文件路径
target_include_directories(myapp PRIVATE include)

# 链接库
target_link_libraries(myapp PRIVATE m)

# 设置输出目录
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)

# 安装规则
install(TARGETS myapp
    RUNTIME DESTINATION bin
    LIBRARY DESTINATION lib
    ARCHIVE DESTINATION lib
)

# 添加子目录（模块化）
add_subdirectory(src)
add_subdirectory(tests)

# 编译选项
target_compile_options(myapp PRIVATE -Wall -Wextra -O2)

# 条件编译
if(CMAKE_BUILD_TYPE STREQUAL "Debug")
    target_compile_definitions(myapp PRIVATE DEBUG)
endif()
```

### 5.5 CMake 常用变量

| 变量                            | 说明           | 示例值                                                |
| ------------------------------- | -------------- | ----------------------------------------------------- |
| `CMAKE_BUILD_TYPE`              | 构建类型       | `Debug` / `Release` / `RelWithDebInfo` / `MinSizeRel` |
| `CMAKE_INSTALL_PREFIX`          | 安装路径       | `/usr/local`                                          |
| `CMAKE_CXX_STANDARD`            | C++ 标准版本   | `11` / `14` / `17` / `20`                             |
| `CMAKE_SOURCE_DIR`              | 源目录路径     | `/home/user/project`                                  |
| `CMAKE_BINARY_DIR`              | 构建目录路径   | `/home/user/project/build`                            |
| `CMAKE_C_COMPILER`              | C 编译器       | `gcc` / `clang`                                       |
| `CMAKE_CXX_COMPILER`            | C++ 编译器     | `g++` / `clang++`                                     |
| `CMAKE_C_FLAGS`                 | C 编译器标志   | `-Wall -O2`                                           |
| `CMAKE_CXX_FLAGS`               | C++ 编译器标志 | `-Wall -O2`                                           |
| `CMAKE_EXPORT_COMPILE_COMMANDS` | 导出编译数据库 | `ON`                                                  |

```bash
# 在命令行设置变量
cmake -B build -DCMAKE_BUILD_TYPE=Debug \
                -DCMAKE_INSTALL_PREFIX=/opt/myapp \
                -DCMAKE_CXX_STANDARD=20 \
                -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
```

### 5.6 CMake 常用命令

| 命令                           | 说明                     | 示例                                                |
| ------------------------------ | ------------------------ | --------------------------------------------------- |
| `project()`                    | 定义项目名称和版本       | `project(MyApp VERSION 1.0)`                        |
| `add_executable()`             | 添加可执行文件           | `add_executable(myapp main.cpp)`                    |
| `add_library()`                | 添加库                   | `add_library(mylib STATIC util.cpp)`                |
| `target_link_libraries()`      | 链接库                   | `target_link_libraries(myapp PRIVATE mylib)`        |
| `target_include_directories()` | 添加头文件路径           | `target_include_directories(myapp PRIVATE include)` |
| `target_compile_definitions()` | 添加宏定义               | `target_compile_definitions(myapp PRIVATE DEBUG)`   |
| `target_compile_features()`    | 声明需要 C++ 特性        | `target_compile_features(myapp PRIVATE cxx_std_17)` |
| `add_subdirectory()`           | 添加子目录               | `add_subdirectory(src)`                             |
| `include_directories()`        | 全局头文件路径（不推荐） | `include_directories(include)`                      |
| `link_directories()`           | 全局库路径（不推荐）     | `link_directories(/usr/local/lib)`                  |
| `find_package()`               | 查找外部包               | `find_package(OpenSSL REQUIRED)`                    |
| `find_library()`               | 查找库                   | `find_library(MATH_LIB m)`                          |
| `find_path()`                  | 查找头文件路径           | `find_path(OPENSSL_INC openssl/ssl.h)`              |
| `option()`                     | 定义开关选项             | `option(BUILD_TESTS "构建测试" ON)`                 |
| `message()`                    | 打印信息                 | `message(STATUS "Project: ${PROJECT_NAME}")`        |
| `include()`                    | 包含其他 CMake 文件      | `include(${CMAKE_CURRENT_SOURCE_DIR}/cmake/helpers.cmake)` |
| `add_custom_target()`          | 添加自定义目标           | `add_custom_target(format COMMAND clang-format)`    |
| `add_custom_command()`         | 添加自定义命令           | `add_custom_command(OUTPUT file DEPENDS input)`     |
| `file()`                       | 文件操作                 | `file(GLOB SRCS *.cpp)`                             |
| `configure_file()`             | 配置模板文件             | `configure_file(config.h.in config.h)`              |

### 5.7 编译数据库生成

```bash
# 生成 compile_commands.json（clangd / IDE 使用）
cmake -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
ln -s build/compile_commands.json .  # 软链接到根目录
```

### 5.8 完整 CMake 项目示例

```cmake
# ==================================================
# 完整 CMakeLists.txt 示例（多模块项目）
# ==================================================

cmake_minimum_required(VERSION 3.15)
project(MyApp VERSION 1.0.0 LANGUAGES CXX)

# ==================== 选项 ====================
option(BUILD_TESTS "Build tests" ON)
option(BUILD_EXAMPLES "Build examples" OFF)
option(USE_SANITIZER "Enable sanitizers" OFF)

# ==================== 标准 ====================
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# ==================== 构建类型 ====================
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
endif()

# ==================== 编译选项 ====================
# 注意：用列表（分号/多个参数）保存选项，而不是带空格的字符串，
# 否则 add_compile_options(${COMMON_FLAGS}) 会把整串当成一个参数
set(COMMON_FLAGS -Wall -Wextra -Wpedantic)
if(CMAKE_BUILD_TYPE STREQUAL "Debug")
    list(APPEND COMMON_FLAGS -g -O0)
else()
    list(APPEND COMMON_FLAGS -O2)
endif()

if(USE_SANITIZER)
    list(APPEND COMMON_FLAGS -fsanitize=address,undefined)
endif()

add_compile_options(${COMMON_FLAGS})

# ==================== 核心库（静态） ====================
add_library(MyCore STATIC
    src/core/engine.cpp
    src/core/manager.cpp
)

target_include_directories(MyCore
    PUBLIC
        include
    PRIVATE
        src
)

# ==================== 主程序 ====================
add_executable(${PROJECT_NAME}
    src/main.cpp
    src/utils/logger.cpp
)

target_link_libraries(${PROJECT_NAME}
    PRIVATE
        MyCore
        pthread
        m
)

target_include_directories(${PROJECT_NAME}
    PRIVATE
        src
    PUBLIC
        include
)

# ==================== 测试 ====================
if(BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()

# ==================== 示例 ====================
if(BUILD_EXAMPLES)
    add_subdirectory(examples)
endif()

# ==================== 安装 ====================
install(TARGETS ${PROJECT_NAME}
    RUNTIME DESTINATION bin
)

install(TARGETS MyCore
    ARCHIVE DESTINATION lib
)

# 若库有公开头文件需要安装，可使用：
# install(DIRECTORY include/ DESTINATION include/MyCore)

# ==================== 编译数据库 ====================
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# ==================== 自定义目标 ====================
add_custom_target(format
    COMMAND clang-format -i src/*.cpp src/*.h include/*.h
    COMMENT "Running clang-format"
)
```

### 5.9 预设文件（CMakePresets.json）

```json
{
  "version": 3,
  "cmakeMinimumRequired": {
    "major": 3,
    "minor": 21
  },
  "configurePresets": [
    {
      "name": "default",
      "generator": "Ninja",
      "binaryDir": "build",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Release",
        "CMAKE_CXX_STANDARD": "17",
        "CMAKE_EXPORT_COMPILE_COMMANDS": "ON"
      }
    },
    {
      "name": "debug",
      "inherits": "default",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Debug"
      }
    }
  ],
  "buildPresets": [
    {
      "name": "default",
      "configurePreset": "default"
    },
    {
      "name": "debug",
      "configurePreset": "debug"
    }
  ]
}
```

```bash
# 使用预设文件
cmake --preset default
cmake --build --preset default
```

---

## 6. 快速参考卡片

### 6.1 GCC/G++ 速查

| 场景           | 命令                                   |
| -------------- | -------------------------------------- |
| 编译 C 文件    | `gcc main.c -o program`                |
| 编译 C++ 文件  | `g++ main.cpp -o program`              |
| 编译多个文件   | `gcc main.c util.c -o program`         |
| 调试版本       | `gcc -g -O0 main.c -o program`         |
| 发布版本       | `gcc -O2 main.c -o program`            |
| 启用警告       | `gcc -Wall -Wextra main.c`             |
| 指定 C++ 标准  | `g++ -std=c++17 main.cpp`              |
| 链接数学库     | `gcc main.c -lm -o program`            |
| 添加头文件路径 | `gcc -I./include main.c`               |
| 添加库路径     | `gcc -L./lib -lmylib main.c`           |
| 创建静态库     | `ar rcs libmylib.a *.o`                |
| 创建共享库     | `gcc -shared -fPIC -o libmylib.so *.o` |
| ASan 调试      | `gcc -fsanitize=address -g main.c`     |

### 6.2 Make 速查

| 场景          | 命令                          |
| ------------- | ----------------------------- |
| 构建项目      | `make`                        |
| 指定目标      | `make clean` / `make install` |
| 并行构建      | `make -j4`                    |
| 使用所有核心  | `make -j$(nproc)`             |
| 模拟运行      | `make -n`                     |
| 强制重新构建  | `make -B`                     |
| 指定 Makefile | `make -f MyMakefile`          |
| 设置变量      | `make CC=clang`               |

### 6.3 CMake 速查

| 场景         | 命令                                                |
| ------------ | --------------------------------------------------- |
| 标准构建     | `cmake -B build && cmake --build build`             |
| 指定构建类型 | `cmake -B build -DCMAKE_BUILD_TYPE=Release`         |
| 指定安装路径 | `cmake -B build -DCMAKE_INSTALL_PREFIX=/opt/app`    |
| 使用 Ninja   | `cmake -B build -G Ninja`                           |
| 安装         | `sudo cmake --install build`                        |
| 清理构建     | `rm -rf build`                                      |
| 编译数据库   | `cmake -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON` |
| 使用预设     | `cmake --preset default`                            |

---

## 7. 常见编译错误与解决方案

| 错误                                    | 原因                 | 解决方案                                |
| --------------------------------------- | -------------------- | --------------------------------------- |
| `undefined reference to 'function'`     | 链接时找不到函数     | 检查是否链接了对应的库（`-l`）          |
| `fatal error: header.h: No such file`   | 头文件找不到         | 添加 `-I` 路径                          |
| `cannot find -lmylib`                   | 库文件找不到         | 添加 `-L` 路径或检查库名                |
| `error: 'xxx' was not declared`         | 未包含正确头文件     | 检查 `#include`                         |
| `error: 'xxx' is not a member of 'std'` | 未包含或标准版本不符 | 检查头文件或 `-std=c++11`               |
| `multiple definition of 'xxx'`          | 重复定义             | 使用 `inline` 或 `static`，或头文件守卫 |
| `relocation R_X86_64_32 against ...`    | 链接时 PIC 问题      | 编译时添加 `-fPIC`                      |
| `CMake Error: Could not find ...`       | CMake 找不到依赖     | 安装依赖或设置 `CMAKE_PREFIX_PATH`      |

---

## 8. 推荐构建流程

### 8.1 简单项目（单文件）

```bash
gcc main.c -Wall -O2 -g -o program
```

### 8.2 中型项目（多文件，手动 Makefile）

```bash
make -j$(nproc)
make install
```

### 8.3 大型项目（CMake + 构建工具）

```bash
cmake -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cmake --build build -j$(nproc)
ctest --test-dir build  # 运行测试
sudo cmake --install build
```

---

下一篇：《02-依赖管理与包管理器.md》
