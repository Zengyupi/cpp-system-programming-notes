# 外设总线与DMA定时器

> 本节目标：掌握嵌入式常用外设与通信总线的工作原理与时序——GPIO、UART、I2C、SPI、CAN 的帧格式、配置要点与常见坑；理解 DMA 的三种模式与定时器/PWM/输入捕获的原理；并深入物联网通信——lwIP 协议栈架构、MQTT/CoAP 协议对比与嵌入式实现、WiFi/BLE/Zigbee/LoRa 的选型对比。学完后能根据场景选择合适的总线与无线方案，并写出高效的外设驱动代码。

---

## 本章速览

- [1. 常用外设与通信总线](#1-常用外设与通信总线)
  - [1.1 GPIO](#11-gpio)
  - [1.2 UART（异步串口）](#12-uart异步串口)
  - [1.3 I2C（两线、多从、地址寻址）](#13-i2c两线多从地址寻址)
  - [1.4 SPI（四线、全双工、高速）](#14-spi四线全双工高速)
  - [1.5 CAN / CAN-FD（汽车与工业总线）](#15-can--can-fd汽车与工业总线)
  - [1.6 总线选型对比](#16-总线选型对比)
- [2. DMA 与定时器](#2-dma-与定时器)
  - [2.1 DMA：不靠 CPU 搬运数据](#21-dma不靠-cpu-搬运数据)
  - [2.2 定时器、PWM、输入捕获](#22-定时器pwm输入捕获)
- [3. 物联网通信协议与无线选型](#3-物联网通信协议与无线选型)
  - [3.1 lwIP 协议栈架构与 API](#31-lwip-协议栈架构与-api)
  - [3.2 MQTT / CoAP 协议对比与嵌入式实现](#32-mqtt--coap-协议对比与嵌入式实现)
  - [3.3 WiFi / BLE / Zigbee / LoRa 选型对比](#33-wifi--ble--zigbee--lora-选型对比)
- [4. 快速参考卡片](#4-快速参考卡片)
- [5. 常见坑](#5-常见坑)

---

## 1. 常用外设与通信总线

### 1.1 GPIO

| 配置 | 用途 |
| --- | --- |
| 输入浮空/上拉/下拉 | 按键（一般上拉，按下接地）、外部电平 |
| 推挽输出 | LED、片选，能主动输出强 0/强 1 |
| 开漏输出 + 外部上拉 | I2C、多设备线与、电平转换 |
| 复用推挽/开漏 | USART/SPI 等外设接管引脚（AF） |
| 模拟模式 | ADC/DAC，断开数字施密特触发器省电 |

### 1.2 UART（异步串口）

**帧格式**：空闲高 → 起始位(低) → 5~9 数据位(LSB 先发) → 可选校验 → 停止位(高，1/1.5/2 位)。双方波特率必须一致，**误差建议 <2%**（否则采样点漂移到位边缘出错）。

```text
空闲  起始  D0  D1  D2  D3  D4  D5  D6  D7  校验 停止  空闲
  1 ┐  0                         ...数据位...        1/0   1
     └─拉低一位告诉接收方开始（靠起始位同步，无时钟线）
```

| 进阶点 | 说明 |
| --- | --- |
| 流控 RTS/CTS | 硬件握手，接收方来不及处理时拉 CTS 让对方停发，高速可靠通信使用 |
| DMA + IDLE 空闲中断 | **接收不定长数据的标准做法**：DMA 循环搬数据到内存，一帧结束触发 IDLE 中断，主循环按 DMA 剩余计数算出本帧长度，避免逐字节中断开销 |
| RS-485 | UART + 差分收发器（如 MAX485），半双工需一个 GPIO 控制收发方向，工业 Modbus RTU 标配 |
| 常见坑 | TX/RX 接反、共地缺失、波特率误差、未处理 ORE 溢出（读 SR 再读 DR 清除） |

### 1.3 I2C（两线、多从、地址寻址）

SDA/SCL 均**开漏 + 上拉电阻**（线与，只能拉低、靠电阻拉高，故必须接上拉，典型 4.7kΩ）。

```text
START：SCL 高电平时 SDA 由高→低（唯一允许在 SCL 高时改 SDA 的情况，其余时刻数据在 SCL 低时变化）
数据：每 8 位后接收方回 1 个 ACK（第 9 个时钟，SDA 拉低=ACK，高=NACK）
STOP ：SCL 高电平时 SDA 由低→高
读从设备寄存器：START | 设备地址+W | 寄存器号 | RESTART | 设备地址+R | 读 N 字节 | STOP
```

```c
// I2C 读某传感器一个 8 位寄存器（HAL 版，体现"写寄存器号→重启读"流程）
uint8_t reg = 0x0F, val;
HAL_I2C_Master_Transmit(&hi2c1, addr<<1, &reg, 1, 100);      // 7位地址左移，最低位=R/W
HAL_I2C_Master_Receive (&hi2c1, addr<<1 | 1, &val, 1, 100);
```

| 要点 | 说明 |
| --- | --- |
| 速率 | 标准 100k / 快速 400k / Fast+ 1M / 高速 3.4M |
| 地址 | 7 位（常见）或 10 位；同一总线地址不能冲突 |
| 时钟拉伸 | 从机可拉低 SCL 让主机等待（处理不过来时） |
| 多主与仲裁 | 线与机制天然支持仲裁，谁先输出 0 谁占用总线 |
| 上拉阻值 | 线越长/设备越多电容越大，上拉要越小（1.5k~10k 权衡速度与功耗） |

### 1.4 SPI（四线、全双工、高速）

MOSI（主出从入）、MISO（主入从出）、SCLK、CS/SS（片选，每从机一根，低有效）。**CPOL/CPHA 组合出 4 种模式，主从必须一致**：

| 模式 | CPOL 空闲电平 | CPHA 采样沿 | 典型 |
| --- | --- | --- | --- |
| 0 | 0（低） | 第 1 个边沿（上升沿采样） | 最常用，多数 Flash/传感器 |
| 1 | 0 | 第 2 个边沿（下降沿采样） | — |
| 2 | 1（高） | 第 1 个边沿（下降沿采样） | — |
| 3 | 1 | 第 2 个边沿（上升沿采样） | 部分 LCD/Flash |

```c
// SPI 读 NOR Flash 的 JEDEC ID（片选拉低→发命令→读回→片选拉高，全双工边发边收）
uint8_t tx[4] = {0x9F, 0, 0, 0}, rx[4];
CS_LOW();
HAL_SPI_TransmitReceive(&hspi1, tx, rx, 4, 100);
CS_HIGH();
// rx[1..3] = 厂商ID/容量ID
```

对比 I2C：SPI 无应答、无地址（靠独立 CS）、全双工、速率高一个数量级、但线多、总线设备多时 CS 线膨胀。

### 1.5 CAN / CAN-FD（汽车与工业总线）

差分信号 CAN_H/CAN_L，**显性=0、隐性=1**，抗干扰强、可达数公里（低速）。

```text
标准帧：SOF | 仲裁段(11位ID+RTR) | 控制段(DLC长度) | 数据段(0~8字节) | CRC | ACK槽 | EOF
```

| 机制 | 说明 |
| --- | --- |
| **非破坏性仲裁** | 多节点同时发送时逐位线与，ID 数值小（显性 0 多）者优先，失败者退避重发，数据不丢 |
| ACK 槽 | 发送方发隐性，任一正确接收的节点拉显性表示应答，无人应答即错误 |
| CRC + 错误帧 | 硬件 CRC 校验，出错节点发错误帧强制重传 |
| 错误状态 | 主动错误→被动错误→总线关闭（TEC/REC 计数），坏节点自动离线保护总线 |
| 过滤器 | 硬件按 ID 掩码/列表过滤，只把关心的报文送进接收 FIFO |
| CAN-FD | 数据场扩到 64 字节、速率可达 8Mbps，BRS 切换数据相位速率 |

### 1.6 总线选型对比

| 维度 | UART | I2C | SPI | CAN |
| --- | --- | --- | --- | --- |
| 线数 | 2 | 2 | 4 | 2 差分 |
| 双工 | 全双工 | 半双工 | 全双工 | 半双工 |
| 设备数 | 点对点 | 多（地址） | 多（片选） | 多（ID 仲裁） |
| 速率 | 中 | 低 | 高 | 中（FD 高） |
| 距离/抗扰 | 短/一般 | 板内/一般 | 板内/一般 | 远/强 |
| 典型 | 日志/模块 | 传感器/EEPROM | Flash/LCD | 车/工业 |

---

## 2. DMA 与定时器

### 2.1 DMA：不靠 CPU 搬运数据

DMA 控制器直接在外设与内存（或内存与内存）间搬数据，**搬完再中断通知 CPU**，期间 CPU 可做别的或睡眠。

| 模式 | 说明 | 用途 |
| --- | --- | --- |
| 正常模式 | 搬满设定长度即停 | 单次定长收发 |
| 循环模式 | 搬到末尾自动回到开头 | 连续 ADC 采样、UART 持续接收（配合 IDLE 处理不定长） |
| 双缓冲 | 两个缓冲区交替，处理一个时填另一个 | 高吞吐音频/ADC，无丢帧 |

```text
UART 不定长接收最佳实践：
  DMA 循环模式 + UART IDLE 中断
  → 数据持续被 DMA 写入 ring buffer，CPU 零介入
  → 一帧结束总线空闲触发 IDLE 中断
  → ISR 里读 NDTR（DMA 剩余计数）算出本次收了多少字节，通知任务解析
```

### 2.2 定时器、PWM、输入捕获

| 功能 | 原理 | 用途 |
| --- | --- | --- |
| 基本定时 | 计数器按预分频时钟累加，到 ARR 重装并产生更新中断 | 周期任务、RTOS SysTick |
| PWM | 比较寄存器 CCR 与计数值比较输出高低电平，**占空比=CCR/(ARR+1)**，频率由时钟/分频/ARR 决定 | 电机调速、LED 调光、舵机（50Hz，0.5~2.5ms 脉宽） |
| 输入捕获 | 信号边沿锁存计数值 | 测脉宽、测频率、解码红外 |
| 编码器模式 | 两相正交信号自动加减计数 | 读电机编码器位置/转速 |
| 输出比较/单脉冲 | 精确时刻翻转引脚 | 时序发生 |

---

## 3. 物联网通信协议与无线选型

嵌入式设备联网是 IoT 的核心。本节从底层无线技术到上层应用协议，建立完整的通信选型知识体系。

### 3.1 lwIP 协议栈架构与 API

lwIP（lightweight IP）是资源受限设备上最主流的 TCP/IP 协议栈，被 FreeRTOS、Zephyr、ESP-IDF 等广泛集成。最小 RAM 占用可低至几十 KB。

#### 分层架构

```text
┌──────────────────────────────────────────────┐
│  应用层：HTTP/MQTT/CoAP/TLS（mbedTLS/wolfSSL）│
├──────────────────────────────────────────────┤
│  Socket API（可选，需 netconn 或 socket 层）    │
├──────────────────────────────────────────────┤
│  netconn API（顺序 API，基于邮箱/信号量）        │
├──────────────────────────────────────────────┤
│  raw API（回调 API，零拷贝、最高效、最复杂）      │
├──────────────────────────────────────────────┤
│  TCP  ──  UDP  ──  ICMP  ──  IGMP            │
├──────────────────────────────────────────────┤
│  IP（IPv4/IPv6） + 分片重组                    │
├──────────────────────────────────────────────┤
│  ARP / ND（邻居发现） / DHCP / AutoIP / DNS    │
├──────────────────────────────────────────────┤
│  网络接口层：ethernetif → MAC/DMA 驱动          │
└──────────────────────────────────────────────┘
```

#### 三种 API 对比

| API | 编程模型 | 效率 | 适用场景 |
| --- | --- | --- | --- |
| **raw API** | 回调函数（`tcp_recv`/`tcp_sent` 注册回调） | 最高（零拷贝、无任务切换） | 资源极紧、高性能服务器 |
| **netconn API** | 顺序阻塞调用（`netconn_recv`/`netconn_write`） | 中（一次拷贝） | 多任务环境、业务逻辑复杂 |
| **socket API** | POSIX 标准（`socket`/`bind`/`recv`/`send`） | 中（兼容层开销） | 跨平台代码、从 Linux 移植 |

#### raw API 示例：TCP 回显服务器

```c
#include "lwip/tcp.h"

static err_t echo_recv(void *arg, struct tcp_pcb *pcb, struct pbuf *p, err_t err) {
    if (p == NULL) { tcp_close(pcb); return ERR_OK; }  // 对端关闭
    tcp_recved(pcb, p->tot_len);                         // 告知已接收（滑动窗口）
    tcp_write(pcb, p->payload, p->len, TCP_WRITE_FLAG_COPY);  // 回显
    pbuf_free(p);
    return ERR_OK;
}

static err_t echo_accept(void *arg, struct tcp_pcb *newpcb, err_t err) {
    tcp_recv(newpcb, echo_recv);   // 注册接收回调
    return ERR_OK;
}

void echo_server_init(void) {
    struct tcp_pcb *pcb = tcp_new();
    tcp_bind(pcb, IP_ADDR_ANY, 7);   // 绑定 7 号端口（echo）
    pcb = tcp_listen(pcb);
    tcp_accept(pcb, echo_accept);     // 注册连接回调
}
```

> **常见坑**：① 忘记调 `tcp_recved()` 导致接收窗口不滑动、对端停发；② `tcp_write` 后忘记 `tcp_output()` 立即发送（可设 `tcp_nagle_disable` 关 Nagle 算法）；③ pbuf 必须 `pbuf_free`，否则内存泄漏；④ 多任务访问 lwIP 必须加 `sys_arch_protect`/`sys_arch_unprotect` 或用 `tcpip_callback` 序列化。

### 3.2 MQTT / CoAP 协议对比与嵌入式实现

MQTT 和 CoAP 是 IoT 应用层最主流的两个协议，分别面向"可靠消息传递"和"受限设备 RESTful 交互"。

#### 协议对比

| 维度 | MQTT | CoAP |
| --- | --- | --- |
| 传输层 | TCP（+TLS） | UDP（+DTLS） |
| 模型 | 发布/订阅（Pub/Sub），Broker 中转 | 请求/响应（RESTful），可点对点 |
| 消息开销 | 固定头 2 字节 + 可变头，最小 2 字节 | 4 字节固定头，极简 |
| QoS | 0/1/2 三级（最多一次/至少一次/恰好一次） | 确认/非确认两种，支持重传 |
| 主题/资源 | 主题字符串（`sensor/temp`），支持通配符 | URI 路径（`/sensors/temp`） |
| 保活 | 心跳（PINGREQ/PINGRESP） | 无内置心跳，靠应用层 |
| 最后遗嘱 | LWT（异常断开时 Broker 发布遗嘱消息） | 无 |
| 典型场景 | 大量设备上报、指令下发、智能家居 | 传感器读数、资源受限设备、点对点 |
| 嵌入式实现 | paho-mqtt-embedded、esp-mqtt、lwIP mqtt | libcoap、microcoap、esp-coap |

#### MQTT 嵌入式实现（基于 paho-mqtt-embedded C）

```c
#include "MQTTClient.h"

static Network n;
static MQTTClient client;
static unsigned char sendbuf[512], readbuf[512];

void mqtt_task(void) {
    NetworkInit(&n);
    NetworkConnect(&n, "broker.emqx.io", 1883);  // TCP 连接 Broker

    MQTTClientInit(&client, &n, 1000, sendbuf, sizeof(sendbuf), readbuf, sizeof(readbuf));

    MQTTPacket_connectData data = MQTTPacket_connectData_initializer;
    data.clientID.cstring = "stm32_device_01";
    data.keepAliveInterval = 60;
    data.cleansession = 1;
    MQTTConnect(&client, &data);

    MQTTSubscribe(&client, "cmd/device01", QOS1, message_handler);  // 订阅指令主题

    while (1) {
        MQTTYield(&client, 1000);   // 维持心跳、处理收包
        // 发布传感器数据
        MQTTMessage msg = { QOS1, 0, 0, payload_len, payload_buf };
        MQTTPublish(&client, "sensor/device01/temp", &msg);
        vTaskDelay(pdMS_TO_TICKS(5000));
    }
}
```

#### CoAP 嵌入式实现（基于 libcoap 风格的极简 GET）

```c
// CoAP 消息格式：Ver(2bit) Type(2bit) TKL(4bit) | Code(8bit) | Message ID(16bit) | Token | Options | Payload
// Type: 0=CON(可确认) 1=NON(非确认) 2=ACK 3=RST
// Code: 0.01=GET 0.02=POST 0.03=PUT 0.04=DELETE；2.05=Content 响应

typedef struct __attribute__((packed)) {
    uint8_t  ver_type_tkl;    // version=1, type, token length
    uint8_t  code;            // 请求方法或响应码
    uint16_t msg_id;          // 消息 ID（大端）
} coap_header_t;

// 发送一个 CON GET 请求到 /sensors/temp
void coap_get_temp(const uint8_t* server_ip, uint16_t port) {
    uint8_t buf[64];
    coap_header_t* h = (coap_header_t*)buf;
    h->ver_type_tkl = (1 << 6) | (0 << 4) | 0;  // v1, CON, TKL=0
    h->code = 0x01;                                  // GET
    h->msg_id = htons(0x1234);

    // Option: Uri-Path = "sensors" (delta=11, length=7), "temp" (delta=0, length=4)
    uint8_t* p = buf + sizeof(coap_header_t);
    *p++ = 0xB7; memcpy(p, "sensors", 7); p += 7;
    *p++ = 0x04; memcpy(p, "temp", 4); p += 4;

    udp_send(server_ip, port, buf, p - buf);  // 通过 UDP 发送
}
```

### 3.3 WiFi / BLE / Zigbee / LoRa 选型对比

| 维度 | WiFi (802.11 b/g/n) | BLE (Bluetooth 5.x) | Zigbee (802.15.4) | LoRa (LPWAN) |
| --- | --- | --- | --- | --- |
| **频段** | 2.4G/5G | 2.4G | 2.4G（全球）/ sub-GHz | sub-GHz（433/868/915MHz） |
| **典型功耗** | 高（100~300mA TX，连接保持 ~20mA） | 极低（TX ~10mA，广播 ~10μA，纽扣电池可用年） | 低（TX ~30mA，休眠 ~1μA） | 极低（TX ~120mA 但占空比极低，平均 μA 级） |
| **传输距离** | 10~100m（室内） | 10~50m（BLE 5 长距可达 200m+） | 10~100m（Mesh 可扩展） | 2~15km（城市）/ 50km+（视距） |
| **数据速率** | 高（1~150Mbps） | 中（125K~2Mbps） | 低（250Kbps） | 极低（0.3~50Kbps） |
| **网络拓扑** | 星型（AP 中心） | 星型/点对点/Broadcast | Mesh（自组网、多跳） | 星型（网关集中） |
| **成本** | 中（模组 $1.5~5） | 低（模组 $0.5~2） | 低（模组 $1~3） | 中（模组 $3~8，网关贵） |
| **典型场景** | 摄像头、网关、高速数据传输、需要互联网直连 | 可穿戴、 beacon、智能家居直连、手机配对 | 智能家居（灯/开关/传感器）、工业监控 Mesh | 智能水表/电表、农业监测、城市级物联网、长距离低速率 |
| **代表芯片/模组** | ESP32/ESP32-C3、RTL8710、BL602 | nRF52832/52840、ESP32-C3、CC2640 | CC2530/CC2652、EFR32、ESP32-H2 | SX1276/SX1262、LLCC68、ASR6501 |

#### 选型决策树

```text
需要直接连互联网/传大文件？
├─ 是 → WiFi（或 WiFi+BLE 双模如 ESP32）
└─ 否 → 设备数量与密度？
         ├─ 手机直连/可穿戴/低延迟 → BLE
         ├─ 室内大量设备自组网 → Zigbee / Thread（基于 802.15.4）
         └─ 长距离/电池供电/低速率 → LoRa / NB-IoT（蜂窝）
```

> **关键注意**：① BLE 和 Zigbee 都在 2.4G，与 WiFi 共存时需注意信道规划（Zigbee 常用 11/15/20/25 信道避开 WiFi 1/6/11）；② LoRa 是物理层技术，上层协议常用 LoRaWAN（Class A/B/C 设备分类）；③ 实际项目常做"双模"——BLE 配网 + WiFi 数据传输，或 Zigbee 终端 + WiFi 网关。

---

## 4. 快速参考卡片

### 总线一句话选型

| 场景 | 选 | 理由 |
| --- | --- | --- |
| 调试日志 / 模块 AT 指令 | UART | 最简单、成熟 |
| 板内传感器/EEPROM（低速多设备） | I2C | 两线、地址寻址 |
| NOR Flash / LCD（高速全双工） | SPI | 四线、快一个数量级 |
| 工业/汽车现场、抗干扰长距离 | CAN / RS-485 | 差分、仲裁、错误重传 |
| 不定长串口接收 | DMA 循环 + IDLE 中断 | 零逐字节中断 |

### DMA/定时器速查

| 需求 | 做法 |
| --- | --- |
| UART 连续收不定长帧 | DMA 循环模式 + IDLE 中断，读 NDTR 算帧长 |
| ADC 连续采样不丢 | DMA 双缓冲，处理一块时填另一块 |
| PWM 调光/电机 | CCR 占空比 = CCR/(ARR+1)，频率由时钟/分频/ARR |
| 测频率/脉宽 | 输入捕获锁存计数器 |
| 正交编码器读位置 | 编码器模式自动加减 |

### 无线选型一句话

| 需求 | 选 |
| --- | --- |
| 直连互联网/大流量 | WiFi |
| 手机直连/可穿戴/纽扣电池 | BLE |
| 室内大量设备自组网 | Zigbee / Thread |
| 数公里长距离/极低速率/电池 | LoRa / NB-IoT |

---

## 5. 常见坑

1. **I2C 忘接上拉电阻**：SDA/SCL 开漏只能拉低，无上拉则总线永远为低；阻值按总线电容选（典型 4.7kΩ，长线/多设备需更小）。
2. **I2C 主从时钟模式不匹配**：CPOL/CPHA 与从设备不一致导致读到全 FF 或 00；启动时序（START/STOP 必须在 SCL 低时改 SDA）违反会总线锁死。
3. **SPI 片选/模式错**：多从机共用 SCLK/MOSI 但各自 CS，漏拉某根 CS 会误通信；主从 CPOL/CPHA 必须同模式。
4. **UART 溢出 ORE 未清**：接收溢出后必须"读 SR 再读 DR"才清除，否则一直丢数据；波特率误差超过 ~2% 采样点漂移出错。
5. **DMA 与 cache 一致性**：带 cache 的 MCU（Cortex-A）上 DMA 直接读写内存，需 clean/invalidate cache，否则 CPU 看到旧数据；Cortex-M 无 cache 无此问题。
6. **DMA 缓冲与变量不 cache 对齐**：DMA 访问起始地址未对齐或跨非连续区域，部分外设要求 4/8 字节对齐。
7. **CAN 无人应答/总线关闭**：只接一个节点自发自收时 ACK 槽无人拉低会报错；TEC/REC 计数累积到总线关闭后需软件恢复。
8. **lwIP 多任务未加锁**：多个任务同时操作同一 pcb 必须 `sys_arch_protect` 或用 `tcpip_callback` 投递到唯一 tcpip 线程，否则堆损坏。
9. **MQTT 心跳/遗嘱漏配**：长时间无 PINGREQ 被 Broker 踢下线；异常断网时靠 LWT 让其他端感知设备离线。
10. **2.4G 共存干扰**：WiFi/BLE/Zigbee 同频段，信道规划不当（Zigbee 不避开 WiFi 1/6/11）会大量丢包。

---

上一篇：《02-MCU启动流程与嵌入式C关键技术.md》　｜　下一篇：《04-中断系统与RTOS原理.md》　｜　模块索引：《../README.md》
