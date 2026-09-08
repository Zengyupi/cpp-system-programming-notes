# Python 脚本与自动化（C++ 工程师视角）

> 本节目标：面向已有 C++ 基础的学习者，讲解当 Shell 力不从心、又不值得动用 C++ 时如何用 Python 快速搞定任务，涵盖结构化文本/日志处理、驱动编译与回归测试、二进制协议帧解析、数据统计以及 C++ 模块的脚本胶水层。语法对照 C++ 讲解，工程化（虚拟环境、依赖、lint、与 C++ 互调）讲透。学完后能够根据任务特点选择 Python 并编写健壮的自动化脚本。命令行操作见《../08-网络与系统工具/01-Linux命令行速查.md》，Shell 适用场景见《04-Shell脚本编程.md》，二进制字节序见《../08-网络与系统工具/03-二进制查看工具.md》。

## 本章速览

- [1. 什么时候用 Python：C++ / Shell / Python 分工](#1-什么时候用-pythonc--shell--python-分工)
- [2. 环境与工程化（先把环境搞干净）](#2-环境与工程化先把环境搞干净)
  - [2.1 解释器与版本](#21-解释器与版本)
  - [2.2 虚拟环境（必须养成习惯）](#22-虚拟环境必须养成习惯)
  - [2.3 国内镜像源（下载慢必配）](#23-国内镜像源下载慢必配)
  - [2.4 现代项目结构与依赖声明](#24-现代项目结构与依赖声明)
- [3. 核心语法速通（对照 C++）](#3-核心语法速通对照-c)
  - [3.1 思维差异（先扭转过来）](#31-思维差异先扭转过来)
  - [3.2 内置容器（最高频）](#32-内置容器最高频)
  - [3.3 推导式（替代手写循环，Python 灵魂）](#33-推导式替代手写循环python-灵魂)
  - [3.4 函数、多返回值、默认参数、类型注解](#34-函数多返回值默认参数类型注解)
  - [3.5 异常与 with（上下文管理器 = Python 版 RAII）](#35-异常与-with上下文管理器--python-版-raii)
  - [3.6 迭代器与生成器（惰性、省内存）](#36-迭代器与生成器惰性省内存)
- [4. 常用标准库（C++ 工程里最实用的一批）](#4-常用标准库c-工程里最实用的一批)
  - [4.1 subprocess：驱动编译与测试（替代手写 shell 串命令）](#41-subprocess驱动编译与测试替代手写-shell-串命令)
  - [4.2 argparse：正规命令行工具](#42-argparse正规命令行工具)
  - [4.3 logging：别再用 print 调试](#43-logging别再用-print-调试)
- [5. 四个 C++ 工程师高频实战](#5-四个-c-工程师高频实战)
  - [5.1 结构化日志分析（比 awk/sed 好维护）](#51-结构化日志分析比-awksed-好维护)
  - [5.2 驱动批量回归测试](#52-驱动批量回归测试)
  - [5.3 struct 解析二进制协议帧（呼应 Modbus / hexdump）](#53-struct-解析二进制协议帧呼应-modbus--hexdump)
  - [5.4 数据统计：numpy / pandas 速览](#54-数据统计numpy--pandas-速览)
- [6. 三类并发模型（知道何时用哪个）](#6-三类并发模型知道何时用哪个)
- [7. Python 与 C++ 互操作（核心加分项）](#7-python-与-c-互操作核心加分项)
  - [7.1 三种方式对比](#71-三种方式对比)
  - [7.2 ctypes 直接调动态库](#72-ctypes-直接调动态库)
  - [7.3 pybind11 绑定（推荐，header-only）](#73-pybind11-绑定推荐header-only)
- [8. 代码质量与工程规范](#8-代码质量与工程规范)
- [9. AI 胶水：用 Python 把大模型接进工具链](#9-ai-胶水用-python-把大模型接进工具链)
- [10. 快速参考卡片](#10-快速参考卡片)
- [11. 常见问题与坑](#11-常见问题与坑)
- [12. 延伸阅读与官方资料](#12-延伸阅读与官方资料)

---

## 1. 什么时候用 Python：C++ / Shell / Python 分工

| 任务特征 | 选择 | 原因 |
| --- | --- | --- |
| 几条命令串联、简单管道、启停服务 | **Shell** | 最短、原生、无依赖 |
| 复杂数据结构、JSON/CSV 解析、正则多分支、跨平台、超过 100 行逻辑 | **Python** | Shell 一复杂就难维护（引号地狱、错误处理弱） |
| 性能敏感、常驻服务、直接操作硬件/内核、交付给客户的核心模块 | **C++** | Python 有解释器开销与 GIL |
| 用 C++ 写好核心算法，外层要灵活配置/快速验证/给测试同学用 | **C++ 核心 + Python 绑定** | 性能与灵活性兼得（见第 7 章） |

> 经验法则：**Shell 写"胶水"，C++ 写"引擎"，Python 写"工具与原型"**。一个 C++ 后台项目里，Python 常出现在：构建脚本、自动化测试、压测/数据造数、日志分析、运维工具、原型验证。招聘 JD 里"至少掌握一门脚本语言（Python/Lua/Shell）"几乎是标配。

---

## 2. 环境与工程化（先把环境搞干净）

### 2.1 解释器与版本

```bash
python3 --version            # 认准 python3 / py -3（Windows）
which -a python3             # 可能有多个解释器，确认当前用哪个
ls -l $(which python3)       # 看是否软链到具体版本
```

- 生产/嵌入式目标板上的 Python 多为 **3.8~3.10**（受发行版限制），写脚本别随手用 3.10+ 才有的语法（如 `match-case` 是 3.10、`X | Y` 类型联合是 3.10、`tomllib` 是 3.11）。
- Windows 上 `python` 可能指向商店占位符或另一个版本，多版本用 **py 启动器**：`py -3.12 script.py`。

### 2.2 虚拟环境（必须养成习惯）

虚拟环境给每个项目独立的依赖目录，避免"装了个全局包把别的项目搞崩"。

```bash
# 标准库 venv（无需额外安装，推荐）
python3 -m venv .venv                 # 在项目下创建 .venv
source .venv/bin/activate             # Linux/macOS 激活
.venv\Scripts\Activate.ps1            # Windows PowerShell 激活
deactivate                            # 退出

# 激活后 pip 只装到这个环境
pip install requests
pip freeze > requirements.txt         # 锁定精确版本
pip install -r requirements.txt       # 别人/CI 一键复现
```

| 工具 | 定位 |
| --- | --- |
| `venv` | 标准库自带，够用 |
| `conda`/`miniconda` | 数据科学、需要管理非 Python 二进制依赖（如 CUDA/numpy 版本） |
| `uv` | Rust 写的新一代包管理器，装包/建虚拟环境极快（`uv venv`、`uv pip install`），2025 后流行 |
| `pyenv` | 在一台机器装/切多个 Python 版本 |

### 2.3 国内镜像源（下载慢必配）

```bash
# 临时用
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple requests
# 永久配置
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

### 2.4 现代项目结构与依赖声明

```text
my_tool/
├── my_tool/                # 包目录
│   ├── __init__.py
│   └── core.py
├── tests/
│   └── test_core.py
├── pyproject.toml          # 现代标准：项目元信息+依赖+工具配置（推荐）
├── requirements.txt        # 部署锁定版本（pip freeze 生成）
└── README.md
```

`pyproject.toml` 片段：

```ini
[project]
name = "my-tool"
version = "0.1.0"
requires-python = ">=3.9"
dependencies = ["requests>=2.31", "pydantic>=2.0"]

[project.scripts]
mytool = "my_tool.core:main"     # 安装后生成 mytool 命令
```

---

## 3. 核心语法速通（对照 C++）

### 3.1 思维差异（先扭转过来）

| 维度 | C++ | Python |
| --- | --- | --- |
| 类型 | 静态强类型，编译期定 | **动态强类型**，变量是"贴在对象上的标签"，运行期定 |
| 内存 | 手动/RAII/智能指针 | 引用计数 + GC，`with` 管理资源 |
| 语句结尾/作用域 | `;` 和 `{}` | **缩进即作用域**（无大括号，统一 4 空格） |
| 容器 | `std::vector/map/set` | `list/dict/set/tuple` 字面量直接写 |
| 循环 | 下标/迭代器 | `for x in 可迭代对象`，少用下标 |
| 空值/布尔 | `nullptr`/`true` | `None`/`True`/`False` |
| 编译 | 先编译后运行 | 解释执行，出错在运行期 |

### 3.2 内置容器（最高频）

```python
# list：相当于 vector，可混装、可改
xs = [1, 2, 3]
xs.append(4)            # 尾部加
xs[0] = 10
print(xs[-1])           # 负索引 = 倒数第一个 -> 4
print(xs[1:3])          # 切片 [起:止)，左闭右开

# tuple：不可变，常用于多返回值、做 dict 的 key
point = (3, 4)
x, y = point            # 解包

# dict：相当于 unordered_map，key 必须可哈希
d = {"name": "gw", "port": 502}
d["baud"] = 9600
for k, v in d.items():  # 直接遍历键值对
    print(k, v)
print(d.get("x", 0))    # key 不存在给默认值，不抛异常

# set：去重、集合运算
s = {1, 2, 2, 3}        # {1,2,3}
a, b = {1, 2}, {2, 3}
print(a & b, a | b)     # 交集 {2}，并集 {1,2,3}
```

### 3.3 推导式（替代手写循环，Python 灵魂）

```text
nums = [1, 2, 3, 4]
squares = [x * x for x in nums if x % 2 == 0]   # list 推导 -> [4,16]
m = {x: x * x for x in nums}                    # dict 推导
flat = [v for row in [[1, 2], [3]] for v in row]  # 嵌套拍平 -> [1,2,3]
# 等价 C++：for + push_back + if，一行搞定
```

### 3.4 函数、多返回值、默认参数、类型注解

```python
from typing import Optional

def parse_frame(raw: bytes, check_crc: bool = True) -> Optional[dict]:
    """解析一帧报文；类型注解不强制运行，但 mypy/IDE 能查错。"""
    if len(raw) < 4:
        return None
    return {"addr": raw[0], "func": raw[1], "payload": raw[2:-2]}

frame, ok = parse_frame(b'\x01\x03\x00\x01'), True   # 注解只是提示
```

> **默认参数陷阱（高频坑）**：默认值只在函数定义时求值一次，别用可变对象做默认值。

```python
# 错误：多次调用共享同一个 list
def bad(x, acc=[]):
    acc.append(x); return acc
# 正确
def good(x, acc=None):
    if acc is None:
        acc = []
    acc.append(x); return acc
```

### 3.5 异常与 with（上下文管理器 = Python 版 RAII）

```python
try:
    f = open("a.txt", encoding="utf-8")
    data = f.read()
except FileNotFoundError as e:
    print("文件不存在", e)
except (IOError, OSError):
    pass
else:                       # 没异常才执行
    pass
finally:
    pass

# with 自动关闭/释放，等价 C++ RAII，强烈推荐
with open("a.txt", encoding="utf-8") as f:
    data = f.read()          # 出作用域自动 f.close()，即使抛异常
```

自定义上下文管理器（实现 `__enter__/__exit__`），或用 `contextlib.contextmanager`。

### 3.6 迭代器与生成器（惰性、省内存）

```python
def count_lines(path):
    """生成器：逐行 yield，不全量读进内存，可处理 GB 级日志。"""
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            yield line.rstrip("\n")

for line in count_lines("server.log"):   # 每次只取一行
    if "ERROR" in line:
        print(line)
```

---

## 4. 常用标准库（C++ 工程里最实用的一批）

| 模块 | 用途 | 典型场景 |
| --- | --- | --- |
| `os` / `pathlib` | 路径、环境变量、目录 | 跨平台拼路径（**用 pathlib 别手拼斜杠**） |
| `sys` | 命令行参数、退出码、stdin | `sys.argv`、`sys.exit(code)` |
| `subprocess` | 调外部程序 | 驱动 g++/cmake/ctest、抓输出 |
| `argparse` | 命令行参数解析 | 写带 `-h/--flag` 的正规工具 |
| `logging` | 分级日志 | 替代 print，可同时输出文件/控制台 |
| `json` | JSON 读写 | 解析接口返回/配置文件 |
| `csv` | CSV 读写 | 测试用例表、报表 |
| `re` | 正则 | 从日志提取字段 |
| `struct` | 二进制打包/解包 | **解析 Modbus/自定义协议帧**（见 5.3） |
| `datetime` | 时间 | 日志时间戳统计 |
| `threading` / `multiprocessing` / `asyncio` | 并发 | IO 任务用线程/协程，CPU 密集用多进程（绕 GIL） |
| `unittest` / `tempfile` / `shutil` | 测试、临时文件、文件操作 | 自动化脚本配套 |

### 4.1 subprocess：驱动编译与测试（替代手写 shell 串命令）

```python
import subprocess

def run(cmd, timeout=60):
    # check=True：非 0 退出码直接抛异常；text=True：返回 str 而非 bytes
    r = subprocess.run(cmd, capture_output=True, text=True,
                       timeout=timeout, check=False)
    return r.returncode, r.stdout, r.stderr

# 批量编译并统计结果（比 bash 循环更好做判断和汇总）
rc, out, err = run(["cmake", "--build", "build", "-j"])
if rc != 0:
    print("编译失败：", err)
```

> **安全要点**：`subprocess` 用**列表传参**（`["g++", src, "-o", out]`），不要 `shell=True` 拼字符串——后者遇到带空格/特殊字符的输入会有命令注入风险（对应 C/C++ 里绝不能 `system(user_input)`）。

### 4.2 argparse：正规命令行工具

```python
import argparse

def main():
    p = argparse.ArgumentParser(description="批量回归测试工具")
    p.add_argument("--build-dir", default="build", help="构建目录")
    p.add_argument("-j", type=int, default=8, help="并行度")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()
    print(args.build_dir, args.j, args.verbose)

if __name__ == "__main__":
    main()
```

### 4.3 logging：别再用 print 调试

```python
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("tool.log", encoding="utf-8"),
              logging.StreamHandler()])
logging.info("开始处理")
```

---

## 5. 四个 C++ 工程师高频实战

### 5.1 结构化日志分析（比 awk/sed 好维护）

```python
# 统计每个接口的错误次数与平均耗时
import re
from collections import defaultdict

pat = re.compile(r"req=(\w+).*?cost=(\d+)ms.*?status=(\d+)")
cnt, cost_sum = defaultdict(int), defaultdict(int)

with open("server.log", encoding="utf-8", errors="ignore") as f:
    for line in f:
        m = pat.search(line)
        if not m:
            continue
        api, cost, status = m.group(1), int(m.group(2)), int(m.group(3))
        cnt[api] += 1
        cost_sum[api] += cost
        if status >= 500:
            logging.error("%s 5xx: %s", api, line.strip())

for api in sorted(cnt):
    print(f"{api:12} 次数={cnt[api]:5} 平均={cost_sum[api]/cnt[api]:.1f}ms")
```

### 5.2 驱动批量回归测试

```python
import subprocess, pathlib

cases = sorted(pathlib.Path("tests").glob("case_*.in"))
passed = failed = 0
for cf in cases:
    inp = cf.read_text(encoding="utf-8")
    expect = cf.with_suffix(".out").read_text(encoding="utf-8").strip()
    r = subprocess.run(["./app"], input=inp, capture_output=True, text=True)
    if r.stdout.strip() == expect:
        passed += 1
    else:
        failed += 1
        print(f"[FAIL] {cf.name}\n  expect={expect!r}\n  got={r.stdout.strip()!r}")
print(f"通过 {passed}，失败 {failed}")
```

### 5.3 struct 解析二进制协议帧（呼应 Modbus / hexdump）

`struct` 用格式串描述字节布局，`>` 表示大端（网络序），`<` 小端，`H`=u16、`I`=u32、`B`=u8、`s`=字节串。字节序辨析见《../08-网络与系统工具/03-二进制查看工具.md》。

```python
import struct

# Modbus TCP 头：MBAP(7B) = 事务id H + 协议id H + 长度 H + 单元id B
def parse_modbus_tcp(frame: bytes):
    txn, proto, length, unit = struct.unpack(">HHHB", frame[:7])
    func = frame[7]
    # 读保持寄存器响应：功能码 + 字节数 + 寄存器值(大端)
    byte_cnt = frame[8]
    regs = struct.unpack(f">{byte_cnt // 2}H", frame[9:9 + byte_cnt])
    return {"txn": txn, "unit": unit, "func": func, "regs": regs}

# 打包一帧：> 表示大端；打包结果可直接发给设备/做单元测试的期望值
raw = struct.pack(">HHHBBHH", 1, 0, 6, 1, 3, 0, 10)
```

### 5.4 数据统计：numpy / pandas 速览

性能压测产出一堆 CSV，用 pandas 几行出统计（比 Excel 可复现）：

```python
import pandas as pd

df = pd.read_csv("bench.csv")              # 列：ts,api,latency
g = df.groupby("api")["latency"]
print(g.agg(["count", "mean", "median",
             lambda x: x.quantile(0.99)])) # QPS、均值、P50、P99
df[df["latency"] > 100].to_csv("slow.csv") # 筛出慢请求
```

- `numpy`：面向连续数值数组（向量化，底层 C，别写 Python for 循环逐元素算）。
- `pandas`：表格数据分析。**只是工程统计就够用，不必深入到数据科学家程度。**

---

## 6. 三类并发模型（知道何时用哪个）

| 模型 | 模块 | 适用 | 关键点 |
| --- | --- | --- | --- |
| 多线程 | `threading` | **IO 密集**（等网络/磁盘/子进程） | GIL 下同一时刻只有一个线程执行 Python 字节码，但等 IO 时会释放 GIL |
| 多进程 | `multiprocessing` | **CPU 密集**（真并行计算） | 绕开 GIL，代价是进程间数据要序列化/共享内存 |
| 异步协程 | `asyncio` | 海量 IO 连接、爬虫/网关对接 | 单线程事件循环，`await` 处切换；库必须是 async 版（aiohttp 而非 requests） |

```python
from concurrent.futures import ThreadPoolExecutor
import subprocess

# 并行跑 8 个编译/测试任务，写法比手写线程简单
with ThreadPoolExecutor(max_workers=8) as pool:
    results = list(pool.map(lambda d: subprocess.run(["make","-C",d]),
                            ["m1", "m2", "m3"]))
```

> GIL（全局解释器锁）是 CPython 实现细节：**它限制的是 Python 字节码级并行，不限制 C 扩展内部**（numpy、你用 pybind11 写的 C++ 函数执行时会释放 GIL）。这也是"重活交给 C++"的原因之一。

---

## 7. Python 与 C++ 互操作（核心加分项）

### 7.1 三种方式对比

| 方式 | 方向 | 适用 | 成本 |
| --- | --- | --- | --- |
| `ctypes`（标准库） | Python 调 C 接口的 `.so/.dll` | 已有 C ABI 库、快速调几个函数 | 低，但只认 C 接口、要手写类型 |
| `cffi` | Python 调 C | 比 ctypes 更稳，可内联 C | 中 |
| **pybind11** | C++ 类/STL/智能指针 → Python | **正经把 C++ 模块导出给 Python**，支持类、重载、vector/map | 中，现代项目首选 |
| CPython 原生扩展 `Python.h` | C++ 写扩展 | 追求极致控制 | 高、模板代码啰嗦 |

### 7.2 ctypes 直接调动态库

```cpp
// math_ext.cpp：导出纯 C 接口
extern "C" int add(int a, int b) { return a + b; }
```

```text
g++ -shared -fPIC math_ext.cpp -o libmath_ext.so
```

```python
import ctypes
lib = ctypes.CDLL("./libmath_ext.so")
lib.add.restype = ctypes.c_int       # 必须声明类型，否则默认按 int 可能出错
lib.add.argtypes = [ctypes.c_int, ctypes.c_int]
print(lib.add(3, 4))                 # 7
```

### 7.3 pybind11 绑定（推荐，header-only）

```cpp
// bind.cpp
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>            // 自动转 std::vector / std::string
#include <vector>
#include <algorithm>
namespace py = pybind11;

std::vector<int> dedup_sorted(std::vector<int> v) {
    std::sort(v.begin(), v.end());
    v.erase(std::unique(v.begin(), v.end()), v.end());
    return v;                        // 自动转成 Python list
}

PYBIND11_MODULE(cext, m) {
    m.doc() = "C++ core for python";
    m.def("dedup_sorted", &dedup_sorted, "sort and unique");
}
```

`CMakeLists.txt` 用 `find_package(pybind11)` + `pybind11_add_module(cext bind.cpp)`，或命令行：

```text
c++ -O3 -Wall -shared -std=c++17 -fPIC $(python3 -m pybind11 --includes) \
    bind.cpp -o cext$(python3-config --extension-suffix)
```

```python
import cext
print(cext.dedup_sorted([3, 1, 3, 2, 1]))   # [1, 2, 3]
```

> **耗时 C++ 函数里释放 GIL**：`py::gil_scoped_release rel;` 包住重计算，让多线程真正并行，算完再自动拿回 GIL。

---

## 8. 代码质量与工程规范

| 工具 | 作用 | 用法 |
| --- | --- | --- |
| `ruff` | lint + 格式化（极快，整合 flake8/isort/black） | `ruff check .`、`ruff format .` |
| `black` | 强制统一格式，省掉风格争论 | `black .` |
| `mypy` | 静态类型检查（配合类型注解） | `mypy my_tool` |
| `pytest` | 测试（比 unittest 简洁） | `pytest -q` |
| `pip-audit` | 查依赖已知漏洞 | `pip-audit` |

```python
# test_core.py：pytest 用 assert 直接判断，参数化覆盖多组输入
import pytest

@pytest.mark.parametrize("a,b,exp", [(1,2,3), (-1,1,0)])
def test_add(a, b, exp):
    assert a + b == exp
```

风格底线：**4 空格缩进、蛇形命名 `snake_case`、模块/函数写 docstring、不用 `from x import *`、异常别裸 `except:`（至少 `except Exception`）**。

---

## 9. AI 胶水：用 Python 把大模型接进工具链

Python 是 AI 生态的"普通话"，C++ 工程师至少会用它做接口串联（模型本身的 C++ 部署见《../17-音视频游戏与AI/03-端侧AI推理部署.md》）：

```python
import requests

def ask(prompt: str) -> str:
    r = requests.post(
        "http://localhost:11434/api/generate",   # 本地 Ollama 等兼容接口
        json={"model": "qwen2.5", "prompt": prompt, "stream": False},
        timeout=30)
    r.raise_for_status()
    return r.json()["response"]

# 例：让模型给每个 C++ 源文件生成提交说明、归类崩溃日志
```

---

## 10. 快速参考卡片

```python
分工：Shell 胶水 / C++ 引擎 / Python 工具与原型
环境：python -m venv .venv → activate → pip install -r requirements.txt
容器：list[] tuple() dict{} set{}；推导式 [x for x in xs if ...]
资源：with open(...) as f  ==  C++ RAII；生成器 yield 处理大文件
外部程序：subprocess.run([...], capture_output=True, text=True)，列表传参，别 shell=True
二进制：struct.pack/unpack，>大端 <小端，H=u16 I=u32 B=u8
并发：IO 用 threading/asyncio，CPU 密集用 multiprocessing（GIL）
互调：快速用 ctypes(C ABI)，正经用 pybind11(类/STL)，重算时释放 GIL
质量：ruff format/check、mypy、pytest、pip-audit
陷阱：可变默认参数只构造一次；负索引/切片；编码统一 utf-8
```

## 11. 常见问题与坑

| 问题 | 原因与解决 |
| --- | --- |
| `ModuleNotFoundError` 但明明装了 | 装到了别的解释器/环境。`python -m pip install xxx` 保证"用哪个 python 装哪个"；确认已激活 venv |
| Windows 打印/写文件中文乱码 | 显式 `encoding="utf-8"`；`open(..., encoding="utf-8")`，别依赖系统默认 GBK |
| 脚本在开发机正常、目标板报语法错 | 目标板 Python 版本低。`requires-python` 卡版本，避免用新高亮语法 |
| 多线程没加速 CPU 计算 | GIL。改 `multiprocessing`，或把热循环下沉到 C++/numpy |
| `subprocess` 中文输出乱码/卡住 | `text=True` + 指定 `encoding`；管道满会死锁时用 `communicate()`；长任务设 `timeout` |
| pip 装包慢/超时 | 配清华源；公司网络注意代理 `HTTP_PROXY` |
| 读大日志内存爆掉 | 别 `f.readlines()` 全读，逐行迭代或生成器 |
| `requests` 在 asyncio 里阻塞整个循环 | 用对应的异步库 `aiohttp`，或丢进 `run_in_executor` |
| 浮点/时间比较对不上 | 浮点别直接 `==`；时间统一用 UTC 时间戳，展示再转时区 |
| 依赖越装越乱、版本冲突 | 每个项目独立 venv，`requirements.txt` 锁版本，别全局乱装 |

---

## 12. 延伸阅读与官方资料

> 优先读官方文档（比二手博客准确、且持续更新）；离线时这些链接不影响正文，ASCII 图与代码自包含。

**官方文档（权威、免费）**

- Python 3 官方文档（中文）：[docs.python.org/zh-cn/3](https://docs.python.org/zh-cn/3/)
- 虚拟环境 venv：[docs.python.org/3/library/venv.html](https://docs.python.org/3/library/venv.html)
- subprocess（调用外部程序）：[docs.python.org/3/library/subprocess.html](https://docs.python.org/3/library/subprocess.html)
- struct（二进制/协议帧打包解包）：[docs.python.org/3/library/struct.html](https://docs.python.org/3/library/struct.html)
- ctypes（调 C 动态库）：[docs.python.org/3/library/ctypes.html](https://docs.python.org/3/library/ctypes.html)
- concurrent.futures（线程/进程池）：[docs.python.org/3/library/concurrent.futures.html](https://docs.python.org/3/library/concurrent.futures.html)

**第三方工具与库**

- pybind11（C++ 绑定官方手册）：[pybind11.readthedocs.io](https://pybind11.readthedocs.io/)
- NumPy：[numpy.org/doc](https://numpy.org/doc/stable/)；Pandas：[pandas.pydata.org/docs](https://pandas.pydata.org/docs/)
- uv（新一代包管理器）：[docs.astral.sh/uv](https://docs.astral.sh/uv/)
- pytest：[docs.pytest.org](https://docs.pytest.org/)；ruff（lint+format）：[docs.astral.sh/ruff](https://docs.astral.sh/ruff/)；mypy（类型检查）：[mypy.readthedocs.io](https://mypy.readthedocs.io/)
- Requests（HTTP 客户端）：[requests.readthedocs.io](https://requests.readthedocs.io/)

**与本知识库联动**：C++ 编译构建见《01-构建工具GCC与CMake.md》，二进制字节序见《../08-网络与系统工具/03-二进制查看工具.md》，AI 接口/部署见《../17-音视频游戏与AI/03-端侧AI推理部署.md》。

---

上一篇：《04-Shell脚本编程.md》
下一篇：《06-Python进阶与常用库.md》
