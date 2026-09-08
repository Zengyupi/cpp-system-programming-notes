# 游戏服务器架构 Skynet

> 本节目标：讲解云风开源的轻量级游戏服务器框架 Skynet 的核心设计与工程实践，学完后能够理解 Actor 模型与消息驱动架构、掌握 Skynet 服务编写与 Lua/C 交互、熟悉网络层封装与重要组件、对比 TrinityCore 等大型 MMO 后端设计、掌握万人在线游戏的分服/网关/场景服务架构要点。对应岗位方向：游戏服务器开发（网易、腾讯、米哈游、莉莉丝等）。机器人与自动驾驶的分布式中间件见《02-机器人与自动驾驶.md》。

## 本章速览

- [1. Skynet 定位与设计哲学](#1-skynet-定位与设计哲学)
- [2. Actor 模型核心概念](#2-actor-模型核心概念)
  - [2.1 Actor 与消息驱动](#21-actor-与消息驱动)
  - [2.2 CSP vs Actor 并发模型对比](#22-csp-vs-actor-并发模型对比)
- [3. Skynet 整体架构](#3-skynet-整体架构)
  - [3.1 核心模块组成](#31-核心模块组成)
  - [3.2 启动流程](#32-启动流程)
- [4. 消息队列与调度器](#4-消息队列与调度器)
  - [4.1 无锁消息队列实现](#41-无锁消息队列实现)
  - [4.2 调度器工作机制](#42-调度器工作机制)
- [5. 网络层封装](#5-网络层封装)
  - [5.1 skynet.socket（reactor 封装）](#51-skynetsocketreactor-封装)
  - [5.2 socketchannel 客户端封装](#52-socketchannel-客户端封装)
- [6. Lua/C 接口编程](#6-luac-接口编程)
  - [6.1 Lua 服务编写](#61-lua-服务编写)
  - [6.2 C 服务编写](#62-c-服务编写)
  - [6.3 Lua-C 交互机制](#63-lua-c-交互机制)
- [7. 重要组件与 API](#7-重要组件与-api)
  - [7.1 skynet.send / skynet.call / skynet.response](#71-skynetsend--skynetcall--skynetresponse)
  - [7.2 multicastd 广播](#72-multicastd-广播)
  - [7.3 sharedatad / datasheet 数据共享](#73-sharedatad--datasheet-数据共享)
- [8. 与 TrinityCore 对比](#8-与-trinitycore-对比)
  - [8.1 网络模块对比](#81-网络模块对比)
  - [8.2 线程模型对比](#82-线程模型对比)
  - [8.3 技能/AI/副本模块设计对比](#83-技能ai副本模块设计对比)
- [9. 万人在线游戏架构要点](#9-万人在线游戏架构要点)
  - [9.1 分线/分服策略](#91-分线分服策略)
  - [9.2 网关服务设计](#92-网关服务设计)
  - [9.3 场景服务与 AOI](#93-场景服务与-aoi)
  - [9.4 数据库连接池与持久化](#94-数据库连接池与持久化)
- [10. 快速参考卡片](#10-快速参考卡片)
- [11. 常见问题与坑](#11-常见问题与坑)

---

## 1. Skynet 定位与设计哲学

Skynet 是云风（吴云洋）开源的轻量级游戏服务器框架，采用 **C 核心 + Lua 服务** 的双层架构，基于 Actor 模型实现高并发消息驱动。

| 特性 | 说明 |
| --- | --- |
| **语言** | C 编写核心运行时，Lua 编写业务逻辑 |
| **并发模型** | Actor 模型，每个服务是独立 Actor |
| **线程模型** | 多工作线程 + 全局消息队列调度 |
| **网络** | 内置 epoll/kqueue/IOCP reactor 封装 |
| **定位** | 轻量级、可嵌入、适合手游/中小型 MMO |
| **开源协议** | MIT |
| **仓库** | github.com/cloudwu/skynet |

设计哲学：
- **简单优先**：核心代码精简（约 2 万行 C），易于理解和定制
- **消息驱动**：一切皆消息，服务间通过消息通信，无共享状态
- **热更新友好**：Lua 服务支持运行时替换逻辑
- **跨平台**：Linux 为主，支持 macOS/Windows（需适配）

---

## 2. Actor 模型核心概念

### 2.1 Actor 与消息驱动

Actor 模型是一种并发计算模型，核心三要素：

1. **处理（Processing）**：每个 Actor 串行处理自己的消息队列
2. **存储（Storage）**：Actor 拥有私有状态，外部不可直接访问
3. **通信（Communication）**：Actor 之间仅通过异步消息传递

```text
┌─────────────┐    消息     ┌─────────────┐    消息     ┌─────────────┐
│  Actor A    │ ──────────> │  Actor B    │ ──────────> │  Actor C    │
│  (私有状态)  │             │  (私有状态)  │             │  (私有状态)  │
│  msg_queue  │             │  msg_queue  │             │  msg_queue  │
└─────────────┘             └─────────────┘             └─────────────┘
       ^                          ^                          ^
       │                          │                          │
   调度器从全局队列取出消息，分发给对应 Actor 的工作线程处理
```

Skynet 中每个服务（service）就是一个 Actor：
- 拥有独立的 Lua 虚拟机（或 C 上下文）
- 拥有私有的消息队列
- 一次只处理一条消息，天然无锁
- 通过 `skynet.send`（异步）/ `skynet.call`（同步等待响应）通信

### 2.2 CSP vs Actor 并发模型对比

| 维度 | CSP（Go 通道） | Actor（Skynet/Erlang） |
| --- | --- | --- |
| **通信焦点** | 通道（Channel）是一等公民 | Actor（进程/服务）是一等公民 |
| **消息方向** | 发送者知道通道，不关心接收者 | 发送者知道接收者（PID/handle） |
| **状态共享** | 通过通道传递数据，无共享 | Actor 私有状态，消息传递 |
| **同步原语** | channel + select | mailbox + 模式匹配 |
| **容错** | 需自行实现 supervisor | 内置监督树（Erlang）/需自建（Skynet） |
| **代表语言** | Go、Rust（crossbeam） | Erlang、Akka、Skynet |
| **适用场景** | 流水线、任务分发 | 游戏实体、独立服务、分布式系统 |

```cpp
// CSP 风格（Go 伪代码）：关注通道
ch := make(chan int)
go func() { ch <- 42 }()
val := <-ch

// Actor 风格（Skynet Lua）：关注服务实体
local target = skynet.queryservice("mydb")
skynet.send(target, "lua", "set", "key", "value")
```

---

## 3. Skynet 整体架构

### 3.1 核心模块组成

```text
┌─────────────────────────────────────────────────────┐
│                   Lua 服务层（业务逻辑）               │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐       │
│  │ gate   │ │ agent  │ │ scene  │ │ dbmgr  │  ...   │
│  └────────┘ └────────┘ └────────┘ └────────┘       │
├─────────────────────────────────────────────────────┤
│                   C 核心层（运行时）                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │
│  │ skynet_env│ │ 消息队列  │ │ 调度器    │ │ 定时器  │ │
│  └──────────┘ └──────────┘ └──────────┘ └────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │ 网络层    │ │ Lua VM   │ │ 服务管理  │            │
│  │ (socket) │ │ 绑定     │ │ (harbor) │            │
│  └──────────┘ └──────────┘ └──────────┘            │
├─────────────────────────────────────────────────────┤
│                   操作系统（Linux epoll）              │
└─────────────────────────────────────────────────────┘
```

| 模块 | 职责 |
| --- | --- |
| **skynet_env** | 全局环境变量、配置读取、服务注册表 |
| **消息队列** | 全局队列 + 每服务私有队列，无锁实现 |
| **调度器** | 工作线程从全局队列取消息，分发到对应服务 |
| **定时器** | 基于时间轮的定时器，支持 skynet.timeout |
| **网络层** | socket 封装，reactor 模式，epoll 驱动 |
| **服务管理** | 服务启动/销毁/查询，harbor 跨节点通信 |
| **Lua VM** | 每个 Lua 服务独立 VM，隔离性好 |

### 3.2 启动流程

```text
1. 读取配置文件（config），解析 thread/harbor/logger 等参数
2. 初始化 skynet_env，注册内置 C 服务（snlua、logger、gate 等）
3. 启动 logger 服务
4. 启动 bootstrap 服务（通常是 snlua 加载 bootstrap.lua）
5. bootstrap.lua 中启动业务主服务（如 main.lua）
6. 主服务启动 gate、agentmgr、scene 等业务服务
7. 工作线程进入调度循环，处理消息
```

配置文件示例：

```text
thread = 8          -- 工作线程数，通常 = CPU 核数
harbor = 0          -- 0=单节点模式，1=多节点（需 harbor 服务）
logger = nil        -- logger 服务地址，nil 用默认
logpath = "."       -- 日志目录
bootstrap = "snlua bootstrap"   -- 启动服务
start = "main"      -- bootstrap 后启动的 Lua 服务名
```

---

## 4. 消息队列与调度器

### 4.1 无锁消息队列实现

Skynet 的消息队列采用**全局队列 + 每服务私有队列**的两级结构：

```text
全局队列（global_queue）：存放有消息待处理的服务队列指针
     │
     ▼
┌──────────────────────────────────────────────┐
│ 服务A队列 → 服务C队列 → 服务B队列 → ...       │
└──────────────────────────────────────────────┘
     │              │              │
     ▼              ▼              ▼
  msg1,msg2      msg5           msg3,msg4
（每服务私有队列，FIFO）
```

关键设计：
- **全局队列**：无锁队列（lock-free queue），存放"有消息的服务队列"
- **服务私有队列**：每服务一个，自旋锁保护（因为竞争少）
- **消息结构**：`struct skynet_message { uint32_t source; int session; void *data; size_t sz; }`

```c
// 消息入队：先放入服务私有队列，若队列之前为空则挂入全局队列
void skynet_mq_push(struct message_queue *q, struct skynet_message *message) {
    SPIN_LOCK(q)
    // 加入私有队列尾部
    q->queue[q->tail] = *message;
    q->tail = (q->tail + 1) % q->cap;
    // 若队列之前为空，需要挂入全局队列
    if (q->head == ...) {
        skynet_globalmq_push(q);
    }
    SPIN_UNLOCK(q)
}
```

### 4.2 调度器工作机制

```text
工作线程循环：
  1. 从全局队列取出一个服务队列 q
  2. 从 q 中取出一条消息 msg
  3. 若 q 中还有消息，将 q 重新挂回全局队列尾部
  4. 调用 q 对应服务的回调函数处理 msg
  5. 回到步骤 1
```

调度特点：
- **工作线程数** = 配置的 `thread`，通常等于 CPU 核数
- **无服务绑定**：服务不绑定特定线程，任意工作线程都可处理
- **公平性**：全局队列 FIFO，每个服务每次只处理一条消息，避免饥饿
- **阻塞处理**：`skynet.call` 会挂起当前 Lua 协程，等待响应消息到达后恢复

---

## 5. 网络层封装

### 5.1 skynet.socket（reactor 封装）

Skynet 网络层基于 epoll（Linux）/kqueue（BSD）/IOCP（Windows）实现 reactor 模式，对 Lua 暴露简洁 API：

```lua
local socket = require "skynet.socket"

-- 监听端口
local listen_fd = socket.listen("0.0.0.0", 8888)
socket.start(listen_fd, function(fd, addr)
    -- 新连接回调
    skynet.error("new connection from", addr)
    socket.start(fd)  -- 开始接收数据
    -- 读取消息循环
    while true do
        local data = socket.read(fd)  -- 阻塞读（协程挂起）
        if not data then break end
        -- 处理 data
        socket.write(fd, "response: " .. data)
    end
    socket.close(fd)
end)
```

| API | 说明 |
| --- | --- |
| `socket.listen(addr, port)` | 监听端口，返回 listen fd |
| `socket.start(fd, accept_cb)` | 启动监听/连接，accept_cb 处理新连接 |
| `socket.read(fd, sz)` | 读取 sz 字节，不指定则读一行 |
| `socket.write(fd, data)` | 发送数据 |
| `socket.close(fd)` | 关闭连接 |
| `socket.abandon(fd)` | 将 fd 转交给其他服务 |

内部实现要点：
- 每个 socket 连接关联一个 Lua 协程，`read` 时挂起，数据到达时唤醒
- 底层用 epoll LT（水平触发）模式，缓冲区管理在 C 层
- 支持 `socket.abandon` 将连接在服务间转移（网关 → agent）

### 5.2 socketchannel 客户端封装

`socketchannel` 是对客户端连接的高级封装，支持连接池、自动重连、请求-响应匹配：

```lua
local socketchannel = require "skynet.socketchannel"

local channel = socketchannel.channel {
    host = "127.0.0.1",
    port = 6379,
    -- 响应解析：从流中切出一条完整响应
    response = function(sock)
        local line = sock:readline("\r\n")
        return line
    end,
}

-- 连接并发送请求，自动等待响应
local resp = channel:request("PING\r\n")
print(resp)  -- +PONG
```

适用场景：连接 Redis、MySQL、内部 RPC 服务等需要请求-响应模式的客户端。

---

## 6. Lua/C 接口编程

### 6.1 Lua 服务编写

Lua 服务是 Skynet 最常用的服务类型，每个服务运行在独立 Lua VM 中：

```lua
-- myservice.lua
local skynet = require "skynet"

local CMD = {}  -- 消息处理表

function CMD.foobar(...)
    skynet.error("received foobar", ...)
    return "result"
end

-- 服务入口
skynet.start(function()
    -- 注册消息分发：类型为 "lua" 的消息按 CMD 表分发
    skynet.dispatch("lua", function(session, source, cmd, ...)
        local f = CMD[cmd]
        if f then
            skynet.ret(skynet.pack(f(...)))
        else
            skynet.error("unknown cmd:", cmd)
        end
    end)
    skynet.register("myservice")  -- 注册名字，供其他服务查询
end)
```

调用方：

```lua
local skynet = require "skynet"

skynet.start(function()
    local addr = skynet.queryservice("myservice")
    -- 异步发送，不等待返回
    skynet.send(addr, "lua", "foobar", "hello")
    -- 同步调用，等待返回值
    local ret = skynet.call(addr, "lua", "foobar", "world")
    print(ret)  -- result
end)
```

### 6.2 C 服务编写

C 服务用于性能敏感的核心模块，需实现 `struct skynet_module` 接口：

```c
// myservice.c
#include "skynet.h"
#include "skynet_server.h"
#include <stdio.h>

struct myservice {
    int counter;
};

static int _init(struct myservice *inst, struct skynet_context *ctx, const char *parm) {
    inst->counter = 0;
    return 0;
}

static void _release(struct myservice *inst) {
    // 释放资源
}

static int _callback(struct skynet_context *ctx, void *ud, int type, int session,
                     uint32_t source, const void *msg, size_t sz) {
    struct myservice *inst = ud;
    inst->counter++;
    // 处理消息
    return 0;
}

struct skynet_module * myservice_create(void) {
    static struct skynet_module m = {
        .name = "myservice",
        .init = (void *)_init,
        .release = (void *)_release,
        .callback = _callback,
    };
    return &m;
}
```

### 6.3 Lua-C 交互机制

Lua 服务调用 C 模块通过 Lua C API 绑定：

```c
// C 侧：导出函数到 Lua
static int l_myfunc(lua_State *L) {
    int a = luaL_checkinteger(L, 1);
    int b = luaL_checkinteger(L, 2);
    lua_pushinteger(L, a + b);
    return 1;
}

int luaopen_mylib(lua_State *L) {
    luaL_Reg reg[] = {
        {"myfunc", l_myfunc},
        {NULL, NULL}
    };
    luaL_newlib(L, reg);
    return 1;
}
```

```lua
-- Lua 侧：加载 C 模块
local mylib = require "mylib"
local sum = mylib.myfunc(1, 2)  -- 3
```

交互原则：
- **热路径用 C**：数据包解析、物理计算、AOI 等性能瓶颈用 C 实现
- **业务逻辑用 Lua**：玩法、任务、商城等迭代频繁的逻辑用 Lua
- **数据传递**：通过 Lua stack 传参，大对象用 lightuserdata + 引用计数

---

## 7. 重要组件与 API

### 7.1 skynet.send / skynet.call / skynet.response

| API | 模式 | 说明 |
| --- | --- | --- |
| `skynet.send(addr, type, ...)` | 异步 | 发送消息，不等待返回，立即返回 |
| `skynet.call(addr, type, ...)` | 同步 | 发送消息并挂起协程，等待 `skynet.ret` 返回 |
| `skynet.response()` | 延迟响应 | 获取响应函数，可在异步回调中返回结果 |

```lua
-- skynet.response 延迟响应示例
skynet.dispatch("lua", function(session, source, cmd, ...)
    if cmd == "query" then
        local response = skynet.response()  -- 捕获响应函数
        -- 异步查询数据库
        skynet.send(dbmgr, "lua", "query", function(result)
            response(true, result)  -- 异步返回结果
        end)
        -- 注意：这里不能 skynet.ret，因为要异步返回
        return skynet.DONOTRET
    end
end)
```

### 7.2 multicastd 广播

`multicastd` 是 Skynet 内置的组播服务，用于一对多消息分发（如场景内玩家同步）：

```lua
local multicastd = require "multicastd"

-- 创建一个频道
local channel = multicastd.new()
-- 订阅者加入频道
channel:subscribe(subscriber_addr)
-- 发布消息到频道所有订阅者
channel:publish("hello", "world")
```

适用场景：
- 场景服务向同屏所有玩家广播位置/动作
- 公会/队伍聊天
- 世界公告

### 7.3 sharedatad / datasheet 数据共享

`sharedatad` 实现多 Lua VM 间的**只读共享数据**，避免每服务一份配置表的内存浪费：

```lua
local sharedata = require "sharedata"

-- 主服务加载配置表并发布
local config = require "config.item"  -- 大表，几十 MB
sharedata.new("item_config", config)

-- 其他服务引用（不复制数据，共享内存）
local item_config = sharedata.query("item_config")
local item = item_config[1001]  -- 只读访问
```

原理：
- 数据存储在 C 层的共享结构中
- 每个 Lua VM 通过元表（metatable）代理访问
- 写入需要 `sharedata.update`，原子替换
- 适合配置表、静态数据等读多写少场景

`datasheet` 是更轻量的版本，支持嵌套结构和增量更新。

---

## 8. 与 TrinityCore 对比

TrinityCore 是魔兽世界（WoW）的开源服务端，C++ 编写，是大型 MMO 后端的代表。

### 8.1 网络模块对比

| 维度 | Skynet | TrinityCore |
| --- | --- | --- |
| **网络库** | 自研 socket（epoll reactor） | boost.asio（proactor 封装） |
| **IO 模型** | Reactor（epoll LT） | Proactor（IOCP/epoll 封装） |
| **连接管理** | gate 服务统一管理，abandon 转移 | WorldSocket 类，每连接一个对象 |
| **数据包** | 自定义二进制协议 | WoW 协议（加密 + 压缩） |
| **线程模型** | 多工作线程 + Actor 消息 | 网络线程 + 世界线程分离 |

```cpp
// TrinityCore WorldSocket 继承自 boost.asio
class WorldSocket : public Socket<WorldSocket> {
public:
    void Start() override;
    bool Update() override;
protected:
    void ReadHandler() override;
    // 处理 Opcodes（消息号）
    void Handle_NULL(WorldPacket& recvPacket);
    void Handle_CMSG_AUTH_SESSION(WorldPacket& recvPacket);
};
```

### 8.2 线程模型对比

```text
Skynet 线程模型：
┌─────────────────────────────────────────┐
│  工作线程1  工作线程2  ...  工作线程N    │
│  (统一调度消息，无服务绑定)              │
└─────────────────────────────────────────┘

TrinityCore 线程模型：
┌──────────┐  ┌──────────┐  ┌──────────┐
│ 网络线程  │  │ 世界线程  │  │ DB线程   │
│ (accept/ │  │ (更新AI/ │  │ (异步查询)│
│  recv)   │  │  移动/   │  │          │
│          │  │  战斗)   │  │          │
└──────────┘  └──────────┘  └──────────┘
     │              │              │
     └──────────────┼──────────────┘
                消息队列/回调
```

| 维度 | Skynet | TrinityCore |
| --- | --- | --- |
| **线程划分** | 统一工作线程池 | 按功能划分（网络/世界/DB） |
| **世界更新** | 场景服务内定时器驱动 | 世界线程固定 tick（如 100ms） |
| **并行粒度** | 服务级（Actor） | 地图/副本级（Map 多线程） |
| **锁使用** | 几乎无锁（Actor 隔离） | 大量互斥锁保护共享对象 |

### 8.3 技能/AI/副本模块设计对比

| 模块 | Skynet 典型设计 | TrinityCore 设计 |
| --- | --- | --- |
| **技能系统** | Lua 表配置 + 效果函数，场景服务执行 | Spell 类体系，Aura/Buff 效果链 |
| **AI 系统** | 行为树/状态机 Lua 实现，定时器驱动 | CreatureAI 基类，事件驱动，脚本化（SmartAI） |
| **副本系统** | 每副本一个场景服务 Actor | Map 实例，多线程更新，InstancedMap |
| **怪物刷新** | 场景服务管理 spawn 表 | SpawnData + Creature 对象池 |
| **战斗计算** | Lua 公式 + C 加速模块 | Unit 类属性系统，伤害计算链 |

TrinityCore 的 `CreatureAI` 示例：

```cpp
class npc_example : public CreatureAI {
public:
    npc_example(Creature* c) : CreatureAI(c) {}

    void EnterCombat(Unit* who) override {
        Talk(0);  // 喊话
        me->CastSpell(who, SPELL_FIREBALL);
    }

    void UpdateAI(uint32 diff) override {
        if (!UpdateVictim()) return;
        // 技能冷却管理
        events.Update(diff);
        if (uint32 spellId = events.ExecuteEvent()) {
            DoCastVictim(spellId);
        }
        DoMeleeAttackIfReady();
    }
};
```

---

## 9. 万人在线游戏架构要点

### 9.1 分线/分服策略

```text
┌─────────────────────────────────────────────────────┐
│                    登录/中心服                         │
│         (账号验证、服列表、跨服匹配、充值)              │
└──────────────────────┬──────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
   ┌─────────┐   ┌─────────┐   ┌─────────┐
   │ 游戏服1  │   │ 游戏服2  │   │ 游戏服N  │
   │ (线1)   │   │ (线1)   │   │ (线1)   │
   │ (线2)   │   │ (线2)   │   │         │
   └─────────┘   └─────────┘   └─────────┘
```

| 策略 | 说明 | 适用场景 |
| --- | --- | --- |
| **分服（Shard）** | 数据完全隔离，玩家不可跨服 | 传统 MMO，数据量大 |
| **分线（Channel）** | 同一服内多条线，玩家可切换，共享数据 | 手游，缓解单场景压力 |
| **跨服** | 中心服协调，特定玩法跨服匹配 | 竞技场、世界 BOSS |

### 9.2 网关服务设计

网关（gate）是客户端连接的入口，负责：
- 接受 TCP/WebSocket 连接
- 协议解析（拆包/粘包）
- 连接认证后 `abandon` 给 agent 服务
- 心跳检测与超时断开
- 流量统计与限流

```lua
-- gate 服务核心逻辑
local socket = require "skynet.socket"

skynet.start(function()
    local agent_pool = {}  -- agent 服务池
    local listen_fd = socket.listen("0.0.0.0", 9001)
    socket.start(listen_fd, function(fd, addr)
        -- 分配一个 agent
        local agent = table.remove(agent_pool) or skynet.newservice("agent")
        skynet.call(agent, "lua", "start", fd, addr)
        -- 将连接转交给 agent
        socket.abandon(fd)
        skynet.send(agent, "lua", "socket_start", fd)
    end)
end)
```

### 9.3 场景服务与 AOI

场景服务（scene）管理游戏世界中的实体，核心是 AOI（Area of Interest，兴趣区域）算法：

```text
        玩家A的视野范围
     ┌──────────────────┐
     │  玩家A ●         │
     │        ↕ 同步    │
     │  怪物B ◇    NPC C│
     │                  │
     └──────────────────┘
  玩家D ●（在视野外，不同步）
```

AOI 算法选择：
- **九宫格**：简单，将地图划分为格子，玩家只同步周围 9 格
- **十字链表**：动态维护，适合大地图
- **动态 AOI**：基于距离，视野半径可配置

Skynet 中每个场景是一个独立 Actor，场景内实体串行更新，无锁。

### 9.4 数据库连接池与持久化

```text
┌──────────┐    写请求    ┌──────────┐    SQL     ┌──────────┐
│ 业务服务  │ ──────────> │  dbmgr   │ ─────────> │  MySQL   │
│ (agent/  │             │ (连接池)  │            │  /Redis  │
│  scene)  │ <────────── │           │ <───────── │          │
└──────────┘   异步回调   └──────────┘   结果集   └──────────┘
```

设计要点：
- **dbmgr 服务**：管理 N 个数据库连接，轮询分发
- **异步写入**：业务服务 `skynet.send` 写请求，不阻塞
- **定时落盘**：玩家数据定时（如 5 分钟）批量写入
- **缓存层**：Redis 缓存热点数据（玩家基本信息、排行榜）
- **防丢失**：下线时强制落盘，服务崩溃时从日志恢复

---

## 10. 快速参考卡片

```text
Skynet API 速查：
  skynet.start(fn)            服务入口，fn 中注册 dispatch
  skynet.dispatch(type, cb)   注册消息类型处理回调
  skynet.send(addr,type,...)  异步发消息，返回 true/false
  skynet.call(addr,type,...)  同步调用，挂起协程等返回
  skynet.ret(...)             返回 call 的结果
  skynet.response()           延迟响应，返回 response 函数
  skynet.newservice(name,...) 启动新 Lua 服务
  skynet.queryservice(name)   按名字查询服务地址（阻塞等待启动）
  skynet.register(name)       注册服务名字
  skynet.timeout(ti, fn)      定时器，ti 为 1/100 秒
  skynet.fork(fn, ...)        启动新协程
  socket.listen/start/read/write/close/abandon  网络 API

Actor 消息流程：
  发送方 skynet.send → 消息入目标服务私有队列
  → 若队列空则挂入全局队列 → 工作线程取出 → 调用 dispatch 回调
  → skynet.call 额外：挂起协程，session 匹配响应后恢复

与 TrinityCore 对照表：
  网络层：Skynet自研reactor ↔ TrinityCore boost.asio proactor
  并发：Actor消息驱动无锁 ↔ 功能线程+大量互斥锁
  业务语言：Lua(热更友好) ↔ C++(性能优先)
  世界更新：场景服务定时器 ↔ 世界线程固定tick
  适用：手游/中小型MMO ↔ 大型MMO(魔兽世界级)
```

## 11. 常见问题与坑

1. **`skynet.call` 死锁**：A call B，B call A，形成循环等待。解决：避免跨服务循环调用，用 `skynet.send` + 回调。
2. **消息队列溢出**：某服务处理不过来，消息堆积内存暴涨。解决：监控队列长度，过载时丢弃非关键消息或限流。
3. **Lua VM 内存隔离导致共享数据浪费**：每服务一份配置表。解决：用 `sharedatad`/`datasheet` 共享只读数据。
4. **socket.abandon 后忘记在新服务 start**：连接收不到数据。解决：abandon 后必须在目标服务调用 `socket.start(fd)`。
5. **定时器精度问题**：`skynet.timeout` 最小精度 1/100 秒，且可能因调度延迟。解决：高精度需求用 C 服务或系统定时器。
6. **大消息拷贝开销**：消息 data 通过 `skynet.pack` 序列化拷贝。解决：大对象用共享内存 + 传指针（lightuserdata）。
7. **多节点 harbor 配置复杂**：跨节点消息需 harbor 服务，延迟高。解决：尽量单节点，跨节点用独立 RPC 服务。
8. **Lua 热更新替换函数不生效**：已运行的协程持有旧函数引用。解决：热更后需要重新触发或用全局表间接调用。
9. **工作线程数设置不当**：过多导致上下文切换，过少 CPU 利用不足。解决：`thread` = CPU 核数，压测微调。
10. **数据库同步调用阻塞服务**：在 Lua 服务中直接用同步 MySQL 库会阻塞整个 Actor。解决：用 `skynet.db.mysql`（异步协程版）或独立 dbmgr 服务。

---

上一篇：《06-音视频开发与编解码.md》
下一篇：《08-WebRTC与WHIP_WHEP协议.md》
