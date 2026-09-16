# RTMP推流协议（报文级解析视角）

> 本节目标：从字节层面掌握 RTMP 协议的握手、Chunk 分块与消息类型，能逐字段拆解 Basic Header/Message Header，理解推流（publish）与拉流（play）的完整状态机，能用 FFmpeg 推流和 nginx-rtmp-module 搭建直播服务器，并对比 HLS/DASH/WebRTC 选型。

## 本章速览

- [1. RTMP 协议基础](#1-rtmp-协议基础)
- [2. RTMP 握手（C0/C1/C2 与 S0/S1/S2）](#2-rtmp-握手c0c1c2-与-s0s1s2)
- [3. Chunk 分块机制](#3-chunk-分块机制)
  - [3.1 Basic Header](#31-basic-header)
  - [3.2 Message Header](#32-message-header)
  - [3.3 Extended Timestamp](#33-extended-timestamp)
- [4. 消息类型与协议控制消息](#4-消息类型与协议控制消息)
- [5. 推流流程（publish）状态机](#5-推流流程publish状态机)
- [6. 拉流流程（play）状态机](#6-拉流流程play状态机)
- [7. 与 HLS / DASH / WebRTC 对比](#7-与-hls--dash--webrtc-对比)
- [8. FFmpeg 推流与 nginx-rtmp-module 搭建](#8-ffmpeg-推流与-nginx-rtmp-module-搭建)
- [9. 快速参考卡片](#9-快速参考卡片)
- [10. 常见问题与坑](#10-常见问题与坑)

---

## 1. RTMP 协议基础

RTMP（Real-Time Messaging Protocol）是 Adobe 开发的基于 TCP 的应用层协议，默认端口 **1935**，最初用于 Flash 播放器与服务器之间的音视频流传输，至今仍是直播推流的事实标准。TCP/HTTP 基础详见《06-HTTP与TLS应用层报文.md》。

**核心概念：**

| 概念 | 说明 |
| --- | --- |
| Connection | RTMP 连接，对应一个 TCP 连接，握手后建立 |
| Stream | 流通道，一个 Connection 可多路复用多个 Stream（createStream 创建） |
| Chunk | 分块单元，RTMP 消息在传输层被切分为 Chunk，默认 Chunk Size=128 字节 |
| Message | RTMP 消息，包含音视频数据或命令，被切分为 Chunk 传输 |
| Chunk Stream ID (CSID) | Chunk 流标识，不同 CSID 的 Chunk 可交错传输，接收端按 CSID 重组 |

**RTMP 变种：**

- **RTMP**：明文 TCP，端口 1935
- **RTMPS**：RTMP over TLS/SSL，端口 443
- **RTMPT**：RTMP over HTTP，端口 80（隧道封装，穿透防火墙）
- **RTMPE**：RTMP 加密（Adobe 专有加密，已被破解）

---

## 2. RTMP 握手（C0/C1/C2 与 S0/S1/S2）

RTMP 连接建立后，首先进行**三次握手**，客户端发 C0+C1，服务器回 S0+S1+S2，客户端发 C2。与 TCP 三次握手不同，RTMP 握手在 TCP 连接之上进行。

```text
客户端                          服务器
  |--- C0 (1字节) ------------->|
  |--- C1 (1536字节) ---------->|
  |                              |
  |<-- S0 (1字节) --------------|
  |<-- S1 (1536字节) -----------|
  |<-- S2 (1536字节) -----------|
  |                              |
  |--- C2 (1536字节) ---------->|
  |                              |  握手完成，开始交换 Chunk
```

### C0/S0：版本号

```text
1 字节：版本号，当前固定为 0x03（RTMP 3）
```

### C1/S1：时间戳 + 零 + 随机数

```text
0-3 字节:   time（4字节大端，客户端时间戳，毫秒）
4-7 字节:   zero（4字节，必须为0）
8-1535 字节: random（1528字节随机数，用于密钥交换/防重放）
```

### C2/S2：时间戳回显 + 时间戳2 + 随机数回显

```text
0-3 字节:   time1（4字节，对端 C1/S1 的 time 回显）
4-7 字节:   time2（4字节，本机收到对端 C1/S1 的时间戳）
8-1535 字节: random（对端 C1/S1 的 random 原样回显）
```

**简化握手（Simple Handshake）：** 实际实现中 C1/S1 的 zero 字段常被用于复杂握手（Complex Handshake）的密钥协商，但大多数开源实现（nginx-rtmp、FFmpeg）使用简化握手，random 字段可任意填充。

---

## 3. Chunk 分块机制

握手完成后，所有 RTMP 消息以 **Chunk** 形式传输。Chunk 是 RTMP 的传输层单元，设计目的是将大消息（如视频关键帧）切分，与小消息（如音频帧、命令）交错传输，避免大消息阻塞。

### 3.1 Basic Header

```text
Basic Header 长度：1-3 字节，包含 Chunk Type (fmt) 和 Chunk Stream ID (CSID)

1字节格式（CSID 2-63）:
  bit7-6: fmt（Chunk Type，0-3）
  bit5-0: csid（2-63，0和1为扩展标记）

2字节格式（CSID 64-319）:
  字节1: fmt(bit7-6) + 0x00(bit5-0，标记扩展)
  字节2: csid - 64（0-255，实际 CSID=64+该值）

3字节格式（CSID 64-65599）:
  字节1: fmt(bit7-6) + 0x01(bit5-0，标记扩展)
  字节2-3: csid - 64（小端，0-65535，实际 CSID=64+该值）
```

**常用 CSID：**

| CSID | 用途 |
| --- | --- |
| 2 | 协议控制消息（设置块大小、ack、用户控制等） |
| 3 | 命令消息（connect、createStream、publish 等 AMF 编码） |
| 4+ | 音视频数据（每个 Stream 通常用独立 CSID） |

### 3.2 Message Header

Message Header 有 4 种格式，由 Basic Header 的 fmt 字段决定：

**fmt=0（完整头，11字节）：** 新消息或时间戳回绕时使用

```text
0-2 字节:   timestamp（3字节大端，绝对时间戳，毫秒；>=0xFFFFFF 时设为0xFFFFFF，用扩展时间戳）
3-5 字节:   message length（3字节大端，消息体长度，不含头）
6 字节:     message type id（1字节，消息类型，见第4节）
7-10 字节:  message stream id（4字节小端，流ID，createStream 返回的 ID）
```

**fmt=1（7 字节头）：** 同 CSID 同 Stream 的后续消息，时间戳为增量

```text
0-2 字节:   timestamp delta（3字节大端，相对上一Chunk的时间戳增量）
3-5 字节:   message length（3字节大端）
6 字节:     message type id（1字节）
（无 message stream id，继承 fmt=0 的值）
```

**fmt=2（3 字节头）：** 同 CSID 同 Stream 同长度同类型的后续消息

```text
0-2 字节:   timestamp delta（3字节大端）
（无 length/type/stream id，全部继承）
```

**fmt=3（无头，0字节）：** 完全继承上一 Chunk 的所有字段，用于大消息的后续分块

```text
无 Message Header 字段
（timestamp delta 也继承，即与上一块相同的增量）
```

### 3.3 Extended Timestamp

当 timestamp 或 timestamp delta >= 0xFFFFFF（16777215，约4.66小时）时，Message Header 中的时间戳字段设为 0xFFFFFF，并在 Chunk Data 前追加 **4 字节扩展时间戳**（大端）。

```text
Extended Timestamp: 4字节大端，实际时间戳值
仅当 fmt=0/1/2 的时间戳字段=0xFFFFFF 时出现
fmt=3 时，若上一Chunk有扩展时间戳则也出现
```

---

## 4. 消息类型与协议控制消息

Message Type ID（1字节）决定消息类型：

| Type ID | 名称 | 方向 | 说明 |
| --- | --- | --- | --- |
| 1 | Set Chunk Size | 双向 | 设置对端 Chunk 分块大小，默认128，最大2147483647 |
| 2 | Abort Message | 双向 | 中止当前 Chunk 消息的接收，丢弃已收部分 |
| 3 | Acknowledgement | 双向 | 确认已接收字节数，对端收到后可继续发送 |
| 4 | User Control Message | 双向 | 用户控制事件（Stream Begin/EOF/Dry/SetBufferLength 等） |
| 5 | Window Acknowledgement Size | 双向 | 设置窗口确认大小，对端每收这么多字节发一次 ACK |
| 6 | Set Peer Bandwidth | 双向 | 设置对端带宽，限制发送速率 |
| 8 | Audio Message | 推流端到服务器 | 音频数据（AAC/MP3 等） |
| 9 | Video Message | 推流端到服务器 | 视频数据（H.264/H.265 等） |
| 15 | Data Message (AMF3) | 双向 | AMF3 编码的数据消息（元数据） |
| 17 | Command Message (AMF3) | 双向 | AMF3 编码的命令消息 |
| 18 | Data Message (AMF0) | 双向 | AMF0 编码的数据消息（onMetaData） |
| 20 | Command Message (AMF0) | 双向 | AMF0 编码的命令消息（connect/publish/play） |
| 22 | Aggregate Message | 双向 | 聚合消息，包含多个子消息 |

### 协议控制消息详解

**Set Chunk Size（Type=1）：** Payload 为 4 字节大端整数，设置对端发送 Chunk 时的最大数据长度。推流开始时通常设为 4096 或更大，减少分块开销。

```text
示例：设置 Chunk Size=4096
Basic Header: 0x02 (fmt=0, csid=2)
Message Header: 00 00 00 00 00 04 01 00 00 00 00 (timestamp=0, length=4, type=1, stream=0)
Payload: 00 00 10 00 (4096 大端)
```

**Window Acknowledgement Size（Type=5）：** Payload 为 4 字节大端整数，通常设为 2500000（2.5MB）。

**Set Peer Bandwidth（Type=6）：** Payload 为 4 字节带宽 + 1 字节限制类型（0=硬限制, 1=软限制, 2=动态）。

**User Control Message（Type=4）：** Payload 为 2 字节事件类型 + 事件数据。

| 事件类型 | 名称 | 数据 |
| --- | --- | --- |
| 0 | Stream Begin | 4字节流ID |
| 1 | Stream EOF | 4字节流ID |
| 2 | Stream Dry | 4字节流ID |
| 3 | SetBufferLength | 4字节流ID + 4字节缓冲长度(ms) |
| 4 | StreamIsRecorded | 4字节流ID |
| 6 | PingRequest | 4字节时间戳 |
| 7 | PingResponse | 4字节时间戳 |

### AMF0 命令消息格式

命令消息（Type=20 AMF0）的 Payload 结构：

```text
1. Command Name（AMF0 String）：命令名，如 "connect", "createStream", "publish"
2. Transaction ID（AMF0 Number）：事务ID，用于匹配请求/响应
3. Command Object（AMF0 Object/null）：命令参数对象
4. [Optional Arguments...]：额外参数
```

AMF0 类型标记：

| 标记 | 类型 | 说明 |
| --- | --- | --- |
| 0x00 | Number | 8字节 IEEE 754 双精度 |
| 0x01 | Boolean | 1字节 |
| 0x02 | String | 2字节长度 + UTF-8 数据 |
| 0x03 | Object | 键值对序列，以 0x00 0x00 0x09 结束 |
| 0x05 | Null | 无数据 |
| 0x08 | ECMA Array | 4字节关联计数 + 键值对 |
| 0x0A | Strict Array | 4字节数组长度 + 元素 |

---

## 5. 推流流程（publish）状态机

推流是指编码器（FFmpeg/OBS）将音视频数据发送到 RTMP 服务器的过程。

```text
阶段1: 握手（C0/C1 -> S0/S1/S2 -> C2）
阶段2: connect 命令
  客户端 -> connect(app, tcUrl, ...)  [Type=20, CSID=3]
  服务器 -> Window Acknowledgement Size + Set Peer Bandwidth
  服务器 -> _result(transactionId=1, ...)  [连接成功]
阶段3: createStream
  客户端 -> createStream()  [transactionId=2]
  服务器 -> _result(transactionId=2, streamId=1)  [返回流ID]
阶段4: releaseStream + FCPublish（可选，部分服务器要求）
  客户端 -> releaseStream(null, streamKey)
  客户端 -> FCPublish(null, streamKey)
阶段5: publish
  客户端 -> publish(streamKey, "live")  [在 streamId=1 上]
  服务器 -> onStatus("NetStream.Publish.Start")
  服务器 -> User Control: Stream Begin(streamId=1)
阶段6: 推流数据
  客户端 -> 持续发送 Audio(Type=8) / Video(Type=9) Chunk
  客户端 -> onMetaData（码率、分辨率、帧率等元数据）
阶段7: 断开
  客户端 -> deleteStream() 或直接关闭 TCP
```

**connect 命令参数示例：**

```text
Command Name: "connect"
Transaction ID: 1
Command Object: {
  app: "live",              # 应用名，URL 中 rtmp://host/live/streamKey 的 live
  flashVer: "FMLE/3.0",    # 客户端版本
  tcUrl: "rtmp://192.168.1.100:1935/live",  # 完整URL
  fpad: false,
  capabilities: 239,
  audioCodecs: 3191,
  videoCodecs: 252,
  videoFunction: 1,
  objectEncoding: 0         # AMF0
}
```

**publish 命令参数：**

```text
Command Name: "publish"
Transaction ID: 0  (publish 不需要响应，事务ID通常为0)
Command Object: null
Argument 1: "streamKey"    # 流名，URL 路径的最后一段
Argument 2: "live"         # 类型：live(直播)/record(录制)/append(追加)
```

---

## 6. 拉流流程（play）状态机

拉流是指播放器从 RTMP 服务器接收音视频数据的过程。

```text
阶段1: 握手（同推流）
阶段2: connect
  客户端 -> connect(app, tcUrl, ...)
  服务器 -> _result(连接成功)
阶段3: createStream
  客户端 -> createStream()
  服务器 -> _result(streamId=1)
阶段4: play
  客户端 -> play(null, streamKey, -2, -1, false)
  服务器 -> User Control: Stream Begin(streamId=1)
  服务器 -> onStatus("NetStream.Play.Reset")
  服务器 -> onStatus("NetStream.Play.Start")
  服务器 -> RtmpSampleAccess（音频/视频采样访问权限）
阶段5: 接收数据
  服务器 -> 持续发送 Audio/Video Chunk + onMetaData
  （服务器可能先发 AVC/AAC 序列头，再发音视频帧）
阶段6: 暂停/继续（可选）
  客户端 -> pause(true/false, timestamp)
阶段7: 断开
  客户端 -> closeStream() 或 deleteStream()
```

**play 命令参数：**

```text
Command Name: "play"
Transaction ID: 0
Command Object: null
Argument 1: "streamKey"    # 流名
Argument 2: start          # 开始时间，-2=直播流优先, -1=直播, >=0=VOD起始位置(秒)
Argument 3: duration       # 播放时长，-1=播放到结束
Argument 4: reset          # 是否重置播放列表
```

---

## 7. 与 HLS / DASH / WebRTC 对比

| 维度 | RTMP | HLS | DASH | WebRTC |
| --- | --- | --- | --- | --- |
| 传输协议 | TCP (1935) | HTTP(S) | HTTP(S) | UDP/SRTP |
| 延迟 | 1-3秒 | 5-30秒 | 5-30秒 | 0.2-1秒 |
| 封装 | FLV Tag | MPEG-TS / fMP4 | fMP4 / WebM | RTP |
| 兼容性 | 需 Flash/专用播放器 | 全平台（iOS原生） | 需播放器支持 | 浏览器原生（Chrome/Firefox） |
| 自适应码率 | 不支持 | 支持（多码率m3u8） | 支持（MPD描述） | 支持（Simulcast/SVC） |
| 推流支持 | 是（事实标准） | 否（需先推RTMP再转HLS） | 否 | 是（但复杂） |
| 防火墙穿透 | 差（1935端口常被封） | 好（443端口） | 好（443端口） | 中（需STUN/TURN） |
| 典型场景 | 直播推流、低延迟互动 | 大规模直播、点播 | 点播、自适应码率 | 视频会议、实时互动 |

**RTMP 的低延迟优势：** 基于 TCP 长连接，消息流式传输，无需分片等待，端到端延迟通常 1-3 秒。局限是 TCP 重传导致卡顿累积、不支持自适应码率、1935 端口易被封。

**现代直播架构：** 推流端用 RTMP 推到服务器，服务器转封装为 HLS/DASH 分发，低延迟场景用 RTMP 或 WebRTC 直接拉流。HTTP-FLV（RTMP over HTTP）是折中方案，延迟 2-5 秒且兼容性好。

---

## 8. FFmpeg 推流与 nginx-rtmp-module 搭建

### 8.1 FFmpeg 推流命令

```bash
# 基础推流（本地文件推到 RTMP 服务器）
ffmpeg -re -i input.mp4 -c:v libx264 -preset veryfast -b:v 2500k \
  -c:a aac -b:a 128k -f flv rtmp://192.168.1.100:1935/live/streamKey

# 摄像头实时推流（Linux）
ffmpeg -f v4l2 -i /dev/video0 -f alsa -i default \
  -c:v libx264 -preset ultrafast -b:v 1500k -c:a aac -b:a 128k \
  -f flv rtmp://192.168.1.100:1935/live/streamKey

# 仅推流不转码（copy，要求源已是 H.264+AAC）
ffmpeg -re -i input.mp4 -c copy -f flv rtmp://192.168.1.100:1935/live/streamKey

# 推流 + 本地录制
ffmpeg -re -i input.mp4 -c:v libx264 -c:a aac \
  -f flv rtmp://192.168.1.100:1935/live/streamKey \
  -c copy output.flv
```

**关键参数说明：**

- `-re`：按原始帧率读取（模拟实时流，文件推流必加）
- `-c:v libx264`：视频编码 H.264（RTMP 标准要求）
- `-c:a aac`：音频编码 AAC（RTMP 标准要求）
- `-f flv`：输出格式 FLV（RTMP 封装格式）
- `-preset veryfast`：编码速度预设，ultrafast/fast/medium/slow

### 8.2 nginx-rtmp-module 搭建

```bash
# WSL Ubuntu 24.04 实跑：安装依赖
sudo apt install -y build-essential libpcre3 libpcre3-dev libssl-dev zlib1g-dev

# 下载 nginx 和 rtmp 模块源码
wget https://nginx.org/download/nginx-1.26.2.tar.gz
git clone https://github.com/arut/nginx-rtmp-module.git

# 编译安装
tar -xzf nginx-1.26.2.tar.gz
cd nginx-1.26.2
./configure --add-module=../nginx-rtmp-module --with-http_ssl_module
make -j$(nproc)
sudo make install
```

```nginx
# /usr/local/nginx/conf/nginx.conf
rtmp {
    server {
        listen 1935;
        chunk_size 4096;

        application live {
            live on;
            record off;

            # 转 HLS
            hls on;
            hls_path /tmp/hls;
            hls_fragment 3s;
            hls_playlist_length 15s;

            # 转 DASH
            dash on;
            dash_path /tmp/dash;
            dash_fragment 3s;

            # 推流认证（on_publish 回调）
            on_publish http://127.0.0.1:8080/auth;
        }
    }
}

http {
    server {
        listen 8080;
        location /hls {
            root /tmp;
            add_header Cache-Control no-cache;
        }
        location /dash {
            root /tmp;
        }
        # 推流认证回调
        location /auth {
            if ($arg_streamkey != "secret123") { return 403; }
            return 200;
        }
    }
}
```

```bash
# WSL Ubuntu 24.04 实跑：启动与测试
sudo /usr/local/nginx/sbin/nginx
# 推流测试
ffmpeg -re -i test.mp4 -c copy -f flv rtmp://localhost:1935/live/test?streamkey=secret123
# 拉流测试（ffplay）
ffplay rtmp://localhost:1935/live/test
# HLS 拉流
ffplay http://localhost:8080/hls/test.m3u8
```

---

## 9. 快速参考卡片

### Chunk 格式表

```text
Basic Header:
  fmt(2bit) + csid(6bit)           = 1字节 (csid 2-63)
  fmt(2bit) + 00(6bit) + csid-64   = 2字节 (csid 64-319)
  fmt(2bit) + 01(6bit) + csid-64(LE,2B) = 3字节 (csid 64-65599)

Message Header (by fmt):
  fmt=0: timestamp(3B) + length(3B) + type(1B) + streamId(4B LE) = 11B
  fmt=1: ts_delta(3B) + length(3B) + type(1B) = 7B
  fmt=2: ts_delta(3B) = 3B
  fmt=3: 0B (全继承)

Extended Timestamp: 4B BE，仅当 timestamp/delta >= 0xFFFFFF 时出现
```

### 推流拉流状态机

```text
推流: 握手 -> connect -> _result -> createStream -> _result(streamId)
      -> releaseStream/FCPublish(可选) -> publish -> onStatus(Publish.Start)
      -> Audio/Video 数据 -> deleteStream/断开

拉流: 握手 -> connect -> _result -> createStream -> _result(streamId)
      -> play -> StreamBegin -> onStatus(Play.Start)
      -> Audio/Video 数据 -> closeStream/断开
```

### FFmpeg 命令模板

```text
文件推流:  ffmpeg -re -i INPUT -c:v libx264 -preset veryfast -b:v 2500k
                    -c:a aac -b:a 128k -f flv rtmp://HOST:1935/APP/KEY
摄像头推流: ffmpeg -f v4l2 -i /dev/video0 -f alsa -i default
                    -c:v libx264 -preset ultrafast -c:a aac -f flv rtmp://...
直接copy:  ffmpeg -re -i INPUT -c copy -f flv rtmp://...
拉流播放:  ffplay rtmp://HOST:1935/APP/KEY
```

---

## 10. 常见问题与坑

| 问题 | 原因与解决 |
| --- | --- |
| 推流连接被拒 | 服务器 1935 端口未开放或防火墙拦截；检查 `listen 1935` 和 `ufw allow 1935` |
| 推流后服务器无流 | on_publish 认证回调返回非200；检查 streamkey 参数和回调逻辑 |
| 播放器花屏/绿屏 | 缺少 SPS/PPS 序列头；推流端必须在关键帧前发送 AVC Decoder Configuration Record |
| 音频不同步 | 时间戳不连续或音频采样率不匹配；确保音视频时间戳单调递增，AAC 用 44100/48000Hz |
| 延迟越来越大 | 播放器缓冲累积；设置 `ffplay -fflags nobuffer -flags low_delay`，或用 HTTP-FLV |
| Chunk Size 太小导致性能差 | 默认 128 字节分块开销大；推流开始时 Set Chunk Size 设为 4096+ |
| HLS 延迟高 | hls_fragment 设太大；生产用 2-3 秒分片，playlist_length 3-5 个分片 |
| RTMP 不支持 H.265 | 标准 RTMP 仅支持 H.264；H.265 需用增强 RTMP（enhanced RTMP）或转码为 H.264 |
| 多推流端同 key 冲突 | 同一 streamKey 只能一个推流端；第二个推流会被拒绝或踢掉第一个 |
| TCP 连接正常但无数据 | createStream 后未在正确的 streamId 上发 publish；确保 publish 命令的 message stream id 与 createStream 返回值一致 |

---

上一篇：《09-MQTT协议与mosquitto.md》　｜　模块索引：《README.md》
