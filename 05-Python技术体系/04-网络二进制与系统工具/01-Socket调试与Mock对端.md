# Socket 调试与 Mock 对端

> 本节目标：用 Python 标准库 socket 与 selectors 快速搭建 TCP/UDP 收发小工具、模拟设备或服务端做联调 mock、完成端口探测与连通性检查，并对照 C++ Reactor 模型说明脚本层的取舍。

## 本章速览

- [1. 工程场景：为什么用 Python 写网络小工具](#1-工程场景为什么用-python-写网络小工具)
- [2. TCP 收发与调试客户端](#2-tcp-收发与调试客户端)
  - [2.1 一次性请求-响应客户端](#21-一次性请求-响应客户端)
  - [2.2 长连接保活与粘包处理](#22-长连接保活与粘包处理)
- [3. UDP 报文收发工具](#3-udp-报文收发工具)
- [4. Mock 对端：模拟设备与服务端](#4-mock-对端模拟设备与服务端)
  - [4.1 TCP Mock 服务端](#41-tcp-mock-服务端)
  - [4.2 UDP Mock 应答器](#42-udp-mock-应答器)
- [5. 端口探测与连通性检查](#5-端口探测与连通性检查)
- [6. selectors 最小用法与 Reactor 对照](#6-selectors-最小用法与-reactor-对照)
  - [6.1 与 C++ Reactor 的对照](#61-与-c-reactor-的对照)
- [7. 快速参考卡片](#7-快速参考卡片)
- [8. 常见坑](#8-常见坑)
- [9. 本节小结](#9-本节小结)

---

## 1. 工程场景：为什么用 Python 写网络小工具

写 C++ 服务端或嵌入式设备协议时，联调阶段最缺的不是性能，而是**一个能随时改、随时跑的对端**。C++ 写一个测试客户端要处理编译、链接、字节序、缓冲区管理，改一个字段就要重新编译；而 Python 脚本几十行就能模拟一台设备、回放一段报文、批量压测端口。

典型场景：

- 设备还没到货，先用 Python mock 一个 TCP 服务端，按协议文档回固定应答，让 C++ 客户端先跑通流程。
- 线上抓了一段二进制报文，需要逐字段解析后重发给测试环境复现 bug。
- 部署新服务前，批量扫描一段端口范围确认防火墙策略是否生效。
- 写 C++ Reactor 服务端时，需要一个可控的对端来触发各种异常：半关闭、RST、慢发送、粘包。

Python 的 socket 模块是对 BSD Socket API 的薄封装，API 名称和语义与 C 几乎一致，C++ 程序员可以零门槛上手。

## 2. TCP 收发与调试客户端

### 2.1 一次性请求-响应客户端

最常见的调试需求：发一段字节，收一段应答，打印十六进制。

```python
"""tcp_echo_client.py — 一次性 TCP 请求-响应调试工具"""
import socket
import sys

def hex_dump(data: bytes) -> str:
    """字节转十六进制字符串，每 16 字节换行"""
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i:i+16]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{i:04x}  {hex_part:<47s}  {ascii_part}")
    return "\n".join(lines)

def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8888
    # 报文示例：2 字节长度(大端) + 4 字节命令码 + payload
    payload = b"\x00\x01\x02\x03\x04\x05\x06\x07"
    cmd = 0x1001
    body = cmd.to_bytes(4, "big") + payload
    msg = len(body).to_bytes(2, "big") + body

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(5.0)
        s.connect((host, port))
        s.sendall(msg)
        print(f"[SEND] {len(msg)} bytes")
        print(hex_dump(msg))

        # 先读 2 字节长度头
        header = s.recv(2)
        if len(header) < 2:
            print("[ERROR] 连接被对端关闭，未收到长度头")
            return
        body_len = int.from_bytes(header, "big")
        # 循环读满 body_len，处理粘包/分片
        body = b""
        while len(body) < body_len:
            chunk = s.recv(body_len - len(body))
            if not chunk:
                print(f"[ERROR] 对端提前关闭，已收 {len(body)}/{body_len} 字节")
                return
            body += chunk

        print(f"\n[RECV] {len(body)} bytes")
        print(hex_dump(body))

if __name__ == "__main__":
    main()
```

运行方式：

```bash
python tcp_echo_client.py 192.168.1.10 8888
```

关键点：`recv(n)` 不保证收到 n 字节，必须循环读满；`sendall()` 内部循环发送，比 `send()` 更安全。

### 2.2 长连接保活与粘包处理

模拟设备长连接时，需要心跳保活和按帧切分。用一个生成器从字节流中按长度头切帧：

```python
"""frame_reader.py — 按 2 字节大端长度头切分 TCP 字节流"""
from collections.abc import Generator

def frame_reader(sock, header_size: int = 2, byteorder: str = "big") -> Generator[bytes, None, None]:
    """从 TCP 套接字持续产出完整帧，连接关闭时结束"""
    buf = b""
    while True:
        # 缓冲区不足一个头，继续读
        while len(buf) < header_size:
            chunk = sock.recv(4096)
            if not chunk:
                return  # 对端关闭
            buf += chunk
        body_len = int.from_bytes(buf[:header_size], byteorder)
        # 缓冲区不足一帧，继续读
        while len(buf) < header_size + body_len:
            chunk = sock.recv(4096)
            if not chunk:
                return
            buf += chunk
        frame = buf[header_size:header_size + body_len]
        buf = buf[header_size + body_len:]
        yield frame
```

使用示例：

```python
import socket
# from frame_reader import frame_reader

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect(("127.0.0.1", 8888))
    for frame in frame_reader(s):
        print(f"收到帧: {frame.hex()}")
        # 处理帧...
```

## 3. UDP 报文收发工具

UDP 无连接，`sendto` 和 `recvfrom` 是核心。调试设备发现协议（如 DHCP、SSDP、自定义广播发现）时常用。

```python
"""udp_tool.py — UDP 收发与广播工具"""
import socket
import sys

def udp_send_recv(host: str, port: int, data: bytes, timeout: float = 3.0) -> bytes | None:
    """发送 UDP 报文并等待一个应答"""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        s.sendto(data, (host, port))
        try:
            resp, addr = s.recvfrom(65535)
            print(f"[RECV] from {addr}: {resp.hex()}")
            return resp
        except socket.timeout:
            print("[TIMEOUT] 未收到 UDP 应答")
            return None

def udp_broadcast(port: int, data: bytes):
    """发送 UDP 广播，用于设备发现"""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(3.0)
        s.sendto(data, ("255.255.255.255", port))
        # 收集所有应答
        responses = []
        try:
            while True:
                resp, addr = s.recvfrom(65535)
                responses.append((addr, resp))
                print(f"[DISCOVER] {addr}: {resp.hex()}")
        except socket.timeout:
            pass
        return responses

if __name__ == "__main__":
    # 示例：发送自定义发现报文
    discover = b"\xAA\x55\x01\x00"  # 魔数 + 版本
    udp_broadcast(9000, discover)
```

UDP 调试注意：`recvfrom` 一次只返回一个数据报，不会粘包；但可能丢包，必须设超时。

## 4. Mock 对端：模拟设备与服务端

### 4.1 TCP Mock 服务端

设备未到货时，用 Python 起一个 mock 服务端，按协议文档回应答。C++ 客户端连上来就能跑通完整流程。

```python
"""tcp_mock_server.py — 模拟设备的 TCP 服务端，按命令码回固定应答"""
import socket
import threading

# 命令码 -> 应答报文 的映射表（按协议文档填写）
MOCK_RESPONSES = {
    0x1001: b"\x00\x00",                    # 成功应答
    0x1002: b"\x00\x01\x00\x10",            # 带数据的应答
    0x2001: b"\xFF\xFF",                      # 错误码
}

def handle_client(conn: socket.socket, addr):
    print(f"[CONNECT] {addr}")
    try:
        while True:
            # 读 2 字节长度头
            header = conn.recv(2)
            if not header:
                break
            body_len = int.from_bytes(header, "big")
            body = b""
            while len(body) < body_len:
                chunk = conn.recv(body_len - len(body))
                if not chunk:
                    break
                body += chunk
            if len(body) < body_len:
                break

            # 解析 4 字节命令码
            if len(body) >= 4:
                cmd = int.from_bytes(body[:4], "big")
                print(f"[RECV] {addr} cmd=0x{cmd:04x} len={body_len}")
                resp = MOCK_RESPONSES.get(cmd, b"\xEE\xEE")  # 未知命令
                resp_frame = len(resp).to_bytes(2, "big") + resp
                conn.sendall(resp_frame)
                print(f"[SEND] {addr} -> {resp.hex()}")
    except (ConnectionResetError, BrokenPipeError):
        pass
    finally:
        conn.close()
        print(f"[CLOSE] {addr}")

def main(host: str = "0.0.0.0", port: int = 8888):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, port))
        srv.listen(5)
        print(f"[LISTEN] {host}:{port}")
        while True:
            conn, addr = srv.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

if __name__ == "__main__":
    main()
```

这个 mock 服务端每连接一个线程，足够联调使用。如果需要模拟数百连接，改用 `selectors`（见第 6 节）。

### 4.2 UDP Mock 应答器

UDP mock 更简单，单线程循环收发即可：

```python
"""udp_mock.py — UDP 模拟应答器"""
import socket

MOCK_RESPONSES = {
    b"\xAA\x55\x01": b"\xAA\x55\x02\x00\x01",  # 发现请求 -> 发现应答
}

def main(port: int = 9000):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("0.0.0.0", port))
        print(f"[UDP LISTEN] :{port}")
        while True:
            data, addr = s.recvfrom(65535)
            print(f"[RECV] {addr}: {data.hex()}")
            key = data[:3]
            resp = MOCK_RESPONSES.get(key, b"\xEE\xEE")
            s.sendto(resp, addr)
            print(f"[SEND] {addr} <- {resp.hex()}")

if __name__ == "__main__":
    main()
```

## 5. 端口探测与连通性检查

部署前确认防火墙、服务是否存活。TCP 全连接探测最可靠：

```python
"""port_scan.py — 端口连通性批量探测"""
import socket
from concurrent.futures import ThreadPoolExecutor

def check_port(host: str, port: int, timeout: float = 1.0) -> tuple[int, bool, str]:
    """探测单个端口，返回 (端口, 是否开放, 服务名猜测)"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            result = s.connect_ex((host, port))
            if result == 0:
                # 尝试读 banner
                try:
                    s.settimeout(0.5)
                    banner = s.recv(64).decode("ascii", errors="replace").strip()
                except Exception:
                    banner = ""
                return (port, True, banner)
            return (port, False, "")
    except Exception as e:
        return (port, False, str(e))

def scan(host: str, ports: range, workers: int = 50):
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = pool.map(lambda p: check_port(host, p), ports)
    for port, open_, banner in sorted(results):
        status = "OPEN " if open_ else "closed"
        extra = f"  [{banner}]" if banner else ""
        print(f"  {port:5d}  {status}{extra}")

if __name__ == "__main__":
    import sys
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    print(f"扫描 {host} 常用端口...")
    scan(host, range(1, 1025))
```

`connect_ex` 不抛异常而是返回错误码，适合批量扫描。UDP 端口探测不可靠（无连接+丢包），通常用发送特定报文等应答的方式判断。

## 6. selectors 最小用法与 Reactor 对照

当 mock 服务端需要处理大量并发连接时，每连接一线程会浪费资源。`selectors` 模块封装了 `select`/`poll`/`epoll`/`kqueue`，是 Python 标准库的 IO 多路复用。

```python
"""reactor_mock.py — 用 selectors 实现单线程 Reactor 式 mock 服务端"""
import selectors
import socket

sel = selectors.DefaultSelector()
# 每个连接的缓冲区：{fileno: {"buf": bytes, "addr": tuple}}
clients: dict[int, dict] = {}

MOCK_RESPONSES = {0x1001: b"\x00\x00", 0x1002: b"\x00\x01"}

def accept(sock: socket.socket, mask):
    conn, addr = sock.accept()
    conn.setblocking(False)
    clients[conn.fileno()] = {"buf": b"", "addr": addr}
    sel.register(conn, selectors.EVENT_READ, data=handle_read)
    print(f"[CONNECT] {addr} (fd={conn.fileno()})")

def handle_read(conn: socket.socket, mask):
    fd = conn.fileno()
    try:
        chunk = conn.recv(4096)
    except ConnectionResetError:
        chunk = b""
    if not chunk:
        print(f"[CLOSE] {clients[fd]['addr']}")
        sel.unregister(conn)
        conn.close()
        del clients[fd]
        return
    clients[fd]["buf"] += chunk
    # 尝试切帧并应答
    buf = clients[fd]["buf"]
    while len(buf) >= 2:
        body_len = int.from_bytes(buf[:2], "big")
        if len(buf) < 2 + body_len:
            break
        frame = buf[2:2 + body_len]
        buf = buf[2 + body_len:]
        cmd = int.from_bytes(frame[:4], "big") if len(frame) >= 4 else 0
        resp = MOCK_RESPONSES.get(cmd, b"\xEE\xEE")
        resp_frame = len(resp).to_bytes(2, "big") + resp
        # 非阻塞发送，实际工程需要处理 EAGAIN 和发送缓冲区
        conn.sendall(resp_frame)
        print(f"[ECHO] {clients[fd]['addr']} cmd=0x{cmd:04x}")
    clients[fd]["buf"] = buf

def main(host="0.0.0.0", port=8888):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(100)
    srv.setblocking(False)
    sel.register(srv, selectors.EVENT_READ, data=accept)
    print(f"[REACTOR LISTEN] {host}:{port}")
    while True:
        events = sel.select(timeout=None)
        for key, mask in events:
            callback = key.data
            callback(key.fileobj, mask)

if __name__ == "__main__":
    main()
```

### 6.1 与 C++ Reactor 的对照

写过 C++ Reactor（如 muduo、libevent、自研事件循环）后看这段代码，对应关系非常清晰：

| C++ Reactor 概念 | Python selectors 对应 |
|---|---|
| EventLoop | `while True: sel.select()` |
| Channel / EventHandler | `sel.register(fileobj, events, data=callback)` |
| Poller / EpollPoller | `selectors.DefaultSelector()`（自动选 epoll/kqueue） |
| 可读回调 `handleRead()` | `data=handle_read` 函数 |
| `accept()` 分发新连接 | `accept()` 回调中 `sel.register(conn, ...)` |
| 输入缓冲区 `inputBuffer_` | `clients[fd]["buf"]` |

脚本层的取舍：

- **不做零拷贝、不做线程池**：mock 工具 QPS 低，单线程足够。
- **`sendall` 直接发**：C++ Reactor 中要处理 EAGAIN、注册可写事件、维护发送队列；脚本里数据量小，`sendall` 阻塞一会无所谓。
- **缓冲区用 `bytes` 拼接**：C++ 用 `std::string` 或环形缓冲区避免频繁分配；Python 脚本不在乎这点性能。
- **错误处理简化**：C++ 要区分 `EAGAIN`/`ECONNRESET`/`EPIPE`；脚本统一 `try/except` 关连接即可。

更多 Reactor 原理参见《../../01-C++技术体系/03-网络编程/02-IO多路复用与Reactor模型.md》。

## 7. 快速参考卡片

| 需求 | 做法 |
| --- | --- |
| TCP 客户端 | `s = socket.create_connection((host, port), timeout=3)` → `s.sendall(b"...")` → `s.recv(4096)` |
| TCP 服务端 | `socket.socket()` + `bind` + `listen` + `accept`（或用 `socketserver.ThreadingTCPServer`） |
| UDP | `socket.socket(AF_INET, SOCK_DGRAM)` + `sendto/recvfrom`（保留报文边界） |
| 超时控制 | `s.settimeout(2)`（抛 `socket.timeout`）或 `select.select([s], [], [], 2)` |
| 收发十六进制打印 | `print(data.hex(" "))` / `binascii.hexlify`；接收端可 `bytes.fromhex` |
| 处理粘包 | 按长度字段循环读：`recv_exact(n)` 直到读满 |
| Mock 对端 | 起一个假服务端回放固定响应；或用 `socketpair` 在同进程内造两端 |
| 端口占用排查 | `ss -ltnp` / `lsof -i:8080`；Python 侧 `socket.bind` 报错即端口冲突 |
| 并发 mock | `threading` 每连接一线程；协议复杂时用 `asyncio` |
| 常见坑点 | `recv` 返回空 bytes 表示对端关闭（不是"还没数据"）；只调一次 `recv` 不保证收全 |

---

## 8. 常见坑

**坑 1：`recv(n)` 以为一定收到 n 字节。** TCP 是流协议，`recv(1024)` 可能返回 1 字节也可能返回 1024 字节。必须按协议长度头循环读满。UDP 不存在这个问题，但会丢包。

**坑 2：忘记设超时。** `connect` 和 `recv` 默认无限阻塞，mock 工具挂死很难排查。一律 `settimeout()`，或用 `setblocking(False)` + selectors。

**坑 3：大端小端搞反。** 网络协议默认大端（`big` / `network`），但有些私有协议用小端。`int.from_bytes(data, "big")` 和 `int.to_bytes(length, "big")` 显式指定，不要依赖默认值。

**坑 4：`SO_REUSEADDR` 缺失。** 调试时频繁启停服务端，上一个进程的 socket 还在 TIME_WAIT，`bind` 报 `Address already in use`。`setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)` 解决。

**坑 5：用 `send()` 代替 `sendall()`。** `send()` 可能只发了一部分就返回（返回实际发送字节数），必须循环。`sendall()` 内部已经处理。

**坑 6：UDP 广播地址用错。** `255.255.255.255` 是受限广播，路由器不转发。跨网段发现要用子网广播地址（如 `192.168.1.255`），且必须 `setsockopt(SO_BROADCAST, 1)`。

## 9. 本节小结

- Python `socket` 是 BSD Socket API 的薄封装，C++ 程序员零门槛，适合写联调小工具而非高性能服务。
- TCP 调试核心是**循环读满 + 长度头切帧**；UDP 调试核心是**超时 + 广播开关**。
- Mock 对端用命令码映射表就能模拟设备应答，每连接一线程足够联调；高并发改用 `selectors`。
- `selectors` 与 C++ Reactor 概念一一对应，但脚本层省略了发送队列、零拷贝、线程池等工程复杂度。
- 端口探测用 `connect_ex` + 线程池，快速确认防火墙和服务存活。

---

下一篇：《02-HTTP联调与本地Mock服务.md》　｜　模块索引：《../README.md》
