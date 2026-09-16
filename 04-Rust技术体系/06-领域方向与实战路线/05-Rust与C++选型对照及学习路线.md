# Rust 与 C++选型对照及学习路线

> 本节目标：从语言哲学、性能、内存安全、开发效率、生态成熟度、就业趋势六个维度系统对比 Rust 与 C++，给出 C++ 老项目引入 Rust 的渐进迁移策略，规划从入门到实战的分阶段学习路线，提供 15 个阶梯练手项目和 30 道 Rust 面试高频题及答题要点。

## 本章速览

- [1. 语言哲学对比](#1-语言哲学对比)
  - [1.1 设计目标与核心价值观](#11-设计目标与核心价值观)
  - [1.2 表达哲学：显式优于隐式](#12-表达哲学显式优于隐式)
- [2. 六维度系统对比](#2-六维度系统对比)
  - [2.1 性能](#21-性能)
  - [2.2 内存安全](#22-内存安全)
  - [2.3 开发效率](#23-开发效率)
  - [2.4 生态成熟度](#24-生态成熟度)
  - [2.5 并发模型](#25-并发模型)
  - [2.6 就业岗位与趋势（定性）](#26-就业岗位与趋势定性)
- [3. 互操作与渐进迁移策略](#3-互操作与渐进迁移策略)
  - [3.1 FFI 基础：C ABI 桥接](#31-ffi-基础c-abi-桥接)
  - [3.2 C++ 调用 Rust：cxx 与 autocxx](#32-c-调用-rustcxx-与-autocxx)
  - [3.3 Rust 调用 C++：bindgen](#33-rust-调用-cbindgen)
  - [3.4 渐进迁移四步法](#34-渐进迁移四步法)
- [4. 分阶段学习路线](#4-分阶段学习路线)
  - [4.1 第一阶段：入门（1-2 周）](#41-第一阶段入门1-2-周)
  - [4.2 第二阶段：所有权与借用（2-3 周）](#42-第二阶段所有权与借用2-3-周)
  - [4.3 第三阶段：trait 与泛型（2 周）](#43-第三阶段trait-与泛型2-周)
  - [4.4 第四阶段：并发与 async（3-4 周）](#44-第四阶段并发与-async3-4-周)
  - [4.5 第五阶段：工程化与实战（持续）](#45-第五阶段工程化与实战持续)
- [5. 阶梯练手项目清单（15 个）](#5-阶梯练手项目清单15-个)
- [6. Rust 面试高频题 30 道及答题要点](#6-rust-面试高频题-30-道及答题要点)
- [7. 快速参考卡片](#7-快速参考卡片)
- [8. 常见坑](#8-常见坑)
- [9. 本节小结](#9-本节小结)

---

## 1. 语言哲学对比

### 1.1 设计目标与核心价值观

C++ 的设计哲学是**"零成本抽象 + 多范式 + 向后兼容"**。Bjarne Stroustrup 的核心目标是让 C 语言获得面向对象和泛型能力，同时不牺牲性能。这导致 C++ 是一门"加法语言"——每个标准都在增加新特性，旧特性永不移除，语言复杂度持续累积。

Rust 的设计哲学是**"安全 + 并发 + 实用"**。Mozilla 的核心目标是解决 C++ 中的内存安全和数据竞争问题，同时保持系统级性能。Rust 是一门"减法语言"——通过所有权系统在编译期消除整类 bug，用更严格的规则换取更少的运行时错误。

| 维度 | C++ | Rust |
| --- | --- | --- |
| 核心目标 | 高效 + 灵活 + 兼容 | 安全 + 并发 + 零成本 |
| 错误倾向 | 运行时错误（内存/并发） | 编译期错误（所有权/借用） |
| 学习曲线 | 平缓入门，陡峭精通 | 陡峭入门，平缓精通 |
| 设计取舍 | 灵活性优先，安全靠纪律 | 安全性优先，灵活需 unsafe |
| 标准演进 | 增量加法，保留历史包袱 | 可移除旧特性（edition 机制） |

### 1.2 表达哲学：显式优于隐式

C++ 中有大量隐式行为：隐式类型转换（`int` → `double`、派生类 → 基类）、隐式构造函数（`explicit` 才禁止）、隐式 `this` 指针、异常隐式传播、运算符重载的隐式调用。这些隐式行为让代码简洁，但也让 bug 更隐蔽。

Rust 的原则是**显式优于隐式**：类型转换必须用 `as` 或 `From/Into` trait，构造函数是关联函数 `Type::new()`，错误传播用 `?` 运算符显式标记，运算符重载通过 trait 显式实现，借用检查器要求明确标注生命周期。这种显式性让代码更冗长，但也更可预测、更易审查。

## 2. 六维度系统对比

### 2.1 性能

Rust 和 C++ 的性能在同一量级，都是**零成本抽象**的代表——高级抽象不产生运行时开销。具体差异：

- **编译优化**：两者都依赖 LLVM 后端（rustc 和 clang），优化能力基本对齐。Rust 的 `unsafe` 块内可以写出与 C++ 完全等价的代码
- **迭代器**：Rust 的迭代器适配器（`map`/`filter`/`fold`）在 release 模式下完全内联，生成的汇编与手写循环一致，甚至更好（自动向量化）
- **边界检查**：Rust 默认数组/切片访问有边界检查（panic 而非越界），C++ 的 `[]` 无检查。但 Rust 的迭代器和 `get_unchecked`（unsafe）可以消除检查开销
- **分配器**：Rust 默认使用系统分配器，可通过 `#[global_allocator]` 切换为 jemalloc/mimalloc。C++ 默认 `new/delete`，可自定义 `allocator`
- **微基准差异**：在某些微基准测试中 C++ 快 5%–10%，通常是因为 Rust 的边界检查或 panic 机制；在实际应用中差异通常不可测量

**结论**：性能不是选择 Rust 或 C++ 的决定性因素，两者都是系统级性能。选择 Rust 的核心理由是安全，不是性能。

### 2.2 内存安全

这是 Rust 与 C++ 最根本的差异。C++ 的内存安全完全依赖开发者纪律和工具（ASan/Valgrind/静态分析），而 Rust 在编译期保证：

- **无数据竞争**：`Send`/`Sync` trait 在编译期保证跨线程安全
- **无 use-after-free**：所有权系统保证引用不会指向已释放的内存
- **无空指针解引用**：`Option<T>` 强制处理空值，不存在 `nullptr`
- **无缓冲区溢出**：切片和 `Vec` 的安全 API 有边界检查
- **无未初始化内存**：变量必须初始化才能使用

C++ 现代特性（`unique_ptr`/`shared_ptr`、`std::optional`、`std::span`）可以缓解这些问题，但它们是库层面的约定，不是语言层面的保证——开发者仍然可以写出 `unique_ptr` 解引用空指针、`shared_ptr` 循环引用、`span` 指向已释放内存。Rust 的保证是编译器强制执行的，无法绕过（除非使用 `unsafe`）。

微软安全响应中心的数据表明，其产品中约 70% 的安全漏洞是内存安全问题。Chrome 团队也报告类似比例。Rust 从根本上消除了这类漏洞。

### 2.3 开发效率

开发效率需要分阶段看：

- **初期（0-3 个月）**：C++ 更高。C++ 的语法和概念对有 C/Java 基础的开发者更熟悉，Rust 的所有权/借用/生命周期是全新概念，编译错误频繁，"与借用检查器搏斗"是必经阶段
- **中期（3-12 个月）**：Rust 反超。一旦理解了所有权系统，Rust 的编译错误变成了"免费的代码审查"——编译器指出的问题往往是 C++ 中需要资深开发者审查才能发现的 bug。重构时 Rust 的编译器保证修改不会引入内存/并发错误，C++ 重构需要大量测试覆盖
- **长期（1 年+）**：Rust 显著更高。C++ 项目随着代码量增长，技术债务累积（旧风格代码、历史包袱、隐式行为），新人上手难度指数级增长。Rust 项目的代码质量底线由编译器保证，新人提交的代码至少在内存/并发安全上是正确的

Cargo 也是开发效率的巨大优势：统一的构建系统、包管理、测试框架、文档生成，一条 `cargo new/build/test/doc` 搞定。C++ 的构建系统碎片化（CMake/Meson/Bazel/Make）、包管理缺失（Conan/vcpkg 仍在演进）、测试框架各自为政。

### 2.4 生态成熟度

| 领域 | C++ | Rust |
| --- | --- | --- |
| 游戏引擎 | Unreal、Unity（C++后端）、自研 | Bevy（活跃）、godot-rust 绑定 |
| GUI | Qt、wxWidgets、MFC、GTKmm | Tauri、egui、slint、gtk-rs |
| 数据库 | MySQL、PostgreSQL、Redis、MongoDB | TiKV、sled、SQLite 绑定、MeiliSearch |
| 网络/代理 | Nginx、HAProxy、Envoy（C++） | pingora、Linkerd2-proxy、rust-libp2p |
| 区块链 | 较少（部分 C++ 实现） | Solana、Substrate、Polkadot、CosmWasm |
| 操作系统 | Linux 内核、Windows、macOS | Linux 内核 Rust 支持、Redox OS、Theseus |
| 嵌入式 | 事实标准（ARM/MCU 全部支持） | `no_std` 支持成熟，STM32/ESP32/RISC-V |
| 科学计算 | Eigen、Boost、CGAL、TensorFlow C++ | ndarray、faer（新）、polars |
| 音频/视频 | FFmpeg、GStreamer、WebRTC | Symphonia（纯 Rust 音频）、rav1e（AV1 编码） |

C++ 生态在传统领域（游戏、GUI、科学计算、嵌入式）有 20+ 年的积累，Rust 生态在新兴领域（区块链、云原生基础设施、CLI 工具）增长更快。Rust 的 FFI 能力让它可以调用任何 C 库，弥补了生态差距。

### 2.5 并发模型

C++ 的并发模型是**"线程 + 共享内存 + 锁"**：`std::thread`、`std::mutex`、`std::condition_variable`、`std::atomic`。数据竞争是未定义行为，编译器不做任何检查。C++20 引入了 `std::jthread`、`std::counting_semaphore`、`std::latch`、`std::barrier`，但核心模型未变。C++23/26 计划引入执行器（executor）和异步操作，但生态尚未成熟。

Rust 的并发模型是**"所有权 + Send/Sync + 异步运行时"**：
- `std::thread` 用于 OS 线程，`spawn` 要求闭包 `Send + 'static`
- `std::sync` 提供 `Mutex`/`RwLock`/`Arc`/`Barrier`，编译器保证只有 `Send + Sync` 的类型可以跨线程共享
- `async/await` 是语言级特性，`tokio`/`async-std`/`smol` 提供运行时
- `tokio::sync` 提供异步版的 `Mutex`/`RwLock`/`mpsc`/`oneshot`/`watch`
- `crossbeam` 提供无锁数据结构和工作窃取通道

Rust 的并发优势是**编译期消除数据竞争**——两个线程同时写同一个变量在 Rust 中无法通过编译（除非用 `unsafe` 或 `Mutex` 保护）。这在 C++ 中是运行时 bug，极难复现和调试。

### 2.6 就业岗位与趋势（定性）

> 以下为定性描述，不涉及具体薪资数字。

**C++ 就业市场**：存量巨大，岗位集中在游戏（腾讯/网易/米哈游）、数据库（Oracle/MySQL/Redis）、高频交易（量化私募）、嵌入式/自动驾驶（车企/Tier1）、操作系统/编译器（华为/苹果/微软）、音视频（FFmpeg/直播）。C++ 岗位要求经验丰富，初级岗位较少，薪资与经验强相关。

**Rust 就业市场**：增量快速增长，岗位集中在区块链（Solana/Polkadot 生态项目）、云原生基础设施（PingCAP/TiKV、Cloudflare/pingora、Buoyant/Linkerd）、CLI 工具（初创公司）、操作系统（Linux 内核 Rust 子系统）、WebAssembly（Wasm 运行时和工具链）、安全关键系统。Rust 岗位通常要求同时具备系统编程基础和 Rust 经验，初级岗位正在增加但仍少于 C++。

**趋势判断**：Rust 在基础设施和新兴领域的采用率持续上升，Linux 内核接受 Rust 是标志性事件。但 C++ 在游戏、嵌入式、传统高性能计算领域的地位短期内不可撼动。最务实的策略是**C++ 为基本盘，Rust 为差异化技能**——两者都掌握的开发者在求职市场最有竞争力。

## 3. 互操作与渐进迁移策略

### 3.1 FFI 基础：C ABI 桥接

Rust 和 C++ 的互操作通过 C ABI 进行——Rust 函数标记 `extern "C"`，C++ 函数用 `extern "C"` 包装，双方通过 C 兼容的类型（指针、整数、浮点数、C 风格结构体）通信。

Rust 侧导出 C 函数：

```rust
// lib.rs
#[no_mangle]
pub extern "C" fn rust_add(a: i32, b: i32) -> i32 {
    a + b
}

#[no_mangle]
pub extern "C" fn rust_greet(name: *const std::os::raw::c_char) {
    let c_str = unsafe { std::ffi::CStr::from_ptr(name) };
    if let Ok(s) = c_str.to_str() {
        println!("Rust: 你好, {}!", s);
    }
}
```

Cargo.toml 配置为 cdylib：

```toml
[lib]
crate-type = ["cdylib", "staticlib"]
```

C++ 侧调用：

```cpp
// main.cpp
#include <cstdint>
#include <iostream>

extern "C" {
    int32_t rust_add(int32_t a, int32_t b);
    void rust_greet(const char* name);
}

int main() {
    std::cout << "1 + 2 = " << rust_add(1, 2) << std::endl;
    rust_greet("C++ 世界");
    return 0;
}
```

### 3.2 C++ 调用 Rust：cxx 与 autocxx

直接用 C ABI 桥接需要手动处理字符串、向量、错误类型的转换，繁琐且容易出错。`cxx`（以 crates.io 最新稳定版为准）是 Google 开发的 Rust/C++ 互操作库，提供类型安全的双向绑定：

```rust
// Rust 侧
#[cxx::bridge]
mod ffi {
    // Rust 暴露给 C++ 的函数
    extern "Rust" {
        fn rust_process(input: &str) -> String;
        fn rust_compute(values: &[f64]) -> f64;
    }

    // C++ 暴露给 Rust 的函数和类型
    unsafe extern "C++" {
        include!("myapp/include/cpp_api.h");
        type CppConfig;
        fn cpp_create_config(path: &str) -> UniquePtr<CppConfig>;
        fn cpp_get_value(self: &CppConfig, key: &str) -> String;
    }
}

fn rust_process(input: &str) -> String {
    format!("Rust 处理: {}", input)
}

fn rust_compute(values: &[f64]) -> f64 {
    values.iter().sum()
}
```

`cxx` 自动生成 C++ 侧的绑定代码，`String`/`&str`/`Vec<T>`/`&[T]` 在两边自动转换，`UniquePtr<T>` 对应 C++ 的 `std::unique_ptr`。

`autocxx` 是 cxx 的超集，可以自动解析 C++ 头文件并生成 Rust 绑定，适合已有大型 C++ 代码库的场景。

### 3.3 Rust 调用 C++：bindgen

`bindgen`（以 crates.io 最新稳定版为准）从 C/C++ 头文件自动生成 Rust FFI 绑定：

```rust
// build.rs
fn main() {
    println!("cargo:rerun-if-changed=include/wrapper.h");
    let bindings = bindgen::Builder::default()
        .header("include/wrapper.h")
        .parse_callbacks(Box::new(bindgen::CargoCallbacks::new()))
        .generate()
        .expect("生成绑定失败");
    bindings
        .write_to_file("src/bindings.rs")
        .expect("写入绑定失败");
}
```

生成的绑定是 `unsafe` 的原始 FFI，通常需要再封装一层安全的 Rust API。对于 C++ 库，推荐先写 C 风格的包装头文件（`extern "C"` 函数），再用 bindgen 生成绑定。

### 3.4 渐进迁移四步法

对于已有 C++ 代码库，不建议重写，推荐渐进式迁移：

**第一步：建立 FFI 边界**。在 C++ 代码中定义清晰的模块边界，将需要迁移的部分封装为 C ABI 接口（`extern "C"` 函数 + 不透明指针句柄）。确保 C++ 侧可以通过这些接口调用模块功能。

**第二步：用 Rust 重写单个模块**。选择一个边界清晰、风险可控的模块（如日志、配置解析、工具函数），用 Rust 重写，通过 cxx 或 C ABI 与 C++ 主程序集成。保持 C++ 侧的接口不变，内部实现替换为 Rust。

**第三步：扩大迁移范围**。在验证了 Rust 模块的稳定性和性能后，逐步迁移更多模块。优先迁移：新增功能（直接用 Rust 写）、并发密集模块（Rust 的编译期并发安全收益最大）、安全敏感模块（处理不可信输入的解析器）。

**第四步：考虑核心模块迁移**。对于性能关键的核心模块，需要仔细评估迁移成本和收益。可以用 Rust 重写后做 A/B 性能对比，确认无回退后再切换。TiKV 的 RocksDB 绑定、Linkerd 的代理重写都是这种策略的成功案例。

**关键原则**：永远不要"大爆炸"式重写。保持 C++ 和 Rust 代码长期共存，通过 FFI 边界通信，让迁移在每个迭代中都是可逆的。

## 4. 分阶段学习路线

### 4.1 第一阶段：入门（1-2 周）

目标：熟悉 Rust 语法、Cargo 工具链、基本类型和控制流。

- 安装 Rustup，配置 stable 工具链
- 阅读《The Rust Programming Language》前 6 章（变量、函数、控制流、所有权基础、结构体、枚举）
- 完成 Rustlings 前 30 道练习（variables、functions、if、move_semantics、structs、enums）
- 用 `cargo new` 创建项目，写一个猜数字游戏和一个温度转换器
- 理解 `Result`/`Option` 和 `match`/`if let` 的基本用法

C++ 对照要点：Rust 的 `let` 对应 C++ 的 `auto`，`mut` 对应去掉 `const`，`enum` 是代数数据类型（比 C++ `enum class` 强大），`match` 是穷尽模式匹配（比 `switch` 强大）。

### 4.2 第二阶段：所有权与借用（2-3 周）

目标：彻底理解所有权、借用、生命周期，这是 Rust 最核心也最难的部分。

- 深入阅读《Rust 程序设计语言》第 4、10、15 章（引用与借用、生命周期、智能指针）
- 完成 Rustlings 的 move_semantics、borrows、lifetimes、options、error_handling 全部练习
- 理解 `Box<T>`、`Rc<T>`、`Arc<T>`、`RefCell<T>`、`Mutex<T>` 的使用场景和内部可变性
- 写一个单链表或二叉树（需要 `Box`/`Rc`/`RefCell`），体会所有权在数据结构中的应用
- 理解借用检查器的常见错误：`cannot move out of borrowed content`、`cannot borrow as mutable because also borrowed as immutable`、`lifetime may not live long enough`

C++ 对照要点：Rust 的 `&T` 对应 C++ 的 `const T&`，`&mut T` 对应 `T&`，但 Rust 强制保证了 C++ 仅靠约定的规则（不可变引用可多个、可变引用唯一、引用不悬空）。`Box<T>` 对应 `unique_ptr<T>`，`Rc<T>` 对应非线程安全的 `shared_ptr<T>`，`Arc<T>` 对应线程安全的 `shared_ptr<T>`。

### 4.3 第三阶段：trait 与泛型（2 周）

目标：掌握 trait 系统、泛型、trait object、闭包、迭代器。

- 阅读《Rust 程序设计语言》第 10、13 章（泛型与 trait、函数式语言特性）
- 理解 trait 作为接口的用法，`impl Trait`、`dyn Trait`、trait bounds、where 子句
- 掌握闭包（`Fn`/`FnMut`/`FnOnce`）和迭代器适配器（`map`/`filter`/`fold`/`collect`）
- 为自定义类型实现 `Display`、`Debug`、`From`、`Into`、`Iterator` 等标准 trait
- 理解孤儿规则和 trait 一致性，以及 `derive` 宏的原理

C++ 对照要点：Rust 的 trait 对应 C++ 的概念（Concepts，C++20）+ 抽象基类，但更灵活。泛型对应 C++ 模板，但 Rust 的 trait bounds 在编译期检查类型参数，C++ 模板是鸭子类型（直到实例化才检查）。`dyn Trait` 对应 C++ 的虚函数多态，有动态分发开销；`impl Trait` 和泛型对应静态分发，零开销。

### 4.4 第四阶段：并发与 async（3-4 周）

目标：掌握 Rust 的并发原语和异步编程，这是 Rust 区别于 C++ 的核心优势领域。

- 阅读《Rust 程序设计语言》第 16 章（无畏并发）和《Asynchronous Programming in Rust》
- 理解 `Send`/`Sync` trait，为什么它们能在编译期消除数据竞争
- 掌握 `std::thread`、`std::sync`（`Mutex`/`RwLock`/`Arc`/`Barrier`）、`std::sync::mpsc`
- 学习 `tokio` 运行时：`#[tokio::main]`、`tokio::spawn`、`tokio::sync`（异步 Mutex/channel）、`tokio::time`、`tokio::fs`、`tokio::net`
- 理解 `async/await` 的状态机原理，`Future` trait，Pin/UnPin，运行时的调度机制
- 写一个并发的 TCP echo server 和一个异步的 HTTP 客户端（用 `reqwest`）

C++ 对照要点：Rust 的 `std::thread` 对应 C++ `std::thread`，但 `spawn` 要求 `Send + 'static`。`async/await` 对应 C++20 协程，但 Rust 的生态（tokio）远比 C++ 协程生态成熟。Rust 的 `Send/Sync` 是 C++ 没有的编译期并发安全保证。更深入的并发模式可对照《../../01-C++技术体系/04-并发编程/05-线程池与并发实战模式.md》。

### 4.5 第五阶段：工程化与实战（持续）

目标：掌握 Rust 工程化实践，完成真实项目。

- 学习 `cargo` 高级用法：workspace、features、profile 优化、build.rs、cargo-asm/cargo-expand
- 测试：单元测试（`#[cfg(test)]`）、集成测试（`tests/`）、文档测试（`///` 中的代码块）、属性测试（`proptest`）
- 错误处理：`thiserror`（库错误）、`anyhow`（应用错误）、`eyre`（美化错误）
- 日志：`tracing`（结构化日志 + 分布式追踪）、`log` + `env_logger`
- 序列化：`serde` + `serde_json`/`toml`/`bincode`
- CLI：`clap` derive、`anyhow`、`indicatif`
- 异步网络：`tokio`、`hyper`、`reqwest`、`tonic`（gRPC）
- 完成至少一个完整项目（见下方练手项目清单）

## 5. 阶梯练手项目清单（15 个）

按难度从低到高排列，每个项目标注核心知识点：

| 序号 | 项目 | 核心知识点 | 预计工时 |
| --- | --- | --- | --- |
| 1 | 命令行待办清单（todo CLI） | clap、文件 IO、序列化 JSON | 4h |
| 2 | 温度转换器 + 单位换算器 | 基本语法、模式匹配、测试 | 2h |
| 3 | Markdown 链接检查器 | 正则、文件遍历、错误处理 | 6h |
| 4 | mini-grep（带正则和测试） | clap、regex、迭代器、单元/集成测试 | 8h |
| 5 | 并发文件下载器 | reqwest、tokio、indicatif、并发控制 | 8h |
| 6 | 简易 HTTP 服务器 | tokio::net、TCP 处理、HTTP 解析 | 12h |
| 7 | K-V 存储引擎（MemTable + WAL + SSTable） | 序列化、文件 IO、并发锁、崩溃恢复 | 20h |
| 8 | Redis 协议兼容的内存 K-V 服务器 | tokio、协议解析、并发数据结构 | 16h |
| 9 | 线程池实现 | 线程管理、channel、任务分发、优雅关闭 | 12h |
| 10 | 异步运行时（极简版 tokio） | Future trait、状态机、调度器、waker | 24h |
| 11 | TCP 代理 + 负载均衡 | tokio、双向转发、轮询/一致性哈希、健康检查 | 16h |
| 12 | gRPC 服务（tonic）+ 客户端 | protobuf、tonic、流式 RPC、拦截器 | 12h |
| 13 | 区块链最小实现（PoW + 交易 + P2P） | 哈希、签名、网络通信、共识基础 | 30h |
| 14 | WebAssembly 运行时插件系统 | wasmtime、插件加载、能力安全、宿主函数 | 20h |
| 15 | 贡献一个开源 Rust 项目的 PR | 代码阅读、社区规范、CI/CD、代码审查 | 不定 |

建议路径：1-4 入门 → 5-7 进阶 → 8-10 深入并发 → 11-13 领域实战 → 14-15 开源贡献。

## 6. Rust 面试高频题 30 道及答题要点

**语言基础（1-8）**

1. **所有权规则是什么？** 三个规则：每个值有唯一所有者；值在所有者离开作用域时被 drop；可以通过引用或移动共享/转移所有权。
2. **借用规则是什么？** 同一时刻要么一个可变引用，要么多个不可变引用；引用必须始终有效（不悬空）。
3. `&str` 和 `String` 的区别？ `&str` 是字符串切片（借用，不可变视图），`String` 是堆分配的可增长字符串（拥有所有权）。类比 C++ 的 `string_view` 和 `std::string`。
4. **什么是生命周期标注？为什么需要？** 生命周期标注告诉编译器引用的有效范围，确保引用不悬空。函数签名中 `fn foo<'a>(x: &'a str) -> &'a str` 表示返回值的生命周期与参数一致。
5. `Option<T>` 和 `Result<T, E>` 的区别？ `Option` 表示值可能不存在（Some/None），`Result` 表示操作可能成功或失败（Ok/Err）。`Option` 无错误信息，`Result` 携带错误类型。
6. `?` 运算符的作用？ 自动传播错误：如果 `Result` 是 `Err`，立即从函数返回该错误；如果是 `Ok`，解包内部值。要求函数返回类型是 `Result`。
7. **什么是 trait object？`dyn Trait` 和 `impl Trait` 的区别？** `dyn Trait` 是动态分发（运行时虚函数表，有开销），`impl Trait` 是静态分发（编译期单态化，零开销）。`dyn Trait` 可以在运行时存储不同类型，`impl Trait` 类型在编译期固定。
8. **闭包的三个 trait（Fn/FnMut/FnOnce）区别？** `FnOnce` 消费捕获变量（只能调用一次）；`FnMut` 可变借用捕获变量（可多次调用，修改环境）；`Fn` 不可变借用捕获变量（可多次调用，不修改环境）。

**内存与智能指针（9-14）**

9. `Box<T>`、`Rc<T>`、`Arc<T>` 的区别和使用场景？ `Box` 唯一所有权（堆分配，对应 unique_ptr）；`Rc` 引用计数（单线程，非线程安全共享）；`Arc` 原子引用计数（多线程安全共享）。
10. **什么是内部可变性？`RefCell<T>` 的作用？** 内部可变性允许在不可变引用后修改数据，通过运行时借用检查实现。`RefCell` 在单线程中提供运行时检查的可变/不可变借用，违反借用规则时 panic。
11. `Cell<T>` 和 `RefCell<T>` 的区别？ `Cell` 适用于 Copy 类型，通过 get/set 操作值（无运行时借用检查）；`RefCell` 适用于非 Copy 类型，通过 borrow/borrow_mut 返回引用（有运行时借用检查）。
12. **什么是悬空引用？Rust 如何防止？** 悬空引用指向已释放的内存。Rust 的借用检查器在编译期保证引用的生命周期不短于被引用值的生命周期，`drop` 后无法再使用引用。
13. **Rust 有 GC 吗？内存如何管理？** 没有 GC。内存通过所有权系统管理：值在所有者离开作用域时自动 `drop`（RAII），`Rc`/`Arc` 提供引用计数。编译期确定内存生命周期，无运行时开销。
14. **什么是 Drop trait？与 C++ 析构函数的区别？** `Drop` trait 在值离开作用域时自动调用 `drop(&mut self)`，用于释放资源。与 C++ 析构函数类似，但 Rust 的 drop 顺序确定（与创建顺序相反），且不允许手动调用 `drop`（需用 `std::mem::drop`）。

**并发与异步（15-22）**

15. `Send` 和 `Sync` trait 的作用？ `Send` 表示类型可以跨线程转移所有权；`Sync` 表示类型可以跨线程共享不可变引用（`&T` 是 `Send`）。编译器自动为满足条件的类型实现，`unsafe impl` 可手动实现。
16. **Rust 如何在编译期防止数据竞争？** 通过 `Send`/`Sync`：只有 `Send` 的类型可以跨线程移动，只有 `Sync` 的类型可以跨线程共享。`Mutex<T>` 要求 `T: Send`，`Arc<T>` 要求 `T: Sync + Send`。两个可变引用同时存在被借用检查器拒绝。
17. `std::sync::Mutex` 和 `tokio::sync::Mutex` 的区别？ 标准库 Mutex 是阻塞的（lock 会阻塞线程），不能在 async 中跨 `.await` 持有；tokio Mutex 是异步的（lock 返回 Future，不阻塞线程），可以跨 `.await` 持有，但有额外开销。
18. **什么是 async/await？Future trait 的核心是什么？** `async fn` 返回一个实现 `Future` 的状态机，`.await` 轮询 Future 直到就绪。`Future` trait 的核心是 `poll(self: Pin<&mut Self>, cx: &mut Context) -> Poll<T>`，运行时调用 poll 推进状态机，`Waker` 用于通知运行时再次轮询。
19. **什么是 Pin？为什么 async 需要 Pin？** `Pin<P>` 固定指针指向的值在内存中不移动。async 状态机包含自引用结构（跨 `.await` 的引用指向自身字段），如果状态机被移动，自引用会悬空。Pin 保证状态机在 poll 期间不被移动。
20. **tokio 的多线程和单线程运行时区别？** 多线程运行时（`#[tokio::main]` 默认）使用线程池，任务在多个 OS 线程上调度，适合 CPU 密集和高并发；单线程运行时（`current_thread`）所有任务在一个线程上运行，适合 IO 密集和低延迟场景，无锁竞争。
21. **什么是 tokio 的 work-stealing？** 多线程运行时中，每个线程有自己的任务队列。当一个线程的队列为空时，它会从其他线程的队列"偷"任务执行。这保证了负载均衡，避免某些线程空闲而其他线程过载。
22. **mpsc channel 的三种类型？** `unbounded`（无界，可能内存溢出）、`bounded`（有界，满时发送方 await 阻塞）、`oneshot`（一次性，发送单个值）。tokio 还提供 `watch`（多消费者最新值）、`broadcast`（多消费者广播）。

**工程与生态（23-30）**

23. **cargo 的 workspace 是什么？如何使用？** Workspace 允许多个 crate 共享同一个 `Cargo.lock` 和输出目录，适合大型项目。根目录 `Cargo.toml` 用 `[workspace]` 声明成员路径，子 crate 用 `[package]` 独立配置，依赖用 `path = "../xxx"` 或 workspace 继承。
24. **features 是什么？如何用于条件编译？** Features 是 Cargo 的条件编译机制，在 `Cargo.toml` 的 `[features]` 中定义，代码中用 `#[cfg(feature = "xxx")]` 条件编译。可选依赖自动成为 feature，`dep:xxx` 语法启用依赖而不创建 feature。
25. **thiserror 和 anyhow 的区别和使用场景？** `thiserror` 用于库的自定义错误类型（派生 `Error` trait，`#[error("...")]` 定义显示格式），提供结构化错误；`anyhow` 用于应用层，提供动态错误类型和 `.context()` 上下文链，不需要预定义错误枚举。库用 thiserror，应用用 anyhow。
26. **serde 的 Serialize/Deserialize 如何工作？** `serde` 是序列化/反序列化框架，`Serialize` trait 将值转为数据格式（JSON/TOML/等），`Deserialize` trait 从数据格式构造值。`derive` 宏自动为结构体生成实现，`#[serde(rename = "...")]`、`#[serde(default)]`、`#[serde(skip)]` 等属性控制行为。
27. **unsafe Rust 的使用场景和规则？** `unsafe` 用于：解引用裸指针、调用 unsafe 函数/外部函数、修改静态变量、实现 unsafe trait、访问 union 字段。unsafe 块内编译器不保证内存安全，开发者需手动保证不变量。原则：unsafe 块尽可能小，封装为安全 API，文档说明安全前提。
28. **什么是零成本抽象？举例说明。** 零成本抽象指高级语言特性在编译后不产生运行时开销。Rust 的例子：迭代器适配器（map/filter 编译为手写循环）、泛型单态化（每个具体类型生成专用代码，无虚函数开销）、trait 静态分发（impl Trait 编译为具体类型调用）、RAII（drop 编译为内联的资源释放代码）。
29. **Rust 的编译为什么慢？如何加速？** 慢的原因：泛型单态化（大量代码生成）、借用检查器（复杂的数据流分析）、LLVM 优化（Rust 依赖 LLVM，优化耗时）、增量编译不足。加速方法：`cargo check`（不生成二进制）、sccache（编译缓存）、`codegen-units = 256`（debug 模式并行编译）、减少泛型使用、用 `mold` 链接器、升级硬件。
30. **C++ 项目引入 Rust 的最佳实践？** 渐进式迁移：先建立 C ABI 边界，用 cxx/bindgen 做互操作，从边界清晰的模块开始重写，优先迁移新增功能和并发/安全敏感模块，保持 C++/Rust 长期共存，每个迭代可逆。避免大爆炸重写，用 FFI 边界通信，用 Rust 模块的单元测试保证质量。

## 7. 快速参考卡片

| 查询点 | 速答 |
| --- | --- |
| 选型六维 | 性能、内存安全、开发效率、生态成熟度、并发模型、岗位需求 |
| Rust 优势场景 | 新建基础设施（代理/存储/运行时）、需要记忆安全与并发安全、单二进制交付 |
| C++ 优势场景 | 存量代码库庞大、GPU/游戏/科学计算生态、极致可控的底层优化 |
| FFI 桥接 | C ABI 为界：`extern "C"` + `#[repr(C)]`；C++ 侧用 `cxx`/`autocxx`，Rust 侧用 `bindgen` |
| 渐进迁移四步 | ① 新模块用 Rust ② 叶子模块替换 ③ 边界清晰模块对齐 C ABI ④ 核心逐步下沉 |
| 学习五阶段 | 入门 → 所有权借用 → trait/泛型 → 并发 async → 工程化实战（详见下文路线表） |
| 练手项目 | 15 个阶梯项目：CLI → 解析器 → 网络服务 → 存储 → 并发 → FFI |
| 常见误区 | 为性能神话重写、忽略生态缺口、FFI 边界过细、只学语法不做项目 |
| 面试重点 | 所有权/借用、trait 与 dyn、Send/Sync、async 原理、unsafe 边界、与 C++ 差异 |
| 交叉对照 | 每个 Rust 概念在本库 01-C++技术体系 中都有对照篇，双线学习效率最高 |

---

## 8. 常见坑

### 坑 1：为"性能神话"提前重写

Rust 不保证比 C++ 快。边界检查、缺少成熟的高性能库、单态化体积膨胀都可能让迁移后更慢。先 profile，确认瓶颈确实来自语言层面（内存安全负担、GC 停顿、并发模型），再决定迁移范围。

### 坑 2：忽略生态缺口

桌面 GUI、图形渲染、科学计算、深度学习、部分行业 SDK 的 Rust 生态仍弱于 C++/Python。选型前先确认目标领域的**关键依赖**是否成熟（有无人维护、有无生产案例），否则会在中途被迫回退或自研。

### 坑 3：FFI 边界设计过细

把接口切得很碎（每次小操作跨语言调用）会放大调用开销与两边的 unsafe 面积。按批/按块设计：一次调用传输一批数据，边界上用 `repr(C)` 结构体或紧凑缓冲区。

### 坑 4：一次性大重写

C++ → Rust 的大仓重写风险极高（编译期约束、团队学习成本、回归验证）。推荐渐进路线：新功能用 Rust → 替换叶子模块 → 按 C ABI 对齐边界模块 → 最后评估核心迁移。

### 坑 5：用 unsafe 抄 C++ 习惯

遇到借用检查报错就加 `unsafe`，等于放弃了 Rust 的核心收益，还引入了比 C++ 更难审查的风险（因为不变量分散在文档里）。正确姿势：先重新设计所有权（用索引、拆分结构、`Rc/Arc`、arena），unsafe 只留给真正无法表达的场景。

### 坑 6：只学语法不写项目

所有权与生命周期靠肌肉记忆，读教程只能建立概念。按本库的 15 个阶梯项目实操，并把每个项目与 C++ 对照实现一遍，才能在面试中讲清"为什么这样设计"。

---

## 9. 本节小结

Rust 与 C++ 的选择不是非此即彼，而是根据场景权衡。C++ 在生态成熟度和存量代码上有优势，Rust 在内存安全、并发安全和开发效率（中长期）上有优势。两者性能同级，性能不是决定性因素。对于 C++ 开发者，Rust 的学习曲线集中在所有权和借用系统，一旦突破，C++ 的系统编程经验可以直接迁移。互操作通过 C ABI + cxx/bindgen 实现，渐进迁移是最务实的策略。学习路线分五阶段：入门 → 所有权 → trait → 并发 async → 工程化实战，配合 15 个阶梯项目和 30 道面试题，可以系统地建立 Rust 能力。

至此，Rust 技术体系的 06-领域方向与实战路线模块全部完成。从 CLI 工具到存储数据库，从区块链云原生到游戏图形 GUI，再到本篇的选型对照与学习路线，覆盖了 Rust 在各领域的核心应用。建议结合 C++ 技术体系的对应篇章对照学习，充分发挥「双语对照」的优势。

---

上一篇：《04-游戏图形与桌面GUI.md》　｜　模块索引：《../README.md》
