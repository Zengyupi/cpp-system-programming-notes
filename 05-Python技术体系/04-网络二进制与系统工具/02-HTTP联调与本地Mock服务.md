# HTTP 联调与本地 Mock 服务

> 本节目标：用 requests/httpx 调用内部 HTTP 接口（会话、重试、超时、代理、文件上传），用标准库 http.server 或 FastAPI 写本地 mock 与测试桩，以及抓包结果重放。明确不展开 Web 职业技术栈，只聚焦工程师联调与测试场景。

## 本章速览

- [1. 工程场景：C++ 服务端的 HTTP 联调痛点](#1-工程场景c-服务端的-http-联调痛点)
- [2. requests 基础与内部接口调用](#2-requests-基础与内部接口调用)
  - [2.1 会话、超时与重试](#21-会话超时与重试)
  - [2.2 代理与证书](#22-代理与证书)
  - [2.3 文件上传与二进制 body](#23-文件上传与二进制-body)
- [3. httpx：同步+异步统一接口](#3-httpx同步异步统一接口)
- [4. 本地 Mock 服务：标准库 http.server](#4-本地-mock-服务标准库-httpserver)
- [5. 本地 Mock 服务：FastAPI 最小测试桩](#5-本地-mock-服务fastapi-最小测试桩)
- [6. 抓包结果重放](#6-抓包结果重放)
- [7. 快速参考卡片](#7-快速参考卡片)
- [8. 常见坑](#8-常见坑)
- [9. 本节小结](#9-本节小结)

---

## 1. 工程场景：C++ 服务端的 HTTP 联调痛点

C++ 写的服务端常暴露 HTTP 接口供其他模块调用（配置下发、状态查询、控制命令、日志上报）。联调时的痛点：

- 用 `curl` 拼复杂请求头和 body 容易出错，改一个字段要重敲整条命令。
- 内部接口需要鉴权 token、签名、自定义 Header，每次手动维护很痛苦。
- 对端服务还没开发完，C++ 客户端需要一个 mock 服务端来验证请求构造和响应解析。
- 线上抓了一个异常请求，需要在测试环境原样重放复现问题。

Python 的 `requests`（同步）和 `httpx`（同步+异步）是 HTTP 客户端的事实标准，几十行代码就能完成鉴权、重试、文件上传。写 mock 服务端时，标准库 `http.server` 零依赖，`FastAPI` 则用最少代码提供自动 JSON 序列化和路径参数。

**边界声明**：本节不涉及 Django/Flask/FastAPI 的 Web 开发职业路线（路由设计、中间件、ORM、部署、安全等），只把它们当作**本地测试桩**来用。

## 2. requests 基础与内部接口调用

`requests`（以PyPI最新稳定版为准）。最基础的 GET/POST：

```python
"""http_basic.py — requests 基础调用"""
import requests

# GET 带查询参数
resp = requests.get(
    "http://10.0.0.5:8080/api/v1/status",
    params={"device_id": "DEV-001", "verbose": 1},
    timeout=5.0,
)
print(resp.status_code)
print(resp.headers.get("Content-Type"))
print(resp.json())  # 自动解析 JSON

# POST JSON
resp = requests.post(
    "http://10.0.0.5:8080/api/v1/config",
    json={"interval": 30, "retries": 3},   # 自动设 Content-Type: application/json
    timeout=5.0,
)
resp.raise_for_status()  # 非 2xx 抛异常
```

### 2.1 会话、超时与重试

调用内部接口时，通常需要在多个请求间共享 cookie、鉴权头、连接池。用 `Session`：

```python
"""http_session.py — 会话、鉴权、重试"""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def build_session(base_url: str, token: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {token}",
        "X-Client": "py-debug-tool",
    })
    # 重试策略：连接错误、5xx、429 自动重试
    retry = Retry(
        total=3,
        backoff_factor=0.5,          # 退避：0.5, 1, 2 秒
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST", "PUT"],
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s

# 使用
session = build_session("http://10.0.0.5:8080", "my-jwt-token")
for dev_id in ["DEV-001", "DEV-002", "DEV-003"]:
    resp = session.get(
        f"http://10.0.0.5:8080/api/v1/status",
        params={"device_id": dev_id},
        timeout=(3.0, 10.0),  # (连接超时, 读取超时)
    )
    print(f"{dev_id}: {resp.status_code}")
```

超时必须显式设置。`timeout=(connect, read)` 分别控制连接建立和读取数据，避免某个慢请求把整个脚本挂死。

### 2.2 代理与证书

公司内网可能需要走 HTTP 代理，或者内部服务用自签名证书：

```python
"""http_proxy.py — 代理与自签名证书"""
import requests

proxies = {
    "http": "http://proxy.company.com:8080",
    "https": "http://proxy.company.com:8080",
}

# 方式 1：每次请求指定
resp = requests.get("http://internal-api/v1/data", proxies=proxies, timeout=5)

# 方式 2：Session 全局设置
session = requests.Session()
session.proxies.update(proxies)

# 自签名证书：指定 CA 证书文件，或 verify=False 跳过验证（仅调试用！）
resp = requests.get(
    "https://internal-api/v1/data",
    verify="/path/to/internal-ca.crt",  # 或 verify=False
    timeout=5,
)
# verify=False 时会有 InsecureRequestWarning，可临时屏蔽：
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
```

### 2.3 文件上传与二进制 body

C++ 服务端可能需要接收固件文件、日志包、原始二进制报文。用 `files` 参数做 multipart 上传，或直接传 `bytes` 做 raw body：

```python
"""http_upload.py — 文件上传与二进制 body"""
import requests

# multipart/form-data 上传固件
with open("firmware_v2.bin", "rb") as f:
    resp = requests.post(
        "http://10.0.0.5:8080/api/v1/upgrade",
        files={"firmware": ("firmware_v2.bin", f, "application/octet-stream")},
        data={"version": "2.0.0", "device_type": "gateway"},
        timeout=60.0,
    )
print(resp.json())

# raw 二进制 body（自定义协议 over HTTP）
raw_packet = bytes([0xAA, 0x55, 0x01, 0x00, 0x10, 0x20])
resp = requests.post(
    "http://10.0.0.5:8080/api/v1/raw",
    data=raw_packet,
    headers={"Content-Type": "application/octet-stream"},
    timeout=10.0,
)
```

## 3. httpx：同步+异步统一接口

`httpx`（以PyPI最新稳定版为准）。API 与 requests 几乎一致，但额外支持 HTTP/2 和异步。当需要并发调用大量接口时，异步模式比线程池更轻量：

```python
"""http_async.py — httpx 异步并发调用"""
import asyncio
import httpx

async def fetch_status(client: httpx.AsyncClient, device_id: str) -> dict:
    resp = await client.get(
        "http://10.0.0.5:8080/api/v1/status",
        params={"device_id": device_id},
    )
    return {"device": device_id, "code": resp.status_code, "data": resp.json()}

async def main():
    devices = [f"DEV-{i:03d}" for i in range(1, 51)]
    # 连接池 + 超时 + 鉴权头
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(10.0, connect=3.0),
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        headers={"Authorization": "Bearer my-token"},
    ) as client:
        tasks = [fetch_status(client, d) for d in devices]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Exception):
            print(f"ERROR: {r}")
        else:
            print(f"{r['device']}: {r['code']}")

if __name__ == "__main__":
    asyncio.run(main())
```

`httpx` 的同步用法与 requests 几乎相同，迁移成本极低：`httpx.Client()` 对应 `requests.Session()`，`client.get()` 对应 `session.get()`。

## 4. 本地 Mock 服务：标准库 http.server

零依赖方案。适合写一个简单的测试桩，按路径返回固定 JSON 或二进制。C++ 客户端连上来验证请求构造：

```python
"""mock_server_stdlib.py — 标准库 http.server 实现本地 mock"""
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

# 路径 -> 响应 的映射表
MOCK_ROUTES = {
    "/api/v1/status": (200, "application/json",
                        json.dumps({"online": True, "version": "1.2.3"}).encode()),
    "/api/v1/config": (200, "application/json",
                        json.dumps({"interval": 30, "retries": 3}).encode()),
    "/api/v1/notfound": (404, "application/json",
                          json.dumps({"error": "not found"}).encode()),
}

class MockHandler(BaseHTTPRequestHandler):
    def _send(self, code: int, content_type: str, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        print(f"[GET] {self.path}  headers={dict(self.headers)}")
        route = MOCK_ROUTES.get(self.path.split("?")[0])
        if route:
            code, ct, body = route
            self._send(code, ct, body)
        else:
            self._send(404, "application/json",
                       json.dumps({"error": "no mock route"}).encode())

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        print(f"[POST] {self.path}  body={body.hex()}  len={length}")
        # 回显请求体，验证 C++ 客户端发送是否正确
        self._send(200, "application/octet-stream", body)

    def log_message(self, format, *args):
        pass  # 屏蔽默认日志，用自己的 print

if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 8888), MockHandler)
    print("[MOCK] http://127.0.0.1:8888")
    server.serve_forever()
```

标准库方案是单线程的，同一时刻只能处理一个请求。联调足够，如果需要并发，用 `ThreadingHTTPServer`（Python 3.7+）替换 `HTTPServer` 即可。

## 5. 本地 Mock 服务：FastAPI 最小测试桩

当 mock 需要路径参数、请求体自动解析、更复杂的逻辑时，`FastAPI`（以PyPI最新稳定版为准）用最少代码搞定。安装：`pip install fastapi uvicorn`。

```python
"""mock_server_fastapi.py — FastAPI 本地 mock 测试桩"""
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="Local Mock", version="1.0")

# 内存状态，模拟设备注册表
devices: dict[str, dict] = {}

class ConfigIn(BaseModel):
    interval: int = 30
    retries: int = 3

@app.get("/api/v1/status/{device_id}")
async def get_status(device_id: str, request: Request):
    print(f"[GET] /api/v1/status/{device_id}  headers={dict(request.headers)}")
    if device_id in devices:
        return {"device_id": device_id, **devices[device_id]}
    return {"device_id": device_id, "online": False, "error": "unknown device"}

@app.post("/api/v1/config/{device_id}")
async def set_config(device_id: str, cfg: ConfigIn, request: Request):
    print(f"[POST] /api/v1/config/{device_id}  body={cfg.model_dump()}")
    devices[device_id] = {"online": True, "config": cfg.model_dump()}
    return {"device_id": device_id, "result": "ok", "config": cfg.model_dump()}

@app.post("/api/v1/raw")
async def raw_body(request: Request):
    """接收原始二进制，回显，用于验证 C++ 端 raw body 发送"""
    body = await request.body()
    print(f"[RAW] len={len(body)} hex={body.hex()}")
    return Response(content=body, media_type="application/octet-stream")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8888, log_level="warning")
```

启动后访问 `http://127.0.0.1:8888/docs` 可以看到自动生成的 Swagger 文档，方便手动测试。**再次强调**：这里只把 FastAPI 当测试桩，不展开其 Web 开发生态。

## 6. 抓包结果重放

线上用 Wireshark/tcpdump 抓了一个异常请求，需要在测试环境重放。把抓包导出的原始字节保存为文件，用 requests 原样发送：

```python
"""replay.py — 抓包结果重放"""
import requests
import json

def replay_from_file(pcap_export: str, target_url: str):
    """从文本文件读取请求并重放
    文件格式：
        METHOD /path HTTP/1.1
        Header1: value1
        Header2: value2

        <body hex or raw>
    """
    with open(pcap_export, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 解析请求行
    method, path, _ = lines[0].strip().split(" ", 2)
    # 解析 headers
    headers = {}
    body_start = 0
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "":
            body_start = i + 1
            break
        key, _, val = line.strip().partition(":")
        headers[key.strip()] = val.strip()

    # 解析 body（十六进制）
    body_hex = "".join(lines[body_start:]).strip().replace(" ", "").replace("\n", "")
    body = bytes.fromhex(body_hex) if body_hex else None

    print(f"[REPLAY] {method} {path}")
    print(f"  headers: {headers}")
    print(f"  body: {body.hex() if body else '(none)'}")

    resp = requests.request(
        method,
        target_url + path,
        headers=headers,
        data=body,
        timeout=10.0,
    )
    print(f"  -> {resp.status_code}")
    print(f"  -> response: {resp.text[:500]}")

if __name__ == "__main__":
    replay_from_file("captured_request.txt", "http://10.0.0.5:8080")
```

如果抓包是 pcapng 格式，可以用 `scapy`（以PyPI最新稳定版为准）解析提取 HTTP 载荷，但 scapy 依赖较重，简单场景直接 Wireshark 导出为文本更方便。

## 7. 快速参考卡片

| 需求 | 做法 |
| --- | --- |
| 快速起 HTTP 服务 | `python -m http.server 8000`（静态文件）；`--directory dir` 指定根 |
| 自定义 handler | 继承 `BaseHTTPRequestHandler`，实现 `do_GET/do_POST`，`self.wfile.write(body)` |
| 路由分发 | 小规模字典路由；复杂用 `flask`/`fastapi`（`@app.post("/api")`） |
| 请求侧 | `requests.get(url, timeout=3)`；`s.post(url, json={...})`；`r.raise_for_status()` |
| 看原始报文 | `python -m http.server` 配 `tcpdump`/`curl -v`；或用 `http.client.HTTPConnection` 手控 |
| 并发压测 | `ab -n 1000 -c 50` / `wrk`；Python 侧 `concurrent.futures` 并发请求 |
| Mock 状态码 | 故意返回 4xx/5xx 验证客户端容错；慢响应测超时（`time.sleep`） |
| 抓包对照 | 与 Wireshark/tshark 对照验证 Content-Length、分块传输 |
| HTTPS 本地 | `ssl.wrap_socket` + 自签证书；客户端 `verify=False`（仅调试） |
| 常见坑点 | 忘了设置 `Content-Length` 导致客户端一直等；服务端单线程阻塞（用 `ThreadingHTTPServer`） |

---

## 8. 常见坑

**坑 1：不设超时。** `requests.get(url)` 默认无限等待，内部服务挂起时脚本直接卡死。永远传 `timeout`，建议 `timeout=(connect, read)` 分别设置。

**坑 2：Session 不关闭导致连接泄漏。** 用 `with requests.Session() as s:` 或在脚本结束前 `s.close()`。httpx 的 `AsyncClient` 同理必须用 `async with`。

**坑 3：`json` 参数与 `data` 参数混淆。** `json={"k": "v"}` 自动序列化并设 `Content-Type: application/json`；`data={"k": "v"}` 会变成 form-encoded。发送原始字节用 `data=bytes`。

**坑 4：重试只重试 GET 不重试 POST。** 默认 `Retry` 只对幂等方法重试。如果接口 POST 也是幂等的（如查询），显式设置 `allowed_methods`。非幂等 POST（如创建订单）绝不能自动重试。

**坑 5：自签名证书用 `verify=False` 后忘记警告。** 调试可以，但提交代码前必须改成 `verify="/path/to/ca.crt"`。生产环境禁用 `verify=False`。

**坑 6：mock 服务端单线程阻塞。** 标准库 `HTTPServer` 是单线程的，如果 C++ 客户端发了一个请求但不读响应（或很慢），后续请求全部排队。改用 `ThreadingHTTPServer` 或 FastAPI。

## 9. 本节小结

- `requests` 是同步 HTTP 客户端事实标准，`Session` 管理鉴权和连接池，`Retry` 做自动重试，`timeout` 必须显式设置。
- `httpx` API 与 requests 兼容，额外支持异步和 HTTP/2，并发调用大量接口时用 `asyncio.gather`。
- 本地 mock 有两档：标准库 `http.server` 零依赖适合简单桩；`FastAPI` 代码量少、自动 JSON 解析、带 Swagger，适合复杂桩。两者都只作测试桩，不展开 Web 开发。
- 抓包重放的核心是把请求行、Header、Body 从抓包导出中解析出来，用 `requests.request` 原样发送。
- 最常见的坑是不设超时、Session 不关闭、`json`/`data` 混淆、单线程 mock 阻塞。

---

上一篇：《01-Socket调试与Mock对端.md》　｜　下一篇：《03-二进制文件与格式解析.md》　｜　模块索引：《../README.md》
