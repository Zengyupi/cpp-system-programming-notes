# gRPC与RPC框架原理

> 本节目标：从原理到实践掌握 RPC 框架——理解 Client/Server/Channel/Service/Stub 五大核心概念与一次 RPC 调用的完整链路，掌握 HTTP/2 协议的帧、流、多路复用与 HPACK 头部压缩，能用 protobuf 的 service/rpc 定义四种调用模型（unary/server streaming/client streaming/bidi streaming），理解 gRPC 内部 CompletionQueue 异步模型与回调机制，掌握服务注册发现（etcd/Consul）与客户端负载均衡，对比自研 RPC（zrpc/NtyCo 风格）在协议设计、序列化、内存池上的差异，理解 interceptor 拦截器、deadline 超时与重试机制。序列化基础见《../05-存储与序列化/03-Protobuf序列化协议.md》，网络底层见《01-网络基础与TCP-IP.md》。

## 本章速览

- [1. RPC 原理](#1-rpc-原理)
  - [1.1 五大核心概念](#11-五大核心概念)
  - [1.2 一次 RPC 调用的完整链路](#12-一次-rpc-调用的完整链路)
  - [1.3 RPC vs REST 对比](#13-rpc-vs-rest-对比)
- [2. HTTP/2 协议基础](#2-http2-协议基础)
  - [2.1 帧（Frame）](#21-帧frame)
  - [2.2 流（Stream）与多路复用](#22-流stream与多路复用)
  - [2.3 HPACK 头部压缩](#23-hpack-头部压缩)
  - [2.4 流控与优先级](#24-流控与优先级)
- [3. protobuf 服务定义](#3-protobuf-服务定义)
  - [3.1 service/rpc 关键字](#31-servicerpc-关键字)
  - [3.2 四种调用模型](#32-四种调用模型)
- [4. gRPC 内部组件](#4-grpc-内部组件)
  - [4.1 CompletionQueue 异步模型](#41-completionqueue-异步模型)
  - [4.2 同步 vs 异步 vs 回调](#42-同步-vs-异步-vs-回调)
  - [4.3 线程模型与连接管理](#43-线程模型与连接管理)
- [5. 服务注册与发现](#5-服务注册与发现)
  - [5.1 注册中心选型](#51-注册中心选型)
  - [5.2 etcd 集成方案](#52-etcd-集成方案)
  - [5.3 客户端负载均衡](#53-客户端负载均衡)
- [6. 与自研 RPC 对照](#6-与自研-rpc-对照)
  - [6.1 协议设计对比](#61-协议设计对比)
  - [6.2 序列化与内存池](#62-序列化与内存池)
- [7. interceptor 与超时重试](#7-interceptor-与超时重试)
  - [7.1 拦截器机制](#71-拦截器机制)
  - [7.2 deadline 与超时](#72-deadline-与超时)
  - [7.3 重试策略](#73-重试策略)
- [8. 快速参考卡片](#8-快速参考卡片)

---

## 1. RPC 原理

### 1.1 五大核心概念

| 概念 | 角色 | 说明 |
|---|---|---|
| **Client** | 调用方 | 发起 RPC 请求的进程 |
| **Server** | 被调用方 | 提供 RPC 服务的进程，注册 Service 实现 |
| **Channel** | 通信通道 | 客户端到服务端的 HTTP/2 连接抽象，一个 Channel 可承载多个并发调用 |
| **Service** | 服务定义 | `.proto` 中 `service` 声明的一组方法，对应服务端一个实现类 |
| **Stub** | 存根 | 客户端代理对象，封装序列化/网络/反序列化，使远程调用看起来像本地函数调用 |

```text
客户端视角：
  业务代码 → Stub.SayHello(req)
              ├─ 序列化 req → 二进制
              ├─ 通过 Channel 发送 HTTP/2 请求
              ├─ 等待响应
              └─ 反序列化响应 → 返回给业务代码

服务端视角：
  收到 HTTP/2 请求 → 反序列化 → 路由到 Service 实现
    → 业务逻辑处理 → 序列化响应 → HTTP/2 回传
```

### 1.2 一次 RPC 调用的完整链路

```text
Client                                    Server
  │                                         │
  │ 1. Stub 调用 SayHello(req)              │
  │ 2. protobuf 序列化 req → bytes          │
  │ 3. 封装 HTTP/2 HEADERS + DATA 帧        │
  │ 4. 通过 Channel (TCP+TLS) 发送 ────────►│
  │                                         │ 5. 解帧、HPACK 解压头
  │                                         │ 6. 路由 :path → Service/Method
  │                                         │ 7. protobuf 反序列化 → req
  │                                         │ 8. 调用 Service 实现
  │                                         │ 9. 序列化 resp → bytes
  │ 10. 收到 HTTP/2 响应帧 ◄────────────────│ 10. 封装响应帧发送
  │ 11. 反序列化 → resp                     │
  │ 12. 返回给业务代码                      │
```

### 1.3 RPC vs REST 对比

| 维度 | gRPC (RPC) | REST (HTTP/1.1+JSON) |
|---|---|---|
| 传输协议 | HTTP/2（二进制帧） | HTTP/1.1（文本） |
| 序列化 | Protobuf（二进制、紧凑） | JSON（文本、冗余） |
| 接口定义 | `.proto`（强类型、代码生成） | 无强制（OpenAPI 可选） |
| 多路复用 | 单连接多流并发 | 需多连接（HTTP/1.1 队头阻塞） |
| 流式调用 | 四种模型原生支持 | 需 SSE/WebSocket  hack |
| 性能 | 高（序列化快、头部压缩、二进制） | 较低（JSON 解析慢、头部冗余） |
| 浏览器支持 | 需 gRPC-Web 代理 | 原生支持 |
| 调试 | 需 grpcurl/evans | curl/Postman 直接 |
| 适用 | 微服务内部高性能通信 | 对外 API、浏览器端 |

---

## 2. HTTP/2 协议基础

### 2.1 帧（Frame）

HTTP/2 是**二进制分帧协议**，所有消息拆成帧传输。帧头固定 9 字节：

```text
帧格式（RFC 7540）：
+-----------------------------------------------+
|  Length (24)  |  Type (8)  |  Flags (8)  |
+-+-------------+  +---------------------------+
|R|  Stream Identifier (31)                     |
+=+=============================================+
|  Frame Payload (0...)                         |
+-----------------------------------------------+
```

| 字段 | 长度 | 说明 |
|---|---|---|
| Length | 24 bit | payload 长度（最大 16384 字节，可协商） |
| Type | 8 bit | 帧类型 |
| Flags | 8 bit | 标志位（如 END_STREAM、END_HEADERS） |
| R | 1 bit | 保留位 |
| Stream ID | 31 bit | 流标识（0 表示连接级） |

**主要帧类型**：

| Type | 名称 | 作用 |
|---|---|---|
| 0x0 | DATA | 消息体（请求/响应数据） |
| 0x1 | HEADERS | 头部块（含 :method/:path/:status 等伪头） |
| 0x2 | PRIORITY | 流优先级 |
| 0x3 | RST_STREAM | 重置流 |
| 0x4 | SETTINGS | 连接参数协商 |
| 0x5 | PUSH_PROMISE | 服务器推送 |
| 0x6 | PING | 心跳/RTT 测量 |
| 0x7 | GOAWAY | 优雅关闭连接 |
| 0x8 | WINDOW_UPDATE | 流控窗口更新 |
| 0x9 | CONTINUATION | 头部块续传 |

### 2.2 流（Stream）与多路复用

**流（Stream）**：连接内一个双向的虚拟字节流，承载一次完整的请求-响应交换。流 ID 由客户端发起为奇数，服务端发起为偶数。

```text
单个 TCP 连接上的多路复用：
  Stream 1 (奇数, 客户端发起) ── 请求 A ──► 响应 A
  Stream 3 (奇数, 客户端发起) ── 请求 B ──► 响应 B
  Stream 5 (奇数, 客户端发起) ── 请求 C ──► 响应 C
  所有流的帧交错传输，互不阻塞
```

**关键优势**：
- HTTP/1.1 队头阻塞：一个请求的响应没回来，同连接后续请求必须等
- HTTP/2：帧交错，Stream 3 的响应可以在 Stream 1 响应中间穿插
- 一个连接承载所有并发 RPC 调用，减少 TCP 握手和 TLS 握手开销

**gRPC 中的流**：每个 RPC 调用对应一个 HTTP/2 Stream，stream ID 在 Channel 内递增。

### 2.3 HPACK 头部压缩

HTTP/1.x 头部是纯文本，每次请求重复发送大量相同头（Cookie/User-Agent 等）。HTTP/2 用 **HPACK**（RFC 7541）压缩：

1. **静态表**：预定义 61 个常见头（`:method GET`、`:path /`、`content-type` 等），用索引号代替
2. **动态表**：连接级 LRU 缓存，首次发送的头存入表，后续用索引号引用
3. **Huffman 编码**：对字面量值用 Huffman 编码进一步压缩

```text
首次请求：
  :method POST (静态表索引 3 → 只需发索引)
  :path /helloworld.Greeter/SayHello (动态表新增，后续发索引)
  content-type application/grpc (静态表索引)
  te trailers (静态表索引)

后续请求：
  大部分头只需 1~2 字节索引，头部从几百字节降到几字节
```

gRPC 关键伪头：
- `:method` = POST
- `:scheme` = http/https
- `:path` = /{service}/{method}（如 `/helloworld.Greeter/SayHello`）
- `:authority` = 目标主机
- `content-type` = application/grpc（或 application/grpc+proto）
- `te` = trailers（gRPC 用 HTTP/2 trailer 传状态码）

### 2.4 流控与优先级

- **流控**：基于 WINDOW_UPDATE 帧的滑动窗口，接收方控制发送方速率，防止快发送方压垮慢接收方。初始窗口 65535 字节，可通过 SETTINGS 调大。
- **优先级**：PRIORITY 帧指定流的依赖树和权重，服务端按优先级分配资源（gRPC 较少使用）。

---

## 3. protobuf 服务定义

### 3.1 service/rpc 关键字

`.proto` 文件中用 `service` 定义服务，`rpc` 定义方法：

```protobuf
syntax = "proto3";

package helloworld;

option cc_generic_services = false;  // gRPC C++ 用代码生成的 stub，不用 generic service

// 请求/响应消息
message HelloRequest {
    string name = 1;
}
message HelloReply {
    string message = 1;
}

// 服务定义
service Greeter {
    // 一元调用：一个请求 → 一个响应
    rpc SayHello (HelloRequest) returns (HelloReply);
}
```

`protoc` + `grpc_cpp_plugin` 生成：
- `helloworld.pb.h/cc`：消息序列化代码
- `helloworld.grpc.pb.h/cc`：Service 基类（服务端继承）、Stub 类（客户端使用）

### 3.2 四种调用模型

```protobuf
service StreamService {
    // ① Unary：一元调用（1 请求 → 1 响应）
    rpc UnaryCall (Request) returns (Response);

    // ② Server Streaming：服务端流式（1 请求 → N 响应）
    rpc ServerStream (Request) returns (stream Response);

    // ③ Client Streaming：客户端流式（N 请求 → 1 响应）
    rpc ClientStream (stream Request) returns (Response);

    // ④ Bidi Streaming：双向流式（N 请求 → N 响应，全双工）
    rpc BidiStream (stream Request) returns (stream Response);
}
```

| 模型 | 请求 | 响应 | 典型场景 |
|---|---|---|---|
| Unary | 1 | 1 | 普通 RPC 调用（增删改查） |
| Server Streaming | 1 | N | 订阅推送、日志流、行情推送 |
| Client Streaming | N | 1 | 大文件上传、批量数据上报 |
| Bidi Streaming | N | N | 聊天、实时协作、游戏状态同步 |

**C++ 四种模型调用示例**：

```cpp
// ① Unary
HelloReply reply;
ClientContext ctx;
Status status = stub->SayHello(&ctx, request, &reply);

// ② Server Streaming
ClientContext ctx;
auto reader = stub->ServerStream(&ctx, request);
HelloReply reply;
while (reader->Read(&reply)) {
    // 处理每个响应
}
Status status = reader->Finish();

// ③ Client Streaming
ClientContext ctx;
HelloReply reply;
auto writer = stub->ClientStream(&ctx, &reply);
for (auto& req : requests) {
    writer->Write(req);
}
writer->WritesDone();
Status status = writer->Finish();

// ④ Bidi Streaming
ClientContext ctx;
auto stream = stub->BidiStream(&ctx);
// 写线程
std::thread writer([&]() {
    for (auto& req : requests) stream->Write(req);
    stream->WritesDone();
});
// 读线程
HelloReply reply;
while (stream->Read(&reply)) {
    // 处理响应
}
writer.join();
Status status = stream->Finish();
```

---

## 4. gRPC 内部组件

### 4.1 CompletionQueue 异步模型

gRPC C++ 的异步核心是 **CompletionQueue（CQ）**——一个事件队列，所有异步操作的完成事件都入队。

```text
异步调用流程：
  1. stub->AsyncSayHello(&ctx, request, &cq, tag)  → 发起调用，立即返回
  2. 内部将请求序列化、通过 HTTP/2 发送
  3. 响应到达后，将 (tag, ok) 放入 CompletionQueue
  4. 业务线程 cq.Next(&tag, &ok) 取出完成事件
  5. 通过 tag 找到对应的 ResponseReader，调用 Finish 取结果
```

```cpp
// 异步客户端核心模式
CompletionQueue cq;
Greeter::Stub stub(channel);

// 发起异步调用
ClientContext ctx;
HelloRequest req;
HelloReply reply;
Status status;
auto rpc = stub->AsyncSayHello(&ctx, req, &cq);
rpc->Finish(&reply, &status, (void*)1);  // tag=(void*)1

// 事件循环（通常单独线程）
void* tag;
bool ok;
while (cq.Next(&tag, &ok)) {
    if (tag == (void*)1 && ok) {
        // 调用完成，reply 和 status 已填充
        std::cout << reply.message() << std::endl;
    }
}
```

**异步服务端**：基于 `ServerCompletionQueue` + `CallData` 状态机，每个请求一个 CallData 对象，状态为 CREATE/READ/PROCESS/FINISH。

### 4.2 同步 vs 异步 vs 回调

| 模式 | API | 线程模型 | 适用场景 |
|---|---|---|---|
| 同步 | `stub->SayHello(&ctx, req, &reply)` | 调用线程阻塞等待 | 简单业务、线程池足够 |
| 异步 | `AsyncSayHello` + CompletionQueue | 非阻塞，事件循环驱动 | 高并发、连接数多 |
| 回调（实验性） | `stub->async()->SayHello(&ctx, req, reply, callback)` | 回调在 CQ 线程执行 | 避免手动管理 CQ |

**gRPC 内部线程**：
- 每个 Channel 有一个或多个 **polling thread**（epoll 线程），负责 IO
- CompletionQueue 由用户线程驱动 `cq.Next()`
- 异步服务端通常用 `grpc::ServerBuilder::AddCompletionQueue` + 多线程 `cq.Next()`

### 4.3 线程模型与连接管理

```text
gRPC C++ 线程模型：
  业务线程池（调用 stub / 处理 Service）
       │
       ▼
  CompletionQueue（用户驱动 Next）
       │
       ▼
  gRPC core（C core）
    ├─ polling engine（epoll，1~N 个线程，由 GRPC_ENABLE_FORK_SUPPORT 等控制）
    ├─ TCP 连接池（一个 Channel 到一个后端通常 1 个 HTTP/2 连接）
    └─ timer（超时管理）
```

- **Channel 连接**：一个 Channel 对应一个目标地址，内部维护一个 HTTP/2 连接（断线自动重连，指数退避）
- **多路复用**：所有 RPC 调用共享这一个连接的多个 Stream
- **NameResolver**：Channel 创建时解析目标地址（DNS、unix、或自定义 resolver）
- **LoadBalancingPolicy**：多后端时选择哪个后端建立连接（pick_first/round_robin/自定义）

---

## 5. 服务注册与发现

### 5.1 注册中心选型

| 注册中心 | 一致性 | 健康检查 | 主流生态 | 适用 |
|---|---|---|---|---|
| etcd | CP (Raft) | 租约（lease）心跳 | Kubernetes、Go 生态 | 云原生、强一致 |
| Consul | CP (Raft) | 主动/被动检查 | HashiCorp 生态、多数据中心 | 多机房、服务网格 |
| ZooKeeper | CP (ZAB) | 临时节点心跳 | Java 生态（Dubbo） | 传统 Java 微服务 |
| Eureka | AP | 客户端心跳 | Spring Cloud | 容忍网络分区、注册量大 |
| Nacos | AP/CP 可切换 | 心跳 | 阿里生态 | 国内微服务主流 |

gRPC 官方不内置注册中心，需通过 **自定义 NameResolver** 集成。

### 5.2 etcd 集成方案

```text
服务端启动：
  1. 连接 etcd
  2. 创建租约 lease (TTL=5s)
  3. put key="/services/MyService/10.0.0.1:50051" value=addr, 绑定 lease
  4. 启动 goroutine/线程定时 KeepAlive 续租

客户端：
  1. 自定义 NameResolver，watch /services/MyService/ 前缀
  2. 初始获取所有实例，后续 watch 变更（PUT/DELETE）
  3. 变更时调用 resolver.StateChanged() 通知 Channel 更新地址列表
  4. LoadBalancingPolicy（round_robin）从地址列表选后端
```

```cpp
// 自定义 NameResolver 骨架（gRPC C++）
class EtcdResolver : public grpc::internal::DNSResolver {
public:
    void Start() override {
        // 从 etcd 获取服务实例列表
        // watch 前缀，变更时调用 SetStateAndUpdateLocked()
    }
};
```

### 5.3 客户端负载均衡

gRPC 内置两种 LB 策略：
- **pick_first**（默认）：选第一个可用地址，失败尝试下一个，所有 RPC 走同一连接
- **round_robin**：轮询所有可用地址，每个 RPC 选不同后端

```cpp
// 启用 round_robin
grpc::ChannelArguments args;
args.SetLoadBalancingPolicyName("round_robin");
auto channel = grpc::CreateCustomChannel(
    "etcd:///services/MyService",  // 自定义 scheme
    grpc::InsecureChannelCredentials(), args);
```

**自定义 LB 策略**：继承 `grpc::LoadBalancingPolicy`，实现 `UpdateLocked`/`Pick`/`ResetBackoff`，可实现加权轮询、一致性哈希、最少连接等。

---

## 6. 与自研 RPC 对照

### 6.1 协议设计对比

| 维度 | gRPC | 自研 RPC（zrpc/NtyCo 风格） |
|---|---|---|
| 传输层 | HTTP/2（标准、通用） | 私有 TCP 协议（精简、可控） |
| 协议头 | HTTP/2 帧头 9 字节 + HPACK 头 | 自定义固定头（如 16 字节：magic+version+cmd+seq+len） |
| 序列化 | Protobuf（标准、跨语言） | Protobuf/自研二进制/JSON |
| 多路复用 | HTTP/2 Stream（标准） | 自实现：连接上按 seq 分发响应 |
| 流式 | 四种模型原生 | 需自实现（长连接 + 消息推送） |
| 兼容性 | 强（标准协议，跨语言互通） | 弱（仅内部使用） |
| 协议开销 | HTTP/2 帧头 + HPACK（较小） | 可做到极致精简（固定头 8~16 字节） |

**自研 RPC 典型协议头**（zrpc 风格）：

```text
+----------+----------+----------+----------+
|  magic   | version  |   cmd    |  status  |   4B
+----------+----------+----------+----------+
|              sequence (4B)                  |   4B
+----------+----------+----------+----------+
|              body_len (4B)                  |   4B
+----------+----------+----------+----------+
|              request_id (8B)                |   8B
+---------------------------------------------+
|              body (protobuf)                |
+---------------------------------------------+
```

自研优势：协议头可精简到 16~20 字节，无 HTTP/2 的 SETTINGS/PING/HEADERS 等控制帧开销；seq 字段直接实现请求-响应匹配，无需 Stream ID。

### 6.2 序列化与内存池

| 维度 | gRPC | 自研 RPC |
|---|---|---|
| 序列化 | Protobuf（每次调用 new 消息对象，堆分配） | Protobuf + 对象池/内存池，复用消息对象 |
| 缓冲区 | gRPC core 内部管理（slice 引用计数） | RingBuffer/ChainBuffer，零拷贝 |
| 连接管理 | HTTP/2 连接 + 自动重连 | 自实现连接池 + 心跳检测 |
| 内存分配 | 每请求多次 malloc（消息对象、序列化 buffer） | 内存池预分配，O(1) 取用 |
| 零拷贝 | 有限（Protobuf 序列化需拷贝到 slice） | sendfile/writev 分散写，用户态零拷贝 |

**自研 RPC 性能优化点**：
1. 消息对象池：`MessagePool<HelloRequest>`，调用前从池取，用完归还，避免 malloc
2. 内存池：每个连接一个 `MemoryPool`，序列化 buffer 从池分配
3. RingBuffer：收发缓冲区用环形缓冲区，减少拷贝
4. 批量发送：攒批 writev，减少系统调用

---

## 7. interceptor 与超时重试

### 7.1 拦截器机制

gRPC 拦截器（Interceptor）在 RPC 调用前后插入逻辑，类似 AOP。C++ 支持：

**客户端拦截器**：`grpc::experimental::ClientInterceptorFactoryInterface`

```cpp
class LoggingInterceptor : public grpc::experimental::Interceptor {
public:
    void Intercept(grpc::experimental::InterceptorBatchMethods* methods) override {
        if (methods->QueryInterceptionHookPoint(
                grpc::experimental::InterceptionHookPoints::PRE_SEND_INITIAL_METADATA)) {
            // 调用前：记录方法名、注入 trace_id
            std::cout << "RPC start: " << methods->GetMethodName() << std::endl;
        }
        if (methods->QueryInterceptionHookPoint(
                grpc::experimental::InterceptionHookPoints::POST_RECV_STATUS)) {
            // 调用后：记录状态、耗时
            std::cout << "RPC end" << std::endl;
        }
        methods->Proceed();  // 继续下一个拦截器/实际调用
    }
};
```

**服务端拦截器**：`grpc::experimental::ServerInterceptorFactoryInterface`

**典型用途**：日志、监控（Prometheus）、链路追踪（OpenTelemetry）、鉴权、限流、重试、熔断。

### 7.2 deadline 与超时

gRPC 用 **deadline**（绝对时间点）而非 timeout（相对时长），deadline 会通过 HTTP/2 头 `grpc-timeout` 传递到服务端，全链路传播。

```cpp
// 客户端设置 deadline
ClientContext ctx;
ctx.set_deadline(std::chrono::system_clock::now() + std::chrono::seconds(5));
Status status = stub->SayHello(&ctx, req, &reply);
if (status.error_code() == grpc::DEADLINE_EXCEEDED) {
    // 超时处理
}

// 服务端检查剩余时间
if (context->IsCancelled()) {
    // 客户端已取消或超时，中止处理
    return Status(StatusCode::DEADLINE_EXCEEDED, "timeout");
}
```

`grpc-timeout` 头格式：`数字+单位`，如 `5S`（5秒）、`200m`（200毫秒）、`1H`（1小时）。单位：H/M/S/m/u/n。

**全链路超时传播**：A→B→C，A 设 10s，B 收到后剩余 8s，B 调 C 时传 8s，C 必须在 8s 内返回。避免下游已超时上游还在等。

### 7.3 重试策略

gRPC 支持**服务配置（Service Config）** 定义重试策略，通过 JSON 配置：

```json
{
    "methodConfig": [{
        "name": [{"service": "helloworld.Greeter"}],
        "timeout": "10s",
        "retryPolicy": {
            "maxAttempts": 3,
            "initialBackoff": "0.1s",
            "maxBackoff": "1s",
            "backoffMultiplier": 2,
            "retryableStatusCodes": ["UNAVAILABLE", "DEADLINE_EXCEEDED"]
        }
    }]
}
```

| 参数 | 说明 |
|---|---|
| maxAttempts | 最大尝试次数（含首次） |
| initialBackoff | 初始退避时间 |
| maxBackoff | 最大退避时间 |
| backoffMultiplier | 退避倍增系数 |
| retryableStatusCodes | 可重试的状态码（只对幂等方法重试！） |

**重要**：只对**幂等方法**启用重试。非幂等方法（如创建订单）重试会导致重复创建。

---

## 8. 快速参考卡片

### .proto 服务定义模板

```protobuf
syntax = "proto3";
package myservice;

option go_package = "github.com/xxx/myservice";
option java_package = "com.xxx.myservice";

message Request { string query = 1; }
message Response { string result = 1; }

service MyService {
    rpc Unary (Request) returns (Response);
    rpc ServerStream (Request) returns (stream Response);
    rpc ClientStream (stream Request) returns (Response);
    rpc BidiStream (stream Request) returns (stream Response);
}
```

### 四种调用模型 C++ 速查

```text
Unary:          stub->Method(&ctx, req, &resp) → Status
ServerStream:   stub->Method(&ctx, req) → reader; while(reader->Read(&resp)); reader->Finish()
ClientStream:   stub->Method(&ctx, &resp) → writer; writer->Write(req); writer->WritesDone(); writer->Finish()
BidiStream:     stub->Method(&ctx) → stream; stream->Write(req); stream->Read(&resp); stream->Finish()
```

### gRPC 状态码速查

| Code | 数值 | 含义 |
|---|---|---|
| OK | 0 | 成功 |
| CANCELLED | 1 | 调用被取消 |
| UNKNOWN | 2 | 未知错误 |
| INVALID_ARGUMENT | 3 | 参数无效 |
| DEADLINE_EXCEEDED | 4 | 超时 |
| NOT_FOUND | 5 | 资源不存在 |
| ALREADY_EXISTS | 6 | 资源已存在 |
| PERMISSION_DENIED | 7 | 权限不足 |
| UNAUTHENTICATED | 16 | 未认证 |
| UNAVAILABLE | 14 | 服务不可用（可重试） |
| INTERNAL | 13 | 内部错误 |

### 常见坑

1. **未设 deadline 导致调用永久挂起**：网络分区时 RPC 无超时，线程池被占满。每个调用必须设 deadline，默认 5~10s。
2. **对非幂等方法启用重试**：创建订单重试导致重复下单。重试策略只配在幂等方法（GET/查询/删除）上。
3. **Channel 频繁创建销毁**：Channel 是重量级对象（含连接池、线程），应全局单例复用。不要每次调用 new Channel。
4. **同步调用阻塞业务线程**：高并发下同步 stub 占满线程池。用异步（CompletionQueue）或协程封装。
5. **大消息超过默认 4MB 限制**：`GRPC_ARG_MAX_RECEIVE_MESSAGE_LENGTH` 默认 4MB，大文件传输报 RESOURCE_EXHAUSTED。调大或改用流式。
6. **服务端未处理 IsCancelled**：客户端超时后服务端仍在执行，浪费资源。长耗时操作中定期检查 `context->IsCancelled()`。
7. **HTTP/2 连接被中间件断开**：某些负载均衡器（AWS NLB 空闲超时 350s）断开空闲连接。开启 keepalive：`GRPC_ARG_KEEPALIVE_TIME_MS=30000`。
8. **proto3 字段默认值无法区分"未设置"和"设置为零值"**：proto3 标量字段无 presence，`int32 x=0` 无法判断是没传还是传了 0。用 `optional` 关键字（proto3.1+）或 wrapper 类型。
9. **拦截器中忘记调用 Proceed()**：拦截链中断，RPC 永远挂起。每个拦截路径必须调用 `methods->Proceed()`。
10. **误以为 gRPC 支持浏览器直接调用**：浏览器不支持 HTTP/2 trailer 和 gRPC 内容类型，需 gRPC-Web 代理（Envoy/grpc-web）。

---

上一篇：《05-Nginx深度：反向代理与模块开发.md》
下一篇：《07-ZeroMQ消息模式.md》
