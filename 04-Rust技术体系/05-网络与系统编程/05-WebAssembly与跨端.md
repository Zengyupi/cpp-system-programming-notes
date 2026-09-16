# WebAssembly 与跨端

> 本节目标：掌握 Rust WebAssembly 技术栈的完整能力——从 wasm32 目标到 wasm-bindgen 互操作，从 trunk 构建到 WASI 服务端，从包体优化到典型跨端场景，建立 Rust 作为 WASM 首选语言的工程化认知。

## 本章速览

- [1. wasm32 目标与 Rust WASM 生态总览](#1-wasm32-目标与-rust-wasm-生态总览)
  - [1.1 wasm32-unknown-unknown 与 wasm32-wasi](#11-wasm32-unknown-unknown-与-wasm32-wasi)
  - [1.2 Rust 为何是 WASM 首选语言](#12-rust-为何是-wasm-首选语言)
- [2. wasm-bindgen：Rust 与 JS 互操作](#2-wasm-bindgenrust-与-js-互操作)
  - [2.1 #\[wasm_bindgen\] 属性与函数导出](#21-wasm_bindgen-属性与函数导出)
  - [2.2 结构体与方法导出](#22-结构体与方法导出)
- [3. js-sys 与 web-sys：浏览器 API 绑定](#3-js-sys-与-web-sys浏览器-api-绑定)
  - [3.1 js-sys：JavaScript 标准库类型](#31-js-sysjavascript-标准库类型)
  - [3.2 web-sys：Web API 全量绑定](#32-web-sysweb-api-全量绑定)
- [4. trunk 构建与前端集成](#4-trunk-构建与前端集成)
  - [4.1 trunk 配置与构建流程](#41-trunk-配置与构建流程)
  - [4.2 与 JS 框架集成（React/Vue）](#42-与-js-框架集成reactvue)
- [5. WASI 与服务端 WebAssembly](#5-wasi-与服务端-webassembly)
  - [5.1 wasm32-wasi 目标与能力](#51-wasm32-wasi-目标与能力)
  - [5.2 wasmtime 运行时与服务端场景](#52-wasmtime-运行时与服务端场景)
- [6. 包体优化与性能分析](#6-包体优化与性能分析)
  - [6.1 wasm-opt 与包体积压缩](#61-wasm-opt-与包体积压缩)
  - [6.2 性能分析与基准对比](#62-性能分析与基准对比)
- [7. 典型跨端场景与限制](#7-典型跨端场景与限制)
  - [7.1 计算密集型前端、游戏引擎、插件系统](#71-计算密集型前端游戏引擎插件系统)
  - [7.2 当前限制与未来方向](#72-当前限制与未来方向)
- [8. 快速参考卡片](#8-快速参考卡片)
- [9. 常见坑与本节小结](#9-常见坑与本节小结)
  - [常见坑](#常见坑)
  - [本节小结](#本节小结)

---

## 1. wasm32 目标与 Rust WASM 生态总览

### 1.1 wasm32-unknown-unknown 与 wasm32-wasi

Rust 支持两个主要的 WebAssembly 编译目标，适用于不同场景：

| 目标 | 环境 | 标准库支持 | 典型用途 |
|------|------|-----------|----------|
| `wasm32-unknown-unknown` | 浏览器 / Node.js | `core` + `alloc`（无 `std` 的 OS 部分） | 前端计算、游戏、UI 组件 |
| `wasm32-wasi` | WASI 运行时（wasmtime、WasmEdge 等） | 完整 `std`（文件、网络、环境变量） | 服务端插件、边缘计算、沙箱执行 |

`wasm32-unknown-unknown` 中 `std` 的 OS 相关功能（文件系统、网络、线程、进程）不可用，因为浏览器环境没有这些能力。但 `core` 和 `alloc` 完全可用，`Vec`、`String`、`HashMap` 等集合类型正常工作。

```bash
# 安装 wasm32 目标
rustup target add wasm32-unknown-unknown
rustup target add wasm32-wasi

# 编译为浏览器 WASM
cargo build --target wasm32-unknown-unknown --release

# 编译为 WASI WASM
cargo build --target wasm32-wasi --release
```

编译产物位于 `target/wasm32-unknown-unknown/release/*.wasm`。但直接使用原始 `.wasm` 文件比较麻烦——需要手动处理 JS 胶水代码、内存管理、类型转换。`wasm-bindgen` 工具自动生成这些胶水代码。

### 1.2 Rust 为何是 WASM 首选语言

WebAssembly 的设计目标是"接近原生性能的安全沙箱执行"，Rust 与 WASM 的契合度极高：

| 特性 | Rust 优势 | C/C++ 对比 |
|------|-----------|-----------|
| 无 GC | 没有垃圾回收暂停，性能可预测 | C/C++ 也无 GC，但有手动内存管理风险 |
| 小体积 | 默认无运行时，`wasm-opt` 后可到几十 KB | C/C++ 需要 Emscripten 运行时，体积较大 |
| 内存安全 | 所有权系统消除内存错误 | C/C++ 需 AddressSanitizer 检测 |
| 工具链 | `wasm-bindgen` + `trunk` 一键构建 | Emscripten 配置复杂 |
| 生态 | `web-sys` 全量 Web API 绑定 | 需手动编写 JS 绑定 |
| 异步支持 | `wasm-bindgen-futures` 桥接 JS Promise | 需手动处理异步 |

Rust 编译为 WASM 的代码体积通常比 C/C++ + Emscripten 小 30%-50%，因为 Rust 不需要 Emscripten 的 libc 兼容层和 JS 运行时。且 `wasm-bindgen` 生成的胶水代码高度优化，类型转换开销最小化。

C++ 对照：C++ 编译为 WASM 主要通过 Emscripten（基于 LLVM），它提供了完整的 POSIX 兼容层（`libc`、`SDL`、`OpenGL` 等），适合将现有 C++ 游戏引擎移植到浏览器。但 Emscripten 的运行时体积大（最小约 100KB），且 JS 互操作需要手写 `EM_JS` 或 `embind`。Rust 的 `wasm-bindgen` + `web-sys` 提供了更现代、更类型安全的互操作方案，适合新项目。

## 2. wasm-bindgen：Rust 与 JS 互操作

### 2.1 #[wasm_bindgen] 属性与函数导出

`wasm-bindgen` 是 Rust WASM 生态的核心工具，它通过 `#[wasm_bindgen]` 属性标记需要导出到 JS 的函数和结构体，自动生成 JS 胶水代码，处理 Rust 类型与 JS 类型的转换。

```toml
# Cargo.toml
[lib]
crate-type = ["cdylib"]  # 编译为动态库（WASM 格式）

[dependencies]
wasm-bindgen = "0.2"
```

```rust
// src/lib.rs
use wasm_bindgen::prelude::*;

/// 导出简单函数：Rust 函数可在 JS 中直接调用
#[wasm_bindgen]
pub fn greet(name: &str) -> String {
    format!("Hello, {}! 来自 Rust WASM", name)
}

/// 数值计算：斐波那契数列
#[wasm_bindgen]
pub fn fibonacci(n: u32) -> u64 {
    match n {
        0 => 1,
        1 => 1,
        _ => fibonacci(n - 1) + fibonacci(n - 2),
    }
}

/// 接收 JS 回调：Rust 调用 JS 函数
#[wasm_bindgen]
pub fn process_data(data: &[u8], callback: &js_sys::Function) -> Result<(), JsValue> {
    let sum: u32 = data.iter().map(|&x| x as u32).sum();
    // 调用 JS 回调，this 设为 null
    callback.call1(&JsValue::NULL, &JsValue::from(sum))?;
    Ok(())
}

/// 返回 Result：错误自动转换为 JS 异常
#[wasm_bindgen]
pub fn divide(a: f64, b: f64) -> Result<f64, JsValue> {
    if b == 0.0 {
        Err(JsValue::from_str("除数不能为零"))
    } else {
        Ok(a / b)
    }
}
```

使用 `wasm-bindgen-cli` 生成 JS 胶水代码：

```bash
# 安装 wasm-bindgen CLI
cargo install wasm-bindgen-cli

# 生成 JS 绑定（输出到 pkg/ 目录）
wasm-bindgen target/wasm32-unknown-unknown/release/my_wasm.wasm --out-dir pkg

# 生成的文件：
# pkg/my_wasm.js          - JS 胶水代码
# pkg/my_wasm.d.ts        - TypeScript 类型声明
# pkg/my_wasm_bg.wasm     - 实际 WASM 二进制
```

JS 中调用：

```javascript
// JS 端调用
import init, { greet, fibonacci, divide } from './pkg/my_wasm.js';

async function main() {
    await init(); // 初始化 WASM 模块

    console.log(greet('World'));       // "Hello, World! 来自 Rust WASM"
    console.log(fibonacci(20));         // 10946

    try {
        console.log(divide(10, 0));
    } catch (e) {
        console.error(e);               // "除数不能为零"
    }
}
main();
```

`#[wasm_bindgen]` 自动处理的类型转换：

| Rust 类型 | JS 类型 |
|-----------|---------|
| `u8`/`u16`/`u32`/`i8`/`i16`/`i32` | `number` |
| `u64`/`i64` | `BigInt`（需 `--target web` 或启用 bigint） |
| `f32`/`f64` | `number` |
| `bool` | `boolean` |
| `&str`/`String` | `string` |
| `&[u8]`/`Vec<u8>` | `Uint8Array` |
| `Result<T, E>` | `T` / 抛出异常 |
| `JsValue` | 任意 JS 值 |

### 2.2 结构体与方法导出

结构体可以通过 `#[wasm_bindgen]` 导出为 JS 类，方法自动成为类方法：

```rust
use wasm_bindgen::prelude::*;

#[wasm_bindgen]
pub struct Calculator {
    value: f64,
}

#[wasm_bindgen]
impl Calculator {
    /// 构造函数：JS 中 `new Calculator(10)`
    #[wasm_bindgen(constructor)]
    pub fn new(initial: f64) -> Calculator {
        Calculator { value: initial }
    }

    /// getter：JS 中 `calc.value`
    #[wasm_bindgen(getter)]
    pub fn value(&self) -> f64 {
        self.value
    }

    /// setter：JS 中 `calc.value = 20`
    #[wasm_bindgen(setter)]
    pub fn set_value(&mut self, value: f64) {
        self.value = value;
    }

    /// 方法：JS 中 `calc.add(5)`
    pub fn add(&mut self, x: f64) {
        self.value += x;
    }

    pub fn multiply(&mut self, x: f64) {
        self.value *= x;
    }

    /// 静态方法：JS 中 `Calculator.fromString("3.14")`
    #[wasm_bindgen(static_method_of = Calculator)]
    pub fn from_string(s: &str) -> Option<Calculator> {
        s.parse().ok().map(|value| Calculator { value })
    }
}
```

JS 中使用：

```javascript
import init, { Calculator } from './pkg/my_wasm.js';

await init();

const calc = new Calculator(10);
calc.add(5);
console.log(calc.value);      // 15
calc.multiply(2);
console.log(calc.value);      // 30
calc.value = 100;             // setter
console.log(calc.value);      // 100

const calc2 = Calculator.fromString("3.14");
console.log(calc2.value);     // 3.14
```

结构体导出到 JS 后，Rust 的所有权规则仍然适用——JS 持有的是 Rust 结构体的指针（通过 `Box` 管理），当 JS 对象被垃圾回收时，`wasm-bindgen` 自动调用 Rust 的析构函数释放内存。这避免了 C++ + Emscripten 中常见的"忘记 `delete` 导致内存泄漏"问题。

C++ 对照：C++ 类导出到 JS 通过 Emscripten 的 `embind`（`EMSCRIPTEN_BINDINGS` 块），需要手动声明构造函数、方法、属性，且内存管理需要手动 `Module.destroy()` 或使用 `onRuntimeInitialized` 回调。Rust 的 `#[wasm_bindgen]` 属性更简洁，自动生成 TypeScript 类型声明，且内存管理自动化。

## 3. js-sys 与 web-sys：浏览器 API 绑定

### 3.1 js-sys：JavaScript 标准库类型

`js-sys` crate 提供了 JavaScript 标准库（ECMAScript）类型的 Rust 绑定，包括 `Object`、`Array`、`Map`、`Set`、`Promise`、`JSON`、`Math`、`Date` 等。这些绑定是零成本的——它们只是对 JS 值的引用，没有额外开销。

```toml
# Cargo.toml
[dependencies]
js-sys = "0.3"
wasm-bindgen = "0.2"
```

```rust
use wasm_bindgen::prelude::*;
use js_sys::{Array, Map, Set, Promise, JSON, Math, Date};

#[wasm_bindgen]
pub fn js_std_demo() -> Result<(), JsValue> {
    // Array 操作
    let array = Array::new();
    array.push(&JsValue::from(1));
    array.push(&JsValue::from(2));
    array.push(&JsValue::from(3));
    console_log(&format!("数组长度: {}", array.length()));

    // Map 操作
    let map = Map::new();
    map.set(&JsValue::from("key"), &JsValue::from("value"));
    console_log(&format!("Map 值: {:?}", map.get(&JsValue::from("key"))));

    // Set 操作
    let set = Set::new(&JsValue::undefined());
    set.add(&JsValue::from(1));
    set.add(&JsValue::from(1)); // 重复，自动去重
    console_log(&format!("Set 大小: {}", set.size()));

    // JSON 序列化/反序列化
    let obj = JSON::parse(r#"{"name":"Alice","age":30}"#)?;
    let json_str = JSON::stringify(&obj)?;
    console_log(&format!("JSON: {}", json_str.as_string().unwrap()));

    // Math
    let max = Math::max(&JsValue::from(3), &JsValue::from(7));
    console_log(&format!("max(3,7) = {:?}", max.as_f64()));

    // Date
    let now = Date::new_0();
    console_log(&format!("当前时间: {}", now.to_iso_string().as_string().unwrap()));

    Ok(())
}

// 辅助函数：调用 console.log
#[wasm_bindgen]
extern "C" {
    #[wasm_bindgen(js_namespace = console)]
    fn log(s: &str);
}
fn console_log(s: &str) { log(s); }
```

`js-sys` 的类型都实现了 `AsRef<JsValue>` 和 `From<T> for JsValue`，可以在需要 `JsValue` 的地方自由转换。`Promise` 类型可以通过 `wasm-bindgen-futures` 与 Rust 的 `Future` 互相转换。

### 3.2 web-sys：Web API 全量绑定

`web-sys` crate 提供了所有 Web API 的 Rust 绑定，包括 DOM、Canvas、WebGL、Fetch、WebSocket、Web Audio、WebRTC、IndexedDB 等。覆盖范围超过 1000 个 API，是 Rust 前端开发的基础。

`web-sys` 默认不启用任何 API（因为全量启用会大幅增加编译时间和包体积），需要通过 feature 显式启用：

```toml
# Cargo.toml
[dependencies]
web-sys = { version = "0.3", features = [
    "Document",
    "Window",
    "Element",
    "HtmlElement",
    "Node",
    "Console",
    "CanvasRenderingContext2d",
    "HtmlCanvasElement",
    "Request",
    "Response",
    "Headers",
    "WebSocket",
] }
```

```rust
use wasm_bindgen::prelude::*;
use web_sys::{Document, Window, console};

#[wasm_bindgen(start)]
pub fn main() -> Result<(), JsValue> {
    // 获取 window 和 document
    let window = web_sys::window().ok_or("no window")?;
    let document = window.document().ok_or("no document")?;

    // 创建 div 元素
    let div = document.create_element("div")?;
    div.set_inner_html("<h1>来自 Rust WASM 的问候</h1>");
    div.set_attribute("style", "color: blue; font-family: sans-serif;")?;

    // 添加到 body
    document.body()
        .ok_or("no body")?
        .append_child(&div)?;

    // Canvas 绘图
    let canvas = document.create_element("canvas")?
        .dyn_into::<web_sys::HtmlCanvasElement>()?;
    canvas.set_width(400);
    canvas.set_height(200);
    document.body().unwrap().append_child(&canvas)?;

    let context = canvas
        .get_context("2d")?
        .ok_or("no 2d context")?
        .dyn_into::<web_sys::CanvasRenderingContext2d>()?;

    context.set_fill_style(&JsValue::from("red"));
    context.fill_rect(10.0, 10.0, 100.0, 80.0);
    context.set_fill_style(&JsValue::from("black"));
    context.set_font("20px sans-serif");
    context.fill_text("Rust + Canvas", 10.0, 120.0)?;

    console::log_1(&JsValue::from("WASM 初始化完成"));
    Ok(())
}
```

`#[wasm_bindgen(start)]` 标记的函数会在 WASM 模块加载后自动执行，等价于 JS 的 `DOMContentLoaded` 事件处理。`web-sys` 的 API 设计严格遵循 Web 标准——方法名、参数顺序与 JS API 一致，只是类型化为 Rust。例如 `document.createElement("div")` 在 Rust 中是 `document.create_element("div")?`，返回 `Result<Element, JsValue>`（`?` 处理 JS 异常）。

C++ 对照：C++ 操作 DOM 通过 Emscripten 的 `emscripten.h`（`EM_ASM` 内联 JS）或 `embind`（`val` 类），代码风格是"在 C++ 中写 JS 字符串"，缺乏类型安全。Rust 的 `web-sys` 提供了全量类型安全的 Web API 绑定，方法名和参数类型在编译期检查，拼写错误或类型错误会编译失败而非运行时崩溃。这是 Rust 前端开发相比 C++ 的核心优势。

## 4. trunk 构建与前端集成

### 4.1 trunk 配置与构建流程

`trunk` 是 Rust WASM 的标准构建工具，类似于前端的 webpack/Vite。它自动处理：编译 Rust 为 WASM、运行 `wasm-bindgen` 生成胶水代码、复制静态资源、内联 JS/CSS、启动开发服务器（热重载）、生产构建优化。

```bash
# 安装 trunk
cargo install trunk
```

```toml
# Cargo.toml
[lib]
crate-type = ["cdylib"]

[dependencies]
wasm-bindgen = "0.2"
web-sys = { version = "0.3", features = ["Document", "Window", "Element", "Console"] }
```

```html
<!-- index.html - trunk 的入口文件 -->
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>Rust WASM 应用</title>
    <link data-trunk rel="css" href="style.css" />
    <link data-trunk rel="copy-file" href="favicon.ico" />
</head>
<body>
    <div id="app"></div>
    <!-- trunk 自动注入 WASM 加载脚本 -->
</body>
</html>
```

```toml
# Trunk.toml - 可选的 trunk 配置文件
[build]
target = "index.html"
dist = "dist"

[tools]
wasm-opt = "version >= 114"

[[proxy]]
# 开发服务器代理 API 请求到后端
backend = "http://localhost:8080/api"
```

常用命令：

```bash
# 开发模式：启动开发服务器，支持热重载
trunk serve

# 指定端口
trunk serve --port 3000

# 生产构建：优化 WASM 体积，输出到 dist/
trunk build --release

# 清理构建产物
trunk clean
```

`trunk serve` 启动的开发服务器支持**热重载**——修改 Rust 代码后自动重新编译并刷新浏览器。编译增量缓存使得修改后的重新编译通常在 1-3 秒内完成，开发体验接近 JS 框架的 HMR。

### 4.2 与 JS 框架集成（React/Vue）

Rust WASM 不需要完全替代 JS 框架，可以作为计算密集型模块嵌入 React/Vue 应用。`wasm-bindgen` 生成的 ES Module 可以直接被 JS 框架导入：

```javascript
// React 组件中使用 Rust WASM
import { useState, useEffect } from 'react';
import init, { fibonacci, process_image } from './pkg/my_wasm.js';

function FibonacciCalculator() {
    const [wasm, setWasm] = useState(null);
    const [result, setResult] = useState(null);

    useEffect(() => {
        // 初始化 WASM（异步）
        init().then(() => setWasm(true));
    }, []);

    const handleCalculate = (n) => {
        // 调用 Rust 函数
        const start = performance.now();
        const value = fibonacci(n);
        const elapsed = performance.now() - start;
        setResult({ value, elapsed });
    };

    if (!wasm) return <div>加载 WASM 中...</div>;

    return (
        <div>
            <button onClick={() => handleCalculate(40)}>
                计算 fibonacci(40)
            </button>
            {result && (
                <p>结果: {result.value}，耗时: {result.elapsed.toFixed(2)}ms</p>
            )}
        </div>
    );
}
```

对于更复杂的集成（如 Rust 实现完整的前端 UI），可以使用 `yew`（Rust 的 React -like 框架，基于 `web-sys`）或 `Leptos`（细粒度响应式框架）。这些框架允许完全用 Rust 编写前端应用，组件、状态管理、路由都在 Rust 中完成。

```toml
# Yew 框架示例依赖
[dependencies]
yew = { version = "0.21", features = ["csr"] }
wasm-bindgen = "0.2"
web-sys = { version = "0.3", features = ["Document", "Window", "Element", "Node"] }
```

```rust
// Yew 组件示例
use yew::prelude::*;

#[function_component(App)]
fn app() -> Html {
    let counter = use_state(|| 0);
    let onclick = {
        let counter = counter.clone();
        Callback::from(move |_| counter.set(*counter + 1))
    };

    html! {
        <div style="font-family: sans-serif; padding: 20px;">
            <h1>{ "Yew + Rust WASM" }</h1>
            <p>{ "计数器: " }{ *counter }</p>
            <button {onclick}>{ "增加" }</button>
        </div>
    }
}

fn main() {
    yew::Renderer::<App>::new().render();
}
```

C++ 对照：C++ 前端框架（如 asm-dom、magnum）生态较小，与 React/Vue 的集成需要手动编写 Emscripten 绑定。Rust 的 `wasm-bindgen` 生成标准 ES Module，可以直接被任何 JS 构建工具（webpack、Vite、Rollup）导入，且 `yew`/`Leptos` 等纯 Rust 前端框架正在快速成熟。Rust 在"JS 框架 + WASM 计算模块"的混合模式下集成最顺畅。

## 5. WASI 与服务端 WebAssembly

### 5.1 wasm32-wasi 目标与能力

WASI（WebAssembly System Interface）是 WebAssembly 的系统接口标准，为 WASM 模块提供了类似 POSIX 的 API（文件系统、网络、环境变量、时钟、随机数），使得 WASM 可以在浏览器之外的服务端环境运行。

`wasm32-wasi` 目标支持完整的 Rust `std`——`std::fs`、`std::net`、`std::env`、`std::time` 都可以使用。这与 `wasm32-unknown-unknown`（无 OS API）形成对比。

```rust
// src/main.rs - WASI 程序
use std::fs;
use std::io::{Read, Write};
use std::net::TcpStream;

fn main() -> std::io::Result<()> {
    // 读取环境变量
    if let Ok(path) = std::env::var("CONFIG_PATH") {
        println!("配置路径: {}", path);
    }

    // 文件操作
    let content = fs::read_to_string("/data/input.txt")?;
    println!("文件内容: {}", content);

    // 网络操作（WASI 预览版 2 支持 sockets）
    // let mut stream = TcpStream::connect("example.com:80")?;
    // stream.write_all(b"GET / HTTP/1.0\r\n\r\n")?;
    // let mut response = String::new();
    // stream.read_to_string(&mut response)?;

    // 标准输出
    println!("WASI 程序执行完成");
    Ok(())
}
```

```bash
# 编译为 WASI
cargo build --target wasm32-wasi --release

# 使用 wasmtime 运行（需要预先安装 wasmtime）
# --dir 映射宿主机目录到 WASM 沙箱（WASI 的安全模型：默认无法访问文件系统）
wasmtime --dir ./data:/data target/wasm32-wasi/release/my_wasi.wasm
```

WASI 的安全模型是**能力安全（capability-based security）**——WASM 模块默认无法访问任何系统资源，必须由运行时显式授予（如 `--dir` 授予目录访问权限、`--tcplisten` 授予网络监听权限）。这比传统进程的"用户权限"模型更精细，适合不可信代码执行（如插件系统、边缘计算、多租户平台）。

### 5.2 wasmtime 运行时与服务端场景

`wasmtime` 是 Bytecode Alliance 开发的 WASM/WASI 运行时，用 Rust 编写，性能接近原生（通常为原生的 50%-90%）。它提供了 Rust API，可以将 WASM 执行嵌入到 Rust 应用中：

```toml
# Cargo.toml（宿主程序）
[dependencies]
wasmtime = "20"
wasmtime-wasi = "20"
```

```rust
// 宿主程序：嵌入 wasmtime 执行 WASM 模块
use wasmtime::*;
use wasmtime_wasi::sync::WasiCtxBuilder;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // 创建引擎
    let engine = Engine::default();

    // 编译 WASM 模块（从文件）
    let module = Module::from_file(&engine, "target/wasm32-wasi/release/plugin.wasm")?;

    // 创建 WASI 上下文：授予目录访问和环境变量
    let wasi = WasiCtxBuilder::new()
        .inherit_stdio()
        .inherit_args()?
        .env("PLUGIN_MODE", "production")?
        .preopened_dir("./data", "/data")?
        .build();

    // 创建链接器和存储
    let mut linker = Linker::new(&engine);
    wasmtime_wasi::add_to_linker(&mut linker, |s| s)?;

    let mut store = Store::new(&engine, wasi);

    // 实例化模块
    let instance = linker.instantiate(&mut store, &module)?;

    // 调用导出的函数
    let run = instance.get_typed_func::<(), ()>(&mut store, "run")?;
    run.call(&mut store, ())?;

    Ok(())
}
```

服务端 WASM 的典型场景：

| 场景 | 优势 | 代表项目 |
|------|------|----------|
| 插件系统 | 安全沙箱、跨平台、快速启动 | Shopify Functions、Suborbital |
| 边缘计算 | 冷启动快（毫秒级）、体积小 | Fastly Compute@Edge、Cloudflare Workers |
| 多租户执行 | 能力安全、资源隔离 | Fermyon Spin、WasmCloud |
| 可移植工作负载 | 一次编译到处运行（x86/ARM/RISC-V） | Docker 替代方案探索 |
| 区块链智能合约 | 确定性执行、沙箱安全 | Polkadot、Solana（部分） |

WASM 服务端的核心优势是**冷启动速度**——WASM 模块实例化通常在 100 微秒到几毫秒之间，而容器（Docker）冷启动需要几百毫秒到几秒，虚拟机需要几秒到几十秒。这使得 WASM 适合事件驱动的无服务器（Serverless）场景，请求到来时即时启动实例处理，处理完立即销毁，无需常驻进程。

C++ 对照：C++ 也可以编译为 WASM（通过 Emscripten + WASI SDK），但 Rust 的 `wasm32-wasi` 目标是一等公民，`std` 完整支持，且 `wasmtime` 本身就是 Rust 编写的，宿主 API 与 Rust 生态无缝集成。C++ 的 WASI 开发需要配置 WASI SDK（基于 clang），且标准库支持不如 Rust 完整。

## 6. 包体优化与性能分析

### 6.1 wasm-opt 与包体积压缩

Rust 编译的 WASM 默认体积较大（包含 panic 处理、格式化代码、未使用的 `std` 函数等），通过以下组合可以将体积压缩到最小：

```toml
# Cargo.toml - 最小体积配置
[profile.release]
opt-level = "z"        # 极致体积优化
lto = true              # full LTO
codegen-units = 1       # 单编译单元
panic = "abort"         # 移除 panic 展开逻辑
strip = true            # 剥离符号（wasm-bindgen 后处理）
```

```bash
# 1. 编译
cargo build --target wasm32-unknown-unknown --release

# 2. wasm-bindgen 生成胶水代码（--remove-producers-section 移除生产者信息）
wasm-bindgen target/wasm32-unknown-unknown/release/app.wasm \
    --out-dir pkg \
    --remove-producers-section

# 3. wasm-opt 优化（Binaryen 工具集，需要预先安装）
wasm-opt -Oz --dce --vacuum --remove-unused-module-elements \
    pkg/app_bg.wasm -o pkg/app_bg.wasm

# 4. 压缩（gzip/brotli，Web 服务器传输时自动压缩）
gzip -9 pkg/app_bg.wasm
```

优化效果对比（以一个包含 `web-sys` DOM 操作的简单应用为例）：

| 配置 | WASM 体积 | gzip 后 |
|------|-----------|---------|
| 默认 debug | ~2 MB | ~500 KB |
| 默认 release | ~500 KB | ~150 KB |
| release + opt-level=z + lto | ~200 KB | ~60 KB |
| 上述 + panic=abort + strip | ~120 KB | ~40 KB |
| 上述 + wasm-opt -Oz | ~60 KB | ~20 KB |

`trunk build --release` 自动执行上述所有优化步骤（编译 + wasm-bindgen + wasm-opt），无需手动执行。

另一个重要的优化是**移除 panicking 框架**。默认的 panic 处理包含 `core::fmt` 格式化代码（用于打印 panic 消息），这可能占几十 KB。使用 `panic = "abort"` 或自定义 `panic_handler`（直接调用 `wasm32_unreachable`）可以移除这些代码：

```rust
// 自定义 panic handler：直接 trap，不格式化消息
#[cfg(target_arch = "wasm32")]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    unsafe { core::arch::wasm32::unreachable() }
}
```

### 6.2 性能分析与基准对比

WASM 性能分析工具：

1. **浏览器 DevTools**：Chrome/Firefox 的开发者工具支持 WASM 调试——可以在 Sources 面板查看 WASM 反汇编代码，设置断点，查看调用栈。启用 DWARF 调试信息后（`-g`），可以显示原始 Rust 源码。
2. **`wasm-bindgen` 的 `--keep-debug`**：保留调试信息用于分析。
3. **`twiggy`**：WASM 代码大小分析工具，显示每个函数占用的字节数，帮助定位体积热点。

```bash
# 安装 twiggy
cargo install twiggy

# 分析 WASM 体积分布
twiggy top pkg/app_bg.wasm

# 输出示例（按体积排序的函数）：
# Shallow Bytes │ Shallow % │ Item
# ───────────────┼───────────┼─────────────────────────────────────────
#          23456 │    18.2%  │ <core::fmt::Formatter>::write_str
#          12345 │     9.6%  │ serde_json::de::Deserializer::parse
#           8901 │     6.9%  │ my_app::process_data
```

性能基准对比（典型计算任务，WASM vs 原生）：

| 任务 | 原生 Rust | WASM (Chrome) | WASM / 原生 |
|------|-----------|---------------|-------------|
| 斐波那契(40) 递归 | 0.5s | 0.7s | 1.4x |
| JSON 解析 (1MB) | 12ms | 18ms | 1.5x |
| 矩阵乘法 (1000x1000) | 45ms | 60ms | 1.3x |
| SHA256 (100MB) | 320ms | 410ms | 1.3x |
| 字符串处理 | 8ms | 15ms | 1.9x |

WASM 的性能通常为原生的 50%-80%（即 1.2x-2x 开销），主要开销来自：边界检查（内存安全）、间接调用（无法内联跨模块函数）、SIMD 限制（部分浏览器未启用 WASM SIMD）。对于计算密集型任务（数学、加密、编解码），WASM 接近原生；对于字符串和对象密集型任务，开销较大。

C++ 对照：C++ 编译的 WASM 性能与 Rust WASM 接近（都基于 LLVM），但 C++ + Emscripten 的运行时开销略大（POSIX 兼容层）。Rust 的 `wasm-bindgen` 胶水代码更轻量，JS 互操作开销更小。两者在纯计算性能上差异不大，主要差异在工具链和包体积。

## 7. 典型跨端场景与限制

### 7.1 计算密集型前端、游戏引擎、插件系统

**场景一：计算密集型前端模块**

最成熟的 WASM 应用场景是将计算密集型逻辑从 JS 移到 Rust WASM，包括：
- 图片/视频处理（滤镜、格式转换、压缩）
- 数据处理（CSV/Excel 解析、科学计算、统计分析）
- 加密/解密（哈希、签名、加密算法）
- 文本处理（Markdown 解析、语法高亮、搜索索引）
- 3D 模型处理（网格简化、格式转换、物理模拟）

典型案例：`image-rs`（Rust 图像处理库）编译为 WASM 后在浏览器中处理图片，性能比 JS 实现快 5-10 倍；`ruff`（Python linter）编译为 WASM 后在浏览器中运行，用于在线代码编辑器。

**场景二：游戏引擎与图形应用**

Rust 游戏引擎（`bevy`、`macroquad`、`fyrox`）都支持编译为 WASM，在浏览器中运行。`bevy` 引擎的 WASM 支持通过 `web-sys` 操作 WebGL2/WebGPU，通过 `wasm-bindgen` 处理输入事件。游戏资源（模型、纹理）通过 `fetch` API 异步加载。

```toml
# macroquad 游戏引擎 WASM 示例
[dependencies]
macroquad = "0.4"
```

```rust
use macroquad::prelude::*;

#[macroquad::main("WASM 游戏")]
async fn main() {
    let mut x = 0.0f32;
    loop {
        clear_background(LIGHTGRAY);
        x += 2.0;
        if x > screen_width() { x = 0.0; }
        draw_circle(x, screen_height() / 2.0, 30.0, BLUE);
        draw_text("Rust + WASM 游戏", 20.0, 40.0, 30.0, DARKGRAY);
        next_frame().await;
    }
}
```

`macroquad` 的 API 在桌面和 WASM 上完全一致——同一份代码可以编译为桌面原生应用和浏览器 WASM，这是 Rust 跨端能力的体现。

**场景三：插件系统与可移植扩展**

WASM 的安全沙箱和跨平台特性使其成为插件系统的理想选择：
- **编辑器插件**：VS Code 的 Web 版支持 WASM 扩展，Zed 编辑器使用 WASM 插件
- **数据库扩展**：`SingleStore`、`Redpanda` 支持 WASM 存储过程/转换函数
- **API 网关插件**：`Envoy` 支持 WASM 过滤器（Proxy-Wasm 标准）
- **CI/CD 插件**：`Suborbital` 平台使用 WASM 执行可移植的扩展函数

插件系统的核心优势：插件作者可以用任何支持 WASM 的语言编写（Rust、C/C++、Go、AssemblyScript、Python 等），宿主应用安全沙箱执行，无需担心插件崩溃影响宿主，且插件跨平台跨架构可移植。

### 7.2 当前限制与未来方向

**当前限制**：

1. **线程支持有限**：`wasm32-unknown-unknown` 默认不支持多线程（`std::thread` 不可用）。WebAssembly Threads 提案已被主流浏览器支持，但需要跨域隔离（COOP/COEP 头），且 Rust 需要使用 `wasm-bindgen-rayon` 等库才能使用 `rayon` 并行迭代。
2. **GC 互操作不成熟**：WASM 目前无法直接操作 JS 的垃圾回收对象（如 DOM 节点、JS 对象），必须通过 `wasm-bindgen` 的引用表间接访问，每次跨边界调用有开销。WASM GC 提案（已在 Chrome 中启用）将改善这一点，但 Rust 对 WASM GC 的支持仍在开发中。
3. **调试体验不如原生**：浏览器 DevTools 对 WASM 的调试支持在改善，但仍不如原生 GDB/LLDB——变量查看、条件断点、性能分析的体验有差距。
4. **异步 JS 互操作开销**：Rust `Future` 与 JS `Promise` 的转换通过 `wasm-bindgen-futures` 实现，每次跨边界有微任务调度开销。高频异步操作场景可能成为瓶颈。
5. **包体积仍需优化**：即使经过 `wasm-opt` 优化，包含复杂依赖（如 `serde`、`regex`）的 WASM 模块仍可能超过 100KB，对于移动端弱网环境需要注意。
6. **WASI 标准未稳定**：WASI 预览版 2（组件模型）正在标准化中，API 仍在变化。生产环境使用 WASI 需要锁定运行时版本。

**未来方向**：

1. **WASM 组件模型（Component Model）**：定义 WASM 模块之间的标准接口（IDL + 二进制格式），支持不同语言编写的模块互相调用，类似于 OS 的共享库但跨语言跨平台。
2. **WASI 预览版 2/3**：更完整的系统接口（异步 IO、sockets、线程、时钟），支持更多服务端场景。
3. **WASM GC**：允许 WASM 直接分配和操作 GC 对象（与 JS 堆共享），减少跨边界开销，支持 Java/Kotlin/Dart 等 GC 语言编译为 WASM。
4. **WebGPU**：Rust 通过 `web-sys` 操作 WebGPU API，在浏览器中获得接近原生的 GPU 计算能力，适合机器学习推理、科学计算、3D 渲染。
5. **WASM 容器化**：Docker 已支持 WASM 运行时（与 containerd 集成），WASM 模块可以像容器一样部署和编排，冷启动速度比容器快 10-100 倍。

C++ 对照：C++ 在 WASM 领域起步更早（Emscripten 自 2010 年），在游戏引擎移植（Unreal、Unity）和大型 C++ 应用移植方面有更多案例。Rust 的优势在于更现代的工具链、更小的包体积、更安全的互操作、以及与 WASI/wasmtime 的深度集成（wasmtime 本身是 Rust 项目）。两者不是竞争关系——C++ 适合将现有大型 C++ 代码库移植到浏览器，Rust 适合新的 WASM 项目和服务端 WASM 应用。

## 8. 快速参考卡片

| 查询点 | 速答 |
| --- | --- |
| 工具链 | `wasm-pack build --target web`（推荐）/ `wasm-bindgen-cli` 手工绑定 |
| 目标平台 | `wasm32-unknown-unknown`（浏览器）/ `wasm32-wasi`（服务端，WASI 能力受限） |
| 绑定导出 | `#[wasm_bindgen] pub fn add(a: i32, b: i32) -> i32`；结构体用 `#[wasm_bindgen(getter)]` |
| 调用 JS | `js_sys`（Array/Object/Promise）、`web_sys`（DOM/Canvas/fetch） |
| JS 互操作类型 | `JsValue`、`JsString`、`Closure`（回调需 `forget()` 或保存所有权） |
| 异步互操作 | `wasm_bindgen_futures::JsFuture::from(promise).await` |
| 体积优化 | `opt-level = "z"`、`lto = true`、`panic = "abort"`、`wasm-opt -Oz`、`strip` |
| 线程与 SIMD | 需 `--target-features` + COOP/COEP 头；`wasm32-wasi-threads` 实验性 |
| 跨端框架 | `Tauri`（桌面/移动，Web 前端 + Rust 后端）、`Yew`/`Leptos`（前端框架） |
| 常见坑点 | 忘了 `wasm-opt` 或 debug 构建导致包体 MB 级；WASI 无文件系统/网络需显式能力授予 |

---

## 9. 常见坑与本节小结

### 常见坑

1. **忘记 `crate-type = ["cdylib"]`**：编译为 WASM 库必须在 `Cargo.toml` 中设置 `crate-type = ["cdylib"]`，否则 cargo 会尝试编译为可执行文件，链接失败。
2. **`wasm-bindgen` 版本与 CLI 版本不匹配**：`wasm-bindgen` 依赖的版本必须与 `wasm-bindgen-cli` 的版本一致，否则生成的胶水代码与 WASM 二进制不兼容，运行时崩溃。使用 `trunk` 可以自动管理版本。
3. **在 WASM 中使用 `std::thread`**：`wasm32-unknown-unknown` 不支持线程，`std::thread::spawn` 会 panic。需要并行计算时使用 `wasm-bindgen-rayon`（Web Workers）或重新设计为单线程异步。
4. **`web-sys` feature 未启用**：`web-sys` 默认不启用任何 API，使用 `Document`、`CanvasRenderingContext2d` 等类型前必须在 `Cargo.toml` 的 `features` 中显式启用，否则编译错误"未找到类型"。
5. **WASM 中 panic 无输出**：默认的 panic handler 在 WASM 中只是 `unreachable`（trap），不会打印错误消息。使用 `console_error_panic_hook` crate 将 panic 消息输出到 `console.error`，便于调试。
6. **`Result<_, JsValue>` 的错误转换**：Rust 错误类型（如 `std::io::Error`）不能直接转换为 `JsValue`，需要手动映射或使用 `?` 操作符时确保错误类型实现了 `Into<JsValue>`。常用做法是 `map_err(|e| JsValue::from_str(&e.to_string()))`。
7. **WASI 程序无法访问文件**：WASI 默认沙箱无法访问任何文件，运行时必须通过 `--dir` 显式映射目录。"No such file or directory" 错误通常是因为忘记 `--dir`。
8. **`wasm-opt` 未安装导致 trunk build 失败**：`trunk build --release` 默认调用 `wasm-opt`，如果系统未安装 Binaryen 工具集会报错。需要 `brew install binaryen`（macOS）或从 GitHub 下载预编译二进制。
9. **大对象跨 JS-WASM 边界开销大**：每次将 JS `Array`/`Object` 传入 Rust 或从 Rust 返回复杂结构，`wasm-bindgen` 都需要逐个字段转换。高频调用应使用 `Uint8Array`（零拷贝共享 WASM 内存）或 `serde-wasm-bindgen`（序列化传输）。
10. **WASM 内存增长限制**：WASM 线性内存默认最大 4GB（32 位地址空间），且增长是按 64KB 页递增的。处理超大文件（>1GB）时需要注意内存限制，或使用流式处理。

### 本节小结

Rust 是 WebAssembly 的首选语言，其技术栈涵盖浏览器端和服务端两大场景。浏览器端以 `wasm32-unknown-unknown` 为目标，`wasm-bindgen` 提供类型安全的 JS 互操作（函数导出、结构体/方法导出、getter/setter），`js-sys` 绑定 JS 标准库，`web-sys` 全量绑定 Web API（DOM、Canvas、Fetch、WebSocket 等），`trunk` 提供一键构建和开发服务器（热重载），可以与 React/Vue 集成或使用 `yew`/`Leptos` 纯 Rust 前端框架。服务端以 `wasm32-wasi` 为目标，支持完整 `std`（文件、网络、环境变量），`wasmtime` 运行时提供安全沙箱和能力安全模型，适用于插件系统、边缘计算、多租户执行等场景。包体优化通过 `opt-level="z"` + LTO + `panic="abort"` + `wasm-opt` 组合，可将典型应用压缩到 20-60KB（gzip 后）。性能通常为原生的 50%-80%，计算密集型任务接近原生。典型跨端场景包括计算密集型前端模块、游戏引擎、插件系统。当前限制包括线程支持、GC 互操作、调试体验，但 WASM 组件模型、WASI 预览版 2、WebGPU 等未来方向正在快速改善。与 C++ + Emscripten 相比，Rust 的优势在于更现代的工具链、更小的包体积、更安全的互操作，以及与 wasmtime/WASI 生态的深度集成。

---

上一篇：《04-操作系统与底层开发.md》　｜　模块索引：《../README.md》
