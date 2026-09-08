# lsof 文件句柄排查

> 本节目标：讲解 lsof（List Open Files）排查"谁占用了端口、文件、设备"的方法——基本输出列解读、`-i` 端口排查、`-p` 进程句柄、已删除文件与磁盘空间未释放、按用户/命令/目录过滤。学完后能够解决"端口被占起不来、文件删不掉、df 满了却找不到大文件、句柄泄漏"四类高频线上问题。本篇输出均在 Ubuntu 24.04（lsof 4.95.0）实跑验证。网络连接状态配合《01-Linux命令行速查.md》的 ss，文件占用与《07-curl网络调试.md》的本地服务场景可组合使用。

## 本章速览

- [0. lsof 解决什么问题](#0-lsof-解决什么问题)
- [1. 基本调用与输出列解读](#1-基本调用与输出列解读)
- [2. 端口占用排查](#2-端口占用排查)
- [3. 进程打开的文件](#3-进程打开的文件)
- [4. 已删除文件与磁盘空间](#4-已删除文件与磁盘空间)
- [5. 按用户命令目录过滤](#5-按用户命令目录过滤)
- [6. 实战工作流](#6-实战工作流)
- [7. 快速参考卡片](#7-快速参考卡片)
- [8. 常见问题与坑](#8-常见问题与坑)

---

## 0. lsof 解决什么问题

"文件被谁占着、端口被谁占着"这类问题没有 lsof 只能一个个猜。lsof 一次性列出进程打开的**文件描述符指向的一切**：普通文件、目录、动态库、socket、设备、管道。

| 高频问题 | lsof 打法 |
| --- | --- |
| 端口被占，服务起不来（Address already in use） | `lsof -i :8080` |
| 文件删不掉（Text file busy / 被进程占用） | `lsof /path/file` |
| df 显示磁盘满，但 du 找不到大文件 | `lsof +L1 \| grep deleted` |
| 怀疑句柄泄漏 | `lsof -p PID` 数 fd |
| 想确认某个进程还连着哪些网络 | `lsof -p PID \| grep TCP` |

> 与 `ss` 的分工：`ss` 看**连接状态**（LISTEN/ESTABLISHED、队列长度），lsof 看**进程 ↔ 资源**的归属关系。排查"端口被占"通常是 `ss -tlnp` 或 `lsof -i :port` 先拿到 PID，再决定是杀进程还是查占用者。

---

## 1. 基本调用与输出列解读

```bash
lsof                # 全部进程的打开文件（量大，一般不裸跑）
lsof -i :端口       # 谁占用该端口
lsof -p PID         # 某进程打开的文件
lsof 文件路径        # 谁打开着这个文件
lsof +L1            # 已删除但仍被打开的文件
```

输出列：

```text
COMMAND   PID USER   FD   TYPE DEVICE SIZE/OFF  NODE NAME
python3 14747  zqs  cwd    DIR   8,48    12288 73729 /tmp
python3 14747  zqs  rtd    DIR   8,48     4096     2 /
python3 14747  zqs  txt    REG   8,48  8025024 10290 /usr/bin/python3.12
python3 14747  zqs  mem    REG   8,48  5309400 14677 /usr/lib/x86_64-linux-gnu/libcrypto.so.3
python3 14747  zqs  mem    REG   8,48   202904 16040 /usr/lib/x86_64-linux-gnu/liblzma.so.5.4.5
```

| 列 | 含义 |
| --- | --- |
| `COMMAND` / `PID` / `USER` | 进程名、进程号、属主 |
| `FD` | 描述符：`cwd` 工作目录、`rtd` 根目录、`txt` 可执行文件、`mem` 映射的动态库/内存映射、数字+`u`/`w`/`r`（fd 号 + 读写）、`DEL`（已删除） |
| `TYPE` | `REG` 普通文件、`DIR` 目录、`CHR` 字符设备、`IPv4`/`IPv6` socket、`unix` 域套接字、`FIFO` 管道 |
| `DEVICE` / `SIZE/OFF` | 所在设备（主:次）/ 文件大小或偏移 |
| `NODE` | inode 号 |
| `NAME` | 文件路径或 socket 详情 |

---

## 2. 端口占用排查

```bash
$ python3 -m http.server 18080 &
$ lsof -i :18080
COMMAND   PID USER   FD   TYPE DEVICE SIZE/OFF NODE NAME
python3 14747  zqs    3u  IPv4 239009      0t0  TCP *:18080 (LISTEN)
```

- `TCP *:18080 (LISTEN)`：python3（PID 14747）正监听 18080 端口，fd 3。
- 服务起不来报 `Address already in use`：`lsof -i :端口` 找到 PID → 确认是不是旧实例 → `kill` 或处理。

常用变体：

```bash
lsof -i tcp                     # 所有 TCP 连接
lsof -i tcp:80                  # 指定协议 + 端口
lsof -i :1-1024                 # 端口段
lsof -i -sTCP:LISTEN            # 只看监听中的
lsof -i -sTCP:ESTABLISHED       # 只看已建立的连接
lsof -nP -i tcp                 # 不解析主机名/端口名，更快更准（推荐）
```

`lsof -i tcp` 实例（能看到连接状态与对端）：

```text
COMMAND     PID USER   FD   TYPE DEVICE SIZE/OFF NODE NAME
MainThrea   520  zqs   22u  IPv4  19852      0t0  TCP localhost:38455 (LISTEN)
MainThrea   520  zqs   26u  IPv4  19854      0t0  TCP localhost:38455->localhost:39384 (ESTABLISHED)
```

---

## 3. 进程打开的文件

排查"这个进程到底占着哪些文件/连接"：

```bash
$ lsof -p 14747 | head -8
COMMAND   PID USER   FD   TYPE DEVICE SIZE/OFF  NODE NAME
python3 14747  zqs  cwd    DIR   8,48    12288 73729 /tmp
python3 14747  zqs  rtd    DIR   8,48     4096     2 /
python3 14747  zqs  txt    REG   8,48  8025024 10290 /usr/bin/python3.12
python3 14747  zqs  mem    REG   8,48  5309400 14677 /usr/lib/x86_64-linux-gnu/libcrypto.so.3
python3 14747  zqs  mem    REG   8,48   2125328 90993 /usr/lib/x86_64-linux-gnu/libc.so.6
python3 14747  zqs    3u  IPv4 239009      0t0  TCP *:18080 (LISTEN)
```

- `cwd`/`rtd`/`txt`/`mem` 是每个进程都有的"常规项"（工作目录、可执行文件、加载的库），**真正要看的是数字 fd 行**（如 `3u IPv4 ... TCP *:18080`）——那是它打开的 socket/文件。
- 句柄泄漏排查：`lsof -p PID | wc -l` 观察 fd 数是否随请求增长不回落；底层等价视角是 `ls /proc/PID/fd | wc -l`。

```bash
lsof -p PID | grep TCP        # 这个进程的所有网络连接
lsof -p PID | grep REG        # 打开的文件
lsof -p PID | grep -v -E 'mem|cwd|rtd|txt'    # 去掉常规项，只看真实句柄
```

---

## 4. 已删除文件与磁盘空间

经典场景：`df` 显示磁盘满了，但 `du` 找不到大文件——**文件已被删除，但仍有进程打开着它**，空间要到进程释放才回收：

```bash
$ python3 -c "import time; f=open('/tmp/leak.txt','w'); f.write('x'*1000); f.flush(); time.sleep(6)" &
$ rm -f /tmp/leak.txt
$ lsof +L1 | grep leak
COMMAND   PID USER   FD   TYPE DEVICE SIZE/OFF NLINK  NODE NAME
python3 15416  zqs    3w   REG   8,48     1000     0 95093 /tmp/leak.txt (deleted)
```

- `+L1`：列出 link count 小于 1 的文件，即**已被删除但仍被打开**。
- `NLINK 0` 与 `(deleted)` 后缀是特征：找到 PID（15416）后重启该进程或 kill 它，磁盘空间才释放。
- 日志类程序天天打开又轮转删除的文件（如 `xxx.log.1 (deleted)`）最常见；也常发生在"程序持有临时文件句柄不关"的泄漏里。

```bash
lsof +L1 | grep deleted        # 全系统找已删除占用
lsof +L1 | grep -i log         # 常见：日志文件
```

---

## 5. 按用户命令目录过滤

```bash
lsof -u zqs                   # 某用户打开的所有文件
lsof -u ^root                 # 排除 root
lsof -c python3               # 命令名以 python3 开头的进程
lsof +D /var/log              # 递归列出目录下被打开的文件（慢，大目录慎用）
lsof /path/to/file            # 谁打开着这个文件
lsof -a -u zqs -i :8080       # -a = 同时满足（AND）；不加 -a 默认 OR
```

- `-a`（AND）很关键：默认多个条件是 OR，`lsof -u zqs -i :8080` 会列出"zqs 的所有文件"+"8080 的所有占用"；加 `-a` 才是"zqs 占用 8080 的"。
- `+D` 递归扫描会遍历目录树，生产环境对 `/var`、`/` 等大目录慎用。

---

## 6. 实战工作流

```bash
# 1) 服务起不来：Address already in use
lsof -nP -i :8080                     # 拿到占用 PID
ps -fp <PID>                          # 确认是什么进程，是旧实例就 kill

# 2) 文件删不掉：Text file busy 或 device busy
lsof /opt/app/xxx.so                  # 谁在用，处理后重试删除

# 3) df 满但 du 找不到大文件
df -h /var
lsof +L1 | grep deleted               # 找到持句柄的进程，重启/杀它

# 4) 句柄泄漏排查
pid=$(pgrep -f my_server)
watch -n 5 "lsof -p $pid | wc -l"     # 观察 fd 数是否随流量增长不回落
lsof -p $pid | grep -v -E 'mem|cwd|rtd|txt'   # 看具体是什么 fd 在涨

# 5) 某进程的网络连接
lsof -nP -p <PID> | grep -E 'TCP|UDP'
```

---

## 7. 快速参考卡片

```bash
谁占用端口：         lsof -nP -i :8080
只看监听：           lsof -nP -i -sTCP:LISTEN
某进程全部 fd：       lsof -p PID
进程的网络连接：      lsof -nP -p PID | grep TCP
谁打开某文件：        lsof /path/file
目录下被打开的文件：   lsof +D /dir
已删除仍被占用：      lsof +L1 | grep deleted
按用户/命令：         lsof -u zqs / lsof -c python3
条件 AND：           lsof -a -u zqs -i :8080
fd 计数（泄漏）：     lsof -p PID | wc -l   （等价 ls /proc/PID/fd | wc -l）
```

---

## 8. 常见问题与坑

1. **`lsof: command not found`**：部分精简系统未装，`apt install lsof` 后使用。
2. **`-i :port` 没输出不代表端口没人用**：确认协议（`-i tcp:port` vs `-i udp:port`）；监听态用 `-sTCP:LISTEN` 过滤确认。
3. **默认解析主机名很慢**：域名反解拖慢输出，`-n`（不解析域名）`-P`（不解析端口名）配合使用。
4. **`+D` 递归大目录很慢**：对 `/`、`/var` 慎用；先 `du` 缩小范围。
5. **看不到别的用户的进程**：普通用户只能看自己的；跨用户/系统进程用 root。
6. **`deleted` 文件释放不了**：必须让持句柄的进程关闭（重启/kill），删文件本身没用。
7. **FD 数字后的 `u`/`w`/`r` 是读写模式**：`3u`=fd 3 可读写、`3w`=只写、`3r`=只读。
8. **`lsof` 列出的 `mem`/`txt` 不是泄漏**：动态库映射和可执行文件是每个进程的常规项；看真实句柄要过滤或只看数字 fd。
9. **`lsof` 与 `ss` 输出对不上**：lsof 反映打开瞬间的句柄，`ss` 反映当前连接状态；两个都看是排查"连接泄漏 vs 句柄泄漏"的标准动作。
10. **`-u` 与 `-i` 不加 `-a` 是 OR**：想表达"同时满足"务必 `-a`。

---

上一篇：《07-curl网络调试.md》
下一篇：《09-nc与telnet网络调试.md》
