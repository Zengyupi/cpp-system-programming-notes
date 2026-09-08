# JSON 数据格式与解析

> 本节目标：系统讲解 JSON（JavaScript Object Notation）的语法规范、数据模型、解析原理、C++ 主流解析库的选型与用法、JSON 与关系型数据库的结合、JSON Schema 校验、以及 JSON 在序列化场景中的优缺点与常见坑。学完后能够根据性能和易用性需求选择合适的 JSON 库，写出健壮的 JSON 解析代码，并理解 JSON 与 Protobuf/XML 的选型差异。与《03-Protobuf序列化协议.md》《05-XML数据格式与解析.md》构成序列化三剑客，与《01-MySQL数据库精要.md》的 JSON 类型章节呼应。

## 本章速览

- [1. JSON 概述与设计哲学](#1-json-概述与设计哲学)
  - [1.1 什么是 JSON](#11-什么是-json)
  - [1.2 JSON 的典型应用场景](#12-json-的典型应用场景)
- [2. JSON 语法规范](#2-json-语法规范)
  - [2.1 完整示例](#21-完整示例)
  - [2.2 语法规则速查](#22-语法规则速查)
  - [2.3 字符串转义规则](#23-字符串转义规则)
- [3. JSON 数据模型与类型系统](#3-json-数据模型与类型系统)
  - [3.1 六种数据类型详解](#31-六种数据类型详解)
  - [3.2 number 类型的精度陷阱](#32-number-类型的精度陷阱)
  - [3.3 null 的语义](#33-null-的语义)
- [4. JSON 解析原理](#4-json-解析原理)
  - [4.1 解析器的两种模型：DOM vs SAX](#41-解析器的两种模型dom-vs-sax)
  - [4.2 解析器的性能优化技术](#42-解析器的性能优化技术)
  - [4.3 解析性能对比（参考量级）](#43-解析性能对比参考量级)
- [5. C++ JSON 解析库详解](#5-c-json-解析库详解)
  - [5.1 nlohmann/json（推荐首选）](#51-nlohmannjson推荐首选)
  - [5.2 rapidjson（高性能场景）](#52-rapidjson高性能场景)
  - [5.3 simdjson（极致性能）](#53-simdjson极致性能)
  - [5.4 库选型决策](#54-库选型决策)
- [6. JSON 与数据库](#6-json-与数据库)
  - [6.1 MySQL JSON 类型](#61-mysql-json-类型)
  - [6.2 PostgreSQL JSONB](#62-postgresql-jsonb)
- [7. JSON Schema 与校验](#7-json-schema-与校验)
- [8. JSON 与其他序列化格式对比](#8-json-与其他序列化格式对比)
- [9. 常见坑与最佳实践](#9-常见坑与最佳实践)
  - [9.1 常见坑汇总](#91-常见坑汇总)
  - [9.2 最佳实践](#92-最佳实践)
- [10. 快速参考卡片](#10-快速参考卡片)

---

## 1. JSON 概述与设计哲学

### 1.1 什么是 JSON

JSON（JavaScript Object Notation）是一种**轻量级、文本化、自描述**的数据交换格式。它脱胎于 JavaScript 的对象字面量语法，但早已成为跨语言的事实标准（RFC 8259 / ECMA-404）。

JSON 的核心设计哲学：
- **文本可读**：人眼可直接阅读和调试，不需要专门工具
- **极简语法**：只有 6 种数据类型，语法规则一页纸就能讲完
- **自描述**：键名自带语义，不需要额外的 schema 就能理解数据结构
- **跨语言通用**：几乎所有编程语言都有成熟的 JSON 解析库

### 1.2 JSON 的典型应用场景

| 场景 | 说明 |
|---|---|
| Web API 数据交换 | RESTful API 的事实标准格式，前后端通信 |
| 配置文件 | 许多工具（VS Code、npm、package.json）用 JSON 做配置 |
| 日志格式 | 结构化日志（JSON Lines）便于机器解析和检索 |
| 数据库存储 | MySQL 5.7+、PostgreSQL 原生支持 JSON/JSONB 类型 |
| NoSQL 文档 | MongoDB 的文档本质上就是 BSON（JSON 的二进制扩展） |
| 消息队列 payload | 许多 MQ 系统默认用 JSON 做消息体 |
| 前后端状态传输 | Redux/Vuex 状态、AJAX 响应数据 |

---

## 2. JSON 语法规范

### 2.1 完整示例

```json
{
    "name": "张三",
    "age": 25,
    "is_student": false,
    "score": null,
    "courses": ["数学", "英语", "计算机"],
    "address": {
        "city": "北京",
        "zip": "100000",
        "geo": [39.9042, 116.4074]
    },
    "tags": ["developer", "c++", "linux"]
}
```

### 2.2 语法规则速查

| 规则 | 说明 | 反例 |
|---|---|---|
| 键必须用双引号 | `"key": value` | `'key': value`（单引号非法）、`{key: value}`（无引号非法） |
| 值类型仅限 6 种 | object、array、string、number、boolean、null | `undefined`、`NaN`、`Infinity` 都不是合法 JSON 值 |
| 不支持注释 | 标准 JSON 无 `//` 或 `/* */` | `{ // 注释 }` 解析失败 |
| 不支持尾逗号 | 最后一项后不能加逗号 | `[1, 2, 3,]` 解析失败 |
| 字符串必须双引号 | `"hello"` | `'hello'` 非法 |
| 数字无精度区分 | 整数和浮点数统一为 number | `25` 和 `25.0` 都是 number |
| 顶层可以是任意类型 | 不一定必须是对象 | `[1,2,3]`、`"hello"`、`42` 都是合法 JSON 文档 |

### 2.3 字符串转义规则

JSON 字符串中的特殊字符必须转义：

| 转义序列 | 含义 | Unicode 码点 |
|---|---|---|
| `\"` | 双引号 | U+0022 |
| `\\` | 反斜杠 | U+005C |
| `\/` | 正斜杠 | U+002F（可选转义） |
| `\b` | 退格 | U+0008 |
| `\f` | 换页 | U+000C |
| `\n` | 换行 | U+000A |
| `\r` | 回车 | U+000D |
| `\t` | 水平制表符 | U+0009 |
| `\uXXXX` | Unicode 码点 | 4 位十六进制，如 `\u4e2d` = 中 |

> **注意**：控制字符（U+0000 ~ U+001F）不能直接出现在 JSON 字符串中，必须用 `\uXXXX` 转义。这是许多手写 JSON 容易忽略的坑。

---

## 3. JSON 数据模型与类型系统

### 3.1 六种数据类型详解

| 类型 | 示例 | 说明 | C++ 映射（nlohmann） |
|---|---|---|---|
| object | `{"a": 1}` | 无序键值对集合，键唯一 | `std::map` / `std::unordered_map` |
| array | `[1, 2, 3]` | 有序值列表，可混合类型 | `std::vector` |
| string | `"hello"` | Unicode 文本，双引号包裹 | `std::string` |
| number | `42`, `3.14`, `-1e10` | 整数或浮点数，统一为 number | `int` / `double`（需注意精度） |
| boolean | `true` / `false` | 布尔值 | `bool` |
| null | `null` | 空值/缺失值 | `nullptr` 语义 |

### 3.2 number 类型的精度陷阱

JSON 规范**不区分整数和浮点数**，也不规定精度上限。这导致：

| 问题 | 说明 | 解决方案 |
|---|---|---|
| 大整数精度丢失 | JavaScript 的 number 是 IEEE 754 双精度浮点，安全整数范围为 ±2^53（约 9×10^15）。超过此范围的整数会丢失精度 | 大整数（如订单号、雪花 ID）用字符串传输 |
| 浮点数精度 | `0.1 + 0.2 !== 0.3` 在所有语言中都存在 | 金额用整数（分）或定点数（Decimal）传输 |
| 解析器差异 | 不同语言的 JSON 解析器对超大数字的处理不同（有的抛异常，有的转字符串，有的静默丢精度） | 不要依赖 number 的精确语义，关键 ID 用 string |

```text
// 反例：大整数用 number 传输，JavaScript 端精度丢失
// {"order_id": 9007199254740993}  →  JavaScript 读到 9007199254740992

// 正例：大整数用字符串传输
// {"order_id": "9007199254740993"}  →  各端都能精确读取
```

### 3.3 null 的语义

JSON 的 `null` 表示"值存在但为空"，与"键不存在"是两个不同的概念：

```json
{
    "name": "张三",
    "nickname": null,    // 键存在，值为空
    "email": null        // 键存在，值为空
    // "phone" 键不存在
}
```

| 场景 | 含义 | 处理方式 |
|---|---|---|
| 键存在且值为 null | 明确表示"无值"/"已清空" | `j.contains("nickname") && j["nickname"].is_null()` |
| 键不存在 | 字段未提供/未知 | `!j.contains("phone")` |
| 键存在且有值 | 正常数据 | `j["name"].get<std::string>()` |

> 在 API 设计中，PATCH 请求常用 `null` 表示"清空该字段"，而键不存在表示"不修改该字段"。这是 RESTful API 的常见约定。

---

## 4. JSON 解析原理

### 4.1 解析器的两种模型：DOM vs SAX

| 维度 | DOM（Document Object Model） | SAX（Simple API for XML，事件驱动） |
|---|---|---|
| 工作方式 | 一次性解析整个文档，构建内存中的树结构 | 边读边触发事件回调，不构建完整树 |
| 内存占用 | 与文档大小成正比（通常是文档的 2-10 倍） | 恒定（只保留当前状态） |
| 访问方式 | 随机访问任意节点 | 只能顺序访问，无法回溯 |
| 易用性 | 高（直接操作树节点） | 低（需要写状态机/回调） |
| 适用场景 | 中小文档、需要随机访问、需要修改 | 超大文档、流式处理、只需要提取部分字段 |
| 代表库 | nlohmann/json、rapidjson DOM、jsoncpp | rapidjson SAX、simdjson（On-Demand） |

### 4.2 解析器的性能优化技术

现代高性能 JSON 解析器采用了多种优化技术：

| 技术 | 说明 | 代表库 |
|---|---|---|
| SIMD 向量化 | 用 CPU 的 SIMD 指令（AVX2/NEON）一次处理多个字节，加速结构化字符扫描 | simdjson |
| 惰性解析（On-Demand） | 不一次性构建完整 DOM，只在访问字段时才解析对应部分 | simdjson On-Demand |
| 零拷贝字符串 | 解析时不复制字符串内容，直接指向输入缓冲区中的位置（需保证缓冲区生命周期） | rapidjson、simdjson |
| 内存池分配 | 用预分配的内存池管理节点，避免频繁 malloc/free | rapidjson |
| 状态机优化 | 用紧凑的状态机和跳转表加速字符分类 | 所有高性能库 |

### 4.3 解析性能对比（参考量级）

| 库 | 解析速度（参考） | 内存开销 | 易用性 |
|---|---|---|---|
| simdjson | 极快（~3GB/s，SIMD） | 低（On-Demand 模式） | 中（API 较底层） |
| rapidjson | 快（~1GB/s） | 低（DOM 模式） | 中（需要管理 Allocator） |
| nlohmann/json | 中（~100MB/s） | 较高（每个节点都是独立对象） | 高（STL 风格，头文件单文件） |
| jsoncpp | 较慢 | 中 | 高（经典 API） |

> 注意：以上速度为参考量级，实际性能取决于文档结构、编译器优化、CPU 架构。对于大多数业务场景（KB 级文档），nlohmann/json 的性能完全足够，易用性的价值远大于微秒级差异。

---

## 5. C++ JSON 解析库详解

### 5.1 nlohmann/json（推荐首选）

**特点**：单头文件、STL 风格 API、C++11 即可用、支持 JSON Pointer、JSON Patch、BSON/UBJSON/CBOR/MsgPack 二进制格式。

```cpp
#include <nlohmann/json.hpp>
using json = nlohmann::json;

// ===== 解析 =====
// 从字符串解析
json j = json::parse(R"({"name":"张三","age":25,"skills":["C++","Linux"]})");

// 从文件解析
std::ifstream f("config.json");
json config = json::parse(f);

// 解析异常处理
try {
    json j = json::parse(invalid_json_str);
} catch (const json::parse_error& e) {
    std::cerr << "JSON 解析失败: " << e.what() << '\n';
    // e.id 是错误码，e.byte 是出错位置
}

// ===== 访问 =====
std::string name = j["name"];              // 隐式转换，键不存在会插入 null！
int age = j.at("age").get<int>();          // at() 越界抛异常，推荐
std::string city = j.value("address", "未知"); // value() 提供默认值，不抛异常

// 安全访问（C++17 结构化绑定）
if (auto it = j.find("email"); it != j.end()) {
    std::string email = it->get<std::string>();
}

// ===== 遍历 =====
for (auto& [key, value] : j.items()) {     // C++17
    std::cout << key << ": " << value << '\n';
}
for (auto& el : j["skills"]) {              // 数组遍历
    std::cout << el.get<std::string>() << '\n';
}

// ===== 序列化 =====
std::string compact = j.dump();             // 紧凑格式
std::string pretty = j.dump(4);             // 4 空格缩进
std::string pretty_ensure_ascii = j.dump(4, ' ', true); // 第三个参数 ensure_ascii，非 ASCII 转义为 \uXXXX

// ===== 类型检查 =====
j.is_object();    // 是否为对象
j.is_array();     // 是否为数组
j.is_string();    // 是否为字符串
j.is_number();    // 是否为数字（整数或浮点）
j.is_boolean();   // 是否为布尔
j.is_null();      // 是否为 null
j.contains("key"); // 是否包含键（C++20 前用 find）
```

**nlohmann/json 的常见坑**：

| 坑 | 说明 | 正确做法 |
|---|---|---|
| `j["key"]` 不存在时插入 null | operator[] 是修改操作，const 对象不能用 | 用 `j.at("key")`（抛异常）或 `j.value("key", default)`（默认值） |
| 隐式转换导致意外类型 | `int x = j["age"]` 如果 age 是字符串会抛异常 | 用 `.get<int>()` 显式转换，或 `.get_to(x)` |
| 大文档内存爆炸 | 每个 JSON 值都是独立的 heap 对象，开销大 | 大文档用 simdjson 或 rapidjson |
| dump 中文变 \uXXXX | 默认 ensure_ascii=false 输出 UTF-8，设为 true 则转义 | 根据接收方能力选择 |

### 5.2 rapidjson（高性能场景）

**特点**：腾讯开源，高性能，支持 DOM/SAX 两种模式，需要手动管理 Allocator。

```cpp
#include "rapidjson/document.h"
#include "rapidjson/writer.h"
#include "rapidjson/stringbuffer.h"
using namespace rapidjson;

// DOM 解析
Document doc;
doc.Parse(R"({"name":"张三","age":25})");
if (doc.HasParseError()) {
    std::cerr << "解析错误: " << GetParseError_En(doc.GetParseError())
              << " at offset " << doc.GetErrorOffset() << '\n';
}

// 访问（注意：rapidjson 的字符串指针指向文档内部缓冲区，文档生命周期内有效）
assert(doc["name"].IsString());
const char* name = doc["name"].GetString();
int age = doc["age"].GetInt();

// 遍历数组
for (auto& v : doc["skills"].GetArray()) {
    std::cout << v.GetString() << '\n';
}

// 序列化
StringBuffer buffer;
Writer<StringBuffer> writer(buffer);
doc.Accept(writer);
std::string json_str = buffer.GetString();
```

### 5.3 simdjson（极致性能）

**特点**：利用 SIMD 指令实现极速解析，支持 On-Demand 惰性解析模式。适合超大 JSON 文档或高吞吐量场景。

```cpp
#include "simdjson.h"
using namespace simdjson;

// On-Demand 模式（推荐，惰性解析）
ondemand::parser parser;
auto doc = parser.iterate(json_string);  // 不立即解析全部

// 按需访问字段（只解析访问到的部分）
std::string_view name = doc["name"];
int64_t age = doc["age"];

// 数组遍历
for (auto skill : doc["skills"]) {
    std::string_view s = skill;
}
```

### 5.4 库选型决策

```text
需要解析 JSON 文档？
    │
    ├─ 文档 < 1MB，追求开发效率？
    │   └─ nlohmann/json（单头文件，STL 风格，最易用）
    │
    ├─ 文档 1MB~100MB，追求性能？
    │   └─ rapidjson（DOM/SAX，成熟稳定，性能好）
    │
    ├─ 文档 > 100MB 或超高吞吐？
    │   └─ simdjson（SIMD 加速，On-Demand 惰性解析）
    │
    └─ 需要在嵌入式/资源受限环境？
        └─ rapidjson（可裁剪，内存占用可控）或 jsmn（极简，<500 行）
```

---

## 6. JSON 与数据库

### 6.1 MySQL JSON 类型

MySQL 5.7 起原生支持 JSON 类型，8.0 进一步增强了函数和索引支持。

```sql
-- 建表
CREATE TABLE users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    info JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 插入
INSERT INTO users (info) VALUES
('{"name":"张三","age":25,"address":{"city":"北京"}}');

-- 查询：-> 提取（带引号），->> 提取（去引号，unquote）
SELECT info->>'$.name' AS name, info->>'$.address.city' AS city FROM users;

-- 等价函数
SELECT JSON_UNQUOTE(JSON_EXTRACT(info, '$.name')) FROM users;

-- 条件查询
SELECT * FROM users WHERE JSON_CONTAINS(info, '"张三"', '$.name');
SELECT * FROM users WHERE JSON_EXTRACT(info, '$.age') > 20;

-- 更新
UPDATE users SET info = JSON_SET(info, '$.age', 26) WHERE id = 1;
UPDATE users SET info = JSON_INSERT(info, '$.email', 'zhang@example.com') WHERE id = 1;
UPDATE users SET info = JSON_REMOVE(info, '$.email') WHERE id = 1;

-- 数组操作
UPDATE users SET info = JSON_ARRAY_APPEND(info, '$.skills', 'C++') WHERE id = 1;
```

| 函数 | 说明 |
|---|---|
| `JSON_EXTRACT(col, path)` / `col->path` | 提取值（保留引号） |
| `JSON_UNQUOTE(JSON_EXTRACT(...))` / `col->>path` | 提取并去引号 |
| `JSON_CONTAINS(col, val, path)` | 判断是否包含值 |
| `JSON_SET(col, path, val)` | 设置值（存在则更新，不存在则插入） |
| `JSON_INSERT(col, path, val)` | 插入值（仅当不存在时） |
| `JSON_REPLACE(col, path, val)` | 替换值（仅当存在时） |
| `JSON_REMOVE(col, path)` | 删除键/元素 |
| `JSON_ARRAY_APPEND(col, path, val)` | 向数组追加元素 |
| `JSON_LENGTH(col, path)` | 数组/对象长度 |
| `JSON_KEYS(col, path)` | 对象的所有键 |

**MySQL JSON 的索引限制**：JSON 列本身不能直接建普通索引，需要通过**生成列（Generated Column）**或**函数索引（MySQL 8.0）**实现：

```sql
-- 方法1：生成列 + 索引（5.7+）
ALTER TABLE users ADD COLUMN name_gen VARCHAR(50)
    GENERATED ALWAYS AS (info->>'$.name') STORED;
CREATE INDEX idx_name ON users(name_gen);

-- 方法2：函数索引（8.0+）
CREATE INDEX idx_name ON users((CAST(info->>'$.name' AS CHAR(50))));
```

### 6.2 PostgreSQL JSONB

PostgreSQL 有两种 JSON 类型：`json`（原文存储，解析慢）和 `jsonb`（二进制存储，解析快，支持索引）。**生产环境推荐用 jsonb**。

| 维度 | json | jsonb |
|---|---|---|
| 存储方式 | 原始文本（保留空格、键顺序） | 解析后的二进制格式 |
| 写入速度 | 快（不解析） | 慢（需解析） |
| 查询速度 | 慢（每次查询都解析） | 快（已解析） |
| 索引 | 不支持 GIN | 支持 GIN 索引 |
| 去重 | 保留重复键 | 去重（只保留最后一个） |
| 适用 | 只存储不查询、需要保留原始格式 | 需要查询、索引、频繁操作 |

```sql
-- GIN 索引加速 JSONB 查询
CREATE INDEX idx_info ON users USING GIN (info jsonb_path_ops);

-- 查询
SELECT * FROM users WHERE info @> '{"name": "张三"}';  -- 包含查询
SELECT * FROM users WHERE info -> 'address' ->> 'city' = '北京';
```

---

## 7. JSON Schema 与校验

标准 JSON 本身没有 schema 约束，但 **JSON Schema**（draft 2020-12）提供了声明式的数据校验能力。

```json
{
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "User",
    "type": "object",
    "required": ["name", "email"],
    "properties": {
        "name": { "type": "string", "minLength": 1, "maxLength": 50 },
        "age": { "type": "integer", "minimum": 0, "maximum": 150 },
        "email": { "type": "string", "format": "email" },
        "role": { "type": "string", "enum": ["admin", "user", "guest"] },
        "tags": { "type": "array", "items": { "type": "string" }, "uniqueItems": true }
    },
    "additionalProperties": false
}
```

| 关键字 | 作用 |
|---|---|
| `type` | 约束类型（object/array/string/number/integer/boolean/null） |
| `required` | 必需字段列表 |
| `properties` | 各字段的子 schema |
| `minimum`/`maximum` | 数值范围 |
| `minLength`/`maxLength` | 字符串长度 |
| `enum` | 枚举值 |
| `pattern` | 正则匹配 |
| `format` | 格式（email、date、uri 等） |
| `additionalProperties` | 是否允许额外字段 |
| `items` | 数组元素的 schema |
| `minItems`/`maxItems` | 数组长度 |

C++ 中可用 `json-schema-validator`（基于 nlohmann/json）做校验：

```cpp
#include <nlohmann/json-schema.hpp>
using nlohmann::json;
using nlohmann::json_schema::json_validator;

json schema = json::parse(R"({
    "type": "object",
    "required": ["name", "age"],
    "properties": {
        "name": {"type": "string"},
        "age": {"type": "integer", "minimum": 0}
    }
})");

json_validator validator(schema);
try {
    validator.validate(data);  // 校验失败抛异常
} catch (const std::exception& e) {
    std::cerr << "校验失败: " << e.what() << '\n';
}
```

---

## 8. JSON 与其他序列化格式对比

| 维度 | JSON | XML | Protobuf | MessagePack |
|---|---|---|---|---|
| 格式 | 文本 | 文本 | 二进制 | 二进制 |
| 可读性 | 好 | 好（但冗长） | 差（需 schema） | 差 |
| 体积 | 中 | 大 | 小 | 小 |
| 解析速度 | 中 | 慢 | 极快 | 快 |
| Schema | 可选（JSON Schema） | 强制（DTD/XSD） | 强制（.proto） | 无 |
| 跨语言 | 极好 | 好 | 好（需生成代码） | 好 |
| 二进制支持 | 需 Base64 | 需 Base64/CDATA | 原生 bytes | 原生 bin |
| 数字精度 | 双精度浮点 | 文本（任意精度） | 固定类型（int32/int64/double） | 双精度 |
| 适用场景 | Web API、配置、日志 | 配置、文档、WebService | 高性能 RPC、微服务 | 高效数据交换、缓存 |

> 选型建议：**对外 API 用 JSON**（可读性好、调试方便）；**内部高性能 RPC 用 Protobuf**（体积小、速度快、有 schema 约束）；**需要强 schema 和文档验证的传统企业系统用 XML**。

---

## 9. 常见坑与最佳实践

### 9.1 常见坑汇总

| 坑 | 现象 | 解决方案 |
|---|---|---|
| 用单引号写键 | 解析失败 | JSON 键必须双引号 |
| 尾逗号 | `[1,2,3,]` 解析失败 | 去掉最后一个逗号 |
| 大整数精度丢失 | 订单号 > 2^53 后末尾变 0 | 大整数用字符串传输 |
| 二进制数据无法存储 | JSON 只有文本类型 | 用 Base64 编码（体积膨胀 33%）或换二进制格式 |
| `j["key"]` 不存在时插入 null | nlohmann 的 operator[] 是修改操作 | 用 `at()` 或 `value()` 或 `find()` |
| 未处理解析异常 | 非法 JSON 导致程序崩溃 | 用 try/catch 包裹 parse，检查 HasParseError |
| 中文乱码 | 编码不统一（GBK vs UTF-8） | 统一用 UTF-8，解析前确认编码 |
| MySQL JSON 列无法建索引 | 查询全表扫描 | 用生成列或函数索引 |
| 混淆 null 和键不存在 | PATCH 语义错误 | 明确区分：null=清空，不存在=不修改 |
| 浮点数金额精度 | 0.1+0.2 问题 | 金额用整数（分）或定点数 |
| 注释 | JSON5/HJSON 有注释但标准 JSON 没有 | 标准 JSON 不用注释，配置文件可考虑 JSON5/TOML/YAML |

### 9.2 最佳实践

1. **统一 UTF-8 编码**：JSON 规范默认 UTF-8，所有生产和消费方都用 UTF-8，避免转码。
2. **大整数用字符串**：ID、订单号等可能超过 2^53 的字段一律用 string 类型。
3. **金额用整数或定点数**：不要用浮点数表示金额，用分为单位的整数或 Decimal 字符串。
4. **解析必须处理异常**：所有外部输入的 JSON 都可能非法，parse 必须包裹 try/catch。
5. **用 at()/value() 而非 operator[]**：nlohmann/json 中 operator[] 会插入 null，const 对象不能用，优先用 at()（抛异常）或 value()（默认值）。
6. **中小文档用 nlohmann/json**：开发效率优先，性能足够。大文档再考虑 rapidjson/simdjson。
7. **API 响应用统一包装**：`{"code": 0, "message": "ok", "data": {...}}` 便于错误处理。
8. **时间用 ISO 8601 字符串**：`"2024-01-15T08:30:00Z"`，不要用时间戳数字（时区和精度问题）。
9. **MySQL JSON 字段加生成列索引**：需要查询的 JSON 字段一定要建索引，否则全表扫描。
10. **不要用 JSON 替代关系型设计**：JSON 适合半结构化、稀疏字段，核心业务数据还是用规范的关系表。

---

## 10. 快速参考卡片

```text
语法：键双引号，值6种类型(object/array/string/number/boolean/null)，无注释无尾逗号
转义：\" \\ \/ \b \f \n \r \t \uXXXX
精度：大整数>2^53 用字符串；金额用整数分；时间用 ISO8601 字符串
库选型：nlohmann/json(易用首选) / rapidjson(高性能DOM/SAX) / simdjson(SIMD极速)
nlohmann：parse()解析，at()安全访问，value()给默认值，dump()序列化，items()遍历
MySQL：JSON类型 + ->>/JSON_EXTRACT 查询 + 生成列/函数索引
PG：JSONB + GIN索引 + @>包含查询
校验：JSON Schema + json-schema-validator
对比：JSON(文本可读) vs Protobuf(二进制高性能) vs XML(强schema冗长)
坑：单引号键/尾逗号/大整数精度/operator[]插入null/解析未捕获异常/中文编码
```

---

上一篇：《03-Protobuf序列化协议.md》
下一篇：《05-XML数据格式与解析.md》
