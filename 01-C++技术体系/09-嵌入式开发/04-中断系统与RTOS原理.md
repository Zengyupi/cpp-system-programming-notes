# 中断系统与RTOS原理

> 本节目标：掌握 Cortex-M NVIC 中断系统的优先级分组、嵌套机制与 ISR 编写铁律；理解裸机前后台系统与 RTOS 的本质区别；深入 FreeRTOS 的全部核心 API——任务创建/调度、队列、信号量/互斥量、事件组、任务通知、流缓冲/消息缓冲，每个配实操代码；掌握实时性分析方法——中断延迟组成与测量、RMA/EDF 调度算法的可调度性判定、优先级反转与优先级继承。学完后能独立设计基于 RTOS 的嵌入式软件架构，并对系统实时性做出量化评估。

---

## 本章速览

- [1. 中断系统](#1-中断系统)
  - [1.1 优先级与嵌套](#11-优先级与嵌套)
  - [1.2 ISR 编写铁律](#12-isr-编写铁律)
  - [1.3 顶半部 / 底半部](#13-顶半部--底半部)
- [2. 软件开发模式](#2-软件开发模式)
  - [2.1 裸机：前后台系统](#21-裸机前后台系统)
  - [2.2 FreeRTOS API 深度](#22-freertos-api-深度)
  - [2.3 嵌入式 Linux](#23-嵌入式-linux)
- [3. 实时性分析](#3-实时性分析)
  - [3.1 中断延迟组成与测量](#31-中断延迟组成与测量)
  - [3.2 RMA（速率单调分析）](#32-rma速率单调分析)
  - [3.3 EDF（最早截止优先）](#33-edf最早截止优先)
  - [3.4 优先级反转与优先级继承（实时性视角）](#34-优先级反转与优先级继承实时性视角)
- [4. 快速参考卡片](#4-快速参考卡片)
- [5. 常见坑](#5-常见坑)

---

## 1. 中断系统

### 1.1 优先级与嵌套

- Cortex-M 中断优先级数值**越小优先级越高**；分为**抢占优先级**（能否打断别的中断）和**子优先级**（同时 pending 时谁先执行），由优先级分组位（NVIC_PriorityGroup）切分。
- 高抢占优先级 ISR 可**嵌套**打断低优先级 ISR；同抢占级不嵌套，按子优先级/硬件编号排队。
- FreeRTOS 把优先级划成两部分：高于 `configMAX_SYSCALL_INTERRUPT_PRIORITY` 的中断**不调任何 RTOS API、不被临界区屏蔽**（追求最快响应），其余可调 `...FromISR` API。

### 1.2 ISR 编写铁律

```c
// 好的 ISR：只做最少的事——取数据、清标志、发通知，重活留给任务
extern RingBuf uart_rx_rb;
void USART1_IRQHandler(void) {
    if (USART1->SR & USART_SR_RXNE) {
        uint8_t b = USART1->DR;              // 读 DR 同时清 RXNE
        rb_push(&uart_rx_rb, b);             // 塞进环形缓冲
    }
    if (USART1->SR & USART_SR_ORE) { (void)USART1->DR; }  // 读 SR 再读 DR 清溢出
    // 通知任务：xSemaphoreGiveFromISR / vTaskNotifyGiveFromISR + portYIELD_FROM_ISR
}
```

| 铁律 | 原因 |
| --- | --- |
| 尽量短、不做延时/循环等待 | ISR 执行期间同级或低级中断被压住，过长导致丢中断/喂狗不及 |
| 不在 ISR 里用阻塞 API、`printf`、malloc | 不确定时长、可能死锁、堆非可重入 |
| 共享变量加 volatile，复合操作进临界区 | 防编译器优化与竞态 |
| 进 ISR 先查标志、退出前清标志 | 避免重复进中断；标志清除方式因芯片而异（写 0/读再写/硬件自动） |
| RTOS 用 FromISR 版本 API | 普通版本会触发断言/破坏调度 |

### 1.3 顶半部 / 底半部

ISR（顶半部）只捕获事件、把数据入队并发出通知；任务/线程（底半部）再做解析、协议处理、应答。这样中断延迟最小，也避免在 ISR 里做耗时工作——与 Linux 中断的 hardirq/softirq/tasklet 思想一致。

---

## 2. 软件开发模式

### 2.1 裸机：前后台系统

后台 = main 超级循环（while(1) 轮询各模块），前台 = ISR。复杂裸机常用**时间片轮询（协作式调度器）**替代阻塞 delay：

```c
// 时间片轮询：每个任务按自己的周期执行，主循环不阻塞，实时性远好于 delay 串联
typedef struct { void (*task)(void); uint32_t period; uint32_t last; } Task_t;
Task_t tasks[] = { {read_sensor,10,0}, {refresh_ui,50,0}, {send_report,1000,0} };
uint32_t now;
int main(void){
    timer_init();                       // 1ms 心跳，now 在 SysTick 里 ++
    for(;;){
        now = get_tick();
        for (unsigned i=0;i<sizeof(tasks)/sizeof(tasks[0]);++i)
            if (now - tasks[i].last >= tasks[i].period){
                tasks[i].last = now;
                tasks[i].task();        // 每个任务必须快速返回，不能阻塞
            }
        __WFI();                        // 没事做就休眠等中断，省电
    }
}
```

### 2.2 FreeRTOS API 深度

FreeRTOS 是市占率最高的 RTOS，内核极小（最小 ~6KB Flash、~1KB RAM），API 设计简洁。以下按"任务→IPC→同步→内存"的顺序逐一讲解并配代码。

#### （1）任务创建与调度

```c
#include "FreeRTOS.h"
#include "task.h"

// 任务函数：返回 void，参数 void*，必须是无限循环或调用 vTaskDelete(NULL)
void sensor_task(void *pvParameters) {
    const TickType_t period = pdMS_TO_TICKS(100);  // 100ms 周期
    TickType_t last_wake = xTaskGetTickCount();
    for (;;) {
        read_sensor();
        process_data();
        // vTaskDelayUntil 精确周期（从 last_wake 算起），vTaskDelay 是相对延时
        vTaskDelayUntil(&last_wake, period);
    }
}

int main(void) {
    // xTaskCreate(任务函数, 任务名, 栈深度(字!), 参数, 优先级, 任务句柄)
    // 优先级：数值越大优先级越高；configMAX_PRIORITIES 定义最大级数
    xTaskCreate(sensor_task, "Sensor", 256, NULL, 3, NULL);
    xTaskCreate(ui_task,     "UI",     512, NULL, 2, NULL);
    xTaskCreate(comm_task,   "Comm",   384, NULL, 4, NULL);

    vTaskStartScheduler();  // 启动调度器，永不返回（除非内存不足）
    for (;;);               // 不会到这里
}
```

**任务状态机**：

```text
            创建
             ▼
        ┌────────┐  就绪/被更高优先级抢占   ┌────────┐
        │ Blocked│◄────延迟/等信号量──────│ Ready  │──调度器选中──►┌─────────┐
        │ 阻塞   │────超时/获得资源──────►│ 就绪   │◄─时间片到─────│ Running │
        └────────┘                        └────────┘              └─────────┘
             ▲  vTaskSuspend                  │ vTaskDelete
             └──────── Suspended 挂起 ◄───────┘
```

- **优先级抢占式**：永远运行处于就绪态的**最高优先级**任务；高优先级就绪立即抢占低优先级。
- **时间片轮转**：同优先级任务按一个 SysTick tick 轮流运行（`configUSE_TIME_SLICING`）。
- 调度发生点：tick 中断、任务阻塞、任务就绪（`...FromISR`）、主动让出（`taskYIELD()`）。

#### （2）队列（Queue）

队列是任务间/ISR→任务传递数据的核心机制，**自带拷贝与阻塞，线程安全**。

```c
#include "queue.h"

typedef struct { uint32_t id; float value; } SensorData_t;
static QueueHandle_t xSensorQueue;

void producer_task(void *p) {
    SensorData_t data;
    for (;;) {
        data.id = 1; data.value = read_adc();
        // 发送到队列尾，阻塞最多 10 个 tick 等待空间
        xQueueSend(xSensorQueue, &data, pdMS_TO_TICKS(10));
        vTaskDelay(pdMS_TO_TICKS(50));
    }
}

void consumer_task(void *p) {
    SensorData_t data;
    for (;;) {
        // 从队列头接收，portMAX_DELAY = 无限等待
        if (xQueueReceive(xSensorQueue, &data, portMAX_DELAY) == pdPASS) {
            process(data);
        }
    }
}

// ISR 中必须用 FromISR 版本
void ADC_IRQHandler(void) {
    SensorData_t data = { .id = 1, .value = ADC->DR };
    BaseType_t higher_priority_task_woken = pdFALSE;
    xQueueSendFromISR(xSensorQueue, &data, &higher_priority_task_woken);
    portYIELD_FROM_ISR(higher_priority_task_woken);  // 如果唤醒了更高优先级任务，立即切换
}

int main(void) {
    // 创建队列：长度 10，每个元素 sizeof(SensorData_t)
    xSensorQueue = xQueueCreate(10, sizeof(SensorData_t));
    xTaskCreate(producer_task, "Prod", 128, NULL, 2, NULL);
    xTaskCreate(consumer_task, "Cons", 128, NULL, 3, NULL);
    vTaskStartScheduler();
}
```

> 队列也可作"邮箱"用（`xQueueOverwrite` 覆盖最新值），或传递指针（队列元素是 `void*`，注意指向的内存生命周期）。

#### （3）信号量与互斥量

| 原语 | 用途 | 关键区别 |
| --- | --- | --- |
| 二值信号量 | ISR→任务"有事件了" | 同步，不计数，不能在 ISR 中获取 |
| 计数信号量 | 资源池（N 个资源）、事件计数 | 可累计，最大计数值创建时指定 |
| **互斥量 Mutex** | 保护临界资源 | **带优先级继承**，解决优先级反转；不能在 ISR 用 |
| 递归互斥 | 同一任务多次获取 | 避免自死锁，获取/释放次数必须匹配 |

```c
// 二值信号量：ISR 通知任务处理
static SemaphoreHandle_t xDataReadySem;

void DATA_IRQHandler(void) {
    BaseType_t woken = pdFALSE;
    xSemaphoreGiveFromISR(xDataReadySem, &woken);  // 给出信号量
    portYIELD_FROM_ISR(woken);
}

void handler_task(void *p) {
    for (;;) {
        // 等待信号量，无限超时
        if (xSemaphoreTake(xDataReadySem, portMAX_DELAY) == pdTRUE) {
            process_hardware_data();  // 重活在任务里做，不在 ISR
        }
    }
}

// 互斥量：保护共享资源（带优先级继承）
static SemaphoreHandle_t xSpiMutex;

void spi_transaction(uint8_t *tx, uint8_t *rx, size_t len) {
    xSemaphoreTake(xSpiMutex, portMAX_DELAY);   // 获取互斥锁
    HAL_SPI_TransmitReceive(&hspi1, tx, rx, len, 100);
    xSemaphoreGive(xSpiMutex);                    // 释放
}

// 初始化
xDataReadySem = xSemaphoreCreateBinary();  // 二值信号量
xSpiMutex     = xSemaphoreCreateMutex();    // 互斥量（带优先级继承）
```

#### （4）事件组（Event Group）

事件组允许一个任务同时等待多个事件（"与"逻辑：全部发生；"或"逻辑：任一发生），每个事件用一个 bit 表示。

```c
#include "event_groups.h"

#define BIT_TEMP_READY   (1 << 0)
#define BIT_HUMI_READY   (1 << 1)
#define BIT_NET_CONNECTED (1 << 2)

static EventGroupHandle_t xEventGroup;

void sensor_task(void *p) {
    for (;;) {
        read_temp();
        xEventGroupSetBits(xEventGroup, BIT_TEMP_READY);  // 置位
        read_humi();
        xEventGroupSetBits(xEventGroup, BIT_HUMI_READY);
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

void report_task(void *p) {
    for (;;) {
        // 等待"温度 AND 湿度"都就绪（与逻辑），等待后自动清除这两个 bit
        EventBits_t bits = xEventGroupWaitBits(
            xEventGroup,
            BIT_TEMP_READY | BIT_HUMI_READY,  // 关心的 bit
            pdTRUE,    // xClearOnExit：退出时清除
            pdTRUE,    // xWaitForAllBits：等待全部（与逻辑）；pdFALSE = 任一（或逻辑）
            portMAX_DELAY);
        if (bits & (BIT_TEMP_READY | BIT_HUMI_READY)) {
            send_report();
        }
    }
}

xEventGroup = xEventGroupCreate();
```

> 事件组在 32 位平台上有 24 个可用 bit（高 8 位内核保留）。ISR 中用 `xEventGroupSetBitsFromISR`。

#### （5）任务通知（Task Notification）

任务通知是 FreeRTOS 最轻量的 IPC 机制——**直接发送到目标任务的通知值**，无需创建队列/信号量对象，RAM 占用几乎为零（每个任务 TCB 里自带一个 32 位通知值）。多数场景可替代二值信号量、计数信号量、事件组。

```c
// 用任务通知替代二值信号量：ISR 通知任务
void DATA_IRQHandler(void) {
    BaseType_t woken = pdFALSE;
    // 向 handler_task_handle 发送通知（递增通知值，类似计数信号量）
    vTaskNotifyGiveFromISR(handler_task_handle, &woken);
    portYIELD_FROM_ISR(woken);
}

void handler_task(void *p) {
    for (;;) {
        // 等待通知，pdTRUE=取走后清零（类似二值信号量）；pdFALSE=递减（类似计数信号量）
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        process_data();
    }
}

// 用任务通知传递数值（替代队列/事件组的轻量场景）
void producer_task(void *p) {
    uint32_t value = 0;
    for (;;) {
        value = read_sensor();
        // eSetValueWithOverwrite：覆盖目标任务通知值（不等待）
        xTaskNotify(consumer_handle, value, eSetValueWithOverwrite);
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}

void consumer_task(void *p) {
    uint32_t value;
    for (;;) {
        // 等待通知，取出通知值到 value
        xTaskNotifyWait(0, 0xFFFFFFFF, &value, portMAX_DELAY);
        process(value);
    }
}
```

> 任务通知的局限：只能一对一（一个任务通知另一个任务），不能广播；不能被多个任务同时等待。需要多对多或广播时仍用队列/事件组。

#### （6）流缓冲与消息缓冲

流缓冲（Stream Buffer）传递**字节流**（类似管道），消息缓冲（Message Buffer）传递**定长消息**（每条消息带长度头）。两者都基于"单写者单读者"优化，比队列更省拷贝。

```c
#include "stream_buffer.h"

static StreamBufferHandle_t xStreamBuf;
#define STREAM_BUF_SIZE 1024

void uart_rx_task(void *p) {
    uint8_t buf[128];
    for (;;) {
        // 从流缓冲读取，至少等 1 字节，最多等 128 字节，超时 100ms
        size_t n = xStreamBufferReceive(xStreamBuf, buf, sizeof(buf), pdMS_TO_TICKS(100));
        if (n > 0) process_uart_data(buf, n);
    }
}

// DMA 完成中断中写入流缓冲
void DMA_Stream_IRQHandler(void) {
    BaseType_t woken = pdFALSE;
    xStreamBufferSendFromISR(xStreamBuf, dma_buf, dma_len, &woken);
    portYIELD_FROM_ISR(woken);
}

xStreamBuf = xStreamBufferCreate(STREAM_BUF_SIZE, 1);  // 触发级别=1：有 1 字节就唤醒读者
```

#### （7）优先级反转与优先级继承【高频】

```text
低优先级 L 持有互斥锁 → 高优先级 H 也要这把锁被迫等 L →
中优先级 M（不需要锁）就绪后抢占 L 一直跑 → H 被 M 间接阻塞，甚至无限期
解决：互斥量带【优先级继承】——H 等待时，把 L 临时提到 H 的优先级，
      让 L 尽快释放锁，随后恢复，M 无法再插队。（二值信号量没有此机制！）
```

> 优先级继承只能缓解优先级反转，不能完全消除（继承期间 L 仍可能被更高优先级抢占）。FreeRTOS 的互斥量默认启用优先级继承；二值信号量**没有**继承机制，保护共享资源必须用 Mutex 而非 Semaphore。

#### （8）内存与栈

- 任务创建：`xTaskCreate` 栈深度参数单位是**字（word）**，32 位平台 128 字=512 字节，不是 128 字节。
- 三种堆方案：`heap_1`（只分配不释放，最安全）、`heap_4`（合并相邻空闲块，常用）、`heap_5`（多块非连续内存）。**确定性场景尽量在初始化时创建完所有任务/队列，运行期不动态创建**，避免碎片与不确定耗时。
- 栈溢出检测：`configCHECK_FOR_STACK_OVERFLOW` 设为 1 或 2，在钩子函数 `vApplicationStackOverflowHook` 中记录并复位。

#### （9）主流 RTOS 对比

| RTOS | 内核特点 | 许可 | 组件/生态 | 适用场景 |
| --- | --- | --- | --- | --- |
| **FreeRTOS** | 微内核、抢占式、优先级继承、任务通知 | MIT | 内核极简，组件需自行集成（lwIP/FatFS）；资料最多、市占率最高 | 通用 MCU、IoT、工业控制 |
| **RT-Thread** | 分层架构（内核+组件+设备框架），FinSH Shell | Apache-2.0 | 设备驱动框架、网络协议栈、文件系统、AI 组件一站式；国产社区活跃 | IoT 网关、消费电子、国产芯片 |
| **Zephyr** | 微内核+可配置，设备树驱动模型，多架构 | Apache-2.0 | Linux 基金会托管，原生支持 BLE/Thread/WiFi，Devicetree，CMake/Kconfig | 低功耗蓝牙、可穿戴、智能家居、多架构产品 |
| NuttX | POSIX 兼容（API 接近 Linux），可加载应用 | Apache-2.0 | 类 Linux 编程体验，VFS/网络/POSIX 接口完整 | 从 Linux 移植、无人机（PX4） |
| ThreadX | picokernel 设计，极快响应，高安全认证（IEC 61508/ISO 26262） | MIT | 安全认证齐全，GUIX 文件系统/网络组件 | 医疗、汽车、航空航天等高安全领域 |
| μC/OS-III | 教学经典， round-robin+抢占，认证齐全 | Apache-2.0 | 文档详尽，配套 μC/FS/μC/TCP-IP | 教学、工业控制 |

### 2.3 嵌入式 Linux

在 MPU 上运行完整内核，支持多进程、网络协议栈、文件系统、GUI、容器；开发方式与服务器 Linux 接近，但要自己做**板级移植、内核/驱动裁剪、根文件系统构建**。典型最小资源：带 MMU 的 Cortex-A、32MB+ RAM。详见《05-嵌入式Linux系统与驱动开发.md》。

---

## 3. 实时性分析

实时系统的核心是**确定性**——不仅要算得对，还要在截止期前算完。本节给出量化分析方法。

### 3.1 中断延迟组成与测量

中断延迟（Interrupt Latency）指从中断请求发生到 ISR 第一条指令执行的时间。

```text
中断延迟 = 硬件延迟 + 指令完成延迟 + 中断禁用时间 + 上下文切换时间
           │           │              │              └─ 压栈 R0-R3/R12/LR/PC/xPSR（硬件自动，12 周期）
           │           │              └─ 最长的关中断/临界区持续时间（主要变量！）
           │           └─ 当前正在执行的指令完成（最长 LDM/STM 多寄存器加载，约 12 周期）
           └─ 中断信号同步到内核时钟（1~3 周期）
```

| 组成 | Cortex-M 典型值 | 说明 |
| --- | --- | --- |
| 硬件同步 | 1~3 周期 | 不可避免 |
| 指令完成 | 最多 ~12 周期 | 多加载/存储指令 |
| 关中断时间 | 0~数百周期 | **主要优化目标**：临界区越短越好 |
| 异常入口（压栈） | 12 周期（零等待内存） | 硬件自动，含取向量 |
| **总计（最佳）** | **~16 周期** | 168MHz 下约 95ns |
| **总计（典型）** | **几十~几百周期** | 取决于临界区长度 |

#### 测量方法

```c
// 方法1：用 DWT 周期计数器精确测量（Cortex-M3+ 都有 DWT）
volatile uint32_t isr_start_cycle, isr_end_cycle;

void MEASURE_IRQHandler(void) {
    isr_start_cycle = DWT->CYCCNT;   // ISR 第一条可执行指令处记录
    // ... ISR 实际处理 ...
    isr_end_cycle = DWT->CYCCNT;
}

// 方法2：GPIO 翻转 + 示波器测量（最直观，含硬件延迟）
// 在中断触发源拉高一瞬间，ISR 第一条指令翻转另一个 GPIO，测两个上升沿间距
void TIM_IRQHandler(void) {
    GPIOA->BSRR = (1 << 5);  // ISR 入口立即翻转 PA5
    // ... 处理 ...
    GPIOA->BSRR = (1 << (5+16));  // 出口翻转回来
}
```

> **优化方向**：① 缩短所有 `taskENTER_CRITICAL`/关中断区间；② 用 `BASEPRI` 替代 `PRIMASK`（只屏蔽低优先级中断，高优先级仍可响应）；③ 高频关键中断优先级设为高于 `configMAX_SYSCALL_INTERRUPT_PRIORITY`（不被 RTOS 临界区屏蔽，但不能调 RTOS API）；④ 避免在 ISR 中做耗时操作（顶/底半部分离）。

### 3.2 RMA（速率单调分析）

RMA（Rate-Monotonic Analysis）是固定优先级实时调度的经典理论。**核心结论**：对于周期任务，**周期越短（频率越高）的任务分配越高优先级**是最优的固定优先级分配方案。

#### 可调度性判定公式

给定 n 个独立周期任务，每个任务 i 有：
- 周期 $T_i$（两次释放的间隔）
- 执行时间 $C_i$（最坏情况执行时间 WCET）
- 截止期 = 周期（隐含截止期）

**利用率**：$U = \sum_{i=1}^{n} \frac{C_i}{T_i}$

**RMA 充分条件（Liu & Layland 界）**：

$$U \leq n \left(2^{1/n} - 1\right)$$

| n（任务数） | 利用率上界 |
| --- | --- |
| 1 | 1.000 (100%) |
| 2 | 0.828 (82.8%) |
| 3 | 0.780 (78.0%) |
| 5 | 0.743 (74.3%) |
| 10 | 0.718 (71.8%) |
| ∞ | ln 2 ≈ 0.693 (69.3%) |

> 这是**充分非必要**条件——不满足不一定不可调度，满足则一定可调度。精确判定需用"响应时间分析（RTA）"。

#### 计算示例

三个周期任务：

| 任务 | 周期 T (ms) | 执行时间 C (ms) | 利用率 C/T |
| --- | --- | --- | --- |
| τ1（最高优先级，周期最短） | 10 | 2 | 0.200 |
| τ2 | 20 | 3 | 0.150 |
| τ3（最低优先级） | 50 | 8 | 0.160 |

总利用率 $U = 0.200 + 0.150 + 0.160 = 0.510$

Liu & Layland 界（n=3）：$3 \times (2^{1/3} - 1) = 3 \times 0.260 = 0.780$

$0.510 \leq 0.780$ → **可调度**。

#### 响应时间分析（RTA，精确判定）

对最低优先级任务 τ3，迭代计算其响应时间 $R$：

$$R^{(k+1)} = C_3 + \sum_{i \in hp(3)} \left\lceil \frac{R^{(k)}}{T_i} \right\rceil C_i$$

其中 $hp(3)$ = 比 τ3 优先级高的任务集合 {τ1, τ2}。

迭代：
- $R^{(0)} = C_3 = 8$
- $R^{(1)} = 8 + \lceil 8/10 \rceil \times 2 + \lceil 8/20 \rceil \times 3 = 8 + 1 \times 2 + 1 \times 3 = 13$
- $R^{(2)} = 8 + \lceil 13/10 \rceil \times 2 + \lceil 13/20 \rceil \times 3 = 8 + 2 \times 2 + 1 \times 3 = 15$
- $R^{(3)} = 8 + \lceil 15/10 \rceil \times 2 + \lceil 15/20 \rceil \times 3 = 8 + 2 \times 2 + 1 \times 3 = 15$

收敛：$R_3 = 15 \text{ms} \leq T_3 = 50 \text{ms}$ → 可调度。

### 3.3 EDF（最早截止优先）

EDF（Earliest Deadline First）是**动态优先级**调度算法——当前就绪任务中，**截止期最早的任务获得 CPU**。优先级随截止期动态变化，不是固定的。

#### 可调度性判定

对于 n 个周期任务（隐含截止期=周期），EDF 的可调度条件是**充分必要**的：

$$U = \sum_{i=1}^{n} \frac{C_i}{T_i} \leq 1$$

即**总利用率不超过 100% 即可调度**。这比 RMA 的 69.3%~100% 界更宽松——EDF 的处理器利用率理论上可达 100%。

#### RMA vs EDF 对比

| 维度 | RMA（固定优先级） | EDF（动态优先级） |
| --- | --- | --- |
| 优先级 | 固定（周期越短越高） | 动态（截止期最早最高） |
| 利用率上界 | 69.3%~100%（取决于 n） | 100%（充分必要） |
| 实现复杂度 | 低（FreeRTOS/RT-Thread 原生支持） | 高（需运行时排序截止期，通用 RTOS 不原生支持） |
| 过载行为 | 可预测（高优先级任务仍满足，低优先级可能丢失） | 不可预测（过载时多米诺效应，所有任务都可能错过截止期） |
| 抖动 | 较小（优先级固定，响应时间确定） | 可能较大（优先级动态变化） |
| 适用 | 工业控制、汽车（硬实时、可预测性优先） | 多媒体、软实时（追求高利用率） |

> **嵌入式实践**：绝大多数商用 RTOS（FreeRTOS/RT-Thread/Zephyr）使用固定优先级抢占调度（等价于 RMA 思想），因为实现简单、过载行为可预测。EDF 更多出现在学术研究和特定软实时场景（如 Linux 的 SCHED_DEADLINE）。

### 3.4 优先级反转与优先级继承（实时性视角）

优先级反转是实时系统中最经典的问题之一，在 2.2 节（7）中已从 API 角度讲解。从实时性分析角度补充：

**优先级反转对可调度性的影响**：当高优先级任务 H 被低优先级任务 L 持有的资源阻塞时，H 的响应时间中需要加入"阻塞时间" $B$——即 L 持有资源的最长时间。RMA 可调度条件修正为：

$$\forall i: \quad C_i + B_i + \sum_{j \in hp(i)} \left\lceil \frac{T_i}{T_j} \right\rceil C_j \leq T_i$$

其中 $B_i$ 是任务 i 被低优先级任务阻塞的最大时间。**优先级继承将 $B_i$ 限制为"低优先级任务持锁的最长临界区时间"**（而非"低优先级任务的整个执行时间"），因为继承期间 L 不会被中优先级任务抢占。

**优先级天花板协议（Priority Ceiling Protocol）** 是比优先级继承更强的机制——每个资源有一个"天花板优先级"（等于可能持有该资源的最高任务优先级），任务获取资源时直接升到天花板优先级，可完全避免链式阻塞和死锁。FreeRTOS 未原生实现天花板协议，需要时可手动用 `vTaskPrioritySet` 模拟。

---

## 4. 快速参考卡片

### ISR vs 任务分工

| 在 ISR（顶半部）做 | 在任务（底半部）做 |
| --- | --- |
| 取数据/清标志/把数据入队 | 协议解析、打印、应答、业务逻辑 |
| `...FromISR` + `portYIELD_FROM_ISR` | 普通阻塞 API |
| 不阻塞、不 malloc、不 printf | 可阻塞、可耗时 |

### FreeRTOS IPC 选型

| 需求 | 选 | 备注 |
| --- | --- | --- |
| ISR→单任务通知 | 任务通知 `vTaskNotifyGiveFromISR` | 最省 RAM，一对一 |
| 传递数据（拷贝） | 队列 | 线程安全、自带阻塞 |
| ISR→任务事件同步 | 二值信号量 | 不保护共享资源 |
| 保护共享资源 | **互斥量 Mutex** | 带优先级继承 |
| 同时等多事件（与/或） | 事件组 | 24 个可用 bit |
| 字节流/定长消息 | 流缓冲/消息缓冲 | 单写单读，比队列省拷贝 |

### 实时性公式速查

| 算法 | 可调度条件 | 利用率上界 |
| --- | --- | --- |
| RMA（固定优先级） | 充分非必要：$U \leq n(2^{1/n}-1)$ | 69.3%~100% |
| EDF（动态优先级） | 充要：$U \leq 1$ | 100% |
| 精确判定 | RTA 迭代响应时间至收敛 | — |

---

## 5. 常见坑

1. **ISR 里调普通 RTOS API**：任务侧 API 不能在 ISR 用，必须用 `...FromISR` 版本并在末尾 `portYIELD_FROM_ISR`，否则触发断言或破坏调度。
2. **ISR 太长/阻塞/printf**：压住低级中断、丢数据；重活一律丢给任务，ISR 只做"取数+清标志+通知"。
3. **用二值信号量保护共享资源**：二值信号量无优先级继承，高优先级任务等锁时可能被中优先级任务无限期阻塞（优先级反转）；保护临界资源必须用 Mutex。
4. **栈深度单位搞错**：`xTaskCreate` 栈深度单位是字不是字节，32 位平台 128 字 = 512 字节；用 `uxTaskGetStackHighWaterMark` 实测。
5. **运行期动态创建/删除任务**：堆碎片与耗时不确定；确定性场景初始化时一次性创建完所有任务与队列。
6. **任务通知误用为广播**：任务通知只能一对一，多任务等同一事件需用事件组/队列。
7. **临界区过长**：中断延迟主要由最长关中断时间决定，`taskENTER_CRITICAL`/`BASEPRI` 区间越短越好；高实时中断应高于 `configMAX_SYSCALL_INTERRUPT_PRIORITY`。
8. **vTaskDelay 当周期延时**：`vTaskDelay` 是相对延时，周期漂移；精确周期用 `vTaskDelayUntil`。
9. **栈溢出不检测**：不开 `configCHECK_FOR_STACK_OVERFLOW`，栈撞堆后随机 HardFault 极难查；必须开钩子并记录。
10. **RMA 界当充要条件**：Liu & Layland 界是充分非必要，未达界不代表不可调度，需 RTA 精确判定。

---

上一篇：《03-外设总线与DMA定时器.md》　｜　下一篇：《05-嵌入式Linux系统与驱动开发.md》　｜　模块索引：《../README.md》
