# 异步日志与Protobuf

> 本节目标：掌握异步日志的设计原理与手撕实现——同步日志三大瓶颈（IO 阻塞 / 格式化 CPU / 锁竞争）、双缓冲机制（前台写 A 后台写 B、指针交换缩临界区、空闲池复用 4MB 缓冲、写满或 3s 超时触发交接）、崩溃找回（信号处理器内仅用 async-signal-safe 的 write 尽力刷出尾部日志）；掌握 spdlog 实战（basic/rotating/daily 三类文件 sink、异步线程池与 block/overwrite_oldest 溢出策略、pattern 格式符、flush_on+flush_every）；理解应用层协议设计七要素（magic/version/cmd/seq/len/crc/body）与长度前缀定界解决 TCP 粘包半包；掌握 Protobuf（.proto 语法、序列化 API、varint 变长编码与 tag 规则、zigzag 负数映射、字段编号兼容）。前置《../12-网络与服务器架构/04-Reactor与高性能网络库.md》（TCP 字节流与粘包），关联《01-中间件实战.md》（RPC 与序列化选型）。 课程模块 3.3：开源组件——异步日志方案 spdlog、应用层协议设计 ProtoBuf。 日志是故障复盘的**第一现场**，协议是服务间对话的**语法**。

## 本章速览

