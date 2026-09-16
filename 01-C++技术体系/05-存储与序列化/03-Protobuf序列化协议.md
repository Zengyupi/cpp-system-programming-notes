# Protobuf 序列化协议

> 本节目标：掌握 Protobuf 的编码原理与工程实践——.proto 语法与字段编号、varint 变长编码、tag 的 field_number+wire_type 结构、zigzag 负数编码、proto2/proto3 差异与兼容性规则、与 gRPC 的关系。学完能手算 Protobuf 编码字节、设计向前/向后兼容的 schema，并理解其相比 JSON/XML 的体积与性能优势。关联《04-JSON数据格式与解析.md》《05-XML数据格式与解析.md》构成序列化三剑客。

## 本章速览

- [1. 与 JSON/XML 对比](#1-与-jsonxml-对比)
- [2. .proto 语法](#2-proto-语法)
  - [2.1 字段类型](#21-字段类型)
- [3. 编码原理（核心）](#3-编码原理核心)
  - [3.1 Varint 变长编码](#31-varint-变长编码)
  - [3.2 Tag（字段键）](#32-tag字段键)
  - [3.3 完整编码示例](#33-完整编码示例)
  - [3.4 Zigzag 编码（负数）](#34-zigzag-编码负数)
- [4. proto2 vs proto3](#4-proto2-vs-proto3)
- [5. 编译与使用](#5-编译与使用)
- [6. 兼容性](#6-兼容性)
- [7. 与 gRPC 的关系](#7-与-grpc-的关系)
- [8. 快速参考卡片](#8-快速参考卡片)
- [9. 常见坑](#9-常见坑)

---

## 1. 与 JSON/XML 对比

| 维度     | Protobuf        | JSON          | XML        |
| ------ | --------------- | ------------- | ---------- |
| 格式     | 二进制             | 文本            | 文本         |
| 体积     | 最小（约 1/3\~1/10） | 中             | 大          |
| 速度     | 最快              | 中             | 慢          |
| 可读性    | 不可读             | 好             | 较好         |
| schema | .proto 强定义      | 无/JSON Schema | DTD/Schema |
| 跨语言    | 强（代码生成）         | 通用            | 通用         |
| 适用     | RPC、高性能传输       | Web API       | 配置、文档      |

## 2. .proto 语法

```protobuf
syntax = "proto3";

package user;                       // 包名（对应 C++ 命名空间）

import "common.proto";              // 导入其他 proto

message Person {
    int32 id = 1;                   // 字段 = 编号（编码用）
    string name = 2;
    string email = 3;
    repeated string phones = 4;     // 数组/列表
    Address addr = 5;               // 嵌套 message
    map<string, int32> scores = 6;  // map
    Status status = 7;              // enum

    reserved 8, 9;                  // 保留编号（防止复用）
    reserved "old_field";           // 保留字段名
}

message Address {
    string city = 1;
    string zip = 2;
}

enum Status {
    UNKNOWN = 0;                    // proto3 枚举必须从 0 开始
    ACTIVE = 1;
    INACTIVE = 2;
}
```

### 2.1 字段类型

| proto 类型          | C++ 类型              | 说明               |
| ----------------- | ------------------- | ---------------- |
| int32/uint32      | int32\_t/uint32\_t  | 变长编码             |
| sint32/sint64     | int32\_t/int64\_t   | zigzag 编码（负数高效）  |
| fixed32/fixed64   | uint32\_t/uint64\_t | 定长 4/8 字节        |
| sfixed32/sfixed64 | int32\_t/int64\_t   | 定长有符号            |
| float/double      | float/double        | 定长               |
| bool              | bool                | varint           |
| string            | std::string         | length-delimited |
| bytes             | std::string         | 二进制              |
| repeated          | 容器                  | 数组               |

## 3. 编码原理（核心）

### 3.1 Varint 变长编码

整数按 7 位一组，**小端序**，每字节最高位是**延续位**（1=还有后续，0=结束）。

```text
值 300 的编码：
300 二进制 = 100101100
分 7 位（低 7 位在前）：0101100  0000010
加延续位：10101100  00000010
→ 0xAC 0x02（小端，低字节在前）
```

```cpp
// varint 解码逻辑
uint64_t read_varint(const uint8_t* buf, int& pos) {
    uint64_t result = 0;
    int shift = 0;
    while (true) {
        uint8_t byte = buf[pos++];
        result |= (uint64_t)(byte & 0x7F) << shift;
        if (!(byte & 0x80)) break;      // 最高位 0 表示结束
        shift += 7;
    }
    return result;
}
```

### 3.2 Tag（字段键）

每个字段前有一个 tag 字节（可能多字节）：

```text
tag = (field_number << 3) | wire_type
```

| wire\_type | 值 | 含义               | 适用类型                   |
| ---------- | - | ---------------- | ---------------------- |
| 0          | 0 | Varint           | int32/64、bool、enum     |
| 1          | 1 | 64-bit           | fixed64、double         |
| 2          | 2 | Length-delimited | string、bytes、嵌套、packed |
| 5          | 5 | 32-bit           | fixed32、float          |

**示例**：字段编号 1，wire\_type 0（varint）→ tag = (1<<3)|0 = 8 = 0x08。

### 3.3 完整编码示例

```text
message Test1 { int32 a = 1; }
// a = 150
```

编码过程：

1. tag = (1 << 3) | 0 = 0x08
2. varint(150) = 0x96 0x01（150 二进制 10010110，7 位一组 0000001 0010110，加延续位 → 10010110 00000001）
3. 结果：`08 96 01`（3 字节）

```text
message Test2 { string b = 2; }
// b = "testing"（7 字节）
```

编码过程：

1. tag = (2 << 3) | 2 = 18 = 0x12
2. length = 7 = 0x07
3. 内容 "testing"
4. 结果：`12 07 74 65 73 74 69 6e 67`

### 3.4 Zigzag 编码（负数）

`int32` 存负数时 varint 会变成 10 字节（负数补码全是 1）。用 `sint32` + zigzag 解决：

```text
zigzag(n) = (n << 1) ^ (n >> 31)   // 32 位
zigzag(n) = (n << 1) ^ (n >> 63)   // 64 位
```

| 原值 | zigzag 值 |
| -- | -------- |
| 0  | 0        |
| -1 | 1        |
| 1  | 2        |
| -2 | 3        |
| 2  | 4        |

```text
int32_t zigzag_encode(int32_t n) { return (n << 1) ^ (n >> 31); }
int32_t zigzag_decode(int32_t n) { return (n >> 1) ^ -(n & 1); }
```

**负数用 sint32/sint64，避免 varint 膨胀。**

## 4. proto2 vs proto3

| 特性         | proto2       | proto3                  |
| ---------- | ------------ | ----------------------- |
| required   | 支持           | 移除                      |
| optional   | 支持           | 所有字段默认 optional         |
| 默认值        | 可自定义         | 固定（0/空/false）           |
| 枚举首值       | 任意           | 必须为 0                   |
| extensions | 支持           | 移除（用 Any）               |
| 字段存在性检查    | has\_field() | 标量无 has（可选 optional 恢复） |

## 5. 编译与使用

```bash
# 生成 C++ 代码
protoc --cpp_out=. person.proto
# 生成 gRPC 代码
protoc --grpc_out=. --plugin=protoc-gen-grpc=$(which grpc_cpp_plugin) person.proto
```

```cpp
// C++ 序列化与反序列化
Person p;
p.set_id(1);
p.set_name("张三");
p.add_phones("123456");

// 序列化
std::string data;
p.SerializeToString(&data);

// 反序列化
Person p2;
p2.ParseFromString(data);
std::cout << p2.name() << std::endl;
```

## 6. 兼容性

| 规则             | 说明        |
| -------------- | --------- |
| 不修改已有字段编号      | 编号是编码身份   |
| 删除字段用 reserved | 防止编号被复用   |
| 新增字段用新编号       | 老程序忽略未知字段 |
| 不修改字段类型        | 会导致解码错误   |

**向前兼容**：新程序读旧数据（缺字段用默认值）；**向后兼容**：旧程序读新数据（忽略未知字段）。

## 7. 与 gRPC 的关系

```text
gRPC = Protobuf（序列化）+ HTTP/2（传输）+ 代码生成（服务定义）
```

```protobuf
service UserService {
    rpc GetUser(GetUserRequest) returns (GetUserResponse);
}
```

Protobuf 定义消息，gRPC 用 `.proto` 的 service 定义生成 RPC 框架代码。

## 8. 快速参考卡片

```text
体积：Protobuf < JSON < XML；速度相反
tag = (field_number << 3) | wire_type
varint：7 位一组，最高位延续位，小端序
负数用 sint + zigzag，避免 varint 膨胀
wire_type：0=varint 1=64bit 2=length 5=32bit
字段编号是身份，删除用 reserved，不可复用
proto3：无 required，标量有固定默认值但无法区分「未设置」与「设为默认值」
```

**常见坑：**

1. 修改已有字段编号或类型，导致新旧数据不兼容。
2. 负数用 int32 而非 sint32，体积膨胀 10 字节。
3. 删除字段未用 reserved，编号被复用导致错误解析。
4. proto3 标量默认值 0，无法区分"未设置"和"设为 0"。
5. 未处理 `ParseFromString` 返回值（失败返回 false）。

---


## 9. 常见坑

- **字段号是契约**：不得随意修改或复用字段号；删除字段要用 `reserved` 占位，否则新旧版本必然错解。
- **兼容边界**：新增 `optional` 字段最安全；把 `int32` 改成 `string`、或改字段号都会破坏兼容。
- **proto3 默认值陷阱**：标量字段等于默认值时不会被序列化，接收方无法区分"未设置"与"显式设为 0"——需要区分时加 `optional` 并用 `has_xxx()`。
- **`required` 不要用**：proto2 的 `required` 一旦漏传即解析失败，升级/灰度时极易炸。
- **负数用 `sint32`**：普通 `int32` 存负数走 varint 要占满 10 字节，`sint32/sint64` 用 zigzag 编码更省。
- **`map` 无序**：遍历顺序不保证，依赖顺序的逻辑要自己排序；`repeated` 数值类型默认 packed 编码。
- **大消息防护**：解析前设总字节上限（`set_total_bytes_limit`），避免恶意超大报文打爆内存。
- **常见坑**：`SerializeToString()` / `ParseFromString()` 的返回值未检查就继续用；跨语言字段名规范化不一致（如 `foo_bar` vs `fooBar`）。

---

上一篇：《02-Redis设计与数据结构.md》　｜　下一篇：《04-JSON数据格式与解析.md》　｜　模块索引：《../README.md》
