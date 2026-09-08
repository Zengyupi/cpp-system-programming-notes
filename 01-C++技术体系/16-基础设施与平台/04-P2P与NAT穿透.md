# P2P 与 NAT 穿透

> 本节目标：讲解 NAT 原理与类型、P2P 穿透的核心机制、STUN/TURN/ICE 协议族，学完后能够理解不同 NAT 类型下的穿透策略、掌握 UDP/TCP 打洞的实现思路、熟悉 STUN/TURN/ICE 的协作流程、能够基于 libnice 或自研信令搭建 P2P 通信。对应岗位方向：音视频通信、即时通讯、文件共享、游戏联机、物联网设备互联。

## 本章速览

- [1. NAT 原理与类型](#1-nat-原理与类型)
  - [1.1 NAT 工作机制](#11-nat-工作机制)
  - [1.2 四种 NAT 类型](#12-四种-nat-类型)
- [2. NAT 类型检测（STUN 协议）](#2-nat-类型检测stun-协议)
  - [2.1 STUN 协议结构](#21-stun-协议结构)
  - [2.2 NAT 类型检测流程](#22-nat-类型检测流程)
- [3. P2P 穿透原理](#3-p2p-穿透原理)
  - [3.1 UDP 打洞](#31-udp-打洞)
  - [3.2 TCP 打洞](#32-tcp-打洞)
  - [3.3 中继转发（TURN）](#33-中继转发turn)
- [4. 穿透的三种拓扑场景](#4-穿透的三种拓扑场景)
- [5. STUN/TURN/ICE 协议族](#5-stunturnice-协议族)
  - [5.1 信令交换](#51-信令交换)
  - [5.2 候选地址收集](#52-候选地址收集)
  - [5.3 连通性检查（Connectivity Check）](#53-连通性检查connectivity-check)
- [6. 典型 P2P 框架实现思路](#6-典型-p2p-框架实现思路)
- [7. 代码实现](#7-代码实现)
  - [7.1 NAT 类型检测](#71-nat-类型检测)
  - [7.2 UDP 打洞实现](#72-udp-打洞实现)
- [8. 快速参考卡片](#8-快速参考卡片)
- [9. 常见问题与坑](#9-常见问题与坑)

---

## 1. NAT 原理与类型

NAT（Network Address Translation，网络地址转换）解决 IPv4 地址不足问题，允许多台内网设备共享一个公网 IP。NAT 设备维护一张**地址映射表**，将内网 `(私网IP, 私网端口)` 映射为 `(公网IP, 公网端口)`。

### 1.1 NAT 工作机制

```text
内网主机 192.168.1.100:5000  ──→  NAT路由器  ──→  公网服务器 203.0.113.10:80
     源IP:192.168.1.100        映射表:               看到的源:
     源端口:5000               192.168.1.100:5000    118.26.5.10:32100
                              → 118.26.5.10:32100
```

出站数据包：NAT 修改源 IP/端口为映射后的公网地址；
入站数据包：NAT 根据映射表将目标公网地址还原为内网地址。

**关键约束**：入站数据包必须匹配映射表中已有的条目，否则 NAT 会丢弃。这就是 P2P 穿透需要解决的核心问题——如何让两个都在 NAT 后的主机互相看到对方的公网映射。

### 1.2 四种 NAT 类型

RFC 3489 定义了四种 NAT 类型，按"对入站数据包的过滤严格程度"从宽松到严格排列：

| NAT 类型 | 映射规则 | 入站过滤规则 | 穿透难度 |
| --- | --- | --- | --- |
| **完全锥型（Full Cone）** | 同一内网 `(IP,端口)` 始终映射到同一公网 `(IP,端口)` | 任何外部主机都可向该公网地址发包 | 最容易，直接打洞 |
| **IP 限制锥型（Restricted Cone）** | 同上 | 仅允许内网主机曾发送过数据的外部 IP 回包 | 需先向对方发一个包"打洞" |
| **端口限制锥型（Port Restricted Cone）** | 同上 | 仅允许内网主机曾发送过数据的外部 `(IP,端口)` 回包 | 需双方同时向对方打洞 |
| **对称型（Symmetric）** | 对不同目标 `(IP,端口)` 分配不同的公网端口 | 同端口限制锥型 | 极难，通常需中继 |

```text
完全锥型：    A 打洞后，B/C/D 任意主机都能向 A 的公网地址发包
IP限制锥型：  A 向 B 发过包后，只有 B 能回包（B 的任意端口均可）
端口限制锥型：A 向 B:8000 发过包后，只有 B:8000 能回包
对称型：      A 向 B:8000 和向 C:9000 会得到不同的公网端口映射
```

> 对称型 NAT 因为对不同目标分配不同端口，对方无法预测自己的公网端口，纯 P2P 打洞几乎不可能成功，必须依赖 TURN 中继或预测端口（端口递增猜测，成功率低）。

---

## 2. NAT 类型检测（STUN 协议）

STUN（Session Traversal Utilities for NAT，RFC 5389）是一个轻量级协议，用于客户端发现自己在 NAT 后的公网映射地址和 NAT 类型。

### 2.1 STUN 协议结构

```text
STUN 消息格式（20 字节头 + 属性）：
┌─────────────────────────────────────────┐
│ 类型(16bit) │ 长度(16bit)               │
├─────────────────────────────────────────┤
│ Magic Cookie(32bit) = 0x2112A442        │
├─────────────────────────────────────────┤
│ Transaction ID(96bit)                   │
├─────────────────────────────────────────┤
│ 属性（TLV：Type-Length-Value）...        │
└─────────────────────────────────────────┘
```

常用消息类型：
- `0x0001` Binding Request：客户端请求绑定，服务器返回公网映射地址
- `0x0101` Binding Response：包含 `XOR-MAPPED-ADDRESS` 属性（客户端的公网 IP:端口）

STUN 服务器有两个公网 IP 和两个端口（用于检测 NAT 类型）。

### 2.2 NAT 类型检测流程

RFC 3489 定义的检测算法（通过多轮 Binding Request 对比映射结果）：

```text
步骤1：客户端向 STUN 服务器 IP1:Port1 发 Binding Request
       → 得到映射地址 M1（公网IP:端口）
       → 若 M1 == 本机地址，则为公网主机，无 NAT

步骤2：服务器从 IP2:Port2（不同IP）回复
       → 若客户端收到，说明 NAT 是完全锥型（不限制源IP）
       → 若收不到，继续步骤3

步骤3：客户端向 STUN 服务器 IP1:Port2（同IP不同端口）发 Binding Request
       → 得到映射地址 M2
       → 若 M1 == M2，说明映射不随目标端口变化 → 锥型
         再发一个请求让服务器从不同端口回，判断是IP限制还是端口限制
       → 若 M1 != M2，说明映射随目标变化 → 对称型
```

实际生产中，RFC 3489 的 NAT 类型检测已被认为不可靠（NAT 行为复杂多变），现代 WebRTC 使用 ICE 框架直接做连通性检查，不再依赖精确的 NAT 类型判定。

---

## 3. P2P 穿透原理

### 3.1 UDP 打洞

UDP 是无连接协议，打洞相对简单。核心思想：**双方同时向对方的公网映射地址发送 UDP 包，在各自 NAT 上创建"允许对方入站"的映射条目**。

```text
前提：A 和 B 通过信令服务器交换了各自的公网映射地址（由 STUN 获取）

A: 192.168.1.100 → NAT_A → 公网 118.26.5.10:32100
B: 192.168.2.200 → NAT_B → 公网 119.30.20.5:45000

步骤：
1. A 向 119.30.20.5:45000 发 UDP 包 → NAT_A 创建映射，允许 B 回包
2. B 向 118.26.5.10:32100 发 UDP 包 → NAT_B 创建映射，允许 A 回包
3. 双方的包可能互相穿过对方 NAT（"打洞"成功）
4. 此后 A 和 B 可直接通信
```

时序关键点：双方必须在 NAT 映射条目超时前（通常 30s~5min）完成打洞，且需要**几乎同时**发送，因为先发的一方的包会被对方 NAT 丢弃（对方还没创建映射），但这没关系——先发方的包已经在自己 NAT 上创建了允许对方入站的规则。

### 3.2 TCP 打洞

TCP 是面向连接协议，打洞比 UDP 复杂，需要处理 TCP 状态机。核心技术是 **TCP 同时打开（Simultaneous Open）**：

```text
1. A 和 B 通过信令交换公网地址
2. A 调用 connect() 连接 B 的公网地址（同时 bind 到本地端口）
3. B 调用 connect() 连接 A 的公网地址（同时 bind 到本地端口）
4. 双方发出 SYN 包，在 NAT 上创建映射
5. 两个 SYN 在网络中交叉到达对方
6. TCP 状态机进入 SYN_RECV → 双方回 SYN+ACK → 建立连接
```

TCP 打洞的难点：
- 必须设置 `SO_REUSEADDR`（部分系统需 `SO_REUSEPORT`），允许 bind 和 connect 使用同一端口
- NAT 对 TCP 连接的超时通常比 UDP 短（约 2~4 分钟）
- 对称型 NAT 下 TCP 打洞基本不可行
- 部分 NAT 会"篡改"TCP 序列号（序列无关 NAT），导致连接失败

> 相关阅读：《../../02-网络协议与报文解析/04-TCP报文与三次握手四次挥手深度剖析.md》（在 `../../02-网络协议与报文解析/`），TCP 同时打开的状态机细节是理解 TCP 打洞的基础。

实际生产中，TCP 打洞成功率低于 UDP，通常优先用 UDP，失败后回退到 TCP 中继。

### 3.3 中继转发（TURN）

当 P2P 直连失败（对称型 NAT、企业级防火墙、双重 NAT）时，使用 TURN（Traversal Using Relays around NAT，RFC 8656）中继：

```text
A ──→ TURN 服务器 ──→ B
     （分配中继端口，转发所有数据）
```

TURN 服务器为客户端分配一个公网中继地址，所有数据经由服务器转发。代价是服务器带宽成本，因此 ICE 总是**优先尝试直连，直连失败才用中继**。

---

## 4. 穿透的三种拓扑场景

| 场景 | A 位置 | B 位置 | 穿透策略 | 成功率 |
| --- | --- | --- | --- | --- |
| **双方都在公网** | 公网 | 公网 | 直接连接，无需穿透 | 100% |
| **一方在 NAT 后** | NAT 后 | 公网 | NAT 后的一方主动连接公网方（NAT 出站放行） | ~100% |
| **双方都在 NAT 后** | NAT 后 | NAT 后 | STUN 获取映射 → UDP/TCP 打洞 → 失败则 TURN 中继 | 60%~85%（取决于 NAT 类型） |

双方都在 NAT 后是最常见也最复杂的场景，需要完整的 ICE 流程。

---

## 5. STUN/TURN/ICE 协议族

ICE（Interactive Connectivity Establishment，RFC 8445）是整合 STUN 和 TURN 的框架，自动选择最优通信路径。

### 5.1 信令交换

ICE 本身不定义信令协议，依赖外部通道（WebSocket、HTTP、SIP 等）交换 SDP（Session Description Protocol）信息：

```text
A 收集候选地址 → 封装为 SDP offer → 信令服务器 → B
B 收集候选地址 → 封装为 SDP answer → 信令服务器 → A
```

SDP 中包含 `candidate` 属性，格式：
```text
a=candidate:1 1 udp 2113937151 192.168.1.100 54321 typ host
a=candidate:2 1 udp 1845501695 118.26.5.10 32100 typ srflx raddr 192.168.1.100 rport 54321
a=candidate:3 1 udp 41819902 118.26.5.10 60000 typ relay raddr 118.26.5.10 rport 32100
```

### 5.2 候选地址收集

ICE 为每个传输通道收集三类候选地址（Candidate）：

| 类型 | 标识 | 来源 | 优先级 |
| --- | --- | --- | --- |
| **主机候选（Host）** | `typ host` | 本机网卡的私网地址 | 最高 |
| **服务器反射候选（Srflx）** | `typ srflx` | STUN 服务器返回的公网映射地址 | 中 |
| **中继候选（Relay）** | `typ relay` | TURN 服务器分配的中继地址 | 最低 |

优先级公式（RFC 8445）：
```
priority = (2^24)*(type_preference) + (2^8)*(local_preference) + (256 - component_id)
```
类型偏好：host=126，srflx=100，relay=0。

### 5.3 连通性检查（Connectivity Check）

双方交换候选地址后，ICE 按优先级从高到低配对候选地址，发送 STUN Binding Request 做连通性检查：

```text
候选对（Candidate Pair）排序：
  (A_host, B_host) → (A_host, B_srflx) → (A_srflx, B_host)
    → (A_srflx, B_srflx) → ... → (A_relay, B_relay)

对每个候选对：
  1. 发送 STUN Binding Request（带 USE-CANDIDATE 属性标记选中）
  2. 收到 Binding Response → 连通性检查成功
  3. 第一个成功的候选对被选为有效路径（Nominated Pair）
  4. 继续检查更高优先级的候选对（可能找到更优路径）
```

ICE 还支持 **Trickle ICE**（涓流 ICE）：边收集候选边发送，无需等待全部收集完成，加速连接建立。

---

## 6. 典型 P2P 框架实现思路

### BT（BitTorrent）

- 使用 **DHT（分布式哈希表）** 替代中心化 tracker 发现节点
- 通过 **PEX（Peer Exchange）** 在已连接节点间交换邻居信息
- 支持 **uTP（micro Transport Protocol）**：基于 UDP 的可靠传输，具备 LEDBAT 拥塞控制，避免抢占带宽
- NAT 穿透通过 tracker 交换 peer 地址，UDP 打洞；失败则依赖其他 peer 中继

### 快播（Qvod）

- 混合 P2P-CDN 架构：热门资源走 CDN，长尾资源走 P2P
- 自定义 P2P 协议，基于 UDP 打洞 + 数据分片
- 节点缓存已下载数据，作为上传源贡献带宽
- 超级节点（Super Node）辅助 NAT 穿透和数据调度

### WebRTC

- 标准化 ICE + STUN + TURN 协议栈
- 浏览器内置，信令由应用层自定义
- 支持 SRTP 加密、DTLS 握手
- 是目前最成熟的 P2P 音视频通信方案

### 自研 P2P 框架核心模块

```text
┌─────────────────────────────────────────────┐
│              应用层（业务逻辑）               │
├─────────────────────────────────────────────┤
│  可靠传输层（UDT/KCP/QUIC，基于UDP的可靠传输）│
├─────────────────────────────────────────────┤
│  ICE 连接管理层（候选收集/连通性检查/路径选择） │
├─────────────────────────────────────────────┤
│  STUN 客户端 │ TURN 客户端 │ NAT 类型检测     │
├─────────────────────────────────────────────┤
│  信令层（WebSocket/HTTP，交换候选地址）       │
├─────────────────────────────────────────────┤
│              UDP/TCP Socket                 │
└─────────────────────────────────────────────┘
```

---

## 7. 代码实现

### 7.1 NAT 类型检测

```cpp
#include <iostream>
#include <string>
#include <cstring>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>

// STUN Binding Request 构造（简化版，仅核心字段）
struct StunMessage {
    uint16_t type;
    uint16_t length;
    uint32_t magic_cookie;
    uint8_t  transaction_id[12];
};

// 向 STUN 服务器发送 Binding Request，返回映射的公网地址
bool stunBindingRequest(const std::string& server_ip, uint16_t server_port,
                        int sock, std::string& mapped_ip, uint16_t& mapped_port) {
    StunMessage req = {};
    req.type = htons(0x0001);  // Binding Request
    req.length = 0;
    req.magic_cookie = htonl(0x2112A442);
    // 填充随机 transaction_id
    for (int i = 0; i < 12; ++i) req.transaction_id[i] = rand() % 256;

    sockaddr_in server = {};
    server.sin_family = AF_INET;
    server.sin_port = htons(server_port);
    inet_pton(AF_INET, server_ip.c_str(), &server.sin_addr);

    sendto(sock, &req, sizeof(req), 0, (sockaddr*)&server, sizeof(server));

    // 接收响应（实际应处理重传和超时）
    uint8_t buf[1024];
    sockaddr_in from;
    socklen_t fromlen = sizeof(from);
    ssize_t n = recvfrom(sock, buf, sizeof(buf), 0, (sockaddr*)&from, &fromlen);
    if (n < 20) return false;

    // 解析 XOR-MAPPED-ADDRESS 属性（简化：跳过属性头解析）
    // 实际实现需遍历 TLV 属性找到 0x0020 类型
    // 此处仅演示框架
    return true;
}

int main() {
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    // 绑定到固定端口（便于检测映射是否变化）
    sockaddr_in local = {};
    local.sin_family = AF_INET;
    local.sin_port = htons(54321);
    bind(sock, (sockaddr*)&local, sizeof(local));

    std::string mapped_ip;
    uint16_t mapped_port;
    // 向公共 STUN 服务器查询
    if (stunBindingRequest("stun.l.google.com", 19302, sock, mapped_ip, mapped_port)) {
        std::cout << "公网映射地址: " << mapped_ip << ":" << mapped_port << std::endl;
    }
    close(sock);
    return 0;
}
```

### 7.2 UDP 打洞实现

```cpp
// 打洞客户端：通过信令获取对端公网地址后，持续发送打洞包
class HolePuncher {
public:
    HolePuncher(int local_port) : sock_fd_(-1) {
        sock_fd_ = socket(AF_INET, SOCK_DGRAM, 0);
        sockaddr_in local = {};
        local.sin_family = AF_INET;
        local.sin_addr.s_addr = htonl(INADDR_ANY);
        local.sin_port = htons(local_port);
        bind(sock_fd_, (sockaddr*)&local, sizeof(local));
    }

    // 设置对端公网地址（通过信令服务器交换得到）
    void setPeerAddress(const std::string& peer_ip, uint16_t peer_port) {
        peer_addr_.sin_family = AF_INET;
        peer_addr_.sin_port = htons(peer_port);
        inet_pton(AF_INET, peer_ip.c_str(), &peer_addr_.sin_addr);
    }

    // 发送打洞包：周期性向对端公网地址发送，直到收到回应
    void punch() {
        const char* punch_msg = "HOLE_PUNCH";
        // 快速发送多个打洞包（应对先发包被丢弃的情况）
        for (int i = 0; i < 10; ++i) {
            sendto(sock_fd_, punch_msg, strlen(punch_msg), 0,
                   (sockaddr*)&peer_addr_, sizeof(peer_addr_));
            usleep(100000);  // 100ms 间隔
        }
    }

    // 检查是否打洞成功（收到对端数据）
    bool waitForPeer(int timeout_sec = 5) {
        fd_set rfds;
        FD_ZERO(&rfds);
        FD_SET(sock_fd_, &rfds);
        timeval tv = {timeout_sec, 0};
        int ret = select(sock_fd_ + 1, &rfds, nullptr, nullptr, &tv);
        return ret > 0;
    }

    ~HolePuncher() { if (sock_fd_ >= 0) close(sock_fd_); }

private:
    int sock_fd_;
    sockaddr_in peer_addr_ = {};
};
```

---

## 8. 快速参考卡片

```text
NAT 类型对照：
  完全锥型    → 任意外部主机可回包，最易穿透
  IP限制锥型  → 仅曾通信过的外部IP可回包
  端口限制锥型→ 仅曾通信过的外部IP:端口可回包（最常见家用路由器）
  对称型      → 不同目标不同映射端口，极难穿透，需中继

穿透成功率（经验值）：
  锥型 NAT 间 UDP 打洞    → 80%~95%
  锥型 NAT 间 TCP 打洞    → 50%~70%
  含对称型 NAT 的 UDP 打洞 → 10%~30%
  含对称型 NAT 的 TCP 打洞 → <5%
  TURN 中继               → 100%（有带宽成本）

STUN/TURN/ICE 关系：
  STUN = 地址发现工具（我在公网的映射是什么？）
  TURN = 中继转发服务（直连不通时的保底通道）
  ICE  = 整合框架（收集候选→排序→连通性检查→选最优路径）

候选地址优先级：host(126) > srflx(100) > relay(0)
NAT 映射超时：UDP 通常 30s~5min，TCP 通常 2~4min，需心跳保活
```

## 9. 常见问题与坑

1. **NAT 映射超时导致连接中断**：UDP 映射通常 30s~5min 无流量就过期，必须定期发送心跳包（建议 15s 间隔）。
2. **对称型 NAT 打洞失败**：不要强行尝试，直接回退 TURN 中继；端口预测（猜测递增端口）成功率极低且不稳定。
3. **双重 NAT（运营商级 NAT + 家用 NAT）**：CGNAT 下用户共享公网 IP，STUN 只能看到运营商 NAT 的映射，打洞成功率大幅下降，需 TURN。
4. **TCP 打洞时 `SO_REUSEADDR` 不够**：Linux 需 `SO_REUSEPORT` 或先 bind 再 connect；Windows 需设置 `SO_REUSEADDR` 并使用 `WSAConnect`。
5. **信令交换延迟导致打洞窗口错过**：候选地址有时效性，信令延迟过大会导致映射已过期，使用 Trickle ICE 边收集边交换。
6. **企业防火墙阻断 UDP**：企业网络常只放行 80/443 TCP，此时需 TURN over TCP/TLS（端口 443）伪装成 HTTPS 流量。
7. **STUN 服务器不可用**：公共 STUN 服务器不稳定，生产环境应自建 STUN/TURN 服务器（如 coturn）。
8. **IPv6 环境下 NAT 穿透不必要**：IPv6 端到端可达，无需 NAT 穿透，但需注意防火墙规则。
9. **打洞包被对端 NAT 丢弃是正常的**：先发方的包必然被丢弃（对方还没创建映射），但它在己方 NAT 上创建了规则，不要因第一个包没回应就判定失败。
10. **多网卡环境候选地址混乱**：主机候选可能包含虚拟网卡（VPN、Docker）地址，需过滤无效接口或设置 ICE 网络偏好。

---

上一篇：《03-Windows平台开发.md》
下一篇：《05-frp内网穿透.md》
