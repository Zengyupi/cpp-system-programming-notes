# 持续集成与crate发布

> 本节目标：掌握 Rust 工程化的最后一公里——从 cargo 命令全表到 build.rs 构建脚本，从 profile 优化到交叉编译，再到 GitHub Actions CI 模板与 crates.io 发布流程，建立完整的工程交付能力。

## 本章速览

- [1. cargo 命令全表](#1-cargo-命令全表)
  - [1.1 核心开发命令](#11-核心开发命令)
  - [1.2 分析与辅助命令](#12-分析与辅助命令)
- [2. build.rs 构建脚本](#2-buildrs-构建脚本)
  - [2.1 构建脚本的执行时机与输出](#21-构建脚本的执行时机与输出)
  - [2.2 典型应用：代码生成与环境探测](#22-典型应用代码生成与环境探测)
- [3. profile 与 release 体积优化](#3-profile-与-release-体积优化)
  - [3.1 profile 配置详解](#31-profile-配置详解)
  - [3.2 strip/LTO/UPX 体积优化](#32-stripltoupx-体积优化)
- [4. 交叉编译与 target](#4-交叉编译与-target)
  - [4.1 target 三元组与工具链安装](#41-target-三元组与工具链安装)
  - [4.2 cross 工具与 musl 静态链接](#42-cross-工具与-musl-静态链接)
- [5. GitHub Actions CI 模板](#5-github-actions-ci-模板)
  - [5.1 检查/测试/覆盖率流水线](#51-检查测试覆盖率流水线)
  - [5.2 多平台构建与发布](#52-多平台构建与发布)
- [6. crates.io 发布流程](#6-cratesio-发布流程)
  - [6.1 发布前检查与元数据](#61-发布前检查与元数据)
  - [6.2 语义化版本与 MSRV](#62-语义化版本与-msrv)
- [7. 常见坑与本节小结](#7-常见坑与本节小结)
  - [常见坑](#常见坑)
  - [本节小结](#本节小结)

---

## 1. cargo 命令全表

### 1.1 核心开发命令

cargo 是 Rust 的包管理器和构建系统，集依赖管理、编译、测试、发布于一体。与 C++ 中 CMake + Conan/vcpkg + 自定义脚本的组合相比，cargo 提供了统一的命令行入口。

| 命令 | 作用 | C++ 等价 |
|------|------|----------|
| `cargo new` | 创建新项目 | `cmake` 初始化 + 模板 |
| `cargo init` | 在已有目录初始化 | 手动创建 CMakeLists.txt |
| `cargo build` | 编译（debug） | `cmake --build` |
| `cargo build --release` | 编译（release） | `cmake --build --config Release` |
| `cargo run` | 编译并运行 | 编译后 `./target` |
| `cargo test` | 运行所有测试 | `ctest` + 测试框架 |
| `cargo check` | 类型检查（不生成二进制） | 无直接等价（快速语法检查） |
| `cargo clean` | 清理构建产物 | `make clean` |
| `cargo update` | 更新依赖到最新兼容版本 | `conan update` |
| `cargo add` | 添加依赖 | 手动编辑 CMakeLists + find_package |
| `cargo remove` | 移除依赖 | 手动编辑 |
| `cargo search` | 搜索 crate | `conan search` |
| `cargo doc` | 生成文档 | `doxygen` |
| `cargo doc --open` | 生成并在浏览器打开 | 生成后手动打开 |

`cargo check` 是 Rust 开发中最高频的命令——它只做类型检查和借用检查，不生成机器码，速度比 `cargo build` 快 3-5 倍。C++ 中没有直接等价物，最接近的是 `clang-check --ast-dump`，但远不如 `cargo check` 便捷。

### 1.2 分析与辅助命令

| 命令 | 作用 | 典型场景 |
|------|------|----------|
| `cargo tree` | 显示依赖树 | 排查依赖冲突、查找间接依赖 |
| `cargo tree -i <crate>` | 反向依赖树 | 查找谁依赖了某个 crate |
| `cargo tree --duplicates` | 显示重复版本 | 排查同一 crate 多版本共存 |
| `cargo audit` | 安全漏洞扫描 | CI 中检查已知 CVE |
| `cargo outdated` | 检查过时依赖 | 定期升级依赖 |
| `cargo clippy` | 代码 lint | 代码质量检查 |
| `cargo fmt` | 代码格式化 | 统一代码风格 |
| `cargo fix` | 自动修复警告 | 批量修复编译器建议 |
| `cargo expand` | 展开宏 | 调试宏展开结果 |
| `cargo metadata` | 输出项目元数据 JSON | 工具集成 |
| `cargo vendor` | 下载依赖到本地 | 离线构建、审计 |
| `cargo bench` | 运行基准测试 | 性能回归检测 |
| `cargo publish` | 发布到 crates.io | crate 发布 |

`cargo clippy` 是 Rust 的官方 linter，提供超过 700 条 lint 规则，涵盖性能、正确性、风格、复杂度等维度。C++ 中对应的是 Clang-Tidy，但 clippy 与 cargo 集成更紧密，且规则更新更活跃。

```bash
# 常用 clippy 配置
cargo clippy --all-targets --all-features -- -D warnings  # 所有警告视为错误
cargo clippy --fix --allow-dirty  # 自动修复可修复的 lint
```

## 2. build.rs 构建脚本

### 2.1 构建脚本的执行时机与输出

`build.rs` 是 crate 根目录下的可选构建脚本，在 crate 本身被编译之前编译并运行。它的典型用途包括：生成代码（如 Protobuf、bindgen）、探测系统库（如 `pkg-config`）、设置编译时环境变量、执行平台特定的配置。

`build.rs` 通过 `println!("cargo:{}", ...)` 格式的输出与 cargo 通信，cargo 解析这些指令并应用到构建过程：

| 指令 | 作用 |
|------|------|
| `cargo:rustc-link-lib=NAME` | 链接系统库 |
| `cargo:rustc-link-search=PATH` | 添加库搜索路径 |
| `cargo:rustc-cfg=KEY` | 设置 cfg 条件编译标志 |
| `cargo:rustc-env=VAR=VALUE` | 设置编译时环境变量（`env!` 宏读取） |
| `cargo:rerun-if-changed=PATH` | 指定文件变更时重新运行 build.rs |
| `cargo:rerun-if-env-changed=VAR` | 指定环境变量变更时重新运行 |
| `cargo:warning=MESSAGE` | 输出警告 |

### 2.2 典型应用：代码生成与环境探测

**示例一：Protobuf 代码生成（与 prost 配合）**

```rust
// build.rs
fn main() -> Result<(), Box<dyn std::error::Error>> {
    // 只在 proto 文件变更时重新运行
    println!("cargo:rerun-if-changed=proto/user.proto");
    println!("cargo:rerun-if-changed=proto/order.proto");

    // 使用 prost-build 编译 .proto 文件
    prost_build::compile_protos(
        &["proto/user.proto", "proto/order.proto"],
        &["proto/"],
    )?;

    Ok(())
}
```

**示例二：系统库探测与条件编译**

```rust
// build.rs
use std::env;

fn main() {
    // 探测操作系统
    let target_os = env::var("CARGO_CFG_TARGET_OS").unwrap();
    match target_os.as_str() {
        "linux" => {
            println!("cargo:rustc-cfg=os_linux");
            println!("cargo:rustc-link-lib=dylib=pthread");
        }
        "windows" => {
            println!("cargo:rustc-cfg=os_windows");
            println!("cargo:rustc-link-lib=dylib=ws2_32");
        }
        "macos" => {
            println!("cargo:rustc-cfg=os_macos");
        }
        _ => {}
    }

    // 设置编译时版本信息
    let version = env::var("CARGO_PKG_VERSION").unwrap();
    let git_hash = std::process::Command::new("git")
        .args(["rev-parse", "--short", "HEAD"])
        .output()
        .ok()
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .unwrap_or_else(|| "unknown".to_string());
    println!("cargo:rustc-env=GIT_HASH={}", git_hash.trim());
    println!("cargo:rustc-env=BUILD_VERSION={}", version);
}
```

```rust
// src/main.rs 中使用编译时环境变量
fn main() {
    println!("版本: {}", env!("BUILD_VERSION"));
    println!("Git: {}", env!("GIT_HASH"));

    #[cfg(os_linux)]
    println!("运行在 Linux 上");

    #[cfg(os_windows)]
    println!("运行在 Windows 上");
}
```

C++ 对照：C++ 中 build.rs 的功能通常分散在 CMake 的 `execute_process`、`configure_file`、`find_package` 和自定义 target 中。Rust 的 `build.rs` 将所有构建时逻辑收敛到一个文件，且通过 `cargo:` 指令与构建系统通信，机制更统一。但需要注意：`build.rs` 是在编译主机上运行的，交叉编译时不能假设目标平台的环境。

## 3. profile 与 release 体积优化

### 3.1 profile 配置详解

Cargo 通过 `[profile.*]` 段控制编译配置，内置四个 profile：`dev`（默认 debug）、`release`、`test`、`bench`。可以在 `Cargo.toml` 中覆盖默认值。

```toml
# Cargo.toml

# 开发配置：编译速度优先
[profile.dev]
opt-level = 0          # 0-3，0 无优化（最快编译），3 最大优化
debug = 1              # 0 无调试信息，1 限行号，2 完整调试信息
debug-assertions = true # 启用 debug_assert! 宏
overflow-checks = true  # 整数溢出检查（debug 默认开启）
incremental = true      # 增量编译
codegen-units = 256     # 并行编译单元数（越多编译越快，优化越差）

# 发布配置：运行性能和体积优先
[profile.release]
opt-level = 3
debug = false
debug-assertions = false
overflow-checks = false  # release 下溢出按二补码回绕（C++ 有符号溢出为 UB，无符号才回绕）
incremental = false
codegen-units = 1        # 单编译单元，最大化优化（但编译慢）
lto = false               # 链接时优化（false/"thin"/true）
panic = "unwind"          # panic 策略（"unwind"/"abort"）
strip = false             # 剥离符号（false/"symbols"/"debuginfo"）

# 自定义 profile：发布但保留调试信息（用于生产环境定位问题）
[profile.prod-debug]
inherits = "release"
debug = 1
strip = "debuginfo"  # 只剥离调试信息，保留符号表
```

关键参数说明：

- `opt-level = "s"` / `"z"`：优化体积而非速度，`"s"` 平衡体积和速度，`"z"` 极致压缩体积。
- `lto = "thin"`：薄 LTO，比 full LTO 快很多，性能损失通常小于 5%。
- `codegen-units = 1`：禁用并行编译单元，允许编译器跨模块内联，但编译时间显著增加。
- `panic = "abort"`：panic 时直接终止进程，不展开栈。可以减小二进制体积（移除展开逻辑），但 `should_panic` 测试无法工作。

### 3.2 strip/LTO/UPX 体积优化

Rust 编译出的二进制默认体积较大（静态链接标准库、包含 panic 展开逻辑等），通过以下组合可以将体积压缩到原来的 1/3 到 1/5：

```toml
# 最小体积配置
[profile.release]
opt-level = "z"        # 极致体积优化
lto = true              # full LTO
codegen-units = 1       # 单编译单元
panic = "abort"         # 移除展开逻辑
strip = "symbols"       # 剥离所有符号
```

优化效果对比（以一个简单 HTTP 服务器为例）：

| 配置 | 体积 | 说明 |
|------|------|------|
| 默认 debug | ~120 MB | 包含完整调试信息 |
| 默认 release | ~8 MB | 基础优化 |
| release + lto=thin | ~6 MB | 薄 LTO |
| release + lto=true + codegen-units=1 | ~4.5 MB | full LTO |
| 上述 + panic=abort + strip | ~2.5 MB | 最小体积 |
| 上述 + UPX 压缩 | ~1 MB | 运行时解压，启动略慢 |

UPX 是通用的可执行文件压缩工具，压缩后的二进制在运行时自动解压到内存。适合对体积极度敏感的场景（如嵌入式、容器镜像），但会增加启动时间，且某些杀毒软件可能误报。

```bash
# UPX 压缩（需要先安装 upx）
upx --best --lzma target/release/my_app
```

C++ 对照：C++ 二进制体积优化的手段类似（`-Os`/`-Oz`、`-flto`、`strip`、UPX），但 C++ 默认动态链接 libc 和 libstdc++，二进制本身较小。Rust 默认静态链接标准库，所以体积优化更重要。容器化部署时，Rust 静态链接的优势是可以使用 `scratch` 或 `distroless` 基础镜像，整体镜像体积可能反而小于 C++ 动态链接的镜像。

## 4. 交叉编译与 target

### 4.1 target 三元组与工具链安装

Rust 支持丰富的交叉编译目标，通过 `rustup target add` 安装目标标准库，然后 `cargo build --target <triple>` 即可交叉编译。

目标三元组格式：`<arch>-<vendor>-<os>-<env>`，常用目标：

| 三元组 | 目标平台 |
|--------|----------|
| `x86_64-unknown-linux-gnu` | Linux x86_64 (glibc) |
| `x86_64-unknown-linux-musl` | Linux x86_64 (musl，静态链接) |
| `aarch64-unknown-linux-gnu` | Linux ARM64 (glibc) |
| `aarch64-unknown-linux-musl` | Linux ARM64 (musl) |
| `x86_64-pc-windows-msvc` | Windows x86_64 (MSVC) |
| `x86_64-pc-windows-gnu` | Windows x86_64 (MinGW) |
| `aarch64-apple-darwin` | macOS ARM64 (Apple Silicon) |
| `x86_64-apple-darwin` | macOS x86_64 (Intel) |
| `wasm32-unknown-unknown` | WebAssembly (浏览器) |
| `wasm32-wasi` | WebAssembly (WASI) |
| `thumbv7em-none-eabihf` | ARM Cortex-M4 (裸机) |

```bash
# 安装目标标准库
rustup target add x86_64-unknown-linux-musl
rustup target add aarch64-unknown-linux-gnu

# 交叉编译
cargo build --release --target x86_64-unknown-linux-musl

# 产物位置
ls target/x86_64-unknown-linux-musl/release/my_app
```

纯 Rust 代码（不依赖系统 C 库）的交叉编译非常简单——只需安装 target 即可。但如果依赖了使用 C 扩展的 crate（如 `ring`、`openssl-sys`），则需要对应的 C 交叉编译工具链。

### 4.2 cross 工具与 musl 静态链接

对于需要 C 工具链的交叉编译，`cross` 是社区维护的工具，它使用 Docker 容器提供预配置的交叉编译环境，无需手动安装工具链。

```bash
# 安装 cross
cargo install cross --git https://github.com/cross-rs/cross

# 交叉编译（用法与 cargo 一致）
cross build --release --target aarch64-unknown-linux-gnu
cross test --target armv7-unknown-linux-gnueabihf
```

**musl 静态链接**是 Rust 交叉编译中最常用的技巧之一。musl 是一个轻量级 C 标准库，支持完全静态链接，生成的二进制不依赖系统 glibc，可以在任何 Linux 发行版上运行（包括 Alpine、scratch 容器）。

```bash
# 安装 musl 目标
rustup target add x86_64-unknown-linux-musl

# Linux 上需要安装 musl-tools（提供 musl-gcc 包装器）
# Ubuntu/Debian: sudo apt install musl-tools

# 编译完全静态链接的二进制
cargo build --release --target x86_64-unknown-linux-musl

# 验证：没有动态依赖
ldd target/x86_64-unknown-linux-musl/release/my_app
# 输出：not a dynamic executable
```

对于依赖 OpenSSL 的 crate，musl 静态链接需要额外配置（使用 `vendored` feature 让 OpenSSL 从源码编译并静态链接）：

```toml
# Cargo.toml
[dependencies]
openssl = { version = "0.10", features = ["vendored"] }
```

C++ 对照：C++ 交叉编译通常需要手动安装对应平台的工具链（如 `aarch64-linux-gnu-gcc`），配置 CMake 的 `CMAKE_TOOLCHAIN_FILE`，处理 sysroot 和依赖库路径。Rust 的 `rustup target add` + `cross` 大幅简化了这个过程，musl 静态链接更是一键生成可移植二进制。这是 Rust 工具链相比 C++ 的显著工程优势。

## 5. GitHub Actions CI 模板

### 5.1 检查/测试/覆盖率流水线

一个标准的 Rust 项目 CI 流水线包含：格式检查、clippy lint、测试、覆盖率。以下模板可直接使用：

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

env:
  CARGO_TERM_COLOR: always
  RUST_BACKTRACE: 1

jobs:
  check:
    name: Format & Clippy
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
        with:
          components: rustfmt, clippy
      - name: Format check
        run: cargo fmt --all -- --check
      - name: Clippy
        run: cargo clippy --all-targets --all-features -- -D warnings

  test:
    name: Test (${{ matrix.os }})
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
      - uses: Swatinem/rust-cache@v2  # 缓存 cargo 构建产物
      - name: Run tests
        run: cargo test --all-targets --all-features --verbose

  coverage:
    name: Code Coverage
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
        with:
          components: llvm-tools-preview
      - name: Install cargo-llvm-cov
        uses: taiki-e/install-action@cargo-llvm-cov
      - name: Generate coverage
        run: cargo llvm-cov --all-features --workspace --lcov --output-path lcov.info
      - name: Upload to Codecov
        uses: codecov/codecov-action@v4
        with:
          files: lcov.info
          fail_ci_if_error: true
```

关键组件说明：

- `dtolnay/rust-toolchain@stable`：安装 Rust 工具链，比 `actions-rs/toolchain` 更新更活跃。
- `Swatinem/rust-cache@v2`：缓存 `~/.cargo` 和 `target` 目录，将 CI 时间从 10 分钟缩短到 2-3 分钟。
- `taiki-e/install-action`：安装 cargo 子命令（如 `cargo-llvm-cov`），自动处理缓存。
- `cargo-llvm-cov`：基于 LLVM 原生覆盖率，跨平台支持好，比 tarpaulin 更稳定。

### 5.2 多平台构建与发布

Release 流水线在打 tag 时自动构建多平台二进制并发布到 GitHub Releases：

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    tags:
      - "v*"

jobs:
  build:
    name: Build ${{ matrix.target }}
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        include:
          - os: ubuntu-latest
            target: x86_64-unknown-linux-musl
          - os: ubuntu-latest
            target: aarch64-unknown-linux-musl
          - os: windows-latest
            target: x86_64-pc-windows-msvc
          - os: macos-latest
            target: aarch64-apple-darwin
          - os: macos-latest
            target: x86_64-apple-darwin
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
        with:
          targets: ${{ matrix.target }}
      - uses: Swatinem/rust-cache@v2
      - name: Build
        uses: taiki-e/upload-rust-binary-action@v1
        with:
          bin: my_app
          target: ${{ matrix.target }}
          tar: unix
          zip: windows
          token: ${{ secrets.GITHUB_TOKEN }}
```

`taiki-e/upload-rust-binary-action` 自动完成编译、打包（tar.gz/zip）、计算校验和、上传到 GitHub Releases 的全流程。C++ 中通常需要手动写脚本处理各平台的编译和打包，Rust 生态的 Action 大幅减少了 CI 配置代码。

## 6. crates.io 发布流程

### 6.1 发布前检查与元数据

发布 crate 到 crates.io 前，需要确保 `Cargo.toml` 包含完整的元数据：

```toml
[package]
name = "my-crate"
version = "0.1.0"
edition = "2021"
authors = ["Name <email@example.com>"]
description = "一句话描述 crate 的功能（必填，否则发布被拒）"
license = "MIT OR Apache-2.0"  # 或 license-file = "LICENSE"
repository = "https://github.com/user/my-crate"
homepage = "https://example.com"
documentation = "https://docs.rs/my-crate"
readme = "README.md"
keywords = ["networking", "async"]  # 最多 5 个
categories = ["network-programming", "asynchronous"]  # 必须是 crates.io 预定义分类
rust-version = "1.75"  # MSRV (Minimum Supported Rust Version)

# 排除不需要发布的文件
exclude = [
    "/.github",
    "/benches",
    "/examples",
    "*.log",
]

[dependencies]
# 依赖必须使用版本号，不能用 path/git 依赖（发布时会被拒绝）
serde = { version = "1", features = ["derive"] }
```

发布步骤：

```bash
# 1. 登录 crates.io（首次需要在 https://crates.io/me 生成 token）
cargo login <your-api-token>

# 2. 发布前检查（打包但不上传，验证内容）
cargo package --list   # 查看将包含的文件
cargo package          # 本地打包验证

# 3. 发布
cargo publish

# 4. 验证
cargo search my-crate
```

**重要限制**：crate 一旦发布就**不可删除**（只能用 `cargo yank` 标记为不推荐使用，但代码仍然保留）。版本号也不可复用——发布了 0.1.0 后，即使 yank 了也不能重新发布 0.1.0。这与 npm 的 unpublish 不同，crates.io 更强调不可变性。

### 6.2 语义化版本与 MSRV

Rust 生态严格遵循语义化版本（SemVer）：`MAJOR.MINOR.PATCH`

- **PATCH**（0.0.x → 0.0.x+1）：bug 修复，不改变公开 API
- **MINOR**（0.x.0 → 0.x+1.0）：新增功能，向后兼容
- **MAJOR**（x.0.0 → x+1.0.0）：不兼容的 API 变更

0.x 版本的特殊规则：`0.MINOR.PATCH` 中，MINOR 版本变更视为不兼容（等价于 MAJOR）。即 0.1.x 到 0.2.0 是 breaking change。

**MSRV（Minimum Supported Rust Version）** 是 crate 承诺支持的最低 Rust 版本，在 `Cargo.toml` 中通过 `rust-version` 字段声明。提升 MSRV 被视为 breaking change（需要递增 MINOR 或 MAJOR 版本），因为它可能破坏使用旧版 Rust 的用户。CI 中应添加 MSRV 检查：

```yaml
msrv:
  name: MSRV Check
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: dtolnay/rust-toolchain@1.75.0  # 与 Cargo.toml 中 rust-version 一致
    - uses: Swatinem/rust-cache@v2
    - run: cargo build --all-features
```

C++ 对照：C++ 库的版本管理通常没有统一标准，有的用 SemVer，有的用日期版本，有的用提交哈希。C++ 标准的版本（C++11/14/17/20/23）等价于 Rust 的 edition，但 C++ 编译器的向后兼容性比 Rust 差（新编译器可能拒绝旧代码）。crates.io 的不可变性和 SemVer 严格性是 Rust 生态质量保障的重要基础——依赖的 crate 不会突然消失或变更，`Cargo.lock` 确保了构建的可复现性。

## 7. 常见坑与本节小结

### 常见坑

1. **`cargo publish` 被拒：缺少 description 或 license**：crates.io 要求 `description` 和 `license`（或 `license-file`）必填。缺少任何一个都会被拒绝。
2. **依赖中包含 path/git 依赖导致发布失败**：发布到 crates.io 的 crate 不能依赖 `path = "..."` 或 `git = "..."` 的 crate，所有依赖必须来自 crates.io。发布前需将本地依赖改为版本号。
3. **`cargo package` 包含了意外文件**：默认会包含所有未被 `.gitignore` 排除的文件。使用 `exclude` 字段明确排除 CI 配置、测试文件、文档等。用 `cargo package --list` 检查。
4. **交叉编译时 build.rs 探测了错误的平台**：`build.rs` 在编译主机上运行，`std::env::consts::OS` 返回的是主机平台而非目标平台。应使用 `CARGO_CFG_TARGET_OS` 环境变量获取目标平台。
5. **musl 静态链接 + OpenSSL 编译失败**：`openssl-sys` 默认链接系统 OpenSSL，musl 环境下需要 `features = ["vendored"]` 从源码编译。或改用 `rustls`（纯 Rust TLS 实现，无此问题）。
6. **CI 缓存导致旧构建产物干扰**：`Swatinem/rust-cache` 默认缓存 `target` 目录，如果 `Cargo.toml` 变更但缓存 key 未更新，可能使用旧产物。清理缓存或在 CI 中定期 `cargo clean`。
7. **`cargo yank` 不能删除已发布版本**：yank 只是阻止新用户安装该版本，已下载的用户不受影响，代码仍然公开。如果发布了有严重安全问题的版本，需要发新版本修复并在 README 中公告。
8. **Windows 下交叉编译到 Linux 需要 Docker**：Windows 主机无法直接交叉编译到 Linux（缺少 C 工具链），使用 `cross`（基于 Docker）或在 WSL2 中编译。

### 本节小结

Rust 的工程化交付以 cargo 为统一入口，覆盖了从依赖管理、编译、测试、lint 到发布的全流程。`build.rs` 构建脚本处理代码生成和系统探测，通过 `cargo:` 指令与构建系统通信。profile 配置通过 `opt-level`、`lto`、`codegen-units`、`panic`、`strip` 的组合在编译速度、运行性能、二进制体积之间权衡，极致优化可将体积压缩到默认 release 的 1/3。交叉编译通过 `rustup target add` 一键安装标准库，`cross` 工具用 Docker 处理 C 工具链，musl 静态链接生成完全可移植的二进制。GitHub Actions CI 通过 `dtolnay/rust-toolchain`、`Swatinem/rust-cache`、`taiki-e/install-action` 等官方/社区 Action 实现格式检查、lint、测试、覆盖率、多平台发布的自动化。crates.io 发布要求完整元数据，遵循严格 SemVer，已发布版本不可删除（仅可 yank），MSRV 提升视为 breaking change。与 C++ 的 CMake + Conan + 自定义脚本体系相比，Rust 的工具链更统一、自动化程度更高，是 Rust 生态工程化优势的集中体现。

---

上一篇：《04-编译错误排查与调试.md》
