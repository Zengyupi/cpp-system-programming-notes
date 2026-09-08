# Future状态机与async原理

> 本节目标：掌握Future trait与Poll机制、async块/函数的语法糖本质、Pin/Unpin与自引用结构的关系、手动poll状态机变换、Waker唤醒机制，理解零成本async的本质，并能对比C++20 coroutine的差异。

## 本章速览

- [1. Future trait与Poll机制](#1-future-trait与poll机制)
  - [1.1 Future trait定义](#11-future-trait定义)
  - [1.2 Poll::Ready与Pending](#12-pollready与pending)
  - [1.3 简单Future实现](#13-简单future实现)
- [2. async块/函数语法糖](#2-async块函数语法糖)
  - [2.1 async fn的状态机变换](#21-async-fn的状态机变换)
  - [2.2 .await的工作原理](#22-await的工作原理)
- [3. Pin/Unpin与自引用结构](#3-pinunpin与自引用结构)
  - [3.1 为什么需要Pin](#31-为什么需要pin)
  - [3.2 Pin的API与Unpin](#32-pin的api与unpin)
  - [3.3 自引用结构与Pin](#33-自引用结构与pin)
- [4. Waker唤醒机制](#4-waker唤醒机制)
  - [4.1 Waker的作用](#41-waker的作用)
  - [4.2 自定义Waker实现](#42-自定义waker实现)
- [5. 手动poll状态机变换](#5-手动poll状态机变换)
- [6. 零成本async本质](#6-零成本async本质)
- [7. 对比C++20 coroutine](#7-对比c20-coroutine)
- [8. 本节小结](#8-本节小结)

---

## 1. Future trait与Poll机制

### 1.1 Future trait定义

`Future`是Rust异步编程的核心trait，定义了一个异步计算的抽象：

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
- `poll`：尝试推进异步计算，返回`Poll::Ready(value)`（完成）或`Poll::Pending`（未完成）
- `Pin<&mut Self>`：保证Future在内存中不会被移动（详见第3节）
- `Context<'_>`：提供`Waker`，用于在Future就绪时通知执行器

### 1.2 Poll::Ready与Pending

`Poll`是一个简单的枚举：

```rust
pub enum Poll<T> {
    Ready(T),    // 计算完成，携带结果
    Pending,     // 计算未完成，需要等待
}
```

poll的契约：
- 返回`Pending`时，Future必须在将来某个时刻通过`Waker`通知执行器再次poll
- 返回`Ready`后，Future不应该再被poll（再次poll的行为未定义）
- poll是**非阻塞**的：如果不能立即完成，必须返回Pending，不能阻塞线程

### 1.3 简单Future实现

一个立即返回值的Future：

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

一个需要等待的Future（定时器）：

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

## 2. async块/函数语法糖

### 2.1 async fn的状态机变换

`async fn`是语法糖，编译器将其变换为一个实现了`Future` trait的状态机结构体。

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
1. 每个`.await`点是一个状态边界
2. 跨`.await`点存活的变量被保存在状态机结构体中
3. 不跨`.await`点的变量是普通局部变量，在栈上分配
4. poll方法是一个循环，根据当前状态执行对应的代码段

### 2.2 .await的工作原理

`.await`的本质是：**poll子Future，如果Pending就保存状态并返回Pending，如果Ready就解包值继续执行**。

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

async块也是语法糖：

```rust
// async块
let fut = async {
    let x = compute().await;
    x + 1
};

// 等价于一个匿名的Future状态机
```

## 3. Pin/Unpin与自引用结构

### 3.1 为什么需要Pin

async状态机可能包含**自引用**：一个字段引用了同一个结构体中的另一个字段。

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

如果这个Future在内存中被移动（例如从栈移到堆，或在`Vec`中重新分配），`ref_to_data`指针就会悬空。

```text
移动前：                        移动后：
┌─────────────────────┐        ┌─────────────────────┐
│ data: [1, 2, 3]    │        │ data: [1, 2, 3]    │
│ ref_to_data: 0x1000 │──┐     │ ref_to_data: 0x1000 │──┐ 悬空！
└─────────────────────┘  │     └─────────────────────┘  │
  地址 0x1000             │       地址 0x2000             │
                          └──指向0x1000                     └──仍指向0x1000（已失效）
```

`Pin`的作用：**阻止值被移动**，保证自引用指针始终有效。

### 3.2 Pin的API与Unpin

`Pin<P>`是一个指针包装器，保证指针指向的值不会被移动：

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

`Pin`的关键API：

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

### 3.3 自引用结构与Pin

手动实现一个自引用结构（需要unsafe）：

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

## 4. Waker唤醒机制

### 4.1 Waker的作用

`Waker`是执行器和Future之间的通知机制：
- Future在poll时收到`Context`，从中获取`Waker`
- Future返回Pending时，保存`Waker`
- 当Future就绪时（如IO完成、定时器到期），调用`waker.wake()`通知执行器
- 执行器收到通知后，再次poll这个Future

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

### 4.2 自定义Waker实现

简化执行器展示Waker核心机制：

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

核心：Task实现Wake trait，wake时把自己放回任务队列，执行器不断从队列取任务poll。实际执行器（Tokio）在此基础上增加IO驱动、定时器、work-stealing等。

## 5. 手动poll状态机变换

手动实现状态机，等价于`async { let x = step1().await; let y = step2(x).await; y + 1 }`：

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

核心：enum每个变体代表一个状态，poll方法匹配当前状态、推进计算、转移到下一状态。跨await的变量（如`x`）保存在状态变体字段中。

## 6. 零成本async本质

Rust的async是**零成本抽象**：

1. **无运行时开销**：async fn编译为状态机结构体，没有堆分配（除非显式`Box::pin`）、没有虚函数调用、没有GC
2. **无调度器开销**：Future本身不包含调度逻辑，调度由外部执行器负责
3. **编译期优化**：状态机的poll方法可以被LLVM内联和优化，简单的async代码可能完全优化为同步代码
4. **按需分配**：只有跨await点的变量才保存在状态机中，不跨await的变量是普通栈变量

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

对照C++20 coroutine：C++20的coroutine默认有堆分配（promise对象在堆上），虽然编译器可以做堆分配消除（HALO），但不保证。Rust的async状态机默认在栈上，只有显式`Box::pin`才堆分配。

## 7. 对比C++20 coroutine

| 特性 | Rust async/await | C++20 coroutine |
|------|-------------------|------------------|
| 核心抽象 | `Future` trait | `coroutine_handle` + promise |
| 状态机 | 编译器生成匿名结构体 | 编译器生成coroutine frame |
| 默认分配 | 栈上（无堆分配） | 堆上（promise在堆） |
| 移动安全 | `Pin`保证不移动 | 无Pin，coroutine frame地址稳定 |
| 唤醒机制 | `Waker` trait | `coroutine_handle::resume()` |
| 执行器 | 外部执行器（Tokio等） | 无标准执行器，需自行实现 |
| 组合子 | `futures` crate提供 | 无标准库支持，需第三方库 |
| 取消 | drop Future即取消 | 需手动实现取消逻辑 |
| 错误处理 | `Result` + `?` | 异常或返回错误码 |
| 生态 | Tokio/async-std/smol | cppcoro/libunifex |

C++20 coroutine的关键差异：

```cpp
// C++20 coroutine示例（概念性）
#include <coroutine>

task<int> fetch_data() {
    auto response = co_await http_get("url");
    auto parsed = co_await parse(response);
    co_return parsed;
}
```

C++ coroutine的promise类型决定了coroutine的行为（是否堆分配、返回值类型等），需要大量模板元编程。Rust的async设计更统一：所有async fn都返回实现Future的类型，行为一致。

Rust的取消模型更安全：drop Future就取消了，因为状态机的drop会递归drop所有字段。C++ coroutine需要手动实现取消，容易泄漏资源。

## 8. 本节小结

- **Future trait**：`poll(self: Pin<&mut Self>, cx: &mut Context) -> Poll<Output>`是异步计算的核心抽象。返回`Ready(value)`表示完成，`Pending`表示未完成且会通过Waker通知。
- **async fn语法糖**：编译器将async fn变换为状态机结构体，每个`.await`点是状态边界，跨await的变量保存在状态机字段中。poll方法根据当前状态推进计算。
- **Pin/Unpin**：Pin保证值不被移动，解决async状态机的自引用问题。`PhantomPinned`使类型`!Unpin`。大多数普通类型自动`Unpin`。`pin!`在栈上创建Pin值，`Box::pin`在堆上创建。
- **Waker唤醒**：Future在Pending时保存Waker，就绪时调用`wake()`通知执行器重新poll。Task实现Wake trait，wake时把自己放回任务队列。
- **手动状态机**：用enum表示状态，poll方法匹配状态并推进，清晰展示async的本质。
- **零成本async**：无堆分配（默认）、无虚函数、无GC，状态机可被LLVM深度优化。简单async代码可能完全优化为同步代码。
- **对比C++20 coroutine**：Rust默认栈分配（C++默认堆分配）、Pin保证移动安全（C++无Pin）、统一的Future抽象（C++需自定义promise）、drop即取消（C++需手动取消）。async的底层IO依赖epoll/io_uring的Reactor模型，对照《../../01-C++技术体系/03-网络编程/02-IO多路复用与Reactor模型.md》理解事件驱动本质。

---

上一篇：《02-锁原子与无锁结构.md》
下一篇：《04-Tokio运行时与异步生态.md》
