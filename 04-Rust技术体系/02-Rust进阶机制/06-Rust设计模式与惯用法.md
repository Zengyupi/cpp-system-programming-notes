# Rust设计模式与惯用法

> 本节目标：掌握Rust生态中的核心设计模式——Builder、Newtype、typestate类型状态机、RAII与Drop守卫、组合替代继承、trait object扩展、门面/错误转换/扩展trait模式，熟悉惯用法速查，能够识别反模式与代码异味。

## 本章速览

- [1. Builder模式](#1-builder模式)
  - [1.1 标准Builder实现](#11-标准builder实现)
  - [1.2 派生宏与typed-builder](#12-派生宏与typed-builder)
- [2. Newtype模式](#2-newtype模式)
  - [2.1 类型安全封装](#21-类型安全封装)
  - [2.2 为外部类型实现trait](#22-为外部类型实现trait)
  - [2.3 Deref与透明转发](#23-deref与透明转发)
- [3. typestate类型状态机](#3-typestate类型状态机)
  - [3.1 编译期状态转移](#31-编译期状态转移)
  - [3.2 实战：HTTP请求构建器](#32-实战http请求构建器)
- [4. RAII与Drop守卫](#4-raii与drop守卫)
  - [4.1 资源守卫模式](#41-资源守卫模式)
  - [4.2 作用域守卫与defer](#42-作用域守卫与defer)
- [5. 组合替代继承](#5-组合替代继承)
  - [5.1 trait定义行为，struct组合状态](#51-trait定义行为struct组合状态)
  - [5.2 对比C++继承体系](#52-对比c继承体系)
- [6. trait object扩展模式](#6-trait-object扩展模式)
  - [6.1 异构集合](#61-异构集合)
  - [6.2 插件架构](#62-插件架构)
- [7. 门面/错误转换/扩展trait模式](#7-门面错误转换扩展trait模式)
  - [7.1 门面模式（Facade）](#71-门面模式facade)
  - [7.2 错误转换模式（From/Into）](#72-错误转换模式frominto)
  - [7.3 扩展trait模式（Extension Trait）](#73-扩展trait模式extension-trait)
- [8. 惯用法速查](#8-惯用法速查)
- [9. 反模式与代码异味对照表](#9-反模式与代码异味对照表)
- [10. 本节小结](#10-本节小结)

---

## 1. Builder模式

Builder模式用于构造具有多个可选字段的复杂对象，避免构造函数参数过多。

### 1.1 标准Builder实现

```rust
#[derive(Debug, Clone)]
pub struct ServerConfig {
    host: String,
    port: u16,
    max_connections: usize,
    timeout_secs: u64,
    tls_enabled: bool,
    workers: usize,
}

// Builder结构体持有可选字段
pub struct ServerConfigBuilder {
    host: Option<String>,
    port: Option<u16>,
    max_connections: Option<usize>,
    timeout_secs: Option<u64>,
    tls_enabled: Option<bool>,
    workers: Option<usize>,
}

impl ServerConfigBuilder {
    pub fn new() -> Self {
        ServerConfigBuilder {
            host: None,
            port: None,
            max_connections: None,
            timeout_secs: None,
            tls_enabled: None,
            workers: None,
        }
    }

    // 每个setter返回Self，支持链式调用
    pub fn host(mut self, host: impl Into<String>) -> Self {
        self.host = Some(host.into());
        self
    }

    pub fn port(mut self, port: u16) -> Self {
        self.port = Some(port);
        self
    }

    pub fn max_connections(mut self, max: usize) -> Self {
        self.max_connections = Some(max);
        self
    }

    pub fn timeout_secs(mut self, secs: u64) -> Self {
        self.timeout_secs = Some(secs);
        self
    }

    pub fn tls_enabled(mut self, enabled: bool) -> Self {
        self.tls_enabled = Some(enabled);
        self
    }

    pub fn workers(mut self, n: usize) -> Self {
        self.workers = Some(n);
        self
    }

    // build方法填充默认值并返回结果
    pub fn build(self) -> ServerConfig {
        ServerConfig {
            host: self.host.unwrap_or_else(|| "127.0.0.1".to_string()),
            port: self.port.unwrap_or(8080),
            max_connections: self.max_connections.unwrap_or(1024),
            timeout_secs: self.timeout_secs.unwrap_or(30),
            tls_enabled: self.tls_enabled.unwrap_or(false),
            workers: self.workers.unwrap_or_else(num_cpus::get),
        }
    }
}

impl Default for ServerConfigBuilder {
    fn default() -> Self {
        Self::new()
    }
}

fn main() {
    // 链式调用，只设置需要的字段
    let config = ServerConfigBuilder::new()
        .host("0.0.0.0")
        .port(9090)
        .tls_enabled(true)
        .workers(8)
        .build();

    println!("{:?}", config);
}
```

Builder模式的优势：
- **可读性**：字段名出现在调用处，不需要记住参数顺序
- **可选字段**：未设置的字段使用默认值
- **不可变**：build后对象不可变，线程安全
- **验证**：build方法可以在构造时验证字段组合

### 1.2 派生宏与typed-builder

手写Builder繁琐，社区提供了`typed-builder`派生宏自动生成（以crates.io最新稳定版为准）：

```rust
use typed_builder::TypedBuilder;

#[derive(TypedBuilder, Debug)]
pub struct ServerConfig {
    #[builder(default = "127.0.0.1".to_string())]
    host: String,
    #[builder(default = 8080)]
    port: u16,
    #[builder(default = false)]
    tls_enabled: bool,
}

fn main() {
    let config = ServerConfig::builder()
        .host("0.0.0.0".to_string())
        .port(9090)
        .build();
    println!("{:?}", config);
}
```

对照C++：C++的Builder模式通常需要手写，没有语言级派生宏支持。

## 2. Newtype模式

Newtype用单字段元组结构体包装类型，提供类型安全和额外语义：

```rust
pub struct UserId(pub u64);
pub struct OrderId(pub u64);
fn find_user(id: UserId) -> Option<String> { Some(format!("user_{}", id.0)) }
// find_user(OrderId(42)); // 编译错误：类型不匹配
```

### 2.1 类型安全封装

核心价值：用类型系统表达语义，编译期阻止逻辑错误（如把OrderId传给UserId参数）。C++可用`boost::strong_typedef`实现类似效果，但不是语言惯用法。

### 2.2 为外部类型实现trait

孤儿规则（orphan rule）要求：为类型实现trait时，trait或类型至少有一个是当前crate定义的。Newtype可以绕过这个限制：

```rust
// 想为Vec<u8>实现Display，但Vec<u8>和Display都不是当前crate定义的
// 直接实现会违反孤儿规则

// 用Newtype包装
pub struct HexDump(pub Vec<u8>);

impl std::fmt::Display for HexDump {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        for byte in &self.0 {
            write!(f, "{:02x} ", byte)?;
        }
        Ok(())
    }
}

fn main() {
    let data = HexDump(vec![0xDE, 0xAD, 0xBE, 0xEF]);
    println!("{}", data); // 输出 "de ad be ef "
}
```

### 2.3 Deref与透明转发

Newtype可通过`Deref`透明转发内部类型方法：

```rust
use std::ops::Deref;
pub struct Email(String);
impl Deref for Email {
    type Target = String;
    fn deref(&self) -> &String { &self.0 }
}
// email.len()、email.is_empty() 自动转发到String
```

注意：`Deref`只用于"确实是一种"（is-a）关系，语义不同的类型应显式调用`.0`或提供命名方法。

## 3. typestate类型状态机

typestate模式用不同的类型表示对象的不同状态，在编译期保证状态转移的合法性。

### 3.1 编译期状态转移

```rust
// 状态标记类型（零大小结构体）
pub struct Created;
pub struct Running;
pub struct Stopped;

// 泛型结构体，状态作为类型参数
pub struct Service<State = Created> {
    name: String,
    _state: std::marker::PhantomData<State>,
}

impl Service<Created> {
    pub fn new(name: &str) -> Self {
        Service {
            name: name.to_string(),
            _state: std::marker::PhantomData,
        }
    }

    // 从Created转移到Running，消耗self，返回新状态的Service
    pub fn start(self) -> Service<Running> {
        println!("Service '{}' started", self.name);
        Service {
            name: self.name,
            _state: std::marker::PhantomData,
        }
    }
}

impl Service<Running> {
    pub fn process(&self, data: &str) {
        println!("Service '{}' processing: {}", self.name, data);
    }

    // 从Running转移到Stopped
    pub fn stop(self) -> Service<Stopped> {
        println!("Service '{}' stopped", self.name);
        Service {
            name: self.name,
            _state: std::marker::PhantomData,
        }
    }
}

impl Service<Stopped> {
    pub fn restart(self) -> Service<Running> {
        println!("Service '{}' restarting", self.name);
        Service {
            name: self.name,
            _state: std::marker::PhantomData,
        }
    }
}

fn main() {
    let service = Service::new("api");
    // service.process("data"); // 编译错误：Created状态没有process方法

    let running = service.start();
    running.process("hello"); // OK：Running状态有process方法
    // running.start(); // 编译错误：Running状态没有start方法（不能重复启动）

    let stopped = running.stop();
    // stopped.process("data"); // 编译错误：Stopped状态没有process方法

    let running_again = stopped.restart();
    running_again.process("world");
}
```

typestate的核心价值：**非法状态转移在编译期被拒绝**，不需要运行时检查。这是Rust类型系统独有的强大模式。

### 3.2 实战：HTTP请求构建器

typestate可以确保build之前必须设置URL和方法：

```rust
// 状态标记
pub struct NoUrl; pub struct HasUrl;
pub struct NoMethod; pub struct HasMethod;

pub struct RequestBuilder<U = NoUrl, M = NoMethod> {
    url: Option<String>, method: Option<String>,
    _u: std::marker::PhantomData<U>, _m: std::marker::PhantomData<M>,
}

impl<U, M> RequestBuilder<U, M> {
    pub fn url(self, url: &str) -> RequestBuilder<HasUrl, M> { /*...*/ }
    pub fn method(self, m: &str) -> RequestBuilder<U, HasMethod> { /*...*/ }
}

// 只有同时有URL和方法时才能build
impl RequestBuilder<HasUrl, HasMethod> {
    pub fn build(self) -> HttpRequest { /*...*/ }
}

// RequestBuilder::new().method("GET").build() // 编译错误：缺URL
// RequestBuilder::new().url("x.com").build()   // 编译错误：缺方法
```

核心思路：用两个泛型参数分别跟踪URL和方法的设置状态，`build`方法只在`RequestBuilder<HasUrl, HasMethod>`上实现，未设置必要字段时编译期报错。

对照C++：C++可以用模板元编程实现typestate（如`boost::statechart`），但语法极其晦涩，错误信息难以理解。Rust的泛型和PhantomData使得typestate成为日常可用的模式。

## 4. RAII与Drop守卫

### 4.1 资源守卫模式

RAII（Resource Acquisition Is Initialization）是Rust的核心惯用法：资源在构造时获取，在drop时释放。

```rust
use std::sync::Mutex;

// 标准库的MutexGuard是RAII的典范
fn demo_mutex() {
    let data = Mutex::new(0);

    {
        let mut guard = data.lock().unwrap();
        *guard += 1;
        // guard离开作用域时自动drop，锁被释放
    } // 锁在这里释放

    // 锁已释放，可以再次获取
    let guard = data.lock().unwrap();
    println!("{}", *guard);
}

// 自定义RAII守卫：文件锁
pub struct FileLock {
    path: String,
}

impl FileLock {
    pub fn acquire(path: &str) -> Result<Self, std::io::Error> {
        // 创建锁文件（简化实现）
        std::fs::write(path, b"locked")?;
        Ok(FileLock { path: path.to_string() })
    }
}

impl Drop for FileLock {
    fn drop(&mut self) {
        // 自动释放：删除锁文件
        let _ = std::fs::remove_file(&self.path);
        println!("Lock released: {}", self.path);
    }
}

fn main() {
    demo_mutex();

    let _lock = FileLock::acquire("/tmp/myapp.lock").unwrap();
    // 临界区...
    // 离开main时，_lock自动drop，锁文件被删除
}
```

### 4.2 作用域守卫与defer

有时需要在作用域结束时执行清理，但不需要定义完整结构体。可用`scopeguard` crate（以crates.io最新稳定版为准）或自定义defer宏：

```rust
macro_rules! defer {
    ($($code:tt)*) => {
        let _guard = {
            struct Guard<F: FnOnce()>(Option<F>);
            impl<F: FnOnce()> Drop for Guard<F> {
                fn drop(&mut self) { if let Some(f) = self.0.take() { f(); } }
            }
            Guard(Some(|| { $($code)* }))
        };
    };
}

fn main() {
    defer!(println!("cleanup runs at scope end"));
    println!("middle");
}
```

defer对照Go的`defer`关键字，但Rust实现是零成本的（编译为drop调用），LIFO顺序执行。

## 5. 组合替代继承

### 5.1 trait定义行为，struct组合状态

Rust没有继承，用trait定义行为、struct组合状态：

```rust
pub trait Drawable { fn draw(&self); fn area(&self) -> f64; }
pub struct Position { x: f64, y: f64 }

// 组合：Circle包含Position字段，而不是继承
pub struct Circle { pub pos: Position, pub radius: f64 }
impl Drawable for Circle {
    fn draw(&self) { println!("circle at ({},{})", self.pos.x, self.pos.y); }
    fn area(&self) -> f64 { std::f64::consts::PI * self.radius * self.radius }
}

// 异构集合用trait object
fn draw_all(shapes: &[Box<dyn Drawable>]) { for s in shapes { s.draw(); } }
```

### 5.2 对比C++继承体系

| 特性 | Rust（组合+trait） | C++（继承） |
|------|---------------------|-------------|
| 代码复用 | 组合字段 + 默认trait方法 | 基类成员继承 |
| 多态 | `dyn Trait`（vtable） | 虚函数（vtable） |
| 多重继承 | trait可组合多个 | 支持但危险（菱形继承） |
| 扩展 | 为外部类型实现trait | 不能修改外部类 |
| 脆弱基类问题 | 无（trait无状态） | 有 |

Rust组合+trait避免了C++继承的脆弱基类问题和菱形继承问题，trait默认方法提供代码复用。

## 6. trait object扩展模式

### 6.1 异构集合

trait object存储不同类型但实现相同trait的对象：

```rust
pub trait EventHandler { fn handle(&self, event: &Event); }
pub struct EventDispatcher { handlers: Vec<Box<dyn EventHandler>> }

impl EventDispatcher {
    pub fn register(&mut self, h: Box<dyn EventHandler>) { self.handlers.push(h); }
    pub fn dispatch(&self, e: &Event) { for h in &self.handlers { h.handle(e); } }
}
// LoggingHandler、MetricsHandler等实现EventHandler，通过Box<dyn EventHandler>注册
```

### 6.2 插件架构

trait object是实现插件架构的基础：

```rust
// 核心crate定义插件trait
pub trait Plugin {
    fn name(&self) -> &str;
    fn on_load(&mut self);
    fn on_event(&self, event: &str);
}

pub struct PluginManager { plugins: Vec<Box<dyn Plugin>> }

impl PluginManager {
    pub fn load(&mut self, mut plugin: Box<dyn Plugin>) {
        plugin.on_load();
        self.plugins.push(plugin);
    }
    pub fn broadcast(&self, event: &str) {
        for p in &self.plugins { p.on_event(event); }
    }
}
// 插件crate实现Plugin trait，通过Box<dyn Plugin>注册到PluginManager
```

## 7. 门面/错误转换/扩展trait模式

### 7.1 门面模式（Facade）

门面模式为复杂子系统提供简化统一接口：

```rust
pub struct MediaPlayer { audio: AudioDecoder, video: VideoDecoder, renderer: Renderer }

impl MediaPlayer {
    // 一行调用完成：打开音频→打开视频→初始化渲染器→解码→渲染
    pub fn play(&self, path: &str) -> Result<(), &'static str> {
        self.audio.open(path)?;
        self.video.open(path)?;
        self.renderer.init();
        self.renderer.render_frame(&self.video.decode(), &self.audio.decode());
        Ok(())
    }
}
```

### 7.2 错误转换模式（From/Into）

实现`From` trait支持`?`运算符自动错误转换：

```rust
#[derive(Debug)]
pub enum AppError { Io(std::io::Error), Parse(std::num::ParseIntError) }

impl From<std::io::Error> for AppError {
    fn from(e: std::io::Error) -> Self { AppError::Io(e) }
}
impl From<std::num::ParseIntError> for AppError {
    fn from(e: std::num::ParseIntError) -> Self { AppError::Parse(e) }
}

fn read_config(path: &str) -> Result<u32, AppError> {
    let content = std::fs::read_to_string(path)?; // 自动转AppError
    Ok(content.trim().parse()?) // 自动转AppError
}
```

也可用`thiserror`派生宏自动生成`From`和`Display`实现（以crates.io最新稳定版为准）。

### 7.3 扩展trait模式（Extension Trait）

为外部类型添加方法而不违反孤儿规则：

```rust
pub trait VecExt<T> {
    fn map_collect<U, F: FnMut(&T) -> U>(&self, f: F) -> Vec<U>;
}

impl<T> VecExt<T> for Vec<T> {
    fn map_collect<U, F: FnMut(&T) -> U>(&self, f: F) -> Vec<U> {
        self.iter().map(f).collect()
    }
}

fn main() {
    let nums = vec![1, 2, 3];
    let doubled: Vec<i32> = nums.map_collect(|x| x * 2);
    println!("{:?}", doubled); // [2, 4, 6]
}
```

生态中广泛使用：`itertools::Itertools`、`tokio::io::AsyncReadExt`、`futures::StreamExt`等。

扩展trait模式在Rust生态中广泛使用，如`itertools::Itertools`为迭代器添加方法、`tokio::io::AsyncReadExt`为异步读取器添加方法。

## 8. 惯用法速查

| 惯用法 | 代码模式 | 用途 |
|--------|----------|------|
| 构造器 | `Type::new()` | 构造对象，替代C++构造函数 |
| 默认值 | `Type::default()` / `#[derive(Default)]` | 提供默认构造 |
| 转换 | `From`/`Into`/`TryFrom`/`TryInto` | 类型转换，`?`自动错误转换 |
| 引用转换 | `AsRef`/`AsMut`/`Borrow`/`ToOwned` | 泛型函数接受多种引用类型 |
| 格式化 | `Display`/`Debug`/`ToString` | 字符串表示 |
| 迭代 | `IntoIterator`/`FromIterator` | `for`循环和`collect()` |
| 运算符 | `Add`/`Deref`/`Drop`等 | 运算符重载 |
| 错误 | `Error` trait + `thiserror`/`anyhow` | 错误处理 |
| 异步 | `Future`/`Stream`/`Sink` | 异步抽象 |

## 9. 反模式与代码异味对照表

| 反模式/异味 | 表现 | 正确做法 |
|-------------|------|----------|
| `unwrap()`滥用 | 生产代码中大量`unwrap()` | 用`?`传播错误，或`expect()`附带信息 |
| `clone()`治百病 | 遇到借用错误就`clone()` | 分析借用关系，用结构调整或`Rc`/`Arc` |
| `Box<dyn Trait>`过度使用 | 所有地方都用trait object | 优先泛型（静态分派），只在需要异构集合时用 |
| `unsafe`块过大 | 整个函数都在unsafe中 | 最小化unsafe范围，封装为安全API |
| `&String`/`&Vec<T>`参数 | 函数参数用具体类型 | 用`&str`/`&[T]`（更通用，自动Deref） |
| `#[inline(always)]`滥用 | 所有函数都加`always` | 让编译器决定，只在热点路径用 |

## 10. 本节小结

- **Builder模式**：用独立的Builder结构体构造复杂对象，支持链式调用和可选字段。`typed-builder`派生宏可自动生成。对照C++的命名参数惯用法，但Rust的`Option`类型更安全。
- **Newtype模式**：单字段元组结构体包装类型，提供类型安全（阻止语义混淆）和绕过孤儿规则（为外部类型实现trait）。`Deref`可透明转发内部方法，但应谨慎使用。
- **typestate类型状态机**：用泛型参数表示状态，编译期保证状态转移合法性。非法操作（如对未启动的服务调用process）在编译期被拒绝。这是Rust类型系统独有的强大模式，C++的等价实现极其晦涩。
- **RAII与Drop守卫**：资源在构造时获取、drop时释放，是Rust的核心惯用法。`MutexGuard`、`FileLock`等都是RAII的应用。defer宏提供Go风格的作用域清理，零成本实现。
- **组合替代继承**：trait定义行为、struct组合状态，避免C++继承的脆弱基类问题和菱形继承问题。`dyn Trait`提供动态多态，泛型提供静态多态。
- **trait object扩展**：异构集合和插件架构的基础。`Box<dyn Trait>`存储不同类型的对象，通过vtable动态分派。
- **门面/错误转换/扩展trait**：门面简化复杂子系统接口；`From`/`Into`支持`?`自动错误转换，对照C++异常安全机制（《../../01-C++技术体系/01-语言基础/07-异常处理与异常安全.md》）理解错误传播的差异；扩展trait为外部类型添加方法（如`Itertools`、`AsyncReadExt`）。

---

上一篇：《05-零成本抽象与性能本质.md》
