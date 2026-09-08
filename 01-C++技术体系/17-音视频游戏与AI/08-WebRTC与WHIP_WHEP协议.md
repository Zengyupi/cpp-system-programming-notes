# WebRTC 与 WHIP/WHEP 协议

> 本节目标：讲解 WebRTC 实时通信的核心技术栈与 WHIP/WHEP HTTP 信令协议，学完后能够理解 SDP 媒体协商与 ICE 连通性检查、掌握 PeerConnection 与媒体轨道管理、实现 WHIP 推流与 WHEP 拉流服务、对比 RTMP/HLS 延迟与适用场景。对应岗位方向：音视频引擎、直播、RTC、视频会议（声网、腾讯云、字节、网易等）。音视频编解码基础（H.264/H.265/FFmpeg）见《06-音视频开发与编解码.md》。

## 本章速览

- [1. WebRTC 基础概念](#1-webrtc-基础概念)
  - [1.1 P2P 实时通信架构](#11-p2p-实时通信架构)
  - [1.2 浏览器原生支持与低延迟](#12-浏览器原生支持与低延迟)
- [2. SDP 协议](#2-sdp-协议)
  - [2.1 会话描述结构](#21-会话描述结构)
  - [2.2 Offer/Answer 交换流程](#22-offeranswer-交换流程)
- [3. ICE 候选处理](#3-ice-候选处理)
  - [3.1 候选类型：host/srflx/relay](#31-候选类型hostsrflxrelay)
  - [3.2 STUN/TURN 服务器](#32-stunturn-服务器)
  - [3.3 连通性检查（Connectivity Check）](#33-连通性检查connectivity-check)
- [4. PeerConnection 与媒体轨道](#4-peerconnection-与媒体轨道)
  - [4.1 RTCPeerConnection 生命周期](#41-rtcpeerconnection-生命周期)
  - [4.2 Audio/Video Track 管理](#42-audiovideo-track-管理)
- [5. WHIP 协议](#5-whip-协议)
  - [5.1 协议定位与规范](#51-协议定位与规范)
  - [5.2 HTTP 信令推流流程](#52-http-信令推流流程)
- [6. WHEP 协议](#6-whep-协议)
  - [6.1 协议定位与规范](#61-协议定位与规范)
  - [6.2 HTTP 信令拉流流程](#62-http-信令拉流流程)
- [7. WHIP 推流服务实现](#7-whip-推流服务实现)
  - [7.1 HTTP 服务器与 SDP 交换](#71-http-服务器与-sdp-交换)
  - [7.2 RTP 接收与推流状态管理](#72-rtp-接收与推流状态管理)
- [8. WHEP 拉流服务实现](#8-whep-拉流服务实现)
  - [8.1 拉流会话管理](#81-拉流会话管理)
  - [8.2 媒体流转发与多路拉流](#82-媒体流转发与多路拉流)
- [9. 信令服务器设计](#9-信令服务器设计)
  - [9.1 WebSocket 信令](#91-websocket-信令)
  - [9.2 房间管理与消息广播](#92-房间管理与消息广播)
- [10. 与 RTMP/HLS 对比及适用场景](#10-与-rtmphls-对比及适用场景)
- [11. 快速参考卡片](#11-快速参考卡片)
- [12. 常见问题与坑](#12-常见问题与坑)

---

## 1. WebRTC 基础概念

### 1.1 P2P 实时通信架构

WebRTC（Web Real-Time Communication）是支持浏览器进行实时音视频通信的开放标准，由 W3C 和 IETF 标准化。

```text
┌──────────┐                    ┌──────────┐
│ 浏览器 A  │                    │ 浏览器 B  │
│          │  1. 信令交换(SDP/ICE)│          │
│          │ <─────────────────> │          │
│          │                    │          │
│          │  2. P2P 媒体流      │          │
│          │ <=================> │          │
│          │  (SRTP/DTLS 加密)   │          │
└──────────┘                    └──────────┘
     ^                               ^
     │  STUN（发现公网地址）           │
     │  TURN（中继转发，P2P失败时）    │
┌──────────┐                    ┌──────────┐
│ STUN/TURN│                    │ 信令服务器 │
│  服务器   │                    │ (WebSocket)│
└──────────┘                    └──────────┘
```

核心组件：
- **信令服务器**：交换 SDP 和 ICE 候选（WebRTC 不规定信令协议）
- **STUN 服务器**：帮助发现 NAT 后的公网地址
- **TURN 服务器**：P2P 无法建立时中继媒体数据
- **媒体引擎**：浏览器内置，负责编解码、抖动缓冲、回声消除

### 1.2 浏览器原生支持与低延迟

| 浏览器 | 支持情况 |
| --- | --- |
| Chrome | 完整支持，libwebrtc 内核 |
| Firefox | 完整支持 |
| Safari | 支持（需 HTTPS） |
| Edge | 基于 Chromium，完整支持 |

低延迟关键：
- **UDP 传输**：不重传丢失包，避免延迟累积
- **Jitter Buffer**：动态缓冲，平衡延迟与流畅
- **NACK/PLI**：选择性重传关键帧，而非全部重传
- **带宽估计**：GCC（Google Congestion Control）动态调整码率
- 端到端延迟通常 **200ms ~ 500ms**，远低于 HLS（5~30s）

---

## 2. SDP 协议

### 2.1 会话描述结构

SDP（Session Description Protocol）是纯文本格式的会话描述，用于交换媒体能力。

```text
v=0
o=- 4611738904653701706 2 IN IP4 127.0.0.1
s=-
t=0 0
a=group:BUNDLE 0 1
a=extmap-allow-mixed
m=audio 9 UDP/TLS/RTP/SAVPF 111 103 104 9 0 8 106 105 13 110 112 113 126
c=IN IP4 0.0.0.0
a=rtcp:9 IN IP4 0.0.0.0
a=ice-ufrag:uFwO
a=ice-pwd:xxxxxxxxxxxxxxxxxxxx
a=fingerprint:sha-256 xx:xx:xx:...
a=setup:actpass
a=mid:0
a=rtpmap:111 opus/48000/2
a=rtcp-fb:111 transport-cc
a=fmtp:111 minptime=10;useinbandfec=1
a=rtpmap:103 ISAC/16000
...
m=video 9 UDP/TLS/RTP/SAVPF 96 97 98 99 100 101 102 121 127 120 125 107 108 109 124 119 123 118 114 115 116
c=IN IP4 0.0.0.0
a=mid:1
a=rtpmap:96 VP8/90000
a=rtcp-fb:96 goog-remb
a=rtcp-fb:96 transport-cc
a=rtcp-fb:96 ccm fir
a=rtcp-fb:96 nack
a=rtcp-fb:96 nack pli
...
```

| 字段 | 含义 |
| --- | --- |
| `v=` | SDP 版本 |
| `o=` | 会话发起者（用户名、ID、版本、地址） |
| `m=` | 媒体行：类型（audio/video）、端口、传输协议、payload type 列表 |
| `c=` | 连接信息（IP 地址） |
| `a=` | 属性行：ice-ufrag/pwd、fingerprint、rtpmap、fmtp 等 |
| `a=mid` | 媒体标识，BUNDLE 复用用 |
| `a=rtpmap` | payload type 到编码的映射（如 111=opus/48000/2） |
| `a=fmtp` | 编码参数（如 opus 的 minptime） |
| `a=rtcp-fb` | RTCP 反馈（nack、pli、goog-remb） |

### 2.2 Offer/Answer 交换流程

```text
调用方（Offer）                    应答方（Answer）
    │                                │
    │ 1. createOffer()               │
    │ 2. setLocalDescription(offer)  │
    │ ──────── offer SDP ──────────> │
    │                                │ 3. setRemoteDescription(offer)
    │                                │ 4. createAnswer()
    │                                │ 5. setLocalDescription(answer)
    │ <─────── answer SDP ────────── │
    │ 6. setRemoteDescription(answer)│
    │                                │
    │ <====== 媒体流（SRTP）=======> │
```

JavaScript 示例：

```javascript
// 发送方
const pc = new RTCPeerConnection({ iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] });
pc.addTrack(stream.getVideoTracks()[0], stream);
const offer = await pc.createOffer();
await pc.setLocalDescription(offer);
signaling.send({ type: 'offer', sdp: offer.sdp });

// 接收方
pc.ontrack = (e) => { remoteVideo.srcObject = e.streams[0]; };
await pc.setRemoteDescription(new RTCSessionDescription(offer));
const answer = await pc.createAnswer();
await pc.setLocalDescription(answer);
signaling.send({ type: 'answer', sdp: answer.sdp });
```

---

## 3. ICE 候选处理

### 3.1 候选类型：host/srflx/relay

ICE（Interactive Connectivity Establishment）收集所有可能的通信地址，按优先级尝试连接。

| 类型 | 全称 | 说明 | 优先级 |
| --- | --- | --- | --- |
| **host** | Host Candidate | 本机网卡地址（局域网 IP） | 最高 |
| **srflx** | Server Reflexive | STUN 发现的 NAT 公网映射地址 | 中 |
| **relay** | Relayed Candidate | TURN 服务器分配的中继地址 | 最低 |

```text
候选地址示例：
candidate:842163049 1 udp 1677729535 192.168.1.100 52575 typ host
candidate:123456789 1 udp 1677729535 203.0.113.50 52575 typ srflx raddr 192.168.1.100 rport 52575
candidate:987654321 1 udp 41885439 198.51.100.10 60000 typ relay raddr 203.0.113.50 rport 52575
```

候选格式：`candidate:<foundation> <component> <protocol> <priority> <ip> <port> typ <type>`

### 3.2 STUN/TURN 服务器

**STUN**（Session Traversal Utilities for NAT）：
- 客户端向 STUN 服务器发请求，服务器返回客户端看到的公网 IP:Port
- 用于发现 srflx 候选
- 轻量，仅在连接建立时使用

**TURN**（Traversal Using Relays around NAT）：
- 当 P2P 无法建立（对称 NAT、企业防火墙）时，通过 TURN 中继
- 媒体流经过 TURN 服务器转发，消耗带宽
- 标准端口 3478，TURN over TLS 5349

常用开源实现：
- **coturn**：最流行的 STUN/TURN 服务器，C 语言实现
- **pion/turn**：Go 语言实现，易嵌入

```bash
# coturn 启动示例
turnserver -c /etc/turnserver.conf
# 配置关键项：
# listening-port=3478
# relay-ip=192.168.1.100
# external-ip=203.0.113.50
# user=username:password
# realm=example.com
```

### 3.3 连通性检查（Connectivity Check）

ICE 收集完候选后，按优先级配对进行连通性检查：

```text
1. 候选收集（Gathering）：host → srflx → relay
2. 候选交换：通过信令服务器交换对端候选
3. 配对排序：按优先级公式排序所有候选对
4. 连通性检查：发送 STUN Binding Request，验证可达性
5. 选定候选对（Nominated Pair）：第一个成功的配对用于媒体传输
6. 持续检查：ICE Keepalive，网络变化时重新协商
```

优先级公式：
```
priority = (2^24)*(type_preference) + (2^8)*(local_preference) + (2^0)*(256-component_id)
type_preference: host=126, srflx=100, relay=0
```

---

## 4. PeerConnection 与媒体轨道

### 4.1 RTCPeerConnection 生命周期

```text
new ──> have-local-offer ──> have-remote-offer ──> stable
         ↑                      │                      │
         │                      ▼                      │
         └──────── have-local-pranswer <── have-remote-pranswer
```

| 状态 | 说明 |
| --- | --- |
| `new` | 刚创建，未设置任何描述 |
| `have-local-offer` | 已设置本地 offer |
| `have-remote-offer` | 已设置远端 offer |
| `have-local-pranswer` | 已设置本地临时应答 |
| `have-remote-pranswer` | 已设置远端临时应答 |
| `stable` | offer/answer 交换完成，连接稳定 |

ICE 连接状态：`new` → `checking` → `connected` → `completed`（或 `failed`/`disconnected`/`closed`）

### 4.2 Audio/Video Track 管理

```javascript
// 获取本地媒体
const stream = await navigator.mediaDevices.getUserMedia({
    audio: true,
    video: { width: 1280, height: 720, frameRate: 30 }
});

// 添加轨道到 PeerConnection
const audioSender = pc.addTrack(stream.getAudioTracks()[0], stream);
const videoSender = pc.addTrack(stream.getVideoTracks()[0], stream);

// 动态替换轨道（如切换摄像头）
const newStream = await navigator.mediaDevices.getUserMedia({ video: true });
await videoSender.replaceTrack(newStream.getVideoTracks()[0]);

// 接收远端轨道
pc.ontrack = (event) => {
    if (event.track.kind === 'video') {
        remoteVideo.srcObject = event.streams[0];
    }
};

// 轨道控制
stream.getVideoTracks()[0].enabled = false;  // 静音/关闭摄像头（黑帧）
stream.getVideoTracks()[0].stop();            // 彻底释放设备
```

| 概念 | 说明 |
| --- | --- |
| **MediaStream** | 轨道容器，可包含多个 audio/video track |
| **MediaStreamTrack** | 单条媒体轨道，对应一个摄像头/麦克风 |
| **RTCRtpSender** | 发送端控制，可替换轨道、设置编码参数 |
| **RTCRtpReceiver** | 接收端控制，可获取统计信息 |
| **RTCRtpTransceiver** | sender + receiver 组合，对应 SDP 中的 m= 行 |

---

## 5. WHIP 协议

### 5.1 协议定位与规范

WHIP（WebRTC-HTTP Ingestion Protocol）是 IETF 草案，定义了用 HTTP 做 WebRTC 推流信令的标准方式。

- **规范**：draft-ietf-wish-whip（IETF WISH 工作组）
- **核心思想**：用 HTTP POST 交换 SDP，替代自定义 WebSocket 信令
- **适用场景**：OBS、FFmpeg、移动端推流到媒体服务器
- **优势**：标准化、可穿透防火墙、易于 CDN 集成、支持认证

### 5.2 HTTP 信令推流流程

```text
推流端（WHIP Client）              媒体服务器（WHIP Server）
       │                                │
       │ POST /whip/endpoint            │
       │ Content-Type: application/sdp  │
       │ Body: offer SDP                │
       │ ─────────────────────────────> │
       │                                │ 处理 offer，创建 PeerConnection
       │ 201 Created                    │
       │ Content-Type: application/sdp  │
       │ Location: /whip/endpoint/sess1 │
       │ Body: answer SDP               │
       │ <───────────────────────────── │
       │                                │
       │ <====== SRTP 媒体流 =========> │
       │                                │
       │ DELETE /whip/endpoint/sess1    │
       │ ─────────────────────────────> │ 停止推流，释放资源
       │ 200 OK                         │
       │ <───────────────────────────── │
```

关键 HTTP 头：
- `Content-Type: application/sdp`：SDP 内容类型
- `Location`：返回的会话资源 URL，用于后续管理
- `Authorization: Bearer <token>`：认证
- `Link: <...>; rel="urn:ietf:params:..."`：扩展能力声明

---

## 6. WHEP 协议

### 6.1 协议定位与规范

WHEP（WebRTC-HTTP Egress Protocol）是 WHIP 的对应协议，用于 HTTP 信令拉流。

- **规范**：draft-ietf-wish-whep
- **核心思想**：用 HTTP POST 交换 SDP，从服务器拉取 WebRTC 流
- **适用场景**：浏览器播放、CDN 回源、级联
- **与 WHIP 对称**：WHIP 是推（Ingestion），WHEP 是拉（Egress）

### 6.2 HTTP 信令拉流流程

```text
拉流端（WHEP Client）              媒体服务器（WHEP Server）
       │                                │
       │ POST /whep/stream/stream1      │
       │ Content-Type: application/sdp  │
       │ Body: offer SDP                │
       │ ─────────────────────────────> │
       │                                │ 查找流，创建 PeerConnection
       │ 201 Created                    │
       │ Content-Type: application/sdp  │
       │ Location: /whep/stream/sess2   │
       │ Body: answer SDP               │
       │ <───────────────────────────── │
       │                                │
       │ <====== SRTP 媒体流 ========== │
       │                                │
       │ DELETE /whep/stream/sess2      │
       │ ─────────────────────────────> │ 停止拉流
       │ 200 OK                         │
       │ <───────────────────────────── │
```

---

## 7. WHIP 推流服务实现

### 7.1 HTTP 服务器与 SDP 交换

以 Go + pion/webrtc 为例实现 WHIP 服务端：

```go
package main

import (
    "io"
    "net/http"
    "github.com/pion/webrtc/v3"
)

var peerConnections = make(map[string]*webrtc.PeerConnection)

func whipHandler(w http.ResponseWriter, r *http.Request) {
    if r.Method != http.MethodPost {
        http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
        return
    }
    // 读取 offer SDP
    body, _ := io.ReadAll(r.Body)
    offer := webrtc.SessionDescription{
        Type: webrtc.SDPTypeOffer,
        SDP:  string(body),
    }

    // 创建 PeerConnection
    pc, _ := webrtc.NewPeerConnection(webrtc.Configuration{
        ICEServers: []webrtc.ICEServer{
            {URLs: []string{"stun:stun.l.google.com:19302"}},
        },
    })

    // 接收轨道回调
    pc.OnTrack(func(track *webrtc.TrackRemote, receiver *webrtc.RTPReceiver) {
        // 将 RTP 包转发到其他订阅者或录制
        go func() {
            for {
                pkt, _, _ := track.ReadRTP()
                // 处理 pkt
            }
        }()
    })

    pc.SetRemoteDescription(offer)
    answer, _ := pc.CreateAnswer(nil)
    pc.SetLocalDescription(answer)

    // 返回 answer SDP
    sessionID := generateSessionID()
    peerConnections[sessionID] = pc
    w.Header().Set("Content-Type", "application/sdp")
    w.Header().Set("Location", "/whip/"+sessionID)
    w.WriteHeader(http.StatusCreated)
    w.Write([]byte(answer.SDP))
}

func main() {
    http.HandleFunc("/whip", whipHandler)
    http.HandleFunc("/whip/", func(w http.ResponseWriter, r *http.Request) {
        if r.Method == http.MethodDelete {
            id := r.URL.Path[len("/whip/"):]
            if pc, ok := peerConnections[id]; ok {
                pc.Close()
                delete(peerConnections, id)
            }
            w.WriteHeader(http.StatusOK)
        }
    })
    http.ListenAndServe(":8080", nil)
}
```

### 7.2 RTP 接收与推流状态管理

```go
// 推流会话状态
type WHIPSession struct {
    PC        *webrtc.PeerConnection
    StreamID  string
    Tracks    map[uint32]*webrtc.TrackRemote  // SSRC → track
    StartTime time.Time
    Bytes     uint64
    Packets   uint64
}

// ICE 状态监控
pc.OnICEConnectionStateChange(func(state webrtc.ICEConnectionState) {
    switch state {
    case webrtc.ICEConnectionStateConnected:
        log.Println("推流连接建立")
    case webrtc.ICEConnectionStateFailed:
        log.Println("推流连接失败，清理资源")
        pc.Close()
    case webrtc.ICEConnectionStateDisconnected:
        // 启动重连计时器，超时后关闭
        time.AfterFunc(30*time.Second, func() {
            if pc.ICEConnectionState() == webrtc.ICEConnectionStateDisconnected {
                pc.Close()
            }
        })
    }
})
```

---

## 8. WHEP 拉流服务实现

### 8.1 拉流会话管理

```go
type WHEPSession struct {
    PC        *webrtc.PeerConnection
    StreamID  string
    Senders   []*webrtc.RTPSender
    StartTime time.Time
}

var whepSessions = make(map[string]*WHEPSession)

func whepHandler(w http.ResponseWriter, r *http.Request) {
    streamID := r.URL.Query().Get("stream")
    body, _ := io.ReadAll(r.Body)
    offer := webrtc.SessionDescription{Type: webrtc.SDPTypeOffer, SDP: string(body)}

    pc, _ := webrtc.NewPeerConnection(webrtc.Configuration{
        ICEServers: []webrtc.ICEServer{{URLs: []string{"stun:stun.l.google.com:19302"}}},
    })

    // 从推流会话获取轨道，添加到本地
    if pushSession := getPushSession(streamID); pushSession != nil {
        for _, track := range pushSession.Tracks {
            // 创建本地 track 转发
            localTrack, _ := webrtc.NewTrackLocalStaticRTP(
                track.Codec().RTPCodecCapability,
                track.ID(), track.StreamID(),
            )
            sender, _ := pc.AddTrack(localTrack)
            // 启动转发 goroutine
            go forwardRTP(track, localTrack, sender)
        }
    }

    pc.SetRemoteDescription(offer)
    answer, _ := pc.CreateAnswer(nil)
    pc.SetLocalDescription(answer)

    sessionID := generateSessionID()
    whepSessions[sessionID] = &WHEPSession{PC: pc, StreamID: streamID}
    w.Header().Set("Content-Type", "application/sdp")
    w.Header().Set("Location", "/whep/"+sessionID)
    w.WriteHeader(http.StatusCreated)
    w.Write([]byte(answer.SDP))
}
```

### 8.2 媒体流转发与多路拉流

```go
// RTP 转发：从推流 track 读取，写入所有拉流本地 track
func forwardRTP(src *webrtc.TrackRemote, dst *webrtc.TrackLocalStaticRTP,
                sender *webrtc.RTPSender) {
    for {
        pkt, _, err := src.ReadRTP()
        if err != nil { return }
        // 可在此处做转码、转封装、统计
        dst.WriteRTP(pkt)
    }
}

// 多路拉流：一个推流对应 N 个拉流会话
// 推流 track → 广播到所有订阅者的本地 track
type StreamBroker struct {
    pushTrack *webrtc.TrackRemote
    subscribers []*webrtc.TrackLocalStaticRTP
    mu sync.RWMutex
}

func (b *StreamBroker) broadcast() {
    for {
        pkt, _, err := b.pushTrack.ReadRTP()
        if err != nil { return }
        b.mu.RLock()
        for _, sub := range b.subscribers {
            sub.WriteRTP(pkt)
        }
        b.mu.RUnlock()
    }
}
```

---

## 9. 信令服务器设计

### 9.1 WebSocket 信令

对于 P2P 视频会议场景，需要自定义信令服务器（WebRTC 不规定信令）：

```javascript
// 信令消息类型
// { type: 'join', room: '123' }
// { type: 'offer', to: 'user2', sdp: '...' }
// { type: 'answer', to: 'user1', sdp: '...' }
// { type: 'ice', to: 'user2', candidate: {...} }
// { type: 'leave', room: '123' }

const WebSocket = require('ws');
const wss = new WebSocket.Server({ port: 8888 });

const rooms = new Map();  // roomId → Set<ws>

wss.on('connection', (ws) => {
    ws.on('message', (data) => {
        const msg = JSON.parse(data);
        switch (msg.type) {
            case 'join':
                if (!rooms.has(msg.room)) rooms.set(msg.room, new Set());
                rooms.get(msg.room).add(ws);
                ws.roomId = msg.room;
                // 通知房间内其他人有新用户加入
                broadcast(msg.room, { type: 'user-joined', id: msg.userId }, ws);
                break;
            case 'offer':
            case 'answer':
            case 'ice':
                // 转发给目标用户
                forwardToUser(msg.to, msg);
                break;
        }
    });
});
```

### 9.2 房间管理与消息广播

```text
信令服务器架构：
┌──────────────────────────────────────────┐
│           WebSocket 网关（无状态）          │
│  ┌────────┐  ┌────────┐  ┌────────┐     │
│  │ 连接1   │  │ 连接2   │  │ 连接3   │     │
│  └────────┘  └────────┘  └────────┘     │
└──────────────┬───────────────────────────┘
               │ Redis Pub/Sub
┌──────────────▼───────────────────────────┐
│           房间状态存储（Redis）             │
│  room:123 → [user1, user2, user3]        │
└──────────────────────────────────────────┘
```

设计要点：
- **无状态网关**：WebSocket 连接不存房间状态，便于水平扩展
- **Redis Pub/Sub**：跨节点广播信令消息
- **心跳检测**：30s 无消息断开，清理房间
- **SFU 集成**：多人会议时信令服务器协调 SFU 端口

---

## 10. 与 RTMP/HLS 对比及适用场景

| 维度 | WebRTC | RTMP | HLS |
| --- | --- | --- | --- |
| **传输协议** | SRTP over UDP | TCP | HTTP(TCP) |
| **延迟** | 200ms ~ 500ms | 1s ~ 3s | 5s ~ 30s |
| **浏览器支持** | 原生支持 | 需插件（已淘汰） | 原生支持（HLS.js/MSE） |
| **连接建立** | ICE 协商（复杂） | TCP 直连（简单） | HTTP 请求（简单） |
| **穿透 NAT** | STUN/TURN | 需公网或端口映射 | HTTP 天然穿透 |
| **加密** | DTLS-SRTP（强制） | RTMPS（可选） | HTTPS（可选） |
| **丢包处理** | NACK/PLI + FEC | TCP 重传（延迟大） | TCP 重传 |
| **码率自适应** | GCC 动态调整 | 固定码率 | 多码率自适应 |
| **适用场景** | 视频会议、互动直播、云游戏 | 传统直播推流（OBS） | 大规模点播/直播 |
| **服务端复杂度** | 高（SFU/MCU） | 中（Nginx-RTMP） | 低（静态文件） |

**选型建议**：
- **互动直播（连麦）**：WebRTC（低延迟）+ RTMP/HLS（大规模分发）混合
- **视频会议**：WebRTC + SFU（如 mediasoup、Janus）
- **秀场直播**：RTMP 推流 + HLS/HTTP-FLV 分发
- **云游戏/云桌面**：WebRTC（必须低延迟）
- **监控/安防**：WebRTC（低延迟预览）+ HLS（存储回放）

---

## 11. 快速参考卡片

```text
SDP 字段速查：
  v=0              SDP版本
  o=<user> <id> <ver> IN IP4 <addr>  发起者信息
  m=<media> <port> <proto> <pt...>   媒体行(audio/video, UDP/TLS/RTP/SAVPF)
  a=ice-ufrag:<xxx>  ICE 用户名片段
  a=ice-pwd:<xxx>    ICE 密码
  a=fingerprint:sha-256 <xx:xx:...>  DTLS 证书指纹
  a=setup:actpass    DTLS 角色(active/passive/actpass)
  a=mid:<id>         媒体标识(BUNDLE复用)
  a=rtpmap:<pt> <codec>/<rate>/<ch>  编码映射
  a=fmtp:<pt> <params>               编码参数
  a=rtcp-fb:<pt> <fb>                RTCP反馈(nack/pli/goog-remb)

WHIP/WHEP 流程：
  POST /whip|whep/<endpoint>  Content-Type: application/sdp  Body: offer
  → 201 Created  Content-Type: application/sdp  Location: <session_url>  Body: answer
  → SRTP 媒体流传输
  DELETE <session_url> → 200 OK（结束会话）

ICE 候选类型表：
  host   本机IP，优先级最高，局域网直连用
  srflx  STUN发现的NAT映射地址，P2P穿透用
  relay  TURN中继地址，P2P失败时兜底，优先级最低
```

## 12. 常见问题与坑

1. **ICE 连接失败（ICE failed）**：对称 NAT 或企业防火墙阻止 UDP。解决：配置 TURN 服务器，确保 TURN 端口开放。
2. **本地测试正常，线上无法连接**：缺少 STUN/TURN 或 TURN 配置错误。解决：用 `trickle-ice` 工具测试，检查 coturn 配置的 `external-ip`。
3. **Safari 不支持**：Safari 需要 HTTPS 环境，且部分 API 有前缀。解决：用 adapter.js 抹平差异，确保 HTTPS。
4. **音频回声**：未开启回声消除（AEC）。解决：`getUserMedia` 中 `audio: { echoCancellation: true }`，默认已开启。
5. **视频卡顿/花屏**：带宽不足或丢包率高。解决：降低分辨率/码率，开启 simulcast（多档码率）。
6. **SDP 协商失败**：两端编码不兼容。解决：检查 SDP 中 rtpmap，确保有共同编码（如 H.264），用 `setCodecPreferences` 指定。
7. **WHIP 推流 401/403**：认证失败。解决：检查 `Authorization: Bearer` token，确保媒体服务器配置了认证。
8. **多人会议 CPU 过高**：P2P mesh 模式 N 平方连接。解决：用 SFU（mediasoup/Janus），客户端只连 SFU。
9. **TURN 带宽耗尽**：大量用户走中继。解决：优化 ICE 候选优先级，部署边缘 TURN 节点，限制单用户带宽。
10. **移动端后台断流**：App 进入后台后 WebRTC 暂停。解决：iOS 用 CallKit + PushKit，Android 用前台服务保活。

---

上一篇：《07-游戏服务器架构Skynet.md》
下一篇：《09-ROS2实操要点.md》
