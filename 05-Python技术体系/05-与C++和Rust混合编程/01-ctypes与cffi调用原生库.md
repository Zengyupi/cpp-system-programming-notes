# ctypes 与 cffi 调用原生库

> 本节目标：用 ctypes 加载已编译的 .so/.dll 原生库，完成结构体、联合、指针、回调函数的类型映射，明确内存管理的责任边界，并用 cffi 提供更严格的类型检查。聚焦快速复用已编译 C 库，不涉及 C++ 名称修饰（那是 pybind11 的领域）。

## 本章速览

- [1. 工程场景：为什么从 Python 调用 C 库](#1-工程场景为什么从-python-调用-c-库)
- [2. ctypes 基础：加载库与函数调用](#2-ctypes-基础加载库与函数调用)
- [3. 类型映射与函数签名](#3-类型映射与函数签名)
- [4. 结构体与联合](#4-结构体与联合)
- [5. 指针与数组](#5-指针与数组)
  - [5.1 创建指针](#51-创建指针)
  - [5.2 数组](#52-数组)
  - [5.3 字符串与字节缓冲区](#53-字符串与字节缓冲区)
- [6. 回调函数](#6-回调函数)
- [7. 内存管理责任边界](#7-内存管理责任边界)
- [8. cffi：更严格的 C 外部函数接口](#8-cffi更严格的-c-外部函数接口)
- [9. 完整示例：复用已编译的协议解析库](#9-完整示例复用已编译的协议解析库)
- [10. 快速参考卡片](#10-快速参考卡片)
- [11. 常见坑](#11-常见坑)
- [12. 本节小结](#12-本节小结)

---

## 1. 工程场景：为什么从 Python 调用 C 库

C++ 程序员手里有大量已编译的 C 库：设备通讯协议库、加解密库、编解码库、硬件驱动 SDK。有时候需要用 Python 快速写个测试脚本、批量处理工具、或自动化验证流程，但不想把整个库用 Python 重写一遍。

典型场景：

- 设备厂商提供了 C SDK（.so + 头文件），需要用 Python 写自动化测试脚本，批量调用 SDK 接口验证设备行为。
- 已有一个 C 语言写的协议解析库，需要在 Python 的日志分析脚本中调用它解析二进制报文。
- 加解密算法用 C 实现了，Python 端需要调用而不是重新实现（避免引入 bug）。
- 硬件驱动只提供 C API，需要用 Python 做上层自动化。

ctypes 是 Python 标准库，零依赖，适合快速调用。cffi 是第三方库（以PyPI最新稳定版为准），提供 C 源码头文件级别的类型检查，更安全但需要额外安装。两者都只能调用 **C ABI** 的函数——C++ 函数因为名称修饰（name mangling）不能直接调用，需要用 `extern "C"` 包装或用 pybind11（见下一篇）。

## 2. ctypes 基础：加载库与函数调用

ctypes 加载动态库的方式因平台而异：

```python
"""ctypes_load.py — 加载动态库"""
import ctypes
import os
import platform

# 方式 1：按平台构造库路径
if platform.system() == "Windows":
    lib_path = os.path.join(os.path.dirname(__file__), "mylib.dll")
    lib = ctypes.CDLL(lib_path)
elif platform.system() == "Darwin":
    lib_path = os.path.join(os.path.dirname(__file__), "libmylib.dylib")
    lib = ctypes.CDLL(lib_path)
else:
    lib_path = os.path.join(os.path.dirname(__file__), "libmylib.so")
    lib = ctypes.CDLL(lib_path)

# 方式 2：用 ctypes.util 查找系统库（类似编译器 -l 查找）
import ctypes.util
libc_path = ctypes.util.find_library("c")
libc = ctypes.CDLL(libc_path)

# 方式 3：Windows 上用 WinDLL（stdcall 调用约定）
# lib = ctypes.WinDLL("mylib.dll")  # 32位 Windows stdcall
```

`CDLL` 用 cdecl 调用约定（Linux/macOS 默认，Windows 上 C/C++ 默认也是 cdecl）。`WinDLL` 用 stdcall（32 位 Windows API 常用）。64 位 Windows 上只有一种调用约定，两者等价。

调用函数：

```python
"""ctypes_call.py — 基本函数调用"""
import ctypes

lib = ctypes.CDLL("./libmathutil.so")

# 不声明签名直接调用（不推荐，参数类型不检查）
result = lib.add(3, 4)
print(result)  # 7

# 声明函数签名（推荐）
lib.add.argtypes = [ctypes.c_int, ctypes.c_int]
lib.add.restype = ctypes.c_int
result = lib.add(3, 4)
print(result)  # 7

# 调用 libc 的 printf
libc = ctypes.CDLL(ctypes.util.find_library("c"))
libc.printf.argtypes = [ctypes.c_char_p]
libc.printf.restype = ctypes.c_int
libc.printf(b"Hello from libc printf: %d\n", 42)  # 注意：变参函数 argtypes 只声明固定参数
```

**必须设置 `argtypes` 和 `restype`**。不设置时，ctypes 会做默认转换：整数转 `c_int`，字符串转 `c_char_p`，但浮点数会出错（默认当整数传），指针类型也会推断错误。显式声明是最佳实践。

## 3. 类型映射与函数签名

ctypes 类型与 C 类型的对应关系：

| ctypes 类型 | C 类型 | Python 传入 |
|---|---|---|
| `c_bool` | `_Bool` / `bool` | `True`/`False` |
| `c_char` | `char` | 单字节 bytes，如 `b"A"` |
| `c_byte` / `c_ubyte` | `signed/unsigned char` | int |
| `c_short` / `c_ushort` | `signed/unsigned short` | int |
| `c_int` / `c_uint` | `signed/unsigned int` | int |
| `c_long` / `c_ulong` | `signed/unsigned long` | int |
| `c_longlong` / `c_ulonglong` | `signed/unsigned long long` | int |
| `c_float` | `float` | float |
| `c_double` | `double` | float |
| `c_char_p` | `char *`（以 NUL 结尾） | bytes |
| `c_wchar_p` | `wchar_t *` | str |
| `c_void_p` | `void *` | int 或 None |
| `POINTER(c_int)` | `int *` | 指针对象 |

```python
"""ctypes_types.py — 类型映射示例"""
import ctypes

lib = ctypes.CDLL("./libdemo.so")

# int foo(double x, int flag, const char* name);
lib.foo.argtypes = [ctypes.c_double, ctypes.c_int, ctypes.c_char_p]
lib.foo.restype = ctypes.c_int
result = lib.foo(3.14, 1, b"device-001")

# void* create_context(int size);  返回不透明指针
lib.create_context.argtypes = [ctypes.c_int]
lib.create_context.restype = ctypes.c_void_p
ctx = lib.create_context(1024)
print(f"context pointer: {ctx}")  # 一个整数地址

# void destroy_context(void* ctx);
lib.destroy_context.argtypes = [ctypes.c_void_p]
lib.destroy_context.restype = None
lib.destroy_context(ctx)
```

不透明指针（`void *`）用 `c_void_p`，Python 端只保存地址，不解析内容。这是调用 C 库时最常见的模式——C 库内部管理结构体，Python 端只持有指针。

## 4. 结构体与联合

当 C 函数需要传入或返回结构体时，在 Python 端定义对应的 `ctypes.Structure`：

```python
"""ctypes_struct.py — 结构体与联合"""
import ctypes

# C 头文件中的定义：
# typedef struct {
#     uint32_t device_id;
#     char     name[32];
#     float    temperature;
#     uint8_t  status;
# } DeviceInfo;

class DeviceInfo(ctypes.Structure):
    _pack_ = 1  # 1 字节对齐，必须与 C 端一致
    _fields_ = [
        ("device_id", ctypes.c_uint32),
        ("name", ctypes.c_char * 32),
        ("temperature", ctypes.c_float),
        ("status", ctypes.c_uint8),
    ]

# 使用
info = DeviceInfo()
info.device_id = 0x12345678
info.name = b"sensor-001"
info.temperature = 36.5
info.status = 1

print(f"id=0x{info.device_id:08x}, name={info.name.decode()}, "
      f"temp={info.temperature}, status={info.status}")
print(f"结构体大小: {ctypes.sizeof(DeviceInfo)}")  # 4+32+4+1 = 41（_pack_=1）

# 传给 C 函数
# int register_device(DeviceInfo* info);
lib = ctypes.CDLL("./libdevice.so")
lib.register_device.argtypes = [ctypes.POINTER(DeviceInfo)]
lib.register_device.restype = ctypes.c_int
ret = lib.register_device(ctypes.byref(info))
```

联合的定义：

```python
"""ctypes_union.py — 联合"""
import ctypes

# C 定义：
# typedef union {
#     uint32_t u32;
#     uint16_t u16[2];
#     uint8_t  u8[4];
# } DataUnion;

class DataUnion(ctypes.Union):
    _fields_ = [
        ("u32", ctypes.c_uint32),
        ("u16", ctypes.c_uint16 * 2),
        ("u8", ctypes.c_uint8 * 4),
    ]

u = DataUnion()
u.u32 = 0x12345678
print(f"u16[0]=0x{u.u16[0]:04x}, u16[1]=0x{u.u16[1]:04x}")
print(f"u8={[hex(b) for b in u.u8]}")
```

**对齐是最容易出错的地方**。`_pack_` 必须与 C 端的 `#pragma pack` 或 `__attribute__((packed))` 一致。如果 C 端是默认对齐（通常 4 或 8 字节），Python 端不设 `_pack_`（默认按自然对齐）。不确定时，用 `ctypes.sizeof()` 与 C 端的 `sizeof` 对比验证。

位域也支持，在 `_fields_` 中加第三元素指定位数：

```python
class StatusReg(ctypes.Structure):
    _fields_ = [
        ("power_on", ctypes.c_uint8, 1),
        ("error", ctypes.c_uint8, 1),
        ("reserved", ctypes.c_uint8, 6),
    ]
```

## 5. 指针与数组

### 5.1 创建指针

```python
"""ctypes_pointer.py — 指针与数组"""
import ctypes

# 方式 1：pointer() 创建指针（指向 ctypes 变量）
x = ctypes.c_int(42)
px = ctypes.pointer(x)
print(px.contents.value)  # 42
px.contents.value = 100
print(x.value)  # 100

# 方式 2：byref() 更轻量，仅用于函数传参（不能访问 contents）
lib.process.argtypes = [ctypes.POINTER(ctypes.c_int)]
lib.process(ctypes.byref(x))

# 方式 3：从 Python 整数创建指针（不推荐，地址可能无效）
# p = ctypes.cast(0xdeadbeef, ctypes.POINTER(ctypes.c_int))
```

### 5.2 数组

```python
"""ctypes_array.py — 数组"""
import ctypes

# 定长数组：类型 * 长度
IntArray5 = ctypes.c_int * 5
arr = IntArray5(1, 2, 3, 4, 5)
print(arr[0], arr[4])  # 1 5
print(len(arr))  # 5

# 从 Python list 创建
data = [10, 20, 30, 40, 50]
arr = (ctypes.c_int * len(data))(*data)

# 传给 C 函数：int sum(int* arr, int n);
lib.sum.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_int]
lib.sum.restype = ctypes.c_int
result = lib.sum(arr, len(arr))
print(f"sum = {result}")  # 150

# 接收 C 端返回的数组指针
# int* get_buffer(int* out_size);
lib.get_buffer.argtypes = [ctypes.POINTER(ctypes.c_int)]
lib.get_buffer.restype = ctypes.POINTER(ctypes.c_int)
out_size = ctypes.c_int()
buf_ptr = lib.get_buffer(ctypes.byref(out_size))
# 用切片访问指针指向的数组
for i in range(out_size.value):
    print(f"buf[{i}] = {buf_ptr[i]}")
# 注意：buf_ptr 指向的内存在 C 端管理，不要在 Python 端 free
```

### 5.3 字符串与字节缓冲区

```python
"""ctypes_string.py — 字符串与缓冲区"""
import ctypes

# 传入 const char*：用 bytes
lib.set_name.argtypes = [ctypes.c_char_p]
lib.set_name(b"device-001")

# 传入可写缓冲区：create_string_buffer
buf = ctypes.create_string_buffer(256)  # 256 字节的可写缓冲区
lib.get_error_message.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
lib.get_error_message(buf, ctypes.sizeof(buf))
print(buf.value.decode("utf-8"))  # .value 返回到第一个 NUL 的 bytes

# create_unicode_buffer 对应 wchar_t*
wbuf = ctypes.create_unicode_buffer(256)
```

`c_char_p` 传入的 bytes 是只读的，C 函数不能修改它的内容。需要 C 端写入缓冲区时，必须用 `create_string_buffer()`。

## 6. 回调函数

C 库经常用回调函数做事件通知（如设备状态变化、数据到达）。ctypes 用 `CFUNCTYPE` 定义回调类型：

```python
"""ctypes_callback.py — 回调函数"""
import ctypes

# C 头文件：
# typedef void (*EventCallback)(int event_type, const char* message, void* user_data);
# void register_callback(EventCallback cb, void* user_data);

# 定义回调类型：返回值 void，参数 (int, char*, void*)
EventCallback = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p)

# 回调实现
@EventCallback
def on_event(event_type: int, message: bytes, user_data: int):
    print(f"[事件] type={event_type}, msg={message.decode()}, user_data={user_data}")
    # 注意：回调函数中不要做耗时操作，不要抛异常
    # 异常会导致 C 端未定义行为

# 注册回调
lib = ctypes.CDLL("./libdevice.so")
lib.register_callback.argtypes = [EventCallback, ctypes.c_void_p]
lib.register_callback.restype = None
lib.register_callback(on_event, None)

# 触发事件（C 端会调用回调）
lib.trigger_event(1, b"device connected")
```

**回调函数的生命周期管理是大坑**。`@EventCallback` 装饰器创建的回调对象必须保持引用，否则被 Python 垃圾回收后，C 端调用时会崩溃。如果回调是局部变量，函数返回后就被回收了。解决方案：

```python
# 错误：回调是局部变量，函数返回后被回收
def bad_register():
    @EventCallback
    def cb(etype, msg, ud):
        print(etype)
    lib.register_callback(cb, None)  # cb 在此函数返回后被回收！

# 正确：保存在全局或实例变量中
_callbacks = []  # 全局列表保持引用

def good_register():
    @EventCallback
    def cb(etype, msg, ud):
        print(etype)
    _callbacks.append(cb)  # 保持引用
    lib.register_callback(cb, None)
```

Windows 上 stdcall 回调用 `WINFUNCTYPE` 代替 `CFUNCTYPE`。

## 7. 内存管理责任边界

ctypes 调用 C 库时，内存管理的核心原则是**谁分配谁释放**。

```python
"""memory_mgmt.py — 内存管理责任边界"""
import ctypes

lib = ctypes.CDLL("./libdemo.so")

# 场景 1：C 端分配，C 端释放
# char* format_data(int value);  返回 C 端 malloc 的字符串
# void free_string(char* s);      C 端提供释放函数
lib.format_data.argtypes = [ctypes.c_int]
lib.format_data.restype = ctypes.c_char_p
lib.free_string.argtypes = [ctypes.c_char_p]

raw_ptr = lib.format_data(42)
# c_char_p 会自动转成 Python bytes，但原始指针丢失了！
# 正确做法：用 c_void_p 接收指针，复制内容后再释放
lib.format_data.restype = ctypes.c_void_p
ptr = lib.format_data(42)
result = ctypes.string_at(ptr).decode("utf-8")  # 复制到 Python
lib.free_string(ptr)  # C 端释放
print(result)

# 场景 2：Python 端分配，传给 C 端使用，Python 端释放
buf = ctypes.create_string_buffer(1024)
lib.fill_buffer.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
lib.fill_buffer(buf, ctypes.sizeof(buf))
print(buf.value.decode())
# buf 是 Python 对象，离开作用域后自动释放，不需要手动 free

# 场景 3：C 端返回结构体指针，需要用对应类型解析
# DeviceInfo* create_device(uint32_t id);
lib.create_device.argtypes = [ctypes.c_uint32]
lib.create_device.restype = ctypes.POINTER(DeviceInfo)
dev_ptr = lib.create_device(100)
print(f"id={dev_ptr.contents.device_id}, name={dev_ptr.contents.name.decode()}")
# 用完后 C 端释放
lib.destroy_device.argtypes = [ctypes.POINTER(DeviceInfo)]
lib.destroy_device(dev_ptr)
```

关键规则：

1. **C 端 `malloc` 的内存，必须用 C 端提供的 `free` 函数释放**，不能用 Python 的 `free`（不同的分配器）。
2. **`restype = c_char_p` 会自动把指针转成 bytes 并丢失原始地址**，如果 C 端需要释放，必须用 `c_void_p` 接收，`string_at()` 复制后再释放。
3. **Python 端 `create_string_buffer` 分配的内存由 Python 管理**，传给 C 端只读或写入都可以，但 C 端不能 `free` 它。
4. **不透明指针（`void*`）全程用 `c_void_p` 传递**，Python 端不解析内容，只在 C 端的 create/destroy 函数间传递。

## 8. cffi：更严格的 C 外部函数接口

cffi（以PyPI最新稳定版为准）是 ctypes 的替代方案，核心优势是**直接解析 C 头文件**，类型检查更严格，错误信息更清晰。安装：`pip install cffi`。

```python
"""cffi_basic.py — cffi 基础用法"""
from cffi import FFI

ffi = FFI()

# 声明 C 接口（直接写 C 声明，cffi 会解析类型）
ffi.cdef("""
    typedef struct {
        uint32_t device_id;
        char     name[32];
        float    temperature;
        uint8_t  status;
    } DeviceInfo;

    int add(int a, int b);
    int register_device(DeviceInfo* info);
    void* create_context(int size);
    void destroy_context(void* ctx);
    typedef void (*EventCallback)(int, const char*, void*);
    void register_callback(EventCallback cb, void* user_data);
""")

# 加载库
lib = ffi.dlopen("./libdevice.so")

# 调用函数
print(lib.add(3, 4))  # 7

# 创建结构体
info = ffi.new("DeviceInfo*")
info.device_id = 0x12345678
info.name = b"sensor-001"
info.temperature = 36.5
info.status = 1
ret = lib.register_device(info)

# 不透明指针
ctx = lib.create_context(1024)
print(f"ctx = {ctx}")
lib.destroy_context(ctx)

# 回调
@ffi.callback("void(int, const char*, void*)")
def on_event(event_type, message, user_data):
    print(f"[事件] type={event_type}, msg={ffi.string(message).decode()}")

lib.register_callback(on_event, ffi.NULL)
```

cffi 与 ctypes 的对比：

| 特性 | ctypes | cffi |
|---|---|---|
| 依赖 | 标准库 | 需 `pip install cffi` |
| 类型声明 | Python 类（`Structure`） | C 语法（`ffi.cdef`） |
| 类型检查 | 运行时弱检查 | 解析 C 声明，较严格 |
| 错误信息 | 模糊（段错误、类型错误） | 清晰（指出哪个参数类型不对） |
| 回调引用管理 | 需手动保持引用 | `@ffi.callback` 自动管理 |
| 内存分配 | `create_string_buffer` | `ffi.new()` / `ffi.buffer()` |
| 适用场景 | 快速脚本、零依赖 | 大型项目、需要类型安全 |

cffi 的 `ffi.new("Type*")` 分配的内存在 Python 端管理，`ffi.gc()` 可以绑定 C 端的释放函数实现自动清理：

```python
"""cffi_gc.py — cffi 自动内存清理"""
# ctx = ffi.gc(lib.create_context(1024), lib.destroy_context)
# ctx 被 Python 垃圾回收时自动调用 destroy_context
```

## 9. 完整示例：复用已编译的协议解析库

假设设备厂商提供了一个 C 语言的协议解析库 `libprotocol.so`，头文件如下：

```c
/* protocol.h */
#include <stdint.h>

typedef enum {
    PROTO_OK = 0,
    PROTO_ERR_BAD_MAGIC = -1,
    PROTO_ERR_BAD_CRC = -2,
    PROTO_ERR_TOO_SHORT = -3,
} ProtoStatus;

typedef struct {
    uint16_t length;
    uint8_t  version;
    uint8_t  cmd;
    uint32_t seq;
    uint8_t  payload[256];
} ProtoFrame;

/* 解析原始字节为帧结构，返回状态码 */
ProtoStatus proto_parse(const uint8_t* data, size_t len, ProtoFrame* out_frame);

/* 帧序列化为字节，返回实际写入长度 */
size_t proto_serialize(const ProtoFrame* frame, uint8_t* out_buf, size_t buf_size);

/* 计算 CRC16 */
uint16_t proto_crc16(const uint8_t* data, size_t len);
```

用 ctypes 调用这个库做批量报文解析：

```python
"""protocol_tool.py — 用 ctypes 调用 C 协议解析库做批量解析"""
import ctypes
import os
import sys

# 加载库
_lib_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "libprotocol.so")
lib = ctypes.CDLL(_lib_path)

# 枚举值
PROTO_OK = 0
PROTO_ERR_BAD_MAGIC = -1
PROTO_ERR_BAD_CRC = -2
PROTO_ERR_TOO_SHORT = -3

STATUS_NAMES = {
    PROTO_OK: "OK",
    PROTO_ERR_BAD_MAGIC: "BAD_MAGIC",
    PROTO_ERR_BAD_CRC: "BAD_CRC",
    PROTO_ERR_TOO_SHORT: "TOO_SHORT",
}

# 结构体
class ProtoFrame(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("length", ctypes.c_uint16),
        ("version", ctypes.c_uint8),
        ("cmd", ctypes.c_uint8),
        ("seq", ctypes.c_uint32),
        ("payload", ctypes.c_uint8 * 256),
    ]

# 函数签名
lib.proto_parse.argtypes = [
    ctypes.POINTER(ctypes.c_uint8),
    ctypes.c_size_t,
    ctypes.POINTER(ProtoFrame),
]
lib.proto_parse.restype = ctypes.c_int

lib.proto_serialize.argtypes = [
    ctypes.POINTER(ProtoFrame),
    ctypes.POINTER(ctypes.c_uint8),
    ctypes.c_size_t,
]
lib.proto_serialize.restype = ctypes.c_size_t

lib.proto_crc16.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t]
lib.proto_crc16.restype = ctypes.c_uint16

def parse_packet(data: bytes) -> tuple[int, ProtoFrame | None]:
    """解析单个报文"""
    buf = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
    frame = ProtoFrame()
    status = lib.proto_parse(buf, len(data), ctypes.byref(frame))
    return status, (frame if status == PROTO_OK else None)

def serialize_frame(frame: ProtoFrame) -> bytes:
    """帧序列化为字节"""
    out = (ctypes.c_uint8 * 512)()
    n = lib.proto_serialize(ctypes.byref(frame), out, ctypes.sizeof(out))
    return bytes(out[:n])

def batch_parse(filepath: str):
    """从文件批量读取报文（每行一个 hex 字符串）并解析"""
    ok_count = 0
    err_count = 0
    with open(filepath, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            hex_str = line.strip()
            if not hex_str or hex_str.startswith("#"):
                continue
            try:
                data = bytes.fromhex(hex_str)
            except ValueError:
                print(f"行 {lineno}: 无效 hex，跳过")
                continue

            status, frame = parse_packet(data)
            if status == PROTO_OK:
                ok_count += 1
                payload_hex = bytes(frame.payload[:frame.length - 8]).hex()
                print(f"行 {lineno}: OK  cmd=0x{frame.cmd:02x}  seq={frame.seq}  "
                      f"ver={frame.version}  payload={payload_hex}")
            else:
                err_count += 1
                print(f"行 {lineno}: FAIL  status={STATUS_NAMES.get(status, status)}  "
                      f"raw={data.hex()}")

    print(f"\n汇总: 成功={ok_count}, 失败={err_count}, 总计={ok_count + err_count}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python protocol_tool.py <packets.hex>")
        sys.exit(1)
    batch_parse(sys.argv[1])
```

这个示例展示了 ctypes 的典型用法：加载库 → 定义结构体 → 声明函数签名 → 写 Python 包装函数 → 批量处理。C 库负责协议解析的核心逻辑（已经过验证），Python 负责文件读取、批量调度、结果输出。

## 10. 快速参考卡片

| 需求 | 做法 |
| --- | --- |
| 加载动态库 | `lib = ctypes.CDLL("./libfoo.so")`（`CDLL` 用 cdecl；Windows 用 `WinDLL`） |
| 声明签名 | `lib.add.argtypes = [c_int, c_int]`；`lib.add.restype = c_int`（必须设，否则默认 int 截断） |
| 指针/数组 | `ctypes.c_int * 4` 建数组；`byref(x)`、`pointer(x)` 传地址 |
| 结构体 | `class P(ctypes.Structure): _fields_ = [("x", c_int)]`（与 C 侧 `#pragma pack` 对齐一致） |
| 字符串 | `c_char_p`（只读）、`create_string_buffer(b"abc", 64)`（可写缓冲区） |
| 回调 | `CFUNCTYPE(None, c_int)` 包装 Python 函数；注意被 GC 回收导致崩溃 |
| cffi 选型 | `ffi.cdef()` + `ffi.dlopen()`（ABI 模式）；API 模式可编译绑定，更快更安全 |
| 构建绑定 | `setuptools` 编译扩展或 `cffi` 的 `set_source` + `verify`（已弃用则用 API 模式） |
| GIL 注意 | ctypes 调用默认释放 GIL？——**不会**（除非库自己释放）；长计算会阻塞 Python 线程 |
| 常见坑点 | 忘记 `argtypes` 导致 64 位指针被截成 32 位；结构体对齐不一致；回调对象须持有引用 |

---

## 11. 常见坑

**坑 1：不声明 `argtypes`/`restype`。** 不声明时 ctypes 做默认转换，浮点数会当整数传（导致值错误），指针类型推断错误（段错误）。必须显式声明。

**坑 2：`restype = c_char_p` 丢失指针。** ctypes 会自动把 `char*` 转成 Python bytes，原始地址丢失。如果 C 端需要释放这个指针，必须用 `c_void_p` 接收，`string_at()` 复制后再释放。

**坑 3：回调函数被垃圾回收。** `CFUNCTYPE` 创建的回调对象如果是局部变量，函数返回后被回收，C 端后续调用时段错误。必须保存在全局变量、实例变量或列表中。

**坑 4：结构体对齐不一致。** `_pack_` 必须与 C 端一致。C 端默认对齐时 Python 端也不设 `_pack_`；C 端 `#pragma pack(1)` 时 Python 端 `_pack_ = 1`。用 `ctypes.sizeof()` 与 C 端 `sizeof` 对比验证。

**坑 5：用 Python 的 `free` 释放 C 端内存。** C 端 `malloc` 的内存必须用 C 端提供的释放函数（可能用不同的分配器）。反过来，Python 分配的缓冲区 C 端也不能 `free`。

**坑 6：`c_char_p` 传入的 bytes 被 C 端修改。** `c_char_p` 指向的 bytes 是 Python 不可变对象，C 端写入会导致内存损坏。需要可写缓冲区时用 `create_string_buffer()`。

**坑 7：C++ 函数不能直接调用。** C++ 函数有名称修饰（name mangling），ctypes 找不到符号。必须用 `extern "C"` 包装 C++ 函数，或用 pybind11（见下一篇）。

**坑 8：64 位指针当 32 位整数处理。** `c_void_p` 在 64 位系统上是 8 字节，如果函数签名写成 `c_int`（4 字节），指针会被截断导致段错误。指针一律用 `c_void_p` 或 `POINTER(类型)`。

## 12. 本节小结

- ctypes 是 Python 标准库，零依赖，适合快速调用已编译的 C 库。只能调用 C ABI，C++ 函数需要 `extern "C"` 包装或用 pybind11。
- 必须显式声明 `argtypes` 和 `restype`，避免默认转换导致的类型错误。
- 结构体用 `ctypes.Structure` 定义，`_pack_` 控制对齐，必须与 C 端一致；联合用 `ctypes.Union`；位域在 `_fields_` 中加位数。
- 指针用 `pointer()`/`byref()`/`POINTER()`，数组用 `类型 * 长度`，可写字符串缓冲区用 `create_string_buffer()`。
- 回调函数用 `CFUNCTYPE` 定义，必须保持回调对象的引用防止被垃圾回收。
- 内存管理核心原则：谁分配谁释放。C 端 `malloc` 的用 C 端函数释放，Python 分配的由 Python 管理。`restype=c_char_p` 会丢失指针，需要释放时用 `c_void_p`。
- cffi 提供 C 头文件级别的类型检查，更安全，`ffi.gc()` 支持自动清理，适合大型项目；ctypes 适合零依赖的快速脚本。
- 完整示例展示了典型工作流：加载库 → 定义结构体 → 声明签名 → Python 包装 → 批量处理，C 库做核心逻辑，Python 做调度和输出。

Rust 库的 FFI 互操作原理与 C 类似（Rust 也支持 `extern "C"` 导出 C ABI），更多内容参见《../../04-Rust技术体系/02-Rust进阶机制/02-Unsafe裸指针与FFI互操作.md》。

---

下一篇：《02-pybind11封装C++模块.md》　｜　模块索引：《../README.md》
