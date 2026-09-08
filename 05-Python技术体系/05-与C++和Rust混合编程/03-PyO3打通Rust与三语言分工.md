# PyO3 打通 Rust 与三语言分工

> 本节目标：用 maturin + PyO3 给 Rust 库做 Python 绑定，完成从工程搭建到函数/类/错误处理的完整示例，对比 pybind11，并给出「C++/Rust 性能内核 + Python 工具/脚本外壳」的三语言分层决策表。

## 本章速览

- [1. 工程场景：Rust 库为什么需要 Python 绑定](#1-工程场景rust-库为什么需要-python-绑定)
- [2. PyO3 与 maturin 简介](#2-pyo3-与-maturin-简介)
- [3. 最小工程：maturin 搭建](#3-最小工程maturin-搭建)
- [4. 绑定函数与基本类型](#4-绑定函数与基本类型)
- [5. 绑定结构体与方法](#5-绑定结构体与方法)
- [6. 错误处理：Result 与异常](#6-错误处理result-与异常)
- [7. Python 对象交互与 GIL](#7-python-对象交互与-gil)
  - [7.1 释放 GIL 执行计算](#71-释放-gil-执行计算)
  - [7.2 直接操作 Python 对象](#72-直接操作-python-对象)
- [8. 对比 pybind11](#8-对比-pybind11)
- [9. 三语言分工决策表](#9-三语言分工决策表)
- [10. 完整示例：Rust 协议解析库的 Python 绑定](#10-完整示例rust-协议解析库的-python-绑定)
- [11. 常见坑](#11-常见坑)
- [12. 本节小结](#12-本节小结)

---

## 1. 工程场景：Rust 库为什么需要 Python 绑定

Rust 在系统编程领域越来越常见：网络代理、嵌入式工具链、加密库、CLI 工具。当一个 Rust 库已经写好（高性能、内存安全），需要在 Python 的测试脚本、自动化工具、数据分析流程中调用时，PyO3 是标准方案。

典型场景：

- 用 Rust 写了一个高性能协议解析器，需要用 Python 写批量测试用例和模糊测试。
- Rust 实现的加解密/编解码库，需要在 Python 的自动化工具中调用。
- 已有一个 Rust CLI 工具，想把核心逻辑暴露为 Python 模块，供 Jupyter 或脚本使用。
- 团队从 C++ 迁移部分模块到 Rust，需要统一的 Python 绑定层来调用两种语言的库。

PyO3（以PyPI最新稳定版为准）是 Rust 的 Python 绑定库，用过程宏（`#[pyfunction]`、`#[pymethods]`、`#[pyclass]`）标注要暴露的符号，编译器自动生成绑定代码。maturin（以PyPI最新稳定版为准）是构建和打包工具，替代了手写 setup.py 的繁琐流程。

Rust 的 FFI 互操作基础（`extern "C"`、`unsafe`、裸指针）参见《../../04-Rust技术体系/02-Rust进阶机制/02-Unsafe裸指针与FFI互操作.md》。

## 2. PyO3 与 maturin 简介

**PyO3** 的核心特性：

- 过程宏驱动：`#[pyfunction]` 标注函数，`#[pyclass]` 标注结构体，`#[pymethods]` 标注 impl 块。
- 自动类型转换：Rust 基本类型（i32、f64、String、Vec、HashMap）自动转 Python 对应类型。
- GIL 管理：`Python<'py>` 令牌表示持有 GIL，`allow_threads` 释放 GIL 执行 Rust 计算。
- 错误转换：Rust 的 `Result<T, E>` 自动转 Python 异常，自定义错误类型实现 `std::error::Error` 即可。

**maturin** 的核心特性：

- 一条命令 `maturin develop` 编译并安装到当前虚拟环境（类似 `pip install -e .`）。
- 自动生成 `pyproject.toml`，支持 cibuildwheel 多平台构建。
- 支持纯 Rust 项目、Rust + Python 混合项目、CMake 项目。

安装：

```bash
pip install maturin
# Rust 工具链需要提前安装：https://rustup.rs
rustc --version  # 确认 Rust 已安装
```

## 3. 最小工程：maturin 搭建

```bash
# 创建项目
mkdir rust_py_demo && cd rust_py_demo
maturin init --bindings pyo3
```

生成的工程结构：

```text
rust_py_demo/
├── Cargo.toml
├── pyproject.toml
├── src/
│   └── lib.rs
└── python/          # 可选：纯 Python 代码
    └── rust_py_demo/
        └── __init__.py
```

`Cargo.toml`：

```toml
[package]
name = "rust_py_demo"
version = "0.1.0"
edition = "2021"

[lib]
name = "rust_py_demo"
crate-type = ["cdylib"]  # 必须是 cdylib，Python 才能加载

[dependencies]
pyo3 = { version = "0.21", features = ["extension-module"] }
```

`pyproject.toml`：

```toml
[build-system]
requires = ["maturin>=1.5,<2.0"]
build-backend = "maturin"

[project]
name = "rust_py_demo"
version = "0.1.0"
requires-python = ">=3.8"

[tool.maturin]
features = ["pyo3/extension-module"]
```

`src/lib.rs`（最小示例）：

```rust
use pyo3::prelude::*;

/// 加法函数，暴露给 Python
#[pyfunction]
fn add(a: i32, b: i32) -> i32 {
    a + b
}

/// 模块定义
#[pymodule]
fn rust_py_demo(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(add, m)?)?;
    Ok(())
}
```

编译安装：

```bash
# 开发模式：编译并安装到当前虚拟环境
maturin develop --release

# 验证
python -c "import rust_py_demo; print(rust_py_demo.add(3, 4))"  # 7
```

`maturin develop --release` 是开发时最常用的命令，等价于 C++ 项目的 `pip install -e .`。修改 Rust 代码后重新执行即可。

## 4. 绑定函数与基本类型

```rust
use pyo3::prelude::*;
use std::collections::HashMap;

/// 基本类型函数
#[pyfunction]
fn compute(a: f64, b: f64, op: &str) -> PyResult<f64> {
    match op {
        "add" => Ok(a + b),
        "sub" => Ok(a - b),
        "mul" => Ok(a * b),
        "div" => {
            if b == 0.0 {
                // 返回 Err 自动转 Python 的 ZeroDivisionError
                Err(pyo3::exceptions::PyZeroDivisionError::new_err("division by zero"))
            } else {
                Ok(a / b)
            }
        }
        _ => Err(pyo3::exceptions::PyValueError::new_err(format!("unknown op: {}", op))),
    }
}

/// 接受和返回 Vec（自动转 Python list）
#[pyfunction]
fn filter_positive(input: Vec<i32>) -> Vec<i32> {
    input.into_iter().filter(|&x| x > 0).collect()
}

/// 接受和返回 HashMap（自动转 Python dict）
#[pyfunction]
fn word_count(text: &str) -> HashMap<String, usize> {
    let mut counts = HashMap::new();
    for word in text.split_whitespace() {
        *counts.entry(word.to_string()).or_insert(0) += 1;
    }
    counts
}

/// 带默认参数的函数
#[pyfunction]
#[pyo3(signature = (base, exponent = 2))]
fn power(base: f64, exponent: i32) -> f64 {
    base.powi(exponent)
}

/// 接受 *args 和 **kwargs
#[pyfunction]
#[pyo3(signature = (*args, **kwargs))]
fn demo_args(args: &Bound<'_, PyTuple>, kwargs: Option<&Bound<'_, PyDict>>) {
    println!("args: {:?}", args);
    if let Some(kw) = kwargs {
        println!("kwargs: {:?}", kw);
    }
}
```

类型映射：

| Rust 类型 | Python 类型 |
|---|---|
| `i8`/`i16`/`i32`/`i64`/`isize` | `int` |
| `u8`/`u16`/`u32`/`u64`/`usize` | `int` |
| `f32`/`f64` | `float` |
| `bool` | `bool` |
| `&str`/`String` | `str` |
| `Vec<T>` | `list` |
| `HashMap<K,V>`/`BTreeMap<K,V>` | `dict` |
| `HashSet<T>`/`BTreeSet<T>` | `set` |
| `Option<T>` | `T` 或 `None` |
| `Result<T,E>` | `T` 或抛出异常 |
| `(T1, T2)` | `tuple` |
| `&[u8]`/`Vec<u8>` | `bytes` |

## 5. 绑定结构体与方法

```rust
use pyo3::prelude::*;

/// 设备类，暴露给 Python
#[pyclass(name = "Device")]  // Python 端的类名
struct Device {
    #[pyo3(get)]  // 只读属性
    id: u32,

    #[pyo3(get, set)]  // 读写属性
    name: String,

    connected: bool,  // 不暴露给 Python，内部状态
}

#[pymethods]
impl Device {
    /// 构造函数
    #[new]
    #[pyo3(signature = (id, name = "unknown"))]
    fn new(id: u32, name: String) -> Self {
        Device { id, name, connected: false }
    }

    /// 实例方法
    fn connect(&mut self) -> PyResult<bool> {
        if self.connected {
            return Ok(false);
        }
        self.connected = true;
        Ok(true)
    }

    fn disconnect(&mut self) {
        self.connected = false;
    }

    #[getter]  // 只读属性的 getter（也可以用 #[pyo3(get)]）
    fn is_connected(&self) -> bool {
        self.connected
    }

    /// 静态方法
    #[staticmethod]
    fn device_count() -> i32 {
        42  // 实际应从全局状态读取
    }

    /// 类方法
    #[classmethod]
    fn from_config(_cls: &Bound<'_, PyType>, config: &Bound<'_, PyDict>) -> PyResult<Self> {
        let id: u32 = config.get_item("id")?.unwrap().extract()?;
        let name: String = config.get_item("name")?.unwrap().extract()?;
        Ok(Device::new(id, name))
    }

    /// __repr__
    fn __repr__(&self) -> String {
        format!("<Device id={} name={} connected={}>", self.id, self.name, self.connected)
    }

    /// __str__
    fn __str__(&self) -> String {
        format!("{}({})", self.name, self.id)
    }
}
```

Python 端使用：

```python
import rust_py_demo

d = rust_py_demo.Device(100, "sensor-001")
print(d.id)            # 100（只读）
print(d.name)          # sensor-001
d.name = "sensor-002"  # 读写
print(d.is_connected)  # False

d.connect()
print(d.is_connected)  # True

print(d)               # <Device id=100 name=sensor-002 connected=True>
print(rust_py_demo.Device.device_count())  # 42

# 类方法
d2 = rust_py_demo.Device.from_config({"id": 200, "name": "actuator"})
```

`#[pyclass]` 标注结构体，`#[pymethods]` 标注 impl 块。`#[new]` 是构造函数，`#[staticmethod]` 是静态方法，`#[classmethod]` 是类方法。属性可以用 `#[pyo3(get, set)]` 直接标注字段，或用 `#[getter]`/`#[setter]` 写自定义方法。

## 6. 错误处理：Result 与异常

PyO3 的错误处理非常优雅：Rust 的 `Result<T, E>` 中 `Err(E)` 自动转换为 Python 异常。

```rust
use pyo3::prelude::*;
use std::fmt;

/// 自定义错误类型
#[derive(Debug)]
struct ProtocolError {
    code: i32,
    message: String,
}

impl fmt::Display for ProtocolError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "ProtocolError(code={}): {}", self.code, self.message)
    }
}

impl std::error::Error for ProtocolError {}

// 实现 From<ProtocolError> for PyErr，让 ? 运算符自动转换
impl From<ProtocolError> for PyErr {
    fn from(err: ProtocolError) -> Self {
        // 可以用内置异常，也可以注册自定义异常类
        pyo3::exceptions::PyRuntimeError::new_err(err.to_string())
    }
}

/// 使用 ? 运算符自动传播错误
#[pyfunction]
fn parse_packet(data: &[u8]) -> PyResult<(u8, u32, Vec<u8>)> {
    if data.len() < 8 {
        return Err(ProtocolError {
            code: -1,
            message: format!("packet too short: {} < 8", data.len()),
        }.into());
    }
    let cmd = data[0];
    let seq = u32::from_be_bytes([data[1], data[2], data[3], data[4]]);
    let payload = data[8..].to_vec();
    Ok((cmd, seq, payload))
}

/// 注册自定义 Python 异常类
#[pymodule]
fn rust_py_demo(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // 定义自定义异常，继承 RuntimeError
    let exc = pyo3::exceptions::PyException::new_type(
        m.py(),
        "ProtocolError",
        Some(pyo3::exceptions::PyRuntimeError::type_object(m.py()).as_any()),
    )?;
    m.add("ProtocolError", exc)?;
    m.add_function(wrap_pyfunction!(parse_packet, m)?)?;
    Ok(())
}
```

Python 端捕获：

```python
import rust_py_demo

try:
    cmd, seq, payload = rust_py_demo.parse_packet(b"\x01\x00\x00")
except rust_py_demo.ProtocolError as e:
    print(f"协议错误: {e}")
except RuntimeError as e:
    print(f"运行时错误: {e}")
```

## 7. Python 对象交互与 GIL

### 7.1 释放 GIL 执行计算

与 pybind11 的 `py::gil_scoped_release` 对应，PyO3 用 `Python::allow_threads`：

```rust
#[pyfunction]
fn heavy_compute(data: Vec<f64>) -> f64 {
    // 释放 GIL，允许其他 Python 线程运行
    Python::with_gil(|py| {
        py.allow_threads(|| {
            // 这里不能访问任何 Python 对象
            let mut sum = 0.0;
            for &x in &data {
                sum += x * x;
            }
            sum.sqrt()
        })
    })
}
```

`allow_threads` 闭包中不能使用 `Python<'py>` 令牌或任何 Python 对象（`&PyAny`、`Bound<PyDict>` 等），因为 GIL 已释放，访问 Python 对象是未定义行为。

### 7.2 直接操作 Python 对象

需要高性能地操作 Python 对象（如大列表）时，可以用 `Bound<'_, PyList>` 直接访问，避免 `Vec` 转换的拷贝：

```rust
use pyo3::prelude::*;
use pyo3::types::PyList;

/// 直接操作 Python list，零拷贝
#[pyfunction]
fn sum_list(list: &Bound<'_, PyList>) -> PyResult<f64> {
    let mut sum = 0.0;
    for item in list.iter() {
        sum += item.extract::<f64>()?;
    }
    Ok(sum)
}

/// 接受 bytes，零拷贝访问底层数据
#[pyfunction]
fn crc32_bytes(data: &[u8]) -> u32 {
    // data 直接指向 Python bytes 的底层内存，零拷贝
    let mut crc: u32 = 0xFFFF_FFFF;
    for &b in data {
        crc ^= b as u32;
        for _ in 0..8 {
            crc = if crc & 1 != 0 {
                (crc >> 1) ^ 0xEDB8_8320
            } else {
                crc >> 1
            };
        }
    }
    !crc
}
```

`&[u8]` 参数直接借用 Python bytes 的内存，零拷贝。这比 `Vec<u8>`（会拷贝）高效得多，适合处理大数据。

## 8. 对比 pybind11

| 维度 | PyO3 (Rust) | pybind11 (C++) |
|---|---|---|
| 语言 | Rust | C++17 |
| 绑定方式 | 过程宏 `#[pyfunction]`/`#[pyclass]` | 宏 `PYBIND11_MODULE` + `m.def()` |
| 构建工具 | maturin（一条命令） | CMake + `pybind11_add_module` |
| 内存安全 | Rust 编译器保证，无悬空指针 | 需手动管理生命周期，`return_value_policy` |
| GIL 释放 | `py.allow_threads(\|\| {})` | `py::gil_scoped_release` |
| 错误处理 | `Result<T,E>` 自动转异常 | `throw` 异常 + `register_exception_translator` |
| STL/集合转换 | `Vec`/`HashMap` 自动转 | `std::vector`/`std::map` 自动转（需 `stl.h`） |
| 零拷贝数据 | `&[u8]` 直接借用 bytes | `py::buffer`/`py::bytes` |
| 编译速度 | Rust 编译较慢（增量编译尚可） | C++ 编译较慢（头文件包含） |
| 生态成熟度 | 较新但活跃，0.2x 版本 | 成熟稳定，2.1x 版本 |
| 交叉编译 | cargo 交叉编译支持好 | CMake 交叉编译需配置 toolchain |
| 适用场景 | Rust 库的 Python 绑定 | C++ 库的 Python 绑定 |

**选择建议**：

- 已有 C++ 库 → 用 pybind11，不要为了绑定而重写为 Rust。
- 已有 Rust 库 → 用 PyO3，天然适配。
- 新写性能内核 → 选 Rust 还是 C++ 取决于团队技能和生态需求；两者的 Python 绑定体验都很好。
- 内存安全要求高（如处理不可信输入）→ Rust + PyO3 更有优势。

## 9. 三语言分工决策表

在一个系统中同时使用 C++、Rust、Python 时，按以下维度分工：

| 维度 | C++ | Rust | Python |
|---|---|---|---|
| **定位** | 性能内核、遗留系统 | 新写性能内核、安全敏感 | 业务外壳、工具脚本 |
| **典型模块** | 已有算法库、驱动、实时处理 | 网络协议、加解密、CLI 工具 | 测试编排、配置管理、报告生成 |
| **性能** | 极高（手动优化） | 极高（零成本抽象） | 低（解释执行） |
| **内存安全** | 手动管理，易出错 | 编译器保证 | GC，安全但有开销 |
| **并发模型** | 线程 + 锁（易死锁） | 所有权 + Send/Sync（编译期检查） | GIL + asyncio |
| **编译时间** | 慢（头文件） | 慢（泛型展开） | 无编译 |
| **开发速度** | 慢（类型+手动内存） | 中（借用检查器学习曲线） | 快（动态类型+丰富库） |
| **互操作** | C ABI / pybind11 | C ABI / PyO3 / cxx | ctypes / cffi / pybind11 / PyO3 |
| **适合场景** | 已有大量 C++ 代码、硬件驱动、超低延迟 | 新系统服务、网络代理、安全工具 | 自动化、测试、数据分析、原型 |
| **不适合场景** | 新项目（维护成本高） | 极短生命周期脚本 | 性能热点 |

**分层架构**：

```text
┌──────────────────────────────────────────────┐
│  Python 层（业务外壳 + 工具脚本）              │
│  - 测试用例编排、参数扫描                      │
│  - 配置解析、日志分析、报告生成                 │
│  - 构建脚本、部署自动化                         │
│  - 快速原型验证                                │
├──────────────────────────────────────────────┤
│  绑定层（薄胶水）                              │
│  - pybind11 (C++ → Python)                    │
│  - PyO3 (Rust → Python)                       │
│  - ctypes/cffi (C ABI → Python)               │
├──────────────────────┬───────────────────────┤
│  C++ 性能内核         │  Rust 性能内核          │
│  - 已有算法库         │  - 网络协议解析         │
│  - 硬件驱动           │  - 加解密编解码         │
│  - 实时信号处理       │  - 异步 IO 服务         │
│  - 遗留系统维护       │  - 新写高性能模块       │
└──────────────────────┴───────────────────────┘
```

**决策流程**：

1. **先写 Python**：所有功能先用 Python 实现，跑通流程。
2. **profile 找瓶颈**：用 `cProfile` 或 `time.perf_counter()` 定位性能热点。
3. **判断是否下沉**：
   - 热点是计算密集型且数据量大 → 下沉到原生语言。
   - 热点是 IO 密集 → 用 Python asyncio 或线程池，不必下沉。
4. **选 C++ 还是 Rust**：
   - 已有 C++ 库可复用 → C++ + pybind11。
   - 新写模块且团队有 Rust 经验 → Rust + PyO3。
   - 内存安全要求高（处理不可信输入）→ Rust。
   - 需要与硬件驱动/已有 C++ 代码深度集成 → C++。
5. **保持绑定层薄**：绑定层只做类型转换和异常翻译，不写业务逻辑。
6. **C++ 与 Rust 共存**：通过 C ABI（`extern "C"`）互操作，或都暴露为 Python 模块在 Python 层组合。

Rust 的异步运行时 Tokio 在高性能网络服务中常用，参见《../../04-Rust技术体系/03-并发与异步编程/04-Tokio运行时与异步生态.md》。

## 10. 完整示例：Rust 协议解析库的 Python 绑定

一个完整的 Rust 协议解析库，暴露为 Python 模块。

`Cargo.toml`：

```toml
[package]
name = "proto_parser"
version = "0.1.0"
edition = "2021"

[lib]
name = "proto_parser"
crate-type = ["cdylib"]

[dependencies]
pyo3 = { version = "0.21", features = ["extension-module"] }
crc32fast = "1.3"
```

`src/lib.rs`：

```rust
use pyo3::prelude::*;
use crc32fast::Hasher;

/// 协议帧
#[pyclass(name = "Frame")]
#[derive(Clone)]
pub struct Frame {
    #[pyo3(get)]
    pub length: u16,
    #[pyo3(get)]
    pub version: u8,
    #[pyo3(get)]
    pub cmd: u8,
    #[pyo3(get)]
    pub seq: u32,
    #[pyo3(get)]
    pub payload: Vec<u8>,
}

#[pymethods]
impl Frame {
    #[new]
    fn new(cmd: u8, seq: u32, payload: Vec<u8>) -> Self {
        Frame {
            length: 8 + payload.len() as u16,
            version: 1,
            cmd,
            seq,
            payload,
        }
    }

    /// 序列化为字节
    fn serialize(&self) -> PyResult<Vec<u8>> {
        let mut buf = Vec::with_capacity(self.length as usize + 6);
        buf.extend_from_slice(&self.length.to_be_bytes());
        buf.push(self.version);
        buf.push(self.cmd);
        buf.extend_from_slice(&self.seq.to_be_bytes());
        buf.extend_from_slice(&self.payload);
        // CRC32 附加在末尾
        let mut hasher = Hasher::new();
        hasher.update(&buf);
        let crc = hasher.finalize();
        buf.extend_from_slice(&crc.to_be_bytes());
        Ok(buf)
    }

    fn __repr__(&self) -> String {
        format!(
            "<Frame cmd=0x{:02x} seq={} len={} payload={}>",
            self.cmd, self.seq, self.length,
            self.payload.iter().map(|b| format!("{:02x}", b)).collect::<String>()
        )
    }
}

/// 解析字节为帧
#[pyfunction]
fn parse_frame(data: &[u8]) -> PyResult<Frame> {
    if data.len() < 10 {
        return Err(pyo3::exceptions::PyValueError::new_err(
            format!("data too short: {} < 10", data.len())
        ));
    }
    let length = u16::from_be_bytes([data[0], data[1]]);
    let version = data[2];
    let cmd = data[3];
    let seq = u32::from_be_bytes([data[4], data[5], data[6], data[7]]);
    let payload_end = 8 + (length as usize - 8);
    if data.len() < payload_end + 4 {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "data truncated: not enough for payload + crc"
        ));
    }
    let payload = data[8..payload_end].to_vec();

    // 验证 CRC32
    let stored_crc = u32::from_be_bytes([
        data[payload_end], data[payload_end+1],
        data[payload_end+2], data[payload_end+3],
    ]);
    let mut hasher = Hasher::new();
    hasher.update(&data[..payload_end]);
    let calc_crc = hasher.finalize();
    if stored_crc != calc_crc {
        return Err(pyo3::exceptions::PyValueError::new_err(
            format!("CRC mismatch: stored=0x{:08x}, calc=0x{:08x}", stored_crc, calc_crc)
        ));
    }

    Ok(Frame { length, version, cmd, seq, payload })
}

/// 批量解析，释放 GIL 提升性能
#[pyfunction]
fn parse_batch(data_list: Vec<Vec<u8>>) -> PyResult<Vec<Frame>> {
    Python::with_gil(|py| {
        py.allow_threads(|| {
            data_list.into_iter()
                .map(|data| parse_frame(&data))
                .collect()
        })
    })
}

#[pymodule]
fn proto_parser(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Frame>()?;
    m.add_function(wrap_pyfunction!(parse_frame, m)?)?;
    m.add_function(wrap_pyfunction!(parse_batch, m)?)?;
    Ok(())
}
```

Python 端使用：

```python
import proto_parser

# 创建帧并序列化
frame = proto_parser.Frame(cmd=0x01, seq=100, payload=bytes([0xAA, 0xBB, 0xCC]))
data = frame.serialize()
print(f"serialized: {data.hex()}")

# 解析回来
parsed = proto_parser.parse_frame(data)
print(parsed)  # <Frame cmd=0x01 seq=100 len=11 payload=aabbcc>

# 批量解析（释放 GIL，多核并行）
packets = [data for _ in range(1000)]
results = proto_parser.parse_batch(packets)
print(f"parsed {len(results)} frames")
```

构建：

```bash
maturin develop --release
python test_proto.py
```

这个示例展示了 PyO3 的完整工作流：`#[pyclass]` 定义类、`#[pymethods]` 绑定方法、`#[pyfunction]` 绑定函数、`PyResult` 错误处理、`allow_threads` 释放 GIL、`&[u8]` 零拷贝访问 bytes。

## 11. 常见坑

**坑 1：`cdylib` 忘记设置。** `Cargo.toml` 中 `[lib] crate-type = ["cdylib"]` 必须设置，否则编译出的是 rlib，Python 无法加载。

**坑 2：GIL 释放后访问 Python 对象。** `py.allow_threads(|| {})` 闭包中不能访问任何 Python 对象（`Bound<PyDict>`、`&PyAny` 等），否则是未定义行为（可能段错误）。必须在释放 GIL 前把需要的数据提取为 Rust 原生类型（`Vec`、`String`）。

**坑 3：`Vec<u8>`  vs `&[u8]` 的拷贝。** 函数参数写 `Vec<u8>` 会从 Python bytes 拷贝一份数据；写 `&[u8]` 是零拷贝借用。大数据量时必须用 `&[u8]`。

**坑 4：`#[pyclass]` 结构体不是 `Send`。** 默认 `#[pyclass]` 标记为 `!Send`（不能跨线程移动），因为 Python 对象不是线程安全的。如果需要在 Rust 线程间移动，用 `#[pyclass(unsendable)]` 或确保只在持有 GIL 的线程中访问。

**坑 5：maturin develop 没加 --release。** 默认是 debug 模式，性能差 10-50 倍。开发时验证功能用 debug，跑性能测试必须 `--release`。

**坑 6：Python 版本不匹配。** maturin 会自动检测当前虚拟环境的 Python 版本，但如果系统有多个 Python，可能编到错误的版本。用 `which python` 确认当前环境，或在 `pyproject.toml` 中指定 `requires-python`。

**坑 7：`#[pyo3(signature)]` 语法错误。** 默认参数必须写在 `signature` 属性中，不能像普通 Rust 函数那样写默认值（Rust 不支持函数默认参数）。`#[pyo3(signature = (a, b = 2))]` 是正确写法。

**坑 8：Windows 上 MSVC 版本不匹配。** Rust 的 MSVC 工具链必须与 Python 解释器使用的 MSVC 版本一致（通常是 Visual Studio 2019/2022）。用 `rustup show` 确认工具链，安装对应的 Build Tools。

## 12. 本节小结

- PyO3 是 Rust 的 Python 绑定标准库，用过程宏 `#[pyfunction]`/`#[pyclass]`/`#[pymethods]` 标注符号，编译器自动生成绑定。
- maturin 是构建工具，`maturin develop --release` 一条命令编译并安装到当前虚拟环境，替代了繁琐的 setup.py。
- 函数绑定用 `#[pyfunction]`，默认参数用 `#[pyo3(signature = (a, b = 2))]`，`Result<T,E>` 自动转 Python 异常。
- 类绑定用 `#[pyclass]` + `#[pymethods]`，`#[new]` 是构造函数，`#[pyo3(get, set)]` 标注属性，`#[staticmethod]`/`#[classmethod]` 绑定静态/类方法。
- GIL 释放用 `Python::with_gil(|py| py.allow_threads(|| {}))`，闭包中不能访问 Python 对象。
- 零拷贝数据用 `&[u8]` 参数直接借用 Python bytes，比 `Vec<u8>` 高效。
- PyO3 与 pybind11 体验相似，选择取决于已有库的语言：C++ 用 pybind11，Rust 用 PyO3。
- 三语言分工：Python 做业务外壳和工具脚本，C++ 做已有性能内核和硬件驱动，Rust 做新写高性能模块和安全敏感组件，绑定层保持薄胶水。
- 最常见的坑：忘记 `cdylib`、GIL 释放后访问 Python 对象、`Vec<u8>` 拷贝、maturin 不加 `--release`、默认参数语法错误。

---

上一篇：《02-pybind11封装C++模块.md》
