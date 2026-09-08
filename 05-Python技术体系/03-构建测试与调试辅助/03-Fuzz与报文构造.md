# Fuzz与报文构造

> 本节目标：掌握随机/变异数据生成器的设计、struct 模块的打包解包（字节序/对齐/memoryview）、按协议字段构造合法与畸形报文、pcap 回放与变异，能够用 Python 为 C++/Rust 网络程序构造测试报文并进行模糊测试，理解 atheris 的适用场景。

## 本章速览

- [1. 工程场景：为什么需要报文构造与 Fuzz](#1-工程场景为什么需要报文构造与-fuzz)
- [2. 随机与变异数据生成器](#2-随机与变异数据生成器)
  - [2.1 纯随机生成器](#21-纯随机生成器)
  - [2.2 变异生成器](#22-变异生成器)
  - [2.3 结构化随机生成器](#23-结构化随机生成器)
- [3. struct 模块：二进制打包解包](#3-struct-模块二进制打包解包)
  - [3.1 格式字符与字节序](#31-格式字符与字节序)
  - [3.2 打包与解包](#32-打包与解包)
  - [3.3 对齐与填充](#33-对齐与填充)
  - [3.4 memoryview 零拷贝操作](#34-memoryview-零拷贝操作)
- [4. 按协议字段构造报文](#4-按协议字段构造报文)
  - [4.1 合法报文构造](#41-合法报文构造)
  - [4.2 畸形报文构造](#42-畸形报文构造)
- [5. pcap 回放与变异](#5-pcap-回放与变异)
- [6. atheris：Python 覆盖率引导 Fuzz](#6-atherispython-覆盖率引导-fuzz)
- [7. 完整实战：协议报文 Fuzz 测试器](#7-完整实战协议报文-fuzz-测试器)
- [8. 常见坑与避坑指南](#8-常见坑与避坑指南)
- [9. 本节小结](#9-本节小结)

---

## 1. 工程场景：为什么需要报文构造与 Fuzz

工业网关、网络服务、嵌入式设备的核心是协议解析。协议解析器是最容易出漏洞的地方：畸形长度字段、越界偏移、不完整报文、特殊字符转义错误，都可能导致崩溃、内存破坏或逻辑错误。单元测试只能覆盖已知用例，**模糊测试（Fuzzing）** 通过大量随机/变异输入自动发现边界 bug。

Python 在 Fuzz 中的角色是**报文构造器和测试编排器**：用 `struct` 模块按协议字段打包二进制报文，用随机/变异生成器产生大量输入，通过 socket 或子进程发送给被测 C++/Rust 程序，监控是否崩溃或输出异常。

典型场景：

- **协议解析 Fuzz**：构造各种合法和畸形的协议报文，发送给解析器，检测崩溃
- **边界值测试**：长度字段为 0、最大值、与实际长度不匹配
- **pcap 回放变异**：从真实抓包文件中提取报文，变异后回放
- **压力测试**：高速发送随机报文，检测内存泄漏和性能退化

交叉引用：协议解析的手写实现见《../../02-网络协议与报文解析/08-抓包分析与手写报文解析.md》。

## 2. 随机与变异数据生成器

### 2.1 纯随机生成器

纯随机生成器产生完全随机的字节流，适合发现"任何输入都不应崩溃"的鲁棒性问题，但对有格式要求的协议命中率低。

```python
import os
import random

class RandomGenerator:
    """纯随机数据生成器。"""

    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

    def bytes(self, length: int) -> bytes:
        """生成随机字节。"""
        return bytes(self.rng.randint(0, 255) for _ in range(length))

    def bytes_os_random(self, length: int) -> bytes:
        """用操作系统熵源生成（不可重复，适合安全相关测试）。"""
        return os.urandom(length)

    def length(self, low: int = 0, high: int = 65535) -> int:
        """生成随机长度，偏向边界值。"""
        r = self.rng.random()
        if r < 0.1:
            return 0  # 空
        elif r < 0.2:
            return 1  # 最小
        elif r < 0.3:
            return high  # 最大
        elif r < 0.4:
            return high - 1  # 接近最大
        else:
            return self.rng.randint(low, high)

    def int_boundary(self, low: int, high: int) -> int:
        """生成偏向边界的整数。"""
        boundaries = [low, low + 1, high - 1, high, 0, -1, 1, -2**31, 2**31 - 1]
        if self.rng.random() < 0.5:
            return self.rng.choice([b for b in boundaries if low <= b <= high])
        return self.rng.randint(low, high)
```

### 2.2 变异生成器

变异生成器从一个已知的"种子报文"出发，通过随机修改产生新报文。比纯随机命中率高，因为保留了报文的基本结构。

```python
class Mutator:
    """报文变异器。"""

    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

    def mutate(self, data: bytes, max_mutations: int = 5) -> bytes:
        """对字节串进行随机变异。"""
        buf = bytearray(data)
        num_mutations = self.rng.randint(1, max_mutations)

        for _ in range(num_mutations):
            op = self.rng.choice([
                "flip_bit", "replace_byte", "insert_byte",
                "delete_byte", "duplicate_block", "swap_blocks",
                "overwrite_int",
            ])

            if op == "flip_bit" and buf:
                idx = self.rng.randrange(len(buf))
                bit = self.rng.randrange(8)
                buf[idx] ^= (1 << bit)

            elif op == "replace_byte" and buf:
                idx = self.rng.randrange(len(buf))
                buf[idx] = self.rng.randint(0, 255)

            elif op == "insert_byte":
                idx = self.rng.randrange(len(buf) + 1)
                buf.insert(idx, self.rng.randint(0, 255))

            elif op == "delete_byte" and len(buf) > 1:
                idx = self.rng.randrange(len(buf))
                del buf[idx]

            elif op == "duplicate_block" and buf:
                start = self.rng.randrange(len(buf))
                length = self.rng.randint(1, min(32, len(buf) - start))
                block = buf[start:start + length]
                insert_pos = self.rng.randrange(len(buf) + 1)
                buf[insert_pos:insert_pos] = block

            elif op == "swap_blocks" and len(buf) >= 4:
                size = self.rng.randint(1, min(8, len(buf) // 2))
                pos1 = self.rng.randrange(len(buf) - size * 2)
                pos2 = self.rng.randrange(pos1 + size, len(buf) - size + 1)
                buf[pos1:pos1 + size], buf[pos2:pos2 + size] = \
                    buf[pos2:pos2 + size], buf[pos1:pos1 + size]

            elif op == "overwrite_int" and len(buf) >= 4:
                idx = self.rng.randrange(len(buf) - 3)
                value = self.rng.choice([0, 1, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF, self.rng.randint(0, 2**32 - 1)])
                struct.pack_into("<I", buf, idx, value)

        return bytes(buf)
```

### 2.3 结构化随机生成器

结构化随机生成器了解协议格式，按字段生成随机值，保证报文的基本结构合法，只在字段值上做文章。命中率最高。

```python
import struct

class StructuredGenerator:
    """按协议字段结构生成随机报文。"""

    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

    def generate_header(self, msg_type: int | None = None) -> bytes:
        """生成协议头：magic(2) + version(1) + msg_type(1) + length(2) + seq(2)。"""
        magic = 0xAA55
        version = self.rng.choice([1, 2])
        msg_type = msg_type if msg_type is not None else self.rng.randint(0, 255)
        length = self.rng.choice([0, 1, 100, 1000, 65535, self.rng.randint(0, 100)])
        seq = self.rng.randint(0, 65535)
        return struct.pack(">HBBHH", magic, version, msg_type, length, seq)

    def generate_payload(self, length: int) -> bytes:
        """生成随机负载。"""
        if length == 0:
            return b""
        # 有时用全 0、全 0xFF、可打印字符等特殊模式
        pattern = self.rng.choice(["random", "zeros", "ones", "printable", "debruijn"])
        if pattern == "zeros":
            return b"\x00" * length
        elif pattern == "ones":
            return b"\xFF" * length
        elif pattern == "printable":
            return bytes(self.rng.randint(0x20, 0x7E) for _ in range(length))
        elif pattern == "debruijn":
            # De Bruijn 序列，便于定位溢出偏移
            pattern_bytes = b"Aa0Aa1Aa2Aa3Aa4Aa5Aa6Aa7Aa8Aa9Ab0Ab1Ab2"
            return (pattern_bytes * ((length // len(pattern_bytes)) + 1))[:length]
        else:
            return bytes(self.rng.randint(0, 255) for _ in range(length))

    def generate_message(self, msg_type: int | None = None) -> bytes:
        """生成完整报文。"""
        header = self.generate_header(msg_type)
        # 从 header 中解析 length 字段
        _, _, _, length, _ = struct.unpack(">HBBHH", header)
        payload = self.generate_payload(length)
        return header + payload
```

## 3. struct 模块：二进制打包解包

### 3.1 格式字符与字节序

| 字符 | C 类型 | Python 类型 | 大小 |
|---|---|---|---|
| `b`/`B` | signed/unsigned char | int | 1 |
| `h`/`H` | signed/unsigned short | int | 2 |
| `i`/`I` | signed/unsigned int | int | 4 |
| `q`/`Q` | signed/unsigned long long | int | 8 |
| `f`/`d` | float/double | float | 4/8 |
| `s` | char[] | bytes | 定长 |
| `x` | 填充字节 | - | 1 |

字节序前缀：

| 前缀 | 字节序 | 对齐 |
|---|---|---|
| `>` / `!` | 大端（网络字节序） | 无 |
| `<` | 小端 | 无 |
| `=` | 原生 | 无 |
| `@`（默认） | 原生 | 原生对齐 |

**网络协议用大端（`>` 或 `!`），x86 本地结构体用小端（`<`）。**

### 3.2 打包与解包

```python
import struct

# 打包：header = magic(2) + type(1) + length(2) + payload
header = struct.pack(">H B H", 0xAA55, 0x01, 100)
# header = b'\xaa\x55\x01\x00d'

# 解包
magic, msg_type, length = struct.unpack(">H B H", header)
print(f"magic=0x{magic:04X}, type={msg_type}, length={length}")

# 定长字符串
name = struct.pack(">16s", b"hello")  # 自动补零到 16 字节
unpacked = struct.unpack(">16s", name)[0].rstrip(b"\x00")  # 去掉补零

# 计算格式大小
struct.calcsize(">H B H")  # 5

# 从指定偏移解包（不切片，避免拷贝）
data = b"\x00\x01\x02\x03\x04\x05\x06\x07"
struct.unpack_from(">I", data, offset=2)  # (0x02030405,)

# 打包到指定偏移（写入 bytearray）
buf = bytearray(8)
struct.pack_into(">I", buf, 0, 0x12345678)
struct.pack_into(">I", buf, 4, 0xDEADBEEF)
```

### 3.3 对齐与填充

默认 `@` 模式会按 C 结构体规则对齐，可能产生填充字节。网络协议通常用 `>` 或 `<` 禁用对齐。

```python
# 默认对齐（@）：int 4 字节对齐，char 后补 3 字节
struct.calcsize("b i")   # 8（1 + 3 填充 + 4）

# 禁用对齐（> 或 <）：无填充
struct.calcsize(">b i")  # 5（1 + 4）

# 手动填充：用 x 表示填充字节
struct.pack(">b x x x i", 1, 0x12345678)  # 显式补 3 字节
```

### 3.4 memoryview 零拷贝操作

`memoryview` 允许在不拷贝的情况下操作字节序列的切片，适合处理大报文。

```python
data = bytearray(1024)
view = memoryview(data)

# 切片不拷贝
header_view = view[0:8]       # 8 字节的 view
payload_view = view[8:]        # 剩余的 view

# 通过 view 修改原数据
struct.pack_into(">H", header_view, 0, 0xAA55)
print(data[0:2])  # bytearray(b'\xaa\x55')

# 转换为 bytes（这一步才拷贝）
header_bytes = header_view.tobytes()

# 释放 view（避免持有大 buffer 的引用导致无法 GC）
view.release()
header_view.release()
```

## 4. 按协议字段构造报文

### 4.1 合法报文构造

```python
class ProtocolMessage:
    """协议报文构造器。

    报文格式：
    - magic: 2 bytes (0xAA55)
    - version: 1 byte
    - msg_type: 1 byte
    - length: 2 bytes (payload 长度)
    - seq: 2 bytes
    - payload: length bytes
    - checksum: 2 bytes (CRC16，payload 的校验)
    """

    MAGIC = 0xAA55
    HEADER_SIZE = 8  # magic(2) + version(1) + type(1) + length(2) + seq(2)
    TRAILER_SIZE = 2  # checksum

    def __init__(self, version: int = 1, msg_type: int = 0, seq: int = 0,
                 payload: bytes = b""):
        self.version = version
        self.msg_type = msg_type
        self.seq = seq
        self.payload = payload

    @staticmethod
    def crc16(data: bytes) -> int:
        """简单 CRC16 校验。"""
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc & 0xFFFF

    def pack(self) -> bytes:
        """打包为二进制报文。"""
        header = struct.pack(
            ">H B B H H",
            self.MAGIC, self.version, self.msg_type,
            len(self.payload), self.seq,
        )
        checksum = self.crc16(self.payload)
        trailer = struct.pack(">H", checksum)
        return header + self.payload + trailer

    @classmethod
    def unpack(cls, data: bytes) -> "ProtocolMessage":
        """从二进制报文解析。"""
        if len(data) < cls.HEADER_SIZE + cls.TRAILER_SIZE:
            raise ValueError(f"报文过短: {len(data)} bytes")

        magic, version, msg_type, length, seq = struct.unpack_from(">H B B H H", data, 0)
        if magic != cls.MAGIC:
            raise ValueError(f"magic 不匹配: 0x{magic:04X}")

        payload_start = cls.HEADER_SIZE
        payload_end = payload_start + length
        if payload_end + cls.TRAILER_SIZE > len(data):
            raise ValueError(f"length 字段越界: {length} > {len(data) - cls.HEADER_SIZE - cls.TRAILER_SIZE}")

        payload = data[payload_start:payload_end]
        checksum = struct.unpack_from(">H", data, payload_end)[0]
        expected = cls.crc16(payload)
        if checksum != expected:
            raise ValueError(f"校验和错误: 0x{checksum:04X} != 0x{expected:04X}")

        return cls(version, msg_type, seq, payload)

# 用法
msg = ProtocolMessage(version=1, msg_type=0x01, seq=42, payload=b"hello")
binary = msg.pack()
parsed = ProtocolMessage.unpack(binary)
```

### 4.2 畸形报文构造

畸形报文用于测试解析器的鲁棒性。常见的畸形类型：

```python
class MalformedGenerator:
    """畸形报文生成器。"""

    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

    def truncated(self, valid_msg: bytes) -> bytes:
        """截断报文：只保留前 N 字节。"""
        cut = self.rng.randint(0, len(valid_msg) - 1)
        return valid_msg[:cut]

    def wrong_length(self, valid_msg: bytes) -> bytes:
        """length 字段与实际 payload 不匹配。"""
        buf = bytearray(valid_msg)
        # 修改 length 字段（偏移 4，2 字节大端）
        fake_length = self.rng.choice([0, 1, 0xFFFF, len(buf) + 100, self.rng.randint(0, 65535)])
        struct.pack_into(">H", buf, 4, fake_length)
        return bytes(buf)

    def wrong_magic(self, valid_msg: bytes) -> bytes:
        """magic 字段错误。"""
        buf = bytearray(valid_msg)
        struct.pack_into(">H", buf, 0, self.rng.choice([0x0000, 0xFFFF, 0x55AA, self.rng.randint(0, 65535)]))
        return bytes(buf)

    def wrong_checksum(self, valid_msg: bytes) -> bytes:
        """校验和错误。"""
        buf = bytearray(valid_msg)
        struct.pack_into(">H", buf, len(buf) - 2, self.rng.randint(0, 65535))
        return bytes(buf)

    def extra_data(self, valid_msg: bytes) -> bytes:
        """报文后追加多余数据。"""
        return valid_msg + bytes(self.rng.randint(0, 255) for _ in range(self.rng.randint(1, 100)))

    def null_bytes_in_payload(self, valid_msg: bytes) -> bytes:
        """payload 中插入 null 字节（测试字符串处理）。"""
        buf = bytearray(valid_msg)
        header_size = ProtocolMessage.HEADER_SIZE
        if len(buf) > header_size + 2:
            pos = header_size + 1
            buf.insert(pos, 0x00)
            # 更新 length 字段
            old_length = struct.unpack_from(">H", buf, 4)[0]
            struct.pack_into(">H", buf, 4, old_length + 1)
        return bytes(buf)

    def generate_all(self, valid_msg: bytes) -> list[tuple[str, bytes]]:
        """生成所有类型的畸形报文。"""
        return [
            ("truncated", self.truncated(valid_msg)),
            ("wrong_length", self.wrong_length(valid_msg)),
            ("wrong_magic", self.wrong_magic(valid_msg)),
            ("wrong_checksum", self.wrong_checksum(valid_msg)),
            ("extra_data", self.extra_data(valid_msg)),
            ("null_bytes", self.null_bytes_in_payload(valid_msg)),
        ]
```

## 5. pcap 回放与变异

pcap 是网络抓包文件格式。可以从真实抓包中提取报文，变异后回放给被测程序。

```python
import struct
from pathlib import Path

class PcapReader:
    """简易 pcap 文件读取器（libpcap 格式）。"""

    PCAP_MAGIC = 0xA1B2C3D4
    PCAP_MAGIC_NS = 0xA1B23C4D  # 纳秒精度

    def __init__(self, filepath: Path):
        self.filepath = filepath
        self._f = None
        self._endian = "<"
        self._ts_resolution = 1_000_000  # 微秒

    def __enter__(self):
        self._f = self.filepath.open("rb")
        magic = struct.unpack("<I", self._f.read(4))[0]
        if magic == self.PCAP_MAGIC:
            self._endian = "<"
            self._ts_resolution = 1_000_000
        elif magic == self.PCAP_MAGIC_NS:
            self._endian = "<"
            self._ts_resolution = 1_000_000_000
        elif struct.unpack(">I", struct.pack("<I", magic))[0] == self.PCAP_MAGIC:
            self._endian = ">"
            self._ts_resolution = 1_000_000
        else:
            raise ValueError(f"不是有效的 pcap 文件: magic=0x{magic:08X}")

        # 跳过 global header 剩余 20 字节
        self._f.read(20)
        return self

    def __exit__(self, *args):
        if self._f:
            self._f.close()

    def __iter__(self):
        return self

    def __next__(self) -> dict:
        """读取下一个数据包。"""
        header = self._f.read(16)
        if len(header) < 16:
            raise StopIteration

        ts_sec, ts_frac, incl_len, orig_len = struct.unpack(
            f"{self._endian}IIII", header
        )
        data = self._f.read(incl_len)
        timestamp = ts_sec + ts_frac / self._ts_resolution

        return {
            "timestamp": timestamp,
            "incl_len": incl_len,
            "orig_len": orig_len,
            "data": data,
        }

def extract_application_data(packet: bytes) -> bytes:
    """从以太网帧中提取应用层数据（简化版，假设 TCP）。"""
    if len(packet) < 54:  # 14(以太网) + 20(IP) + 20(TCP)
        return b""
    # 简化：跳过以太网(14) + IP头(20) + TCP头(20) = 54
    # 实际应解析 IP header length 和 TCP data offset
    return packet[54:]

def replay_and_mutate(pcap_path: Path, mutator: Mutator,
                       send_func, num_packets: int = 1000):
    """从 pcap 读取报文，变异后回放。"""
    with PcapReader(pcap_path) as reader:
        count = 0
        for packet in reader:
            app_data = extract_application_data(packet["data"])
            if not app_data:
                continue

            # 原始报文 + 变异报文都发送
            send_func(app_data)
            mutated = mutator.mutate(app_data)
            send_func(mutated)

            count += 1
            if count >= num_packets:
                break

    print(f"回放并变异了 {count} 个报文")
```

**注意**：完整的 pcap 解析应使用 `dpkt` 或 `scapy` 库（`pip install dpkt scapy`），上面的简化版只适用于固定格式的抓包。

## 6. atheris：Python 覆盖率引导 Fuzz

atheris 是 Google 开源的 Python 覆盖率引导 Fuzz 引擎（`pip install atheris`），基于 libFuzzer。它可以 Fuzz Python 代码，也可以通过 ctypes/cffi Fuzz 原生库。

```python
import atheris

# 最小用法：Fuzz 一个 Python 函数
def TestOneInput(data: bytes):
    """atheris 回调：每次调用传入一个变异后的 bytes。"""
    try:
        # 调用被测函数
        ProtocolMessage.unpack(data)
    except (ValueError, struct.error):
        # 预期内的异常，不算 bug
        pass
    # 未捕获的异常（如 IndexError、AssertionError）会被 atheris 报告为 bug

atheris.Setup(sys.argv, TestOneInput)
atheris.Fuzz()
```

运行：`python fuzz.py -max_len=1024 -rss_limit_mb=2048`

atheris 会自动维护语料库、计算覆盖率、引导变异方向，比纯随机 Fuzz 效率高得多。对于 C++/Rust 程序，推荐用原生 Fuzz 工具（libFuzzer for C++，cargo-fuzz for Rust），Python atheris 适用于：

- Fuzz Python 编写的协议解析器
- 通过 ctypes 调用 C 库进行 Fuzz
- 快速验证解析逻辑，不需要编译原生 Fuzzer

## 7. 完整实战：协议报文 Fuzz 测试器

整合以上能力，实现一个完整的协议 Fuzz 测试器：生成合法/畸形/随机/变异报文，通过子进程发送给被测程序，监控崩溃。

```python
#!/usr/bin/env python3
"""协议报文 Fuzz 测试器。

用法:
  python protocol_fuzz.py --target build/parser --cases 10000
  python protocol_fuzz.py --target build/parser --pcap capture.pcap --cases 5000
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

class Fuzzer:
    """协议 Fuzz 测试器。"""

    def __init__(self, target: Path, seed: int = 42, timeout: float = 2.0):
        self.target = target
        self.rng = random.Random(seed)
        self.structured = StructuredGenerator(seed)
        self.mutator = Mutator(seed)
        self.malformed = MalformedGenerator(seed)
        self.timeout = timeout
        self.stats = {"total": 0, "crashes": 0, "timeouts": 0, "valid_rejected": 0}
        self.crashes = []

    def send_to_target(self, data: bytes) -> tuple[int, str]:
        """通过 stdin 发送报文给被测程序，返回 (returncode, stderr)。"""
        try:
            result = subprocess.run(
                [str(self.target)],
                input=data,
                capture_output=True,
                timeout=self.timeout,
            )
            return result.returncode, result.stderr.decode("utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            return -1, "TIMEOUT"

    def is_crash(self, returncode: int) -> bool:
        """判断是否崩溃（返回码 < 0 表示被信号终止，如 SIGSEGV=11）。"""
        return returncode < 0 or returncode in (134, 139)  # 134=SIGABRT, 139=SIGSEGV

    def fuzz_case(self, name: str, data: bytes) -> bool:
        """执行单个 Fuzz 用例，返回是否崩溃。"""
        self.stats["total"] += 1
        code, stderr = self.send_to_target(data)

        if self.is_crash(code):
            self.stats["crashes"] += 1
            crash_info = {
                "name": name,
                "returncode": code,
                "stderr": stderr[:500],
                "data_hex": data[:256].hex(),
                "data_len": len(data),
            }
            self.crashes.append(crash_info)
            print(f"\n[CRASH] {name}: returncode={code}, len={len(data)}")
            print(f"  stderr: {stderr[:200]}")
            return True

        if code == -1:
            self.stats["timeouts"] += 1

        return False

    def run(self, num_cases: int, pcap_path: Path | None = None):
        """运行 Fuzz 测试。"""
        print(f"Fuzz 目标: {self.target}")
        print(f"用例数: {num_cases}")
        print("=" * 60)

        # 种子报文：一个合法报文
        seed_msg = ProtocolMessage(
            version=1, msg_type=0x01, seq=0,
            payload=b"seed payload for fuzzing",
        ).pack()

        # 如果有 pcap，从中提取种子
        pcap_seeds = []
        if pcap_path and pcap_path.exists():
            with PcapReader(pcap_path) as reader:
                for i, packet in enumerate(reader):
                    app_data = extract_application_data(packet["data"])
                    if app_data:
                        pcap_seeds.append(app_data)
                    if len(pcap_seeds) >= 100:
                        break
            print(f"从 pcap 提取了 {len(pcap_seeds)} 个种子报文")

        start_time = time.time()
        for i in range(num_cases):
            # 选择 Fuzz 策略
            strategy = self.rng.choices(
                ["structured", "mutate_seed", "mutate_pcap", "malformed", "random"],
                weights=[30, 30, 15, 15, 10],
            )[0]

            if strategy == "structured":
                data = self.structured.generate_message()
                name = f"structured_{i}"

            elif strategy == "mutate_seed":
                data = self.mutator.mutate(seed_msg)
                name = f"mutate_seed_{i}"

            elif strategy == "mutate_pcap" and pcap_seeds:
                seed = self.rng.choice(pcap_seeds)
                data = self.mutator.mutate(seed)
                name = f"mutate_pcap_{i}"

            elif strategy == "malformed":
                mal_type, data = self.rng.choice(self.malformed.generate_all(seed_msg))
                name = f"malformed_{mal_type}_{i}"

            else:  # random
                length = self.structured.rng.randint(0, 2048)
                gen = RandomGenerator(self.rng.randint(0, 2**31))
                data = gen.bytes(length)
                name = f"random_{i}"

            crashed = self.fuzz_case(name, data)
            if crashed and len(self.crashes) >= 10:
                print(f"\n已发现 {len(self.crashes)} 个崩溃，停止测试")
                break

            if (i + 1) % 500 == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed
                print(f"进度: {i + 1}/{num_cases}, "
                      f"崩溃: {self.stats['crashes']}, "
                      f"超时: {self.stats['timeouts']}, "
                      f"速率: {rate:.0f} cases/s")

        elapsed = time.time() - start_time
        print(f"\n{'=' * 60}")
        print(f"完成: {self.stats['total']} 用例, {elapsed:.1f}s, "
              f"{self.stats['total'] / elapsed:.0f} cases/s")
        print(f"崩溃: {self.stats['crashes']}, 超时: {self.stats['timeouts']}")

        # 保存崩溃样本
        if self.crashes:
            crash_dir = Path("fuzz_crashes")
            crash_dir.mkdir(exist_ok=True)
            for j, crash in enumerate(self.crashes):
                (crash_dir / f"crash_{j}.bin").write_bytes(
                    bytes.fromhex(crash["data_hex"])
                )
                (crash_dir / f"crash_{j}.txt").write_text(
                    f"name: {crash['name']}\n"
                    f"returncode: {crash['returncode']}\n"
                    f"stderr: {crash['stderr']}\n"
                    f"data_len: {crash['data_len']}\n",
                    encoding="utf-8",
                )
            print(f"崩溃样本已保存到: {crash_dir}")

        return len(self.crashes) == 0

def main():
    parser = argparse.ArgumentParser(description="协议报文 Fuzz 测试器")
    parser.add_argument("--target", type=Path, required=True, help="被测程序路径")
    parser.add_argument("--cases", type=int, default=5000, help="Fuzz 用例数")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    parser.add_argument("--pcap", type=Path, help="pcap 种子文件")
    parser.add_argument("--timeout", type=float, default=2.0, help="单用例超时(秒)")
    args = parser.parse_args()

    if not args.target.exists():
        raise SystemExit(f"被测程序不存在: {args.target}")

    fuzzer = Fuzzer(args.target, seed=args.seed, timeout=args.timeout)
    success = fuzzer.run(args.cases, pcap_path=args.pcap)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
```

## 8. 常见坑与避坑指南

| 坑 | 现象 | 解决方案 |
|---|---|---|
| 字节序错误 | 解析出的字段值不对 | 网络协议用 `>`（大端），x86 本地用 `<`（小端），始终显式指定 |
| struct 对齐填充 | 打包结果比预期多字节 | 用 `>` 或 `<` 禁用对齐，或用 `x` 显式填充 |
| 长度字段与实际不匹配 | 解析器越界读或截断 | 构造报文时 length 必须等于实际 payload 长度，畸形测试时故意设错 |
| Fuzz 太慢 | 每秒只能跑几个用例 | 减少子进程启动开销（用常驻进程 + socket），或用 atheris/libFuzzer |
| 变异破坏了报文结构 | 变异后的报文 magic 不对，直接被拒绝 | 用结构化生成器保证基本结构，只变异字段值；或用覆盖率引导 Fuzz |
| pcap 解析不完整 | 只提取到部分报文 | 用 dpkt/scapy 库解析，处理 VLAN、IP 选项、TCP 选项等 |
| CRC/校验和计算错误 | 合法报文被拒绝 | 用已知报文验证校验和算法，注意字节序和初始值 |
| memoryview 未释放 | 大 buffer 无法 GC | 用完调用 `view.release()`，或用 `with memoryview(...)` 上下文 |
| 随机种子不可复现 | 崩溃后无法复现 | 始终记录种子，Fuzzer 构造时传入 seed |

## 9. 本节小结

- 随机生成器分三种：纯随机（鲁棒性）、变异（基于种子）、结构化（按协议字段，命中率最高）
- 变异操作包括位翻转、字节替换/插入/删除、块复制/交换、整数覆盖，偏向边界值
- `struct` 模块是二进制报文构造的核心：`pack`/`unpack`/`pack_into`/`unpack_from`，始终显式指定字节序
- `memoryview` 实现零拷贝切片，适合大报文处理，用完需 `release()`
- 协议报文构造器包含 magic、版本、类型、长度、序列号、payload、校验和，支持打包和解包
- 畸形报文包括截断、长度不匹配、magic 错误、校验和错误、追加数据、null 字节注入
- pcap 回放从真实抓包提取种子报文，变异后回放
- atheris 是 Python 覆盖率引导 Fuzz 引擎，适合 Python 解析器和通过 ctypes 调用 C 库
- 完整 Fuzz 测试器整合了结构化生成、变异、畸形、pcap 种子、崩溃监控和样本保存

跨模块参考：
- 《../../02-网络协议与报文解析/08-抓包分析与手写报文解析.md》
- 《../../01-C++技术体系/07-调试与测试/02-Valgrind内存检测.md》

---

上一篇：《02-测试驱动与对拍器.md》
下一篇：《04-调试与性能分析辅助.md》
