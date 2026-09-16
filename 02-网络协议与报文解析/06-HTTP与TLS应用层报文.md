# HTTP / HTTPS / TLS 与 WebSocket 应用层报文

> 本节目标：看懂 HTTP 请求/响应的**文本报文**结构、连接复用与分块传输，理解 HTTPS/TLS 握手在抓包里长什么样，以及 WebSocket 如何从 HTTP 升级。给 C++ 后端写管理接口、对接云平台、排查"为什么慢"都要用。加密细节见《../01-C++技术体系/03-网络编程/03-网络安全与加密编程.md》。

## 本章速览

- [1. HTTP 报文结构（纯文本，抓包直接可读）](#1-http-报文结构纯文本抓包直接可读)
  - [1.1 请求报文](#11-请求报文)
  - [1.2 响应报文](#12-响应报文)
  - [1.3 方法与状态码（高频）](#13-方法与状态码高频)
- [2. 连接复用、长度与分块（手写 HTTP 解析必懂）](#2-连接复用长度与分块手写-http-解析必懂)
- [3. 常见头部与缓存](#3-常见头部与缓存)
- [4. HTTPS = HTTP over TLS（抓包看握手）](#4-https--http-over-tls抓包看握手)
  - [4.1 TLS 1.2 握手（RSA 密钥交换，便于理解）](#41-tls-12-握手rsa-密钥交换便于理解)
  - [4.2 抓包与排查](#42-抓包与排查)
- [5. WebSocket：从 HTTP 升级成长连接全双工](#5-websocket从-http-升级成长连接全双工)
- [6. 快速参考卡片](#6-快速参考卡片)
- [7. 常见问题与坑](#7-常见问题与坑)
- [8. 延伸阅读](#8-延伸阅读)

---

## 1. HTTP 报文结构（纯文本，抓包直接可读）

### 1.1 请求报文

```http
POST /api/devices HTTP/1.1\r\n          请求行：方法 路径 版本
Host: 192.168.1.10:8080\r\n             ← 以下都是头部
Content-Type: application/json\r\n
Content-Length: 31\r\n
Connection: keep-alive\r\n
\r\n                                    ← 空行(CRLFCRLF)分隔头与体
{"addr":1,"name":"gateway-a"}           ← 消息体
```

### 1.2 响应报文

```http
HTTP/1.1 200 OK\r\n                     状态行：版本 状态码 原因
Content-Type: application/json\r\n
Content-Length: 18\r\n
\r\n
{"ok":true,"n":12}
```

### 1.3 方法与状态码（高频）

| 方法 | 语义 | 幂等 |
| --- | --- | --- |
| GET 取 / POST 增 / PUT 整体改 / PATCH 局部改 / DELETE 删 / HEAD 只要头 / OPTIONS 预检 | | GET/PUT/DELETE 幂等，POST 不幂等 |

| 状态码 | 类别/常见 |
| --- | --- |
| 2xx | 200 OK、201 Created、204 No Content |
| 3xx | 301/302 重定向、304 Not Modified（协商缓存命中） |
| 4xx | 400 参数错、401 未认证、403 无权限、404、405 方法不允许、408 超时、429 限流 |
| 5xx | 500 内部错、502 网关错、503 不可用、504 网关超时 |

## 2. 连接复用、长度与分块（手写 HTTP 解析必懂）

HTTP/1.1 默认 `Connection: keep-alive`，一条 TCP 连接承载多个请求/响应，于是必须知道"一个响应到哪里结束"，否则会和下一个响应粘在一起：

| 定界方式 | 说明 |
| --- | --- |
| **Content-Length** | 明确体长度，读到这么多字节即完整 |
| **Transfer-Encoding: chunked** | 分块：每块 `十六进制长度\r\n数据\r\n`，以 `0\r\n\r\n` 结束，用于边生成边发、事先不知道总长 |
| 连接关闭 | 老 HTTP/1.0 靠关闭连接界定（已淘汰） |

```text
chunked 编码示例：
1a\r\n            ← 本块长度 0x1a=26 字节
<26字节数据>\r\n
b\r\n             ← 下一块 11 字节
<11字节>\r\n
0\r\n\r\n          ← 结束块
```

- 手写解析器要先解析头部（遇到 `\r\n\r\n`），再按 Content-Length 或 chunked 读体——这本质也是**应用层分帧**，与处理 Modbus/IEC104 半包是同一类问题（见 07 篇）；
- **管线化(pipelining)** 允许连续发请求但响应必须按序，实践被 HTTP/2 多路复用取代；
- HTTP/2 改为**二进制分帧**、单连接多流、头部压缩 HPACK；HTTP/3 基于 QUIC(UDP)。知道演进即可。

## 3. 常见头部与缓存

| 头部 | 作用 |
| --- | --- |
| Host | 虚拟主机区分（HTTP/1.1 必带） |
| Content-Type | 体类型（application/json、x-www-form-urlencoded、multipart/form-data） |
| Content-Length / Transfer-Encoding | 体定界 |
| Authorization | 认证（Bearer token / Basic） |
| Cookie / Set-Cookie | 会话 |
| Cache-Control / ETag / If-None-Match | 缓存与 304 |
| Accept-Encoding / Content-Encoding | gzip 压缩 |
| Upgrade / Connection: Upgrade | 协议升级（WebSocket） |

## 4. HTTPS = HTTP over TLS（抓包看握手）

明文 HTTP 直接跑在 TCP 上；HTTPS 是**先在 TCP 三次握手之上做 TLS 握手协商密钥，之后 HTTP 数据被对称加密**。

### 4.1 TLS 1.2 握手（RSA 密钥交换，便于理解）

```text
客户端                                  服务端
 TCP 三次握手完成后：
 ① ClientHello        ──→   支持的TLS版本、随机数C、密码套件列表、SNI(要访问的域名)
 ② ServerHello+证书   ←──   选定套件、随机数S、服务器证书(含公钥,由CA签名)
   （可选 CertificateRequest 要求客户端证书）
 ③ 密钥协商/PreMaster ──→   用证书公钥加密预主密钥(RSA) 或 ECDHE 交换参数
 ④ 双方由 随机数C+S+预主密钥 算出相同会话密钥
 ⑤ ChangeCipherSpec + Finished（双向，此后对称加密）
 之后 HTTP 数据全部加密传输
```

- **非对称加密**（RSA/ECDHE）只用于**身份认证和协商出对称密钥**，批量数据用**对称加密**（AES-GCM 等），兼顾安全与性能；
- 证书链：服务器证书 ← 中间 CA ← 根 CA，客户端用内置根证书验签；
- **ECDHE 提供前向保密(PFS)**：即使以后服务器私钥泄露也解不开历史会话，现代优先；
- **TLS 1.3（RFC 8446）** 把握手压缩到 **1-RTT**、删掉老旧套件，流程更简、更安全（见《../01-C++技术体系/03-网络编程/03-网络安全与加密编程.md》）。

### 4.2 抓包与排查

- tcpdump/Wireshark 看到的 HTTPS 是加密乱码；调试可用 `SSLKEYLOGFILE` 导出会话密钥让 Wireshark 解密，或在测试环境用中间人代理（mitmproxy，需信任其根证书，仅限授权测试）；
- `openssl s_client -connect host:443 -tls1_2 -showcerts` 看证书链与协商套件；
- 常见：证书过期/域名不匹配/客户端不信任根 CA/套件不匹配导致握手失败；电力专用网络还可能用**国密 TLS（SM2/SM3/SM4）**。

## 5. WebSocket：从 HTTP 升级成长连接全双工

适合服务端主动推送（实时数据、告警）。建立时借用 HTTP：

```http
GET /ws HTTP/1.1
Host: x
Upgrade: websocket            ← 请求升级
Connection: Upgrade
Sec-WebSocket-Key: <随机base64>
Sec-WebSocket-Version: 13

--- 服务端同意 ---
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: <按规则算出的应答>
```

101 之后连接**不再是 HTTP**，变为 WebSocket 二进制/文本帧双向通信（帧带 opcode、掩码、payload length）。它跑在 TCP 上、兼容 80/443，比原生 TCP 易穿透防火墙，但工业设备间采集仍多用 TCP 规约。

## 6. 快速参考卡片

```text
HTTP：请求行/状态行 + 头部(\r\n) + 空行 + 体；keep-alive靠 CL 或 chunked 定界
状态码：2成功 3重定向/缓存 4客户端错 5服务端错
chunked：每块 十六进制长度\r\n数据\r\n，0\r\n\r\n结束
HTTPS：TCP握手后TLS握手(非对称协商密钥→对称加密数据)；证书链验身份；ECDHE前向保密
TLS1.3=1-RTT更安全；解密抓包用SSLKEYLOGFILE/授权代理
WebSocket：HTTP Upgrade→101后变全双工帧
```

## 7. 常见问题与坑

| 问题 | 说明/解决 |
| --- | --- |
| keep-alive 下响应和下一个粘在一起 | 必须按 Content-Length/chunked 精确切分，不能按 recv 次数 |
| 不知道响应体何时读完 | 解析头部定界规则；chunked 找结束块 |
| HTTPS 抓包全是密文 | 正常；用 SSLKEYLOGFILE 或测试代理，勿在生产非法中间人 |
| 握手报证书错误 | 过期/域名不符/缺中间证书/客户端不信任根 CA |
| POST 中文乱码 | 统一 UTF-8，正确设 Content-Type 与 charset |
| HTTP/1.1 高并发队头阻塞 | 多连接或升级 HTTP/2 多路复用 |
| 把 WebSocket 当 HTTP 轮询 | 升级后是独立帧协议，服务端可主动推 |

## 8. 延伸阅读

- HTTP 语义 RFC 9110；HTTP/1.1 RFC 9112；TLS 1.3 RFC 8446、TLS 1.2 RFC 5246；WebSocket RFC 6455
- MDN HTTP 参考：[developer.mozilla.org/zh-CN/docs/Web/HTTP](https://developer.mozilla.org/zh-CN/docs/Web/HTTP)
- OpenSSL s_client：[docs.openssl.org](https://docs.openssl.org/)；本库《../01-C++技术体系/03-网络编程/03-网络安全与加密编程.md》
- 下一篇（工业规约重点）《07-Modbus与IEC104工业报文解析.md》

---

上一篇：《05-UDP-DNS-DHCP报文.md》　｜　下一篇：《07-Modbus与IEC104工业报文解析.md》　｜　模块索引：《README.md》
