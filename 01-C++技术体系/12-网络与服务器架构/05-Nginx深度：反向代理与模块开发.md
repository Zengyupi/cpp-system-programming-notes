# Nginx深度：反向代理与模块开发

> 本节目标：从架构到源码层面掌握 Nginx——理解 master/worker 进程模型与 epoll 事件驱动的协作机制，吃透 conf 五级配置块与 location 匹配优先级，掌握反向代理与负载均衡的核心指令及缓冲机制，理解惊群问题的三种解决方案（accept_mutex/EPOLLEXCLUSIVE/reuseport），深入 Handler 与 Filter 模块的 11 阶段请求处理链和核心数据结构（ngx_str_t/ngx_buf_t/ngx_chain_t/ngx_rbtree_t），了解 Upstream 机制与 OpenResty 的关系。抓包验证代理行为见《../08-网络与系统工具/02-tcpdump网络抓包.md》，运维命令速查见《../08-网络与系统工具/01-Linux命令行速查.md》。

## 本章速览

- [1. Nginx 架构](#1-nginx-架构)
  - [1.1 master/worker 进程模型](#11-masterworker-进程模型)
  - [1.2 事件驱动与 epoll 异步非阻塞](#12-事件驱动与-epoll-异步非阻塞)
  - [1.3 进程间通信与信号](#13-进程间通信与信号)
- [2. conf 配置原理](#2-conf-配置原理)
  - [2.1 五级配置块层级](#21-五级配置块层级)
  - [2.2 include 机制与配置合并](#22-include-机制与配置合并)
- [3. location 匹配规则【高频】](#3-location-匹配规则高频)
  - [3.1 五种修饰符](#31-五种修饰符)
  - [3.2 匹配优先级与顺序](#32-匹配优先级与顺序)
  - [3.3 匹配示例](#33-匹配示例)
- [4. 反向代理](#4-反向代理)
  - [4.1 proxy_pass 与 URI 传递规则](#41-proxy_pass-与-uri-传递规则)
  - [4.2 proxy_set_header 与 Host 传递](#42-proxy_set_header-与-host-传递)
  - [4.3 缓冲机制](#43-缓冲机制)
- [5. 负载均衡](#5-负载均衡)
  - [5.1 upstream 四种策略](#51-upstream-四种策略)
  - [5.2 健康检查与 backup/down](#52-健康检查与-backupdown)
- [6. 惊群问题【高频】](#6-惊群问题高频)
  - [6.1 惊群成因](#61-惊群成因)
  - [6.2 accept_mutex](#62-accept_mutex)
  - [6.3 EPOLLEXCLUSIVE](#63-epollexclusive)
  - [6.4 SO_REUSEPORT](#64-so_reuseport)
- [7. Filter 模块与 Handler 模块机制](#7-filter-模块与-handler-模块机制)
  - [7.1 11 个请求处理阶段](#71-11-个请求处理阶段)
  - [7.2 Handler 模块](#72-handler-模块)
  - [7.3 Header Filter 与 Body Filter 链表](#73-header-filter-与-body-filter-链表)
- [8. 核心数据结构](#8-核心数据结构)
  - [8.1 ngx_str_t](#81-ngx_str_t)
  - [8.2 ngx_list_t 与 ngx_array_t](#82-ngx_list_t-与-ngx_array_t)
  - [8.3 ngx_buf_t 与 ngx_chain_t](#83-ngx_buf_t-与-ngx_chain_t)
  - [8.4 ngx_rbtree_t](#84-ngx_rbtree_t)
  - [8.5 ngx_cycle_t](#85-ngx_cycle_t)
- [9. Upstream 机制设计](#9-upstream-机制设计)
- [10. 与 OpenResty 的关系](#10-与-openresty-的关系)
- [11. 快速参考卡片](#11-快速参考卡片)

---

## 1. Nginx 架构

### 1.1 master/worker 进程模型

Nginx 采用**多进程**架构，启动后产生一个 master 进程和多个 worker 进程（`worker_processes` 控制，通常设为 CPU 核数）。

```text
                     ┌─────────────┐
  client ──TCP──►  :80  listen fd  (fork 前创建，子进程继承)
                     └──────┬──────┘
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
         worker #1      worker #2      worker #N
        (单线程事件循环) (单线程事件循环) (单线程事件循环)
              │             │             │
              └─────────────┼─────────────┘
                            ▼
                     master 进程
              (管理：监控/重启worker/热加载/日志切割)
```

| 角色 | 职责 | 关键特性 |
|---|---|---|
| master | 读取配置、启动/监控 worker、热加载（reload）、日志切割、平滑升级 | 不处理请求，只做管理 |
| worker | 处理客户端请求、epoll 事件循环、与后端通信 | 单线程、非阻塞、CPU 亲和（worker_cpu_affinity） |
| cache loader | 启动时加载磁盘缓存索引 | 一次性，加载完退出 |
| cache manager | 定期检查缓存大小，淘汰过期缓存 | 常驻 |

**为什么用多进程而非多线程？**
- 进程间地址空间隔离，一个 worker 崩溃不影响其他（master 自动重启）
- 避免锁竞争：每个 worker 独立事件循环，无共享数据
- 热加载/reload 时旧 worker 处理完已有连接再退出，新 worker 用新配置启动
- 代价：进程间共享数据需共享内存（如 limit_req 的共享内存区）

**worker 进程的事件循环伪码：**

```c
// ngx_process_cycle.c / worker 循环核心逻辑（简化）
void ngx_worker_process_cycle(ngx_cycle_t *cycle, void *data) {
    for (;;) {
        ngx_process_events_and_timers(cycle);  // epoll_wait + 定时器 + 事件分发
        if (ngx_terminate) break;
        if (ngx_quit) break;
        // 处理 reopen/ reopen logs 等信号
    }
}
```

### 1.2 事件驱动与 epoll 异步非阻塞

Nginx 的高性能核心 = **非阻塞 IO + epoll 边缘触发 + 单线程事件循环**。

```text
worker 事件循环：
  epoll_wait(timeout)  ← timeout 取最近定时器到期时间
       │
       ├─ 可读事件 → recv() 尽可能多读（ET 模式必须读到 EAGAIN）
       ├─ 可写事件 → send() 尽可能多写
       ├─ 定时器到期 → 红黑树中取出所有到期节点执行
       └─ 无事件 → 继续循环（不会空转，epoll_wait 阻塞）
```

**关键设计点：**
- **边缘触发（EPOLLET）**：fd 状态变化时只通知一次，必须一次性读完/写完直到 EAGAIN，否则剩余数据不会再通知
- **非阻塞 socket**：所有 socket 设为 NONBLOCK，read/write 不会阻塞 worker
- **单线程**：一个 worker 同时处理数万连接，靠事件驱动而非线程切换
- **定时器用红黑树**：`ngx_event_timer_rbtree`，key 为到期时间，O(logN) 插入删除，O(1) 取最近到期

### 1.3 进程间通信与信号

master 通过**信号**控制 worker：

| 信号 | 作用 |
|---|---|
| TERM/INT | 快速停止（直接杀 worker） |
| QUIT | 优雅停止（worker 处理完当前连接再退出） |
| HUP | 热加载配置（reload）：新 worker 启动 + 旧 worker 优雅退出 |
| USR1 | 重新打开日志文件（日志切割） |
| USR2 | 平滑升级可执行文件（新旧 master 共存） |
| WINCH | 优雅停止旧 master 的 worker（配合 USR2 升级） |

```bash
# 热加载（WSL Ubuntu 24.04 实跑命令格式）
nginx -s reload        # master 发 HUP 给自己
nginx -s reopen        # 重新打开日志
nginx -s quit          # 优雅停止
```

---

## 2. conf 配置原理

### 2.1 五级配置块层级

Nginx 配置是**树形嵌套结构**，指令有明确的作用域：

```nginx
# ===== main 块（全局）=====
user  nginx;
worker_processes  auto;
error_log  /var/log/nginx/error.log warn;
pid  /var/run/nginx.pid;

events {
    worker_connections  10240;
    use  epoll;
    multi_accept  on;
}

# ===== http 块 =====
http {
    include       mime.types;
    default_type  application/octet-stream;
    sendfile      on;
    keepalive_timeout  65;

    # ===== server 块（虚拟主机）=====
    server {
        listen       80;
        server_name  example.com;

        # ===== location 块（URI 匹配）=====
        location / {
            root   /usr/share/nginx/html;
            index  index.html;
        }

        location /api/ {
            proxy_pass http://backend;
        }
    }
}
```

| 层级 | 作用域 | 典型指令 |
|---|---|---|
| main | 全局，进程级 | user, worker_processes, error_log, pid |
| events | 事件模型 | worker_connections, use, accept_mutex |
| http | HTTP 协议全局 | include, sendfile, keepalive_timeout, upstream |
| server | 虚拟主机 | listen, server_name, access_log |
| location | URI 路径 | root, proxy_pass, rewrite, limit_req |

### 2.2 include 机制与配置合并

`include` 指令在配置解析阶段**文本展开**，支持通配符：

```nginx
http {
    include /etc/nginx/conf.d/*.conf;   # 引入所有虚拟主机配置
    include /etc/nginx/common/proxy.conf;  # 引入公共代理配置
}
```

**配置合并规则**：子块继承父块指令，子块中显式声明则覆盖父块。例如 `proxy_read_timeout` 在 http 块设 60s，某个 location 设 30s，则该 location 用 30s。

**配置解析阶段**（ngx_conf.c）：
1. 词法分析：逐 token 读取
2. 语法分析：根据指令的 `ngx_command_t` 定义找到 set 函数
3. 创建配置结构体：每个模块在每个层级有自己的配置结构体（`ngx_http_conf_ctx_t`）
4. 合并：子层级配置创建时从父层级拷贝并覆盖

---

## 3. location 匹配规则【高频】

### 3.1 五种修饰符

| 修饰符 | 类型 | 说明 |
|---|---|---|
| `=` | 精确匹配 | URI 完全相等才命中，优先级最高 |
| `^~` | 前缀匹配（优先） | 最长前缀匹配后不再检查正则 |
| `~` | 正则匹配（大小写敏感） | 按配置顺序检查，第一个命中即停止 |
| `~*` | 正则匹配（大小写不敏感） | 同上，忽略大小写 |
| 无修饰符 | 普通前缀匹配 | 最长前缀匹配，之后仍会检查正则 |

### 3.2 匹配优先级与顺序

Nginx location 匹配的**完整算法**：

```text
1. 先检查精确匹配 = → 命中则立即返回
2. 检查所有前缀匹配（含 ^~ 和无修饰符）→ 记录最长匹配
3. 若最长匹配是 ^~ → 立即返回，不再检查正则
4. 否则按配置文件顺序检查正则 ~ / ~* → 第一个命中返回
5. 若无正则命中 → 使用第 2 步记录的最长前缀匹配
6. 都没命中 → 404
```

**优先级总结**：`=` > `^~`（最长前缀）> `~`/`~*`（按顺序）> 无修饰符（最长前缀）

### 3.3 匹配示例

```nginx
location = /login {       # ① 精确匹配，仅 /login
    return 200 "exact\n";
}
location ^~ /static/ {    # ② 前缀优先，/static/* 不再走正则
    root /data;
}
location ~* \.(jpg|png)$ { # ③ 正则，大小写不敏感
    root /data/images;
}
location / {              # ④ 通用前缀
    proxy_pass http://backend;
}
```

| 请求 URI | 命中 | 原因 |
|---|---|---|
| `/login` | ① | 精确匹配 |
| `/static/logo.png` | ② | ^~ 前缀命中，跳过正则 |
| `/assets/photo.JPG` | ③ | 正则 ~* 命中 |
| `/api/user` | ④ | 最长前缀 / |

---

## 4. 反向代理

### 4.1 proxy_pass 与 URI 传递规则

`proxy_pass` 后是否带 URI 路径，决定了请求 URI 如何传递给后端：

```nginx
location /api/ {
    # 带 URI（末尾有路径）：Nginx 会用 proxy_pass 的路径替换 location 匹配部分
    proxy_pass http://backend/v1/;
    # 请求 /api/user → 后端收到 /v1/user
}

location /api2/ {
    # 不带 URI（只有 host:port）：原始 URI 透传
    proxy_pass http://backend;
    # 请求 /api2/user → 后端收到 /api2/user
}
```

**关键规则**：proxy_pass 后若包含路径（`http://host/xxx`），则 location 匹配到的前缀被替换为该路径；若只有 `http://host`，则原始 URI 完整透传。

### 4.2 proxy_set_header 与 Host 传递

默认 Nginx 转发时会设置两个头：
- `Host` 设为 proxy_pass 中的 host（而非客户端原始 Host）
- `Connection` 设为 `close`

**生产环境必须修正**：

```nginx
location / {
    proxy_pass http://backend;
    proxy_set_header Host $host;              # 传递原始 Host（后端虚拟主机依赖）
    proxy_set_header X-Real-IP $remote_addr;  # 传递真实客户端 IP
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;  # 代理链
    proxy_set_header X-Forwarded-Proto $scheme;  # 原始协议（http/https）
}
```

`$proxy_add_x_forwarded_for` = 客户端已有 XFF（如有）+ 当前节点 IP，多级代理时形成链路。

### 4.3 缓冲机制

Nginx 反向代理默认**开启缓冲**：先把后端响应读完存到磁盘/内存，再慢慢发给客户端。

| 指令 | 默认值 | 作用 |
|---|---|---|
| `proxy_buffering` | on | 总开关 |
| `proxy_buffer_size` | 4k/8k | 读响应头的 buffer 大小 |
| `proxy_buffers` | 8 4k/8k | 读响应体的 buffer 数量和单大小 |
| `proxy_busy_buffers_size` | 8k/16k | 同时发给客户端的 buffer 上限 |
| `proxy_max_temp_file_size` | 1024m | 响应超过 buffers 时落盘的上限 |
| `proxy_temp_file_write_size` | 8k/16k | 落盘时单次写入大小 |

**缓冲 vs 无缓冲**：
- 缓冲（默认）：后端快速释放连接，Nginx 缓存后按客户端速度发；适合慢客户端
- 无缓冲（`proxy_buffering off`）：后端响应同步转发给客户端，后端连接占用时间长；适合流式响应（SSE/视频）

```nginx
# SSE 流式响应必须关缓冲
location /sse/ {
    proxy_pass http://backend;
    proxy_buffering off;
    proxy_cache off;
    proxy_set_header Connection '';
    proxy_http_version 1.1;
    chunked_transfer_encoding off;
}
```

---

## 5. 负载均衡

### 5.1 upstream 四种策略

```nginx
upstream backend {
    # ① 轮询（默认）：按顺序轮流分配
    server 10.0.0.1:8080;
    server 10.0.0.2:8080;

    # ② 加权轮询：weight 越大分配越多
    # server 10.0.0.1:8080 weight=3;
    # server 10.0.0.2:8080 weight=1;

    # ③ ip_hash：按客户端 IP 哈希，同一客户端固定到同一后端（会话保持）
    # ip_hash;

    # ④ least_conn：优先分配给当前连接数最少的后端
    # least_conn;
}
```

| 策略 | 算法 | 适用场景 | 缺点 |
|---|---|---|---|
| 轮询（round-robin） | 顺序轮流 | 后端性能一致、无状态 | 不考虑负载差异 |
| 加权轮询 | 带权重的平滑轮询（Nginx 用平滑加权算法） | 后端性能不均 | 权重需手动调 |
| ip_hash | IP 前 3 段（C 类）哈希 | 需要会话保持 | 同一 NAT 出口用户集中到一台 |
| least_conn | 当前活跃连接数最少优先 | 请求处理时长差异大 | 不考虑响应时间 |

**Nginx 平滑加权轮询算法**（避免某台高权重机器被连续命中）：每台有 `current_weight`，每次选最大的，选中后 `current_weight -= total_weight`，每轮 `current_weight += weight`。

### 5.2 健康检查与 backup/down

```nginx
upstream backend {
    server 10.0.0.1:8080 max_fails=3 fail_timeout=30s;
    server 10.0.0.2:8080 max_fails=3 fail_timeout=30s;
    server 10.0.0.3:8080 backup;    # 备用节点，主节点全挂才启用
    server 10.0.0.4:8080 down;      # 永久下线（维护中）
    server 10.0.0.5:8080 max_conns=100;  # 最大并发连接数（1.11.5+）
}
```

**被动健康检查**（开源版 Nginx 内置）：
- `max_fails=N`：连续失败 N 次后标记为不可用
- `fail_timeout=T`：不可用持续 T 秒后重新试探
- 失败判定：连接超时/被拒/HTTP 502/503/504（由 `proxy_next_upstream` 定义）

**主动健康检查**：开源版不支持，需 Nginx Plus 或 OpenResty + lua-resty-upstream-healthcheck。

---

## 6. 惊群问题【高频】

### 6.1 惊群成因

多个 worker 进程继承同一个 listen fd 并都注册到各自的 epoll。当一个新连接到来时，**内核唤醒所有等待该 fd 的进程**，但只有一个能 accept 成功，其他被唤醒后发现 EAGAIN 又睡回去——这就是惊群（thundering herd）。

```text
新连接到来 → 内核唤醒 worker1/worker2/.../workerN（全部唤醒）
             → worker1 accept 成功，处理请求
             → worker2~N accept 返回 EAGAIN，白白消耗一次调度
```

危害：N 个 worker 时，每次新连接导致 N 次进程唤醒，CPU 调度开销放大。

### 6.2 accept_mutex

Nginx 经典解决方案：**跨进程互斥锁**。worker 在进入 epoll_wait 前先抢 accept_mutex，抢到的才把 listen fd 加入 epoll，没抢到的不监听 listen fd。

```c
// 简化逻辑（ngx_event.c）
if (ngx_use_accept_mutex) {
    if (ngx_trylock_accept_mutex(cycle) == NGX_OK) {
        // 抢到锁：把 listen fd 加入 epoll（EPOLLIN）
        ngx_enable_accept_events(cycle);
    } else {
        // 没抢到：从 epoll 移除 listen fd，不会被新连接唤醒
        ngx_disable_accept_events(cycle, 0);
    }
}
ngx_process_events(cycle, timer, flags);  // epoll_wait
if (ngx_accept_mutex_held) {
    ngx_shmtx_unlock(&ngx_accept_mutex);  // 处理完事件释放锁
}
```

**缺点**：
- 锁竞争：高并发下抢锁本身有开销
- 负载不均：抢到锁的 worker 一次性 accept 多个连接（`multi_accept on`），可能导致某 worker 连接数偏多
- Nginx 1.11.3 起默认关闭（`accept_mutex off`），因为 EPOLLEXCLUSIVE 更优

### 6.3 EPOLLEXCLUSIVE

Linux 4.5+ 引入的 epoll 标志位：**同一 fd 上的 EPOLLIN 事件只唤醒一个注册了 EPOLLEXCLUSIVE 的进程**，从内核层面解决惊群。

```c
// Nginx 自动检测并使用（ngx_epoll_module.c）
ev.events = EPOLLIN | EPOLLEXCLUSIVE;  // 只唤醒一个 worker
```

**优点**：无锁、内核调度、负载更均匀（内核选唤醒哪个进程）
**限制**：需要 Linux 4.5+，Nginx 1.11.3+ 自动启用

### 6.4 SO_REUSEPORT

Linux 3.9+ 引入的 socket 选项：**多个进程可以 bind 同一个端口**，内核在连接到达时自动分配给其中一个进程（按哈希）。

```nginx
# 每个 worker 独立创建 listen socket（而非继承 master 的）
server {
    listen 80 reuseport;  # Nginx 1.9.1+ 支持
}
```

```text
SO_REUSEPORT 模式：
  worker1 → bind(:80) ─┐
  worker2 → bind(:80) ─┤ 内核按哈希分配新连接
  worker3 → bind(:80) ─┘
```

**三种方案对比**：

| 方案 | 内核版本 | 是否有锁 | 负载均衡 | 特点 |
|---|---|---|---|---|
| accept_mutex | 任意 | 有（用户态自旋锁） | 不均 | 经典方案，已默认关闭 |
| EPOLLEXCLUSIVE | 4.5+ | 无 | 内核选择 | 共享 listen fd，只唤醒一个 |
| SO_REUSEPORT | 3.9+ | 无 | 内核哈希 | 每进程独立 socket，连接分布最均匀 |

**生产建议**：Linux 4.5+ 用 EPOLLEXCLUSIVE（Nginx 默认）；需要极致均匀分布用 `reuseport`。

---

## 7. Filter 模块与 Handler 模块机制

### 7.1 11 个请求处理阶段

Nginx 将 HTTP 请求处理分为 11 个阶段（`ngx_http_core_module.h` 的 `ngx_http_phases`），每个阶段可挂载多个 handler：

| 阶段 | 枚举值 | 职责 | 典型模块 |
|---|---|---|---|
| 1. POST_READ | NGX_HTTP_POST_READ_PHASE | 读取请求后第一阶段 | realip（获取真实 IP） |
| 2. SERVER_REWRITE | NGX_HTTP_SERVER_REWRITE_PHASE | server 级 rewrite | rewrite |
| 3. FIND_CONFIG | NGX_HTTP_FIND_CONFIG_PHASE | 匹配 location（内部阶段，不可挂载） | core |
| 4. REWRITE | NGX_HTTP_REWRITE_PHASE | location 级 rewrite | rewrite |
| 5. POST_REWRITE | NGX_HTTP_POST_REWRITE_PHASE | rewrite 后跳转（内部阶段） | core |
| 6. PREACCESS | NGX_HTTP_PREACCESS_PHASE | 访问控制前 | limit_conn（连接数限制） |
| 7. ACCESS | NGX_HTTP_ACCESS_PHASE | 访问控制 | auth_basic, access（IP 黑白名单） |
| 8. POST_ACCESS | NGX_HTTP_POST_ACCESS_PHASE | access 后处理（内部阶段） | core |
| 9. PRECONTENT | NGX_HTTP_PRECONTENT_PHASE | 内容生成前 | limit_req（限流）, mirror（流量镜像） |
| 10. CONTENT | NGX_HTTP_CONTENT_PHASE | 生成响应内容 | index, autoindex, proxy_pass, static |
| 11. LOG | NGX_HTTP_LOG_PHASE | 记录日志 | access_log |

```text
请求流转：
POST_READ → SERVER_REWRITE → FIND_CONFIG → REWRITE → POST_REWRITE
  → PREACCESS → ACCESS → POST_ACCESS → PRECONTENT → CONTENT → LOG
```

每个阶段的 handler 返回值决定下一步：
- `NGX_OK`：继续下一阶段
- `NGX_DECLINED`：本阶段下一个 handler
- `NGX_AGAIN`/`NGX_DONE`：挂起，等事件（异步）
- 其他（如 403）：直接结束请求

### 7.2 Handler 模块

Handler 模块挂载到 CONTENT 阶段，负责**生成响应内容**。一个 location 只能有一个 content handler（后注册的覆盖先注册的）。

常见 content handler：
- 静态文件：`ngx_http_static_module`（root/alias）
- 反向代理：`ngx_http_proxy_module`（proxy_pass）
- FastCGI：`ngx_http_fastcgi_module`
- 目录列表：`ngx_http_autoindex_module`

**Handler 模块开发骨架**（来源：Nginx 官方文档 + 《深入理解 Nginx》陶辉）：

```c
// 模块配置结构体
typedef struct {
    ngx_str_t  hello_string;
} ngx_http_hello_loc_conf_t;

// 指令定义
static ngx_command_t ngx_http_hello_commands[] = {
    { ngx_string("hello_string"),
      NGX_HTTP_LOC_CONF|NGX_CONF_TAKE1,
      ngx_conf_set_str_slot,
      NGX_HTTP_LOC_CONF_OFFSET,
      offsetof(ngx_http_hello_loc_conf_t, hello_string),
      NULL },
    ngx_null_command
};

// content handler
static ngx_int_t ngx_http_hello_handler(ngx_http_request_t *r) {
    ngx_http_hello_loc_conf_t *hlcf = ngx_http_get_module_loc_conf(r, ngx_http_hello_module);
    r->headers_out.content_type.len = sizeof("text/plain") - 1;
    r->headers_out.content_type.data = (u_char *)"text/plain";
    r->headers_out.status = NGX_HTTP_OK;
    r->headers_out.content_length_n = hlcf->hello_string.len;
    ngx_http_send_header(r);
    ngx_buf_t *b = ngx_create_temp_buf(r->pool, hlcf->hello_string.len);
    ngx_memcpy(b->pos, hlcf->hello_string.data, hlcf->hello_string.len);
    b->last = b->pos + hlcf->hello_string.len;
    b->last_buf = 1;
    ngx_chain_t out = { .buf = b, .next = NULL };
    return ngx_http_output_filter(r, &out);
}
```

### 7.3 Header Filter 与 Body Filter 链表

Filter 模块**不生成内容**，而是对 Handler 产出的响应头/响应体做加工。所有 Filter 组成**链表**，按注册顺序依次调用。

```text
ngx_http_top_header_filter → filter1 → filter2 → ... → ngx_http_header_filter（写响应头到 socket）
ngx_http_top_body_filter   → filter1 → filter2 → ... → ngx_http_write_filter（写响应体到 socket）
```

**注册机制**：每个 filter 模块在 postconfiguration 中把自己插入链表头部：

```c
static ngx_http_output_header_filter_pt  ngx_http_next_header_filter;
static ngx_http_output_body_filter_pt    ngx_http_next_body_filter;

static ngx_int_t ngx_http_hello_filter_init(ngx_conf_t *cf) {
    // 插入 header filter 链表头部
    ngx_http_next_header_filter = ngx_http_top_header_filter;
    ngx_http_top_header_filter = ngx_http_hello_header_filter;
    // 插入 body filter 链表头部
    ngx_http_next_body_filter = ngx_http_top_body_filter;
    ngx_http_top_body_filter = ngx_http_hello_body_filter;
    return NGX_OK;
}
```

**常见内置 Filter**：

| Filter 模块 | 作用 |
|---|---|
| ngx_http_not_modified_filter | 304 未修改判断（If-Modified-Since/ETag） |
| ngx_http_gzip_filter | gzip 压缩响应体 |
| ngx_http_chunked_filter | chunked 传输编码 |
| ngx_http_range_filter | Range 请求分片 |
| ngx_http_headers_filter | 添加/修改响应头（add_header） |
| ngx_http_sub_filter | 响应体字符串替换 |
| ngx_http_addition_filter | 响应前后追加内容 |

**执行顺序**：后注册的先执行（链表头插法）。Nginx 核心 filter 按固定顺序在 `ngx_http_core_module.c` 中注册。

---

## 8. 核心数据结构

### 8.1 ngx_str_t

Nginx 字符串不是 C 风格 `\0` 结尾，而是**长度 + 指针**：

```c
typedef struct {
    size_t    len;   // 长度
    u_char   *data;  // 数据指针（不保证 \0 结尾）
} ngx_str_t;
```

设计原因：避免 `strlen` O(n) 遍历；子串只需调整指针和长度，零拷贝。操作宏：`ngx_string("xxx")`（编译期构造）、`ngx_str_null`（空串）、`ngx_strcmp`（比较）。

### 8.2 ngx_list_t 与 ngx_array_t

**ngx_array_t**（动态数组，元素连续存储）：

```c
typedef struct {
    void        *elts;    // 数组首地址
    ngx_uint_t   nelts;   // 已用元素数
    size_t       size;    // 单元素大小
    ngx_uint_t   nalloc;  // 已分配容量
    ngx_pool_t  *pool;
} ngx_array_t;
```

**ngx_list_t**（链表，每个节点是一个固定大小的数组，兼顾数组局部性和链表动态扩展）：

```c
typedef struct ngx_list_part_s  ngx_list_part_t;
struct ngx_list_part_s {
    void             *elts;   // 本节点数组
    ngx_uint_t        nelts;  // 已用数
    ngx_list_part_t  *next;
};
typedef struct {
    ngx_list_part_t  *last;   // 尾节点
    ngx_list_part_t   part;   // 首节点（内嵌）
    size_t            size;   // 单元素大小
    ngx_uint_t        nalloc; // 每节点容量
    ngx_pool_t       *pool;
} ngx_list_t;
```

### 8.3 ngx_buf_t 与 ngx_chain_t

**ngx_buf_t**（缓冲区，Nginx IO 的核心抽象）：

```c
struct ngx_buf_s {
    u_char       *pos;       // 读指针（当前消费位置）
    u_char       *last;      // 写指针（有效数据末尾）
    u_char       *start;     // buffer 起始
    u_char       *end;       // buffer 末尾
    u_char       *file_pos;  // 文件读指针（sendfile 用）
    u_char       *file_last;
    ngx_file_t   *file;      // 关联文件（sendfile 零拷贝）
    // 标志位
    unsigned      memory:1;      // 内存 buffer
    unsigned      in_file:1;     // 文件 buffer
    unsigned      last_buf:1;    // 最后一个 buffer（响应结束）
    unsigned      last_in_chain:1; // chain 中最后一个
    unsigned      flush:1;       // 立即刷新
    unsigned      temporary:1;   // 可修改内容
    // ...
};
```

**ngx_chain_t**（buffer 链表，将多个 buf 串联，实现 scatter-gather IO）：

```c
struct ngx_chain_s {
    ngx_buf_t    *buf;
    ngx_chain_t  *next;
};
```

设计要点：
- 响应体由 `ngx_chain_t` 链表表示，每个 buf 可指向内存或文件
- `writev` 系统调用一次发送多个 buf（分散写）
- `sendfile` 零拷贝：文件 buf 直接从文件到 socket，不经过用户态

### 8.4 ngx_rbtree_t

Nginx 红黑树用于**定时器管理**和**缓存查找**。key 为 `ngx_rbtree_key_t`（uintptr_t）。

```c
// 定时器红黑树：key = 到期时间（毫秒）
ngx_rbtree_t  ngx_event_timer_rbtree;

// 插入定时器事件
ngx_rbtree_insert(&ngx_event_timer_rbtree, &ev->timer);

// 取最近到期（最左节点）
node = ngx_rbtree_min(root, sentinel);
```

定时器事件结构体内嵌 `ngx_rbtree_node_t timer`，通过 `ngx_rbtree_data(node, ngx_event_t, timer)` 取回事件指针。

### 8.5 ngx_cycle_t

Nginx 的**全局上下文**，每个进程持有一个，包含所有核心资源：

```c
struct ngx_cycle_s {
    void                  **conf_ctx;       // 所有模块配置数组
    ngx_pool_t             *pool;           // 全局内存池
    ngx_log_t              *log;
    ngx_connection_t       *connections;    // 连接池数组
    ngx_event_t            *read_events;    // 读事件池
    ngx_event_t            *write_events;   // 写事件池
    ngx_cycle_t            *old_cycle;      // reload 时指向上一版
    ngx_str_t               conf_file;      // 配置文件路径
    ngx_str_t               prefix;         // 安装前缀
    ngx_array_t             listening;      // 监听端口数组
    ngx_array_t             open_files;     // 打开的文件
    ngx_list_t              shared_memory;  // 共享内存区
    // ...
};
```

reload 时创建新 cycle，旧 worker 持有旧 cycle 处理完连接后退出，新 worker 用新 cycle。

---

## 9. Upstream 机制设计

Upstream 是 Nginx 与**后端服务器通信**的抽象层，proxy/fastcgi/uwsgi/memcached 都基于它。

```text
客户端请求 → content handler (proxy module)
              → 创建 ngx_http_upstream_t
              → 从 upstream 选取后端服务器（负载均衡算法）
              → 建立连接（或复用 keepalive 连接）
              → 发送请求到后端
              → 接收响应头 → header filter 链
              → 接收响应体 → body filter 链（缓冲/落盘/转发）
              → 完成 → 连接归还 keepalive 池或关闭
```

**关键结构体** `ngx_http_upstream_t`：

```c
typedef struct {
    ngx_http_upstream_conf_t  *conf;       // 配置（超时/缓冲等）
    ngx_chain_t               *request_bufs; // 发给后端的请求
    ngx_http_upstream_resolved_t *resolved; // 解析后的后端地址
    ngx_peer_connection_t      peer;        // 后端连接（含 upstream 选取逻辑）
    ngx_buf_t                 *buffer;      // 读后端响应的 buffer
    ngx_chain_t               *bufs;        // 缓冲链表
    ngx_int_t                (*input_filter)(void *data, ssize_t bytes); // 收到后端数据的回调
    void                      *input_filter_ctx;
    unsigned                  request_sent:1;
    unsigned                  header_sent:1;
} ngx_http_upstream_t;
```

**负载均衡选取逻辑**在 `ngx_http_upstream_init_request` → `ngx_http_upstream_get_peer`，调用 `peer.get` 函数指针，不同策略（round-robin/ip_hash/least_conn）注册不同的 get 函数。

**失败转移**：`proxy_next_upstream error timeout http_502 http_503` 定义哪些情况尝试下一个后端，`proxy_next_upstream_tries` 限制最大重试次数。

---

## 10. 与 OpenResty 的关系

**OpenResty = Nginx + LuaJIT + 精选 Lua 库**，由章亦春（agentzh）发起，核心是 `ngx_lua` 模块——将 Lua 嵌入 Nginx 的请求处理各阶段。

```text
OpenResty 架构：
  Nginx 核心（C）
    └─ ngx_lua 模块（C + Lua）
         ├─ LuaJIT（高性能 Lua 解释器/JIT）
         ├─ cosocket（Lua 层非阻塞 socket）
         ├─ shared dict（Lua 共享内存字典）
         └─ 精选库：lua-resty-redis/mysql/dns/lock/...
```

**Lua 可介入的阶段**（比 C 模块开发简单得多）：

| 阶段 | 指令 | 用途 |
|---|---|---|
| rewrite | rewrite_by_lua | URL 重写、变量设置 |
| access | access_by_lua | 鉴权、限流、动态路由 |
| content | content_by_lua | 生成响应（可调用后端） |
| header filter | header_filter_by_lua | 修改响应头 |
| body filter | body_filter_by_lua | 修改响应体 |
| log | log_by_lua | 日志/统计 |
| balancer | balancer_by_lua | 动态负载均衡（动态选后端） |
| ssl | ssl_certificate_by_lua | 动态证书 |

**与原生 Nginx C 模块的对比**：

| 维度 | Nginx C 模块 | OpenResty (Lua) |
|---|---|---|
| 开发效率 | 低（C 语言、编译、重启） | 高（Lua 脚本、reload 即生效） |
| 性能 | 极高（原生） | 高（LuaJIT + cosocket 非阻塞） |
| 动态能力 | 弱（配置需 reload） | 强（运行时动态路由/限流/选后端） |
| 生态 | 官方模块 + 第三方 | lua-resty-* 丰富生态 |
| 适用 | 核心功能/极致性能 | 业务逻辑/网关/动态策略 |

**典型应用**：API 网关（APISIX 基于 OpenResty）、动态 WAF、灰度发布、A/B 测试、自适应限流。

---

## 11. 快速参考卡片

### 常用配置指令速查

```text
# 全局
worker_processes auto;              # worker 数 = CPU 核数
worker_cpu_affinity auto;           # CPU 亲和绑定
worker_rlimit_nofile 65535;         # 单进程文件句柄上限

# events
events {
    use epoll;
    worker_connections 10240;       # 单 worker 最大连接数
    multi_accept on;                # 一次 accept 多个连接
    accept_mutex off;               # 4.5+ 内核用 EPOLLEXCLUSIVE，关互斥锁
}

# http 性能
http {
    sendfile on;                    # 零拷贝发送静态文件
    tcp_nopush on;                  # 配合 sendfile，攒包发送
    tcp_nodelay on;                 # 禁用 Nagle，低延迟
    keepalive_timeout 65;
    keepalive_requests 1000;        # 一个长连接最多请求数
    client_header_buffer_size 4k;
    large_client_header_buffers 4 16k;
    client_max_body_size 20m;       # 上传上限
}

# 反向代理必设
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_connect_timeout 5s;           # 连接后端超时
proxy_read_timeout 60s;             # 读后端响应超时
proxy_send_timeout 60s;
proxy_buffering on;                 # 普通请求开缓冲；SSE/流式关

# 负载均衡
upstream backend {
    least_conn;                     # 或 ip_hash / 默认轮询
    server 10.0.0.1:8080 weight=3 max_fails=3 fail_timeout=30s;
    server 10.0.0.2:8080 weight=1 max_fails=3 fail_timeout=30s;
    server 10.0.0.3:8080 backup;
    keepalive 32;                   # 到后端的长连接池大小
}
```

### 常见坑

1. **proxy_pass 路径替换错误**：`location /api/ { proxy_pass http://backend; }` 透传 `/api/`，而 `proxy_pass http://backend/v1/;` 会替换为 `/v1/`。混淆导致后端 404——配置后用 curl 验证后端收到的 URI。
2. **Host 头未传递**：默认 proxy_pass 把 Host 设为后端地址，后端虚拟主机路由失败。必须 `proxy_set_header Host $host;`。
3. **ip_hash 导致负载严重不均**：公司出口 NAT 后所有用户同一 IP，全打到一台。用 least_conn 或在七层做会话保持（cookie）。
4. **WebSocket 代理失败**：默认 HTTP/1.0 + Connection:close，需 `proxy_http_version 1.1; proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade";`。
5. **SSE/流式响应被缓冲**：proxy_buffering 默认 on，SSE 消息攒满 buffer 才发，客户端收不到实时推送。必须 `proxy_buffering off;`。
6. **worker_connections 不够**：Nginx 作为反向代理时每个客户端连接占 2 个连接（客户端+后端），实际并发 = worker_connections × worker_processes / 2。
7. **reload 后旧 worker 不退出**：有长连接（WebSocket/大文件下载）一直占用，旧 worker 不会退出。用 `worker_shutdown_timeout 30s` 强制超时。
8. **413 Request Entity Too Large**：`client_max_body_size` 默认 1m，上传大文件被拒。按需调大。
9. **upstream 健康检查只有被动模式**：开源版无主动健康检查，后端进程挂了但端口还在（如僵死）不会被剔除。需 OpenResty + lua-resty-upstream-healthcheck 或 Nginx Plus。
10. **location 正则顺序敏感**：`~` 正则按配置文件顺序匹配，第一个命中即返回。把更具体的正则放前面。

---

上一篇：《04-Reactor与高性能网络库.md》
下一篇：《06-gRPC与RPC框架原理.md》
