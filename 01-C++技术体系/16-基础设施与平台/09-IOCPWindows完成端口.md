# IOCP Windows 完成端口

> 本节目标：讲解 Windows 异步 IO 模型的演进、IOCP（Input/Output Completion Port）的工作机制与核心 API，学完后能够理解 Proactor 与 Reactor 的区别、掌握 CreateIoCompletionPort/GetQueuedCompletionStatus 等核心 API、熟悉 Per-Handle Data/Per-I/O Data 设计模式、能够编写基于 IOCP 的高并发服务器骨架、理解 AcceptEx 预投递与线程池优化。对应岗位方向：Windows 服务器开发、游戏服务端、高性能网络代理、Windows 平台中间件、企业级后端服务。

> 代码来源：本文 IOCP 代码基于 Microsoft Win32 API（MSDN 官方文档），为 Windows 平台原生异步 IO 接口。

## 本章速览

- [1. Windows 异步 IO 模型演进](#1-windows-异步-io-模型演进)
- [2. IOCP 工作机制](#2-iocp-工作机制)
  - [2.1 完成端口对象](#21-完成端口对象)
  - [2.2 重叠 IO（OVERLAPPED）](#22-重叠-iooverlapped)
  - [2.3 完成队列](#23-完成队列)
- [3. 核心 API](#3-核心-api)
  - [3.1 CreateIoCompletionPort](#31-createiocompletionport)
  - [3.2 WSARecv / WSASend](#32-wsarecv--wsasend)
  - [3.3 GetQueuedCompletionStatus](#33-getqueuedcompletionstatus)
  - [3.4 PostQueuedCompletionStatus](#34-postqueuedcompletionstatus)
- [4. 关键概念](#4-关键概念)
  - [4.1 并发线程数（NumberOfConcurrentThreads）](#41-并发线程数numberofconcurrentthreads)
  - [4.2 完成键（CompletionKey）](#42-完成键completionkey)
  - [4.3 扩展函数（AcceptEx/GetAcceptExSockaddrs）](#43-扩展函数acceptexgetacceptexsockaddrs)
- [5. 多线程处理方案](#5-多线程处理方案)
  - [5.1 线程池设计](#51-线程池设计)
  - [5.2 AcceptEx 预投递](#52-acceptex-预投递)
- [6. 连接与数据管理：Per-Handle / Per-I/O Data](#6-连接与数据管理per-handle--per-io-data)
- [7. 与 epoll/io_uring 的跨平台对照](#7-与-epollio_uring-的跨平台对照)
- [8. 快速参考卡片](#8-快速参考卡片)
- [9. 常见问题与坑](#9-常见问题与坑)

---

## 1. Windows 异步 IO 模型演进

Windows 提供了多种 Socket IO 模型，从简单到高性能依次演进：

| 模型 | 机制 | 并发能力 | 说明 |
| --- | --- | --- | --- |
| **select** | 轮询 fd_set，检查就绪 | 低（64 连接限制，可扩展） | 跨平台兼容，性能差 |
| **WSAAsyncSelect** | 基于窗口消息，IO 事件转成 Windows 消息 | 中 | 需窗口，消息队列有瓶颈 |
| **WSAEventSelect** | 基于事件对象（Event），WaitForMultipleObjects 等待 | 中（MAXIMUM_WAIT_OBJECTS=64） | 无窗口依赖，但等待数受限 |
| **重叠 IO（Overlapped I/O）** | 异步提交，通过事件或完成例程通知 | 高 | 需管理 OVERLAPPED 和事件 |
| **IOCP（完成端口）** | 内核级完成队列，线程池取完成通知 | 极高（数万~数十万连接） | Windows 最高性能异步 IO 模型 |

```text
性能与扩展性排序：
  select < WSAAsyncSelect < WSAEventSelect < 重叠IO(事件) < 重叠IO(完成例程) < IOCP
```

IOCP 是 Windows 上构建高并发服务器的标准方案，类似于 Linux 上的 epoll，但设计哲学不同：IOCP 是 **Proactor（前摄器）** 模型，epoll 是 **Reactor（反应器）** 模型。

---

## 2. IOCP 工作机制

### 2.1 完成端口对象

完成端口（Completion Port）是一个内核对象，本质上是一个**先进先出（FIFO）的完成队列**，用于管理异步 IO 的完成通知：

```text
应用线程提交异步 IO 请求（WSARecv/WSASend/ReadFile/WriteFile）
    ↓
内核将 IO 请求加入设备驱动队列，立即返回（不等待完成）
    ↓
IO 完成后，内核将完成包（Completion Packet）加入完成端口的 FIFO 队列
    ↓
工作线程调用 GetQueuedCompletionStatus 从队列取完成包
    ↓
线程处理完成的 IO（处理接收数据、继续投递下一个 IO）
```

完成端口与 Socket/文件句柄关联后，该句柄上所有异步 IO 的完成通知都会进入该完成端口。

### 2.2 重叠 IO（OVERLAPPED）

重叠 IO 是 Windows 异步 IO 的基础。提交异步 IO 时需传入一个 `OVERLAPPED` 结构体，内核在 IO 完成时通过它返回状态：

```c
typedef struct _OVERLAPPED {
    ULONG_PTR Internal;       // 内部使用，IO 完成状态
    ULONG_PTR InternalHigh;   // 内部使用，传输字节数
    union {
        struct {
            DWORD Offset;     // 文件偏移（低 32 位）
            DWORD OffsetHigh; // 文件偏移（高 32 位）
        } DUMMYSTRUCTNAME;
        PVOID Pointer;
    } DUMMYUNIONNAME;
    HANDLE hEvent;            // 事件对象（IOCP 模式下设为 NULL）
} OVERLAPPED, *LPOVERLAPPED;
```

在 IOCP 模式下：
- `hEvent` 设为 NULL（不使用事件通知，由完成端口通知）；
- 通常将 `OVERLAPPED` 嵌入自定义结构体（Per-I/O Data），携带应用层上下文；
- IO 完成后，`Internal` 包含错误码，`InternalHigh` 包含传输字节数。

> 关键规则：提交异步 IO 后，**OVERLAPPED 结构体和数据缓冲区必须保持有效**，直到 IO 完成。不能使用栈上变量（函数返回后失效），必须用堆分配或全局变量。

### 2.3 完成队列

完成端口的内核队列存放**完成包（Completion Packet）**，每个完成包包含：

```text
完成包结构：
  - dwNumberOfBytesTransferred  传输的字节数
  - lpCompletionKey             完成键（关联句柄时指定的自定义数据）
  - lpOverlapped                指向 OVERLAPPED 结构体（即 Per-I/O Data）
```

工作线程通过 `GetQueuedCompletionStatus` 取出完成包，根据 `lpCompletionKey` 找到连接对象（Per-Handle Data），根据 `lpOverlapped` 找到 IO 上下文（Per-I/O Data），然后处理。

---

## 3. 核心 API

### 3.1 CreateIoCompletionPort

创建完成端口，或将已存在的句柄关联到完成端口：

```c
HANDLE CreateIoCompletionPort(
    HANDLE    FileHandle,           // 要关联的句柄（Socket/文件），创建新端口时传 INVALID_HANDLE_VALUE
    HANDLE    ExistingCompletionPort, // 已存在的完成端口，创建新端口时传 NULL
    ULONG_PTR CompletionKey,        // 完成键（自定义数据，通常传连接对象指针）
    DWORD     NumberOfConcurrentThreads // 并发线程数，0 = CPU 核数
);
```

两种用法：

```c
// 用法1：创建新的完成端口
HANDLE hIOCP = CreateIoCompletionPort(INVALID_HANDLE_VALUE, NULL, 0, 0);

// 用法2：将 Socket 关联到完成端口
CreateIoCompletionPort((HANDLE)sock, hIOCP, (ULONG_PTR)pConnection, 0);
// pConnection 是 Per-Handle Data，完成时通过 CompletionKey 返回
```

### 3.2 WSARecv / WSASend

异步提交接收/发送请求：

```c
int WSARecv(
    SOCKET s,                          // Socket
    LPWSABUF lpBuffers,                // 接收缓冲区数组（WSABUF）
    DWORD dwBufferCount,               // 缓冲区数量
    LPDWORD lpNumberOfBytesRecvd,      // 立即接收的字节数（如果立即完成）
    LPDWORD lpFlags,                   // 标志（如 MSG_PEEK）
    LPWSAOVERLAPPED lpOverlapped,      // OVERLAPPED 结构体（Per-I/O Data）
    LPWSAOVERLAPPED_COMPLETION_ROUTINE lpCompletionRoutine // 完成例程（IOCP 模式传 NULL）
);

int WSASend(
    SOCKET s,
    LPWSABUF lpBuffers,
    DWORD dwBufferCount,
    LPDWORD lpNumberOfBytesSent,
    DWORD dwFlags,
    LPWSAOVERLAPPED lpOverlapped,
    LPWSAOVERLAPPED_COMPLETION_ROUTINE lpCompletionRoutine
);
```

返回值：
- `0`：IO 立即完成（数据已在内核缓冲区），但完成通知仍会进入完成端口；
- `SOCKET_ERROR` + `WSAGetLastError() == WSA_IO_PENDING`：IO 挂起，完成后通知进入完成端口（正常情况）；
- 其他错误：提交失败。

```c
// 提交异步接收示例
WSABUF buf = { .buf = pIO->buffer, .len = BUFFER_SIZE };
DWORD flags = 0;
int ret = WSARecv(sock, &buf, 1, NULL, &flags, &pIO->overlapped, NULL);
if (ret == SOCKET_ERROR && WSAGetLastError() != WSA_IO_PENDING) {
    // 真正的错误
}
```

### 3.3 GetQueuedCompletionStatus

工作线程从完成端口取完成包：

```c
BOOL GetQueuedCompletionStatus(
    HANDLE       CompletionPort,          // 完成端口
    LPDWORD      lpNumberOfBytes,          // 输出：传输字节数
    PULONG_PTR   lpCompletionKey,          // 输出：完成键（Per-Handle Data）
    LPOVERLAPPED* lpOverlapped,            // 输出：OVERLAPPED 指针（Per-I/O Data）
    DWORD        dwMilliseconds             // 超时时间，INFINITE = 无限等待
);
```

返回值：
- `TRUE`：IO 成功完成；
- `FALSE` + `lpOverlapped == NULL`：完成端口本身出错（如被关闭）；
- `FALSE` + `lpOverlapped != NULL`：IO 完成但失败，错误码用 `GetLastError()` 获取。

```c
// 工作线程主循环
DWORD bytes;
ULONG_PTR completionKey;
OVERLAPPED* pOverlapped;

while (running) {
    BOOL ok = GetQueuedCompletionStatus(hIOCP, &bytes, &completionKey,
                                          &pOverlapped, INFINITE);
    if (!ok && pOverlapped == NULL) {
        // 完成端口错误，退出
        break;
    }

    PerHandleData* pConn = (PerHandleData*)completionKey;
    PerIoData* pIO = CONTAINING_RECORD(pOverlapped, PerIoData, overlapped);

    if (!ok || bytes == 0) {
        // IO 失败或连接关闭，清理
        CloseConnection(pConn);
        continue;
    }

    // 处理完成的 IO
    if (pIO->operation == OP_RECV) {
        HandleRecv(pConn, pIO, bytes);
    } else if (pIO->operation == OP_SEND) {
        HandleSend(pConn, pIO, bytes);
    }
}
```

### 3.4 PostQueuedCompletionStatus

手动向完成端口投递一个完成包，用于自定义通知（如线程退出、自定义事件）：

```c
BOOL PostQueuedCompletionStatus(
    HANDLE    CompletionPort,
    DWORD     dwNumberOfBytesTransferred,  // 自定义值
    ULONG_PTR CompletionKey,                // 自定义完成键
    LPOVERLAPPED lpOverlapped               // 自定义 OVERLAPPED 指针
);
```

典型用途：
- 通知工作线程退出（投递特殊 completionKey）；
- 投递自定义任务（将完成端口当作任务队列使用）。

```c
// 通知所有工作线程退出
for (int i = 0; i < threadCount; ++i) {
    PostQueuedCompletionStatus(hIOCP, 0, (ULONG_PTR)NULL, NULL);
}
// 工作线程检测到 completionKey == NULL 且 overlapped == NULL 时退出
```

---

## 4. 关键概念

### 4.1 并发线程数（NumberOfConcurrentThreads）

创建完成端口时指定的 `NumberOfConcurrentThreads` 控制**最多有多少个线程可以同时运行**（从完成端口取到完成包并处于可运行状态）：

- 设为 `0`：使用 CPU 核数（推荐默认值）；
- 设为 `N`：最多 N 个线程同时运行；
- 当一个线程因等待锁/IO 而阻塞时，内核会唤醒另一个等待线程，保持并发数。

设计原理：避免线程过多导致上下文切换开销。IOCP 内核会管理线程池，当运行线程数低于设定值时唤醒等待线程。

> 经验值：`NumberOfConcurrentThreads = CPU 核数`，工作线程数 = CPU 核数 * 2（部分线程可能阻塞，留有余量）。

### 4.2 完成键（CompletionKey）

完成键是将句柄关联到完成端口时传入的 `ULONG_PTR`（指针大小的整数），在 IO 完成时原样返回：

```c
// 关联时传入连接对象指针
CreateIoCompletionPort((HANDLE)sock, hIOCP, (ULONG_PTR)pConnection, 0);

// 完成时取回
PerHandleData* pConn = (PerHandleData*)completionKey;
```

完成键通常指向 **Per-Handle Data**（每个连接一个对象），包含 Socket、连接状态、收发缓冲区等。

### 4.3 扩展函数（AcceptEx/GetAcceptExSockaddrs）

`AcceptEx` 是微软扩展的 Winsock API，支持**异步接受连接**，并可在接受连接的同时接收第一块数据：

```c
BOOL AcceptEx(
    SOCKET       sListenSocket,    // 监听 Socket
    SOCKET       sAcceptSocket,    // 预先创建的接受 Socket
    PVOID        lpOutputBuffer,   // 输出缓冲区（存放客户端地址 + 第一块数据）
    DWORD        dwReceiveDataLength, // 接收数据长度（0 = 不接收数据，立即返回）
    DWORD        dwLocalAddressLength,  // 本地地址空间（需 +16 字节）
    DWORD        dwRemoteAddressLength, // 远端地址空间（需 +16 字节）
    LPDWORD      lpdwBytesReceived,     // 接收的字节数
    LPOVERLAPPED lpOverlapped           // OVERLAPPED
);
```

`AcceptEx` 的优势：
- 异步接受连接，不阻塞监听线程；
- 可预投递多个 AcceptEx，高并发下连接建立无延迟；
- 接受连接的同时接收第一块数据，减少一次系统调用。

`GetAcceptExSockaddrs` 从 AcceptEx 的输出缓冲区中解析出本地和远端地址：

```c
void GetAcceptExSockaddrs(
    PVOID    lpOutputBuffer,
    DWORD    dwReceiveDataLength,
    DWORD    dwLocalAddressLength,
    DWORD    dwRemoteAddressLength,
    LPSOCKADDR* LocalSockaddr,       // 输出：本地地址
    LPINT     LocalSockaddrLength,
    LPSOCKADDR* RemoteSockaddr,      // 输出：远端地址
    LPINT     RemoteSockaddrLength
);
```

获取扩展函数指针（需通过 WSAIoctl 加载，不能直接链接）：

```c
GUID guidAcceptEx = WSAID_ACCEPTEX;
GUID guidGetAcceptExSockaddrs = WSAID_GETACCEPTEXSOCKADDRS;
DWORD bytes;

LPFN_ACCEPTEX lpfnAcceptEx;
LPFN_GETACCEPTEXSOCKADDRS lpfnGetAcceptExSockaddrs;

WSAIoctl(sock, SIO_GET_EXTENSION_FUNCTION_POINTER,
         &guidAcceptEx, sizeof(guidAcceptEx),
         &lpfnAcceptEx, sizeof(lpfnAcceptEx),
         &bytes, NULL, NULL);

WSAIoctl(sock, SIO_GET_EXTENSION_FUNCTION_POINTER,
         &guidGetAcceptExSockaddrs, sizeof(guidGetAcceptExSockaddrs),
         &lpfnGetAcceptExSockaddrs, sizeof(lpfnGetAcceptExSockaddrs),
         &bytes, NULL, NULL);
```

---

## 5. 多线程处理方案

### 5.1 线程池设计

IOCP 服务器通常使用固定大小的线程池，每个线程循环调用 `GetQueuedCompletionStatus`：

```text
主线程：
  1. 创建完成端口
  2. 创建监听 Socket，绑定，监听
  3. 将监听 Socket 关联到完成端口（用于 AcceptEx 完成通知）
  4. 预投递 N 个 AcceptEx
  5. 创建工作线程池（CPU核数 * 2）
  6. 等待退出信号

工作线程（每个线程）：
  while (running) {
    GetQueuedCompletionStatus → 取完成包
    根据 completionKey 和 overlapped 判断类型：
      - AcceptEx 完成 → 建立新连接，关联到完成端口，投递 WSARecv
      - WSARecv 完成 → 处理数据，投递下一个 WSARecv
      - WSASend 完成 → 处理发送完成，继续发送队列
      - 自定义通知 → 处理（如退出）
  }
```

线程数经验：
- `NumberOfConcurrentThreads = CPU 核数`；
- 工作线程数 = CPU 核数 * 2（防止部分线程阻塞时无可用线程）；
- 纯 IO 密集型可用 CPU 核数 + 1；
- 有阻塞操作（如数据库查询）时需更多线程。

### 5.2 AcceptEx 预投递

高并发服务器中，连接建立的延迟很关键。预投递多个 AcceptEx 可确保有连接时立即被接受：

```c
// 预投递 10 个 AcceptEx
#define PRE_POST_ACCEPT_COUNT 10

for (int i = 0; i < PRE_POST_ACCEPT_COUNT; ++i) {
    PostAcceptEx(hIOCP, listenSock);
}

void PostAcceptEx(HANDLE hIOCP, SOCKET listenSock) {
    // 1. 创建接受 Socket（必须先创建，AcceptEx 不自动创建）
    SOCKET acceptSock = WSASocket(AF_INET, SOCK_STREAM, IPPROTO_IP,
                                    NULL, 0, WSA_FLAG_OVERLAPPED);

    // 2. 分配 Per-I/O Data（含输出缓冲区）
    PerIoData* pIO = AllocateIoData(OP_ACCEPT);
    // 输出缓冲区大小 = 本地地址(16) + 远端地址(16) + 接收数据(可选)
    int bufSize = (sizeof(sockaddr_in) + 16) * 2;

    // 3. 提交 AcceptEx（dwReceiveDataLength=0，连接建立即完成，不等数据）
    BOOL ok = lpfnAcceptEx(listenSock, acceptSock, pIO->buffer,
                            0,  // 不接收数据
                            sizeof(sockaddr_in) + 16,
                            sizeof(sockaddr_in) + 16,
                            &pIO->bytes, &pIO->overlapped);
    if (!ok && WSAGetLastError() != ERROR_IO_PENDING) {
        // 错误处理
    }
    // acceptSock 存在 pIO 中，完成时取出
}
```

AcceptEx 完成后：
1. 从输出缓冲区解析客户端地址；
2. 将 acceptSock 关联到完成端口；
3. 设置 Socket 选项（`SO_UPDATE_ACCEPT_CONTEXT`，继承监听 Socket 的属性）；
4. 投递第一个 WSARecv；
5. 补充投递一个新的 AcceptEx（保持预投递数量）。

---

## 6. 连接与数据管理：Per-Handle / Per-I/O Data

IOCP 编程中两个核心数据结构：

**Per-Handle Data（每个连接一个）**：

```c
typedef struct _PerHandleData {
    SOCKET       sock;           // 连接 Socket
    sockaddr_in  clientAddr;     // 客户端地址
    CRITICAL_SECTION cs;         // 保护该连接的锁（多线程访问时）
    int          pendingRecv;    // 待处理的接收计数
    int          pendingSend;    // 待处理的发送计数
    BOOL         closing;        // 是否正在关闭
    // 应用层数据：用户ID、会话状态、发送队列等
} PerHandleData;
```

**Per-I/O Data（每个异步 IO 一个）**：

```c
typedef struct _PerIoData {
    OVERLAPPED  overlapped;      // 必须第一个成员（便于 CONTAINING_RECORD）
    WSABUF      wsaBuf;          // 缓冲区描述
    char*       buffer;          // 数据缓冲区（堆分配，IO 完成前保持有效）
    int         operation;       // 操作类型：OP_RECV / OP_SEND / OP_ACCEPT
    DWORD       bytes;           // 传输字节数
    SOCKET      acceptSock;      // AcceptEx 时使用
    // 其他上下文：序列号、超时时间等
} PerIoData;

enum { OP_RECV = 1, OP_SEND = 2, OP_ACCEPT = 3 };
```

通过 `CONTAINING_RECORD` 宏从 OVERLAPPED 指针取回 PerIoData：

```c
PerIoData* pIO = CONTAINING_RECORD(pOverlapped, PerIoData, overlapped);
```

内存管理要点：
- Per-Handle Data 在连接建立时分配，连接关闭时释放；
- Per-I/O Data 在每次提交异步 IO 时分配，IO 完成处理后释放（或复用）；
- **必须确保 IO 完成前不释放 Per-I/O Data 和缓冲区**；
- 高并发下可使用内存池/对象池减少分配开销。

---

## 7. 与 epoll/io_uring 的跨平台对照

> 相关阅读：《../13-并发异步与组件/02-io_uring与异步IO.md》（在 `../../09-Linux高性能后台开发/`）、《../03-网络编程/02-IO多路复用与Reactor模型.md》（在 `../../03-计算机网络编程/`）。

| 维度 | IOCP（Windows） | epoll（Linux） | io_uring（Linux） |
| --- | --- | --- | --- |
| **模型** | Proactor（前摄器） | Reactor（反应器） | Proactor（前摄器） |
| **通知时机** | IO 完成后通知 | IO 就绪时通知（需自己调用 recv/send） | IO 完成后通知 |
| **数据拷贝** | 内核直接拷贝到用户缓冲区（提交时指定） | 用户调用 recv 时拷贝 | 内核直接拷贝到用户缓冲区 |
| **系统调用** | 提交 IO（WSARecv）+ 取完成（GQCS） | epoll_ctl + epoll_wait + recv/send | io_uring_enter（提交+等待合一） |
| **缓冲区** | 提交时指定，内核直接写入 | wait 返回后自己 read | 提交时指定，内核直接写入 |
| **线程模型** | 内核管理并发线程数 | 用户自行管理 | 可单线程/多线程 |
| **连接数** | 数万~数十万 | 数万~数百万 | 数万~数百万 |
| **成熟度** | 非常成熟（Windows NT 时代起） | 非常成熟（Linux 2.6 起） | 较新（Linux 5.1+，快速发展） |

**Proactor vs Reactor 核心区别**：

```text
Reactor（epoll）：
  1. 注册"读就绪"事件
  2. 内核通知："Socket 可读了"
  3. 用户调用 recv() 主动读数据
  → 事件就绪通知，用户执行操作

Proactor（IOCP/io_uring）：
  1. 提交"读操作"（指定缓冲区）
  2. 内核执行读操作，数据写入用户缓冲区
  3. 内核通知："读操作完成了，N 字节已写入缓冲区"
  → 操作完成通知，内核执行操作
```

Proactor 的优势：减少一次系统调用（不需要 wait 后再 recv），内核可更高效地调度 IO；劣势：编程模型更复杂（需管理 OVERLAPPED 和缓冲区生命周期）。

---

## 8. 快速参考卡片

```text
IOCP API 速查：
  CreateIoCompletionPort(INVALID_HANDLE_VALUE, NULL, 0, 0)  创建完成端口
  CreateIoCompletionPort((HANDLE)sock, hIOCP, key, 0)        关联句柄
  WSARecv(sock, &buf, 1, NULL, &flags, &overlapped, NULL)    异步接收
  WSASend(sock, &buf, 1, NULL, 0, &overlapped, NULL)          异步发送
  GetQueuedCompletionStatus(hIOCP, &bytes, &key, &ov, INFINITE)  取完成包
  PostQueuedCompletionStatus(hIOCP, 0, key, ov)                投递自定义完成

与 epoll 对照：
  IOCP:    Proactor，提交操作→内核执行→完成通知
  epoll:   Reactor，注册事件→就绪通知→用户执行
  io_uring: Proactor，类似 IOCP，Linux 5.1+

关键数据结构：
  Per-Handle Data → 每连接一个，含 sock/状态/锁（CompletionKey 返回）
  Per-I/O Data    → 每IO一个，含 OVERLAPPED(首成员)/buffer/operation
  CONTAINING_RECORD(ov, PerIoData, overlapped)  从OVERLAPPED取回PerIoData

服务器骨架：
  1. CreateIoCompletionPort 创建端口
  2. WSASocket(WSA_FLAG_OVERLAPPED) + bind + listen
  3. 关联监听Socket到IOCP
  4. 预投递 N 个 AcceptEx
  5. 创建线程池(CPU核*2)，每线程 GQCS 循环
  6. Accept完成→关联新Socket→投递WSARecv→补投AcceptEx
  7. Recv完成→处理数据→投递下一个Recv
  8. Send完成→处理发送队列
```

## 9. 常见问题与坑

1. **OVERLAPPED 和缓冲区提前释放导致崩溃**：提交异步 IO 后，OVERLAPPED 和数据缓冲区必须保持有效直到 IO 完成。绝对不能用栈上变量，必须堆分配或全局变量，且在 GQCS 返回后才能释放。
2. **Socket 未设置 WSA_FLAG_OVERLAPPED**：创建 Socket 时必须用 `WSASocket(..., WSA_FLAG_OVERLAPPED)` 或 `socket()` 后设置，否则异步 IO 会变成同步阻塞。
3. **AcceptEx 的 acceptSock 未预先创建**：AcceptEx 不会自动创建 Socket，必须预先 `WSASocket` 创建并传入。完成后需调用 `setsockopt(SO_UPDATE_ACCEPT_CONTEXT)` 继承监听 Socket 属性。
4. **GetQueuedCompletionStatus 返回 FALSE 但 overlapped 非空**：这表示 IO 完成但失败（如连接重置），不是完成端口错误。必须检查 `GetLastError()` 并处理连接关闭，不能直接退出线程。
5. **多线程同时操作同一连接导致竞态**：多个工作线程可能同时处理同一连接的不同 IO 完成（如一个在 recv、一个在 send），需用 Per-Handle Data 中的 CRITICAL_SECTION 保护连接状态和发送队列。
6. **WSARecv 提交后立即完成但未处理**：WSARecv 返回 0（立即完成）时，完成通知仍会进入 IOCP 队列，不要在提交处直接处理数据，否则会重复处理。统一在 GQCS 循环中处理。
7. **NumberOfConcurrentThreads 设置不当**：设太小导致并发不足，设太大导致上下文切换。默认 0（CPU 核数）通常最优，有阻塞操作时适当增加工作线程数。
8. **完成端口被意外关闭**：所有关联的句柄关闭后，完成端口才会被销毁。如果提前 CloseHandle(hIOCP)，正在 GQCS 的线程会返回错误。确保在所有线程退出后再关闭。
9. **AcceptEx 输出缓冲区大小计算错误**：本地和远端地址空间需 `sizeof(sockaddr_in) + 16`（额外 16 字节是 Windows 要求），否则地址解析错误或缓冲区溢出。
10. **忘记投递下一个 WSARecv**：处理完一个 recv 完成后，必须立即投递下一个 WSARecv，否则该连接不再接收数据（Socket 上没有挂起的接收 IO）。这是最常见的"连接卡住"原因。

---

上一篇：《08-virtio与vhost虚拟化.md》　｜　模块索引：《../README.md》
