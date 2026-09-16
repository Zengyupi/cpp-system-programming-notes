# MCU启动流程与嵌入式C关键技术

> 本节目标：深入理解 MCU 的内存映射、程序段布局与从上电到 main 的完整启动流程，掌握链接脚本如何决定内存布局；熟练运用嵌入式 C 的关键技术——volatile、寄存器位操作、对齐与字节序、临界区保护、环形缓冲区；并理解 C++ 在嵌入式场景中的可行性、代价与静态化写法。学完后能独立编写启动代码、链接脚本，并写出高效、安全的嵌入式 C/C++ 代码。

---

## 本章速览

- [1. MCU 内存模型与启动过程](#1-mcu-内存模型与启动过程)
  - [1.1 总线矩阵与存储映射（以 Cortex-M / STM32 为例）](#11-总线矩阵与存储映射以-cortex-m--stm32-为例)
  - [1.2 程序的段布局](#12-程序的段布局)
  - [1.3 启动流程：从上电到 main](#13-启动流程从上电到-main)
  - [1.4 链接脚本（.ld）决定内存布局](#14-链接脚本ld决定内存布局)
  - [1.5 栈大小怎么估](#15-栈大小怎么估)
- [2. 嵌入式 C 关键技术](#2-嵌入式-c-关键技术)
  - [2.1 volatile：嵌入式第一关键字](#21-volatile嵌入式第一关键字)
  - [2.2 寄存器位操作（读-改-写）](#22-寄存器位操作读-改-写)
  - [2.3 对齐、字节序与 packed](#23-对齐字节序与-packed)
  - [2.4 static / const / 宏在嵌入式的用法](#24-static--const--宏在嵌入式的用法)
  - [2.5 临界区保护](#25-临界区保护)
  - [2.6 环形缓冲区（Ring/Circular Buffer）——串口收发必备](#26-环形缓冲区ringcircular-buffer串口收发必备)
- [3. 嵌入式 C++ 可行性与静态化写法](#3-嵌入式-c-可行性与静态化写法)
  - [3.1 C++ 特性在嵌入式的代价分析](#31-c-特性在嵌入式的代价分析)
  - [3.2 静态化写法：禁用异常/RTTI + placement new + 静态分配](#32-静态化写法禁用异常rtti--placement-new--静态分配)
  - [3.3 C++ 在嵌入式的适用场景与限制](#33-c-在嵌入式的适用场景与限制)
- [4. 快速参考卡片](#4-快速参考卡片)
- [5. 常见坑](#5-常见坑)

---

## 1. MCU 内存模型与启动过程

### 1.1 总线矩阵与存储映射（以 Cortex-M / STM32 为例）

```text
0xFFFFFFFF ┌───────────────┐
           │  系统/内核外设   │  0xE0000000  NVIC/SysTick/SCB
0xE0100000 ├───────────────┤
           │  外部设备 FSMC  │  0xA0000000
0xA0000000 ├───────────────┤
           │  片上外设区      │  0x40000000  GPIO/USART/I2C/SPI 寄存器
0x60000000 ├───────────────┤
           │  SRAM（RAM）     │  0x20000000  可读写，断电丢失（.data/.bss/堆/栈）
0x40000000 ├───────────────┤
           │  Flash（Code）  │  0x08000000  存代码和常量，XIP 直接取指（.text/.rodata）
0x00000000 └───────────────┘
```

- **外设就是一片内存地址**：操作外设 = 读写其寄存器映射地址，这正是需要 `volatile` 的根本原因（见 2.1）。
- **位带（Bit-Banding）**：Cortex-M 把 SRAM/外设区的每一位映射到一个独立地址，写该别名地址等价于原子地置/清某一位，无需"读-改-写"，ISR 与主循环共享标志时无竞态。

### 1.2 程序的段布局

编译产物在 Flash/RAM 中的分布（`size` 命令可查）：

| 段 | 存哪 | 内容 | 上电后处理 |
| --- | --- | --- | --- |
| `.text` | Flash | 代码、指令 | XIP 直接执行 |
| `.rodata` | Flash | const 常量、字符串、查表 | 直接读 |
| `.data` | Flash 存初值，**运行在 RAM** | 非零初始化的全局/静态变量 | Reset 时把初值从 Flash **拷到 RAM** |
| `.bss` | RAM（不占 Flash） | 零初始化/未初始化全局静态变量 | Reset 时**整块清零** |
| heap | RAM 末端方向 | malloc 分配 | 向上增长 |
| stack | RAM 顶部向下 | 局部变量、栈帧、ISR 现场 | 向下增长，与 heap 相向 |

```text
RAM 高地址  0x20020000 ┌──────────┐ ◄ 初始 MSP（栈顶，向量表第 0 项）
                       │  stack   │  向下生长 ↓
                       ├──────────┤
                       │   ↑ heap │  向上生长
                       ├──────────┤
                       │  .bss    │  启动清零
                       ├──────────┤
                       │  .data   │  启动时从 Flash 拷贝初值
RAM 低地址  0x20000000 └──────────┘
   ★ heap 与 stack 相撞 = 栈溢出/堆破坏，是 MCU 最难查的崩溃之一
```

### 1.3 启动流程：从上电到 main

```text
上电复位
 │
 ▼
① 硬件：CPU 从向量表第 0 项取初始 MSP（栈顶指针），第 1 项取 Reset_Handler 地址并跳转
 │   向量表 = 一张函数指针数组：[初始MSP, Reset, NMI, HardFault, MemManage, BusFault,
 │                              UsageFault, ..., SVCall, ..., SysTick, IRQn ...]
 ▼
② Reset_Handler（启动文件 startup_xxx.s，汇编写）：
     - 把 .data 初值从 Flash 拷到 RAM
     - 把 .bss 整块清零
     - 调用 SystemInit()：配时钟树（HSE/PLL）、向量表偏移
     - 调用 __libc_init_array（执行全局 C++ 构造/初始化函数）
     - 跳转 main()
 ▼
③ main：用户初始化外设、创建任务（RTOS）、进入主循环
```

```c
// 中断向量表（C 表达，实际多在启动 .s 文件）
__attribute__((section(".isr_vector")))
void (* const vector_table[])(void) = {
    (void (*)(void))(&_estack),   // 0: 初始主栈指针 MSP（不是函数！）
    Reset_Handler,                // 1: 复位
    NMI_Handler,                  // 2
    HardFault_Handler,            // 3
    // ... SVCall/PendSV/SysTick/外设 IRQ
};
```

### 1.4 链接脚本（.ld）决定内存布局

```ld
/* STM32F407：1M Flash @0x08000000，128K RAM @0x20000000 */
MEMORY {
  FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = 1024K
  RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = 128K
}
/* .data 的加载地址（LMA）在 Flash，运行地址（VMA）在 RAM，启动代码据此拷贝 */
SECTIONS {
  .text : { *(.text*) *(.rodata*) } > FLASH
  _sidata = LOADADDR(.data);              /* .data 初值在 Flash 的位置 */
  .data : { _sdata = .; *(.data*) _edata = .; } > RAM AT > FLASH
  .bss  : { _sbss = .; *(.bss*) *(COMMON) _ebss = .; } > RAM
  /* _estack = ORIGIN(RAM)+LENGTH(RAM)，即栈顶，链接到向量表第 0 项 */
}
```

> 改 RAM/Flash 大小、把某段放到指定地址（如 Bootloader/App 分区）、预留共享内存，都靠改链接脚本。`_sdata/_edata/_sbss/_ebss` 这些符号被启动汇编用来做拷贝/清零。

### 1.5 栈大小怎么估

| 占用 | 来源 |
| --- | --- |
| 任务/线程栈 | 每层函数调用的局部变量 + 传给被调函数的参数 + Cortex-M 异常硬件栈帧：基础 8 字（R0–R3/R12/LR/PC/xPSR）；带 FPU 时扩展栈帧共 26 字（额外压入 S0–S15、FPSCR 与 1 个对齐保留字，即多 18 字；开启懒加载时延迟到 ISR 首次执行浮点指令才真正压入） |
| 中断嵌套 | 每层中断都要在当前栈上压一份硬件栈帧，按最深嵌套累加 |
| 主栈/MSP | 不用 OS 时唯一的栈；用 OS 时中断仍走 MSP，任务走各自 PSP |

方法：先用**偏大**值（如任务 512~1024 字），再用"栈水位线"（FreeRTOS `uxTaskGetStackHighWaterMark`、0xA5 填充法）测实际剩余，逐步收敛。大数组、`printf`（内部缓冲很吃栈）、深层递归是栈杀手。

---

## 2. 嵌入式 C 关键技术

### 2.1 volatile：嵌入式第一关键字

`volatile` 告诉编译器**每次都从内存重新读、不要优化到寄存器、不要重排对它的访问**。三种必加场景：

```c
// ① 内存映射的硬件寄存器（值可能被硬件改变）
#define USART1_SR (*(volatile uint32_t*)0x40011000)
while (!(USART1_SR & (1<<5))) ;     // 没 volatile 编译器可能只读一次变成死循环

// ② ISR 与主循环共享的全局变量
volatile bool flag = false;
void USART1_IRQHandler(void){ flag = true; }
int main(void){ while(!flag); }     // 没 volatile 主循环看不到 ISR 的修改

// ③ 两个线程/主循环与 DMA 共享的缓冲区
```

> 注意：`volatile` **不保证原子性、不保证多线程可见性顺序**（不等于 C++ 的 `std::atomic`）。多核或需要内存屏障时用 atomic/内联 `__DMB()`/`__DSB()`/`__ISB()`。

### 2.2 寄存器位操作（读-改-写）

```c
#define BIT(n)            (1UL << (n))
#define SET_BIT(reg,m)    ((reg) |=  (m))     // 置 1：OR
#define CLR_BIT(reg,m)    ((reg) &= ~(m))     // 清 0：AND 反码
#define TOG_BIT(reg,m)    ((reg) ^=  (m))     // 翻转：XOR
#define GET_BIT(reg,m)    (((reg) & (m)) ? 1 : 0)
#define MOD_FIELD(reg,pos,mask,val) ((reg) = ((reg) & ~(mask)) | (((val)<<(pos)) & (mask)))

GPIOD->MODER |=  (1UL << 26);   // PD13 置输出（MODER 每两位一个引脚：13*2=26）
GPIOD->BSRR   =  (1UL << 13);   // BSRR 低16位置位（原子，推荐，替代 ODR 读改写）
GPIOD->BSRR   =  (1UL << (13+16)); // BSRR 高16位复位
```

> **BSRR/BRR 原子置位**：写一次即生效，避免"读-改-写"在中断打断时丢失另一处的修改；多引脚同时改、或 ISR 也操作同一端口时优先用。

### 2.3 对齐、字节序与 packed

```c
// 外设/协议结构体常要求 1 字节紧凑，不能让编译器插入填充
#pragma pack(push,1)
typedef struct { uint8_t addr; uint16_t reg; uint8_t val; } Cmd_t;  // 紧凑为 4 字节
#pragma pack(pop)
// __attribute__((packed)) 是 GCC 写法；访问非对齐成员在 Cortex-M0 上会触发 HardFault（M3+ 多数支持非对齐访问，但仍慢）

// 网络/传感器多为大端，Cortex-M 为小端，需手动转换
uint16_t bswap16(uint16_t x){ return (x>>8) | (x<<8); }
uint32_t bswap32(uint32_t x){ return __builtin_bswap32(x); }
```

### 2.4 static / const / 宏在嵌入式的用法

| 关键字 | 嵌入式用途 |
| --- | --- |
| `static` 局部 | 值跨调用保留且只初始化一次；**放在 .data/.bss 而非栈上**，避免大局部数组吃栈 |
| `static` 全局/函数 | 文件内可见，避免多文件符号冲突，利于编译器内联优化 |
| `const` | 进 Flash（.rodata）不占 RAM；查表、字符串、配置都加 const 省 RAM |
| `#define` / `enum` | 寄存器位、状态码；编译期常量不占任何运行时资源 |

### 2.5 临界区保护

共享数据被主循环和 ISR（或多个任务）访问时，必须保证"读-改-写"原子：

```c
// 裸机：关中断进出临界区（Cortex-M，BASEPRI 只屏蔽低于某优先级的中断，比全局 PRIMASK 更优雅）
#define ENTER_CRITICAL()  uint32_t base = __get_BASEPRI(); __set_BASEPRI(configMAX_SYSCALL_INTERRUPT_PRIORITY)
#define EXIT_CRITICAL()   __set_BASEPRI(base)

// FreeRTOS：任务侧用（内部处理优先级，ISR 侧要用 ...FromISR 版本）
taskENTER_CRITICAL();
shared_counter++;                 // 临界区内不能阻塞、不能调会阻塞的 API
taskEXIT_CRITICAL();
```

原则：**临界区尽量短**；ISR 内不要关中断等待；能用"ISR 只发通知、任务再处理"就不在临界区做重活。

### 2.6 环形缓冲区（Ring/Circular Buffer）——串口收发必备

单生产者（ISR/DMA 写 head）单消费者（主循环读 tail），head/tail 各只有一方修改，可做到**无锁**：

```c
#include <stdint.h>
#include <stdbool.h>
#define RB_SIZE 256                      // 必须是 2 的幂，可用 &(SIZE-1) 代替取模
typedef struct {
    uint8_t  buf[RB_SIZE];
    volatile uint16_t head;             // 生产者(写)只改 head
    volatile uint16_t tail;             // 消费者(读)只改 tail
} RingBuf;

static inline bool rb_push(RingBuf *rb, uint8_t b) {       // ISR 中调用
    uint16_t next = (rb->head + 1) & (RB_SIZE - 1);
    if (next == rb->tail) return false;                   // 满，丢弃（可加溢出计数）
    rb->buf[rb->head] = b;
    rb->head = next;                                      // 最后更新 head，保证可见顺序
    return true;
}
static inline bool rb_pop(RingBuf *rb, uint8_t *b) {      // 主循环调用
    if (rb->head == rb->tail) return false;               // 空
    *b = rb->buf[rb->tail];
    rb->tail = (rb->tail + 1) & (RB_SIZE - 1);
    return true;
}
// 判空：head==tail；判满：(head+1)&(SIZE-1)==tail（牺牲一个槽区分空/满）
```

---

## 3. 嵌入式 C++ 可行性与静态化写法

嵌入式领域长期以 C 为主，但 C++ 在中大型 MCU（Cortex-M4/M7、ESP32、带 FPU 的芯片）上已完全可用。关键不是"能不能用"，而是"用哪些特性、禁用哪些特性"。

### 3.1 C++ 特性在嵌入式的代价分析

| C++ 特性 | 嵌入式代价 | 建议 |
| --- | --- | --- |
| **异常（Exception）** | 每个 try/catch 生成展开表（.gcc_except_table，通常几十~几百 KB）；throw 路径代码膨胀；运行时 unwinding 不确定耗时；new 失败默认抛异常 | **禁用**（`-fno-exceptions`），用返回码/断言 |
| **RTTI（运行时类型识别）** | `typeid`/`dynamic_cast` 需为每个多态类生成 typeinfo，增加 Flash；dynamic_cast 运行时遍历类层级树，耗时不确定 | **禁用**（`-fno-rtti`），用静态多态/枚举 |
| **动态内存（new/delete）** | 默认调用 malloc/free，堆碎片、分配耗时不确定、失败处理复杂；与 C 的 malloc 共享同一堆 | **限制使用**：初始化阶段一次性分配，运行期用静态池/placement new |
| **虚函数（virtual）** | 每个对象多一个 vptr 指针（4 字节）；每个多态类一个 vtable（Flash）；调用多一次间接跳转（几 ns，可接受） | **可用**，但避免在高频中断路径滥用；注意 vtable 占 Flash |
| **模板（Template）** | 编译期展开，零运行时开销；但每个实例化生成独立代码，可能导致 Flash 膨胀 | **可用**，控制实例化数量；用 `extern template` 显式实例化 |
| **STL 容器** | `std::vector`/`std::map` 内部动态分配；`std::string` 小字符串优化但仍可能分配 | **谨慎**：用固定容量的环形缓冲/数组替代；需要时用自定义分配器 |
| **构造/析构** | 全局对象构造在 `__libc_init_array` 中执行（启动文件已调用）；构造顺序跨翻译单元未定义 | **可用**，避免全局对象间构造依赖；局部对象在栈上构造 |
| **constexpr / 编译期计算** | 零运行时开销，替代宏和查表 | **推荐** |

### 3.2 静态化写法：禁用异常/RTTI + placement new + 静态分配

#### 编译选项

```bash
arm-none-eabi-g++ -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard \
  -fno-exceptions -fno-rtti -fno-threadsafe-statics \
  -ffunction-sections -fdata-sections -Wl,--gc-sections \
  -Os -g main.cpp -o app.elf -T stm32f407.ld
# -fno-exceptions: 禁用异常，new 失败返回 nullptr（需定义 nothrow 行为）
# -fno-rtti: 禁用 RTTI
# -fno-threadsafe-statics: 去掉局部静态变量的线程安全锁（单线程/RTOS 自己保护时省代码）
```

#### placement new：在预分配内存上构造对象，不触发堆分配

```cpp
#include <new>
// 静态缓冲区，对齐到最大对齐要求
alignas(std::max_align_t) static uint8_t sensor_buf[sizeof(TempSensor)];
static TempSensor* sensor = nullptr;

void sensor_init(void) {
    sensor = new (sensor_buf) TempSensor(0x48);  // placement new：在 sensor_buf 上构造
}
void sensor_deinit(void) {
    sensor->~TempSensor();  // 显式调用析构，不调用 delete（不释放内存）
    sensor = nullptr;
}
```

#### 固定容量容器替代 STL 动态容器

```cpp
// 固定容量环形队列（模板 + 静态数组，零堆分配）
template<typename T, size_t N>
class FixedQueue {
    T buf[N];
    size_t head = 0, tail = 0, count = 0;
public:
    bool push(const T& v) {
        if (count >= N) return false;
        buf[tail] = v;
        tail = (tail + 1) % N;
        ++count;
        return true;
    }
    bool pop(T& out) {
        if (count == 0) return false;
        out = buf[head];
        head = (head + 1) % N;
        --count;
        return true;
    }
};
```

#### 禁用异常后的 new 处理

```cpp
// 禁用异常后，operator new 失败默认调用 std::new_handler 或终止
// 推荐用 nothrow 版本，显式检查返回值
#include <new>
MyObj* p = new (std::nothrow) MyObj();
if (!p) { /* 内存不足处理 */ }

// 更彻底：全局重载 operator new/delete 走内存池
void* operator new(size_t size) { return pool_alloc(size); }
void  operator delete(void* p) noexcept { pool_free(p); }
```

### 3.3 C++ 在嵌入式的适用场景与限制

| 场景 | 推荐度 | 理由 |
| --- | --- | --- |
| 应用层业务逻辑、协议栈、状态机 | **强烈推荐** | 类/封装/RAII 提升可维护性，资源充足 |
| 驱动层（寄存器操作、ISR） | **谨慎** | 虚函数调用开销、构造顺序问题；C 更直接 |
| 中断服务例程（ISR） | **不推荐用 C++ 特性** | ISR 必须 C 链接（`extern "C"`）、不能抛异常、不能动态分配；可调用静态成员函数 |
| 极小资源 MCU（Flash<64K, RAM<16K） | **不推荐** | C++ 运行时（vtable/typeinfo/构造数组）基础开销可能超预算 |
| 中大型 MCU + RTOS（ESP32、STM32H7） | **推荐** | 资源充足，C++ 生态（LVGL 绑定、Embedded Template Library）成熟 |
| 嵌入式 Linux 应用层 | **推荐** | 资源无限制，可完整使用 C++17/20 |

> **常见坑**：① 忘加 `extern "C"` 导致 ISR 符号名被 C++ mangling 后链接不到启动文件；② 全局对象构造函数里操作了尚未初始化的硬件（构造在 main 之前）；③ `std::function` 内部堆分配导致运行期不确定；④ 虚析构函数缺失导致子类资源泄漏。用 **ETL（Embedded Template Library）** 替代 STL 是工业界常见做法——它提供固定容量容器、无异常、无 RTTI、确定内存占用。

---

## 4. 快速参考卡片

### 从上电到 main 的检查清单

1. 向量表第 0 项 = 初始 MSP（`_estack`），第 1 项 = Reset_Handler；
2. Reset_Handler：拷 `.data`（Flash→RAM）→ 清 `.bss` → `SystemInit()` 配时钟 → `__libc_init_array()` → `main()`；
3. 链接脚本 `_sidata/_sdata/_edata/_sbss/_ebss` 必须与启动汇编符号一一对应。

### 关键字/宏速查

| 写法 | 用途 |
| --- | --- |
| `volatile uint32_t*` | 外设寄存器、ISR 与主循环共享变量、DMA 缓冲 |
| `BSRR` 写 `1<<n` / `1<<(n+16)` | 原子置位/复位，替代 `ODR` 读-改-写 |
| `__get_BASEPRI`/`__set_BASEPRI` | 裸机临界区，只屏蔽低于阈值的中断 |
| `taskENTER_CRITICAL`/`...FromISR` | FreeRTOS 任务侧 / ISR 侧分工 |
| `__attribute__((packed))` / `#pragma pack(1)` | 协议/外设结构体紧凑 |
| `-fno-exceptions -fno-rtti -fno-threadsafe-statics` | 嵌入式 C++ 三禁 |
| `new (buf) T(...)` + 显式 `~T()` | placement new，不触发堆分配 |

---

## 5. 常见坑

1. **漏加 volatile 导致死循环/读旧值**：内存映射寄存器或 ISR 改写的标志不加 volatile，编译器把循环优化成"只读一次"。
2. **临界区里做长事或阻塞**：关中断期间调用 `printf`/延时，丢中断、破坏实时性；临界区只保护"读-改-写"，越短越好。
3. **环形缓冲区 size 非 2 的幂**：代码用 `&(SIZE-1)` 代替取模，一旦 size 改成非 2 的幂位运算即错；判满靠"牺牲一个槽"（`next==tail`）。
4. **heap 与 stack 相撞**：大局部数组、深递归、`printf` 内部缓冲吃栈，栈向上/堆向下增长最终撞穿，现象是随机 HardFault；用栈水位线（0xA5 填充 / `uxTaskGetStackHighWaterMark`）实测。
5. **`.data` 初值没拷进 RAM**：链接脚本 `AT > FLASH` 与启动代码拷数符号不匹配，全局变量初值异常；改内存分区后必须同时改 `.ld` 与启动文件。
6. **packed 结构体非对齐访问**：Cortex-M0/M0+ 访问 packed 内的 `uint16_t/uint32_t` 成员直接 HardFault；M3+ 虽支持但更慢，总线/DMA 访问地址仍要对齐。
7. **C++ 全局对象构造在 main 之前**：构造函数里操作尚未 `SystemInit()` 的硬件，或跨翻译单元构造顺序未定义；硬件初始化放 `main` 或显式两阶段 init。
8. **ISR 漏 `extern "C"`**：C++ 编译后函数名 mangling，启动文件按 C 符号引用导致链接失败；所有向量表 ISR 入口必须 `extern "C"`。

---

上一篇：《01-嵌入式开发导论与硬件基础.md》　｜　下一篇：《03-外设总线与DMA定时器.md》　｜　模块索引：《../README.md》
