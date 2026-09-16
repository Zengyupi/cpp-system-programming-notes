# 线程模型与 Send-Sync

> 本节目标：掌握 std::thread 的创建与 JoinHandle、thread::scope 作用域线程、move 闭包的所有权转移机制，深入理解 Send/Sync 两个标记 trait 如何在编译期消灭数据竞争，掌握手动实现 Send/Sync 的规则与线程局部存储，能够对照 C++的 std::thread 进行迁移。

## 本章速览

- [1. std::thread 与 JoinHandle](#1-stdthread-与-joinhandle)
  - [1.1 创建线程与等待结束](#11-创建线程与等待结束)
  - [1.2 move 闭包与所有权转移](#12-move-闭包与所有权转移)
  - [1.3 线程命名与栈大小](#13-线程命名与栈大小)
- [2. thread::scope 作用域线程](#2-threadscope-作用域线程)
  - [2.1 为什么需要 scope](#21-为什么需要-scope)
  - [2.2 scope API 与借用](#22-scope-api-与借用)
- [3. Send 与 Sync：编译期数据竞争防护](#3-send-与-sync编译期数据竞争防护)
  - [3.1 Send：可跨线程转移所有权](#31-send可跨线程转移所有权)
  - [3.2 Sync：可跨线程共享引用](#32-sync可跨线程共享引用)
  - [3.3 Send/Sync 的自动推导](#33-sendsync-的自动推导)
  - [3.4 手动实现 Send/Sync 的规则](#34-手动实现-sendsync-的规则)
- [4. 线程局部存储](#4-线程局部存储)
  - [4.1 thread_local!宏](#41-thread_local宏)
  - [4.2 对比 C++thread_local](#42-对比-cthread_local)
- [5. 快速参考卡片](#5-快速参考卡片)
- [6. 常见陷阱](#6-常见陷阱)
  - [陷阱 1：忘记 join 导致主线程提前退出](#陷阱-1忘记-join-导致主线程提前退出)
  - [陷阱 2：Rc 跨线程](#陷阱-2rc-跨线程)
  - [陷阱 3：&mut 跨线程共享](#陷阱-3mut-跨线程共享)
  - [陷阱 4：手动实现 Send/Sync 但实际不安全](#陷阱-4手动实现-sendsync-但实际不安全)
- [7. 本节小结](#7-本节小结)

---

## 1. std::thread 与 JoinHandle

### 1.1 创建线程与等待结束

```rust
use std::thread;

fn main() {
    // spawn创建线程，返回JoinHandle
    let handle = thread::spawn(|| {
        for i in 1..=5 {
            println!("子线程: {}", i);
            thread::sleep(std::time::Duration::from_millis(10));
        }
    });

    // 主线程同时执行
    for i in 1..=3 {
        println!("主线程: {}", i);
        thread::sleep(std::time::Duration::from_millis(20));
    }

    // join等待子线程结束，返回Result<T>
    handle.join().expect("子线程panic了");
    println!("所有线程结束");
}
```

`JoinHandle<T>` 中的 `T` 是闭包返回值的类型。`join()` 返回 `Result<T, Box<dyn Any + Send>>`，如果子线程 panic，`join()` 返回 `Err`。

```rust
use std::thread;

fn main() {
    // 子线程返回值
    let handle = thread::spawn(|| {
        let sum: i32 = (1..=100).sum();
        sum // 返回值
    });

    let result = handle.join().unwrap();
    println!("1到100的和: {}", result); // 5050

    // 子线程panic的情况
    let panic_handle = thread::spawn(|| {
        panic!("故意panic");
    });

    match panic_handle.join() {
        Ok(_) => println!("正常结束"),
        Err(e) => println!("线程panic了: {:?}", e),
    }
}
```

### 1.2 move 闭包与所有权转移

`thread::spawn` 要求闭包是 `'static` 的（不引用局部变量），因为线程可能比创建它的作用域活得更久。使用 `move` 关键字将环境变量的所有权转移进线程：

```rust
use std::thread;

fn main() {
    let data = vec![1, 2, 3, 4, 5];

    // move闭包：data的所有权转移到子线程
    let handle = thread::spawn(move || {
        let sum: i32 = data.iter().sum();
        println!("子线程计算和: {}", sum);
        // data在这里被drop
    });

    // println!("{:?}", data); // 编译错误：data已被move

    handle.join().unwrap();

    // 多个线程各自拥有独立的数据副本
    let shared_name = String::from("worker");
    let mut handles = vec![];

    for i in 0..3 {
        let name = shared_name.clone(); // 每个线程clone一份
        handles.push(thread::spawn(move || {
            println!("{} {} 启动", name, i);
        }));
    }

    for h in handles {
        h.join().unwrap();
    }
}
```

对照 C++：C++的 `std::thread` 也需要注意对象生命周期，但 C++没有编译期检查。C++中可以意外地将引用传入线程而导致悬空引用，Rust 的 `'static` 约束在编译期阻止了这种错误。

```cpp
// C++中的经典bug：引用悬空
#include <thread>
#include <iostream>

void worker() {
    std::vector<int> data = {1, 2, 3};
    // 错误：data是局部变量，线程可能在data销毁后访问它
    std::thread t([&data]() {
        // data可能已经被销毁！未定义行为
        std::cout << data.size() << std::endl;
    });
    t.detach(); // 分离线程，data在worker返回时销毁
}
```

### 1.3 线程命名与栈大小

```rust
use std::thread;

fn main() {
    // Builder模式配置线程
    let handle = thread::Builder::new()
        .name("worker-thread".to_string()) // 线程名，出现在panic信息和调试器中
        .stack_size(8 * 1024 * 1024) // 8MB栈大小（默认通常是2MB或8MB，取决于平台）
        .spawn(|| {
            // thread::current()获取当前线程句柄
            let current = thread::current();
            println!("线程名: {:?}", current.name());
            println!("线程ID: {:?}", current.id());
        })
        .expect("线程创建失败");

    handle.join().unwrap();

    // 获取当前线程信息
    println!("主线程ID: {:?}", thread::current().id());
    println!("可用并行度: {}", thread::available_parallelism().unwrap());
}
```

## 2. thread::scope 作用域线程

### 2.1 为什么需要 scope

`thread::spawn` 要求 `'static`，意味着不能借用局部变量。但有时需要多个线程共享局部数据，且保证所有线程在局部变量销毁前结束。`thread::scope` 提供了这种能力。

```rust
use std::thread;

fn main() {
    let numbers = vec![1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

    // scope创建一个线程作用域
    // 所有在scope内spawn的线程，在scope结束前自动join
    let sum = thread::scope(|s| {
        let mid = numbers.len() / 2;
        let left = &numbers[..mid];
        let right = &numbers[mid..];

        // 在scope中spawn线程，可以借用外部变量
        let handle1 = s.spawn(move || {
            left.iter().sum::<i32>()
        });

        let handle2 = s.spawn(move || {
            right.iter().sum::<i32>()
        });

        // scope结束时自动join所有线程，然后返回结果
        handle1.join().unwrap() + handle2.join().unwrap()
    });

    println!("总和: {}", sum); // 55
    // numbers仍然可用，因为scope保证了线程在numbers销毁前结束
    println!("{:?}", numbers);
}
```

### 2.2 scope API 与借用

`thread::scope` 的核心保证：**scope 块结束时，所有 spawn 的线程都已 join**。这意味着借用的局部变量一定在线程结束后才销毁。

```rust
use std::thread;

fn parallel_map<T, F, R>(data: &[T], f: F) -> Vec<R>
where
    T: Sync,
    F: Fn(&T) -> R + Sync,
    R: Send,
{
    let mut results: Vec<Option<R>> = (0..data.len()).map(|_| None).collect();

    thread::scope(|s| {
        // 用 split_at_mut 切分可变切片，避免对整个 Vec 的重复可变借用
        let mut rest = &mut results[..];
        for item in data.iter() {
            let (head, tail) = rest.split_at_mut(1);
            rest = tail;
            s.spawn(move || {
                head[0] = Some(f(item));
            });
        }
    }); // scope结束，所有线程join完成

    results.into_iter().map(|r| r.unwrap()).collect()
}

fn main() {
    let data = vec![1, 2, 3, 4, 5];
    let squared = parallel_map(&data, |x| x * x);
    println!("{:?}", squared); // [1, 4, 9, 16, 25]
}
```

交叉引用：C++中没有 scope 线程的直接对应，需要手动管理 join 或使用 `std::jthread`（C++20）。详细的 C++线程模型见《../../01-C++技术体系/04-并发编程/01-线程基础与生命周期.md》。

## 3. Send 与 Sync：编译期数据竞争防护

Send 和 Sync 是 Rust 并发安全的基石。它们是**标记 trait**（marker trait），没有方法，但编译器会自动推导并在编译期检查。

### 3.1 Send：可跨线程转移所有权

`Send` 标记表示：**这个类型的所有权可以安全地从一个线程转移到另一个线程**。

```rust
use std::thread;
use std::rc::Rc;

fn main() {
    // i32是Send的，可以安全转移到另一个线程
    let x = 42;
    thread::spawn(move || {
        println!("{}", x); // OK
    }).join().unwrap();

    // Rc<T>不是Send的，不能跨线程转移
    let rc = Rc::new(42);
    // thread::spawn(move || {
    //     println!("{}", rc); // 编译错误：Rc<i32>不能安全地跨线程转移
    // }).join().unwrap();

    // Arc<T>是Send的（当T: Send + Sync时）
    use std::sync::Arc;
    let arc = Arc::new(42);
    let arc2 = arc.clone();
    thread::spawn(move || {
        println!("{}", arc2); // OK：Arc是Send的
    }).join().unwrap();
}
```

`Rc<T>` 不是 Send 的原因：它的引用计数是普通整数（非原子），如果两个线程同时 clone/drop，会导致数据竞争和引用计数错误。

### 3.2 Sync：可跨线程共享引用

`Sync` 标记表示：**这个类型的不可变引用（&T）可以安全地在多个线程间共享**。

```rust
use std::thread;
use std::sync::{Arc, Mutex, RwLock};
use std::cell::RefCell;

fn main() {
    // i32是Sync的，多个线程可以共享&i32
    let x = 42;
    let ref1 = &x;
    let ref2 = &x;
    thread::scope(|s| {
        s.spawn(|| println!("{}", ref1));
        s.spawn(|| println!("{}", ref2));
    });

    // RefCell<T>不是Sync的，不能跨线程共享&RefCell<T>
    let cell = RefCell::new(42);
    // thread::scope(|s| {
    //     s.spawn(|| *cell.borrow_mut() += 1); // 编译错误：RefCell不是Sync
    // });

    // Mutex<T>是Sync的（当T: Send时），可以跨线程共享&Mutex<T>
    let mutex = Mutex::new(0);
    thread::scope(|s| {
        for _ in 0..10 {
            s.spawn(|| {
                let mut guard = mutex.lock().unwrap();
                *guard += 1;
            });
        }
    });
    println!("{}", mutex.lock().unwrap()); // 10
}
```

`RefCell<T>` 不是 Sync 的原因：它的借用计数是普通整数，且 `borrow_mut` 可以通过 `&RefCell` 修改内部值。如果多个线程同时共享 `&RefCell` 并调用 `borrow_mut`，会导致数据竞争。

Send 与 Sync 的关系：

| 类型 | Send | Sync | 说明 |
|------|------|------|------|
| `i32`, `String`, `Vec<T>` | 是 | 是 | 普通拥有所有权的类型 |
| `&T` (当 T: Sync) | 是 | 是 | 不可变引用可跨线程共享和转移 |
| `&mut T` (当 T: Send) | 是 | 否 | 可变引用可转移但不能共享（排他性） |
| `Rc<T>` | 否 | 否 | 非原子引用计数 |
| `Arc<T>` (当 T: Send+Sync) | 是 | 是 | 原子引用计数 |
| `Cell<T>` (当 T: Send) | 是 | 否 | 内部可变性，非线程安全 |
| `RefCell<T>` (当 T: Send) | 是 | 否 | 运行时借用检查，非线程安全 |
| `Mutex<T>` (当 T: Send) | 是 | 是 | 锁保护内部可变性 |
| `RwLock<T>` (当 T: Send+Sync) | 是 | 是 | 读写锁 |
| `AtomicI32` 等 | 是 | 是 | 原子类型 |
| 裸指针 `*const T`/`*mut T` | 否 | 否 | 需要 unsafe 手动实现 |

### 3.3 Send/Sync 的自动推导

编译器自动为类型推导 Send 和 Sync：
- 如果一个类型的所有字段都是 Send，那么这个类型是 Send
- 如果一个类型的所有字段都是 Sync，那么这个类型是 Sync

```rust
// 自动推导：MyStruct的字段都是Send+Sync，所以MyStruct也是Send+Sync
struct MyStruct {
    id: u64,
    name: String,
    data: Vec<u8>,
}

// 包含裸指针的类型，自动推导为!Send + !Sync
struct UnsafeWrapper {
    ptr: *mut i32,
}
// UnsafeWrapper不是Send也不是Sync，需要手动实现
```

### 3.4 手动实现 Send/Sync 的规则

当类型包含裸指针或其他 `!Send`/`!Sync` 的字段，但实际上是线程安全的时，需要手动实现：

```rust
use std::sync::atomic::{AtomicBool, Ordering};

// 自定义原子指针包装器
struct AtomicOption<T> {
    ptr: *mut T,
    occupied: AtomicBool,
}

// 手动实现Send：当T是Send时，AtomicOption<T>是Send
unsafe impl<T: Send> Send for AtomicOption<T> {}

// 手动实现Sync：当T是Send + Sync时，AtomicOption<T>是Sync
unsafe impl<T: Send + Sync> Sync for AtomicOption<T> {}

impl<T> AtomicOption<T> {
    fn new(value: T) -> Self {
        let ptr = Box::into_raw(Box::new(value));
        AtomicOption {
            ptr,
            occupied: AtomicBool::new(true),
        }
    }

    fn take(&self) -> Option<T> {
        if self.occupied.swap(false, Ordering::Acquire) {
            unsafe {
                let value = Box::from_raw(self.ptr);
                Some(*value)
            }
        } else {
            None
        }
    }
}

impl<T> Drop for AtomicOption<T> {
    fn drop(&mut self) {
        if self.occupied.load(Ordering::Relaxed) {
            unsafe {
                let _ = Box::from_raw(self.ptr);
            }
        }
    }
}
```

手动实现 Send/Sync 的安全要求：
- **实现 Send**：必须保证类型的值在跨线程转移后，不会出现数据竞争。通常需要内部使用原子操作或锁保护。
- **实现 Sync**：必须保证多个线程同时持有 `&T` 时，不会出现数据竞争。这比 Send 更严格，因为 `&T` 是共享的。
- 使用 `unsafe impl` 声明，因为编译器无法验证安全性，需要程序员承诺。

对照 C++：C++没有 Send/Sync 概念，线程安全完全是文档约定。一个 C++类是否线程安全，需要看文档或源码，编译器不做任何检查。Rust 把"线程安全"变成了类型系统的一部分，在编译期强制保证。

## 4. 线程局部存储

### 4.1 thread_local!宏

线程局部存储（TLS）为每个线程提供独立的变量副本，不需要同步。

```rust
use std::cell::RefCell;

// 声明线程局部变量
thread_local! {
    static THREAD_COUNTER: RefCell<u64> = RefCell::new(0);
    static THREAD_NAME: String = String::from("unnamed");
}

fn main() {
    use std::thread;

    // 主线程设置
    THREAD_COUNTER.with(|c| *c.borrow_mut() = 100);
    THREAD_NAME.with(|n| *n = String::from("main"));

    let handle = thread::spawn(|| {
        // 子线程有独立的副本，初始值是声明时的默认值
        THREAD_COUNTER.with(|c| {
            println!("子线程初始计数: {}", *c.borrow()); // 0
            *c.borrow_mut() = 200;
        });

        THREAD_NAME.with(|n| {
            *n = String::from("worker");
            println!("子线程名: {}", n);
        });
    });

    handle.join().unwrap();

    // 主线程的值不受子线程影响
    THREAD_COUNTER.with(|c| println!("主线程计数: {}", *c.borrow())); // 100
    THREAD_NAME.with(|n| println!("主线程名: {}", n)); // main
}
```

`thread_local!` 的特点：
- 每个线程有独立的副本
- 首次访问时初始化（惰性初始化）
- 线程结束时自动 drop
- 使用 `with` 方法访问，因为 TLS 变量的地址可能不稳定

更复杂的例子：线程局部的连接池

```rust
use std::cell::RefCell;
use std::collections::VecDeque;

struct Connection {
    id: u64,
}

thread_local! {
    static CONNECTION_POOL: RefCell<VecDeque<Connection>> = RefCell::new(VecDeque::new());
}

fn get_connection() -> Connection {
    CONNECTION_POOL.with(|pool| {
        if let Some(conn) = pool.borrow_mut().pop_front() {
            conn
        } else {
            Connection { id: 0 } // 创建新连接
        }
    })
}

fn return_connection(conn: Connection) {
    CONNECTION_POOL.with(|pool| {
        pool.borrow_mut().push_back(conn);
    });
}
```

### 4.2 对比 C++thread_local

| 特性 | Rust `thread_local!` | C++ `thread_local` |
|------|----------------------|---------------------|
| 初始化 | 惰性（首次访问时） | 静态初始化期或首次使用 |
| 析构 | 线程结束时自动 drop | 线程结束时自动析构 |
| 访问方式 | `.with()` 闭包 | 直接访问变量名 |
| 可变状态 | 需要 `Cell`/`RefCell` | 直接可变 |
| 初始化顺序 | 每个变量独立 | 可能有初始化顺序问题 |
| 跨平台 | 稳定 | 平台相关（某些平台有限制） |

C++的 `thread_local` 可以直接修改变量，Rust 需要 `Cell`/`RefCell` 是因为 Rust 的 `static` 变量默认是不可变的，需要内部可变性容器。

## 5. 快速参考卡片

| 查询点 | 速答 |
| --- | --- |
| 创建线程 | `thread::spawn(move \|\| { ... })` 返回 `JoinHandle<T>`；`.join()` 阻塞并拿到 `Result<T, Box<dyn Any>>` |
| 为什么要 move | 新线程生命周期不确定，借用栈上数据编译不过；`move` 把所有权搬进去 |
| 作用域线程 | `thread::scope(\|s\| { s.spawn(\|\| use(&local)); })`：可借用局部变量，作用域结束自动 join |
| Send | 所有权可跨线程转移：`i32` ✓、`String` ✓、`Rc` ✗、`*mut T` ✗ |
| Sync | `&T` 可跨线程共享：`Mutex<T>` ✓、`RefCell<T>` ✗、`Cell<T>` ✗ |
| 自动推导 | 按字段递归推导；`Rc` 非 Send/Sync、`Arc<Mutex<T>>` 全满足、`Rc<RefCell<T>>` 全不满足 |
| 手动 impl | 只能 `unsafe impl Send/Sync`，需自行论证不变量；写错即 UB |
| 线程局部 | `thread_local! { static C: RefCell<u32> = RefCell::new(0); }`，每线程独立实例 |
| Builder 配置 | `thread::Builder::new().name("w1").stack_size(4 * 1024 * 1024).spawn(f)` |
| 选型 | CPU 密集线程数≈核数；IO 密集改用异步 |

交叉引用：C++ 线程基础见《../../01-C++技术体系/04-并发编程/01-线程基础与生命周期.md》。

---

## 6. 常见陷阱

### 陷阱 1：忘记 join 导致主线程提前退出

```rust
use std::thread;

fn main() {
    thread::spawn(|| {
        // 耗时操作
        thread::sleep(std::time::Duration::from_secs(1));
        println!("子线程完成");
    });
    // 没有join！main返回时进程退出，子线程被强制终止
    // 输出可能没有"子线程完成"
}
```

### 陷阱 2：Rc 跨线程

```rust
use std::rc::Rc;
use std::thread;

fn main() {
    let rc = Rc::new(42);
    // thread::spawn(move || {
    //     println!("{}", rc); // 编译错误：Rc不是Send
    // });
    // 正确：使用Arc
    use std::sync::Arc;
    let arc = Arc::new(42);
    thread::spawn(move || println!("{}", arc)).join().unwrap();
}
```

### 陷阱 3：&mut 跨线程共享

```rust
use std::thread;

fn main() {
    let mut data = vec![1, 2, 3];
    let ref_mut = &mut data;

    // 不能在多个线程间共享&mut（排他性）
    // thread::scope(|s| {
    //     s.spawn(|| ref_mut.push(4));
    //     s.spawn(|| ref_mut.push(5)); // 编译错误：不能同时有两个&mut
    // });

    // 正确：用Mutex或拆分可变借用
    use std::sync::Mutex;
    let data = Mutex::new(vec![1, 2, 3]);
    thread::scope(|s| {
        s.spawn(|| data.lock().unwrap().push(4));
        s.spawn(|| data.lock().unwrap().push(5));
    });
    println!("{:?}", data.lock().unwrap());
}
```

### 陷阱 4：手动实现 Send/Sync 但实际不安全

```rust
// 危险：手动实现Sync但内部有数据竞争
struct UnsafeCounter {
    count: std::cell::Cell<u64>,
}

// unsafe impl Sync for UnsafeCounter {} // 错误！Cell不是Sync的，这样会导致数据竞争

// 正确：使用AtomicU64
struct SafeCounter {
    count: std::sync::atomic::AtomicU64,
}
// SafeCounter自动是Send + Sync，不需要手动实现
```

## 7. 本节小结

- **std::thread**：`spawn` 创建线程返回 `JoinHandle<T>`，`join` 等待结束并获取返回值或 panic 信息。`Builder` 支持线程命名和栈大小配置。
- **move 闭包**：`thread::spawn` 要求 `'static`，用 `move` 转移所有权。C++中可以意外传入悬空引用，Rust 的 `'static` 约束在编译期阻止。
- **thread::scope**：作用域线程允许借用局部变量，scope 结束时自动 join 所有线程。适合并行计算等短期线程场景，避免了 `Arc` 的开销。
- **Send**：标记类型可安全跨线程转移所有权。`Rc<T>` 不是 Send（非原子引用计数），`Arc<T>` 是 Send。
- **Sync**：标记类型的 `&T` 可安全跨线程共享。`RefCell<T>` 不是 Sync（运行时借用检查非线程安全），`Mutex<T>` 是 Sync。
- **自动推导**：所有字段 Send⇒类型 Send，所有字段 Sync⇒类型 Sync。裸指针自动为 `!Send + !Sync`。
- **手动实现**：`unsafe impl Send/Sync` 需要程序员承诺线程安全性。实现 Sync 比 Send 更严格。
- **线程局部存储**：`thread_local!` 宏为每个线程提供独立副本，惰性初始化，线程结束自动 drop。需要 `Cell`/`RefCell` 提供内部可变性。
- 常见陷阱：忘记 join、Rc 跨线程、&mut 共享、不安全的手动 Send/Sync 实现。

交叉引用：C++线程基础与生命周期详见《../../01-C++技术体系/04-并发编程/01-线程基础与生命周期.md》；锁与死锁的 Rust 解决方案见下一篇《02-锁原子与无锁结构.md》。

---

下一篇：《02-锁原子与无锁结构.md》　｜　模块索引：《../README.md》
