# Tokio 运行时与异步生态

> 本节目标：掌握 Tokio 运行时的核心机制——#[tokio::main]、多线程 work-stealing 调度器、spawn/block_on、TcpListener 异步 IO（对照 epoll/io_uring/Reactor）、tokio::sync 原语、select!与超时取消，了解 async-std/smol 对比，并能进行运行时选型。

## 本章速览

- [1. Tokio 运行时基础](#1-tokio-运行时基础)
  - [1.1 #\[tokio::main\]与运行时创建](#11-tokiomain与运行时创建)
  - [1.2 block_on 与 spawn](#12-block_on-与-spawn)
  - [1.3 多线程 work-stealing 调度器](#13-多线程-work-stealing-调度器)
- [2. 异步 IO 与 Reactor 模型](#2-异步-io-与-reactor-模型)
  - [2.1 TcpListener 异步接收](#21-tcplistener-异步接收)
  - [2.2 对照 epoll/io_uring/Reactor](#22-对照-epollio_uringreactor)
- [3. tokio::sync 同步原语](#3-tokiosync-同步原语)
  - [3.1 mpsc 通道](#31-mpsc-通道)
  - [3.2 oneshot 与 watch](#32-oneshot-与-watch)
  - [3.3 异步 Mutex/RwLock](#33-异步-mutexrwlock)
  - [3.4 Notify 与 Barrier](#34-notify-与-barrier)
- [4. select!与超时取消](#4-select与超时取消)
  - [4.1 select!宏](#41-select宏)
  - [4.2 超时与取消](#42-超时与取消)
- [5. async-std 与 smol 对比](#5-async-std-与-smol-对比)
- [6. 运行时选型](#6-运行时选型)
- [7. 快速参考卡片](#7-快速参考卡片)
- [8. 常见坑](#8-常见坑)
- [9. 本节小结](#9-本节小结)

---

## 1. Tokio 运行时基础

### 1.1 #[tokio::main]与运行时创建

`#[tokio::main]` 是一个属性宏，将 `async fn main` 变换为同步 `fn main` 并创建运行时：

```toml
# Cargo.toml
[dependencies]
tokio = { version = "1", features = ["full"] }
```

（tokio 版本以 crates.io 最新稳定版为准）

```rust
// 使用#[tokio::main]宏
#[tokio::main]
async fn main() {
    println!("在Tokio运行时中执行");
    let result = async_computation().await;
    println!("结果: {}", result);
}

async fn async_computation() -> i32 {
    42
}
```

`#[tokio::main]` 的等价展开（概念上）：

```rust
fn main() {
    // 创建多线程运行时
    let runtime = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
        .unwrap();

    // 在运行时中执行async main
    runtime.block_on(async {
        println!("在Tokio运行时中执行");
        let result = async_computation().await;
        println!("结果: {}", result);
    });
}
```

手动配置运行时：

```rust
use tokio::runtime::Builder;

fn main() {
    // 多线程运行时（默认）
    let rt = Builder::new_multi_thread()
        .worker_threads(4)        // 工作线程数（默认等于CPU核心数）
        .max_blocking_threads(10) // 最大阻塞线程数
        .thread_name("my-worker")  // 线程名前缀
        .stack_size(8 * 1024 * 1024) // 栈大小
        .enable_time()             // 启用时间驱动（sleep/timeout）
        .enable_io()               // 启用IO驱动
        .build()
        .unwrap();

    rt.block_on(async {
        println!("自定义运行时");
    });

    // 当前线程运行时（单线程，所有任务在一个线程上执行）
    let current_rt = Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap();

    current_rt.block_on(async {
        println!("当前线程运行时");
    });
}
```

### 1.2 block_on 与 spawn

`block_on` 阻塞当前线程直到 Future 完成：

```rust
use tokio::runtime::Runtime;

fn main() {
    let rt = Runtime::new().unwrap();

    // block_on阻塞当前线程，直到future完成
    let result = rt.block_on(async {
        // 这里可以await
        tokio::time::sleep(std::time::Duration::from_millis(100)).await;
        42
    });

    println!("结果: {}", result);
}
```

`spawn` 创建一个异步任务，在后台并发执行，返回 `JoinHandle`：

```rust
use tokio::task;

#[tokio::main]
async fn main() {
    // spawn创建任务，立即返回，不等待
    let handle = task::spawn(async {
        println!("任务1开始");
        tokio::time::sleep(std::time::Duration::from_millis(100)).await;
        println!("任务1完成");
        42
    });

    // 同时执行其他工作
    println!("主任务继续");

    // await JoinHandle等待任务完成
    let result = handle.await.unwrap();
    println!("任务1结果: {}", result);

    // spawn多个任务
    let mut handles = vec![];
    for i in 0..5 {
        handles.push(task::spawn(async move {
            tokio::time::sleep(std::time::Duration::from_millis(i * 10)).await;
            i * 2
        }));
    }

    for h in handles {
        println!("{}", h.await.unwrap());
    }
}
```

`spawn` 的要求：Future 必须是 `Send + 'static` 的，因为任务可能在不同线程上执行，且可能比当前作用域活得久。

`spawn_local` 用于当前线程运行时，不需要 `Send`：

```rust
use tokio::task;

#[tokio::main(flavor = "current_thread")]
async fn main() {
    // spawn_local不需要Send，因为任务在当前线程执行
    let handle = task::spawn_local(async {
        // 可以使用!Send的类型
        let rc = std::rc::Rc::new(42);
        println!("{}", rc);
    });

    handle.await.unwrap();
}
```

### 1.3 多线程 work-stealing 调度器

Tokio 的多线程运行时使用 work-stealing 调度器：

```text
工作线程池（4个线程）：

┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│ Worker 0 │  │ Worker 1 │  │ Worker 2 │  │ Worker 3 │
│ 任务队列  │  │ 任务队列  │  │ 任务队列  │  │ 任务队列  │
│ [A, B, C]│  │ [D, E]   │  │ [] 空    │  │ [F]      │
└────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘
     │              │              │              │
     └──────────────┴──────┬───────┴──────────────┘
                            │
                    Work-stealing：
                    Worker 2队列为空时，
                    从其他Worker的队列"偷"任务
```

work-stealing 的核心机制：
1. 每个工作线程有自己的任务队列（双端队列）
2. 线程从自己队列的头部取任务执行
3. 当队列为空时，从其他线程队列的尾部"偷"任务
4. 新 spawn 的任务放入当前线程的队列
5. IO 事件和定时器由专门的驱动线程处理，就绪后唤醒工作线程

这种设计的优势：
- **负载均衡**：空闲线程自动从繁忙线程偷任务
- **低竞争**：每个线程主要操作自己的队列，减少锁竞争
- **缓存友好**：任务倾向于在同一个线程上执行，提高 CPU 缓存命中率

对照 C++：C++没有标准的异步运行时，需要自己实现线程池或使用第三方库（如 `boost::asio` 的线程池）。Tokio 的 work-stealing 调度器与 Intel TBB 的任务调度器类似，但 Tokio 集成了 IO 驱动和定时器，是完整的异步运行时。

## 2. 异步 IO 与 Reactor 模型

### 2.1 TcpListener 异步接收

```rust
use tokio::net::TcpListener;
use tokio::io::{AsyncReadExt, AsyncWriteExt};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let listener = TcpListener::bind("127.0.0.1:8080").await?;
    println!("监听 127.0.0.1:8080");

    loop {
        // accept是异步的，等待连接时不阻塞线程
        let (mut socket, addr) = listener.accept().await?;
        println!("新连接: {}", addr);

        // 为每个连接spawn一个任务
        tokio::spawn(async move {
            let mut buf = [0; 1024];

            loop {
                // 异步读取
                match socket.read(&mut buf).await {
                    Ok(0) => {
                        println!("连接关闭: {}", addr);
                        break;
                    }
                    Ok(n) => {
                        // 异步写回（echo）
                        if socket.write_all(&buf[..n]).await.is_err() {
                            break;
                        }
                    }
                    Err(e) => {
                        eprintln!("读取错误: {}", e);
                        break;
                    }
                }
            }
        });
    }
}
```

关键特性：
- `accept().await`：等待连接时，当前任务被挂起，线程可以执行其他任务
- 每个连接一个 `tokio::spawn` 任务，并发处理
- `read`/`write_all` 都是异步的，IO 等待时不阻塞
- 单线程可以处理数千个并发连接

### 2.2 对照 epoll/io_uring/Reactor

Tokio 的 IO 驱动在 Linux 上使用 epoll（或 io_uring，如果启用），实现 Reactor 模式：

```text
Reactor模式架构：

应用任务（Task）
    │
    │ 调用 TcpListener::accept().await
    ▼
Future（poll时注册IO事件到Reactor）
    │
    ▼
Reactor（IO驱动线程）
    │
    │  epoll_wait / io_uring_enter
    ▼
内核（TCP栈）
    │
    │  事件就绪（连接到达、数据可读）
    ▼
Reactor收到事件，通过Waker唤醒对应Task
    │
    ▼
Task被重新poll，accept返回Ready
```

对照 C++的 Reactor 实现（如 `boost::asio`、`libevent`、`libuv`）：

| 特性 | Tokio | boost::asio | libevent/libuv |
|------|-------|-------------|----------------|
| 异步模型 | async/await + Future | 回调/协程（C++20） | 回调 |
| IO 多路复用 | epoll/io_uring/kqueue | epoll/io_uring/kqueue | epoll/kqueue |
| 调度器 | work-stealing 线程池 | 线程池（需手动配置） | 单线程事件循环 |
| 类型安全 | 强类型 Future | 回调参数类型检查弱 | 弱类型回调 |
| 取消 | drop Future 即取消 | 需手动取消 | 需手动取消 |
| 错误处理 | Result + ? | error_code/异常 | 错误码回调 |

交叉引用：IO 多路复用与 Reactor 模型的底层原理详见《../../01-C++技术体系/03-网络编程/02-IO多路复用与Reactor模型.md》。Tokio 的异步 IO 本质上是 epoll/io_uring 的 Rust 封装，加上 Future/Waker 的通知机制。

## 3. tokio::sync 同步原语

### 3.1 mpsc 通道

mpsc（multi-producer, single-consumer）是异步通道，多个发送者，一个接收者：

```rust
use tokio::sync::mpsc;

#[tokio::main]
async fn main() {
    // 创建有界通道，容量为10
    let (tx, mut rx) = mpsc::channel(10);

    // 多个生产者
    for i in 0..3 {
        let tx = tx.clone();
        tokio::spawn(async move {
            for j in 0..5 {
                tx.send(format!("生产者{}: 消息{}", i, j)).await.unwrap();
            }
        });
    }
    drop(tx); // 丢弃原始发送者

    // 单个消费者
    while let Some(msg) = rx.recv().await {
        println!("收到: {}", msg);
    }
    println!("所有发送者已关闭，通道结束");
}
```

有界通道的特性：
- 发送时如果通道满，`send().await` 会挂起等待
- 接收时如果通道空，`recv().await` 会挂起等待
- 所有发送者 drop 后，recv 返回 None

无界通道（`mpsc::unbounded_channel`）：发送不会阻塞，但可能无限增长内存。

### 3.2 oneshot 与 watch

**oneshot**：一次性通道，发送一个值：

```rust
use tokio::sync::oneshot;

#[tokio::main]
async fn main() {
    let (tx, rx) = oneshot::channel();

    tokio::spawn(async move {
        // 做一些计算
        tokio::time::sleep(std::time::Duration::from_millis(100)).await;
        tx.send(42).unwrap(); // 发送一次
    });

    // 等待结果
    let result = rx.await.unwrap();
    println!("结果: {}", result);
}
```

oneshot 常用于：任务间传递一次性结果、取消信号、异步初始化通知。

**watch**：单值广播通道，接收者总是获取最新值：

```rust
use tokio::sync::watch;

#[tokio::main]
async fn main() {
    let (tx, rx) = watch::channel(0); // 初始值0

    // 多个接收者
    for i in 0..3 {
        let mut rx = rx.clone();
        tokio::spawn(async move {
            while rx.changed().await.is_ok() {
                println!("接收者{}: 值变为{}", i, *rx.borrow());
            }
        });
    }

    // 发送者更新值
    for v in 1..=5 {
        tx.send(v).unwrap();
        tokio::time::sleep(std::time::Duration::from_millis(10)).await;
    }
}
```

watch 适用于：配置更新、状态广播、最新值通知（不需要历史值）。

### 3.3 异步 Mutex/RwLock

Tokio 的异步锁与 `std::sync::Mutex` 的区别：lock 是异步的，等待时不阻塞线程：

```rust
use tokio::sync::Mutex;
use std::sync::Arc;

#[tokio::main]
async fn main() {
    let data = Arc::new(Mutex::new(0));
    let mut handles = vec![];

    for _ in 0..10 {
        let data = Arc::clone(&data);
        handles.push(tokio::spawn(async move {
            // 异步lock：等待时挂起任务，不阻塞线程
            let mut guard = data.lock().await;
            *guard += 1;
            // guard drop时释放锁
        }));
    }

    for h in handles {
        h.await.unwrap();
    }

    println!("结果: {}", *data.lock().await); // 10
}
```

**重要**：在异步代码中应该用 `tokio::sync::Mutex` 而不是 `std::sync::Mutex`，因为 `std::sync::Mutex::lock()` 会阻塞线程，可能导致整个运行时的线程池被阻塞（所有任务都无法执行）。

但如果锁的持有时间很短（微秒级），且不会在持有锁时 await，`std::sync::Mutex` 的性能更好（没有异步开销）。选择原则：
- 持有锁期间有 await → 用 `tokio::sync::Mutex`
- 持有锁期间无 await，且锁竞争不激烈 → 用 `std::sync::Mutex`

### 3.4 Notify 与 Barrier

**Notify**：异步通知原语，一个或多个任务等待通知：

```rust
use tokio::sync::Notify;
use std::sync::Arc;

#[tokio::main]
async fn main() {
    let notify = Arc::new(Notify::new());

    // 等待任务
    let notify_clone = Arc::clone(&notify);
    tokio::spawn(async move {
        println!("等待通知...");
        notify_clone.notified().await;
        println!("收到通知！");
    });

    // 发送通知
    tokio::time::sleep(std::time::Duration::from_millis(100)).await;
    notify.notify_one(); // 唤醒一个等待者
    // notify.notify_waiters(); // 唤醒所有等待者
}
```

## 4. select!与超时取消

### 4.1 select!宏

`select!` 同时等待多个 Future，哪个先完成就执行哪个分支：

```rust
use tokio::sync::mpsc;
use tokio::time::{sleep, Duration};

#[tokio::main]
async fn main() {
    let (tx, mut rx) = mpsc::channel::<i32>(10);

    // 发送任务
    tokio::spawn(async move {
        sleep(Duration::from_millis(50)).await;
        tx.send(42).await.unwrap();
    });

    // select：同时等待消息和超时
    tokio::select! {
        msg = rx.recv() => {
            println!("收到消息: {:?}", msg);
        }
        _ = sleep(Duration::from_millis(100)) => {
            println!("超时！");
        }
    }

    // 带biased的select：优先检查第一个分支
    // tokio::select! {
    //     biased;
    //     msg = rx.recv() => { ... }
    //     _ = sleep(...) => { ... }
    // }
}
```

select!的规则：
- 第一个完成的分支被执行，其他分支被 drop（取消）
- 所有分支都必须返回相同类型（如果有返回值）
- 默认随机选择分支（公平性），`biased` 优先第一个分支
- 可以用 `else` 分支处理所有 Future 都 Pending 的情况

### 4.2 超时与取消

超时是异步编程的常见需求：

```rust
use tokio::time::{timeout, Duration};

#[tokio::main]
async fn main() {
    // timeout：如果future在指定时间内未完成，返回Err
    let result = timeout(
        Duration::from_millis(100),
        async {
            // 模拟耗时操作
            tokio::time::sleep(Duration::from_millis(200)).await;
            42
        }
    ).await;

    match result {
        Ok(v) => println!("成功: {}", v),
        Err(_) => println!("超时！"),
    }
}
```

**取消语义**：Rust 的 Future 取消是协作式的——drop Future 就取消了。被取消的 Future 的 drop 会递归 drop 所有字段，释放资源。

```rust
use tokio::time::{timeout, Duration};
use tokio::sync::oneshot;

#[tokio::main]
async fn main() {
    let (tx, rx) = oneshot::channel();

    // 这个任务会被超时取消
    let handle = tokio::spawn(async move {
        // 等待oneshot，但会被超时取消
        let _ = rx.await; // 被取消时，rx被drop，tx.send会返回Err
        println!("这行不会执行");
    });

    // 超时取消任务
    let _ = timeout(Duration::from_millis(50), async {
        handle.await.unwrap();
    }).await;

    // 发送者发现接收者已被取消
    let result = tx.send(42);
    println!("发送结果: {:?}", result); // Err(42)：接收者已drop
}
```

取消的注意事项：
- **协作式取消**：Future 只能在 `.await` 点被取消，正在执行的同步代码不会被中断
- **资源清理**：drop 会自动清理，但如果有 `spawn` 的子任务，子任务不会自动取消（需要 abort）
- **半取消状态**：如果 Future 在修改数据的中间被取消，数据可能处于不一致状态，需要在设计时考虑

## 5. async-std 与 smol 对比

| 特性 | Tokio | async-std | smol |
|------|-------|-----------|------|
| 调度器 | work-stealing 多线程 | work-stealing 多线程 | 可插拔（默认单线程） |
| 生态成熟度 | 最高 | 中等 | 较低 |
| 二进制体积 | 较大 | 中等 | 小 |
| 企业采用 | 最广泛（AWS、Cloudflare） | 较少 | 较少 |

async-std 设计目标是"像 std 一样的异步 API"，smol 是极简运行时可嵌入任何应用。Tokio 是事实标准，除非有特殊需求（极小体积、特定 API 风格），否则推荐 Tokio。

## 6. 运行时选型

选型决策：网络服务/高并发→Tokio（生态最成熟，性能最优）；嵌入式/资源受限→smol（体积小）；偏好 std 风格 API→async-std。Tokio 是事实标准，除非有特殊需求否则推荐 Tokio。

最佳实践：不要嵌套运行时、不要在异步代码中阻塞（用 `spawn_blocking`）、持有锁期间 await 用异步锁、合理设置 worker 线程数、使用有界通道做 backpressure。

## 7. 快速参考卡片

| 查询点 | 速答 |
| --- | --- |
| 入口 | `#[tokio::main]`（默认多线程 runtime）；手工 `Runtime::new()?.block_on(fut)` |
| spawn | `tokio::spawn(async {...})` 要求 `Send + 'static`，返回 `JoinHandle`；`spawn_local` 用于 `!Send` |
| 运行时形态 | `multi_thread`（work-stealing，默认）/`current_thread`（单线程，测试友好） |
| Reactor | `TcpListener`/`AsyncRead`/`AsyncWrite` 背后是 epoll/kqueue/IOCP，与 C++ Reactor 同源 |
| mpsc | `mpsc::channel(n)` 有界通道，`tx.send().await` 提供背压；`rx.recv().await` 返回 `Option` |
| oneshot/watch | 请求-应答一次（oneshot）/ 状态广播（watch，`borrow()` 读最新） |
| 异步同步原语 | `tokio::sync::{Mutex, RwLock, Semaphore, Notify, Barrier}` |
| select! | 多 Future 竞速；未完成分支被 drop（注意取消安全） |
| 超时取消 | `tokio::time::timeout(dur, fut)` 返回 `Result<T, Elapsed>`，超时即取消 |
| 选型 | tokio（生态最全、生产首选）/ async-std（类 std）/ smol（轻量、库友好） |

---

## 8. 常见坑

### 坑 1：在 async 中跨 `await` 持有 `std::sync::MutexGuard`

见前两篇同类坑：会导致 Future 不 `Send`，`tokio::spawn` 编译失败。异步共享状态用 `tokio::sync::Mutex`，或把临界区收缩到不含 await。

### 坑 2：任务里跑重 CPU 计算

一个 `for _ in 0..10_000_000 {}` 就会占住 worker 线程，其它任务全部延迟（表现为"偶发超时"）。用 `spawn_blocking`、专用 rayon 线程池，或分片 `yield_now().await`。

### 坑 3：嵌套运行时

在 runtime 内再 `block_on` 会 panic：*Cannot start a runtime from within a runtime*。库代码不要创建 runtime，只提供 async 函数；需要同步接口时用 `Handle::current().block_on` 之外的手段（如 `block_in_place`）。

### 坑 4：spawn 出去的任务错误被吞掉

`tokio::spawn` 的返回 `JoinHandle` 一旦被丢弃，任务 panic 只打印到 stderr，调用方完全不知情。要点：保留 JoinHandle 并 `.await` 收口，或用 `JoinSet` 统一收集结果。

### 坑 5：select! 分支不取消安全

`select!` 未完成的分支会被 drop。若分支内含"发送一半状态"的逻辑（如 `read_exact` 读到一半），取消后数据丢失。对策：把不取消安全的操作放进 `spawn` 后的 JoinHandle，或用 `biased;` 固定优先级。

### 坑 6：无界通道当默认选择

`mpsc::unbounded_channel()` 在生产者快于消费者时会无限吃内存。默认用有界通道 `mpsc::channel(n)`，让 `send().await` 自然形成背压。

### 坑 7：混用 `std::thread::sleep` 与 `tokio::time::sleep`

前者阻塞线程（含 executor worker），后者挂起任务让出线程。异步代码里只应出现 `tokio::time::*`。

---

## 9. 本节小结

- **Tokio 运行时**：`#[tokio::main]` 宏创建运行时，`block_on` 阻塞执行 Future，`spawn` 创建并发任务。多线程运行时使用 work-stealing 调度器，空闲线程从繁忙线程偷任务，实现负载均衡。
- **异步 IO**：`TcpListener::accept().await` 在等待连接时挂起任务，不阻塞线程。Tokio 在 Linux 上用 epoll/io_uring 实现 Reactor 模式，IO 事件就绪后通过 Waker 唤醒任务。交叉引用《../../01-C++技术体系/03-网络编程/02-IO多路复用与Reactor模型.md》。
- **tokio::sync**：mpsc 通道（多生产者单消费者，有界/无界）、oneshot（一次性通知）、watch（最新值广播）、异步 Mutex/RwLock（lock 是异步的）、Notify（任务通知）。异步锁用于持有锁期间有 await 的场景。
- **select!**：同时等待多个 Future，先完成的执行，其他取消。`timeout` 实现超时，超时后 Future 被 drop 取消。Rust 的取消是协作式的，只能在 await 点取消。
- **async-std/smol**：async-std 提供 std 风格 API，smol 是极简运行时。Tokio 是事实标准，生态最成熟、性能最优、企业采用最广泛。
- 选型：网络服务用 Tokio，资源受限用 smol，偏好 std 风格用 async-std。最佳实践：不嵌套运行时、不阻塞异步线程、合理选锁、使用 backpressure。

---

上一篇：《03-Future状态机与async原理.md》　｜　下一篇：《05-并发架构模式.md》　｜　模块索引：《../README.md》
