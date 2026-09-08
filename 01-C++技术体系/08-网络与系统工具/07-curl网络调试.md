# curl 网络调试

> 本节目标：讲解 curl 作为命令行 HTTP/HTTPS 调试瑞士军刀的完整用法——`-v` 看请求响应全流程、`-w` 时间分解定位慢接口、POST/JSON 接口调试、文件上传、下载断点与限速、代理与 TLS 证书处理。学完后能够不依赖浏览器/Postman 完成接口调试、慢接口定位、TLS 排查与文件传输。本篇输出均在 Ubuntu 24.04（curl 8.5.0）实跑验证，本地用 Python 起 HTTP 服务作测试对象。HTTP 协议原理见《../03-网络编程/01-计算机网络协议详解.md》，抓包对照见《02-tcpdump网络抓包.md》。

## 本章速览

- [0. curl 是什么](#0-curl-是什么)
- [1. 基本调用与输出](#1-基本调用与输出)
- [2. 详细模式看全流程](#2-详细模式看全流程)
- [3. 时间分解看性能](#3-时间分解看性能)
- [4. 方法与数据：POST 调试接口](#4-方法与数据post-调试接口)
- [5. 只看响应头](#5-只看响应头)
- [6. 下载与断点续传](#6-下载与断点续传)
- [7. 连接细节：代理与 TLS](#7-连接细节代理与-tls)
- [8. 实战工作流](#8-实战工作流)
- [9. 快速参考卡片](#9-快速参考卡片)
- [10. 常见问题与坑](#10-常见问题与坑)

---

## 0. curl 是什么

命令行 HTTP 客户端，不带浏览器地发请求、看响应、传文件。后端/嵌入式日常三件事全靠它：

| 场景 | curl 用法 |
| --- | --- |
| 接口调试 | `curl -v http://host/api`，改头改体重放 |
| 慢接口定位 | `curl -w` 拆解连接/首字节/总耗时 |
| TLS/证书排查 | `curl -v` 看握手、`--cacert`/`-k` 处理证书 |
| 文件下载/上传 | `-O`/`-C -`/`-F` |

> 协议原理见《../03-网络编程/01-计算机网络协议详解.md》；要看线上真实字节流用《02-tcpdump网络抓包.md》。curl 是"按你给的请求发"，tcpdump 是"看线路上实际走了什么"，两者配合定位问题最彻底。

测试对象（本地起一个回显服务）：

```python
# echo_srv.py：回显 method/path/body，便于看 curl 实际发出去什么
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(n).decode()
        out = ('method=%s path=%s ctype=%s body=%s' % (self.command, self.path, self.headers.get('Content-Type'), body)).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(out)
    def log_message(self, *a): pass
HTTPServer(('127.0.0.1', 18085), H).serve_forever()
```
```bash
python3 echo_srv.py &
```

---

## 1. 基本调用与输出

```bash
curl http://example.com/          # 请求并把响应 body 打到 stdout
curl -s http://example.com/       # 静默：不显示进度条
curl -o out.html http://ex.com/   # 保存到文件（下载必须 -o/-O）
curl -sS http://ex.com/           # 静默但仍显示错误（推荐）
```

- 默认把响应体打 stdout，进度条打 stderr。**下载文件用 `-o`**，不要 `curl URL > file`（进度条和错误会混进文件）。
- `-s` 连错误都吞，调试时用 `-sS` 或干脆不静默。

---

## 2. 详细模式看全流程

`-v` 输出请求行、请求头、响应头、连接过程，全流程一目了然（输出到 **stderr**）：

```bash
$ curl -sv http://127.0.0.1:18081/ 2>&1 | head -20
*   Trying 127.0.0.1:18081...
* Connected to 127.0.0.1 (127.0.0.1) port 18081
> GET / HTTP/1.1
> Host: 127.0.0.1:18081
> User-Agent: curl/8.5.0
> Accept: */*
>
* HTTP 1.0, assume close after body
< HTTP/1.0 200 OK
< Server: SimpleHTTP/0.6 Python/3.12.3
< Date: Tue, 08 Sep 2026 02:19:08 GMT
< Content-type: text/html; charset=utf-8
< Content-Length: 1574
<
{ [1574 bytes data]
* Closing connection
```

| 行 | 含义 |
| --- | --- |
| `* Trying 127.0.0.1:18081` | DNS 解析完成、开始 TCP 连接 |
| `* Connected to ... port 18081` | TCP 三次握手完成 |
| `> GET / HTTP/1.1` 及后续 `>` 行 | **curl 实际发出去的请求行与请求头** |
| `< HTTP/1.0 200 OK` 及后续 `<` 行 | 服务器返回的响应头 |
| `{ [1574 bytes data]` | 响应体 1574 字节 |
| `* Closing connection` | 连接关闭 |

> 服务端行为异常（302 跳转、500、重定向、头缺失）在 `-v` 下一眼可见。**改请求头重放**是接口调试标准动作：`-v -H 'Authorization: Bearer xxx'` 看服务器怎么回。

HTTPS 时 `-v` 还会显示 TLS 握手细节：

```bash
curl -sv https://example.com -o /dev/null 2>&1 | grep -E 'TLS|subject|issuer|SSL' | head -5
# 例：* SSL connection using TLSv1.3 / AEAD-AES256-GCM-SHA384
```

---

## 3. 时间分解看性能

`-w` 输出自定义格式，拆解一次请求的各阶段耗时：

```bash
$ curl -s -o /dev/null -w 'total=%{time_total}s connect=%{time_connect}s ttfb=%{time_starttransfer}s size=%{size_download}\n' http://127.0.0.1:18081/
total=0.001358s connect=0.000323s ttfb=0.001307s size=1574
```

各时间变量的含义（后端面试高频）：

| 变量 | 含义 | 判断 |
| --- | --- | --- |
| `time_namelookup` | DNS 解析耗时 | 大 → DNS 慢/配置问题 |
| `time_connect` | TCP 握手耗时 | 大 → 网络往返/防火墙 |
| `time_appconnect` | TLS 握手耗时（HTTPS） | 大 → 证书链/加密套件 |
| `time_starttransfer`（ttfb） | 发出请求到收到第一个字节 | **大 → 服务端处理慢** |
| `time_total` | 总耗时 | — |
| `size_download` | 下载字节数 | 核对响应大小 |

外网实测（含 TLS 握手）：

```bash
$ curl -sS -o /dev/null -w 'code=%{http_code} ip=%{remote_ip} tls=%{time_appconnect}s total=%{time_total}s\n' https://example.com
code=200 ip=172.66.147.243 tls=0.397204s total=0.599090s
```

> **慢接口定位两步法**：`connect` 大 → 网络层问题（对端/防火墙/路由）；`ttfb` 大而 connect 小 → **服务端处理慢**（去查服务日志/数据库）。外网环境还能顺手拿到 `remote_ip`（连到了哪台机器，多 IP/CDN 场景确认命中节点）。

---

## 4. 方法与数据：POST 调试接口

```bash
# JSON POST（接口调试最常见）
curl -s -X POST -H 'Content-Type: application/json' \
     -d '{"cmd":"read","addr":1}' http://127.0.0.1:18085/api/v1/read
# 输出：method=POST path=/api/v1/read ctype=application/json body={"cmd":"read","addr":1}

# 表单数据（-d 默认 Content-Type: application/x-www-form-urlencoded）
curl -s -d 'user=alice&age=30' http://host/login

# 文件上传（multipart）
echo 'hello-upload' > /tmp/up.txt
curl -s -F 'file=@/tmp/up.txt' http://127.0.0.1:18085/upload
```

`-v` 看 POST 实际发出去的字节：

```text
> POST /echo HTTP/1.1
> Host: 127.0.0.1:18085
> Content-Type: application/json
> Content-Length: 7
>
< HTTP/1.0 200 OK
```

要点与坑：

- **`-d` 会自动把方法变成 POST**，`-X POST` 常可省略；但 **JSON 必须显式 `-H 'Content-Type: application/json'`**，否则服务器按表单解析。
- `-F` 是 multipart 文件上传（`-F 'file=@路径'`），与 `-d` 的编码完全不同，别混用。
- 本地 POST 回显服务没实现时返回 `501`，说明服务器不支持该方法——这本身就是调试结论。

---

## 5. 只看响应头

```bash
curl -si http://127.0.0.1:18081/ | head -12     # -i：响应头 + body
curl -sI http://example.com/                    # -I：只发 HEAD，只回响应头
```

`-i` 输出（响应头 + body 前几行）：

```text
HTTP/1.0 200 OK
Server: SimpleHTTP/0.6 Python/3.12.3
Date: Tue, 08 Sep 2026 02:19:08 GMT
Content-type: text/html; charset=utf-8
Content-Length: 1574

<!DOCTYPE HTML>
<html lang="en">
```

> 排查缓存、编码、跨域、重定向、长度字段时先 `-I` 看头，不拉 body。`-I` 用 HEAD 方法，部分服务不支持 HEAD 会返回 405，此时改用 `-s -o /dev/null -D -`（只打印头）。

---

## 6. 下载与断点续传

```bash
curl -O https://example.com/file.tar.gz        # 按 URL 文件名保存
curl -o my.tar.gz https://example.com/file     # 指定文件名
curl -C - -O https://example.com/big.iso       # 断点续传（接着上次的进度）
curl --limit-rate 1M -O https://ex.com/big.iso # 限速 1MB/s
curl --max-time 30 -O https://ex.com/big.iso   # 30 秒超时
curl -f -O https://ex.com/404                   # 404 时返回失败退出码（脚本判断用）
```

- `-C -` 续传依赖服务器支持 Range；`-f`（`--fail`）让 HTTP 错误码变成非零退出码，**写脚本判断下载成败必须加**。
- 嵌入式 OTA/内网分发场景：`curl --limit-rate` 控带宽、`--max-time` 防卡死、`-C -` 断点续传，三件套配合后台任务使用。

---

## 7. 连接细节：代理与 TLS

```bash
curl -x http://proxy:8080 http://example.com     # HTTP 代理
curl --connect-timeout 3 http://ex.com/          # TCP 连接超时（不是总超时）
curl --resolve api.example.com:443:1.2.3.4 https://api.example.com/   # 指定域名解析到某 IP
curl -k https://self-signed.local/               # 跳过证书校验（仅调试）
curl --cacert /path/ca.pem https://myapi/        # 指定信任的 CA
curl --cert client.pem --key client.key https://myapi/   # 双向 TLS 客户端证书
```

- `--resolve` 在"DNS 指错了/想测某台后端"时最实用：不改 hosts 就能把域名打到指定 IP。
- `-k` 只用于调试自签名环境，生产必须 `--cacert`/系统信任链。
- 接口调试最常见的 TLS 报错 `SSL certificate problem`：先 `-v` 看是证书过期、自签名还是主机名不匹配，再决定 `--cacert` 或 `-k`。

---

## 8. 实战工作流

```bash
# 1) 接口调试标准流程：-v 看协议层 → 改头/体重放 → -w 看耗时
curl -v -H 'Content-Type: application/json' -d '{"a":1}' http://host/api
curl -s -o /dev/null -w '%{http_code} %{time_total}s\n' http://host/api

# 2) 慢接口定位：connect 大=网络，ttfb 大=服务端
curl -s -o /dev/null -w 'dns=%{time_namelookup}s conn=%{time_connect}s ttfb=%{time_starttransfer}s total=%{time_total}s\n' http://host/api

# 3) 健康检查脚本（判断服务是否活着）
code=$(curl -sf -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8080/health) || { echo "DOWN"; exit 1; }

# 4) 线上抓包前先用 curl 复现一次，确认请求头/参数与线上一致
curl -v -H 'Authorization: Bearer TOKEN' 'http://host/api?v=1&debug=1'
```

---

## 9. 快速参考卡片

```bash
GET 并显示 body：      curl http://host/
静默+保留错误：        curl -sS http://host/
详细看全流程：        curl -sv http://host/           # 输出在 stderr
只看响应头：          curl -sI http://host/ 或 curl -sD - -o /dev/null http://host/
JSON POST：           curl -s -X POST -H 'Content-Type: application/json' -d '{"k":"v"}' http://host/api
表单 POST：           curl -s -d 'a=1&b=2' http://host/
文件上传：            curl -s -F 'file=@/tmp/x.txt' http://host/upload
下载：                curl -O URL / curl -o name URL
断点续传：            curl -C - -O URL
限速/超时：           curl --limit-rate 1M --max-time 30 -O URL
时间分解：            curl -s -o /dev/null -w '%{time_connect}s %{time_starttransfer}s %{time_total}s\n' URL
指定 DNS：            curl --resolve host:443:1.2.3.4 https://host/
跳过证书（调试）：     curl -k https://self-signed/
```

---

## 10. 常见问题与坑

1. **下载用 `>` 重定向**：进度条和错误会混进文件；用 `-o`/`-O`。
2. **`-s` 吞掉所有错误**：脚本里用 `-sS`（保留错误）或 `-f`（失败返回非零码）。
3. **JSON 没加 `-H 'Content-Type: application/json'`**：服务器按表单解析，接口 415/解析失败最常见原因。
4. **`-d` 与 `-F` 混用**：一个 URL 编码一个 multipart，上传文件用 `-F`。
5. **`-v` 输出在 stderr**：管道过滤要 `2>&1`；想看请求头就用它，不要自己猜。
6. **URL 带 `&` 等符号**：shell 里必须加引号，否则 `&` 被 shell 切到后台。
7. **`-I` 返回 405**：服务器不支持 HEAD，改用 `-s -o /dev/null -D -`。
8. **curl 有代理时外网失败**：环境变量 `http_proxy/https_proxy` 会影响 curl；内网调试用 `--noproxy '*'`。
9. **`--max-time` 与 `--connect-timeout` 不同**：前者总时长、后者仅 TCP 连接；两个都设防卡死。
10. **`-X POST` 不是必须的**：`-d` 自动转 POST；`-X` 改方法但不会自动加 body，`-X GET -d 'a=1'` 会发带 body 的 GET（部分服务器直接 400）。

---

上一篇：《06-strace系统调用跟踪.md》
下一篇：《08-lsof文件句柄排查.md》
