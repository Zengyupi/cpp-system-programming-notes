# OpenResty与WAF防护（Nginx+Lua的Web应用防火墙）

> 本节目标：掌握 OpenResty 的架构（Nginx + LuaJIT + lua-resty 库），理解 Nginx 请求处理各阶段嵌入 Lua 的机制，能设计并实现 WAF 防护体系（IP黑白名单/URL过滤/CC防护/SQL注入/XSS防御），掌握 lua-resty 库的使用和性能优化，对比 Nginx 原生模块选型。

## 本章速览

- [1. OpenResty 架构与核心思想](#1-openresty-架构与核心思想)
- [2. Lua 与 Nginx 集成：请求处理阶段](#2-lua-与-nginx-集成请求处理阶段)
- [3. lua-resty 库生态](#3-lua-resty-库生态)
- [4. WAF 架构设计](#4-waf-架构设计)
  - [4.1 IP 黑白名单](#41-ip-黑白名单)
  - [4.2 URL 过滤与 User-Agent 识别](#42-url-过滤与-user-agent-识别)
  - [4.3 Referer 验证与 Cookie 过滤](#43-referer-验证与-cookie-过滤)
  - [4.4 HTTP 方法限制](#44-http-方法限制)
- [5. CC 攻击防护](#5-cc-攻击防护)
- [6. 深度参数过滤：SQL 注入与 XSS](#6-深度参数过滤sql-注入与-xss)
- [7. 日志记录与规则动态更新](#7-日志记录与规则动态更新)
- [8. 性能考量与 Nginx 原生模块对比](#8-性能考量与-nginx-原生模块对比)
- [9. 快速参考卡片](#9-快速参考卡片)
- [10. 常见问题与坑](#10-常见问题与坑)

---

## 1. OpenResty 架构与核心思想

OpenResty 是一个基于 **Nginx + LuaJIT** 的 Web 平台，将 Lua 脚本嵌入 Nginx 的请求处理流程，在 C 级别的 Nginx 性能上获得脚本级别的灵活扩展能力。

**核心组件：**

| 组件 | 说明 |
| --- | --- |
| Nginx | 高性能 Web 服务器/反向代理，事件驱动，C 语言实现 |
| LuaJIT | Lua 的即时编译器，比标准 Lua 快数倍，支持 FFI 调用 C 库 |
| ngx_lua | Nginx 模块，将 Lua 嵌入 Nginx 各请求处理阶段 |
| lua-resty 库 | 精选的 Lua 库集合（redis/mysql/http/dns/lock 等），基于 cosocket 非阻塞 IO |

**核心思想：**

- **在 Nginx 内部写业务逻辑**：不需要后端应用服务器，直接在 Nginx 层用 Lua 处理请求、访问数据库、缓存
- **非阻塞 IO**：Lua 代码中的网络调用（redis/mysql/http）通过 cosocket 实现非阻塞，不阻塞 Nginx worker
- **共享内存**：`lua_shared_dict` 提供 worker 间共享的内存字典，用于缓存、限流计数
- **每个请求一个 Lua 协程**：Nginx 为每个请求创建独立的 Lua 协程，请求间隔离

**与纯 Nginx 的区别：**

| 维度 | 纯 Nginx | OpenResty |
| --- | --- | --- |
| 扩展方式 | C 模块开发（复杂，需重新编译） | Lua 脚本（简单，热加载） |
| 业务逻辑 | 只能通过配置和模块 | 可在 Nginx 层直接写复杂逻辑 |
| 动态配置 | reload（有连接中断风险） | Lua 动态修改，无需 reload |
| 外部服务访问 | 需 C 模块或反向代理 | lua-resty 直接非阻塞访问 redis/mysql |
| 学习曲线 | 配置语法 + C 开发 | Nginx 配置 + Lua 语言 |

---

## 2. Lua 与 Nginx 集成：请求处理阶段

Nginx 请求处理分为 11 个阶段，ngx_lua 在各阶段提供对应的 Lua 钩子：

```text
客户端请求
    |
    v
[1] post-read (read_request_body 之前)
    |  lua_code: access_by_lua 可在此阶段提前拦截
    v
[2] server-rewrite (server 级 rewrite)
    |  lua_code: rewrite_by_lua
    v
[3] find-config (location 匹配)
    v
[4] rewrite (location 级 rewrite)
    |  lua_code: rewrite_by_lua
    v
[5] post-rewrite (rewrite 后跳转)
    v
[6] preaccess (访问控制前)
    |  lua_code: access_by_lua  (WAF 主要工作阶段！)
    v
[7] access (访问控制，如 allow/deny)
    v
[8] post-access (访问控制后)
    v
[9] try-files (try_files 处理)
    v
[10] content (内容生成，proxy_pass 等)
     |  lua_code: content_by_lua
     v
[11] log (日志记录)
     |  lua_code: log_by_lua
```

**各阶段 Lua 指令：**

| 指令 | 阶段 | 用途 |
| --- | --- | --- |
| `set_by_lua` | rewrite | 复杂变量计算 |
| `rewrite_by_lua` | rewrite | URL 重写、跳转、请求修改 |
| `access_by_lua` | access | **WAF 核心阶段**：IP过滤、URL过滤、CC防护、参数检测 |
| `content_by_lua` | content | 生成响应内容（替代 proxy_pass） |
| `header_filter_by_lua` | header-filter | 修改响应头 |
| `body_filter_by_lua` | body-filter | 修改响应体（过滤/替换） |
| `log_by_lua` | log | 自定义日志、统计 |
| `init_by_lua` | master 启动 | 全局初始化（加载模块、预编译） |
| `init_worker_by_lua` | worker 启动 | worker 级初始化（定时器、预热） |
| `balancer_by_lua` | 负载均衡 | 动态选择后端节点 |
| `ssl_certificate_by_lua` | SSL 握手 | 动态加载 SSL 证书 |

**WAF 为什么在 access 阶段：** access 阶段在 content 阶段之前，此时请求头已解析、请求体可选读取，后端尚未被访问。在此阶段拦截恶意请求，不会消耗后端资源。

```nginx
# 典型 WAF 配置结构
http {
    lua_shared_dict waf_ip_blacklist 10m;   # IP黑名单共享内存
    lua_shared_dict waf_cc_limit 50m;        # CC限流计数
    lua_package_path "/usr/local/openresty/nginx/conf/waf/?.lua;;";

    init_by_lua_block {
        waf = require "waf"      -- 加载 WAF 模块
        waf.init()                -- 初始化规则
    }

    server {
        listen 80;
        access_by_lua_block {
            waf.check()           -- 每个请求执行 WAF 检测
        }
        location / {
            proxy_pass http://backend;
        }
    }
}
```

---

## 3. lua-resty 库生态

lua-resty 是 OpenResty 官方维护的 Lua 库集合，基于 cosocket（非阻塞 socket）实现，在 Lua 代码中调用不会阻塞 Nginx worker。

**常用库：**

| 库 | 用途 | 示例 |
| --- | --- | --- |
| lua-resty-redis | Redis 客户端 | 缓存、会话、限流计数 |
| lua-resty-mysql | MySQL 客户端 | 直接在 Nginx 层查数据库 |
| lua-resty-http | HTTP 客户端 | 调用外部 API、子请求 |
| lua-resty-dns | DNS 解析 | 动态域名解析、服务发现 |
| lua-resty-lock | 分布式锁 | 防止缓存击穿 |
| lua-resty-lrucache | LRU 缓存 | worker 本地缓存（比 shared_dict 快） |
| lua-resty-string | 字符串/加密 | MD5/SHA/AES 等 |
| lua-resty-uuid | UUID 生成 | 请求 ID、追踪 |

**lua-resty-redis 示例：**

```lua
-- access_by_lua_block 中使用
local redis = require "resty.redis"
local red = redis:new()
red:set_timeouts(1000, 1000, 1000)  -- connect/send/read 超时(ms)

local ok, err = red:connect("127.0.0.1", 6379)
if not ok then
    ngx.log(ngx.ERR, "redis connect failed: ", err)
    return
end

-- 检查 IP 黑名单
local ip = ngx.var.remote_addr
local blocked, err = red:get("waf:blacklist:" .. ip)
if blocked == "1" then
    ngx.exit(ngx.HTTP_FORBIDDEN)
end

-- 连接池复用（关键！避免每次新建连接）
red:set_keepalive(10000, 100)  -- 空闲10秒，最大100个连接
```

**lua-resty-http 示例（调用外部认证服务）：**

```lua
local http = require "resty.http"
local httpc = http.new()
httpc:set_timeout(3000)

local res, err = httpc:request_uri("http://auth-service:8080/verify", {
    method = "POST",
    body = ngx.var.request_body,
    headers = {
        ["Content-Type"] = "application/json",
        ["X-Token"] = ngx.var.http_x_token,
    }
})

if not res or res.status ~= 200 then
    ngx.exit(ngx.HTTP_UNAUTHORIZED)
end
```

**cosocket 注意事项：**
- 只能在有请求上下文的阶段使用（rewrite/access/content等），不能在 init/set 阶段
- 必须用 `set_keepalive()` 复用连接，否则每次新建 TCP 连接性能差
- DNS 解析用 `lua-resty-dns` 或 `resolver` 指令，不要用 Lua 的 `socket.dns`（阻塞）

---

## 4. WAF 架构设计

WAF（Web Application Firewall）在请求到达后端之前检测和拦截恶意流量。OpenResty WAF 通常在 `access_by_lua` 阶段实现多层防护。

### 4.1 IP 黑白名单

```lua
-- waf/ip_filter.lua
local _M = {}

function _M.check()
    local ip = ngx.var.remote_addr

    -- 1. 白名单直接放行
    local whitelist = ngx.shared.waf_ip_whitelist
    if whitelist:get(ip) then
        return true  -- 放行
    end

    -- 2. 黑名单拦截
    local blacklist = ngx.shared.waf_ip_blacklist
    if blacklist:get(ip) then
        ngx.log(ngx.WARN, "IP blocked by blacklist: ", ip)
        ngx.exit(ngx.HTTP_FORBIDDEN)
    end

    return true
end

return _M
```

```nginx
# 动态管理黑白名单（通过 HTTP API）
location /waf/ip/blacklist {
    allow 127.0.0.1;
    deny all;
    content_by_lua_block {
        local ip = ngx.var.arg_ip
        local action = ngx.var.arg_action  -- add/del
        local dict = ngx.shared.waf_ip_blacklist
        if action == "add" then
            dict:set(ip, 1, 86400)  -- 有效期24小时
        elseif action == "del" then
            dict:delete(ip)
        end
        ngx.say("ok")
    }
}
```

### 4.2 URL 过滤与 User-Agent 识别

```lua
-- waf/url_filter.lua
local _M = {}

-- 恶意 URL 正则规则
local url_rules = {
    [[/\.\./]],                    -- 目录遍历
    [[<script]],                   -- XSS
    [[union\s+select]],            -- SQL注入
    [[/\.(git|svn|env|bak|sql)]], -- 敏感文件
    [[(benchmark|sleep)\s*\(]],    -- SQL时间盲注
    [[cmd(\.exe)?=]],              -- 命令执行
}

function _M.check()
    local uri = ngx.var.request_uri  -- 含 query string
    local ua = ngx.var.http_user_agent or ""

    -- URL 过滤
    for _, rule in ipairs(url_rules) do
        if ngx.re.match(uri, rule, "io") then
            ngx.log(ngx.WARN, "Malicious URL blocked: ", uri, " rule: ", rule)
            ngx.exit(ngx.HTTP_FORBIDDEN)
        end
    end

    -- User-Agent 识别（拦截爬虫/扫描器）
    local bad_ua = {
        "sqlmap", "nmap", "nikto", "acunetix",
        "masscan", "hydra", "dirbuster",
    }
    for _, pattern in ipairs(bad_ua) do
        if ngx.re.match(ua, pattern, "io") then
            ngx.exit(ngx.HTTP_FORBIDDEN)
        end
    end

    -- 空 User-Agent 可选拦截
    if ua == "" then
        -- ngx.exit(ngx.HTTP_FORBIDDEN)  -- 生产环境谨慎，部分正常客户端无UA
    end

    return true
end

return _M
```

### 4.3 Referer 验证与 Cookie 过滤

```lua
-- waf/referer_cookie.lua
local _M = {}

function _M.check()
    -- Referer 验证（防 CSRF，仅对 POST 请求）
    if ngx.var.request_method == "POST" then
        local referer = ngx.var.http_referer or ""
        local host = ngx.var.host
        -- Referer 必须包含本站域名
        if not ngx.re.match(referer, "^https?://" .. host, "io") then
            -- 注意：API 服务可能无 Referer，需按路径白名单处理
            -- ngx.exit(ngx.HTTP_FORBIDDEN)
        end
    end

    -- Cookie 过滤（拦截恶意 Cookie）
    local cookie = ngx.var.http_cookie or ""
    if ngx.re.match(cookie, [[<script|union\s+select|\.\./]], "io") then
        ngx.exit(ngx.HTTP_FORBIDDEN)
    end

    return true
end

return _M
```

### 4.4 HTTP 方法限制

```lua
-- waf/method_filter.lua
local _M = {}

local allowed_methods = {
    GET = true,
    POST = true,
    HEAD = true,
    OPTIONS = true,
    -- PUT = true,    -- REST API 按需开启
    -- DELETE = true,
}

function _M.check()
    local method = ngx.var.request_method
    if not allowed_methods[method] then
        ngx.log(ngx.WARN, "Method not allowed: ", method)
        ngx.exit(ngx.HTTP_NOT_ALLOWED)
    end
    return true
end

return _M
```

---

## 5. CC 攻击防护

CC（Challenge Collapsar）攻击是大量恶意请求耗尽服务器资源。OpenResty 通过 `lua_shared_dict` 计数 + 滑动窗口实现限流。

**基于 IP 的请求频率限制：**

```lua
-- waf/cc_protection.lua
local _M = {}

local LIMIT = 100          -- 每窗口最大请求数
local WINDOW = 60          -- 窗口大小（秒）
local BLOCK_TIME = 300     -- 封禁时间（秒）

function _M.check()
    local ip = ngx.var.remote_addr
    local dict = ngx.shared.waf_cc_limit

    -- 检查是否已被封禁
    local blocked = dict:get("block:" .. ip)
    if blocked then
        ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
    end

    -- 计数（原子操作）
    local key = "count:" .. ip
    local count, err = dict:incr(key, 1)
    if not count then
        -- key 不存在，初始化
        dict:set(key, 1, WINDOW)
        count = 1
    end

    -- 超限则封禁
    if count > LIMIT then
        dict:set("block:" .. ip, 1, BLOCK_TIME)
        dict:delete(key)
        ngx.log(ngx.WARN, "CC attack detected, IP blocked: ", ip, " count: ", count)
        ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
    end

    return true
end

return _M
```

**更精确的滑动窗口限流（令牌桶算法）：**

```lua
-- 令牌桶限流：每秒生成 RATE 个令牌，桶容量 CAPACITY
local function token_bucket_check(dict, key, rate, capacity)
    local now = ngx.now()
    -- 获取上次刷新时间和剩余令牌
    local last_time = dict:get(key .. ":time") or now
    local tokens = dict:get(key .. ":tokens") or capacity

    -- 计算新增令牌
    local elapsed = now - last_time
    tokens = math.min(capacity, tokens + elapsed * rate)

    -- 尝试取一个令牌
    if tokens >= 1 then
        tokens = tokens - 1
        dict:set(key .. ":time", now)
        dict:set(key .. ":tokens", tokens)
        return true  -- 放行
    else
        dict:set(key .. ":time", now)
        dict:set(key .. ":tokens", tokens)
        return false  -- 限流
    end
end
```

**人机验证（验证码）：** 对疑似 CC 的 IP 返回验证码页面，验证通过后加入白名单。

```lua
-- 疑似 CC 时返回 503 + 验证码页面
if count > LIMIT * 0.8 then
    ngx.header.content_type = "text/html"
    ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
    ngx.say([[
        <html><body>
        <h2>检测到异常访问，请完成验证</h2>
        <form method="POST" action="/waf/verify">
            <input name="answer" placeholder="请输入验证码">
            <button type="submit">验证</button>
        </form>
        </body></html>
    ]])
    ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
end
```

---

## 6. 深度参数过滤：SQL 注入与 XSS

对 GET/POST 参数进行深度检测，需要先读取请求体。

```lua
-- waf/injection_filter.lua
local _M = {}

-- SQL 注入特征正则
local sql_rules = {
    [[\bunion\s+(all\s+)?select\b]],
    [[\bselect\b.+\bfrom\b]],
    [[\binsert\s+into\b]],
    [[\bdelete\s+from\b]],
    [[\bdrop\s+(table|database)\b]],
    [[\bupdate\b.+\bset\b]],
    [[\b(benchmark|sleep|pg_sleep)\s*\(]],
    [[--\s*$]],                     -- SQL注释
    [[/\*.*\*/]],                   -- SQL块注释
    [[\bor\s+['"]?\d+['"]?\s*=]], -- or 1=1
    [[\band\s+['"]?\d+['"]?\s*=]],
}

-- XSS 特征正则
local xss_rules = {
    [[<script[^>]*>.*</script>]],
    [[<script[^>]*src\s*=]],
    [[javascript\s*:]],
    [[on\w+\s*=]],                  -- onerror/onload 等事件
    [[<iframe[^>]*>]],
    [[<img[^>]+onerror]],
    [[eval\s*\(]],
    [[alert\s*\(]],
}

local function check_string(value, rules, label)
    if type(value) ~= "string" or value == "" then
        return
    end
    for _, rule in ipairs(rules) do
        if ngx.re.match(value, rule, "io") then
            ngx.log(ngx.WARN, label, " blocked: ", value, " rule: ", rule)
            ngx.exit(ngx.HTTP_FORBIDDEN)
        end
    end
end

function _M.check()
    -- 1. 检查 GET 参数 (ngx.var.args)
    local args = ngx.req.get_uri_args()
    for key, val in pairs(args) do
        if type(val) == "table" then
            for _, v in ipairs(val) do
                check_string(v, sql_rules, "SQLi(GET)")
                check_string(v, xss_rules, "XSS(GET)")
            end
        else
            check_string(val, sql_rules, "SQLi(GET)")
            check_string(val, xss_rules, "XSS(GET)")
        end
    end

    -- 2. 检查 POST 参数（需先读取请求体）
    if ngx.var.request_method == "POST" then
        ngx.req.read_body()
        local post_args = ngx.req.get_post_args()
        if post_args then
            for key, val in pairs(post_args) do
                if type(val) == "table" then
                    for _, v in ipairs(val) do
                        check_string(v, sql_rules, "SQLi(POST)")
                        check_string(v, xss_rules, "XSS(POST)")
                    end
                else
                    check_string(val, sql_rules, "SQLi(POST)")
                    check_string(val, xss_rules, "XSS(POST)")
                end
            end
        end

        -- 3. JSON body 检测（API 场景）
        local content_type = ngx.var.content_type or ""
        if ngx.re.match(content_type, "application/json", "io") then
            local body = ngx.req.get_body_data()
            if body then
                check_string(body, sql_rules, "SQLi(JSON)")
                check_string(body, xss_rules, "XSS(JSON)")
            end
        end
    end

    return true
end

return _M
```

**WAF 主入口（组合所有检测）：**

```lua
-- waf/init.lua
local ip_filter = require "waf.ip_filter"
local url_filter = require "waf.url_filter"
local method_filter = require "waf.method_filter"
local cc_protection = require "waf.cc_protection"
local injection_filter = require "waf.injection_filter"
local referer_cookie = require "waf.referer_cookie"

local _M = {}

function _M.check()
    -- 按开销从小到大排列，尽早拦截
    method_filter.check()
    ip_filter.check()
    url_filter.check()
    cc_protection.check()
    referer_cookie.check()
    injection_filter.check()  -- 最耗时，放最后
end

return _M
```

---

## 7. 日志记录与规则动态更新

### 攻击日志记录

```lua
-- waf/logger.lua
local _M = {}

function _M.log(reason)
    local log_data = {
        time = ngx.localtime(),
        ip = ngx.var.remote_addr,
        method = ngx.var.request_method,
        uri = ngx.var.request_uri,
        ua = ngx.var.http_user_agent or "-",
        referer = ngx.var.http_referer or "-",
        reason = reason,
        request_id = ngx.var.request_id,
    }

    -- 写入 Nginx error log
    ngx.log(ngx.WARN,
        "WAF_BLOCK ", reason,
        " ip=", log_data.ip,
        " method=", log_data.method,
        " uri=", log_data.uri)

    -- 异步写入 Redis（用于统计分析）
    local ok, err = ngx.timer.at(0, function(premature)
        if premature then return end
        local redis = require "resty.redis"
        local red = redis:new()
        red:set_timeouts(500, 500, 500)
        local ok, err = red:connect("127.0.0.1", 6379)
        if ok then
            local cjson = require "cjson"
            red:lpush("waf:attack:log", cjson.encode(log_data))
            red:ltrim("waf:attack:log", 0, 9999)
            red:set_keepalive(10000, 50)
        end
    end)
end

return _M
```

### 规则动态更新（无需 reload）

```lua
-- 通过共享内存 + 定时器实现规则热更新
init_worker_by_lua_block {
    local function reload_rules(premature)
        if premature then return end
        local redis = require "resty.redis"
        local red = redis:new()
        red:set_timeouts(1000, 1000, 1000)
        local ok, err = red:connect("127.0.0.1", 6379)
        if ok then
            -- 从 Redis 拉取最新规则
            local rules, err = red:get("waf:rules:url")
            if rules and rules ~= ngx.null then
                local cjson = require "cjson"
                local rule_table = cjson.decode(rules)
                -- 更新 worker 本地缓存
                local waf = require "waf"
                waf.update_url_rules(rule_table)
            end
            red:set_keepalive(10000, 50)
        end
    end
    -- 每 30 秒刷新一次规则
    ngx.timer.every(30, reload_rules)
}
```

---

## 8. 性能考量与 Nginx 原生模块对比

### 性能优化要点

| 优化点 | 说明 |
| --- | --- |
| 检测顺序 | 开销小的检测放前面（IP/方法/URL），尽早拦截，避免执行耗时检测 |
| 正则缓存 | 用 `ngx.re.match` 而非 Lua 原生 `string.match`，前者 JIT 编译且缓存 |
| 共享内存 vs LRU | 高频读用 `lua-resty-lrucache`（worker本地，无锁），跨worker共享用 `lua_shared_dict` |
| 连接池复用 | redis/mysql/http 必须 `set_keepalive()`，否则每次新建连接 |
| 避免阻塞 | 不用 Lua 标准库的 `socket`/`io`，全部用 cosocket 或 ngx 提供的 API |
| 请求体读取 | `ngx.req.read_body()` 有开销，只在需要检测 POST 参数时调用 |
| 日志异步化 | 用 `ngx.timer.at(0, ...)` 异步写日志，不阻塞请求 |
| LuaJIT FFI | 高频操作可用 FFI 调用 C 函数，比 Lua 实现快 10 倍+ |

### 与 Nginx 原生模块对比

| 功能 | Nginx 原生模块 | OpenResty Lua |
| --- | --- | --- |
| IP 黑白名单 | `ngx_http_access_module`（allow/deny） | Lua + shared_dict（动态更新，无需reload） |
| 限流 | `ngx_http_limit_req_module`（limit_req_zone） | Lua 令牌桶/滑动窗口（更灵活，可自定义维度） |
| 连接数限制 | `ngx_http_limit_conn_module` | Lua 计数 |
| URL 重写 | `rewrite` 指令 | `rewrite_by_lua`（复杂逻辑） |
| 访问控制 | `auth_basic` / `auth_request` | `access_by_lua`（任意逻辑） |
| 动态后端 | `upstream` + 第三方模块 | `balancer_by_lua`（动态路由/权重/熔断） |
| 响应修改 | `sub_filter` / `addition` | `header_filter_by_lua` / `body_filter_by_lua` |
| 开发效率 | 改配置+reload，复杂逻辑需C模块 | 写Lua，热加载，开发快 |
| 性能 | 最高（C原生） | 略低（LuaJIT，通常原生的70-90%） |

**选型建议：**
- 简单静态规则（固定IP黑白名单、基础限流）：用 Nginx 原生模块，性能最高。Nginx 深度原理详见《05-Nginx深度：反向代理与模块开发.md》（待创建）
- 动态规则、复杂逻辑、需要外部服务交互：用 OpenResty Lua
- 生产环境通常混合使用：原生模块做基础防护，Lua 做深度 WAF

---

## 9. 快速参考卡片

### WAF 规则模板

```text
检测层级（按开销排序）:
  1. HTTP方法限制  -> 405
  2. IP白名单      -> 直接放行
  3. IP黑名单      -> 403
  4. URL正则过滤   -> 403（目录遍历/敏感文件/扫描器）
  5. CC限流        -> 503（IP频率/令牌桶）
  6. UA/Referer/Cookie -> 403
  7. GET参数注入检测 -> 403（SQLi/XSS）
  8. POST参数注入检测 -> 403（需read_body）
  9. JSON body检测  -> 403
```

### Lua API 速查

```text
请求信息:
  ngx.var.remote_addr        客户端IP
  ngx.var.request_method     请求方法
  ngx.var.request_uri        完整URI(含query)
  ngx.var.uri                路径(不含query)
  ngx.var.http_user_agent    User-Agent
  ngx.var.http_referer       Referer
  ngx.var.http_cookie        Cookie
  ngx.var.content_type       Content-Type
  ngx.var.request_id         请求ID(需配置)

请求操作:
  ngx.req.get_uri_args()     获取GET参数(table)
  ngx.req.read_body()         读取请求体
  ngx.req.get_post_args()     获取POST参数(table)
  ngx.req.get_body_data()     获取请求体原始数据
  ngx.req.set_header(k, v)    设置请求头

响应操作:
  ngx.exit(status)            终止请求并返回状态码
  ngx.say(...)                输出响应体
  ngx.header[k] = v           设置响应头
  ngx.redirect(url)           302重定向
  ngx.log(level, ...)         写日志(ngx.ERR/WARN/INFO/DEBUG)

共享内存:
  ngx.shared.DICT:get(key)
  ngx.shared.DICT:set(key, val, expire)
  ngx.shared.DICT:incr(key, delta)
  ngx.shared.DICT:delete(key)

定时器:
  ngx.timer.at(delay, callback)     一次性
  ngx.timer.every(interval, callback)  周期性
```

### 防护层级表

```text
L1 网络层: IP黑白名单、TCP连接数限制（Nginx limit_conn）
L2 协议层: HTTP方法限制、异常协议头检测
L3 应用层: URL过滤、UA识别、Referer验证、Cookie过滤
L4 行为层: CC限流、频率检测、人机验证
L5 内容层: SQL注入检测、XSS防御、参数过滤、文件上传检测
L6 日志层: 攻击日志、统计分析、规则动态更新
```

---

## 10. 常见问题与坑

| 问题 | 原因与解决 |
| --- | --- |
| WAF 导致正常请求被误拦截 | 正则规则过于宽泛；用 `ngx.re.match` 的 `io` 选项（不区分大小写+单行模式），规则精确化，建立白名单路径 |
| Lua 代码阻塞 Nginx | 用了阻塞调用（Lua socket/io/sleep）；全部替换为 cosocket 和 `ngx.sleep()`，用 `ngx.timer` 做异步 |
| 共享内存竞争导致计数不准 | `lua_shared_dict` 的 `incr` 是原子的，但 get+set 不是；计数用 `incr`，复杂操作用 `lua-resty-lock` 加锁 |
| POST 参数检测导致上传变慢 | `ngx.req.read_body()` 读取整个请求体到内存/磁盘；大文件上传路径跳过参数检测，或用 `client_body_buffer_size` 优化 |
| 正则匹配 CPU 高 | 规则太多或正则回溯严重；减少规则数量，用更精确的正则，避免 `.*` 嵌套，开启 `ngx.re` 的 JIT 缓存 |
| CC 限流误伤正常用户 | 单 IP 阈值太低或 NAT 出口多用户共享 IP；按 IP+URL 维度限流，提高阈值，白名单重要 IP |
| Redis 连接耗尽 | 未用 `set_keepalive()` 复用连接；每次操作后调用 `set_keepalive(10000, pool_size)`，合理设置连接池大小 |
| 规则更新不生效 | 只更新了一个 worker 的本地缓存；用 `lua_shared_dict` 存储规则，或 `ngx.timer.every` 在每个 worker 定时刷新 |
| WAF 被绕过（编码绕过） | 只检测原始参数，未解码；对 URL 参数先 `ngx.unescape_uri()`，对双重编码递归解码，对 Base64 参数解码后检测 |
| 性能下降明显 | 检测逻辑过重或日志同步写；异步化日志，减少正则数量，用 LRU 缓存检测结果，按路径选择性启用深度检测 |

---

上一篇：《08-etcd与Raft共识.md》
