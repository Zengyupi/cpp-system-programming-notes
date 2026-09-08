# 嵌入式no_std与裸机

> 本节目标：掌握 Rust 嵌入式开发的核心技术栈——从 std/alloc/core/no_std 分层到 cortex-m 启动，从 embedded-hal 抽象到 PAC/HAL 关系，从 defmt 日志到中断与临界区，建立可与 C 嵌入式开发对标的裸机编程能力。

## 本章速览

- [1. std/alloc/core/no_std 分层模型](#1-stdalloccoreno_std-分层模型)
  - [1.1 标准库分层与 no_std 含义](#11-标准库分层与-no_std-含义)
  - [1.2 alloc 与全局分配器](#12-alloc-与全局分配器)
- [2. cortex-m 启动与裸机最小程序](#2-cortex-m-启动与裸机最小程序)
  - [2.1 启动流程与内存布局](#21-启动流程与内存布局)
  - [2.2 最小裸机程序](#22-最小裸机程序)
- [3. PAC/HAL 关系与 embedded-hal](#3-pachal-关系与-embedded-hal)
  - [3.1 PAC 寄存器级抽象](#31-pac-寄存器级抽象)
  - [3.2 HAL 高层抽象与 embedded-hal trait](#32-hal-高层抽象与-embedded-hal-trait)
- [4. defmt 高效日志](#4-defmt-高效日志)
  - [4.1 defmt 架构与延迟格式化](#41-defmt-架构与延迟格式化)
  - [4.2 defmt 输出与探针集成](#42-defmt-输出与探针集成)
- [5. 中断与临界区](#5-中断与临界区)
  - [5.1 中断处理函数注册](#51-中断处理函数注册)
  - [5.2 Critical Section 与共享状态](#52-critical-section-与共享状态)
- [6. 与 C 嵌入式开发对照](#6-与-c-嵌入式开发对照)
- [7. 常见坑与本节小结](#7-常见坑与本节小结)
  - [常见坑](#常见坑)
  - [本节小结](#本节小结)

---

## 1. std/alloc/core/no_std 分层模型

### 1.1 标准库分层与 no_std 含义

Rust 标准库在设计上分为三层，从底层到高层依次为：

| 层级 | crate | 内容 | 依赖 |
|------|-------|------|------|
| 核心层 | `core` | 基础类型、trait、迭代器、运算符、原子操作 | 无（纯语言） |
| 分配层 | `alloc` | `Box`、`Vec`、`String`、`BTreeMap` 等需要堆分配的类型 | `core` + 全局分配器 |
| 标准层 | `std` | 文件系统、网络、线程、时间、进程、环境变量 | `alloc` + 操作系统 |

`no_std` 是通过 `#![no_std]` crate 属性声明的，它移除了对 `std` 的依赖，只使用 `core`（和可选的 `alloc`）。这意味着：

- 没有 `std::fs`、`std::net`、`std::thread`、`std::time`（操作系统相关 API 不可用）
- 没有 `std::string::String`、`std::vec::Vec`（除非启用 `alloc`）
- 没有 `std::println!`（需要自己实现输出）
- `main` 函数不再是默认入口（需要自定义入口或使用运行时提供的入口）
- `panic` 行为需要自定义（`#[panic_handler]`）

```rust
// 最小 no_std crate
#![no_std]

// 必须提供 panic handler
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {} // 裸机上通常是死循环或复位
}
```

C 对照：C 语言没有标准库分层的概念——`libc` 是一个整体，嵌入式开发中通常使用 `newlib-nano` 或自研的精简 libc。Rust 的 `core`/`alloc`/`std` 分层使得嵌入式开发者可以精确控制依赖范围，`core` 中的所有内容（迭代器、trait、模式匹配）在裸机上都可用，这是 C 语言的 `<stdint.h>`/`<stdbool.h>` 无法比拟的。

### 1.2 alloc 与全局分配器

在 `no_std` 环境中使用 `Vec`、`String`、`Box` 等堆分配类型，需要：

1. 启用 `extern crate alloc;`
2. 提供全局分配器（实现 `GlobalAlloc` trait）

```rust
#![no_std]

extern crate alloc;

use alloc::vec::Vec;
use alloc::string::String;
use core::alloc::{GlobalAlloc, Layout};

// 简单的 bump allocator（仅示例，生产环境用 linked-list-allocator 等）
struct BumpAllocator {
    start: usize,
    end: usize,
    pos: core::cell::Cell<usize>,
}

unsafe impl GlobalAlloc for BumpAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let align = layout.align();
        let size = layout.size();
        let start = (self.pos.get() + align - 1) & !(align - 1);
        if start + size > self.end {
            return core::ptr::null_mut();
        }
        self.pos.set(start + size);
        start as *mut u8
    }

    unsafe fn dealloc(&self, _ptr: *mut u8, _layout: Layout) {
        // bump allocator 不支持释放
    }
}

#[global_allocator]
static ALLOCATOR: BumpAllocator = BumpAllocator {
    start: 0x2000_0000,
    end: 0x2000_8000,
    pos: core::cell::Cell::new(0x2000_0000),
};

fn demo_alloc() {
    let mut v: Vec<u32> = Vec::new();
    v.push(1);
    v.push(2);

    let s: String = String::from("hello");
}
```

嵌入式中常用的分配器 crate：`linked-list-allocator`（链表分配器，支持释放）、`buddy_system_allocator`（伙伴系统）、`talc`（高性能分配器）。选择分配器时需要考虑：碎片化、分配/释放速度、线程安全（中断安全）、代码体积。

C 对照：C 嵌入式中通常使用 `malloc`/`free`（由 libc 提供，如 newlib 的 `_sbrk` 实现）或自研的内存池。Rust 的 `GlobalAlloc` trait 将分配器抽象标准化，可以在不同分配器间切换而不修改业务代码。且 Rust 的所有权系统在编译期保证了内存安全，消除了 C 中常见的 use-after-free 和 double-free。

## 2. cortex-m 启动与裸机最小程序

### 2.1 启动流程与内存布局

ARM Cortex-M 系列是 Rust 嵌入式最成熟的目标平台。启动流程（可交叉参考《../../01-C++技术体系/09-嵌入式开发/04-中断系统与RTOS原理.md》中 Cortex-M 中断的详细讨论）：

1. **复位向量**：CPU 从地址 `0x0000_0000` 读取初始栈指针（MSP），从 `0x0000_0004` 读取复位向量（Reset handler 地址）
2. **Reset handler**：初始化 `.data` 段（从 Flash 拷贝到 RAM）、清零 `.bss` 段、调用 `main`
3. **主程序**：运行用户代码

`cortex-m-rt` crate 提供了启动运行时，自动处理向量表、`.data`/`.bss` 初始化、运行时入口。内存布局通过 `memory.x` 文件定义：

```text
/* memory.x - 链接脚本，定义 Flash 和 RAM 地址 */
MEMORY
{
  FLASH : ORIGIN = 0x08000000, LENGTH = 256K
  RAM   : ORIGIN = 0x20000000, LENGTH = 64K
}

/* 栈大小 */
_stack_start = ORIGIN(RAM) + LENGTH(RAM);
```

### 2.2 最小裸机程序

```toml
# Cargo.toml
[package]
name = "embedded-hello"
version = "0.1.0"
edition = "2021"

[dependencies]
cortex-m = "0.7"
cortex-m-rt = "0.7"
panic-halt = "1"  # panic 时 halt（死循环）

[profile.release]
codegen-units = 1
debug = true
lto = true
```

```rust
// src/main.rs
#![no_std]
#![no_main]

use cortex_m_rt::entry;
use panic_halt as _;

#[entry]
fn main() -> ! {
    // 裸机程序入口，返回 !（永不返回）

    // 简单的忙等待延时
    let mut count = 0;
    loop {
        count += 1;
        // 这里可以操作 GPIO、UART 等外设
    }
}
```

`.cargo/config.toml` 配置目标和链接器：

```toml
[build]
target = "thumbv7em-none-eabihf"  # Cortex-M4F 目标

[target.thumbv7em-none-eabihf]
runner = "probe-run --chip STM32F411CEUx"  # 烧录和运行工具
rustflags = [
  "-C", "link-arg=-Tlink.x",  # 使用 cortex-m-rt 提供的链接脚本
]
```

安装目标和工具：

```bash
# 安装 Cortex-M4F 目标标准库
rustup target add thumbv7em-none-eabihf

# 安装烧录工具
cargo install probe-run
cargo install flip-link  # 栈溢出检测（可选）

# 编译并烧录
cargo run --release
```

`probe-run` 是 Rust 嵌入式的标准烧录工具，它通过 SWD/JTAG 探针（如 ST-Link、J-Link）将程序烧录到 MCU 并运行，同时通过 RTT（Real-Time Transfer）捕获 `defmt` 日志输出到终端。这与 C 嵌入式中使用 OpenOCD + GDB 的流程类似，但 `cargo run` 一键完成编译、烧录、运行、日志输出，体验更流畅。

## 3. PAC/HAL 关系与 embedded-hal

### 3.1 PAC 寄存器级抽象

PAC（Peripheral Access Crate）是对 MCU 寄存器的低级抽象，由 `svd2rust` 工具从芯片厂商提供的 SVD（System View Description）文件自动生成。PAC 提供了类型安全的寄存器访问，避免了 C 中直接操作裸地址的错误。

```rust
// 使用 stm32f4 PAC 操作 GPIO（示例）
use stm32f4::stm32f411::Peripherals;

fn setup_gpio() {
    let dp = Peripherals::take().unwrap();

    // 使能 GPIOA 时钟
    dp.RCC.ahb1enr.modify(|_, w| w.gpioaen().set_bit());

    // 配置 PA5 为推挽输出（STM32 板载 LED）
    dp.GPIOA.moder.modify(|_, w| w.moder5().output());
    dp.GPIOA.otyper.modify(|_, w| w.ot5().push_pull());
    dp.GPIOA.ospeedr.modify(|_, w| w.ospeedr5().low_speed());
}

fn toggle_led() {
    let dp = unsafe { Peripherals::steal() };
    // 读改写输出数据寄存器
    dp.GPIOA.odr.modify(|r, w| w.odr5().bit(!r.odr5().bit()));
}
```

PAC 的寄存器访问通过 `read()`/`modify()`/`write()` 方法，使用 builder 模式构造寄存器值。`modify(|r, w| ...)` 提供了读-改-写的原子操作，`r` 是当前寄存器值，`w` 是要写入的值。这比 C 中 `GPIOA->ODR |= (1 << 5)` 的位操作更安全——编译器会检查字段名和值的合法性，拼写错误在编译期暴露。

### 3.2 HAL 高层抽象与 embedded-hal trait

HAL（Hardware Abstraction Layer）构建在 PAC 之上，提供更高层的外设抽象（如 `OutputPin`、`Uart`、`I2c`、`Spi`），隐藏寄存器细节。HAL 的实现遵循 `embedded-hal` crate 定义的 trait，使得驱动代码可以跨 MCU 平台复用。

```toml
# Cargo.toml
[dependencies]
embedded-hal = "1"
stm32f4xx-hal = "0.22"  # STM32F4 系列 HAL
```

```rust
use stm32f4xx_hal::{
    pac,
    prelude::*,
    gpio::{Output, PushPull, Pin},
    serial::{Config, Serial},
};
use embedded_hal::digital::OutputPin;

fn main() -> ! {
    let dp = pac::Peripherals::take().unwrap();
    let cp = cortex_m::Peripherals::take().unwrap();

    // 配置时钟
    let rcc = dp.RCC.constrain();
    let clocks = rcc.cfgr.sysclk(84.MHz()).freeze();

    // 获取 GPIOA
    let gpioa = dp.GPIOA.split();

    // PA5 配置为推挽输出（LED）
    let mut led: Pin<'A', 5, Output<PushPull>> = gpioa.pa5.into_push_pull_output();

    // 配置 UART2（PA2 TX, PA3 RX）
    let tx = gpioa.pa2.into_alternate();
    let rx = gpioa.pa3.into_alternate();
    let serial = Serial::new(
        dp.USART2,
        (tx, rx),
        Config::default().baudrate(115200.bps()),
        &clocks,
    ).unwrap();

    // 延时
    let mut delay = cp.SYST.delay(&clocks);

    loop {
        // embedded-hal 的 OutputPin trait 方法
        led.set_high().unwrap();
        delay.delay_ms(500u32);
        led.set_low().unwrap();
        delay.delay_ms(500u32);
    }
}
```

`embedded-hal` trait 的核心价值是**平台无关的驱动**。一个传感器驱动库（如 `ssd1306` OLED 显示屏驱动）只依赖 `embedded-hal` 的 `I2c` trait，可以在 STM32、nRF52、RP2040、ESP32 等任何实现了该 trait 的平台上运行。这与 C 嵌入式中每个 MCU 都要重写驱动的模式形成鲜明对比。

C 对照：C 嵌入式中通常使用芯片厂商提供的 HAL 库（如 STM32 HAL、NXP MCUXpresso），但这些库互不兼容，驱动代码无法跨平台复用。CMSIS-Driver 试图标准化但采用率有限。Rust 的 `embedded-hal` trait 是社区驱动的统一标准，已有数百个平台无关的驱动 crate（可在 `crates.io` 搜索 `no-std` + 传感器型号），生态成熟度远超 C。

## 4. defmt 高效日志

### 4.1 defmt 架构与延迟格式化

`defmt` 是 Rust 嵌入式的高效日志框架，核心设计是**延迟格式化（deferred formatting）**：日志消息的格式化不在 MCU 上完成，而是在主机端完成。MCU 只发送格式化字符串的索引和原始二进制数据，主机端的 `defmt-print` 工具根据索引查找格式字符串并格式化输出。

这种设计的优势：

- **MCU 端开销极小**：不需要 `sprintf`，不需要字符串拷贝，只发送几个字节的二进制数据
- **日志体积小**：格式化字符串存储在主机的 ELF 文件中，不占用 Flash
- **传输快**：通过 RTT 或 UART 发送少量字节，不阻塞 MCU

```toml
# Cargo.toml
[dependencies]
defmt = "0.3"
defmt-rtt = "0.4"  # RTT 传输后端
panic-probe = "0.3" # panic 时通过 defmt 输出并 halt
```

```rust
use defmt::{info, debug, warn, error};

fn demo_defmt() {
    let sensor_value: u16 = read_sensor();
    let name = "temperature";

    // defmt 宏与 log 类似，但格式化在主机端完成
    info!("传感器读数: {} = {}", name, sensor_value);

    // 支持结构体（需实现 Format trait 或 derive）
    #[derive(defmt::Format)]
    struct Config {
        address: u8,
        enabled: bool,
    }
    let config = Config { address: 0x48, enabled: true };
    debug!("配置: {:?}", config);

    // 不同日志级别
    if sensor_value > 3000 {
        warn!("传感器值过高: {}", sensor_value);
    }
    if sensor_value > 4000 {
        error!("传感器值超出范围!");
    }
}
```

`defmt::Format` trait 是 defmt 版的 `Debug`，可以通过 `#[derive(defmt::Format)]` 自动生成。与 `core::fmt::Debug` 不同，`Format` 的格式化逻辑在主机端执行，MCU 只发送字段的原始字节。

### 4.2 defmt 输出与探针集成

defmt 的输出需要 `probe-run` 或 `defmt-print` 工具配合。`probe-run` 在烧录程序后自动连接 RTT，捕获 defmt 数据并格式化输出：

```bash
# cargo run 自动调用 probe-run，输出 defmt 日志
cargo run --release

# 输出示例：
# (HOST) INFO  flashing program
# (HOST) INFO  success!
# 0.000000 INFO  传感器读数: temperature = 2048
# 0.000500 DEBUG 配置: Config { address: 72, enabled: true }
# 0.001000 WARN  传感器值过高: 3500
```

时间戳 `0.000000` 是 MCU 启动后的相对时间（微秒精度），由 `cortex-m` 的 cycle counter 提供。这使得日志可以精确反映事件发生的时间顺序，对于调试实时系统非常有价值。

C 对照：C 嵌入式中最常用的日志方式是 `printf` 重定向到 UART，但 `printf` 占用大量 Flash（newlib-nano 的 `printf` 约 10-20KB）且执行慢。Segger RTT 是更高效的方案，但需要手动集成且格式化仍在 MCU 端。defmt 的延迟格式化是 Rust 独有的创新——格式化字符串完全不占用 MCU Flash，日志数据传输量最小化，在资源受限的 MCU（如 16KB Flash 的 Cortex-M0）上也能使用丰富的日志。

## 5. 中断与临界区

### 5.1 中断处理函数注册

Cortex-M 的中断处理函数通过 `cortex-m-rt` 的 `#[interrupt]` 属性注册，中断名称由 PAC crate 提供（从 SVD 生成的枚举）：

```rust
use cortex_m_rt::interrupt;
use stm32f4::stm32f411::Interrupt;

// 全局可变状态（中断和主循环共享）
static mut COUNTER: u32 = 0;

#[interrupt]
fn TIM2() {
    // TIM2 中断处理函数
    // 清除中断挂起位
    // SAFETY: 中断上下文中访问外设，需要 unsafe
    let dp = unsafe { stm32f4::stm32f411::Peripherals::steal() };
    dp.TIM2.sr.modify(|_, w| w.uif().clear());

    // 递增计数器
    // SAFETY: 单核心 MCU，中断不会被自身嵌套（同优先级）
    unsafe { COUNTER += 1; }
}

fn main() -> ! {
    let dp = stm32f4::stm32f411::Peripherals::take().unwrap();

    // 配置 TIM2 产生 1ms 中断
    // ... 时钟、预分频、自动重装载值配置 ...

    // 使能 TIM2 中断
    unsafe {
        cortex_m::peripheral::NVIC::unmask(Interrupt::TIM2);
    }

    loop {
        // 主循环中读取计数器
        let count = unsafe { COUNTER };
        if count >= 1000 {
            // 1 秒到了
            unsafe { COUNTER = 0; }
            // 做一些事情
        }
    }
}
```

`#[interrupt]` 宏自动将函数标记为 `extern "C"`（符合 ARM 调用约定），并将其地址填入向量表的对应位置。中断名称必须与 PAC 中的 `Interrupt` 枚举变体一致，拼写错误会编译失败。

### 5.2 Critical Section 与共享状态

在裸机环境中，主循环和中断之间共享状态需要**临界区（Critical Section）**保护。`cortex-m` 的 `interrupt::free` 函数提供了临界区——在闭包执行期间暂时禁用全局中断，确保原子性：

```rust
use core::cell::RefCell;
use cortex_m::interrupt::{self, Mutex};
use stm32f4::stm32f411::Interrupt;

// 用 Mutex<RefCell<T>> 包装共享状态
// Mutex 是 cortex-m 的"中断安全互斥锁"，在临界区内可访问
static SHARED: Mutex<RefCell<Option<u32>>> = Mutex::new(RefCell::new(None));

#[interrupt]
fn EXTI0() {
    // 中断中访问共享状态
    interrupt::free(|cs| {
        *SHARED.borrow(cs).borrow_mut() = Some(42);
    });
}

fn main() -> ! {
    loop {
        // 主循环中访问共享状态
        let value = interrupt::free(|cs| {
            SHARED.borrow(cs).borrow().clone()
        });

        if let Some(v) = value {
            // 处理中断传来的数据
            interrupt::free(|cs| {
                *SHARED.borrow(cs).borrow_mut() = None;
            });
        }
    }
}
```

`Mutex<RefCell<T>>` 是裸机共享状态的标准模式：
- `Mutex`（来自 `cortex-m::interrupt`）确保只有在临界区内才能访问内部数据
- `RefCell` 提供内部可变性（因为 `static` 变量默认不可变）
- `interrupt::free(|cs| ...)` 提供临界区令牌 `cs`，`Mutex::borrow(cs)` 需要该令牌

这种模式在编译期保证了：不在临界区内就无法访问共享状态，消除了 C 中"忘记关中断"导致的数据竞争。且 `interrupt::free` 是零成本抽象——它只是设置 `PRIMASK` 寄存器禁用中断，闭包执行完后恢复，没有运行时开销。

对于更复杂的共享状态（如环形缓冲区），可以使用 `heapless::spsc::Queue`（单生产者单消费者无锁队列），它在中断和主循环之间安全传递数据，不需要临界区：

```rust
use heapless::spsc::Queue;
use heapless::spsc::Producer;
use heapless::spsc::Consumer;

static mut QUEUE: Queue<u8, 64> = Queue::new();

#[interrupt]
fn USART2() {
    // 中断中作为生产者
    let (prod, _) = unsafe { QUEUE.split() };
    // ... 从 UART 读取数据并 enqueue ...
}
```

C 对照：C 嵌入式中共享状态的保护通常是手动 `__disable_irq()` / `__enable_irq()`，容易忘记恢复或在复杂控制流中出错。Rust 的 `interrupt::free` + `Mutex<RefCell<T>>` 模式在编译期强制临界区，且 RAII 确保中断自动恢复。`heapless` crate 提供的无锁数据结构进一步减少了临界区需求。这与《../../01-C++技术体系/09-嵌入式开发/04-中断系统与RTOS原理.md》中讨论的 C 中断编程模式形成鲜明对比——Rust 在语言层面消除了一类常见的嵌入式 bug。

## 6. 与 C 嵌入式开发对照

Rust 嵌入式与 C 嵌入式的核心差异对照（可交叉参考《../../01-C++技术体系/09-嵌入式开发/05-嵌入式Linux系统与驱动开发.md》中 Linux 驱动开发的讨论）：

| 维度 | C 嵌入式 | Rust 嵌入式 |
|------|----------|-------------|
| 标准库 | newlib-nano / 自研 libc | `core` + 可选 `alloc` |
| 寄存器访问 | 裸指针 `*(volatile uint32_t*)0x40020000 \|= ...` | PAC `modify(\|r, w\| ...)` 类型安全 |
| 外设抽象 | 厂商 HAL（STM32 HAL 等），互不兼容 | `embedded-hal` trait，跨平台驱动复用 |
| 中断处理 | 手动填写向量表、`IRQHandler` 函数 | `#[interrupt]` 宏自动注册 |
| 共享状态 | 手动 `__disable_irq()`，易遗漏 | `interrupt::free` + `Mutex` 编译期保证 |
| 日志 | `printf` 重定向 UART（占 Flash、慢） | `defmt` 延迟格式化（极小开销） |
| 内存安全 | 手动管理，use-after-free 常见 | 所有权系统编译期保证 |
| 构建系统 | Makefile / CMake + 工具链配置 | `cargo build` + `.cargo/config.toml` |
| 烧录调试 | OpenOCD + GDB 手动流程 | `cargo run`（probe-run）一键完成 |
| 驱动生态 | 每个 MCU 重写，代码重复 | 平台无关驱动 crate，一次编写到处运行 |
| 静态分析 | 需额外工具（CppCheck、PC-lint） | 编译器 + clippy 内置 |

核心优势总结：Rust 嵌入式在保留 C 的性能和底层控制能力的同时，通过类型系统、所有权、trait 抽象消除了 C 嵌入式中最常见的 bug 类别（内存错误、数据竞争、寄存器拼写错误）。`embedded-hal` 的平台无关驱动生态和 `defmt` 的高效日志是 C 生态缺乏的创新。目前 Rust 嵌入式的主要局限是：部分高端 MCU（如某些 DSP、RISC-V 变体）的 PAC/HAL 支持不如 C 成熟，以及调试工具链（如 ITM 追踪）的覆盖度。但对于主流的 Cortex-M 系列，Rust 已经具备生产级能力。

## 7. 常见坑与本节小结

### 常见坑

1. **忘记 `#![no_main]`**：`no_std` 程序必须同时声明 `#![no_std]` 和 `#![no_main]`，否则编译器会尝试链接 `main` 函数和 `std` 入口，导致链接错误。
2. **`panic_handler` 缺失或重复**：每个 `no_std` binary crate 必须有且仅有一个 `#[panic_handler]`。使用 `panic-halt` 或 `panic-probe` crate 时通过 `use panic_halt as _;` 引入，不要自己再定义。
3. **`memory.x` 地址错误**：Flash 和 RAM 的起始地址和大小必须与具体 MCU 型号一致。地址错误会导致程序烧录后不运行或 HardFault。使用 `cortex-m-rt` 时通过 `flip-link` 可以检测栈溢出。
4. **中断中使用 `alloc`**：中断处理函数中不应进行堆分配（`Vec::push`、`String` 等），因为分配器可能不是中断安全的，且分配可能耗时较长影响实时性。中断中应使用固定大小的缓冲区（`heapless::Vec`）或无锁队列。
5. **`interrupt::free` 嵌套**：`interrupt::free` 可以安全嵌套（内部计数），但临界区过长会增加中断延迟。应尽量缩短临界区，只保护必要的共享状态访问。
6. **PAC `Peripherals::take()` 只能调用一次**：`take()` 返回 `Option<Peripherals>`，第二次调用返回 `None`。在中断中需要访问外设时使用 `unsafe { Peripherals::steal() }`，但要确保不会与主循环的访问冲突。
7. **`defmt` 与 `probe-run` 版本不匹配**：`defmt` 的 wire format 版本必须与 `probe-run` 支持的版本一致，否则日志输出乱码。更新依赖时注意 `defmt` 和 `probe-run` 的兼容性矩阵。
8. **`embedded-hal` 0.2 与 1.0 不兼容**：`embedded-hal` 1.0 于 2023 年底发布，trait 设计有较大变化（错误类型关联、`ErrorType` trait）。旧驱动 crate 可能仍依赖 0.2，需要注意版本兼容或使用 `embedded-hal-bridge` 转换。

### 本节小结

Rust 嵌入式开发以 `no_std` 为基础，通过 `core`/`alloc`/`std` 三层标准库精确控制依赖范围。`cortex-m-rt` 提供启动运行时，自动处理向量表和 `.data`/`.bss` 初始化，`cargo run` + `probe-run` 一键完成编译、烧录、运行、日志输出。PAC 提供类型安全的寄存器访问，HAL 构建在 PAC 之上并遵循 `embedded-hal` trait，实现了平台无关的驱动复用——这是 C 嵌入式生态缺乏的统一抽象。`defmt` 的延迟格式化将日志开销降到最低，格式化字符串完全不占用 MCU Flash。中断处理通过 `#[interrupt]` 宏自动注册，共享状态通过 `interrupt::free` + `Mutex<RefCell<T>>` 在编译期保证临界区安全，消除了 C 中"忘记关中断"的常见错误。与 C 嵌入式开发（可参考《../../01-C++技术体系/09-嵌入式开发/04-中断系统与RTOS原理.md》《../../01-C++技术体系/09-嵌入式开发/05-嵌入式Linux系统与驱动开发.md》）相比，Rust 在保留底层控制能力的同时，通过类型系统和所有权消除了内存错误和数据竞争，`embedded-hal` 驱动生态和 `defmt` 日志是显著的差异化优势。对于主流 Cortex-M 系列，Rust 已具备生产级嵌入式开发能力。

---

上一篇：《02-HTTP服务与Web后端.md》
下一篇：《04-操作系统与底层开发.md》
