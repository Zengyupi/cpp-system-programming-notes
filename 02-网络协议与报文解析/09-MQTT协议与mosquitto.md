# MQTT协议与mosquitto（报文级解析视角）

> 本节目标：从字节层面彻底掌握 MQTT 5.0/3.1.1 报文结构，能逐字段拆解 CONNECT/PUBLISH/SUBSCRIBE 等核心报文，理解三种 QoS 握手流程与遗嘱/保留消息机制，能用 mosquitto 搭建带 TLS/ACL 的 Broker 并进行报文级调试，最终能在工业物联网网关中与 Modbus/IEC104 规约协同工作。

## 本章速览

- [1. MQTT 协议定位与发布订阅模型](#1-mqtt-协议定位与发布订阅模型)
- [2. MQTT 报文结构总览（固定报头/可变报头/Payload）](#2-mqtt-报文结构总览固定报头可变报头payload)
- [3. 核心报文逐字段解析](#3-核心报文逐字段解析)
  - [3.1 CONNECT / CONNACK](#31-connect--connack)
  - [3.2 PUBLISH / PUBACK / PUBREC / PUBREL / PUBCOMP](#32-publish--puback--pubrec--pubrel--pubcomp)
  - [3.3 SUBSCRIBE / SUBACK / UNSUBSCRIBE / UNSUBACK](#33-subscribe--suback--unsubscribe--unsuback)
  - [3.4 PINGREQ / PINGRESP / DISCONNECT](#34-pingreq--pingresp--disconnect)
- [4. QoS 等级与握手流程](#4-qos-等级与握手流程)
- [5. 遗嘱机制（LWT）、保留消息、会话清理](#5-遗嘱机制lwt保留消息会话清理)
- [6. mosquitto 部署与配置](#6-mosquitto-部署与配置)
- [7. 安全认证：ACL / TLS / OAuth-JWT](#7-安全认证acl--tls--oauth-jwt)
- [8. 与 Modbus / IEC104 工业规约对比](#8-与-modbus--iec104-工业规约对比)
- [9. 快速参考卡片](#9-快速参考卡片)
- [10. 常见问题与坑](#10-常见问题与坑)

---

## 1. MQTT 协议定位与发布订阅模型

MQTT（Message Queuing Telemetry Transport）是一种基于 TCP 的轻量级发布/订阅协议，设计目标是**低带宽、高延迟、不稳定网络**下的物联网通信。

**核心三角色：**

| 角色 | 职责 |
| --- | --- |
| Publisher（发布者） | 向 Topic 发布消息，不关心订阅者是谁 |
| Broker（代理/服务器） | 接收发布、过滤、路由到订阅者；mosquitto 即 Broker |
| Subscriber（订阅者） | 向 Broker 订阅感兴趣的 Topic，接收推送 |

**Topic 分级与通配符：**

```text
sensors/plant1/temperature     # 具体主题
sensors/+/temperature          # + 匹配单层（sensors/plant1/temperature 命中，sensors/plant1/area/temperature 不命中）
sensors/#                      # # 匹配多层（必须在末尾），命中 sensors/ 下所有
$SYS/broker/clients/total     # $ 开头为系统主题，普通客户端不能发布
```

**为什么选 MQTT 而非 HTTP：**

- 报文头最小仅 2 字节（PINGREQ），HTTP 头动辄数百字节
- 长连接 + 心跳，避免 TCP 三次握手开销
- 发布订阅天然解耦，适合设备到云的多对多场景
- QoS 保证消息可达，HTTP 需应用层自行实现

---

## 2. MQTT 报文结构总览（固定报头/可变报头/Payload）

所有 MQTT 报文由三部分组成：**固定报头（Fixed Header）+ 可变报头（Variable Header）+ Payload**，其中固定报头所有报文都有，后两者视报文类型而定。

### 2.1 固定报头

```text
字节位:  7 6 5 4   3 2 1 0
       +---------+---------+
字节1  | 类型     | Flags   |
       +---------+---------+
字节2+ | 剩余长度（可变字节编码，1-4字节） |
       +-------------------+
```

**报文类型（高 4 位）：**

| 值 | 类型 | 方向 | 说明 |
| --- | --- | --- | --- |
| 1 | CONNECT | C到S | 客户端请求连接 |
| 2 | CONNACK | S到C | 连接确认 |
| 3 | PUBLISH | 双向 | 发布消息 |
| 4 | PUBACK | 双向 | QoS1 确认 |
| 5 | PUBREC | 双向 | QoS2 收到（第一步） |
| 6 | PUBREL | 双向 | QoS2 释放（第二步） |
| 7 | PUBCOMP | 双向 | QoS2 完成（第三步） |
| 8 | SUBSCRIBE | C到S | 订阅请求 |
| 9 | SUBACK | S到C | 订阅确认 |
| 10 | UNSUBSCRIBE | C到S | 取消订阅 |
| 11 | UNSUBACK | S到C | 取消确认 |
| 12 | PINGREQ | C到S | 心跳请求 |
| 13 | PINGRESP | S到C | 心跳响应 |
| 14 | DISCONNECT | 双向 | 断开连接 |
| 15 | AUTH | 双向 | 认证交换（MQTT 5.0） |

**Flags（低 4 位）：** 仅 PUBLISH 使用，其余报文固定为 0。

```text
bit3: DUP（重传标记，1=重传）
bit2-1: QoS 等级（0=至多一次, 1=至少一次, 2=恰好一次）
bit0: RETAIN（保留消息标记，1=Broker 保留该消息）
```

**剩余长度编码（可变字节算法）：**

剩余长度 = 可变报头长度 + Payload 长度，**不含固定报头自身**。每个字节用低 7 位存数据，最高位为"后续还有字节"标记。

```text
0-127:        单字节（0x00-0x7F）
128-16383:    双字节（首字节 0x80-0xFF，次字节 0x00-0x7F）
16384-2097151: 三字节
2097152-268435455: 四字节（最大 256MB）
```

示例：剩余长度 321，321 = 0x141，首字节低7位=0x41(65)+0x80=0xC1，次字节=0x02，编码为 `C1 02`。

### 2.2 可变报头与 Payload

可变报头包含报文标识符（Packet Identifier）等字段，Payload 承载实际数据。不同报文结构不同，下文逐字段拆解。

---

## 3. 核心报文逐字段解析

### 3.1 CONNECT / CONNACK

**CONNECT 报文（C到S）：**

```text
固定报头: 0x10 + 剩余长度
可变报头:
  协议名:   0x00 0x04 "MQTT"（2字节长度+4字节ASCII，MQTT 3.1.1）
            0x00 0x06 "MQIsdp"（3.1 旧版）
  协议级别: 0x04（3.1.1）/ 0x05（5.0）
  连接标志: 1字节
    bit7: Username Flag
    bit6: Password Flag
    bit5: Will Retain
    bit4-3: Will QoS
    bit2: Will Flag
    bit1: Clean Session（0=持久会话, 1=清理会话）
    bit0: 保留（0）
  保持连接: 2字节（心跳间隔秒数，最大 65535）
Payload:
  Client ID（2字节长度+内容，必须唯一；空ID要求Clean Session=1）
  [Will Topic（2字节长度+内容）]  （Will Flag=1 时）
  [Will Message（2字节长度+内容）]（Will Flag=1 时）
  [Username（2字节长度+内容）]     （Username Flag=1 时）
  [Password（2字节长度+内容）]     （Password Flag=1 时）
```

**CONNECT 实报文字节示例（无用户名密码，Clean Session，KeepAlive=60）：**

```text
10 1F                          # 固定报头：CONNECT，剩余长度31
00 04 4D 51 54 54             # 协议名 "MQTT"
04                             # 协议级别 3.1.1
02                             # 连接标志：Clean Session=1
00 3C                          # KeepAlive=60
00 0E 6D 79 2D 63 6C 69 65 6E 74 2D 30 30 31  # Client ID "my-client-001"
```

**CONNACK 报文（S到C）：**

```text
固定报头: 0x20 0x02（剩余长度恒为2）
可变报头:
  字节1: 连接确认标志
    bit0: Session Present（0=无持久会话, 1=恢复了持久会话）
  字节2: 连接返回码
    0x00: 连接已接受
    0x01: 不可接受的协议版本
    0x02: 客户端标识符被拒绝
    0x03: 服务器不可用
    0x04: 用户名或密码错误
    0x05: 未授权
```

### 3.2 PUBLISH / PUBACK / PUBREC / PUBREL / PUBCOMP

**PUBLISH 报文（双向）：**

```text
固定报头: 0x3?（类型3 + DUP/QoS/RETAIN flags）+ 剩余长度
可变报头:
  Topic Name（2字节长度+内容，不能含通配符）
  [Packet Identifier（2字节）]  （QoS>0 时必须有，QoS0 无此字段）
Payload:
  应用消息体（二进制，长度=剩余长度-可变报头长度）
```

**PUBLISH 实报文（QoS1，Topic=sensor/temp，Payload=23.5，PacketID=0x0001）：**

```text
32 0F                          # PUBLISH, QoS1, 剩余长度15
00 0B 73 65 6E 73 6F 72 2F 74 65 6D 70  # Topic "sensor/temp"
00 01                          # Packet Identifier=1
32 33 2E 35                    # Payload "23.5"
```

**PUBACK（QoS1 确认）：** `0x40 0x02 + PacketID(2字节)`
**PUBREC（QoS2 第一步）：** `0x50 0x02 + PacketID(2字节)`
**PUBREL（QoS2 第二步）：** `0x62 0x02 + PacketID(2字节)`，注意固定报头 flags=0x02
**PUBCOMP（QoS2 第三步）：** `0x70 0x02 + PacketID(2字节)`

### 3.3 SUBSCRIBE / SUBACK / UNSUBSCRIBE / UNSUBACK

**SUBSCRIBE 报文（C到S）：**

```text
固定报头: 0x82 + 剩余长度（flags 固定 0x02）
可变报头: Packet Identifier（2字节）
Payload:  主题过滤器列表（可多个）
  每个: Topic Filter（2字节长度+内容）+ Requested QoS（1字节，0/1/2）
```

**SUBACK 报文（S到C）：**

```text
固定报头: 0x90 + 剩余长度
可变报头: Packet Identifier（2字节，与 SUBSCRIBE 对应）
Payload:  返回码列表（每个主题一个）
  0x00: 成功-QoS0
  0x01: 成功-QoS1
  0x02: 成功-QoS2
  0x80: 失败
```

**UNSUBSCRIBE：** `0xA2 + PacketID + 主题列表`（无 QoS 字节）
**UNSUBACK：** `0xB0 + PacketID`（无 Payload）

### 3.4 PINGREQ / PINGRESP / DISCONNECT

| 报文 | 字节 | 说明 |
| --- | --- | --- |
| PINGREQ | `C0 00` | 客户端心跳，无可变报头无 Payload |
| PINGRESP | `D0 00` | 服务器心跳响应 |
| DISCONNECT | `E0 00` | 客户端优雅断开，不触发遗嘱 |

---

## 4. QoS 等级与握手流程

### QoS 0：至多一次（At Most Once）

```text
Publisher -> PUBLISH(QoS0) -> Broker/Subscriber
（发完即忘，无确认，可能丢失）
```

适用：传感器高频上报，丢一两个数据点无所谓。

### QoS 1：至少一次（At Least Once）

```text
Publisher                     Broker/Subscriber
   |--- PUBLISH(QoS1, PID) --->|
   |                             |  处理消息
   |<--- PUBACK(PID) -----------|
   |  收到PUBACK后释放PID        |
```

- 发布者存储消息直到收到 PUBACK，超时重传（DUP=1）
- **可能重复**：PUBACK 丢失时发布者重传，订阅者收到两次
- 适用：指令下发，重复执行无害或应用层去重

### QoS 2：恰好一次（Exactly Once）

```text
Publisher                     Broker/Subscriber
   |--- PUBLISH(QoS2, PID) --->|
   |                             |  存储消息，去重
   |<--- PUBREC(PID) -----------|
   |--- PUBREL(PID) ----------->|
   |                             |  释放存储，转发给订阅者
   |<--- PUBCOMP(PID) ----------|
   |  完成，释放PID              |
```

- 四次握手，通过 PUBREC/PUBREL 两阶段确保不重复不丢失
- Broker 需存储 PUBLISH 直到收到 PUBREL，存储 PUBREL 直到发送 PUBCOMP
- 适用：支付、计费等不能重复的关键指令

**QoS 降级规则：** 订阅者实际收到的 QoS = min(发布 QoS, 订阅 QoS)。发布者 QoS2 + 订阅者 QoS1，订阅者按 QoS1 收。

---

## 5. 遗嘱机制（LWT）、保留消息、会话清理

### 遗嘱消息（Last Will and Testament, LWT）

客户端在 CONNECT 时预先注册遗嘱：Broker 检测到客户端**异常断开**（未发 DISCONNECT、心跳超时、网络故障）时，自动向指定 Topic 发布遗嘱消息。

```text
连接标志中 Will Flag=1 时注册：
  Will Topic: 遗嘱发布的主题
  Will Message: 遗嘱内容
  Will QoS: 遗嘱消息的 QoS 等级
  Will Retain: 遗嘱是否保留
```

典型场景：设备离线时自动发布 `status/offline`，平台感知设备状态。

**注意：** 客户端正常发送 DISCONNECT 时，Broker **删除**遗嘱不发布。

### 保留消息（Retained Message）

PUBLISH 时 RETAIN=1，Broker 存储该消息（每个 Topic 仅保留最新一条）。**新订阅者**订阅该 Topic 时，立即收到保留消息，无需等待下一次发布。

```bash
# 发布保留消息（温度阈值）
mosquitto_pub -t config/threshold -m "30" -r
# 新订阅者立即收到 "30"
mosquitto_sub -t config/threshold -C 1
```

清除保留消息：向同一 Topic 发布 RETAIN=1 且 Payload 为空的消息。

### 会话清理（Clean Session）

- **Clean Session=1（临时会话）：** 断开后 Broker 清除所有会话信息（订阅、未确认消息、遗嘱）
- **Clean Session=0（持久会话）：** 断开后 Broker 保留会话，重连后继续投递离线期间的 QoS1/QoS2 消息

MQTT 5.0 中改为 **Session Expiry Interval**，可设置会话过期时间（0=断开即清除，0xFFFFFFFF=永不过期）。

---

## 6. mosquitto 部署与配置

### 6.1 安装（WSL Ubuntu 24.04 实跑）

```bash
# WSL Ubuntu 24.04 实跑
sudo apt update && sudo apt install -y mosquitto mosquitto-clients
mosquitto -h | head -5
# 示例输出: mosquitto version 2.0.18
```

### 6.2 基础配置

```bash
# /etc/mosquitto/conf.d/default.conf
listener 1883
allow_anonymous true          # 测试用，生产必须关闭
persistence true
persistence_location /var/lib/mosquitto/
log_dest file /var/log/mosquitto/mosquitto.log
log_type all
```

```bash
# WSL Ubuntu 24.04 实跑
sudo systemctl restart mosquitto
sudo systemctl status mosquitto
# 示例输出: active (running)
```

### 6.3 mosquitto_pub / mosquitto_sub 常用命令

```bash
# 订阅（前台持续接收）
mosquitto_sub -h localhost -t "sensor/#" -v -q 1

# 发布一次
mosquitto_pub -h localhost -t "sensor/temp" -m "23.5" -q 1

# 发布保留消息
mosquitto_pub -t "config/threshold" -m "30" -r

# 带遗嘱连接
mosquitto_sub -t "data/#" --will-topic "status/client1" --will-payload "offline" --will-qos 1 -v

# 调试报文级别（-d 打印所有报文）
mosquitto_sub -h localhost -t "test/#" -d
# 示例输出:
# Client mosq|xxx sending CONNECT
# Client mosq|xxx received CONNACK (0)
# Client mosq|xxx sending SUBSCRIBE (Mid: 1, Topic: test/#, QoS: 0)
# Client mosq|xxx received SUBACK Subscribed (Mid: 1, QoS 0)
```

### 6.4 桥接（Bridge）

mosquitto 支持 Broker 间桥接，实现跨集群消息转发。

```bash
# /etc/mosquitto/conf.d/bridge.conf
connection cloud-bridge
address broker.example.com:1883
topic sensor/# out 1 local/ remote/
cleansession false
keepalive_interval 60
```

---

## 7. 安全认证：ACL / TLS / OAuth-JWT

### 7.1 用户名密码 + ACL

```bash
# 创建密码文件（WSL Ubuntu 24.04 实跑）
sudo mosquitto_passwd -c /etc/mosquitto/passwd device01
# 示例输出: Password: （输入两次）
# Reenter password:
```

```text
# /etc/mosquitto/conf.d/default.conf 追加
listener 1883
allow_anonymous false
password_file /etc/mosquitto/passwd
acl_file /etc/mosquitto/acl
```

```text
# /etc/mosquitto/acl
user device01
topic readwrite sensor/device01/#
topic read  config/#

user admin
topic readwrite #
```

### 7.2 TLS 加密

```bash
# 生成自签名证书（测试用，生产用 Let's Encrypt）
openssl req -new -x509 -days 365 -nodes -keyout server.key -out server.crt -subj "/CN=mqtt.local"
```

```text
# mosquitto 配置
listener 8883
certfile /etc/mosquitto/certs/server.crt
keyfile /etc/mosquitto/certs/server.key
require_certificate false  # 单向认证；双向认证设 true 并配 cafile
```

```bash
# 客户端连接
mosquitto_pub -h mqtt.local -p 8883 --cafile server.crt -t test -m "secure"
```

### 7.3 OAuth/JWT 认证

mosquitto 2.0+ 提供动态安全插件，可对接外部认证。生产环境通常用 **mosquitto-auth-plugin** 或自定义认证插件对接 OAuth2/JWT 签发服务：客户端 CONNECT 时 Username 传 token，Broker 验证 JWT 签名与过期时间。

```bash
# 启用动态安全插件
plugin /usr/lib/mosquitto_dynamic_security.so
plugin_opt_config_file /var/lib/mosquitto/dynamic-security.json

# 通过 mosquitto_ctrl 管理角色
mosquitto_ctrl -u admin dynsec createRole readonly
mosquitto_ctrl -u admin dynsec addRoleACL readonly publishClientSend "sensor/#" deny
```

---

## 8. 与 Modbus / IEC104 工业规约对比

详见《07-Modbus与IEC104工业报文解析.md》，此处聚焦差异：

| 维度 | MQTT | Modbus TCP | IEC 60870-5-104 |
| --- | --- | --- | --- |
| 通信模型 | 发布/订阅（Broker 中转） | 主从轮询（Client/Server） | 主从+突发上报 |
| 连接 | 长连接+心跳 | 短连接/长连接均可 | 长连接+测试帧 |
| 报文开销 | 最小 2 字节 | MBAP 7 字节 + PDU | 启动符+长度 6 字节起 |
| 数据标识 | Topic 字符串 | 寄存器地址 | 公共地址+信息体地址 |
| QoS | 0/1/2 三级 | 无（TCP 保证） | 无（I帧确认/S帧监视） |
| 典型场景 | 物联网设备到云，多对多 | PLC/传感器读写，一对一 | 电力调度，主站对子站 |
| 安全 | TLS+用户名+ACL | 无原生安全 | 无原生安全 |

**工业网关常见架构：** 现场设备用 Modbus/IEC104 采集，网关协议转换，MQTT 上报云端。MQTT 的 QoS1/遗嘱/保留消息完美适配设备状态上报与离线感知。

---

## 9. 快速参考卡片

### 报文类型速查表

```text
类型  报文      固定报头首字节  可变报头关键字段          Payload
1     CONNECT   0x10           协议名/级别/标志/KeepAlive  ClientID+遗嘱+用户+密码
2     CONNACK   0x20           SessionPresent+返回码      无
3     PUBLISH   0x3?           Topic+PacketID(QoS>0)     应用数据
4     PUBACK    0x40           PacketID                  无
5     PUBREC    0x50           PacketID                  无
6     PUBREL    0x62           PacketID                  无
7     PUBCOMP   0x70           PacketID                  无
8     SUBSCRIBE 0x82           PacketID                  Topic+QoS列表
9     SUBACK    0x90           PacketID                  返回码列表
12    PINGREQ   0xC0           无                        无
13    PINGRESP  0xD0           无                        无
14    DISCONNECT 0xE0          无                        无
```

### QoS 握手流程

```text
QoS0: PUBLISH -> （无确认）
QoS1: PUBLISH -> PUBACK
QoS2: PUBLISH -> PUBREC -> PUBREL -> PUBCOMP
```

### mosquitto 命令速查

```text
启动:   mosquitto -c /etc/mosquitto/mosquitto.conf -v
订阅:   mosquitto_sub -h HOST -t TOPIC [-q 0|1|2] [-v] [-C N] [-d]
发布:   mosquitto_pub -h HOST -t TOPIC -m MSG [-q 0|1|2] [-r] [-d]
密码:   mosquitto_passwd -c FILE USER  /  mosquitto_passwd FILE USER（追加）
桥接:   connection NAME + address HOST:PORT + topic PATTERN out|in|both QoS
```

---

## 10. 常见问题与坑

| 问题 | 原因与解决 |
| --- | --- |
| CONNACK 返回码 0x02（ClientID 被拒） | ClientID 重复或为空但 Clean Session=0；确保 ID 唯一或设 Clean Session=1 |
| 消息丢失，QoS1 也丢 | 发布者未等待 PUBACK 就退出；或 Broker 重启无持久化；开启 persistence + 发布者存储未确认消息 |
| QoS2 消息重复 | 订阅者未去重；QoS2 保证 Broker 到订阅者不重复，但发布者到 Broker 重传时 DUP=1，应用层应基于 PacketID 去重 |
| 遗嘱不触发 | 客户端正常发了 DISCONNECT；遗嘱仅在异常断开（心跳超时/网络中断）时触发 |
| 保留消息收不到 | 新订阅者才收到保留消息；已订阅者只收到新发布的；清除需发空 Payload + RETAIN=1 |
| 订阅了 # 但收不到 $SYS 消息 | $ 开头主题不被 # 匹配，需显式订阅 `$SYS/#` |
| mosquitto 2.0 默认只能本地连接 | 配置文件必须显式 `listener 1883`，否则只监听 127.0.0.1 |
| 大消息传输慢 | 剩余长度最大 256MB，但大消息阻塞其他消息；建议分片或用文件传输协议 |
| Topic 设计混乱 | 遵循层级命名 `区域/设备/测点`，避免用 # 通配生产关键 Topic；Topic 不以 / 开头 |
| 心跳超时频繁断开 | KeepAlive 设太小（<10s）或网络抖动；建议 30-60s，Broker 实际超时=1.5乘KeepAlive |

---

上一篇：《08-抓包分析与手写报文解析.md》　｜　下一篇：《10-RTMP推流协议.md》　｜　模块索引：《README.md》
