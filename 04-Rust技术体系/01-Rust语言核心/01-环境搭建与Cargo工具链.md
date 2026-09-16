# 环境搭建与 Cargo 工具链

> 本节目标：完成 Rust 开发环境的从零搭建，理解 rustup 工具链管理机制与 edition 演进，熟练掌握 Cargo 项目管理与常用命令，完成第一个 Rust 程序并逐行理解，建立与 C++ Make/CMake 体系的对照认知。

## 本章速览

- [1. rustup 与工具链管理](#1-rustup-与工具链管理)
  - [1.1 stable / beta / nightly 三通道](#11-stable--beta--nightly-三通道)
  - [1.2 target 与交叉编译](#12-target-与交叉编译)
  - [1.3 组件管理：rust-src / rustfmt / clippy / miri](#13-组件管理rust-src--rustfmt--clippy--miri)
- [2. Edition 演进：2015 → 2018 → 2021 → 2024](#2-edition-演进2015--2018--2021--2024)
- [3. Cargo 项目管理](#3-cargo-项目管理)
  - [3.1 cargo new 与项目结构](#31-cargo-new-与项目结构)
  - [3.2 Cargo.toml 完整示例](#32-cargotoml-完整示例)
  - [3.3 build / run / check / test / doc](#33-build--run--check--test--doc)
  - [3.4 fmt / clippy / fix](#34-fmt--clippy--fix)
  - [3.5 cargo 命令速查表](#35-cargo-命令速查表)
- [4. rust-analyzer 与 VSCode 配置](#4-rust-analyzer-与-vscode-配置)
- [5. 第一个程序逐行讲解](#5-第一个程序逐行讲解)
- [6. 对照 C++：Cargo vs Make / CMake](#6-对照-ccargo-vs-make--cmake)
- [7. 快速参考卡片](#7-快速参考卡片)
- [8. 常见坑与排错](#8-常见坑与排错)
  - [坑 1：Cargo.lock 是否提交？](#坑-1cargolock-是否提交)
  - [坑 2：依赖版本冲突](#坑-2依赖版本冲突)
  - [坑 3：编译慢](#坑-3编译慢)
  - [坑 4：nightly 特性在 stable 中不可用](#坑-4nightly-特性在-stable-中不可用)
  - [坑 5：`cargo run` 传参](#坑-5cargo-run-传参)
- [9. 本节小结](#9-本节小结)

---

## 1. rustup 与工具链管理

rustup 是 Rust 官方的工具链管理器，相当于 C++ 世界中手动管理多个 GCC/Clang 版本的自动化方案。它负责下载、切换、更新 Rust 编译器（rustc）、标准库和配套工具。

### 1.1 stable / beta / nightly 三通道

Rust 维护三条发布通道，对应不同的稳定性与新特性节奏：

| 通道 | 更新频率 | 特点 | 适用场景 |
|---|---|---|---|
| stable | 每 6 周 | 经过完整测试，API 稳定，生产环境首选 | 所有正式项目 |
| beta | 每 6 周 | stable 的预发布版本，用于发现回归问题 | 提前测试兼容性 |
| nightly | 每天 | 包含最新实验特性，可能 breaking change | 探索新特性、使用 unstable API |

```bash
# 安装最新 stable（默认）
rustup default stable

# 安装并切换到 nightly
rustup toolchain install nightly
rustup default nightly

# 仅对当前目录使用 nightly（生成 rust-toolchain.toml）
rustup override set nightly

# 查看已安装的工具链
rustup toolchain list

# 更新所有工具链
rustup update
```

> **对照 C++**：C++ 没有官方的多版本管理器，通常需要手动安装多个 GCC/Clang 并用 `CC`/`CXX` 环境变量或 CMake 工具链文件切换。rustup 将这一过程标准化，一条命令即可切换整个工具链。

### 1.2 target 与交叉编译

rustup 通过 target 管理不同平台的标准库，支持交叉编译：

```bash
# 查看已安装的 target
rustup target list --installed

# 添加 musl 静态链接目标（Linux 下生成完全静态二进制）
rustup target add x86_64-unknown-linux-musl

# 添加 Windows 交叉编译目标
rustup target add x86_64-pc-windows-gnu

# 交叉编译
cargo build --target x86_64-unknown-linux-musl --release
```

常见 target 三元组格式：`<arch>-<vendor>-<os>-<abi>`，如 `x86_64-pc-windows-msvc`、`aarch64-unknown-linux-gnu`、`thumbv7em-none-eabihf`（嵌入式）。

### 1.3 组件管理：rust-src / rustfmt / clippy / miri

rustup 将工具链拆分为可独立安装的组件：

```bash
# 查看可用组件
rustup component list

# 安装常用组件
rustup component add rust-src     # 标准库源码（IDE 跳转、no_std 开发）
rustup component add rustfmt      # 代码格式化工具
rustup component add clippy       # 静态分析/lint 工具
rustup component add miri         # 未定义行为检测（需 nightly）
```

| 组件 | 作用 | C++ 对应 |
|---|---|---|
| rust-src | 标准库源码，支持 IDE 跳转定义 | libstdc++ 源码包 |
| rustfmt | 官方代码格式化，统一风格 | clang-format |
| clippy | 超过 700 条 lint 规则的静态分析 | clang-tidy |
| miri | 解释执行检测未定义行为（UB） | valgrind / ASan（部分重叠） |

## 2. Edition 演进：2015 → 2018 → 2021 → 2024

Edition 是 Rust 独有的版本机制：**同一个编译器版本可以支持多个 edition，不同 edition 的代码可以在同一个项目中互相调用**。这解决了 C++ 中"标准升级导致旧代码编译失败"的痛点。

| Edition | 关键变化 |
|---|---|
| 2015 | 初始版本，模块系统基于 `extern crate`，`try!` 宏而非 `?` |
| 2018 | 路径系统简化（`use crate::`）、`?` 运算符、NLL、模块改进 |
| 2021 | `IntoIterator` for 数组、闭包捕获改进、`panic!` 一致性、reserved 语法 |
| 2024 | `unsafe` 属性细化、`gen` 关键字保留、`let-else` 改进、trait 升级、RPITIT 稳定 |

在 `Cargo.toml` 中指定 edition：

```toml
[package]
name = "my-project"
version = "0.1.0"
edition = "2021"  # 推荐使用最新稳定 edition
```

> **对照 C++**：C++ 通过 `-std=c++17/20/23` 编译器标志切换标准，但不同标准的代码不能无缝混合（ABI/头文件问题）。Rust 的 edition 机制保证了向后兼容的同时允许语言演进，是 Rust 工程化的重要设计。

## 3. Cargo 项目管理

Cargo 是 Rust 的官方构建系统与包管理器，集编译、依赖管理、测试、文档、发布于一体。对 C++ 程序员而言，Cargo 相当于 CMake + Conan/vcpkg + Make + CTest + Doxygen 的统一体。

### 3.1 cargo new 与项目结构

```bash
# 创建二进制项目
cargo new my_app

# 创建库项目
cargo new --lib my_lib

# 使用指定名称和 VCS
cargo new my_app --vcs git
```

生成的项目结构：

```text
my_app/
├── Cargo.toml          # 项目清单（依赖、元数据、构建配置）
├── Cargo.lock          # 依赖锁定文件（自动生成，二进制项目应提交）
├── src/
│   └── main.rs         # 二进制入口
└── .gitignore
```

库项目则是 `src/lib.rs`。大型项目可采用 workspace 结构：

```text
my_workspace/
├── Cargo.toml          # workspace 根清单
├── crates/
│   ├── core/           # 核心库
│   │   ├── Cargo.toml
│   │   └── src/lib.rs
│   └── app/            # 应用
│       ├── Cargo.toml
│       └── src/main.rs
└── Cargo.lock
```

### 3.2 Cargo.toml 完整示例

```toml
[package]
name = "my-app"
version = "0.1.0"
edition = "2021"
authors = ["Name <email@example.com>"]
description = "A sample Rust application"
license = "MIT OR Apache-2.0"
repository = "https://github.com/user/my-app"
readme = "README.md"
keywords = ["sample", "demo"]
categories = ["command-line-utilities"]

# 编译配置
[profile.dev]
opt-level = 0
debug = true
overflow-checks = true

[profile.release]
opt-level = 3
lto = true            # 链接时优化
codegen-units = 1     # 减少并行编译单元以换取更好优化
strip = true          # 剥离符号
panic = "abort"       # panic 时直接终止（减小体积）

# 依赖
[dependencies]
serde = { version = "1", features = ["derive"] }
tokio = { version = "1", features = ["full"] }
anyhow = "1"
thiserror = "1"

# 仅开发依赖（测试/示例/bench）
[dev-dependencies]
criterion = "0.5"

# 构建脚本依赖
[build-dependencies]
cc = "1"

# 平台特定依赖
[target.'cfg(unix)'.dependencies]
nix = "0.27"

[target.'cfg(windows)'.dependencies]
winapi = "0.3"

# workspace 声明（如果是 workspace 根）
[workspace]
members = ["crates/core", "crates/app"]
```

> 依赖版本号遵循语义化版本（SemVer）。`"1"` 等价于 `"^1.0.0"`，表示兼容 1.x.x；`"=1.2.3"` 锁定精确版本；`"~1.2"` 表示 >=1.2.0 且 <1.3.0。crate 版本以 crates.io 最新稳定版为准。

### 3.3 build / run / check / test / doc

```bash
# 编译（debug 模式，输出到 target/debug/）
cargo build

# 编译并运行
cargo run

# 仅类型检查，不生成二进制（最快的反馈循环）
cargo check

# 编译 release 版本（优化，输出到 target/release/）
cargo build --release

# 运行测试
cargo test

# 运行特定测试
cargo test test_name

# 生成文档（输出到 target/doc/）
cargo doc --open

# 清理构建产物
cargo clean
```

`cargo check` 是日常开发中最高频的命令——它只做前端编译（解析、类型检查、借用检查），跳过代码生成和链接，速度极快。C++ 中没有直接对应，最接近的是 `clang -fsyntax-only`，但 Cargo 的增量编译缓存使其反馈速度远超 C++ 构建系统。

### 3.4 fmt / clippy / fix

```bash
# 格式化所有源码
cargo fmt

# 检查格式但不修改（CI 中使用）
cargo fmt --check

# 运行 clippy 静态分析
cargo clippy

# clippy 自动修复可修复的问题
cargo clippy --fix

# cargo fix 自动修复编译器警告和 edition 迁移
cargo fix --edition
```

### 3.5 cargo 命令速查表

| 命令 | 作用 | 常用参数 |
|---|---|---|
| `cargo new` | 创建项目 | `--lib`, `--bin`, `--vcs` |
| `cargo init` | 在现有目录初始化 | `--lib`, `--bin` |
| `cargo build` | 编译 | `--release`, `--target`, `--workspace` |
| `cargo run` | 编译并运行 | `--release`, `-- arg1 arg2` |
| `cargo check` | 类型检查 | `--workspace`, `--all-targets` |
| `cargo test` | 运行测试 | `--release`, `-- test_filter`, `--nocapture` |
| `cargo bench` | 运行基准测试 | 需要 nightly 或 criterion |
| `cargo doc` | 生成文档 | `--open`, `--no-deps` |
| `cargo fmt` | 格式化代码 | `--check` |
| `cargo clippy` | 静态分析 | `--fix`, `-- -D warnings` |
| `cargo add` | 添加依赖 | `--features`, `--dev`, `--build` |
| `cargo remove` | 移除依赖 | |
| `cargo update` | 更新依赖 | `-p crate_name`, `--precise` |
| `cargo tree` | 查看依赖树 | `-i crate_name`, `--duplicates` |
| `cargo audit` | 安全漏洞扫描 | 需安装 cargo-audit |
| `cargo outdated` | 检查过时依赖 | 需安装 cargo-outdated |
| `cargo publish` | 发布到 crates.io | `--dry-run` |
| `cargo install` | 安装二进制 crate | `--locked` |

## 4. rust-analyzer 与 VSCode 配置

rust-analyzer 是 Rust 官方推荐的 LSP（Language Server Protocol）实现，提供代码补全、跳转定义、类型悬停、重命名、内联类型等功能。它取代了旧的 RLS（Rust Language Server）。

VSCode 配置（`.vscode/settings.json`）：

```json
{
  "rust-analyzer.cargo.features": "all",
  "rust-analyzer.check.command": "clippy",
  "rust-analyzer.checkOnSave": true,
  "rust-analyzer.inlayHints.typeHints.enable": true,
  "rust-analyzer.inlayHints.parameterHints.enable": true,
  "rust-analyzer.inlayHints.chainingHints.enable": true,
  "rust-analyzer.procMacro.enable": true,
  "rust-analyzer.cargo.buildScripts.enable": true,
  "[rust]": {
    "editor.formatOnSave": true,
    "editor.defaultFormatter": "rust-lang.rust-analyzer"
  }
}
```

关键功能对照 C++ IDE：

| rust-analyzer 功能 | C++ 对应（CLion / VSCode + clangd） |
|---|---|
| 类型悬停显示完整类型 | clangd 类型悬停 |
| 内联类型提示（inlay hints） | CLion 类型提示 |
| 跳转定义/实现 | Go to Definition |
| 查找所有引用 | Find Usages |
| 保存时自动 `cargo check` | 保存时编译（通常较慢） |
| 自动导入缺失的 use | 自动 include |
| 重命名符号 | Rename Symbol |

> rust-analyzer 的保存时检查基于 `cargo check` 的增量编译，通常在几百毫秒内完成。C++ IDE 的保存时编译往往需要数秒甚至数十秒，这是 Rust 开发体验的显著优势之一。

## 5. 第一个程序逐行讲解

`cargo new` 生成的 `src/main.rs`：

```rust
fn main() {
    println!("Hello, world!");
}
```

逐行解析：

1. **`fn main()`** — 定义程序入口函数。`fn` 是函数定义关键字（C++ 中是返回类型在前）。`main` 函数没有参数、没有返回类型（Rust 中省略返回类型等价于返回 `()`，即 C++ 的 `void`）。与 C++ 不同，Rust 的 `main` 不接受 `argc`/`argv`，命令行参数通过 `std::env::args()` 获取。

2. **`println!("Hello, world!");`** — 调用 `println!` 宏输出字符串并换行。注意 `!` 表示这是宏（macro）而非普通函数。宏在编译期展开，支持可变参数和编译期格式字符串检查。C++ 中 `std::cout << "Hello, world!" << std::endl;` 是函数调用，格式字符串在运行时解析。

3. **语句末尾的分号** — Rust 中语句（statement）以分号结尾，表达式（expression）不以分号结尾。`println!(...)` 是表达式，加分号后变为语句，丢弃其返回值（`()`）。这一区分是 Rust 表达式语言的基础，后续会详细讲解。

运行结果：

```text
$ cargo run
   Compiling my-app v0.1.0 (/path/to/my-app)
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 0.25s
     Running `target/debug/my-app`
Hello, world!
```

一个稍复杂的示例，展示 Rust 的基本语法元素：

```rust
use std::env;

fn main() {
    let name = env::args().nth(1).unwrap_or("world".to_string());
    let count = 3;

    for i in 1..=count {
        println!("{}. Hello, {}!", i, name);
    }
}
```

- `use std::env;` — 引入标准库的 `env` 模块（C++ 的 `#include` + `using`）
- `let name = ...` — 不可变变量绑定（C++ 的 `const auto`）
- `env::args().nth(1)` — 迭代器取第 2 个元素（索引从 0 开始），返回 `Option<String>`
- `.unwrap_or("world".to_string())` — Option 组合子，为 None 时提供默认值
- `1..=count` — 包含右端点的范围（1, 2, 3）；`1..count` 是左闭右开（1, 2）
- `println!("{}. Hello, {}!", i, name)` — 格式化输出，`{}` 是占位符，编译期检查参数数量

## 6. 对照 C++：Cargo vs Make / CMake

| 维度 | Cargo | CMake + Make | C++ 痛点 |
|---|---|---|---|
| 项目描述 | `Cargo.toml` 声明式 | `CMakeLists.txt` 命令式 | CMake 语法晦涩，调试困难 |
| 依赖管理 | 内置 crates.io，一行声明 | 需 Conan/vcpkg/FetchContent | C++ 无官方包管理器，依赖管理混乱 |
| 构建缓存 | 内置增量编译，scc 分布式缓存 | 需 ccache/sccache 额外配置 | 头文件改动导致全量重编译 |
| 测试 | `cargo test` 内置 | CTest + GoogleTest 框架 | 测试框架需手动集成 |
| 文档 | `cargo doc` 自动生成 API 文档 | Doxygen 额外配置 | 文档与代码分离，易过时 |
| 发布 | `cargo publish` 一键发布 | 无统一发布流程 | 库发布需手动处理版本、文档 |
| 交叉编译 | `--target` 一行 | 需编写 toolchain 文件 | 交叉编译配置复杂 |
| 格式化 | `cargo fmt` 官方统一 | clang-format 需配置 .clang-format | 团队风格不统一 |
| 静态分析 | `cargo clippy` 700+ 规则 | clang-tidy 需配置 | 规则配置复杂，误报多 |

> **核心差异**：C++ 的构建工具链是碎片化的（CMake/Make/Ninja/Bazel/Conan/vcpkg 各自为政），而 Cargo 是统一的、约定优于配置的。这使得 Rust 项目的上手成本远低于 C++ 项目——`git clone` 后 `cargo build` 几乎一定能成功，而 C++ 项目往往需要处理依赖安装、CMake 版本、编译器兼容性等一系列问题。

## 7. 快速参考卡片

| 需求 | 命令 |
| --- | --- |
| 安装/更新 | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh`；`rustup update` |
| 切换工具链 | `rustup toolchain install nightly`；`rustup override set nightly` |
| 组件 | `rustup component add rustfmt clippy rust-src` |
| 新建项目 | `cargo new app`（bin）/ `cargo new --lib mylib` |
| 构建运行 | `cargo build [--release]`；`cargo run`；`cargo check`（最快类型检查） |
| 测试格式 | `cargo test`；`cargo fmt`；`cargo clippy -- -D warnings` |
| 依赖管理 | `cargo add serde --features derive`；`cargo tree`；`cargo update` |
| 文档 | `cargo doc --open`；`///`（项）/ `//!`（模块） |
| 交叉编译 | `rustup target add x86_64-unknown-linux-musl`；`cargo build --target ...` |
| 常见坑 | 未设 `edition` 默认为 2015；target/debug 与 release 混跑；新 shell 未 `source ~/.cargo/env` |

---

## 8. 常见坑与排错

### 坑 1：Cargo.lock 是否提交？

- **二进制项目**：必须提交 `Cargo.lock`，保证团队和 CI 环境使用完全相同的依赖版本。
- **库项目**：不提交 `Cargo.lock`，让下游使用者自行解析依赖版本，避免版本锁定冲突。

### 坑 2：依赖版本冲突

当多个依赖引入同一 crate 的不同大版本时，Cargo 会同时编译多个版本（这是允许的），但如果 crate 类型不兼容（如不同版本的 trait），会导致编译错误。使用 `cargo tree -d` 查看重复依赖，考虑统一版本或使用 `cargo update -p crate_name --precise version`。

### 坑 3：编译慢

- 日常开发用 `cargo check` 而非 `cargo build`
- 使用 `sccache` 做分布式编译缓存
- release 模式下 `codegen-units = 1` 会显著减慢编译但提升优化，开发时可去掉
- 考虑用 `mold` 链接器（Linux）加速链接

### 坑 4：nightly 特性在 stable 中不可用

如果代码使用了 `#![feature(...)]`，必须使用 nightly 工具链。在项目根目录创建 `rust-toolchain.toml` 固定工具链：

```toml
[toolchain]
channel = "nightly"
components = ["rust-src", "clippy", "rustfmt"]
```

### 坑 5：`cargo run` 传参

`cargo run -- arg1 arg2`，`--` 分隔 cargo 参数和程序参数。忘记 `--` 会导致参数被 cargo 解析而非传递给程序。

## 9. 本节小结

- rustup 是 Rust 工具链管理器，支持 stable/beta/nightly 三通道和多 target 交叉编译，组件化管理 rust-src/rustfmt/clippy/miri。
- Edition 机制允许同一编译器支持多语言版本，不同 edition 代码可互操作，解决了 C++ 标准升级的破坏性问题。
- Cargo 是统一的构建+包管理+测试+文档工具，`Cargo.toml` 声明项目配置，`cargo check` 是最高频的快速反馈命令。
- rust-analyzer 提供强大的 IDE 支持，保存时 `cargo check` 的增量编译反馈速度远超 C++ IDE。
- 第一个程序展示了 `fn`、`let`、`println!` 宏、迭代器、Option 组合子等基础元素。
- Cargo 相比 CMake+Make+Conan 的碎片化工具链，在依赖管理、构建缓存、测试、文档、发布等方面提供了统一且高效的解决方案。

---

下一篇：《02-基础语法与类型系统.md》　｜　模块索引：《../README.md》
