# nc 与 telnet 网络调试

> 本节目标：讲解两个最基础的 TCP/UDP 命令行调试工具——nc（netcat，网络瑞士军刀）与 telnet（交互式端口探测）。掌握端口连通性探测、手动发送文本协议（HTTP/Redis/SMTP）、临时监听与文件传输、UDP 收发，以及 telnet"非纯透传、明文不安全"两个关键坑。本篇输出均在 Ubuntu 24.04（OpenBSD netcat 1.226、GNU inetutils telnet 2.5）实跑验证。与《07-curl网络调试.md》（HTTP 专用）、《02-tcpdump网络抓包.md》（链路抓包）、《08-lsof文件句柄排查.md》（查端口占用）配套使用。

## 本章速览

- [0. 解决什么问题与选型](#0-解决什么问题与选型)
- [1. nc 端口探测](#1-nc-端口探测)
- [2. nc 手动发送文本协议](#2-nc-手动发送文本协议)
- [3. nc 监听传输与 UDP](#3-nc-监听传输与-udp)
- [4. telnet 连通性测试](#4-telnet-连通性测试)
- [5. telnet 协议调试与非透传的坑](#5-telnet-协议调试与非透传的坑)
- [6. nc、telnet、curl 选型对照](#6-nctelnetcurl-选型对照)
- [7. 实战工作流](#7-实战工作流)
- [8. 快速参考卡片](#8-快速参考卡片)
- [9. 常见问题与坑](#9-常见问题与坑)

---

## 0. 解决什么问题与选型

服务连不上、端口通不通、想绕过客户端直接跟服务端说几句话——这类问题不需要写代码，两个小工具即可：

| 工具 | 本质 | 现代用途 |
| --- | --- | --- |
| `nc`（netcat） | TCP/UDP 原始字节通道，**既能当客户端连，也能当服务端听**，纯字节透传 | 端口探测、手动发协议、临时监听、传文件、UDP 调试 |
| `telnet` | 古老的明文远程终端协议（23 端口），现几乎被 ssh 取代 | 交互式端口连通性测试、人工敲文本协议 |

一句话分工：**脚本化、要精确控制字节用 nc；人在终端前只想确认"端口通不通、服务有没有回 banner"用 telnet。**

> 安装：Debian/Ubuntu 下 `apt install netcat-openbsd telnet`。注意 netcat 有 OpenBSD 版与 traditional 版两种实现，参数略有差异，主流发行版默认是 OpenBSD 版。

---

## 1. nc 端口探测

### 1.1 探测单个端口

`-z` 表示只建立连接、不发送数据（zero-I/O 扫描模式），`-v` 输出详细结果，`-w` 指定超时秒数：

```bash
$ python3 -m http.server 18080 &        # 起一个本地服务
$ nc -zv -w2 127.0.0.1 18080
Connection to 127.0.0.1 18080 port [tcp/*] succeeded!      # 端口开放

$ nc -zv -w2 127.0.0.1 19999
nc: connect to 127.0.0.1 port 19999 (tcp) failed: Connection refused   # 端口关闭/无人监听
```

- `succeeded!` = TCP 三次握手成功，端口有服务监听。
- `Connection refused` = 主机可达但端口无人监听（收到 RST）；如果长时间超时（timed out）则多为防火墙丢包，二者要区分。
- **探测结果走 stderr**，写脚本过滤时要 `2>&1`。
- 退出码：开放返回 0，失败返回非 0，可直接用于 shell 判断：`nc -z 127.0.0.1 8080 && echo up || echo down`。

### 1.2 扫描端口段

端口写成 `起-止` 即可逐个探测：

```bash
$ nc -zv -w1 127.0.0.1 18078-18082 2>&1
nc: connect to 127.0.0.1 port 18078 (tcp) failed: Connection refused
nc: connect to 127.0.0.1 port 18079 (tcp) failed: Connection refused
Connection to 127.0.0.1 18080 port [tcp/*] succeeded!
nc: connect to 127.0.0.1 port 18081 (tcp) failed: Connection refused
nc: connect to 127.0.0.1 port 18082 (tcp) failed: Connection refused
```

> 端口段扫描仅限排查本机/授权环境；对他人主机大范围扫描可能触发安全告警。大范围、多主机扫描应使用 nmap。

常用选项：

| 选项 | 作用 |
| --- | --- |
| `-z` | 只探测不发数据 |
| `-v` | 详细输出（可 `-vv`） |
| `-w N` | 连接/空闲超时 N 秒，防止挂死 |
| `-n` | 不做 DNS 反解，更快 |
| `-4` / `-6` | 强制 IPv4 / IPv6（localhost 解析到 `::1` 连不上时用 `-4`） |

---

## 2. nc 手动发送文本协议

nc 把 **stdin 原样发给对端，把对端的回包原样打到 stdout**，是一个纯透传的字节通道，因此可以手动"说"任何基于文本行的协议。

### 2.1 手动发 HTTP 请求

```bash
$ printf 'GET / HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n' | nc -w2 127.0.0.1 18080
HTTP/1.0 200 OK
Server: SimpleHTTP/0.6 Python/3.12.3
Date: Tue, 08 Sep 2026 03:37:50 GMT
Content-type: text/html
Content-Length: 18

<h1>hello nc</h1>
```

- 请求头之间、请求头与空行之间必须是 `\r\n`，用 `printf` 精确输出；结尾空行（`\r\n\r\n`）不能少。
- 用 HTTP/1.0 时服务端回完即断，最省事；用 HTTP/1.1 必须带 `Host` 头，且默认长连接，需要 `-w` 超时兜底。

### 2.2 调试其他文本协议

同一套手法适用于所有"命令-响应"式文本协议：

```bash
# Redis（RESP 行协议）
printf 'PING\r\n' | nc 127.0.0.1 6379          # 返回 +PONG
printf '*1\r\n$4\r\nPING\r\n' | nc 127.0.0.1 6379

# SMTP：连上后服务端会先主动发 banner，再逐行敲 EHLO、MAIL FROM 等
nc -w5 smtp.example.com 25

# MySQL/自定义二进制协议：可用 nc 收握手包到文件再分析
nc -w2 127.0.0.1 3306 > handshake.bin
```

这种"绕过自家客户端、直接跟服务端对话"的方式，是定位"到底是客户端拼错了请求，还是服务端有问题"的最快手段。HTTP 场景的更专业工具是 curl，见《07-curl网络调试.md》。

---

## 3. nc 监听传输与 UDP

### 3.1 临时起一个 TCP 监听

`-l`（listen）让 nc 反过来当服务端，常用于"在一台机器上开个口子等连接"：

```bash
# 机器 A：监听 9100，把收到的数据写入文件
nc -l 127.0.0.1 9100 > recv.txt

# 机器 B（或另一个终端）：连上去发一行
echo "hello-from-client" | nc -w1 127.0.0.1 9100

# A 端文件内容（实测）：
# hello-from-client
```

- **临时聊天/联调**：两端分别执行 `nc -l 9100` 与 `nc 主机 9100`，直接互敲文字，用来验证双向链路。
- **传文件**：接收方 `nc -l 9100 > file`，发送方 `nc 主机 9100 < file`。适合内网临时传一个文件，免配 scp/共享目录。
- `-k`：客户端断开后继续保持监听、服务下一个连接（不加 `-k` 默认接完一个就退出）。
- 不写地址时 `nc -l 9100` 监听 `0.0.0.0`（所有网卡）；写 `127.0.0.1` 则只接受本机连接，调试时更安全。

### 3.2 UDP 模式

加 `-u` 走 UDP：

```bash
# 服务端
nc -u -l 127.0.0.1 9200 > udp.txt
# 客户端
echo "udp-hello" | nc -u -w1 127.0.0.1 9200
# 服务端收到（实测）：udp-hello
```

UDP 是无连接的，**`nc -uzv` 探测 UDP 端口并不可靠**：没有回应不代表端口关闭（只有收到 ICMP port unreachable 才能判定关闭），验证 UDP 服务要靠实际发数据看响应。

---

## 4. telnet 连通性测试

### 4.1 连上与被拒

```bash
$ telnet 127.0.0.1 18080
Trying 127.0.0.1...
Connected to 127.0.0.1.          # TCP 连接已建立
Escape character is '^]'.        # 提示按 Ctrl+] 进入 telnet 命令模式
Connection closed by foreign host.

$ telnet 127.0.0.1 19999
Trying 127.0.0.1...
telnet: Unable to connect to remote host: Connection refused   # 端口无人监听
```

- 看到 `Connected to` 即说明"网络可达 + 端口有服务"，这一步就能把问题切成"网络层"还是"应用层"。
- 很多文本协议服务（SMTP、Redis、FTP）一连上会**主动推送欢迎 banner**，telnet 连上即可看到，用来判断服务是否活着、版本是多少。

### 4.2 退出与命令模式

- 连接建立后按 `Ctrl + ]` 进入 telnet 命令提示符，常用：`quit` 退出、`close` 关闭连接、`status` 看状态、`z` 挂起。
- 也可以直接 `quit` 或 Ctrl+C 退出。
- **不带端口的 `telnet 主机` 默认连 23 端口**（传统远程登录）。现代服务器基本关闭 23 且全程明文，远程登录一律使用 ssh。

---

## 5. telnet 协议调试与非透传的坑

### 5.1 交互式手动发协议

telnet 连上文本协议端口后，可以人工逐行敲请求（以 HTTP 为例，连上后输入并敲两次回车）：

```text
GET / HTTP/1.0
Host: 127.0.0.1

```

### 5.2 关键坑：telnet 不是纯字节透传

telnet 内部有一套 **TELNET 选项协商协议**（会收发 `0xFF` 开头的 IAC 控制字节），还会对换行做转换，因此它不是一条干净的 TCP 字节管道。用管道批量喂入请求时会踩坑——同一份 HTTP 请求，telnet 被服务端判为非法，而 nc 正常：

```bash
# telnet 管道喂入（实测）：Python http.server 返回 400
{ printf 'GET / HTTP/1.0\r\nHost: x\r\n\r\n'; sleep 1; } | telnet 127.0.0.1 18080
# ...
# <p>Error code: 400</p>
# <p>Message: Bad request version ('\x00').</p>

# 同样的字节用 nc（实测）：正常 200
printf 'GET / HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n' | nc -w2 127.0.0.1 18080
```

结论：

- **精确字节、脚本化、二进制协议 → 用 nc**；telnet 只适合人在终端前的交互式探测。
- telnet 遇到二进制协议（MySQL、TLS 握手）会满屏花屏控制符，这不是服务端乱码，是 telnet 不该用于二进制场景。

### 5.3 明文风险

telnet 的所有内容（包括账号密码）全程明文传输，且无完整性保护。生产环境禁止用 telnet 做远程登录；它现在只作为"端口/文本协议调试器"存在。

---

## 6. nc、telnet、curl 选型对照

| 场景 | 首选工具 | 说明 |
| --- | --- | --- |
| 端口通不通（脚本/批量） | `nc -zv` | 有退出码，结果在 stderr |
| 端口通不通（人工看一眼） | `telnet host port` | 看到 Connected 即可 |
| 精确发送协议字节、脚本化 | `nc` | 纯透传，HTTP/Redis/SMTP 都行 |
| HTTP/HTTPS 接口调试 | `curl` | 方法/头/体/TLS/耗时，见《07-curl网络调试.md》 |
| 看链路上实际的包 | `tcpdump` | 见《02-tcpdump网络抓包.md》 |
| 端口被哪个进程占用 | `lsof -i :端口` / `ss` | 见《08-lsof文件句柄排查.md》、《01-Linux命令行速查.md》 |
| 远程登录服务器 | `ssh` | 不要用 telnet |

---

## 7. 实战工作流

```bash
# 1) 服务起不来/连不上：先分层定位
nc -zv -w2 10.0.0.5 8080          # 不通 → 网络/防火墙；通但业务报错 → 应用层

# 2) 验证防火墙策略（两端配合）
# 被连端临时监听：
nc -l 0.0.0.0 9999
# 发起端探测：
nc -zv 10.0.0.5 9999

# 3) 绕过自家客户端，直接验证服务端协议
printf 'GET /health HTTP/1.0\r\nHost: x\r\n\r\n' | nc -w2 127.0.0.1 8080

# 4) 把服务端原始响应/握手包落盘分析
nc -w2 127.0.0.1 3306 > handshake.bin

# 5) 内网临时传文件
nc -l 9999 > recv.tgz                     # 接收方
nc 10.0.0.5 9999 < send.tgz              # 发送方

# 6) 脚本里做存活判断
nc -z 127.0.0.1 6379 && echo "redis up" || echo "redis down"
```

---

## 8. 快速参考卡片

```bash
# nc
探测端口：       nc -zv -w2 host port
扫描端口段：      nc -zv -w1 host 8000-8010
发文本协议：      printf 'GET / HTTP/1.0\r\nHost: x\r\n\r\n' | nc -w2 host 80
临时监听：        nc -l [-k] [127.0.0.1] 9100
收文件：          nc -l 9100 > file
发文件：          nc host 9100 < file
UDP 服务端/客户端：nc -u -l 9200  /  nc -u host 9200
强制 IPv4：       nc -4 ...
# telnet
交互式探测：      telnet host port
命令模式/退出：    Ctrl+] 后 quit
```

---

## 9. 常见问题与坑

1. **`nc -zv` 没有输出**：探测信息在 stderr，管道接 grep 时加 `2>&1`。
2. **连接一直挂着不返回**：没加 `-w` 超时；对端不主动断开时 nc 会一直等，务必 `-w N`。
3. **`localhost` 连得上、`127.0.0.1` 连不上（或反过来）**：localhost 可能解析到 IPv6 `::1` 而服务只监听 IPv4，用 `-4` 或直接用 `127.0.0.1`。
4. **HTTP/1.1 请求没响应**：缺 `Host` 头或长连接不关闭；调试阶段用 HTTP/1.0 最省事，或加 `-w` 超时。
5. **换行用错**：文本协议要求 `\r\n`，`echo` 默认只有 `\n`，用 `printf '...\r\n'`。
6. **UDP 探测"时灵时不灵"**：UDP 无连接，`-uzv` 结果不可靠，必须实际发数据看响应。
7. **telnet 发请求被服务端报 400/协议错误**：telnet 有选项协商、非纯透传，脚本化请换 nc。
8. **telnet 连二进制端口满屏花屏**：正常现象，二进制协议用 nc 或 tcpdump，不用 telnet。
9. **OpenBSD nc 没有 `-e`**：`-e`（连接后执行程序）因安全风险在主流发行版被移除；需要类似能力应使用受控的正规远程管理方案，不要用于绕过访问控制。
10. **`nc -l` 监听地址含义**：不绑地址等于监听 `0.0.0.0`（对外暴露），只做本机调试时显式绑 `127.0.0.1`。
11. **telnet 明文**：禁止用于登录生产主机，远程管理统一 ssh。

---

上一篇：《08-lsof文件句柄排查.md》
下一篇：《10-Linux系统监控命令族.md》
