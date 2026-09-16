# pybind11 封装 C++ 模块

> 本节目标：用 pybind11 把 C++ 代码封装为 Python 可调用模块，覆盖 CMake 集成、函数/类/枚举/STL 容器/智能指针/异常转换/持有关系的绑定，编译安装，基准对比，以及「计算热点下沉 C++ vs 业务外壳留 Python」的决策原则和常见坑。

## 本章速览

- [1. 工程场景：什么时候该用 pybind11](#1-工程场景什么时候该用-pybind11)
- [2. pybind11 简介与安装](#2-pybind11-简介与安装)
- [3. 最小工程：CMake 集成](#3-最小工程cmake-集成)
- [4. 绑定函数与枚举](#4-绑定函数与枚举)
- [5. 绑定类：构造、方法、属性、静态方法](#5-绑定类构造方法属性静态方法)
- [6. STL 容器与类型转换](#6-stl-容器与类型转换)
- [7. 智能指针与持有关系](#7-智能指针与持有关系)
- [8. 异常转换](#8-异常转换)
- [9. 编译安装与分发](#9-编译安装与分发)
  - [9.1 本地编译](#91-本地编译)
  - [9.2 跨平台分发](#92-跨平台分发)
  - [9.3 编译选项](#93-编译选项)
- [10. 基准对比：Python vs C++ vs pybind11](#10-基准对比python-vs-c-vs-pybind11)
- [11. 决策原则：什么下沉 C++，什么留 Python](#11-决策原则什么下沉-c什么留-python)
- [12. 快速参考卡片](#12-快速参考卡片)
- [13. 常见坑](#13-常见坑)
- [14. 本节小结](#14-本节小结)

---

## 1. 工程场景：什么时候该用 pybind11

ctypes 只能调用 C ABI 的函数，C++ 的类、重载、模板、异常都无法直接映射。当需要把一个 C++ 类库（而不是纯 C 库）暴露给 Python 时，pybind11 是首选。

典型场景：

- 已有一个 C++ 写的高性能计算库（信号处理、协议解析、数学计算），需要在 Python 的测试脚本或自动化工具中调用。
- C++ 服务端的核心算法模块，需要用 Python 写批量测试用例、参数扫描、结果可视化。
- 把 C++ 实现的编解码器、加解密器封装成 Python 模块，供上层 Python 工具链使用。
- 渐进式优化：Python 脚本的某个函数成为性能瓶颈，把它用 C++ 重写后通过 pybind11 调用，其余逻辑保持 Python。

pybind11（以PyPI最新稳定版为准）是一个头文件库，用 C++17 编写，API 设计借鉴了 Boost.Python 但更轻量。它能自动处理 C++ 类、继承、重载、STL 容器、智能指针、异常到 Python 的映射，是 C++/Python 混合编程的事实标准。

## 2. pybind11 简介与安装

pybind11 是纯头文件库，不需要编译安装本身，只需要在 C++ 项目中包含头文件。安装方式：

```bash
# 方式 1：pip 安装（推荐，自动获取 CMake 配置）
pip install pybind11

# 方式 2：CMake FetchContent 拉取（见下节）
# 方式 3：git submodule
git submodule add https://github.com/pybind/pybind11.git extern/pybind11
```

验证安装：

```bash
python -m pybind11 --includes
# 输出: -I/path/to/pybind11/include -I/path/to/python/include
```

pybind11 的核心是一个宏 `PYBIND11_MODULE(module_name, m)`，在其中注册所有要暴露给 Python 的符号。

## 3. 最小工程：CMake 集成

一个标准的 pybind11 工程结构：

```text
mybind/
├── CMakeLists.txt
├── pyproject.toml
├── src/
│   ├── calculator.h      # C++ 头文件
│   ├── calculator.cpp    # C++ 实现
│   └── bindings.cpp      # pybind11 绑定代码
└── tests/
    └── test_calculator.py
```

`CMakeLists.txt`：

```cmake
cmake_minimum_required(VERSION 3.15)
project(mybind LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# 方式 1：通过 pip 安装的 pybind11
find_package(pybind11 CONFIG REQUIRED)

# 方式 2：FetchContent（如果没有 pip 安装）
# include(FetchContent)
# FetchContent_Declare(pybind11
#     GIT_REPOSITORY https://github.com/pybind/pybind11.git
#     GIT_TAG v2.11.1)
# FetchContent_MakeAvailable(pybind11)

# C++ 核心库（静态库，被绑定模块链接）
add_library(calculator STATIC src/calculator.cpp)
target_include_directories(calculator PUBLIC src)

# pybind11 模块
pybind11_add_module(mybind src/bindings.cpp)
target_link_libraries(mybind PRIVATE calculator)

# 编译优化
target_compile_options(mybind PRIVATE -O3)
```

`pyproject.toml`（用于 `pip install .` 构建）：

```toml
[build-system]
requires = ["setuptools>=42", "wheel", "pybind11>=2.11"]
build-backend = "setuptools.build_meta"

[project]
name = "mybind"
version = "0.1.0"
description = "C++ calculator exposed to Python via pybind11"
requires-python = ">=3.8"

[tool.setuptools.packages.find]
where = ["."]
```

构建和安装：

```bash
# 开发模式安装（编译后直接可用，修改 C++ 后需重新编译）
pip install -e . --no-build-isolation

# 或用 CMake 手动构建
mkdir build && cd build
cmake .. -DPYTHON_EXECUTABLE=$(which python)
make -j$(nproc)
# 生成 mybind.cpython-311-x86_64-linux-gnu.so
```

## 4. 绑定函数与枚举

先看 C++ 头文件：

```cpp
// src/calculator.h
#pragma once
#include <cstdint>
#include <string>

namespace calc {

enum class Operation {
    Add,
    Subtract,
    Multiply,
    Divide
};

double compute(double a, double b, Operation op);

// 带默认参数的函数
double power(double base, int exponent = 2);

// 重载函数
int add(int a, int b);
double add(double a, double b);

} // namespace calc
```

绑定代码：

```cpp
// src/bindings.cpp
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>  // STL 容器转换支持
#include "calculator.h"

namespace py = pybind11;

PYBIND11_MODULE(mybind, m) {
    m.doc() = "C++ calculator module exposed via pybind11";

    // 绑定枚举
    py::enum_<calc::Operation>(m, "Operation")
        .value("Add", calc::Operation::Add)
        .value("Subtract", calc::Operation::Subtract)
        .value("Multiply", calc::Operation::Multiply)
        .value("Divide", calc::Operation::Divide)
        .export_values();  // 让枚举值也作为模块属性可用

    // 绑定普通函数
    m.def("compute", &calc::compute, "Compute a op b",
          py::arg("a"), py::arg("b"), py::arg("op"));

    // 绑定带默认参数的函数
    m.def("power", &calc::power, "Power with default exponent",
          py::arg("base"), py::arg("exponent") = 2);

    // 绑定重载函数：必须用 static_cast 明确指定哪个重载
    m.def("add", static_cast<int(*)(int, int)>(&calc::add),
          "Integer add", py::arg("a"), py::arg("b"));
    m.def("add", static_cast<double(*)(double, double)>(&calc::add),
          "Double add", py::arg("a"), py::arg("b"));
}
```

Python 端使用：

```python
import mybind

print(mybind.compute(3.0, 4.0, mybind.Operation.Add))  # 7.0
print(mybind.power(2.0))          # 4.0（默认 exponent=2）
print(mybind.power(2.0, 10))      # 1024.0
print(mybind.add(3, 4))            # 7（int 重载）
print(mybind.add(3.5, 4.5))        # 8.0（double 重载）
```

`py::arg("name")` 给参数命名，Python 端就可以用关键字参数调用。默认参数用 `py::arg("name") = value`。

## 5. 绑定类：构造、方法、属性、静态方法

C++ 类：

```cpp
// src/device.h
#pragma once
#include <string>
#include <vector>
#include <cstdint>

namespace dev {

class Device {
public:
    Device(uint32_t id, const std::string& name);
    ~Device();

    // 实例方法
    bool connect();
    void disconnect();
    bool is_connected() const;

    // 读写属性
    uint32_t id() const { return id_; }
    const std::string& name() const { return name_; }
    void set_name(const std::string& name) { name_ = name; }

    // 静态方法
    static int device_count();

    // 返回 STL 容器
    std::vector<uint8_t> read_data(size_t max_bytes);

private:
    uint32_t id_;
    std::string name_;
    bool connected_ = false;
    static int device_count_;
};

} // namespace dev
```

绑定代码：

```cpp
// src/bindings.cpp（续）
#include "device.h"

PYBIND11_MODULE(mybind, m) {
    // ... 前面的函数和枚举绑定 ...

    py::class_<dev::Device>(m, "Device")
        // 构造函数
        .def(py::init<uint32_t, const std::string&>(),
             py::arg("id"), py::arg("name"))

        // 实例方法
        .def("connect", &dev::Device::connect)
        .def("disconnect", &dev::Device::disconnect)
        .def("is_connected", &dev::Device::is_connected)

        // 只读属性（通过 getter）
        .def_property_readonly("id", &dev::Device::id)

        // 读写属性（通过 getter/setter）
        .def_property("name", &dev::Device::name, &dev::Device::set_name)

        // 静态方法
        .def_static("device_count", &dev::Device::device_count)

        // 返回 STL 容器的方法（需要 #include <pybind11/stl.h>）
        .def("read_data", &dev::Device::read_data, py::arg("max_bytes"))

        // __repr__ 用于 print
        .def("__repr__", [](const dev::Device& d) {
            return std::string("<Device id=") + std::to_string(d.id()) + " name=" + d.name() + ">";
        });
}
```

Python 端：

```python
import mybind

d = mybind.Device(100, "sensor-001")
print(d.id)            # 100（只读属性）
print(d.name)          # sensor-001
d.name = "sensor-002"  # 读写属性
print(d)               # <Device id=100 name=sensor-002>

d.connect()
print(d.is_connected())  # True

data = d.read_data(64)   # 返回 Python list[int]
print(len(data), data[:5])

print(mybind.Device.device_count())  # 静态方法
```

`py::class_<T>` 是类绑定的核心。`def_property_readonly` 绑定只读属性，`def_property` 绑定读写属性，`def_static` 绑定静态方法。lambda 表达式可以直接用于绑定特殊方法（如 `__repr__`）。

## 6. STL 容器与类型转换

pybind11 通过 `pybind11/stl.h` 自动转换常见 STL 容器：

| C++ 类型 | Python 类型 |
|---|---|
| `std::vector<T>` | `list` |
| `std::array<T, N>` | `list` |
| `std::map<K, V>` | `dict` |
| `std::unordered_map<K, V>` | `dict` |
| `std::set<T>` | `set` |
| `std::unordered_set<T>` | `set` |
| `std::optional<T>` | `T` 或 `None` |
| `std::variant<T...>` | 对应类型 |
| `std::string` | `str` |
| `std::pair<T1, T2>` | `tuple` |
| `std::tuple<T...>` | `tuple` |

```cpp
#include <pybind11/stl.h>
#include <vector>
#include <map>
#include <optional>

// 函数接受和返回 STL 容器
std::vector<int> filter_positive(const std::vector<int>& input);
std::map<std::string, double> compute_stats(const std::vector<double>& data);
std::optional<std::string> find_name(int id);

m.def("filter_positive", &filter_positive);
m.def("compute_stats", &compute_stats);
m.def("find_name", &find_name);
```

```python
import mybind

result = mybind.filter_positive([-1, 2, -3, 4, -5])
print(result)  # [2, 4]

stats = mybind.compute_stats([1.0, 2.0, 3.0, 4.0])
print(stats)  # {'mean': 2.5, 'max': 4.0, ...}

name = mybind.find_name(100)
print(name)  # 可能是 "device-100" 或 None
```

**性能注意**：STL 容器转换是**拷贝**。`std::vector<int>` 转 Python `list` 时每个元素都要转换并拷贝。大数组（百万级元素）频繁转换会成为瓶颈。解决方案：

1. 用 `pybind11::array_t<T>`（NumPy 数组）零拷贝传递大数组（需要 `#include <pybind11/numpy.h>`）。
2. 用 `py::buffer` 协议直接暴露底层内存。
3. 减少跨边界调用次数，把批量操作放在 C++ 端一次完成。

## 7. 智能指针与持有关系

pybind11 对 `std::unique_ptr` 和 `std::shared_ptr` 有原生支持。持有关系（ownership）是最容易出错的地方。

```cpp
#include <memory>

class Resource {
public:
    Resource(int value) : value_(value) {}
    int value() const { return value_; }
private:
    int value_;
};

// 工厂函数返回 unique_ptr
std::unique_ptr<Resource> create_resource(int value) {
    return std::make_unique<Resource>(value);
}

// 函数接受 shared_ptr
void process_resource(std::shared_ptr<Resource> res) {
    // 使用 res
}

// 类持有 unique_ptr 成员
class Manager {
public:
    Manager() : resource_(std::make_unique<Resource>(0)) {}
    Resource* get_resource() { return resource_.get(); }  // 返回裸指针
private:
    std::unique_ptr<Resource> resource_;
};
```

绑定：

```cpp
py::class_<Resource>(m, "Resource")
    .def(py::init<int>())
    .def_property_readonly("value", &Resource::value);

// 返回 unique_ptr 的工厂函数：pybind11 自动接管所有权
m.def("create_resource", &create_resource);

// 接受 shared_ptr 的函数
m.def("process_resource", &process_resource);

// Manager 类
py::class_<Manager>(m, "Manager")
    .def(py::init<>())
    // 返回裸指针：默认 pybind11 不拥有，Python 对象不负责释放
    // 但如果 Manager 被销毁，Resource 也被销毁，Python 端的引用会悬空！
    .def("get_resource", &Manager::get_resource,
         py::return_value_policy::reference);  // 明确：仅引用，不拥有
```

持有关系策略：

| 场景 | 策略 | 说明 |
|---|---|---|
| 工厂返回 `unique_ptr` | 默认（pybind11 接管） | Python 对象持有，GC 时自动 delete |
| 工厂返回 `shared_ptr` | 默认（引用计数共享） | Python 和 C++ 共享所有权 |
| 返回单例/全局对象的裸指针 | `py::return_value_policy::reference` | Python 不拥有，不负责释放 |
| 返回内部成员的引用 | `py::return_value_policy::reference_internal` | 生命周期绑定到父对象，父对象存活时子引用有效 |
| C++ 端管理生命周期，Python 只借用 | `py::keep_alive<Nurse, Patient>()` | 确保 Nurse 存活时 Patient 不被回收 |

`reference_internal` 是最常用的安全策略：

```cpp
class Container {
public:
    Item& get_item(int index) { return items_[index]; }
private:
    std::vector<Item> items_;
};

py::class_<Container>(m, "Container")
    .def("get_item", &Container::get_item,
         py::return_value_policy::reference_internal);
// 返回的 Item 的生命周期绑定到 Container，Container 被 GC 前 Item 不会悬空
```

## 8. 异常转换

pybind11 自动把 C++ 标准异常转换为 Python 异常：

| C++ 异常 | Python 异常 |
|---|---|
| `std::exception` | `RuntimeError` |
| `std::bad_alloc` | `MemoryError` |
| `std::domain_error` | `ValueError` |
| `std::invalid_argument` | `ValueError` |
| `std::length_error` | `ValueError` |
| `std::out_of_range` | `IndexError` |
| `std::range_error` | `ValueError` |
| `std::overflow_error` | `OverflowError` |

自定义异常注册：

```cpp
class ProtocolError : public std::runtime_error {
public:
    ProtocolError(const std::string& msg) : std::runtime_error(msg) {}
    int error_code() const { return code_; }
private:
    int code_ = -1;
};

// 在模块中注册自定义异常
PYBIND11_MODULE(mybind, m) {
    // 定义 Python 异常类，继承 RuntimeError
    static py::exception<ProtocolError> py_exc(m, "ProtocolError", PyExc_RuntimeError);

    // 注册翻译函数：C++ 异常 -> Python 异常时附加信息
    py::register_exception_translator([](std::exception_ptr p) {
        try {
            if (p) std::rethrow_exception(p);
        } catch (const ProtocolError& e) {
            PyErr_SetString(PyExc_RuntimeError, e.what());
            // 或用自定义异常：
            // py_exc(e.what());
        }
    });

    // 抛出异常的函数
    m.def("parse_packet", [](const std::vector<uint8_t>& data) {
        if (data.size() < 4) {
            throw ProtocolError("packet too short");
        }
        // ... 解析
    });
}
```

Python 端捕获：

```python
import mybind

try:
    mybind.parse_packet([0x01])
except mybind.ProtocolError as e:
    print(f"协议错误: {e}")
except RuntimeError as e:
    print(f"运行时错误: {e}")
```

## 9. 编译安装与分发

### 9.1 本地编译

```bash
# 开发模式（推荐用于开发调试）
pip install -e . --no-build-isolation -v

# 正式安装
pip install .

# 手动 CMake 构建（不通过 pip）
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
cmake --build . -j
# 产物：mybind.cpython-311-x86_64-linux-gnu.so
# 把 .so 文件放到 Python 能 import 的目录即可
```

### 9.2 跨平台分发

pybind11 模块是编译产物，必须为每个平台（Linux/macOS/Windows）和每个 Python 版本（3.8-3.12）分别编译。分发方案：

- **cibuildwheel**：在 CI 中自动为多平台多 Python 版本构建 wheel，是标准方案。
- **manylinux**：Linux wheel 必须在 manylinux 容器中构建，确保 glibc 兼容性。
- **delocate**（macOS）/ **delvewheel**（Windows）：修复动态库依赖，把依赖的 .so/.dll 打包进 wheel。

`pyproject.toml` 中配置 cibuildwheel：

```toml
[tool.cibuildwheel]
build = "cp38-* cp39-* cp310-* cp311-* cp312-*"
skip = "*-musllinux* *-win32 *-manylinux_i686"

[tool.cibuildwheel.linux]
manylinux-x86_64-image = "manylinux2014"

[tool.cibuildwheel.macos]
archs = "x86_64 arm64"
```

### 9.3 编译选项

```cmake
# Release 模式优化
set(CMAKE_BUILD_TYPE Release)
target_compile_options(mybind PRIVATE -O3 -march=native)

# 隐藏符号（减小 .so 体积，避免符号冲突）
set_target_properties(mybind PROPERTIES CXX_VISIBILITY_PRESET hidden)

# Linux 上链接时不需要的库去掉
target_link_options(mybind PRIVATE -Wl,--as-needed)
```

## 10. 基准对比：Python vs C++ vs pybind11

以一个计算密集型函数为例：计算大量数据的 CRC32。

```cpp
// src/benchmark.h
#pragma once
#include <cstdint>
#include <vector>

namespace bench {

// C++ 实现：查表法 CRC32
uint32_t crc32_cpp(const std::vector<uint8_t>& data);

// 纯 Python 实现会在测试脚本中写

} // namespace bench
```

Python 基准测试：

```python
"""benchmark.py — Python vs C++ (pybind11) 性能对比"""
import time
import mybind
import random

# 生成 10MB 随机数据
data = bytes(random.randint(0, 255) for _ in range(10 * 1024 * 1024))

# Python 纯实现（查表法）
CRC_TABLE = []
for n in range(256):
    c = n
    for _ in range(8):
        c = (c >> 1) ^ 0xEDB88320 if c & 1 else c >> 1
    CRC_TABLE.append(c & 0xFFFFFFFF)

def crc32_python(data: bytes) -> int:
    crc = 0xFFFFFFFF
    for b in data:
        crc = (crc >> 8) ^ CRC_TABLE[(crc ^ b) & 0xFF]
    return crc ^ 0xFFFFFFFF

# 基准
N = 5

t0 = time.perf_counter()
for _ in range(N):
    r1 = crc32_python(data)
t_py = (time.perf_counter() - t0) / N

t0 = time.perf_counter()
for _ in range(N):
    r2 = mybind.crc32_cpp(list(data))  # 注意：bytes->vector 有拷贝开销
t_cpp = (time.perf_counter() - t0) / N

print(f"Python:  {t_py:.3f}s  result=0x{r1:08x}")
print(f"C++:     {t_cpp:.3f}s  result=0x{r2:08x}")
print(f"加速比:  {t_py / t_cpp:.1f}x")
```

典型结果（10MB 数据，x86-64，-O3）：

```text
Python:  3.215s  result=0x...
C++:     0.012s  result=0x...
加速比:  267.9x
```

但注意 `list(data)` 把 10MB bytes 转成 `std::vector<uint8_t>` 有拷贝开销。如果用 `py::buffer` 或 `py::bytes` 直接访问底层内存，C++ 端还能更快：

```cpp
// 用 py::bytes 直接访问，零拷贝
uint32_t crc32_bytes(py::bytes data) {
    py::buffer_info info = py::buffer(data).request();
    const uint8_t* ptr = static_cast<const uint8_t*>(info.ptr);
    size_t len = info.size;
    // ... 直接用 ptr 和 len 计算
}
```

基准结论：

- 计算密集型函数（CRC、编解码、信号处理）C++ 比纯 Python 快 100-1000 倍。
- 跨边界的类型转换（`bytes` -> `vector`）有拷贝开销，大数据量时用 `py::buffer` 零拷贝。
- 如果函数本身很快（微秒级），pybind11 的调用开销（约 50-100ns）可能占主导，此时批量调用比逐个调用更高效。

## 11. 决策原则：什么下沉 C++，什么留 Python

不是所有代码都该用 C++ 重写。决策框架：

| 维度 | 留 Python | 下沉 C++ |
|---|---|---|
| 执行频率 | 低频（初始化、配置解析） | 高频（热循环、每包处理） |
| 数据量 | 小（KB 级） | 大（MB/GB 级） |
| 计算类型 | IO 密集、字符串处理 | CPU 密集、数学计算 |
| 开发成本 | 快速迭代、原型验证 | 稳定后优化 |
| 维护成本 | 业务逻辑、规则引擎 | 核心算法、协议编解码 |
| 已有资产 | 无 | 已有 C++ 库可复用 |

**分层架构推荐**：

```text
┌─────────────────────────────────────┐
│  Python 层（业务外壳）               │
│  - 配置解析、参数管理                 │
│  - 测试用例编排、结果输出             │
│  - 文件 IO、日志、报告生成            │
│  - 简单的控制流和调度                 │
├─────────────────────────────────────┤
│  pybind11 绑定层（薄胶水）            │
│  - 类型转换、异常翻译                 │
│  - 持有关系管理                       │
├─────────────────────────────────────┤
│  C++ 层（性能内核）                   │
│  - 协议编解码、报文解析               │
│  - 计算密集型算法                     │
│  - 大数据量处理                       │
│  - 已有 C++ 库的复用                  │
└─────────────────────────────────────┘
```

**决策流程**：

1. 先全部用 Python 写，跑通功能。
2. 用 `cProfile` 或 `time.perf_counter()` 找瓶颈。
3. 如果瓶颈函数是计算密集型且被高频调用，用 C++ 重写，pybind11 封装。
4. 保持绑定层尽量薄，不要在绑定层写业务逻辑。
5. C++ 端的接口设计成接受原始指针/缓冲区（`py::buffer`），避免 STL 容器的拷贝开销。

## 12. 快速参考卡片

| 需求 | 做法 |
| --- | --- |
| 模块骨架 | `PYBIND11_MODULE(_core, m) { m.def("add", &add); }` |
| 暴露类 | `py::class_<Point>(m, "Point").def(py::init<int, int>()).def_readwrite("x", &Point::x)` |
| STL 互转 | `<pybind11/stl.h>`：`std::vector` ↔ list、`std::map` ↔ dict（需包含头文件） |
| 智能指针 | `std::shared_ptr<T>` 自动映射；`py::return_value_policy::take_ownership` 转移所有权 |
| 释放 GIL | `py::call_guard<py::gil_scoped_release>()` 包重计算，让其它 Python 线程跑 |
| 异常映射 | `py::register_exception<MyErr>(m, "MyError")`；C++ 异常不能穿越未映射边界 |
| 构建集成 | `setup.py` + `Pybind11Extension`，或 CMake `find_package(pybind11)` + `pybind11_add_module` |
| 类型转换成本 | 大容器按值传会有拷贝；`py::array_t<T>`（buffer 协议）实现零拷贝对接 numpy |
| 调试 | `python -X faulthandler`；`.so` 用 `ldd` 查依赖；`nm -D` 看导出符号 |
| 常见坑点 | 返回局部对象引用导致悬垂；忘了 `<pybind11/stl.h>` 报类型不识别的长模板错误 |

---

## 13. 常见坑

**坑 1：GIL 导致 C++ 多线程无效。** Python 的全局解释器锁（GIL）在调用 C++ 函数时仍然持有。如果 C++ 函数内部用多线程并行计算，Python 端的其他线程无法运行。解决方案：在 C++ 函数入口释放 GIL：

```cpp
m.def("heavy_compute", [](const std::vector<double>& data) {
    py::gil_scoped_release release;  // 释放 GIL
    return heavy_compute_impl(data);  // C++ 多线程计算
    // 函数返回时自动重新获取 GIL
});
```

注意：释放 GIL 期间不能调用任何 Python API（包括 `py::print`、异常抛出）。

**坑 2：对象生命周期悬空。** C++ 端返回内部成员的引用/指针，但持有该成员的父对象被 Python GC 回收了，导致悬空指针。用 `py::return_value_policy::reference_internal` 把返回值的生命周期绑定到父对象。

**坑 3：重载函数歧义。** C++ 的重载函数在绑定时必须用 `static_cast` 明确指定，否则编译错误。Python 端调用时，pybind11 按参数类型匹配重载，但 `int` 和 `float` 可能混淆（Python 的 `1` 是 int，`1.0` 是 float）。

**坑 4：STL 容器拷贝开销。** `std::vector` 转 Python `list` 是深拷贝，百万级元素频繁转换会很慢。用 `py::array_t<T>`（NumPy）或 `py::buffer` 零拷贝传递。

**坑 5：异常在 GIL 释放后抛出。** 如果在 `py::gil_scoped_release` 期间抛出 C++ 异常，pybind11 无法正确转换为 Python 异常（因为需要 GIL 来设置 Python 异常状态）。必须在重新获取 GIL 之后再抛出，或在 C++ 端捕获后返回错误码。

**坑 6：`py::init` 的参数顺序。** `py::init<A, B>()` 按 C++ 构造函数的参数顺序绑定，`py::arg` 的顺序必须一致。搞反了会导致参数错位但不报错（因为类型可能兼容）。

**坑 7：Windows 上的运行时库不匹配。** C++ 库用 `/MD`（动态 CRT）编译，pybind11 模块用 `/MT`（静态 CRT）编译，链接时会报符号冲突。必须统一用 `/MD`（Python 官方解释器用 `/MD`）。

**坑 8：忘记 `#include <pybind11/stl.h>`。** 不包含这个头文件时，`std::vector`/`std::map` 等无法自动转换，编译报错或运行时类型错误。需要 `std::optional` 还要 `#include <pybind11/stl.h>`（已包含），`std::variant` 需要 `#include <pybind11/stl.h>`。

## 14. 本节小结

- pybind11 是 C++/Python 混合编程的事实标准，纯头文件库，用 `PYBIND11_MODULE` 宏注册符号。
- 标准工程用 CMake + `pybind11_add_module`，C++ 核心代码编为静态库，绑定模块链接它。
- 函数绑定用 `m.def()`，`py::arg()` 命名参数，默认参数用 `= value`；重载函数必须 `static_cast` 明确指定。
- 类绑定用 `py::class_<T>`，`def_property_readonly`/`def_property` 绑定属性，`def_static` 绑定静态方法，lambda 可绑定特殊方法。
- STL 容器通过 `pybind11/stl.h` 自动转换，但大数组有拷贝开销，用 `py::buffer`/`py::array_t` 零拷贝。
- 智能指针对象：`unique_ptr` 返回由 pybind11 接管，`shared_ptr` 共享引用计数；裸指针返回必须明确 `return_value_policy`，`reference_internal` 是最安全的策略。
- 异常自动转换标准异常，自定义异常用 `py::exception` 注册 + `register_exception_translator` 翻译。
- 性能基准：计算密集型 C++ 比 Python 快 100-1000 倍，但要注意跨边界拷贝开销和 GIL。
- 决策原则：Python 做业务外壳（配置、调度、IO、报告），C++ 做性能内核（算法、编解码、大数据处理），绑定层尽量薄。
- 最常见的坑：GIL 未释放导致多线程无效、生命周期悬空、重载歧义、STL 拷贝、异常在 GIL 释放后抛出、Windows CRT 不匹配。

---

上一篇：《01-ctypes与cffi调用原生库.md》　｜　下一篇：《03-PyO3打通Rust与三语言分工.md》　｜　模块索引：《../README.md》
