# Redis 深入：协议存储与集群

> 本节目标：在《02-Redis设计与数据结构.md》基础上深入 Redis 底层实现。覆盖 RESP 协议与异步客户端手撕、五种对象的编码实现与数据结构论证（跳表/intset/ziplist/quicklist/listpack）、主从复制与 psync 细节、Sentinel 故障转移与脑裂、Cluster 16384 槽位与 gossip 通信、持久化 fork+COW 与 AOF 重写、缓存三兄弟的工程级方案、分布式锁的 Redlock 与 Lua 原子性。学完后能从协议字节级理解 Redis 通信，从编码转换理解内存优化，从槽位与复制理解集群架构，并能在 C++ 中手撕异步 redis 客户端。前置阅读：《02-Redis设计与数据结构.md》《../14-内核云原生与分布式/05-检测组件与分布式锁.md》。

## 本章速览

- [1. RESP 协议：从字节到命令](#1-resp-协议从字节到命令)
  - [1.1 RESP2 协议格式](#11-resp2-协议格式)
  - [1.2 RESP3 新特性](#12-resp3-新特性)
  - [1.3 内联命令与 pipelines](#13-内联命令与-pipelines)
  - [1.4 手撕 RESP 解析器（C++）](#14-手撕-resp-解析器c)
- [2. 异步客户端：hiredis 与事件循环](#2-异步客户端hiredis-与事件循环)
  - [2.1 hiredis 同步 API 回顾](#21-hiredis-同步-api-回顾)
  - [2.2 hiredis 异步 API 与回调](#22-hiredis-异步-api-与回调)
  - [2.3 集成 libev / epoll 事件库](#23-集成-libev--epoll-事件库)
  - [2.4 手撕异步 redis 协议解析与状态机](#24-手撕异步-redis-协议解析与状态机)
- [3. 存储原理深入：编码与数据结构](#3-存储原理深入编码与数据结构)
  - [3.1 对象模型：类型与编码](#31-对象模型类型与编码)
  - [3.2 跳表实现与复杂度论证（zset）](#32-跳表实现与复杂度论证zset)
  - [3.3 整数集合 intset 与升级](#33-整数集合-intset-与升级)
  - [3.4 压缩列表 ziplist 与连锁更新](#34-压缩列表-ziplist-与连锁更新)
  - [3.5 quicklist 与 listpack](#35-quicklist-与-listpack)
  - [3.6 编码转换触发条件汇总](#36-编码转换触发条件汇总)
- [4. 对象模型深入](#4-对象模型深入)
  - [4.1 redisObject 结构](#41-redisobject-结构)
  - [4.2 类型检查与命令多态](#42-类型检查与命令多态)
  - [4.3 对象共享与引用计数](#43-对象共享与引用计数)
  - [4.4 空转时长与内存淘汰](#44-空转时长与内存淘汰)
- [5. 主从复制深入](#5-主从复制深入)
  - [5.1 全量复制与增量复制](#51-全量复制与增量复制)
  - [5.2 psync 命令与 runid/offset](#52-psync-命令与-runidoffset)
  - [5.3 复制积压缓冲区（repl backlog）](#53-复制积压缓冲区repl-backlog)
  - [5.4 复制偏移量与心跳](#54-复制偏移量与心跳)
- [6. Sentinel 哨兵深入](#6-sentinel-哨兵深入)
  - [6.1 故障发现：主观下线与客观下线](#61-故障发现主观下线与客观下线)
  - [6.2 故障转移：选举与切换](#62-故障转移选举与切换)
  - [6.3 配置中心与客户端发现](#63-配置中心与客户端发现)
  - [6.4 脑裂问题与 min-replicas](#64-脑裂问题与-min-replicas)
- [7. Cluster 集群深入](#7-cluster-集群深入)
  - [7.1 16384 槽位与 key 路由](#71-16384-槽位与-key-路由)
  - [7.2 gossip 通信与节点握手](#72-gossip-通信与节点握手)
  - [7.3 故障转移与故障检测](#73-故障转移与故障检测)
  - [7.4 hash tag 与多 key 事务](#74-hash-tag-与多-key-事务)
  - [7.5 重新分片与迁移](#75-重新分片与迁移)
- [8. 持久化深入](#8-持久化深入)
  - [8.1 RDB：fork + COW 写时复制](#81-rdbfork--cow-写时复制)
  - [8.2 AOF：always / everysec / no](#82-aofalways--everysec--no)
  - [8.3 AOF 重写：bgrewriteaof 与缓冲区](#83-aof-重写bgrewriteaof-与缓冲区)
  - [8.4 混合持久化（4.0+）](#84-混合持久化40)
- [9. 缓存三兄弟：工程级解决方案](#9-缓存三兄弟工程级解决方案)
  - [9.1 缓存击穿：热点 key 过期](#91-缓存击穿热点-key-过期)
  - [9.2 缓存穿透：不存在的 key](#92-缓存穿透不存在的-key)
  - [9.3 缓存雪崩：大量 key 同时过期](#93-缓存雪崩大量-key-同时过期)
  - [9.4 三者对比与方案选型表](#94-三者对比与方案选型表)
- [10. 分布式锁深入](#10-分布式锁深入)
  - [10.1 SET NX EX 基础锁](#101-set-nx-ex-基础锁)
  - [10.2 Lua 脚本保证原子性](#102-lua-脚本保证原子性)
  - [10.3 Redlock 算法与争议](#103-redlock-算法与争议)
  - [10.4 看门狗续期与 C++ 实现](#104-看门狗续期与-c-实现)
- [11. 常见坑与最佳实践](#11-常见坑与最佳实践)
- [12. 快速参考卡片](#12-快速参考卡片)

---

## 1. RESP 协议：从字节到命令

### 1.1 RESP2 协议格式

RESP（REdis Serialization Protocol）是 Redis 客户端与服务器之间的通信协议，基于 TCP 连接，以 `\r\n`（CRLF）作为行分隔符。RESP2 是 Redis 2.0 引入的版本，至今仍是默认协议。

RESP2 通过首字节区分数据类型：

| 首字节 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `+` | 简单字符串（Simple String） | 状态回复，不含 `\r\n` | `+OK\r\n` |
| `-` | 错误（Error） | 错误回复 | `-ERR unknown command\r\n` |
| `:` | 整数（Integer） | 64 位有符号整数 | `:1000\r\n` |
| `$` | 批量字符串（Bulk String） | 二进制安全，长度前缀 | `$5\r\nhello\r\n` |
| `*` | 数组（Array） | 元素个数前缀，可嵌套 | `*2\r\n$3\r\nGET\r\n$3\r\nkey\r\n` |

**请求格式**：客户端发送命令时，统一使用数组格式，每个参数是一个批量字符串。例如 `SET key value` 的实际字节流：

```text
*3\r\n
$3\r\n
SET\r\n
$3\r\n
key\r\n
$5\r\n
value\r\n
```

**响应格式**：服务器根据命令返回对应类型。`SET` 成功返回 `+OK\r\n`，`GET` 返回批量字符串或 `$-1\r\n`（nil），`INCR` 返回整数。

> 来源：《Redis设计与实现》黄健宏 第 12 章；Redis 官方文档 Protocol specification。

### 1.2 RESP3 新特性

RESP3 是 Redis 6.0 引入的协议升级，通过 `HELLO 3` 命令切换。主要新增类型：

| 首字节 | 类型 | 说明 |
|--------|------|------|
| `_` | Null | 独立的 null 类型，替代 `$-1` / `*-1` |
| `,` | Double | 浮点数，如 `,3.14\r\n` |
| `(` | Big number | 大整数，超出 64 位范围 |
| `#` | Boolean | `#t\r\n` / `#f\r\n` |
| `!` | Blob error | 二进制安全的错误 |
| `=` | Verbatim string | 带格式标记的字符串（如 txt/mk） |
| `%` | Map | 键值对映射，替代数组模拟 |
| `~` | Set | 集合类型 |
| `>` | Push | 服务器主动推送（如 Pub/Sub、监控） |
| `|` | Attribute | 属性元数据 |

RESP3 的核心价值：客户端无需猜测 nil 是批量字符串还是数组；Map/Set 直接表达语义；Push 类型让 Pub/Sub 和命令响应可以在同一连接上区分。目前主流客户端（hiredis 1.0+、Jedis 4+、ioredis 5+）已支持 RESP3，但生产环境多数仍用 RESP2 兼容性更好。

### 1.3 内联命令与 pipelines

**内联命令（Inline Command）**：当客户端无法发送数组格式时（如 telnet 手动测试），Redis 支持以空格分隔的纯文本命令，以 `\r\n` 结尾。例如直接输入 `GET key\r\n`，服务器会解析为内联命令。限制：参数不能包含空格，否则需用引号。内联命令仅用于调试，生产环境必须用数组格式。

**Pipelines（管道）**：Redis 是请求-响应模型，每条命令都要等待回复。RTT 较高时，大量小命令的延迟累积严重。Pipeline 允许客户端一次性发送多条命令，服务器批量处理后一次性返回所有回复，减少网络往返次数。

```bash
# WSL Ubuntu 24.04 实跑：使用 redis-cli --pipe 批量导入
cat commands.txt | redis-cli --pipe
# 示例输出：All data transferred. Waiting for the last reply...
# Last reply received from server.
# errors: 0, replies: 10000
```

Pipeline 不是原子的，中间命令失败不影响后续命令执行。需要原子性时应使用事务（MULTI/EXEC）或 Lua 脚本。Pipeline 与事务可组合使用：`MULTI` + 多条命令 + `EXEC` 放在一个 pipeline 中发送。

### 1.4 手撕 RESP 解析器（C++）

理解协议的最好方式是手写解析器。以下是一个简化的 RESP2 响应解析器，基于状态机逐字节处理：

```cpp
#include <string>
#include <vector>
#include <variant>
#include <cstdint>
#include <stdexcept>

// RESP 值类型
struct RespValue {
    enum class Type { SimpleString, Error, Integer, BulkString, Array, Null };
    Type type;
    std::string str;           // 简单字符串/错误/批量字符串内容
    int64_t integer = 0;       // 整数值
    std::vector<RespValue> arr; // 数组元素
};

class RespParser {
public:
    // 解析一个完整响应，返回已消费字节数
    size_t parse(const char* data, size_t len, RespValue& out) {
        if (len == 0) return 0;
        size_t pos = 0;
        char type = data[pos++];
        switch (type) {
            case '+': out.type = RespValue::Type::SimpleString; return pos + readLine(data+pos, len-pos, out.str);
            case '-': out.type = RespValue::Type::Error;        return pos + readLine(data+pos, len-pos, out.str);
            case ':': out.type = RespValue::Type::Integer; {
                std::string num; pos += readLine(data+pos, len-pos, num);
                out.integer = std::stoll(num); return pos;
            }
            case '$': {
                std::string lenStr; pos += readLine(data+pos, len-pos, lenStr);
                int64_t bulkLen = std::stoll(lenStr);
                if (bulkLen == -1) { out.type = RespValue::Type::Null; return pos; }
                out.type = RespValue::Type::BulkString;
                if (pos + bulkLen + 2 > len) return 0; // 数据不足
                out.str.assign(data+pos, bulkLen);
                return pos + bulkLen + 2; // +2 跳过 \r\n
            }
            case '*': {
                std::string cntStr; pos += readLine(data+pos, len-pos, cntStr);
                int64_t count = std::stoll(cntStr);
                if (count == -1) { out.type = RespValue::Type::Null; return pos; }
                out.type = RespValue::Type::Array;
                out.arr.resize(count);
                for (int64_t i = 0; i < count; ++i) {
                    size_t consumed = parse(data+pos, len-pos, out.arr[i]);
                    if (consumed == 0) return 0; // 数据不足，等待更多
                    pos += consumed;
                }
                return pos;
            }
            default: throw std::runtime_error("Unknown RESP type");
        }
    }
private:
    // 读取一行到 \r\n，返回消费字节数（不含 \r\n）
    size_t readLine(const char* data, size_t len, std::string& out) {
        for (size_t i = 0; i + 1 < len; ++i) {
            if (data[i] == '\r' && data[i+1] == '\n') {
                out.assign(data, i);
                return i + 2;
            }
        }
        return 0; // 行不完整
    }
};
```

关键点：
1. **增量解析**：TCP 是流协议，响应可能分片到达。解析器必须支持"数据不足时返回 0，等下次数据到达后继续"。
2. **批量字符串二进制安全**：`$5\r\nhello\r\n` 中，内容长度由前缀数字决定，不能用 `\r\n` 查找内容结束。
3. **数组嵌套**：数组元素可以是任意类型，包括另一个数组，需递归解析。
4. **Null 的两种表达**：RESP2 中 `$-1\r\n` 表示 nil 批量字符串，`*-1\r\n` 表示 nil 数组。

---

## 2. 异步客户端：hiredis 与事件循环

### 2.1 hiredis 同步 API 回顾

hiredis 是 Redis 官方 C 客户端库，同步 API 简单直接：

```cpp
#include <hiredis/hiredis.h>

redisContext* c = redisConnect("127.0.0.1", 6379);
if (c->err) { /* 处理错误 */ }

redisReply* reply = (redisReply*)redisCommand(c, "SET %s %s", "key", "value");
// reply->type == REDIS_REPLY_STATUS, reply->str == "OK"
freeReplyObject(reply);

reply = (redisReply*)redisCommand(c, "GET %s", "key");
// reply->type == REDIS_REPLY_STRING, reply->str == "value"
freeReplyObject(reply);

redisFree(c);
```

同步 API 的问题：`redisCommand` 会阻塞等待响应，单连接无法并发。高并发场景下需要异步 API。

### 2.2 hiredis 异步 API 与回调

hiredis 提供 `hiredis/async.h` 异步接口，核心是回调函数：

```cpp
#include <hiredis/hiredis.h>
#include <hiredis/async.h>

void getCallback(redisAsyncContext* c, void* r, void* privdata) {
    redisReply* reply = (redisReply*)r;
    if (reply == nullptr) return;
    printf("GET result: %s\n", reply->str);
    // 处理完后可断开连接
    redisAsyncDisconnect(c);
}

void connectCallback(const redisAsyncContext* c, int status) {
    if (status != REDIS_OK) { printf("Error: %s\n", c->errstr); return; }
    printf("Connected...\n");
}

void disconnectCallback(const redisAsyncContext* c, int status) {
    if (status != REDIS_OK) { printf("Error: %s\n", c->errstr); return; }
    printf("Disconnected...\n");
}

int main() {
    redisAsyncContext* c = redisAsyncConnect("127.0.0.1", 6379);
    if (c->err) { printf("Error: %s\n", c->errstr); return 1; }

    redisAsyncSetConnectCallback(c, connectCallback);
    redisAsyncSetDisconnectCallback(c, disconnectCallback);

    // 异步执行命令，结果通过回调返回
    redisAsyncCommand(c, getCallback, nullptr, "SET %s %s", "key", "value");
    redisAsyncCommand(c, getCallback, nullptr, "GET %s", "key");

    // 需要绑定到事件循环才能驱动，见下节
    return 0;
}
```

异步 API 本身不包含事件循环，需要与 libev、libevent、libuv 或自研 epoll 事件库集成。

### 2.3 集成 libev / epoll 事件库

hiredis 提供了与 libev 的适配层 `adapters/libev.h`：

```cpp
#include <hiredis/adapters/libev.h>

int main() {
    redisAsyncContext* c = redisAsyncConnect("127.0.0.1", 6379);
    redisLibevAttach(EV_DEFAULT, c);  // 绑定到 libev 事件循环

    redisAsyncCommand(c, getCallback, nullptr, "GET key");
    ev_run(EV_DEFAULT, 0);  // 启动事件循环
    return 0;
}
```

如果使用自研 epoll 事件循环，需要实现四个钩子函数：

```cpp
// hiredis 异步上下文需要的事件钩子
struct redisAsyncContext {
    // ...
    // 以下函数指针由事件库实现填充
    void (*evAddRead)(void *privdata);
    void (*evDelRead)(void *privdata);
    void (*evAddWrite)(void *privdata);
    void (*evDelWrite)(void *privdata);
    void (*evCleanup)(void *privdata);
    void *ev.data;  // 事件库私有数据
};
```

自研 epoll 集成的核心逻辑：
1. `evAddRead`：将 fd 注册 EPOLLIN 事件，触发时调用 `redisAsyncHandleRead`
2. `evAddWrite`：将 fd 注册 EPOLLOUT 事件，触发时调用 `redisAsyncHandleWrite`
3. `evDelRead/evDelWrite`：从 epoll 中移除对应事件
4. `evCleanup`：清理事件库资源

这与《../03-网络编程/02-IO多路复用与Reactor模型.md》中的 Reactor 模式完全一致：hiredis 异步上下文就是一个 EventHandler，事件循环负责分发 IO 事件。

### 2.4 手撕异步 redis 协议解析与状态机

在通讯管理机等嵌入式场景中，可能不允许引入 hiredis 依赖。此时需要手撕异步 redis 客户端，核心是**输出缓冲区 + 输入解析状态机**：

```cpp
class AsyncRedisClient {
    enum class ParseState { Type, Line, BulkLen, BulkData, ArrayCount, ArrayElement };
    struct PendingCommand { std::function<void(RespValue)> callback; };

    int fd_;
    std::string sendBuf_;    // 待发送字节
    std::string recvBuf_;    // 已接收未解析字节
    std::deque<PendingCommand> pending_; // 等待响应的命令队列
    ParseState state_ = ParseState::Type;

public:
    // 异步发送命令：序列化为 RESP 字节放入发送缓冲区
    void command(std::function<void(RespValue)> cb, std::string_view cmd, std::string_view key) {
        // 构造 *3\r\n$3\r\nCMD\r\n$N\r\nkey\r\n...
        sendBuf_ += "*3\r\n";
        appendBulk(sendBuf_, cmd);
        appendBulk(sendBuf_, key);
        pending_.push_back({std::move(cb)});
        // 触发可写事件（由事件循环调用 onWritable）
    }

    // 套接字可写时调用：尽可能发送 sendBuf_
    void onWritable() {
        ssize_t n = ::send(fd_, sendBuf_.data(), sendBuf_.size(), 0);
        if (n > 0) sendBuf_.erase(0, n);
    }

    // 套接字可读时调用：读取数据并尝试解析响应
    void onReadable() {
        char tmp[65536];
        ssize_t n = ::recv(fd_, tmp, sizeof(tmp), 0);
        if (n <= 0) { /* 连接关闭 */ return; }
        recvBuf_.append(tmp, n);

        // 循环解析：一条 TCP 报文可能包含多个响应
        while (!recvBuf_.empty()) {
            RespValue val;
            RespParser parser;
            size_t consumed = parser.parse(recvBuf_.data(), recvBuf_.size(), val);
            if (consumed == 0) break; // 数据不足，等下次
            recvBuf_.erase(0, consumed);

            if (!pending_.empty()) {
                auto cb = std::move(pending_.front().callback);
                pending_.pop_front();
                if (cb) cb(val);
            }
        }
    }

private:
    static void appendBulk(std::string& out, std::string_view s) {
        out += '$';
        out += std::to_string(s.size());
        out += "\r\n";
        out.append(s.data(), s.size());
        out += "\r\n";
    }
};
```

关键设计点：
1. **命令与响应对齐**：Redis 严格按命令发送顺序返回响应，用 `pending_` 队列保证回调与响应一一对应。
2. **TCP 粘包处理**：`onReadable` 中循环解析，直到数据不足为止。
3. **半写处理**：`sendBuf_` 保留未发送完的数据，下次可写时继续。
4. **Pipeline 天然支持**：连续调用 `command()` 会把多条命令放入 `sendBuf_`，事件循环一次性发送，服务器批量返回。

---

## 3. 存储原理深入：编码与数据结构

### 3.1 对象模型：类型与编码

Redis 每种数据类型（type）对应多种底层编码（encoding），根据数据规模自动切换，以在内存和性能之间取得平衡。`OBJECT ENCODING key` 可查看当前编码：

```bash
# WSL Ubuntu 24.04 实跑
redis-cli SET small 12345
redis-cli OBJECT ENCODING small
# "int"

redis-cli SET big "this is a long string that exceeds 44 bytes for embstr"
redis-cli OBJECT ENCODING big
# "raw"
```

五种对象的编码对照：

| 对象类型 | 编码 | 触发条件 | 底层结构 |
|----------|------|----------|----------|
| string | int | 值为可表示为 long 的整数 | 直接存在 ptr |
| string | embstr | 长度 ≤ 44 字节的字符串 | redisObject + sdshdr 连续分配 |
| string | raw | 长度 > 44 字节 | 独立 sds |
| list | ziplist (≤3.2) | 元素少且小 | 压缩列表 |
| list | quicklist (≥3.2) | 所有 list | 双向链表 + ziplist 节点 |
| hash | ziplist/listpack | 字段数 ≤ 128 且每个值 ≤ 64 字节 | 压缩列表/列表包 |
| hash | hashtable | 超过阈值 | 字典 |
| set | intset | 全为整数且元素数 ≤ 512 | 整数集合 |
| set | hashtable | 超过阈值 | 字典 |
| zset | ziplist/listpack | 元素数 ≤ 128 且每个成员 ≤ 64 字节 | 压缩列表/列表包 |
| zset | skiplist | 超过阈值 | 跳表 + 字典 |

> 阈值可通过配置修改：`hash-max-ziplist-entries`、`hash-max-ziplist-value`、`set-max-intset-entries`、`zset-max-ziplist-entries`、`zset-max-ziplist-value`。Redis 7.0 起部分 ziplist 替换为 listpack。

### 3.2 跳表实现与复杂度论证（zset）

跳表（Skip List）是 zset 的核心有序结构，Redis 的实现比经典跳表有优化：

**结构定义**（简化版）：

```cpp
struct zskiplistNode {
    sds ele;                          // 成员对象
    double score;                     // 分值
    struct zskiplistNode* backward;   // 后退指针（仅 level 1）
    struct zskiplistLevel {
        struct zskiplistNode* forward; // 前进指针
        unsigned int span;             // 跨度：到下一个节点经过的节点数
    } level[];                        // 柔性数组，层级随机
};

struct zskiplist {
    struct zskiplistNode* header, *tail;
    unsigned long length; // 节点数
    int level;            // 当前最大层数
};
```

**随机层级算法**：

```cpp
int zslRandomLevel(void) {
    int level = 1;
    while ((random() & 0xFFFF) < (ZSKIPLIST_P * 0xFFFF)) // P = 0.25
        level += 1;
    return (level < ZSKIPLIST_MAXLEVEL) ? level : ZSKIPLIST_MAXLEVEL; // MAXLEVEL=32
}
```

Redis 用 `p=0.25`（而非经典的 0.5），意味着层级越高越稀疏，空间更省但平均查找路径稍长。最大 32 层，可支持 2^64 个元素。

**复杂度论证**：
- 查找：从最高层开始，沿 forward 指针前进，当前节点下一个节点 score > 目标则下降一层。期望时间复杂度 **O(log N)**。
- 插入：先查找位置 O(log N)，创建新节点（随机层级），更新各层 forward 指针和 span O(log N)。
- 删除：同插入 O(log N)。
- 范围查询（ZRANGEBYSCORE）：找到起点后沿 level 1 遍历，O(log N + M)，M 为返回元素数。
- 排名计算（ZRANK）：利用 span 累加，查找过程中记录经过的跨度总和，O(log N)。

**为什么 zset 同时用跳表和字典**：字典（hashtable）提供 O(1) 的 member→score 查找（ZSCORE），跳表提供有序范围操作。两者共享同一个 ele 的 sds（不重复存储成员），内存开销可控。

### 3.3 整数集合 intset 与升级

intset 是 set 在全整数且元素较少时的编码，底层是有序整数数组：

```cpp
typedef struct intset {
    uint32_t encoding;  // INTSET_ENC_INT16 / INT32 / INT64
    uint32_t length;    // 元素个数
    int8_t contents[];  // 柔性数组，按 encoding 解释
} intset;
```

**升级机制**：当插入一个超出当前 encoding 范围的整数时，整个数组升级。例如当前是 int16（-32768~32767），插入 40000 时：
1. 重新分配内存：`length * sizeof(int32)`
2. 从后往前将每个元素转换为 int32 并放到新位置（从后往前避免覆盖未处理数据）
3. 插入新元素
4. 更新 encoding 字段

**升级的意义**：
- 节省内存：小整数用 int16，比统一 int64 省 75% 空间。
- 灵活性：自动适应数据范围。

**降级**：intset **不支持降级**。一旦升级，即使大元素被删除，encoding 也保持不变。这是简化实现的权衡。

### 3.4 压缩列表 ziplist 与连锁更新

ziplist 是 Redis 为节省内存设计的连续内存结构，用于 list/hash/zset 的小数据场景。布局：

```text
<zlbytes><zltail><zllen><entry><entry>...<entry><zlend>
  4字节     4字节    2字节   每个entry可变      1字节(0xFF)
```

每个 entry 的结构：

```text
<prevlen><encoding><content>
 1或5字节  1或2字节  可变
```

- `prevlen`：前一个 entry 的长度。≤254 用 1 字节，≥255 用 5 字节（0xFE + 4字节长度）。
- `encoding`：标记 content 的类型和长度（字符串/整数、长度）。

**连锁更新问题**：假设 ziplist 中有多个 entry，每个长度恰好为 253 字节（prevlen 用 1 字节）。此时在头部插入一个 254 字节的新 entry：
1. 第一个原 entry 的 prevlen 需从 1 字节扩展为 5 字节，entry 总长度变为 257。
2. 第二个原 entry 的 prevlen 记录前一个长度，现在前一个变成 257 ≥ 255，也需扩展为 5 字节。
3. 以此类推，所有后续 entry 的 prevlen 都要扩展，每次扩展都需 realloc 并移动数据。

这就是**连锁更新（cascade update）**，最坏时间复杂度 O(N²)。虽然实际触发概率极低（需要恰好 250-253 字节的连续 entry），但 Redis 仍在 7.0 引入 listpack 来彻底解决这个问题。

### 3.5 quicklist 与 listpack

**quicklist**（Redis 3.2+，list 的默认编码）：

quicklist 是双向链表，每个节点是一个 ziplist。结合了链表的插入删除优势和 ziplist 的内存紧凑优势：

```text
quicklist: head <-> [ziplist节点] <-> [ziplist节点] <-> ... <-> tail
```

配置项 `list-max-listpack-size`（旧版 `list-max-ziplist-size`）控制每个节点的 ziplist 大小：
- 正数：每个节点最多存 N 个 entry
- 负数：按字节限制，-1=4KB, -2=8KB, -3=16KB, -4=32KB, -5=64KB

`list-compress-depth` 控制两端不压缩的节点数，中间节点用 LZF 压缩，节省内存但增加 CPU。

**listpack**（Redis 7.0 逐步替代 ziplist）：

listpack 重新设计了 entry 编码，核心改进是**去掉 prevlen**，改用每个 entry 末尾的"总长度"字段（向后编码，从后往前解析）。这样插入/修改一个 entry 不会影响后续 entry 的头部，彻底消除连锁更新。

listpack 的 entry 布局：
```text
<encoding-type><element-data><element-total-bytes>
```
`element-total-bytes` 存在 entry 末尾，解析时从后往前读。当前 listpack 已用于新的 list（quicklist 节点）、hash、zset，逐步替代 ziplist。

### 3.6 编码转换触发条件汇总

| 操作 | 可能触发的转换 | 说明 |
|------|----------------|------|
| SET 大整数 | int → raw | 超过 long 范围或追加字符串操作 |
| APPEND 使字符串 >44 字节 | embstr → raw | embstr 只读，修改时先转 raw |
| HSET 字段数 >128 | ziplist → hashtable | 超过 `hash-max-ziplist-entries` |
| HSET 值 >64 字节 | ziplist → hashtable | 超过 `hash-max-ziplist-value` |
| SADD 非整数 | intset → hashtable | 只要有一个非整数就转换 |
| SADD 元素数 >512 | intset → hashtable | 超过 `set-max-intset-entries` |
| ZADD 元素数 >128 | ziplist → skiplist | 超过 `zset-max-ziplist-entries` |
| ZADD 成员 >64 字节 | ziplist → skiplist | 超过 `zset-max-ziplist-value` |

注意：编码转换是**单向的**（除 string 的 int/embstr/raw 在特定操作下可能互转），hash/set/zset 从紧凑编码转为 hashtable/skiplist 后，即使数据量减少也不会转回。这是为了避免频繁转换的性能抖动。

---

## 4. 对象模型深入

### 4.1 redisObject 结构

Redis 所有值对象都用 `redisObject` 表示：

```cpp
typedef struct redisObject {
    unsigned type:4;        // 对象类型：string/list/hash/set/zset/...
    unsigned encoding:4;    // 底层编码
    unsigned lru:LRU_BITS;  // LRU 时间（24位）或 LFU 数据
    int refcount;           // 引用计数
    void *ptr;              // 指向底层数据结构
} robj;
```

- `type` 占 4 位，标识对外数据类型（`TYPE` 命令返回值）。
- `encoding` 占 4 位，标识底层实现（`OBJECT ENCODING` 返回值）。
- `lru` 占 24 位，记录对象最后一次被访问的时间（LRU 模式）或 LFU 计数器（LFU 模式）。
- `refcount` 引用计数，用于对象共享和内存回收。
- `ptr` 指向实际数据（int 编码时直接存在 ptr 中，不额外分配）。

### 4.2 类型检查与命令多态

Redis 命令执行前会做类型检查：执行 `LPOP` 时检查 key 的 type 是否为 list，不是则返回 `WRONGTYPE Operation against a key holding the wrong kind of value`。

通过类型检查后，命令根据 encoding 选择具体实现函数，这就是**命令多态**。例如 `LLEN` 命令：
- encoding 为 quicklist：调用 `quicklistLength()`
- encoding 为 ziplist（旧版）：遍历 ziplist 计数

对外接口统一，底层实现根据编码分发。C++ 中类似虚函数多态，但 Redis 用 C 实现，通过 if/else 或函数指针表分发。

### 4.3 对象共享与引用计数

Redis 对小整数对象（0~9999）做了共享优化：创建这些整数对象时不新建，而是引用共享对象，`refcount++`。这避免了大量小整数的重复内存分配。

```bash
# WSL Ubuntu 24.04 实跑
redis-cli SET a 100
redis-cli SET b 100
redis-cli OBJECT REFCOUNT a
# (integer) 2  —— a 和 b 共享同一个值为100的对象
```

共享对象的限制：
1. 只共享整数对象（字符串内容千差万别，共享查找成本高）。
2. 共享对象的 `refcount` 不会减少到 0，不会被释放。
3. `OBJECT REFCOUNT` 返回的是引用数，共享对象至少为 2（一个是 key 引用，一个是共享池本身？实际共享池不计入 refcount，返回值是被多少 key 引用）。

### 4.4 空转时长与内存淘汰

`OBJECT IDLETIME key` 返回对象的空转秒数（基于 `lru` 字段计算）：

```bash
# WSL Ubuntu 24.04 实跑
redis-cli SET key value
sleep 10
redis-cli OBJECT IDLETIME key
# (integer) 10
```

`lru` 字段只有 24 位，存储的是 `server.lruclock`（每秒更新的分钟级时间戳，取低 24 位）。空转时长 = 当前 lruclock - 对象 lru（处理回绕）。精度为秒级，但因 24 位限制，最大可表示约 194 天（2^24 秒），超过会回绕。

内存淘汰策略（`maxmemory-policy`）利用 lru/lfu 字段：
- `allkeys-lru` / `volatile-lru`：近似 LRU，随机采样 N 个 key（`maxmemory-samples`，默认 5），淘汰空转最久的。
- `allkeys-lfu` / `volatile-lfu`：近似 LFU，lru 字段复用作 8 位计数器 + 16 位衰减时间。
- 精确 LRU 需要维护全局链表，内存开销大，Redis 用采样近似 LRU，效果接近精确 LRU 但开销小得多。

---

## 5. 主从复制深入

### 5.1 全量复制与增量复制

Redis 主从复制分为两个阶段：

**全量复制（Full Resynchronization）**：
1. 从节点执行 `SLAVEOF`（或 `REPLICAOF`），向主节点发送 `PSYNC ? -1`（首次复制，不知道 runid 和 offset）。
2. 主节点返回 `+FULLRESYNC <runid> <offset>`。
3. 主节点执行 `BGSAVE` 生成 RDB 文件，期间的写命令写入复制积压缓冲区。
4. RDB 生成完毕后发送给从节点，从节点清空本地数据并加载 RDB。
5. 主节点将积压缓冲区中的写命令发送给从节点执行。
6. 全量复制完成，进入增量复制阶段。

**增量复制（Partial Resynchronization）**：
网络闪断后重连时，从节点发送 `PSYNC <runid> <offset>`（携带上次复制的主节点 runid 和已同步到的偏移量）：
- 如果 runid 匹配且 offset 之后的数据仍在复制积压缓冲区中：主节点返回 `+CONTINUE`，发送积压的写命令，增量复制完成。
- 否则：返回 `+FULLRESYNC`，触发全量复制。

### 5.2 psync 命令与 runid/offset

`PSYNC` 是 Redis 2.8 引入的命令，替代旧版 `SYNC`（只支持全量复制）。

- **runid**：每个 Redis 节点启动时生成的唯一 40 字符随机 ID（类似 `1d8d7f6a...`）。从节点记录主节点的 runid，重连时比对。如果主节点重启过（runid 变化），必须全量复制。
- **offset（复制偏移量）**：主节点维护 `master_repl_offset`，每发送一个字节的写命令就累加。从节点维护 `slave_repl_offset`，每接收并执行一个字节就累加。两者差值表示从节点落后的字节数。

```bash
# WSL Ubuntu 24.04 实跑：查看复制信息
redis-cli INFO replication
# 示例输出：
# # Replication
# role:master
# connected_slaves:1
# slave0:ip=127.0.0.1,port=6380,state=online,offset=12345,lag=0
# master_replid:1d8d7f6a5b4c3d2e1f0a9b8c7d6e5f4a3b2c1d0e
# master_replid2:0000000000000000000000000000000000000000
# master_repl_offset:12345
# second_repl_offset:-1
# repl_backlog_active:1
# repl_backlog_size:1048576
# repl_backlog_first_byte_offset:11000
# repl_backlog_histlen:1346
```

`master_replid2` 和 `second_repl_offset` 用于故障转移后：旧主节点降级为从节点时，记录之前的 replid 和 offset，让从节点能增量同步到新主节点。

### 5.3 复制积压缓冲区（repl backlog）

复制积压缓冲区是主节点维护的一个**固定大小环形缓冲区**，存储最近的写命令。默认大小 1MB（`repl-backlog-size`）。

工作机制：
- 主节点每执行一个写命令，就将命令追加到 backlog 中，同时记录每个字节对应的 offset。
- backlog 是环形的，写满后覆盖最旧的数据。
- 从节点重连时请求 offset，如果该 offset ≥ `repl_backlog_first_byte_offset`（backlog 中最旧数据的 offset），则可以增量复制。

**backlog 大小的选择**：
- 太小：网络闪断稍久就需要全量复制，开销大。
- 太大：浪费内存。
- 估算公式：`backlog_size > 平均重连时间 × 主节点平均写带宽`。例如主节点每秒写 100KB，通常闪断 10 秒内恢复，则 backlog 至少 1MB，建议设为 2-4MB 留余量。

`repl-backlog-ttl` 控制没有从节点时 backlog 保留多久后释放（默认 3600 秒）。

### 5.4 复制偏移量与心跳

主从节点之间通过心跳维持连接和同步状态：

- **从节点 → 主节点**：每秒发送 `REPLCONF ACK <offset>`，告知主节点自己的同步进度。主节点据此：
  - 计算从节点延迟（`lag`）。
  - 发现从节点 offset 落后，补发数据（如果在 backlog 中）。
  - `min-replicas-to-write` / `min-replicas-max-lag` 配置：如果从节点数量不足或延迟过大，主节点拒绝写入，防止脑裂。

- **主节点 → 从节点**：默认每 10 秒发送 `PING`（`repl-ping-slave-period`），检测从节点存活。

**复制超时**：`repl-timeout`（默认 60 秒），如果主节点超过该时间未收到从节点的 REPLCONF ACK，或从节点未收到主节点的 PING/数据，则认为连接断开，触发重连。

---

## 6. Sentinel 哨兵深入

### 6.1 故障发现：主观下线与客观下线

Sentinel 是 Redis 的高可用方案，由一组 Sentinel 节点（通常 3 个，奇数）监控主从集群。

**主观下线（Subjectively Down，SDOWN）**：
单个 Sentinel 节点向主节点发送 `PING`，如果在 `down-after-milliseconds` 内未收到有效回复（+PONG / -LOADING / -MASTERDOWN），则该 Sentinel 单方面认为主节点主观下线。

SDOWN 是单个 Sentinel 的判断，可能是网络分区导致的误判，需要多个 Sentinel 共识。

**客观下线（Objectively Down，ODOWN）**：
Sentinel 节点之间通过 `SENTINEL is-master-down-by-addr` 命令交换对主节点状态的判断。当收到 `quorum` 个（通常配置为 `quorum = N/2 + 1`）Sentinel 节点都认为主节点 SDOWN 时，主节点被标记为客观下线。

ODOWN 是集群共识结果，触发故障转移。

> 注意：SDOWN 用于主节点，从节点和 Sentinel 节点的故障检测只需 SDOWN（不需要客观下线），因为从节点故障不需要故障转移。

### 6.2 故障转移：选举与切换

ODOWN 后，进入故障转移流程：

**第一步：选举领头 Sentinel（Leader Election）**：
- 每个认为主节点 ODOWN 的 Sentinel 向其他 Sentinel 发送 `SENTINEL is-master-down-by-addr` 命令，携带自己的 `runid`，请求投票。
- 收到请求的 Sentinel 如果还没投给别人，就投给第一个请求者（先到先得）。
- 获得超过半数（`quorum`）投票的 Sentinel 成为领头 Sentinel，负责执行故障转移。
- 如果选举失败（没有获得足够票数），等待 `sentinel failover-timeout * 2` 后重新选举。

这是 Raft 算法的简化版：每个 term（纪元）内每个 Sentinel 只能投一票，先到先得，多数派胜出。

**第二步：从从节点中选举新主节点**：
领头 Sentinel 按以下优先级选择新主：
1. 过滤掉：已下线、断线 5 秒以上（`down-after` 的 5 倍）、与原主节点断开连接超过 `down-after * 10` 的从节点（数据可能太旧）。
2. 按 `slave-priority`（`replica-priority`）排序，优先级值越小越优先（0 表示永远不选为主）。
3. 优先级相同则按复制偏移量 `slave_repl_offset` 排序，offset 越大（数据越新）越优先。
4. offset 也相同则按 `runid` 字典序排序（最小的胜出，保证确定性）。

**第三步：执行故障转移**：
1. 领头 Sentinel 向选中的从节点发送 `SLAVEOF NO ONE`，使其升级为主节点。
2. 领头 Sentinel 向其他从节点发送 `SLAVEOF <new_master_ip> <new_master_port>`，让它们复制新主节点。
3. 原主节点恢复后，Sentinel 会让它成为新主节点的从节点（`SLAVEOF`）。
4. 更新 Sentinel 集群的配置，广播新主节点信息。

### 6.3 配置中心与客户端发现

Sentinel 同时充当**配置中心**：客户端连接 Sentinel 节点，通过 `SENTINEL get-master-addr-by-name <master-name>` 获取当前主节点地址。

客户端典型工作流程：
1. 启动时连接 Sentinel 节点列表（配置多个，防止单点）。
2. 向任意可用 Sentinel 查询主节点地址。
3. 连接主节点进行读写。
4. 订阅 Sentinel 的 `+switch-master` 频道（Pub/Sub），主节点切换时收到通知，自动重连到新主。

Sentinel 节点本身也会故障，客户端应配置至少 3 个 Sentinel 地址。Sentinel 节点之间通过 gossip 协议互相发现和同步状态。

### 6.4 脑裂问题与 min-replicas

**脑裂（Split Brain）**：网络分区导致原主节点与 Sentinel 集群和从节点隔离，但原主节点仍在运行并接受客户端写入。此时 Sentinel 选举了新主节点，分区恢复后出现两个主节点，数据不一致。

防护措施：
1. **`min-replicas-to-write`**：主节点必须至少有 N 个从节点连接，否则拒绝写入。默认 0（不限制）。
2. **`min-replicas-max-lag`**：从节点延迟（lag）必须小于该值（秒），否则不算有效连接。默认 10。

例如配置 `min-replicas-to-write 1` + `min-replicas-max-lag 10`：主节点至少有 1 个延迟 <10 秒的从节点才接受写入。网络分区后原主节点与从节点断开，不满足条件，拒绝写入，避免脑裂数据。

代价：如果所有从节点都故障，主节点也无法写入，可用性降低。生产环境建议至少 2 个从节点，配置 `min-replicas-to-write 1`。

---

## 7. Cluster 集群深入

### 7.1 16384 槽位与 key 路由

Redis Cluster 采用**数据分片**而非主从复制来扩展。整个 key 空间被划分为 **16384 个哈希槽（hash slot）**，每个节点负责一部分槽位。

**key → 槽位映射算法**：
```text
slot = CRC16(key) mod 16384
```

CRC16 是 16 位循环冗余校验，输出 0~65535，对 16384 取模得到 0~16383。

**为什么是 16384（2^14）个槽位**：
- 槽位信息在节点间通过 gossip 消息传播，消息头中用 bitmap 表示节点负责的槽位：16384 bit = 2KB。如果用 65536 个槽位则是 8KB，gossip 消息过大，网络开销高。
- 16384 个槽位对于通常的集群规模（最多 1000 节点）足够，每个节点平均 16 个槽位，迁移粒度合适。
- 官方说明：集群节点数通常不超过 1000，16384 是合理上限。

**客户端路由**：
- 客户端计算 key 的槽位，发送到负责该槽位的节点。
- 如果发送到错误节点，节点返回 `MOVED <slot> <ip:port>`，客户端缓存槽位映射并重试。
- 槽位迁移过程中，节点返回 `ASK <slot> <ip:port>`，客户端需发送 `ASKING` 命令后再重试（ASK 不更新本地缓存，因为迁移未完成）。

### 7.2 gossip 通信与节点握手

Cluster 节点之间通过 **gossip 协议**交换集群状态信息，使用专门的集群总线端口（客户端端口 + 10000，如客户端 6379，总线 16379）。

**gossip 消息类型**：
- `PING`：节点每秒随机向几个其他节点发送 PING，携带自己的状态和已知的其他节点状态（gossip 信息）。
- `PONG`：对 PING 的回复，也携带 gossip 信息。
- `MEET`：新节点加入时发送，通知其他节点有新节点加入。
- `FAIL`：节点判定另一个节点故障时广播。
- `PUBLISH`：Pub/Sub 消息在集群总线传播。

**节点握手流程**：
1. 新节点启动（配置 `cluster-enabled yes`），但还不知道其他节点。
2. 客户端执行 `CLUSTER MEET <ip> <port>`，让新节点与已有节点握手。
3. 两个节点互发 PING/PONG，交换 gossip 信息，新节点逐渐通过 gossip 发现所有其他节点。
4. 所有节点互相认识后，集群进入正常状态，但需要分配槽位才能处理命令。

**gossip 的最终一致性**：节点状态传播是异步的，可能存在短暂不一致（如一个节点刚加入，部分节点还不知道）。最终所有节点状态会收敛一致。

### 7.3 故障转移与故障检测

Cluster 的故障检测与 Sentinel 类似，但由集群节点自身完成（不需要独立的 Sentinel 进程）。

**故障检测**：
- 每个节点定期向其他节点发送 PING，未在 `cluster-node-timeout` 内收到 PONG 则标记为 **PFAIL**（Possible Failure，主观下线）。
- 节点通过 gossip 收集其他节点对某节点的 PFAIL 报告。如果一个节点收到超过半数**主节点**对某节点的 PFAIL 报告，则将其标记为 **FAIL**（客观下线），并广播 FAIL 消息。

**故障转移**（仅针对主节点）：
1. 故障主节点的从节点中，复制偏移量最大的（数据最新的）触发故障转移。
2. 从节点向所有其他主节点请求投票（`FAILOVER_AUTH_REQUEST`）。
3. 获得超过半数主节点投票的从节点升级为主节点。
4. 新主节点广播 PONG 通知集群，接管原主节点的槽位。
5. 其他从节点复制新主节点。

与 Sentinel 的区别：Cluster 的投票者是其他主节点（而非 Sentinel 节点），从节点既是数据副本也是故障转移参与者。

### 7.4 hash tag 与多 key 命令

默认情况下，多 key 命令（如 `MGET`、`SUNION`、事务）要求所有 key 在同一个槽位，否则返回 `CROSSSLOT Keys in request don't hash to the same slot`。

**hash tag** 机制允许控制 key 的槽位：如果 key 中包含 `{...}`，则只对 `{}` 内的字符串计算 CRC16。

```text
user:{1001}:profile  → CRC16("1001") mod 16384
user:{1001}:orders   → CRC16("1001") mod 16384
user:{1001}:messages → CRC16("1001") mod 16384
```

这三个 key 都路由到同一个槽位，可以安全地使用多 key 命令或事务。

**hash tag 的使用场景**：
- 用户维度的数据聚合：同一用户的 profile、orders、messages 放同一槽位。
- 计数器与数据关联：`count:{article_id}` 和 `article:{article_id}` 放同一节点。
- 避免 hash tag 滥用：如果所有 key 都用同一个 tag，所有数据集中到一个槽位，失去分片意义。

### 7.5 重新分片与迁移

集群扩容时需要将部分槽位从旧节点迁移到新节点：

```bash
# WSL Ubuntu 24.04 实跑：使用 redis-cli --cluster 管理
# 查看集群槽位分布
redis-cli --cluster check 127.0.0.1:6379

# 重新分片：将 1000 个槽位从节点迁移到新节点
redis-cli --cluster reshard 127.0.0.1:6379 \
  --cluster-from <old_node_id> \
  --cluster-to <new_node_id> \
  --cluster-slots 1000 \
  --cluster-yes
```

**迁移过程**（在线迁移，不阻塞服务）：
1. 标记槽位为迁移中（migrating），源节点标记 importing（目标节点）。
2. 逐个迁移 key：源节点对每个 key 执行 `DUMP` + `DEL`，目标节点执行 `RESTORE`。
3. 迁移过程中，客户端访问 key：
   - key 还在源节点：正常处理。
   - key 已迁移到目标节点：源节点返回 `ASK` 重定向。
4. 所有 key 迁移完成后，发送 `CLUSTER SETSLOT <slot> NODE <new_node>` 完成槽位所有权转移。

大 key 迁移会阻塞源节点（DUMP/RESTORE 大 key 耗时），生产环境应避免 bigkey，或在低峰期迁移。

---

## 8. 持久化深入

### 8.1 RDB：fork + COW 写时复制

RDB（Redis Database）是某一时刻的全量二进制快照。触发方式：`SAVE`（阻塞）、`BGSAVE`（后台）、配置 `save <seconds> <changes>` 自动触发、主从复制全量同步时自动触发。

**BGSAVE 流程**：
1. Redis 主进程调用 `fork()` 创建子进程。
2. 子进程遍历内存数据，写入临时 RDB 文件。
3. 子进程完成后，原子地替换旧 RDB 文件（rename）。
4. 主进程继续处理客户端请求，不受影响。

**fork + COW（Copy-On-Write）**：
- `fork()` 后，子进程与父进程共享同一份物理内存页（页表指向相同物理页），不立即复制。
- 父进程继续处理写命令时，修改某页数据会触发**写时复制**：内核复制该物理页，父进程写新页，子进程仍读旧页。
- 这样子进程看到的是 fork 时刻的内存快照，保证 RDB 数据一致性。

**fork 的性能问题**：
- `fork()` 本身需要复制父进程的页表，内存越大耗时越长。例如 20GB 内存的 Redis，fork 可能耗时几百毫秒，期间阻塞主进程。
- COW 期间如果父进程写操作频繁，会复制大量内存页，实际内存占用可能达到 2 倍（理论上限）。
- 优化：`rdb-save-incremental-fsync yes`（子进程每写 32MB 调用 fsync，避免最后集中刷盘）；使用大页内存（THP）会导致 COW 粒度变大（2MB 而非 4KB），内存开销增加，建议关闭 THP。

```bash
# WSL Ubuntu 24.04 实跑：查看最后一次 RDB 信息
redis-cli LASTSAVE
# (integer) 1757280000  —— Unix 时间戳

redis-cli CONFIG GET save
# 1) "save"
# 2) "3600 1 300 100 60 10000"  —— 1小时1次写 / 5分钟100次写 / 1分钟10000次写
```

### 8.2 AOF：always / everysec / no

AOF（Append Only File）记录每个写命令，以 RESP 协议格式追加到文件。重启时重放所有命令恢复数据。

**appendfsync 三种策略**：

| 策略 | 行为 | 安全性 | 性能 |
|------|------|--------|------|
| `always` | 每个写命令都调用 fsync，刷到磁盘才返回 | 最高，最多丢 1 条命令 | 最低，每个写都刷盘 |
| `everysec` | 每秒调用一次 fsync（后台线程），写命令先写缓冲区 | 最多丢 1 秒数据 | 高，推荐默认 |
| `no` | 不主动 fsync，由操作系统决定何时刷盘（通常 30 秒） | 可能丢 30 秒数据 | 最高 |

`everysec` 的实现：主进程将写命令写入 AOF 缓冲区（aof_buf），后台线程每秒执行一次 `fsync`。如果后台 fsync 耗时超过 2 秒（磁盘慢），主进程会阻塞等待 fsync 完成（`aof-rewrite-incremental-fsync` 相关逻辑），避免缓冲区无限增长。

**AOF 重写**见下节。

### 8.3 AOF 重写：bgrewriteaof 与缓冲区

AOF 文件会随时间不断增长（重复命令、已删除 key 的命令等）。AOF 重写（Rewrite）生成一个新的 AOF 文件，只包含恢复当前数据所需的最小命令集。

**重写原理**：不是读取旧 AOF 再处理，而是**遍历内存中的数据**，为每个 key 生成一条等效的写命令（如 `SET key value`、`RPUSH list e1 e2 ...`）。这样旧文件中的冗余命令自然消失。

**BGREWRITEAOF 流程**：
1. 主进程 `fork()` 子进程。
2. 子进程遍历内存，写命令到新 AOF 文件。
3. **重写期间的写命令**：主进程继续处理写请求，这些命令同时写入：
   - 旧 AOF 缓冲区（正常追加，保证旧 AOF 不丢数据）
   - **AOF 重写缓冲区**（aof_rewrite_buf），记录重写期间的增量命令
4. 子进程完成新 AOF 文件后，通知主进程。
5. 主进程将重写缓冲区中的命令追加到新 AOF 文件末尾。
6. 原子地替换旧 AOF 文件（rename）。

触发条件：
- 手动 `BGREWRITEAOF`
- 自动：`auto-aof-rewrite-percentage 100`（AOF 文件比上次重写后增长 100%）且 `auto-aof-rewrite-min-size 64mb`（至少 64MB）

### 8.4 混合持久化（4.0+）

Redis 4.0 引入混合持久化（`aof-use-rdb-preamble yes`，默认开启），结合 RDB 和 AOF 的优点：

- AOF 重写时，前半部分是 RDB 格式的二进制快照（紧凑、加载快），后半部分是重写期间的增量 AOF 命令。
- 重启加载时：先加载 RDB 部分（快），再重放增量 AOF 命令（少）。
- 兼顾了 RDB 的加载速度和 AOF 的数据安全性。

文件结构：
```text
[RDB 二进制数据][AOF 增量命令]
```

加载时 Redis 通过文件开头的 `REDIS` 魔数识别 RDB 部分，RDB 结束后继续解析 AOF 命令。

> 来源：《Redis设计与实现》黄健宏 第 10-11 章；Redis 官方文档 Persistence。

---

## 9. 缓存三兄弟：工程级解决方案

《02-Redis设计与数据结构.md》第 7 章已介绍缓存三兄弟的基本概念，本节深入工程级实现方案。

### 9.1 缓存击穿：热点 key 过期

**场景**：某个热点 key（如秒杀商品库存）过期瞬间，大量并发请求同时穿透到数据库，数据库压力骤增。

**方案一：互斥锁（Mutex Key）**：

```cpp
// C++ 伪代码
std::string getWithMutex(const std::string& key) {
    std::string val = redis.get(key);
    if (!val.empty()) return val;

    // 尝试加锁
    std::string lockKey = "lock:" + key;
    bool locked = redis.set(lockKey, "1", SET_NX | SET_EX, 10); // 10秒过期
    if (locked) {
        // 拿到锁，查 DB 并回写缓存
        val = db.query(key);
        redis.set(key, val, EX, 300);
        redis.del(lockKey);
        return val;
    } else {
        // 没拿到锁，等待重试
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
        return getWithMutex(key); // 递归重试，需加最大重试次数
    }
}
```

注意：锁必须有过期时间（防止持有者崩溃导致死锁）；重试需有最大次数和退避策略。

**方案二：逻辑过期（Logical Expiration）**：

不设置 Redis 物理过期时间，而是在 value 中嵌入逻辑过期时间：

```cpp
struct CacheData {
    std::string data;
    std::chrono::system_clock::time_point expireAt; // 逻辑过期时间
};

std::string getWithLogicalExpire(const std::string& key) {
    CacheData cd = redis.get<CacheData>(key); // 反序列化
    if (cd.data.empty()) return ""; // key 不存在

    if (cd.expireAt > std::chrono::system_clock::now()) {
        return cd.data; // 未过期，直接返回
    }

    // 已过期，异步重建缓存（不阻塞当前请求）
    std::string lockKey = "lock:" + key;
    if (redis.set(lockKey, "1", SET_NX | SET_EX, 10)) {
        std::thread([key]() {
            std::string newVal = db.query(key);
            CacheData newCd{newVal, now() + 300s};
            redis.set(key, serialize(newCd));
            redis.del(lockKey);
        }).detach();
    }

    return cd.data; // 返回旧数据（可接受短暂不一致）
}
```

优点：请求永远不阻塞（返回旧数据）；缺点：内存中 key 永不过期（需要主动清理或设置很长的物理过期兜底），存在短暂数据不一致。

**方案三：热点 key 永不过期 + 主动更新**：
对于确定的热点 key（如首页配置），不设过期时间，由后台定时任务主动更新缓存。

### 9.2 缓存穿透：不存在的 key

**场景**：查询一个数据库和缓存中都不存在的 key（如恶意攻击构造不存在的用户 ID），每次请求都打到数据库。

**方案一：缓存空值（Cache Null）**：

```cpp
std::string getWithNullCache(const std::string& key) {
    std::string val = redis.get(key);
    if (val == "__NULL__") return "";      // 缓存的空值
    if (!val.empty()) return val;            // 正常缓存

    std::string dbVal = db.query(key);
    if (dbVal.empty()) {
        redis.set(key, "__NULL__", EX, 60); // 缓存空值，短过期
        return "";
    }
    redis.set(key, dbVal, EX, 300);
    return dbVal;
}
```

空值过期时间要短（通常 30-120 秒），防止数据新增后长时间不可用。

**方案二：布隆过滤器（Bloom Filter）**：

在缓存前加一层布隆过滤器，将所有存在的 key 的哈希值存入布隆过滤器。查询时先过布隆过滤器：
- 布隆过滤器说不存在 → 一定不存在，直接返回，不查缓存和 DB。
- 布隆过滤器说存在 → 可能存在（有误判率），继续查缓存和 DB。

```cpp
// C++ 伪代码：使用 RedisBloom 模块或自研布隆过滤器
class BloomCache {
    BloomFilter bf; // 启动时从 DB 加载所有合法 key
public:
    std::string get(const std::string& key) {
        if (!bf.mightContain(key)) return ""; // 一定不存在
        std::string val = redis.get(key);
        if (!val.empty()) return val;
        return db.query(key);
    }
};
```

布隆过滤器的优点是省内存（1 亿 key 只需约 100MB，误判率 1%），缺点是存在误判（可能放过不存在的 key）且删除困难（需要计数布隆过滤器）。

**方案三：接口层参数校验**：
对明显非法的请求（如 ID 为负数、格式不对）在接口层直接拒绝，从源头减少穿透。

### 9.3 缓存雪崩：大量 key 同时过期

**场景**：大量缓存 key 在同一时刻过期（如批量设置了相同的过期时间），或 Redis 节点宕机，导致大量请求同时打到数据库。

**方案一：过期时间加随机偏移**：

```cpp
// 设置过期时间时加随机值，避免集中过期
int baseTTL = 300; // 5 分钟
int jitter = rand() % 120; // 0~120 秒随机偏移
redis.set(key, value, EX, baseTTL + jitter);
```

这是最简单有效的方案，将过期时间打散在 5~7 分钟范围内，避免同时过期。

**方案二：多级缓存**：

```text
请求 → 本地缓存（Caffeine/自研 LRU） → Redis 分布式缓存 → DB
```

本地缓存作为一级缓存，即使 Redis 中的 key 过期，本地缓存可能还有数据（本地缓存过期时间设得更长或用不同的过期策略），减少穿透到 DB 的请求。本地缓存容量有限，只存热点数据。

**方案三：Redis 高可用集群**：

避免 Redis 单点故障导致雪崩：
- 主从 + Sentinel：主节点故障自动切换。
- Cluster：多节点分片，单节点故障只影响部分槽位。
- 客户端熔断降级：Redis 不可用时，本地缓存兜底或返回默认值，不直接打 DB。

**方案四：限流降级**：
在数据库前加限流（如令牌桶），超过阈值的请求直接返回降级数据（如默认值、缓存的旧数据），保护数据库不被打垮。

### 9.4 三者对比与方案选型表

| 问题 | 触发原因 | 核心方案 | 辅助方案 |
|------|----------|----------|----------|
| 缓存击穿 | 单个热点 key 过期 | 互斥锁 / 逻辑过期 | 热点 key 永不过期 |
| 缓存穿透 | 查询不存在的 key | 缓存空值 / 布隆过滤器 | 参数校验 |
| 缓存雪崩 | 大量 key 同时过期 / Redis 宕机 | 过期时间随机偏移 / 高可用集群 | 多级缓存 / 限流降级 |

组合使用：生产环境通常同时部署"过期时间随机偏移 + 缓存空值 + 互斥锁（热点 key）+ Redis 高可用"，形成纵深防御。

---

## 10. 分布式锁深入

### 10.1 SET NX EX 基础锁

分布式锁的基础实现：

```bash
# 加锁：SET key value NX EX seconds
# NX = 不存在才设置（互斥），EX = 过期时间（防死锁）
SET lock:order:123 "unique_token" NX EX 30
```

- `NX` 保证互斥：只有一个客户端能设置成功。
- `EX 30` 保证锁不会永久持有：持有者崩溃后 30 秒自动释放。
- `value` 必须是唯一值（如 UUID + 线程 ID），用于释放锁时校验持有者身份，防止误删别人的锁。

**错误示范**：
```bash
# 错误1：先 SETNX 再 EXPIRE，非原子，中间崩溃导致锁永不过期
SETNX lock:order:123 1
EXPIRE lock:order:123 30

# 错误2：释放锁时不校验 value，可能删除别人的锁
DEL lock:order:123
```

### 10.2 Lua 脚本保证原子性

释放锁必须"校验 value + 删除"原子执行，用 Lua 脚本：

```lua
-- unlock.lua
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
```

```cpp
// C++ 调用
std::string unlockScript = R"(
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
)";

bool unlock(const std::string& key, const std::string& token) {
    redisReply* reply = (redisReply*)redisCommand(c,
        "EVAL %s 1 %s %s", unlockScript.c_str(), key.c_str(), token.c_str());
    bool success = reply && reply->type == REDIS_REPLY_INTEGER && reply->integer == 1;
    freeReplyObject(reply);
    return success;
}
```

Redis 执行 Lua 脚本是原子的：脚本执行期间不处理其他命令，保证"校验+删除"不会被打断。

### 10.3 Redlock 算法与争议

**问题**：单节点 Redis 分布式锁在主从切换时可能丢失锁：
1. 客户端 A 在主节点获取锁。
2. 主节点宕机，锁数据还未同步到从节点。
3. 从节点升级为主节点。
4. 客户端 B 在新主节点获取同一个锁。
5. A 和 B 同时持有锁 → 锁失效。

**Redlock 算法**（Redis 作者 antirez 提出）：
假设部署 N 个（通常 5 个）独立的 Redis 主节点（无主从关系）：
1. 客户端记录当前时间戳。
2. 依次向 N 个节点请求加锁（相同 key 和 value，短超时，如 5-50ms，防止单个节点慢阻塞）。
3. 计算成功加锁的节点数。如果 ≥ N/2 + 1（如 5 节点中 ≥3 个），且总耗时 < 锁过期时间，则认为加锁成功。
4. 加锁失败则向所有节点发送解锁命令（包括加锁失败的节点，因为可能加锁成功但回复丢失）。

**争议**（Martin Kleppmann 等学者批评）：
1. **依赖时间假设**：Redlock 假设各节点时钟同步且进程调度延迟可控。如果某个节点发生 GC pause 或时钟跳变，可能导致锁过期判断错误。
2. **性能开销大**：每次加锁需要访问 N 个节点，延迟高。
3. **实际场景中主从切换锁丢失概率极低**：配合 `min-replicas-to-write` 和合理的复制配置，单节点锁已足够。

**工程实践**：
- 大多数业务场景用单节点 `SET NX EX` + Lua 解锁即可，配合看门狗续期。
- 对锁安全性要求极高的场景（如金融扣款），建议用 etcd/ZooKeeper 的分布式锁（基于 Raft/ZAB 共识，不依赖时钟），或在数据库层面用乐观锁/唯一索引兜底。
- Redlock 在实际生产中使用较少，更多是学术讨论。

> 来源：《Redis设计与实现》黄健宏；antirez 博客 "Redlock: Is this algorithm actually safe?"；Martin Kleppmann "How to do distributed locking"。

### 10.4 看门狗续期与 C++ 实现

**问题**：锁的过期时间难以设置：
- 太短：业务逻辑还没执行完锁就过期了，其他客户端获取锁，并发问题。
- 太长：持有者崩溃后，锁要等很久才释放，影响可用性。

**看门狗（Watchdog）续期**：
加锁成功后，启动一个后台定时任务（看门狗），每隔锁过期时间的 1/3（如锁 30 秒，每 10 秒）检查锁是否仍被当前线程持有，如果是则续期（延长过期时间）。业务执行完释放锁时停止看门狗。

```cpp
class DistributedLock {
    std::string key_;
    std::string token_;
    int ttlSeconds_;
    std::atomic<bool> locked_{false};
    std::thread watchdog_;

    // Lua 续期脚本：校验 value 后延长过期时间
    static constexpr const char* kRenewScript = R"(
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('expire', KEYS[1], ARGV[2])
else
    return 0
end
)";

public:
    bool tryLock(const std::string& key, int ttlSeconds = 30) {
        key_ = key;
        ttlSeconds_ = ttlSeconds;
        token_ = generateUUID(); // 唯一标识

        redisReply* r = (redisReply*)redisCommand(redisCtx_,
            "SET %s %s NX EX %d", key.c_str(), token_.c_str(), ttlSeconds);
        bool ok = r && r->type == REDIS_REPLY_STATUS && std::string(r->str) == "OK";
        freeReplyObject(r);
        if (!ok) return false;

        locked_ = true;
        startWatchdog();
        return true;
    }

    void unlock() {
        locked_ = false;
        if (watchdog_.joinable()) watchdog_.join();
        // Lua 原子解锁
        evalLua(kUnlockScript, {key_}, {token_});
    }

private:
    void startWatchdog() {
        watchdog_ = std::thread([this]() {
            int interval = ttlSeconds_ / 3; // 1/3 过期时间续期一次
            while (locked_) {
                std::this_thread::sleep_for(std::chrono::seconds(interval));
                if (!locked_) break;
                // 续期
                evalLua(kRenewScript, {key_}, {token_, std::to_string(ttlSeconds_)});
            }
        });
    }
};
```

看门狗机制是 Redisson（Java Redis 客户端）的核心特性，C++ 中需自行实现。注意：
- 看门狗线程必须在 `unlock()` 时正确停止，避免线程泄漏。
- 续期失败（如 Redis 连接断开）应记录日志，锁可能已过期。
- 可重入锁需要维护持有计数，续期时也要考虑计数。

---

## 11. 常见坑与最佳实践

### 11.1 常见坑汇总

| 坑 | 现象 | 原因 | 解决方案 |
|----|------|------|----------|
| Bigkey | Redis 阻塞、内存不均 | 单个 value 过大（如 list 百万元素） | 拆分、压缩、避免 `KEYS *` |
| Hotkey | 单节点 CPU 打满 | 单个 key 访问量极高 | 本地缓存、key 分片（加后缀） |
| 缓存与 DB 不一致 | 读到旧数据 | 并发读写时序问题 | 延迟双删、订阅 binlog |
| 分布式锁误删 | 并发问题 | 解锁不校验 value | Lua 脚本原子解锁 |
| 主从切换数据丢失 | 锁失效、数据回退 | 异步复制，主宕机时数据未同步 | `min-replicas-to-write`、半同步 |
| Cluster 多 key 报错 | `CROSSSLOT` | 多 key 不在同一槽位 | hash tag `{prefix}` |
| AOF 文件过大 | 重启慢、磁盘满 | 未开启重写或重写阈值不合理 | `auto-aof-rewrite-percentage` |
| fork 耗时过长 | 主进程阻塞 | 内存大、页表复制慢 | 关闭 THP、控制实例内存 ≤20GB |
| 内存碎片率高 | used_memory 远小于 rss | 频繁更新不同大小的 value | `activedefrag yes`、`jemalloc` 调优 |

### 11.2 最佳实践

1. **连接池**：C++ 中使用连接池复用 Redis 连接，避免每次命令新建连接（TCP 握手 + AUTH + SELECT 开销）。连接池大小 = 并发数 / 单连接 QPS，通常 10-50 足够。
2. **Pipeline 批量操作**：批量读写用 pipeline，减少 RTT。但注意 pipeline 不是原子的，需要原子性用 Lua。
3. **Lua 脚本**：复杂的多命令原子操作用 Lua，如"先查再写"、"计数+判断"。Lua 脚本不要执行耗时操作（Redis 单线程，脚本执行期间阻塞所有命令）。
4. **key 命名规范**：`业务:对象:ID`，如 `order:detail:12345`。用冒号分隔，便于按前缀批量管理和 `SCAN` 匹配。
5. **避免大事务**：MULTI/EXEC 中的命令过多会阻塞主进程。大事务拆分为小事务或 Lua。
6. **监控**：监控 `INFO memory`（内存碎片率）、`INFO stats`（keyspace 命中/未命中）、`INFO replication`（主从延迟）、`slowlog`（慢查询）、`latency`（延迟）。
7. **版本选择**：生产环境建议 Redis 6.x 或 7.x（支持多线程 IO、RESP3、listpack、Functions）。Redis 7.0 的 Functions 比 Lua 脚本更易管理和复用。

---

## 12. 快速参考卡片

### 12.1 数据结构编码对照表

| 对象 | 编码 | 触发条件 | 底层结构 |
|------|------|----------|----------|
| string | int | long 范围内整数 | ptr 直接存值 |
| string | embstr | ≤44 字节 | 连续分配 sds |
| string | raw | >44 字节 | 独立 sds |
| list | quicklist | 所有（3.2+） | 双向链表+ziplist/listpack |
| hash | listpack/ziplist | ≤128 字段且 ≤64B/值 | 紧凑列表 |
| hash | hashtable | 超阈值 | 字典 |
| set | intset | 全整数且 ≤512 元素 | 有序整数数组 |
| set | hashtable | 超阈值或含非整数 | 字典 |
| zset | listpack/ziplist | ≤128 元素且 ≤64B/成员 | 紧凑列表 |
| zset | skiplist | 超阈值 | 跳表+字典 |

### 12.2 缓存问题解决方案表

| 问题 | 首选方案 | 备选方案 |
|------|----------|----------|
| 击穿（热点 key 过期） | 互斥锁 | 逻辑过期 / 永不过期 |
| 穿透（不存在 key） | 缓存空值 | 布隆过滤器 / 参数校验 |
| 雪崩（大量同时过期） | 过期时间随机偏移 | 多级缓存 / 高可用集群 / 限流 |

### 12.3 常用配置速查

```text
# 内存
maxmemory 4gb
maxmemory-policy allkeys-lru
maxmemory-samples 5

# 持久化
save 3600 1 300 100 60 10000
appendonly yes
appendfsync everysec
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb
aof-use-rdb-preamble yes

# 复制
repl-backlog-size 4mb
repl-backlog-ttl 3600
min-replicas-to-write 1
min-replicas-max-lag 10

# 集群
cluster-enabled yes
cluster-config-file nodes.conf
cluster-node-timeout 15000

# 慢查询
slowlog-log-slower-than 10000
slowlog-max-len 128

# 内存碎片整理
activedefrag yes
active-defrag-ignore-bytes 100mb
active-defrag-threshold-lower 10
active-defrag-threshold-upper 100
```

### 12.4 常用诊断命令

```bash
# 内存与对象
INFO memory
OBJECT ENCODING key
OBJECT REFCOUNT key
OBJECT IDLETIME key
MEMORY USAGE key

# 慢查询与延迟
SLOWLOG GET 10
LATENCY LATEST
LATENCY DOCTOR

# 复制与集群
INFO replication
CLUSTER INFO
CLUSTER NODES
CLUSTER SLOTS

# 持久化
INFO persistence
LASTSAVE
BGREWRITEAOF

# 客户端与连接
CLIENT LIST
INFO stats
INFO clients
```

---

上一篇：《05-XML数据格式与解析.md》
下一篇：《07-MySQL深入：事务锁与索引优化.md》
