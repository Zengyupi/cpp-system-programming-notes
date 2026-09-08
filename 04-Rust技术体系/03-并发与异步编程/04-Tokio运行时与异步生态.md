# Tokio运行时与异步生态

> 本节目标：掌握Tokio运行时的核心机制——#[tokio::main]、多线程work-stealing调度器、spawn/block_on、TcpListener异步IO（对照epoll/io_uring/Reactor）、tokio::sync原语、select!与超时取消，了解async-std/smol对比，并能进行运行时选型。

## 本章速览

- [1. Tokio运行时基础](#1-tokio运行时基础)
  - [1.1 #\[tokio::main\]与运行时创建](#11-tokiomain与运行时创建)
  - [1.2 block_on与spawn](#12-block_on与spawn)
  - [1.3 多线程work-stealing调度器](#13-多线程work-stealing调度器)
- [2. 异步IO与Reactor模型](#2-异步io与reactor模型)
  - [2.1 TcpListener异步接收](#21-tcplistener异步接收)
  - [2.2 对照epoll/io_uring/Reactor](#22-对照epollio_uringreactor)
- [3. tokio::sync同步原语](#3-tokiosync同步原语)
  - [3.1 mpsc通道](#31-mpsc通道)
  - [3.2 oneshot与watch](#32-oneshot与watch)
  - [3.3 异步Mutex/RwLock](#33-异步mutexrwlock)
  - [3.4 Notify与Barrier](#34-notify与barrier)
- [4. select!与超时取消](#4-select与超时取消)
  - [4.1 select!宏](#41-select宏)
  - [4.2 超时与取消](#42-超时与取消)
- [5. async-std与smol对比](#5-async-std与smol对比)
- [6. 运行时选型](#6-运行时选型)
- [7. 本节小结](#7-本节小结)

---

## 1. Tokio运行时基础

### 1.1 #[tokio::main]与运行时创建

`#[tokio::main]`是一个属性宏，将`async fn main`变换为同步`fn main`并创建运行时：

```toml
# Cargo.toml
[dependencies]
tokio = { version = "1", features = ["full"] }
```

（tokio版本以crates.io最新稳定版为准）

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

`#[tokio::main]`的等价展开（概念上）：

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

### 1.2 block_on与spawn

`block_on`阻塞当前线程直到Future完成：

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

`spawn`创建一个异步任务，在后台并发执行，返回`JoinHandle`：

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

`spawn`的要求：Future必须是`Send + 'static`的，因为任务可能在不同线程上执行，且可能比当前作用域活得久。

`spawn_local`用于当前线程运行时，不需要`Send`：

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

### 1.3 多线程work-stealing调度器

Tokio的多线程运行时使用work-stealing调度器：

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

work-stealing的核心机制：
1. 每个工作线程有自己的任务队列（双端队列）
2. 线程从自己队列的头部取任务执行
3. 当队列为空时，从其他线程队列的尾部"偷"任务
4. 新spawn的任务放入当前线程的队列
5. IO事件和定时器由专门的驱动线程处理，就绪后唤醒工作线程

这种设计的优势：
- **负载均衡**：空闲线程自动从繁忙线程偷任务
- **低竞争**：每个线程主要操作自己的队列，减少锁竞争
- **缓存友好**：任务倾向于在同一个线程上执行，提高CPU缓存命中率

对照C++：C++没有标准的异步运行时，需要自己实现线程池或使用第三方库（如`boost::asio`的线程池）。Tokio的work-stealing调度器与Intel TBB的任务调度器类似，但Tokio集成了IO驱动和定时器，是完整的异步运行时。

## 2. 异步IO与Reactor模型

### 2.1 TcpListener异步接收

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
- 每个连接一个`tokio::spawn`任务，并发处理
- `read`/`write_all`都是异步的，IO等待时不阻塞
- 单线程可以处理数千个并发连接

### 2.2 对照epoll/io_uring/Reactor

Tokio的IO驱动在Linux上使用epoll（或io_uring，如果启用），实现Reactor模式：

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

对照C++的Reactor实现（如`boost::asio`、`libevent`、`libuv`）：

| 特性 | Tokio | boost::asio | libevent/libuv |
|------|-------|-------------|----------------|
| 异步模型 | async/await + Future | 回调/协程（C++20） | 回调 |
| IO多路复用 | epoll/io_uring/kqueue | epoll/io_uring/kqueue | epoll/kqueue |
| 调度器 | work-stealing线程池 | 线程池（需手动配置） | 单线程事件循环 |
| 类型安全 | 强类型Future | 回调参数类型检查弱 | 弱类型回调 |
| 取消 | drop Future即取消 | 需手动取消 | 需手动取消 |
| 错误处理 | Result + ? | error_code/异常 | 错误码回调 |

交叉引用：IO多路复用与Reactor模型的底层原理详见《../../01-C++技术体系/03-网络编程/02-IO多路复用与Reactor模型.md》。Tokio的异步IO本质上是epoll/io_uring的Rust封装，加上Future/Waker的通知机制。

## 3. tokio::sync同步原语

### 3.1 mpsc通道

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
- 发送时如果通道满，`send().await`会挂起等待
- 接收时如果通道空，`recv().await`会挂起等待
- 所有发送者drop后，recv返回None

无界通道（`mpsc::unbounded_channel`）：发送不会阻塞，但可能无限增长内存。

### 3.2 oneshot与watch

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

oneshot常用于：任务间传递一次性结果、取消信号、异步初始化通知。

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

watch适用于：配置更新、状态广播、最新值通知（不需要历史值）。

### 3.3 异步Mutex/RwLock

Tokio的异步锁与`std::sync::Mutex`的区别：lock是异步的，等待时不阻塞线程：

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

**重要**：在异步代码中应该用`tokio::sync::Mutex`而不是`std::sync::Mutex`，因为`std::sync::Mutex::lock()`会阻塞线程，可能导致整个运行时的线程池被阻塞（所有任务都无法执行）。

但如果锁的持有时间很短（微秒级），且不会在持有锁时await，`std::sync::Mutex`的性能更好（没有异步开销）。选择原则：
- 持有锁期间有await → 用`tokio::sync::Mutex`
- 持有锁期间无await，且锁竞争不激烈 → 用`std::sync::Mutex`

### 3.4 Notify与Barrier

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

`select!`同时等待多个Future，哪个先完成就执行哪个分支：

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
- 第一个完成的分支被执行，其他分支被drop（取消）
- 所有分支都必须返回相同类型（如果有返回值）
- 默认随机选择分支（公平性），`biased`优先第一个分支
- 可以用`else`分支处理所有Future都Pending的情况

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

**取消语义**：Rust的Future取消是协作式的——drop Future就取消了。被取消的Future的drop会递归drop所有字段，释放资源。

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
- **协作式取消**：Future只能在`.await`点被取消，正在执行的同步代码不会被中断
- **资源清理**：drop会自动清理，但如果有`spawn`的子任务，子任务不会自动取消（需要abort）
- **半取消状态**：如果Future在修改数据的中间被取消，数据可能处于不一致状态，需要在设计时考虑

## 5. async-std与smol对比

| 特性 | Tokio | async-std | smol |
|------|-------|-----------|------|
| 调度器 | work-stealing多线程 | work-stealing多线程 | 可插拔（默认单线程） |
| 生态成熟度 | 最高 | 中等 | 较低 |
| 二进制体积 | 较大 | 中等 | 小 |
| 企业采用 | 最广泛（AWS、Cloudflare） | 较少 | 较少 |

async-std设计目标是"像std一样的异步API"，smol是极简运行时可嵌入任何应用。Tokio是事实标准，除非有特殊需求（极小体积、特定API风格），否则推荐Tokio。

## 6. 运行时选型

选型决策：网络服务/高并发→Tokio（生态最成熟，性能最优）；嵌入式/资源受限→smol（体积小）；偏好std风格API→async-std。Tokio是事实标准，除非有特殊需求否则推荐Tokio。

最佳实践：不要嵌套运行时、不要在异步代码中阻塞（用`spawn_blocking`）、持有锁期间await用异步锁、合理设置worker线程数、使用有界通道做backpressure。

## 7. 本节小结

- **Tokio运行时**：`#[tokio::main]`宏创建运行时，`block_on`阻塞执行Future，`spawn`创建并发任务。多线程运行时使用work-stealing调度器，空闲线程从繁忙线程偷任务，实现负载均衡。
- **异步IO**：`TcpListener::accept().await`在等待连接时挂起任务，不阻塞线程。Tokio在Linux上用epoll/io_uring实现Reactor模式，IO事件就绪后通过Waker唤醒任务。交叉引用《../../01-C++技术体系/03-网络编程/02-IO多路复用与Reactor模型.md》。
- **tokio::sync**：mpsc通道（多生产者单消费者，有界/无界）、oneshot（一次性通知）、watch（最新值广播）、异步Mutex/RwLock（lock是异步的）、Notify（任务通知）。异步锁用于持有锁期间有await的场景。
- **select!**：同时等待多个Future，先完成的执行，其他取消。`timeout`实现超时，超时后Future被drop取消。Rust的取消是协作式的，只能在await点取消。
- **async-std/smol**：async-std提供std风格API，smol是极简运行时。Tokio是事实标准，生态最成熟、性能最优、企业采用最广泛。
- 选型：网络服务用Tokio，资源受限用smol，偏好std风格用async-std。最佳实践：不嵌套运行时、不阻塞异步线程、合理选锁、使用backpressure。

---

上一篇：《03-Future状态机与async原理.md》
下一篇：《05-并发架构模式.md》