- [1. 概述](#1-概述)
- [2. 性能瓶颈分析](#2-性能瓶颈分析)
  - [2.1 三大瓶颈](#21-三大瓶颈)
  - [2.2 同步 vs 异步日志对比](#22-同步-vs-异步日志对比)
- [3. 异步日志设计与手撕【核心】](#3-异步日志设计与手撕核心)
  - [3.1 总体架构](#31-总体架构)
  - [3.2 双缓冲机制【高频】](#32-双缓冲机制高频)
  - [3.3 批量写入](#33-批量写入)
  - [3.4 崩溃后的日志找回](#34-崩溃后的日志找回)
  - [3.5 手撕精简异步日志（完整代码）](#35-手撕精简异步日志完整代码)
- [4. spdlog 实战](#4-spdlog-实战)
  - [4.1 架构分层](#41-架构分层)
  - [4.2 基础用法（文件 sink 三兄弟）](#42-基础用法文件-sink-三兄弟)
  - [4.3 异步用法与溢出策略](#43-异步用法与溢出策略)
  - [4.4 pattern 格式符与崩溃找回](#44-pattern-格式符与崩溃找回)
- [5. 应用层协议设计](#5-应用层协议设计)
  - [5.1 为什么需要应用层协议](#51-为什么需要应用层协议)
  - [5.2 业界协议对比](#52-业界协议对比)
  - [5.3 协议设计要素清单](#53-协议设计要素清单)
  - [5.4 消息完整性三保障](#54-消息完整性三保障)
- [6. Protobuf【核心】](#6-protobuf核心)
  - [6.1 安装与 CMake 集成](#61-安装与-cmake-集成)
  - [6.2 .proto 语法速查](#62-proto-语法速查)
  - [6.3 手撕 IM 通信协议](#63-手撕-im-通信协议)
  - [6.4 三种序列化方案对比](#64-三种序列化方案对比)
  - [6.5 编码原理【高频】](#65-编码原理高频)
  - [6.6 常用 API 表](#66-常用-api-表)
- [7. 快速参考卡片](#7-快速参考卡片)
- [8. 常见问题与坑](#8-常见问题与坑)

---

## 1. 概述

日志写不下来，线上问题就只能靠猜。同步日志在高 QPS 下的问题可以量化：每条日志一次 `write` 系统调用，单次开销微秒级；1 万 QPS 的服务哪怕 10% 请求打 5 条日志，就是 5000 次/秒系统调用，叠加磁盘抖动时业务线程直接被拖住。

| 目标 | 说明 |
| --- | --- |
| 业务线程快 | 日志调用只做内存拷贝，微秒内返回 |
| 落盘高效 | 后台线程聚合批量写，单次 write 写一大块 |
| 崩溃可找回 | 进程挂了，最后几条日志尽量不丢 |
| 好用好接 | 滚动、分级、格式化、异步开关齐全 |

## 2. 性能瓶颈分析

### 2.1 三大瓶颈

| 瓶颈 | 说明 | 量化 |
| --- | --- | --- |
| 磁盘 IO 阻塞 | write 直接落在业务调用栈上，页缓存脏了/磁盘忙时同步等待 | 慢盘下单次 write 可到毫秒级 |
| 格式化 CPU 开销 | 时间戳、level、字符串拼接每条都要做 | 纯 CPU，无法靠"快盘"解决 |
| 锁竞争 | 多线程写同一文件要互斥，临界区还包含写盘 | 线程越多越恶化 |

### 2.2 同步 vs 异步日志对比

| 维度 | 同步日志 | 异步日志 |
| --- | --- | --- |
| 延迟归属 | 业务线程承担全部（格式化+锁+write） | 业务线程只承担"拷贝进内存缓冲" |
| 吞吐 | 受最慢一次 write 拖累 | 后台批量 write，吞吐高一个量级 |
| 顺序 | 天然有序 | 靠同一把锁保证入队有序即落盘有序 |
| 丢失风险 | 写完就落盘，基本不丢 | 崩溃时缓冲里未刷的部分可能丢（见 3.4） |
| 适用 | 低频工具、调试 | 高 QPS 服务标配 |

## 3. 异步日志设计与手撕【核心】

### 3.1 总体架构

```text
 业务线程1 ─┐
 业务线程2 ─┼─► append(格式化好的行) ──► 当前缓冲 A（加锁追加）
 业务线程N ─┘                                │ 写满 或 后台 3s 超时
                                             ▼
                              加锁：A 交给 full 列表，取一块空闲缓冲继续
                                             │ notify
                                             ▼
                     后台线程：swap 出 full 列表 ──► 无锁批量 write 到文件
                                             │
                              写完的缓冲归还空闲池（复用，避免反复 malloc 4MB）
```

### 3.2 双缓冲机制【高频】

| 要点 | 说明 |
| --- | --- |
| 缓冲 A（当前） | 前台线程在此追加日志；写满才触发交接 |
| 缓冲 B（后台在写） | 后台线程慢慢写盘，与前台互不干扰 |
| 交接动作 | 前台**只交换指针/链表头**，锁的临界区是"指针交换"而非整块写盘——竞争窗口从"毫秒级写盘"缩到"纳秒级交换" |
| 空闲池 | 写完的缓冲 reset 后放回 spare 池复用，避免每秒多次分配/释放 4MB |
| 触发时机 | 缓冲写满（高流量）或超时 3 秒（低流量也要及时落盘） |

为什么是"双缓冲"而不是单缓冲+锁：单缓冲下后台写盘的全程都要持锁，前台全在等；双缓冲把"写盘"挪出临界区，前台几乎无感。

### 3.3 批量写入

后台线程一次醒来可能拿到多个满缓冲 + 一个未满缓冲，逐个 `::write`（同一 fd 顺序写，页缓存顺序落盘）；生产实现可用 `writev` 聚合。单次系统调用摊到几百上千条日志，系统调用次数下降三个数量级。

### 3.4 崩溃后的日志找回

进程收到 SIGSEGV/SIGABRT 时，最后几条日志还躺在内存缓冲里没落盘。方案：注册信号处理器，尽力把当前缓冲 write 出去。

| 约束 | 说明 |
| --- | --- |
| async-signal-safe | 信号处理器里**只能调用异步信号安全函数**：`write` 可以；`printf`（内部持 stdio 锁+可能 malloc）、`malloc/free`、加锁都不可以 |
| 尽力而为 | 不加锁直接 write 当前缓冲，与业务线程有竞态，但通常能把最后几条带出去 |
| 兜底 | spdlog 等价物：`flush_on(err)`（错误级别立即刷）+ `flush_every(3s)` 定时刷，把丢失窗口压到秒级 |

### 3.5 手撕精简异步日志（完整代码）

```cpp
// async_log.hpp —— 双缓冲 + 后台线程的精简异步日志（单文件可直接编译验证）
#pragma once
#include <atomic>
#include <condition_variable>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <memory>
#include <mutex>
#include <thread>
#include <unistd.h>
#include <sys/time.h>
#include <vector>

constexpr int kBufSize = 4 * 1024 * 1024;     // 4MB 大缓冲

template <int N>
class FixedBuf {                              // 定长缓冲：追加 + 复位复用
public:
    void  append(const char *s, size_t n) { if (n <= avail()) { memcpy(cur_, s, n); cur_ += n; } }
    const char *data()  const { return buf_; }
    size_t len()   const { return cur_ - buf_; }
    size_t avail() const { return buf_ + N - cur_; }
    void  reset()        { cur_ = buf_; }
private:
    char buf_[N]{};
    char *cur_ = buf_;
};

class AsyncLogging {
public:
    static AsyncLogging &instance() { static AsyncLogging l; return l; }

    void start(const char *file) {
        fd_ = ::open(file, O_CREAT | O_WRONLY | O_APPEND, 0644);
        running_ = true;
        cur_ = std::make_unique<Buf>();
        th_ = std::thread(&AsyncLogging::backend, this);
    }
    void stop() {
        running_ = false;
        cv_.notify_one();
        if (th_.joinable()) th_.join();
        ::close(fd_);
    }

    // ---------- 前端：业务线程调用，只做内存拷贝 ----------
    void append(const char *line, size_t n) {
        std::lock_guard<std::mutex> lk(mtx_);
        if (cur_->avail() > n) { cur_->append(line, n); return; }
        // 当前缓冲写满：交接给后台，换一块空闲缓冲继续写
        full_.push_back(std::move(cur_));
        if (spare_.empty()) cur_ = std::make_unique<Buf>();      // 无空闲才新建
        else { cur_ = std::move(spare_.back()); spare_.pop_back(); }
        cur_->append(line, n);
        cv_.notify_one();                                        // 唤醒后台
    }

    // 崩溃处理器里调用：不加锁直接 write（async-signal-safe 的 write，尽力而为）
    void flushCurrentUnsafe() {
        std::lock_guard<std::mutex> lk(mtx_);   // 注：严格说锁非 async-signal-safe，
        ::write(fd_, cur_->data(), cur_->len());// 此处"尽力而为"，多数情况下能带出尾部日志
    }

private:
    using Buf = FixedBuf<kBufSize>;
    void backend() {                           // ---------- 后台线程 ----------
        auto cur = std::make_unique<Buf>();    // 本地备用缓冲
        std::vector<std::unique_ptr<Buf>> todo;
        while (running_) {
            {
                std::unique_lock<std::mutex> lk(mtx_);
                if (full_.empty()) cv_.wait_for(lk, std::chrono::seconds(3)); // 3s 超时也刷
                todo.swap(full_);               // ★ 交换链表头，O(1) 拿走全部
                todo.push_back(std::move(cur_));            // 未满的当前缓冲也带走
                cur_ = std::move(cur);                      // 本地备用顶给前台
            }                                               // ★ 出临界区再写盘
            if (todo.size() > 16) todo.resize(16);          // 堆积过深：丢弃保护
            for (auto &b : todo) { ::write(fd_, b->data(), b->len()); b->reset(); }
            // ★ 从写完的缓冲里拿回一块，作为下一轮的本地备用（否则下一轮 cur 为空）
            if (!todo.empty()) { cur = std::move(todo.back()); todo.pop_back(); }
            else cur = std::make_unique<Buf>();
            {   // 其余归还空闲池（上限 16 块，防内存膨胀）
                std::lock_guard<std::mutex> lk(mtx_);
                while (!todo.empty() && spare_.size() < 16) {
                    spare_.push_back(std::move(todo.back()));
                    todo.pop_back();
                }
                todo.clear();
            }
        }
    }

    int fd_ = -1;
    std::atomic<bool> running_{false};
    std::thread th_;
    std::mutex mtx_;                                        // 只保护指针交接
    std::condition_variable cv_;
    std::unique_ptr<Buf> cur_;                              // 前台正在写
    std::vector<std::unique_ptr<Buf>> full_;                // 待落盘
    std::vector<std::unique_ptr<Buf>> spare_;               // 空闲池
};

// ---------- 时间戳格式化（业务线程里做，不在信号处理器里） ----------
inline int fmt_now(char *buf, size_t n) {
    struct timeval tv; gettimeofday(&tv, nullptr);
    struct tm t; localtime_r(&tv.tv_sec, &t);
    return snprintf(buf, n, "%04d-%02d-%02d %02d:%02d:%02d.%03d",
                    t.tm_year + 1900, t.tm_mon + 1, t.tm_mday,
                    t.tm_hour, t.tm_min, t.tm_sec, (int)(tv.tv_usec / 1000));
}

#define LOG_INFO(fmt, ...)                                                     \
    do {                                                                       \
        char ts[32], line[512];                                                \
        fmt_now(ts, sizeof(ts));                                               \
        int _n = snprintf(line, sizeof(line), "%s [I] %s:%d " fmt "\n",        \
                          ts, __FILE__, __LINE__, ##__VA_ARGS__);              \
        if (_n > 0) AsyncLogging::instance().append(line, _n);                 \
    } while (0)
// LOG_WARN/LOG_ERROR/LOG_FATAL 同构，改级别字母；DEBUG 可加编译期开关

// ---------- 崩溃找回：注册一次 ----------
#include <csignal>
inline void install_crash_handler() {
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = [](int sig) {              // 处理器内只能用 async-signal-safe 函数
        AsyncLogging::instance().flushCurrentUnsafe();
        const char msg[] = "\n=== crash by signal, see log tail ===\n";
        write(STDERR_FILENO, msg, sizeof(msg) - 1);
        signal(sig, SIG_DFL);                  // 恢复默认行为
        raise(sig);                            // 重新抛出，生成 core 供 gdb 分析
    };
    sigaction(SIGSEGV, &sa, nullptr);
    sigaction(SIGABRT, &sa, nullptr);
}
```

```cpp
// main.cc 用法
int main() {
    AsyncLogging::instance().start("app.log");
    install_crash_handler();
    LOG_INFO("service start, pid=%d", getpid());       // 业务线程只拷贝进缓冲
    // ... 崩溃时 flushCurrentUnsafe 尽力带出尾部日志 ...
    AsyncLogging::instance().stop();
}
```

## 4. spdlog 实战

### 4.1 架构分层

| 层 | 职责 | 说明 |
| --- | --- | --- |
| registry | 全局 logger 注册表 | `spdlog::get("name")`、默认 logger |
| logger | 对外接口 info/warn/error | 可挂多个 sink（一次日志多处输出） |
| sinks | 输出目的地 | 文件/滚动文件/控制台/syslog/tcp |
| formatter(pattern) | 格式化 | 时间/级别/线程号/文件名拼装 |
| 异步层 | 线程池 + 有界队列 | `spdlog::async_factory` 创建异步 logger |

### 4.2 基础用法（文件 sink 三兄弟）

```cpp
#include <spdlog/spdlog.h>
#include <spdlog/sinks/basic_file_sink.h>
#include <spdlog/sinks/rotating_file_sink.h>
#include <spdlog/sinks/daily_file_sink.h>

// 1. 普通文件
auto f1 = spdlog::basic_logger_mt("basic", "logs/basic.log");
// 2. 按大小滚动：单文件 5MB，最多保留 3 个（app.log, app.1.log, ...）
auto f2 = spdlog::rotating_logger_mt("rot", "logs/app.log", 5 * 1024 * 1024, 3);
// 3. 按天滚动：每天 0 点切新文件
auto f3 = spdlog::daily_logger_mt("daily", "logs/daily.log", 0, 0);

f2->set_level(spdlog::level::debug);
f2->info("user {} login, cost {}ms", "tao", 12);   // fmt 风格格式化，比流式快
f2->flush();                                        // 主动刷盘
```

### 4.3 异步用法与溢出策略

```cpp
#include <spdlog/async.h>
// 线程池：队列 8192 条 × 1 个后台线程（进程级共享）
spdlog::init_thread_pool(8192, 1);
// 溢出策略：block（默认，队列满则业务线程阻塞——不丢日志）
auto a1 = spdlog::basic_logger_mt<spdlog::async_factory>("ab", "logs/async.log");
// overwrite_oldest：队列满覆盖最旧——业务线程永不阻塞但可能丢日志
auto a2 = spdlog::basic_logger_mt<spdlog::async_factory_nonblocking>("ab2", "logs/async2.log");
```

| 溢出策略 | 行为 | 适用 |
| --- | --- | --- |
| block（默认） | 队列满时业务线程等待 | 计费/审计类，一条不能丢 |
| overwrite_oldest | 丢最旧日志 | 监控打点类，可用性优先 |

### 4.4 pattern 格式符与崩溃找回

| 格式符 | 含义 | 格式符 | 含义 |
| --- | --- | --- | --- |
| %v | 日志正文 | %t | 线程 id |
| %l | 级别缩写（I/W/E） | %P | 进程 id |
| %L | 级别单字母 | %s | 源文件名 |
| %Y-%m-%d | 日期 | %H:%M:%S.%e | 时间（%e 毫秒） |
| %# | 行号 | %% | 百分号字面量 |

```cpp
spdlog::set_pattern("[%Y-%m-%d %H:%M:%S.%e][%t][%l] %v");
spdlog::flush_on(spdlog::level::err);          // err 及以上级别立即 flush（崩溃找回）
spdlog::flush_every(std::chrono::seconds(3));  // 定时兜底 flush
```

性能参考：同步 rotating logger 单线程百万条/秒量级；异步模式多线程下更高（具体受盘和格式影响，量级结论即可）。

## 5. 应用层协议设计

### 5.1 为什么需要应用层协议

TCP 是**字节流，没有消息边界**（粘包/拆包本质，见 `../03-计算机网络编程/02-IO多路复用与Reactor模型.md` 5.3）：N 次 send 可能被对端 1 次 recv 读到。必须由应用层定义"一条消息从哪开始到哪结束"。

### 5.2 业界协议对比

| 协议 | 定界方式 | 编码 | 特点 |
| --- | --- | --- | --- |
| IM 私有协议 | 魔数+长度前缀 | protobuf 二进制 | 紧凑、可校验、易扩展（本篇实现） |
| nginx 内部/自研 RPC | 长度前缀 | 二进制结构体/protobuf | 同上思路 |
| redis RESP | \r\n 行/长度前缀 | 文本 | 人类可读、telnet 可调（`../05-数据库与序列化/02-Redis设计与数据结构.md`） |
| HTTP/1.1 | 头部空行+Content-Length/chunked | 文本 | 调试方便但头冗余 |
| HTTP/2 | 二进制分帧（帧头带 Length） | 二进制+HPACK | 多路复用，详见 `../05-数据库与序列化/03-Protobuf序列化协议.md` |

### 5.3 协议设计要素清单

| 字段 | 作用 | 说明 |
| --- | --- | --- |
| magic 魔数 | 快速识别协议/端口误接 | 如 0xABCD，不符直接断开 |
| version 版本 | 协议演进 | 新旧字段兼容判断 |
| cmd 指令 | 消息类型 | LOGIN/CHAT/HEARTBEAT 路由到不同 handler |
| seq 序号 | 关联请求响应 / 去重重排 | 超时重发时靠 seq 幂等 |
| len 长度 | **定界核心** | 决定读多少字节算一条完整消息 |
| crc 校验 | 完整性 | 校验失败丢弃，防脏数据进业务 |
| body 包体 | 序列化后的业务数据 | protobuf/json |

### 5.4 消息完整性三保障

| 保障 | 手段 | 解决什么 |
| --- | --- | --- |
| 定界 | 长度前缀（4 字节大端） | 粘包/半包：先读 4 字节知道体长，再收满 |
| 校验 | CRC32 覆盖 header+body | 网络字节损坏/串流误判 |
| 顺序与幂等 | seq 号去重、滑窗重排 | 重发导致的重复、UDP/重路由乱序 |

## 6. Protobuf【核心】

### 6.1 安装与 CMake 集成

```bash
sudo apt install protobuf-compiler libprotobuf-dev     # 或源码编译
protoc --version                                       # 编译器版本
protoc --cpp_out=. im.proto                            # 生成 im.pb.h / im.pb.cc
```

```cmake
find_package(Protobuf REQUIRED)
add_executable(im_server im.pb.cc server.cc)
target_link_libraries(im_server protobuf)               # 注意 protoc 与 libprotobuf 版本要配套
```

### 6.2 .proto 语法速查

| 语法 | 说明 | 示例 |
| --- | --- | --- |
| package | 命名空间，防消息名冲突 | `package im;` |
| message | 消息定义（生成 C++ 类） | `message LoginReq {...}` |
| singular | 单数字段（proto3 默认） | `string user = 1;` |
| repeated | 数组字段 | `repeated string tags = 3;` |
| optional | 显式 presence（proto3.15+） | `optional int32 age = 4;`（可判断"没设置"） |
| enum | 枚举，proto3 首值必须 0 | `enum Cmd { LOGIN = 0; }` |
| 嵌套 | message 里定义 message | `message Resp { LoginReq req = 1; }` |
| oneof | 多选一字段，省空间 | `oneof body { LoginReq login = 1; ChatMsg chat = 2; }` |
| 字段编号 | 1~15 编码占 1 字节 tag，16~2047 占 2 字节——**常用字段用小编号** | `string user = 1;` |
| reserved | 保留已删除字段的编号/名字，**防复用** | `reserved 5, 9 to 11;` |

### 6.3 手撕 IM 通信协议

```protobuf
// im.proto
syntax = "proto3";
package im;

enum Cmd { LOGIN = 0; HEARTBEAT = 1; CHAT = 2; }

message LoginReq  { string user = 1; string pass = 2; }
message LoginResp { int32  code = 1; string token = 2; }
message Heartbeat { int64  ts = 1; }
message ChatMsg   { string from = 1; string to = 2; string text = 3; }
```

```cpp
// 封包发送：4 字节大端长度 + protobuf 体（长度前缀定界）
bool send_msg(int fd, const google::protobuf::Message &m) {
    std::string body;
    m.SerializeToString(&body);                       // 序列化
    uint32_t len = (uint32_t)body.size();
    char head[4] = { (char)(len >> 24), (char)(len >> 16),
                     (char)(len >> 8), (char)len };   // 大端
    // 演示直接 write；生产要处理部分写（缓冲/循环）与非阻塞
    return write(fd, head, 4) == 4 &&
           write(fd, body.data(), body.size()) == (ssize_t)body.size();
}

// 接收解析：先收 4 字节头，再收满 body
bool recv_msg(int fd, im::ChatMsg *out) {
    char head[4];
    if (!readn(fd, head, 4)) return false;            // readn：循环 read 收满 n 字节
    uint32_t len = ((uint8_t)head[0] << 24) | ((uint8_t)head[1] << 16) |
                   ((uint8_t)head[2] << 8) | (uint8_t)head[3];
    if (len == 0 || len > kMaxBody) return false;     // 长度校验，防恶意包
    std::string body(len, 0);
    if (!readn(fd, body.data(), len)) return false;
    return out->ParseFromArray(body.data(), (int)len); // 反序列化
}
```

### 6.4 三种序列化方案对比

| 维度 | protobuf | json | xml |
| --- | --- | --- | --- |
| 体积 | 最小（varint+字段号代替字段名） | 大（字段名明文重复） | 最大（标签成对） |
| 速度 | 快（二进制拷贝级） | 慢（文本解析） | 最慢 |
| 可读性 | 差（需 proto 文件+工具解码） | 好（肉眼可读） | 好 |
| 跨语言 | 官方生成十余种语言 | 全平台 | 全平台 |
| 前后兼容 | 好（字段编号机制） | 好（新增字段双方忽略） | 好 |
| 典型场景 | 内部 RPC、IM、存储 | 对外 API、配置 | 遗留系统 |

### 6.5 编码原理【高频】

**varint 变长编码**：小数字少占字节。每字节低 7 位是数据，最高位（MSB）=1 表示"还有后续字节"，多字节按**小端组序**（低组在前）拼接。

**tag 规则**：`tag = field_number << 3 | wire_type`，先写 tag 再写值。

| wire type | 编号 | 含义 | 适用 |
| --- | --- | --- | --- |
| VARINT | 0 | 变长整数 | int32/int64/uint/bool/enum |
| I64 | 1 | 固定 8 字节 | fixed64/sfixed64/double |
| LEN | 2 | 长度前缀字节串 | string/bytes/嵌套 message/repeated |
| SGROUP/EGROUP | 3/4 | 分组（已废弃） | 老版本 |
| I32 | 5 | 固定 4 字节 | fixed32/sfixed32/float |

**手工解码示例**：`message { int32 id = 1; string name = 2; }`，设 id=150、name="tao"，编码为 `08 96 01 12 03 74 61 6f`：

| 字节 | 解码 |
| --- | --- |
| 08 | tag = (1<<3)\|0 = 0x08 → 字段 1、varint |
| 96 | 0x96 = 1001 0110：MSB=1 继续，低 7 位 = 0010110 |
| 01 | 0x01 = 0000 0001：MSB=0 结束，低 7 位 = 0000001 |
| 组合 | (0000001 << 7) \| 0010110 = 128+22 = **150** |
| 12 | tag = (2<<3)\|2 = 0x12 → 字段 2、长度前缀 |
| 03 | 长度 = 3 字节 |
| 74 61 6f | ASCII "tao" |

**负数与 zigzag**：int32 的 -1 会被符号扩展成 64 位再 varint，**固定占 10 字节**。用 `sint32/sint64` 走 zigzag 映射：`编码 = (n << 1) ^ (n >> 31)`（算术右移），-1→1、1→2、-2→3、2→4，小绝对值负数也只占 1~2 字节。

### 6.6 常用 API 表

| API | 说明 |
| --- | --- |
| `set_xxx()` / `set_xxx(v)` | 设置标量/string 字段（string 传 const char*/std::string） |
| `mutable_xxx()` | 取 string/bytes/message 字段的可写指针（首次调用构造） |
| `add_xxx()` | repeated 字段追加元素，返回指针/引用 |
| `xxx_size()` | repeated 字段长度 |
| `has_xxx()` | 是否设置（proto3 仅 optional/oneof/子消息字段有） |
| `SerializeToString(std::string*)` | 序列化（覆盖式） |
| `ParseFromArray(const void*, int)` | 从内存反序列化 |
| `ByteSizeLong()` | 序列化后字节数（封长度前缀前要调） |
| `DebugString()` | 人类可读输出，调试神器 |

## 7. 快速参考卡片

| 主题 | 关键点 | 一句话 |
| --- | --- | --- |
| 日志三瓶颈 | IO 阻塞 / 格式化 / 锁竞争 | 全都发生在业务线程就是同步日志的病根 |
| 双缓冲 | 前台写 A，后台写 B，满/超时交换 | 锁只保护指针交换，不保护写盘 |
| 触发交接 | 写满 4MB 或 3 秒超时 | 低流量也要及时落盘 |
| 崩溃找回 | 信号处理器里 write 当前缓冲 | 只能用 async-signal-safe 函数（write 行，printf/malloc 不行） |
| spdlog 异步 | init_thread_pool(8192,1) + async_factory | 溢出策略 block / overwrite_oldest |
| spdlog 找回 | flush_on(err) + flush_every(3s) | 丢失窗口压到秒级 |
| 协议七要素 | magic/version/cmd/seq/len/crc/body | len 是定界核心，seq 管幂等重排 |
| 长度前缀 | 4 字节大端 + body | 粘包半包的标准解 |
| varint | 7bit 分组 + MSB 续位，小端组序 | 150 → 96 01 |
| tag | field<<3 \| wire_type | 08 = 字段1 varint |
| 负数 | int32 负数恒 10 字节；sint32 zigzag | (n<<1)^(n>>31) |
| 字段编号 | 1~15 一字节 tag；删除的编号用 reserved | 编号即 ABI，不能复用 |

## 8. 常见问题与坑

| 坑 | 现象 | 规避 |
| --- | --- | --- |
| 后台线程未 flush 丢尾部日志 | 崩溃后最后几条日志缺失 | 信号处理器 flush 当前缓冲；spdlog 用 flush_on(err)+flush_every |
| 双缓冲交换点死锁 | 交接时持锁又去 write/notify 内部再拿同一把锁 | 写盘一律移出临界区；cv_ 与 mtx_ 配对使用，swap 完再 notify |
| 字段编号复用 | 老数据里编号 5 是 int，新 proto 改成 string → 解析错乱/静默丢数据 | 删除字段必须 `reserved` 编号与名字 |
| 未知字段被丢 | 旧程序解析新协议数据后重新序列化，新字段丢失 | protobuf 默认丢弃未知字段；需要保留用 proto3 的 preserve unknown（或保持读写端同步升级） |
| repeated 海量元素 | 一个消息里 append 百万元素 → 单条消息几百 MB，内存暴涨 | 消息分页/流式分帧（一条逻辑消息拆多帧） |
| protoc 与 libprotobuf 版本不匹配 | 生成的 .pb.cc 链接老 lib → 符号缺失或运行时 ABI 断言崩溃 | 编译器与库版本严格配套；CI 里锁定版本 |
| varint 手算错误 | 把多字节组序当大端 | varint 的组序是**小端**（低 7 位组在前） |
| 同步双向写互等（日志走网络时） | 两个服务互发日志，都只写不读 → TCP 缓冲满互相阻塞 | 网络 sink 用异步/独立连接+读端持续消费 |
| 日志级别线上全开 | DEBUG 全开导致日志量翻百倍，盘被打满 | 级别可热更（配置中心/信号），按需动态调级 |
| 时间戳在信号处理器里格式化 | localtime/snprintf 非 async-signal-safe | 崩溃路径只 write 原始缓冲，不做格式化 |
| 单文件日志无限增长 | 磁盘写满服务全挂 | rotating/daily 滚动 + 磁盘水位告警 |

---

上一篇：《02-Kafka消息队列原理.md》　｜　下一篇：《04-性能分析与调优.md》　｜　模块索引：《../README.md》
