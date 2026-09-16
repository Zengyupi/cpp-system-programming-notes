# Future 状态机与 async 原理

> 本节目标：掌握 Future trait 与 Poll 机制、async 块/函数的语法糖本质、Pin/Unpin 与自引用结构的关系、手动 poll 状态机变换、Waker 唤醒机制，理解零成本 async 的本质，并能对比 C++20 coroutine 的差异。

## 本章速览

- [1. Future trait 与 Poll 机制](#1-future-trait-与-poll-机制)
  - [1.1 Future trait 定义](#11-future-trait-定义)
  - [1.2 Poll::Ready 与 Pending](#12-pollready-与-pending)
  - [1.3 简单 Future 实现](#13-简单-future-实现)
- [2. async 块/函数语法糖](#2-async-块函数语法糖)
  - [2.1 async fn 的状态机变换](#21-async-fn-的状态机变换)
  - [2.2 .await 的工作原理](#22-await-的工作原理)
- [3. Pin/Unpin 与自引用结构](#3-pinunpin-与自引用结构)
  - [3.1 为什么需要 Pin](#31-为什么需要-pin)
  - [3.2 Pin 的 API 与 Unpin](#32-pin-的-api-与-unpin)
  - [3.3 自引用结构与 Pin](#33-自引用结构与-pin)
- [4. Waker 唤醒机制](#4-waker-唤醒机制)
  - [4.1 Waker 的作用](#41-waker-的作用)
  - [4.2 自定义 Waker 实现](#42-自定义-waker-实现)
- [5. 手动 poll 状态机变换](#5-手动-poll-状态机变换)
- [6. 零成本 async 本质](#6-零成本-async-本质)
- [7. 对比 C++20 coroutine](#7-对比-c20-coroutine)
- [8. 快速参考卡片](#8-快速参考卡片)
- [9. 常见坑](#9-常见坑)
- [10. 本节小结](#10-本节小结)

---

## 1. Future trait 与 Poll 机制

### 1.1 Future trait 定义

`Future` 是 Rust 异步编程的核心 trait，定义了一个异步计算的抽象：

```rust
use std::pin::Pin;
use std::task::{Context, Poll};

pub trait Future {
    type Output;

    fn poll(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Self::Output>;
}
```

关键要素：
- `Output`：异步计算完成后的返回值类型
- `poll`：尝试推进异步计算，返回 `Poll::Ready(value)`（完成）或 `Poll::Pending`（未完成）
- `Pin<&mut Self>`：保证 Future 在内存中不会被移动（详见第 3 节）
- `Context<'_>`：提供 `Waker`，用于在 Future 就绪时通知执行器

### 1.2 Poll::Ready 与 Pending

`Poll` 是一个简单的枚举：

```rust
pub enum Poll<T> {
    Ready(T),    // 计算完成，携带结果
    Pending,     // 计算未完成，需要等待
}
```

poll 的契约：
- 返回 `Pending` 时，Future 必须在将来某个时刻通过 `Waker` 通知执行器再次 poll
- 返回 `Ready` 后，Future 不应该再被 poll（再次 poll 的行为未定义）
- poll 是**非阻塞**的：如果不能立即完成，必须返回 Pending，不能阻塞线程

### 1.3 简单 Future 实现

一个立即返回值的 Future：

```rust
use std::future::Future;
use std::pin::Pin;
use std::task::{Context, Poll};

struct Ready<T> {
    value: Option<T>,
}

impl<T> Future for Ready<T> {
    type Output = T;

    fn poll(mut self: Pin<&mut Self>, _cx: &mut Context<'_>) -> Poll<T> {
        match self.value.take() {
            Some(value) => Poll::Ready(value),
            None => Poll::Pending, // 已经被poll过一次
        }
    }
}

fn ready<T>(value: T) -> Ready<T> {
    Ready { value: Some(value) }
}
```

一个需要等待的 Future（定时器）：

```rust
use std::future::Future;
use std::pin::Pin;
use std::task::{Context, Poll, Waker};
use std::sync::{Arc, Mutex};
use std::time::Instant;
use std::thread;

struct TimerFuture {
    target_time: Instant,
    waker: Arc<Mutex<Option<Waker>>>,
}

impl TimerFuture {
    fn new(duration: std::time::Duration) -> Self {
        let target_time = Instant::now() + duration;
        let waker = Arc::new(Mutex::new(None));

        // 后台线程：时间到了就wake
        let waker_clone = Arc::clone(&waker);
        thread::spawn(move || {
            while Instant::now() < target_time {
                thread::sleep(std::time::Duration::from_millis(1));
            }
            if let Some(waker) = waker_clone.lock().unwrap().take() {
                waker.wake();
            }
        });

        TimerFuture { target_time, waker }
    }
}

impl Future for TimerFuture {
    type Output = ();

    fn poll(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<()> {
        if Instant::now() >= self.target_time {
            Poll::Ready(())
        } else {
            // 保存waker，时间到了通知执行器
            *self.waker.lock().unwrap() = Some(cx.waker().clone());
            Poll::Pending
        }
    }
}
```

## 2. async 块/函数语法糖

### 2.1 async fn 的状态机变换

`async fn` 是语法糖，编译器将其变换为一个实现了 `Future` trait 的状态机结构体。

```rust
// 源代码
async fn fetch_data(url: &str) -> String {
    let response = http_get(url).await;
    let parsed = parse_response(response).await;
    parsed
}

// 编译器变换后的概念代码（简化）
struct FetchDataFuture<'a> {
    state: State,
    url: &'a str,
    // 跨await点需要保存的变量
    response: Option<String>,
    http_get_future: Option<HttpGetFuture>,
    parse_future: Option<ParseFuture>,
}

enum State {
    Start,
    WaitingHttpGet,
    WaitingParse,
    Done,
}

impl<'a> Future for FetchDataFuture<'a> {
    type Output = String;

    fn poll(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<String> {
        loop {
            match self.state {
                State::Start => {
                    // 开始执行，创建第一个子Future
                    let fut = http_get(self.url);
                    self.http_get_future = Some(fut);
                    self.state = State::WaitingHttpGet;
                }
                State::WaitingHttpGet => {
                    // poll子Future
                    let result = match self.http_get_future.as_mut().unwrap().poll(cx) {
                        Poll::Ready(v) => v,
                        Poll::Pending => return Poll::Pending,
                    };
                    self.response = Some(result);
                    self.http_get_future = None;
                    let fut = parse_response(self.response.as_ref().unwrap());
                    self.parse_future = Some(fut);
                    self.state = State::WaitingParse;
                }
                State::WaitingParse => {
                    let result = match self.parse_future.as_mut().unwrap().poll(cx) {
                        Poll::Ready(v) => v,
                        Poll::Pending => return Poll::Pending,
                    };
                    self.state = State::Done;
                    return Poll::Ready(result);
                }
                State::Done => panic!("polled after completion"),
            }
        }
    }
}
```

状态机变换的关键：
1. 每个 `.await` 点是一个状态边界
2. 跨 `.await` 点存活的变量被保存在状态机结构体中
3. 不跨 `.await` 点的变量是普通局部变量，在栈上分配
4. poll 方法是一个循环，根据当前状态执行对应的代码段

### 2.2 .await 的工作原理

`.await` 的本质是：**poll 子 Future，如果 Pending 就保存状态并返回 Pending，如果 Ready 就解包值继续执行**。

```rust
// .await的概念展开
let result = match sub_future.poll(cx) {
    Poll::Ready(v) => v,
    Poll::Pending => {
        // 保存当前状态，返回Pending
        // 下次poll时从这里继续
        return Poll::Pending;
    }
};
// 继续执行...
```

async 块也是语法糖：

```rust
// async块
let fut = async {
    let x = compute().await;
    x + 1
};

// 等价于一个匿名的Future状态机
```

## 3. Pin/Unpin 与自引用结构

### 3.1 为什么需要 Pin

async 状态机可能包含**自引用**：一个字段引用了同一个结构体中的另一个字段。

```rust
// async函数中可能产生自引用结构
async fn self_referential() {
    let data = vec![1, 2, 3];
    let ref_to_data = &data; // 引用同一个状态机中的data字段
    some_async_op().await;   // await点：ref_to_data和data都需要保存在状态机中
    println!("{:?}", ref_to_data);
}
```

变换后的状态机（概念上）：

```rust
struct SelfRefFuture {
    state: State,
    data: Vec<i32>,
    ref_to_data: *const Vec<i32>, // 指向self.data的指针！
}
```

如果这个 Future 在内存中被移动（例如从栈移到堆，或在 `Vec` 中重新分配），`ref_to_data` 指针就会悬空。

```text
移动前：                        移动后：
┌─────────────────────┐        ┌─────────────────────┐
│ data: [1, 2, 3]    │        │ data: [1, 2, 3]    │
│ ref_to_data: 0x1000 │──┐     │ ref_to_data: 0x1000 │──┐ 悬空！
└─────────────────────┘  │     └─────────────────────┘  │
  地址 0x1000             │       地址 0x2000             │
                          └──指向0x1000                     └──仍指向0x1000（已失效）
```

`Pin` 的作用：**阻止值被移动**，保证自引用指针始终有效。

### 3.2 Pin 的 API 与 Unpin

`Pin<P>` 是一个指针包装器，保证指针指向的值不会被移动：

```rust
use std::pin::Pin;

// Pin<&mut T>：指向T的可变引用，但T不能被移动
// 要移动T，需要T: Unpin（可以安全移动的类型）

// Unpin是一个标记trait，表示类型可以安全地移动（没有自引用）
// 大多数类型自动实现Unpin
// async状态机默认!Unpin（因为可能有自引用）

use std::marker::Unpin;

// 普通类型是Unpin的
fn assert_unpin<T: Unpin>() {}
assert_unpin::<i32>();
assert_unpin::<String>();
assert_unpin::<Vec<u8>>();

// async块的Future是!Unpin的
// let fut = async { ... };
// assert_unpin::<typeof(fut)>(); // 编译错误
```

`Pin` 的关键 API：

```rust
use std::pin::{Pin, pin};

// pin!宏：在栈上创建一个Pin值（不能被移动）
let pinned = pin!(async {
    // 这个async块被pin在栈上，不能被移动
    42
});

// Box::pin：在堆上创建一个Pin值
let boxed: Pin<Box<dyn Future<Output = i32>>> = Box::pin(async { 42 });

// Pin::new：只有T: Unpin时才能创建（因为Unpin类型移动是安全的）
let mut val = 42;
let pinned = Pin::new(&mut val); // OK：i32是Unpin

// 对于!Unpin类型，需要用unsafe的Pin::new_unchecked
// 或者用pin!/Box::pin等安全方式
```

### 3.3 自引用结构与 Pin

手动实现一个自引用结构（需要 unsafe）：

```rust
use std::pin::Pin;
use std::marker::PhantomPinned;

struct SelfRef {
    data: String,
    // 指向data的指针，使用裸指针避免生命周期问题
    data_ptr: *const String,
    // PhantomPinned使类型!Unpin
    _pin: PhantomPinned,
}

impl SelfRef {
    fn new(data: String) -> Pin<Box<SelfRef>> {
        let mut this = Box::new(SelfRef {
            data,
            data_ptr: std::ptr::null(),
            _pin: PhantomPinned,
        });

        // 安全：在Box中，地址稳定后再设置指针
        let this_ptr: *const String = &this.data;
        this.data_ptr = this_ptr;

        // 转换为Pin<Box<SelfRef>>，保证不会被移动
        unsafe { Pin::new_unchecked(this) }
    }

    fn get_data(self: Pin<&Self>) -> &String {
        // 安全：data_ptr始终指向self.data，因为self被Pin保证不移动
        unsafe { &*self.data_ptr }
    }
}

fn main() {
    let self_ref = SelfRef::new("hello".to_string());
    println!("{}", self_ref.as_ref().get_data());
}
```

## 4. Waker 唤醒机制

### 4.1 Waker 的作用

`Waker` 是执行器和 Future 之间的通知机制：
- Future 在 poll 时收到 `Context`，从中获取 `Waker`
- Future 返回 Pending 时，保存 `Waker`
- 当 Future 就绪时（如 IO 完成、定时器到期），调用 `waker.wake()` 通知执行器
- 执行器收到通知后，再次 poll 这个 Future

```text
执行器（Executor）                    Future
     │                                  │
     │  poll(future, context)           │
     │─────────────────────────────────>│
     │                                  │ 保存context.waker()
     │         Poll::Pending            │
     │<─────────────────────────────────│
     │                                  │
     │         ...等待...                │
     │                                  │ 事件发生（IO完成等）
     │                                  │ waker.wake()
     │  通知：future就绪                 │
     │<─────────────────────────────────│
     │                                  │
     │  poll(future, context)           │
     │─────────────────────────────────>│
     │         Poll::Ready(value)       │
     │<─────────────────────────────────│
```

### 4.2 自定义 Waker 实现

简化执行器展示 Waker 核心机制：

```rust
struct Task { future: Mutex<Pin<Box<dyn Future<Output=()>+Send>>>, queue: Arc<Mutex<VecDeque<Arc<Task>>>> }

impl Wake for Task {
    fn wake(self: Arc<Self>) { self.queue.lock().unwrap().push_back(self); }
}

// 执行器：从队列取任务→创建Waker→poll→Ready则丢弃，Pending则等wake重新入队
fn run(queue: &Mutex<VecDeque<Arc<Task>>>) {
    while let Some(task) = queue.lock().unwrap().pop_front() {
        let waker = Waker::from(task.clone());
        let mut cx = Context::from_waker(&waker);
        let _ = task.future.lock().unwrap().as_mut().poll(&mut cx);
    }
}
```

核心：Task 实现 Wake trait，wake 时把自己放回任务队列，执行器不断从队列取任务 poll。实际执行器（Tokio）在此基础上增加 IO 驱动、定时器、work-stealing 等。

## 5. 手动 poll 状态机变换

手动实现状态机，等价于 `async { let x = step1().await; let y = step2(x).await; y + 1 }`：

```rust
enum ManualFuture {
    Start,
    WaitingStep1(Step1),
    WaitingStep2 { step2: Step2, x: i32 },
    Done,
}

impl Future for ManualFuture {
    type Output = i32;
    fn poll(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<i32> {
        loop {
            match &mut *self {
                ManualFuture::Start => *self = ManualFuture::WaitingStep1(Step1),
                ManualFuture::WaitingStep1(s) => {
                    let x = ready!(unsafe { Pin::new_unchecked(s) }.poll(cx));
                    *self = ManualFuture::WaitingStep2 { step2: Step2 { input: x }, x };
                }
                ManualFuture::WaitingStep2 { step2, .. } => {
                    let y = ready!(unsafe { Pin::new_unchecked(step2) }.poll(cx));
                    *self = ManualFuture::Done;
                    return Poll::Ready(y + 1);
                }
                ManualFuture::Done => panic!("polled after completion"),
            }
        }
    }
}
```

核心：enum 每个变体代表一个状态，poll 方法匹配当前状态、推进计算、转移到下一状态。跨 await 的变量（如 `x`）保存在状态变体字段中。

## 6. 零成本 async 本质

Rust 的 async 是**零成本抽象**：

1. **无运行时开销**：async fn 编译为状态机结构体，没有堆分配（除非显式 `Box::pin`）、没有虚函数调用、没有 GC
2. **无调度器开销**：Future 本身不包含调度逻辑，调度由外部执行器负责
3. **编译期优化**：状态机的 poll 方法可以被 LLVM 内联和优化，简单的 async 代码可能完全优化为同步代码
4. **按需分配**：只有跨 await 点的变量才保存在状态机中，不跨 await 的变量是普通栈变量

```rust
// 这个async函数编译后的状态机可能只有几个字节
async fn trivial() -> i32 {
    42
}
// 等价于Ready(42)，状态机只有一个状态

// 这个async函数的状态机包含跨await的变量
async fn nontrivial() -> i32 {
    let x = 10;           // 不跨await，栈变量
    let y = heavy().await; // await点
    x + y                  // x需要跨await，保存在状态机中
}
```

对照 C++20 coroutine：C++20 的 coroutine 默认有堆分配（promise 对象在堆上），虽然编译器可以做堆分配消除（HALO），但不保证。Rust 的 async 状态机默认在栈上，只有显式 `Box::pin` 才堆分配。

## 7. 对比 C++20 coroutine

| 特性 | Rust async/await | C++20 coroutine |
|------|-------------------|------------------|
| 核心抽象 | `Future` trait | `coroutine_handle` + promise |
| 状态机 | 编译器生成匿名结构体 | 编译器生成 coroutine frame |
| 默认分配 | 栈上（无堆分配） | 堆上（promise 在堆） |
| 移动安全 | `Pin` 保证不移动 | 无 Pin，coroutine frame 地址稳定 |
| 唤醒机制 | `Waker` trait | `coroutine_handle::resume()` |
| 执行器 | 外部执行器（Tokio 等） | 无标准执行器，需自行实现 |
| 组合子 | `futures` crate 提供 | 无标准库支持，需第三方库 |
| 取消 | drop Future 即取消 | 需手动实现取消逻辑 |
| 错误处理 | `Result` + `?` | 异常或返回错误码 |
| 生态 | Tokio/async-std/smol | cppcoro/libunifex |

C++20 coroutine 的关键差异：

```cpp
// C++20 coroutine示例（概念性）
#include <coroutine>

task<int> fetch_data() {
    auto response = co_await http_get("url");
    auto parsed = co_await parse(response);
    co_return parsed;
}
```

C++ coroutine 的 promise 类型决定了 coroutine 的行为（是否堆分配、返回值类型等），需要大量模板元编程。Rust 的 async 设计更统一：所有 async fn 都返回实现 Future 的类型，行为一致。

Rust 的取消模型更安全：drop Future 就取消了，因为状态机的 drop 会递归 drop 所有字段。C++ coroutine 需要手动实现取消，容易泄漏资源。

## 8. 快速参考卡片

| 查询点 | 速答 |
| --- | --- |
| Future trait | `fn poll(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Self::Output>` |
| Poll 两态 | `Ready(v)` / `Pending`；返回 Pending **必须**已安排唤醒，否则永久挂起 |
| async fn | 编译为匿名 Future 结构体 + 状态机；**调用不执行**，`.await`/poll 才推进 |
| `.await` 语义 | 循环 poll 直到 Ready；Pending 时让出执行权给 executor |
| Pin 作用 | 保证 `!Unpin` 值不再移动（自引用状态机中指向自身字段的指针才不会失效） |
| Unpin 速记 | 绝大多数类型自动 `Unpin`；`async` 块、自引用结构一般 `!Unpin` |
| Waker | executor 的"可再轮询"通知；手写 Future 必须保存 `cx.waker().clone()` 并在就绪时 `wake()` |
| 手写 Future 步骤 | 保存 waker → 检查状态 → Ready 返回 / Pending 返回并让出 |
| 对比 C++20 协程 | 同为无栈状态机；Rust 有标准 `Future` 接口 + 生态 runtime，C++ 需自写 promise/awaiter 且无标准调度器 |
| 零成本本质 | 无堆分配（不装箱时）、单态化生成、无 vtable；状态机大小 = 各暂停点局部变量并集 |

---

## 9. 常见坑

### 坑 1：手写 Future 忘记唤醒

返回 `Pending` 却没保存 waker、也没在其他地方 `wake()`，任务会**永久挂起**——不 panic、不报错，只是永远不动。手写 Future 的固定套路：进入 poll 时 `let waker = cx.waker().clone();` 存起来，就绪时调用 `waker.wake()`。

### 坑 2：在 async 里调用阻塞函数

`std::thread::sleep`、同步文件 IO、`std::sync::Mutex` 长临界区都会阻塞整个 executor 线程，其它任务全部停滞（多线程 runtime 下也会污染 worker）。解决：`tokio::task::spawn_blocking` 或 `tokio::time::sleep`。

### 坑 3：跨 `await` 持有非 Send 类型

`Rc<T>`、`RefCell` 借用、`std::sync::MutexGuard` 跨 await 会让整个 Future 变成 `!Send`，`tokio::spawn` 直接编译失败。改造：`Rc`→`Arc`、`RefCell`→`tokio::sync` 或作用域内用完即弃、`std::MutexGuard`→缩短临界区或用异步锁。

### 坑 4：以为调用 `async fn` 就执行了

`let f = do_work();` 只是构造了一个 Future，什么都不发生（编译器会给出 unused warnings）。必须 `.await` 或 `spawn`。同理，`join_all` 之前所有 Future 都是惰性的。

### 坑 5：对 `!Unpin` 类型手工移动

`Pin::get_mut`/`mem::swap`/`mem::replace` 搬动 `!Unpin` 的值会破坏地址不变式 → UB。需要稳定地址时用 `Box::pin(fut)`，或者用 `pin!` 宏。

### 坑 6：递归 async fn

递归 async 函数产生无限大的状态机（编译错：*recursive type has infinite size*）。用 `Box::pin(async move { ... })` 断开类型递归，或改写成显式循环（`while let` + 状态变量）。

---

## 10. 本节小结

- **Future trait**：`poll(self: Pin<&mut Self>, cx: &mut Context) -> Poll<Output>` 是异步计算的核心抽象。返回 `Ready(value)` 表示完成，`Pending` 表示未完成且会通过 Waker 通知。
- **async fn 语法糖**：编译器将 async fn 变换为状态机结构体，每个 `.await` 点是状态边界，跨 await 的变量保存在状态机字段中。poll 方法根据当前状态推进计算。
- **Pin/Unpin**：Pin 保证值不被移动，解决 async 状态机的自引用问题。`PhantomPinned` 使类型 `!Unpin`。大多数普通类型自动 `Unpin`。`pin!` 在栈上创建 Pin 值，`Box::pin` 在堆上创建。
- **Waker 唤醒**：Future 在 Pending 时保存 Waker，就绪时调用 `wake()` 通知执行器重新 poll。Task 实现 Wake trait，wake 时把自己放回任务队列。
- **手动状态机**：用 enum 表示状态，poll 方法匹配状态并推进，清晰展示 async 的本质。
- **零成本 async**：无堆分配（默认）、无虚函数、无 GC，状态机可被 LLVM 深度优化。简单 async 代码可能完全优化为同步代码。
- **对比 C++20 coroutine**：Rust 默认栈分配（C++默认堆分配）、Pin 保证移动安全（C++无 Pin）、统一的 Future 抽象（C++需自定义 promise）、drop 即取消（C++需手动取消）。async 的底层 IO 依赖 epoll/io_uring 的 Reactor 模型，对照《../../01-C++技术体系/03-网络编程/02-IO多路复用与Reactor模型.md》理解事件驱动本质。

---

上一篇：《02-锁原子与无锁结构.md》　｜　下一篇：《04-Tokio运行时与异步生态.md》　｜　模块索引：《../README.md》
