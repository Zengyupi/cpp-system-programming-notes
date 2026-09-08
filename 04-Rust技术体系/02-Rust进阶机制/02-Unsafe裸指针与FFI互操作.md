# Unsafe裸指针与FFI互操作

> 本节目标：掌握unsafe的五种能力边界、裸指针操作、union与transmute、extern "C" ABI、C库调用完整实战、bindgen/cbindgen工具链、cxx与C++互操作、static mut的安全替代，以及封装unsafe为安全API的设计原则。

## 本章速览

- [1. unsafe的五种能力边界](#1-unsafe的五种能力边界)
  - [1.1 解引用裸指针](#11-解引用裸指针)
  - [1.2 调用unsafe函数或方法](#12-调用unsafe函数或方法)
  - [1.3 访问或修改static mut变量](#13-访问或修改static-mut变量)
  - [1.4 实现unsafe trait](#14-实现unsafe-trait)
  - [1.5 访问union的字段](#15-访问union的字段)
- [2. 裸指针*const/*mut](#2-裸指针constmut)
  - [2.1 创建与转换](#21-创建与转换)
  - [2.2 裸指针的算术运算](#22-裸指针的算术运算)
  - [2.3 对照C++指针](#23-对照c指针)
- [3. as转换与transmute](#3-as转换与transmute)
  - [3.1 as指针转换](#31-as指针转换)
  - [3.2 transmute的风险与替代](#32-transmute的风险与替代)
- [4. union类型](#4-union类型)
- [5. extern "C" ABI与C库调用实战](#5-extern-c-abi与c库调用实战)
  - [5.1 声明外部函数](#51-声明外部函数)
  - [5.2 完整实战：封装libc的mmap](#52-完整实战封装libc的mmap)
  - [5.3 字符串与CString](#53-字符串与cstring)
- [6. bindgen与cbindgen工具链](#6-bindgen与cbindgen工具链)
  - [6.1 bindgen：C头文件生成Rust绑定](#61-bindgenc头文件生成rust绑定)
  - [6.2 cbindgen：Rust生成C头文件](#62-cbindgenrust生成c头文件)
- [7. cxx与C++互操作](#7-cxx与c互操作)
- [8. static mut的安全替代](#8-static-mut的安全替代)
- [9. 封装unsafe为安全API的原则](#9-封装unsafe为安全api的原则)
  - [原则1：最小unsafe范围](#原则1最小unsafe范围)
  - [原则2：在安全边界验证前置条件](#原则2在安全边界验证前置条件)
  - [原则3：用类型系统维护不变量](#原则3用类型系统维护不变量)
  - [原则4：文档化安全要求](#原则4文档化安全要求)
- [10. 本节小结](#10-本节小结)

---

## 1. unsafe的五种能力边界

`unsafe`关键字不是"关闭安全检查"的开关，而是一个**能力声明**：在`unsafe`块中，程序员承诺自己维护Rust安全不变量，编译器信任这个承诺。unsafe只解锁五种特定能力。

### 1.1 解引用裸指针

```rust
let x = 42;
let ptr = &x as *const i32;

// 编译错误：不能在安全代码中解引用裸指针
// let val = *ptr;

unsafe {
    let val = *ptr; // OK：在unsafe块中解引用
    println!("{}", val);
}
```

### 1.2 调用unsafe函数或方法

```rust
// 声明一个unsafe函数
unsafe fn dangerous_operation(ptr: *mut i32) {
    *ptr = 100;
}

fn main() {
    let mut x = 0;
    // dangerous_operation(&mut x); // 编译错误：unsafe函数不能在安全上下文调用

    unsafe {
        dangerous_operation(&mut x); // OK
    }
}
```

标准库中大量函数是unsafe的，例如`Vec::set_len`、`str::from_utf8_unchecked`、`slice::from_raw_parts`。

### 1.3 访问或修改static mut变量

```rust
static mut COUNTER: i32 = 0;

fn main() {
    unsafe {
        COUNTER += 1; // 读写static mut都需要unsafe
        println!("{}", COUNTER);
    }
}
```

`static mut`是Rust中最容易被滥用的特性之一，因为它本质上是一个全局可变变量，存在数据竞争风险。详见第8节的安全替代方案。

### 1.4 实现unsafe trait

```rust
// 声明一个unsafe trait：实现者必须承诺某些不变量
unsafe trait MySafeMarker {
    // 这个trait的实现需要unsafe，因为编译器无法验证实现的正确性
}

struct MyType;

// 实现unsafe trait需要unsafe关键字
unsafe impl MySafeMarker for MyType {}
```

标准库中的`Send`和`Sync`是unsafe trait（自动trait），手动实现它们需要unsafe，因为编译器无法验证类型确实是线程安全的。

### 1.5 访问union的字段

```rust
union MyUnion {
    i: i32,
    f: f32,
}

fn main() {
    let u = MyUnion { i: 42 };

    // 访问union字段需要unsafe，因为编译器不知道当前存储的是哪个变体
    unsafe {
        println!("{}", u.i); // OK
        println!("{}", u.f); // 未定义行为：把i32的位模式当作f32解读
    }
}
```

对照C++：C++中`union`的字段访问不需要任何特殊标记，类型双关（type punning）在C++中是未定义行为但编译器通常不报错。Rust把这种风险显式标记为unsafe，提醒程序员这里需要额外小心。

## 2. 裸指针*const/*mut

裸指针是Rust中最接近C指针的类型，不受借用检查器约束。

### 2.1 创建与转换

```rust
// 从引用创建裸指针（安全操作，不需要unsafe）
let x = 42;
let const_ptr: *const i32 = &x;

let mut y = 100;
let mut_ptr: *mut i32 = &mut y;

// 裸指针之间的转换
let const_from_mut: *const i32 = mut_ptr as *const i32;

// Box::into_raw：把Box变成裸指针，转移所有权
let boxed = Box::new(50);
let raw = Box::into_raw(boxed);
unsafe {
    println!("{}", *raw);
    // 必须用Box::from_raw回收，否则内存泄漏
    let _ = Box::from_raw(raw);
}
```

### 2.2 裸指针的算术运算

```rust
let arr = [1, 2, 3, 4, 5];
let ptr = arr.as_ptr();

unsafe {
    // 指针偏移：offset方法
    println!("{}", *ptr.offset(2)); // 输出3

    // add/sub方法（更直观）
    println!("{}", *ptr.add(3)); // 输出4

    // 裸指针的read/write（不执行drop，适合手动内存管理）
    let mut val = 0;
    let dst = &mut val as *mut i32;
    dst.write(999);
    println!("{}", dst.read()); // 输出999
}
```

### 2.3 对照C++指针

| 操作 | Rust裸指针 | C++原始指针 |
|------|-----------|-------------|
| 解引用 | `unsafe { *ptr }` | `*ptr` |
| 空指针 | `std::ptr::null()` / `null_mut()` | `nullptr` |
| 判空 | `ptr.is_null()` | `ptr == nullptr` |
| 偏移 | `ptr.offset(n)` / `ptr.add(n)` | `ptr + n` |
| 指针转引用 | `unsafe { &*ptr }` | `*ptr`（直接用） |
| 引用转指针 | `&x as *const T` | `&x` |

关键区别：Rust的引用（`&T`/`&mut T`）有编译器强制的别名规则和生命周期，裸指针（`*const T`/`*mut T`）没有。从裸指针创建引用时，程序员必须保证引用的有效性和别名规则。

## 3. as转换与transmute

### 3.1 as指针转换

```rust
// 数值与指针之间的转换
let addr = 0x7fff_1234_5678usize;
let ptr = addr as *const i32; // 整数转指针

let back = ptr as usize; // 指针转整数

// 不同类型指针之间的转换
let i_ptr: *const i32 = &42;
let u_ptr: *const u32 = i_ptr as *const u32; // 类型双关

unsafe {
    println!("{:x}", *u_ptr); // 把i32的位模式当作u32解读
}
```

### 3.2 transmute的风险与替代

`std::mem::transmute`是Rust中最强大的类型转换工具，它直接把一种类型的位模式重新解释为另一种类型。

```rust
use std::mem;

unsafe {
    // i32的位模式转u32
    let i: i32 = -1;
    let u: u32 = mem::transmute(i);
    println!("{}", u); // 输出4294967295

    // f32转u32（查看IEEE 754位模式）
    let f: f32 = 1.0;
    let bits: u32 = mem::transmute(f);
    println!("{:08x}", bits); // 输出3f800000
}
```

**transmute的风险**：
1. 尺寸不匹配会编译错误，但语义不匹配不会
2. 可以把任意类型转成任意类型，包括不相关的类型
3. 违反类型不变量（例如把`0`转成`&'static T`）

**优先使用的安全替代**：

```rust
// f32转u32：使用to_bits（安全）
let f: f32 = 1.0;
let bits = f.to_bits(); // 安全，不需要unsafe

// u32转f32：使用from_bits（安全）
let f2 = f32::from_bits(bits);

// 引用转裸指针再转回来：使用as（安全的部分）
let x = 42;
let ptr = &x as *const i32;
let reference = unsafe { &*ptr }; // 只有这一步需要unsafe
```

对照C++：`transmute`等价于C++的`reinterpret_cast`，但C++的`reinterpret_cast`可以在任何地方使用，不需要标记unsafe。Rust要求显式的unsafe块，让代码审查者能快速定位风险点。

## 4. union类型

Rust的union与C的union语义相同：所有字段共享同一块内存。

```rust
#[repr(C)]
union Data {
    int_val: i32,
    float_val: f32,
    bytes: [u8; 4],
}

fn main() {
    let mut d = Data { int_val: 0x4142_4344 };

    unsafe {
        // 查看字节表示
        println!("{:?}", d.bytes); // 小端序：[68, 67, 66, 65]

        // 类型双关：把i32当作f32解读（通常是未定义行为）
        println!("{}", d.float_val);
    }

    // 写入另一个字段
    d.float_val = 3.14;
    unsafe {
        println!("{:?}", d.bytes); // 3.14的IEEE 754表示
    }
}
```

`#[repr(C)]`保证union的内存布局与C兼容，这在FFI中至关重要。没有`#[repr(C)]`的union使用Rust默认布局，不保证与C兼容。

## 5. extern "C" ABI与C库调用实战

### 5.1 声明外部函数

```rust
// 声明C标准库函数
extern "C" {
    fn abs(x: i32) -> i32;
    fn malloc(size: usize) -> *mut std::ffi::c_void;
    fn free(ptr: *mut std::ffi::c_void);
    fn strlen(s: *const std::ffi::c_char) -> usize;
}

fn main() {
    unsafe {
        println!("{}", abs(-42)); // 输出42

        let ptr = malloc(1024);
        if !ptr.is_null() {
            free(ptr);
        }
    }
}
```

`extern "C"`指定使用C的调用约定（ABI）。Rust默认的ABI是`"Rust"`，不保证与C兼容。其他可用的ABI包括`"C-unwind"`、`"system"`、`"stdcall"`（Windows）等。

### 5.2 完整实战：封装libc的mmap

下面是一个完整的、安全的mmap封装示例：

```rust
use std::ffi::c_void;
use std::ptr;

// 常量定义（与sys/mman.h中的值对应，Linux x86_64）
const PROT_READ: i32 = 0x1;
const PROT_WRITE: i32 = 0x2;
const MAP_PRIVATE: i32 = 0x02;
const MAP_ANONYMOUS: i32 = 0x20;
const MAP_FAILED: *mut c_void = !0usize as *mut c_void;

extern "C" {
    fn mmap(
        addr: *mut c_void,
        length: usize,
        prot: i32,
        flags: i32,
        fd: i32,
        offset: i64,
    ) -> *mut c_void;

    fn munmap(addr: *mut c_void, length: usize) -> i32;
}

/// 安全的匿名内存映射封装
pub struct Mmap {
    ptr: *mut u8,
    len: usize,
}

impl Mmap {
    /// 创建一个匿名的、可读可写的内存映射
    pub fn new(size: usize) -> Result<Self, &'static str> {
        if size == 0 {
            return Err("size must be greater than 0");
        }

        let ptr = unsafe {
            mmap(
                ptr::null_mut(),
                size,
                PROT_READ | PROT_WRITE,
                MAP_PRIVATE | MAP_ANONYMOUS,
                -1,
                0,
            )
        };

        if ptr == MAP_FAILED {
            return Err("mmap failed");
        }

        Ok(Mmap {
            ptr: ptr as *mut u8,
            len: size,
        })
    }

    /// 获取映射区域的切片（安全）
    pub fn as_slice(&self) -> &[u8] {
        unsafe { std::slice::from_raw_parts(self.ptr, self.len) }
    }

    /// 获取映射区域的可变切片（安全）
    pub fn as_mut_slice(&mut self) -> &mut [u8] {
        unsafe { std::slice::from_raw_parts_mut(self.ptr, self.len) }
    }
}

impl Drop for Mmap {
    fn drop(&mut self) {
        unsafe {
            munmap(self.ptr as *mut c_void, self.len);
        }
    }
}

fn main() {
    let mut mmap = Mmap::new(4096).expect("mmap failed");

    // 安全地使用映射内存
    let slice = mmap.as_mut_slice();
    slice[0] = 0xAB;
    slice[1] = 0xCD;

    println!("{:02x} {:02x}", slice[0], slice[1]);
    // drop时自动munmap
}
```

这个封装展示了核心原则：**unsafe的能力被限制在最小范围内，对外暴露的API是完全安全的**。用户不需要知道内部使用了mmap，只需要像使用普通`Vec<u8>`一样使用`Mmap`。

### 5.3 字符串与CString

Rust的`&str`和C的`const char*`有本质区别：Rust字符串不是以`\0`结尾的，而是带长度的。

```rust
use std::ffi::{CStr, CString};

fn main() {
    // Rust字符串转C字符串（需要追加\0）
    let rust_str = "hello";
    let c_string = CString::new(rust_str).expect("CString::new failed");

    extern "C" {
        fn puts(s: *const std::ffi::c_char) -> i32;
    }

    unsafe {
        puts(c_string.as_ptr()); // as_ptr()返回*const c_char
    }

    // C字符串转Rust字符串
    let c_buf = b"world\0";
    let c_str = unsafe { CStr::from_ptr(c_buf.as_ptr() as *const std::ffi::c_char) };
    let rust_str_back = c_str.to_str().expect("invalid UTF-8");
    println!("{}", rust_str_back);
}
```

`CString::new`会检查字符串中是否包含内部`\0`（这对C字符串是非法的），返回`Result`。如果确定没有内部`\0`，可以使用`CString::new("...").unwrap()`或`CString::from_vec_with_nul`。

## 6. bindgen与cbindgen工具链

### 6.1 bindgen：C头文件生成Rust绑定

bindgen自动从C头文件生成Rust的`extern "C"`声明，避免手动翻译出错。

```bash
# 安装bindgen
cargo install bindgen-cli

# 生成绑定
bindgen wrapper.h -o bindings.rs
```

`wrapper.h`包含需要生成绑定的头文件：

```c
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
```

在`build.rs`中集成bindgen（以crates.io最新稳定版为准）：

```rust
// build.rs
fn main() {
    println!("cargo:rerun-if-changed=wrapper.h");

    let bindings = bindgen::Builder::default()
        .header("wrapper.h")
        .parse_callbacks(Box::new(bindgen::CargoCallbacks::new()))
        .generate()
        .expect("Unable to generate bindings");

    let out_path = std::path::PathBuf::from(std::env::var("OUT_DIR").unwrap());
    bindings
        .write_to_file(out_path.join("bindings.rs"))
        .expect("Couldn't write bindings!");
}
```

### 6.2 cbindgen：Rust生成C头文件

当Rust库需要被C代码调用时，cbindgen从Rust的`pub extern "C"`函数生成C头文件。

```bash
cargo install cbindgen
cbindgen --config cbindgen.toml --crate my_rust_lib --output my_rust_lib.h
```

Rust侧的导出函数：

```rust
#[no_mangle]
pub extern "C" fn rust_add(a: i32, b: i32) -> i32 {
    a + b
}

#[no_mangle]
pub extern "C" fn rust_process(data: *const u8, len: usize) -> i32 {
    if data.is_null() {
        return -1;
    }
    let slice = unsafe { std::slice::from_raw_parts(data, len) };
    slice.iter().map(|&x| x as i32).sum()
}
```

## 7. cxx与C++互操作

对于C++互操作，`cxx`库（以crates.io最新稳定版为准）提供了比原始`extern "C"`更安全、更符合C++语义的绑定方式。

```rust
// Rust侧
#[cxx::bridge]
mod ffi {
    // C++类型声明
    unsafe extern "C++" {
        include!("myapp/include/header.h");

        type MyCppClass;

        fn new_my_class() -> UniquePtr<MyCppClass>;
        fn process(&self, input: &CxxString) -> i32;
    }

    // Rust导出给C++的函数
    extern "Rust" {
        fn rust_callback(value: i32);
    }
}

fn rust_callback(value: i32) {
    println!("called from C++: {}", value);
}
```

cxx的优势：
- 支持C++的`std::string`、`std::vector`、`std::unique_ptr`等标准类型
- 支持C++类和方法（通过`UniquePtr<T>`或`&T`）
- 自动生成C++侧的绑定代码
- 类型安全：不需要手动处理裸指针

对照C++：C++调用Rust通常需要通过`extern "C"`函数指针回调，cxx把这种模式封装成了类型安全的接口。

## 8. static mut的安全替代

`static mut`是Rust中最危险的特性之一，因为它本质上是一个全局可变变量，在多线程环境下存在数据竞争。

```rust
// 不推荐：static mut
static mut COUNTER: i32 = 0;

// 推荐方案1：Atomic类型
use std::sync::atomic::{AtomicI32, Ordering};
static COUNTER: AtomicI32 = AtomicI32::new(0);

fn increment() {
    COUNTER.fetch_add(1, Ordering::SeqCst);
}

// 推荐方案2：OnceLock + Mutex（需要初始化的复杂状态）
use std::sync::{OnceLock, Mutex};
static CONFIG: OnceLock<Mutex<Config>> = OnceLock::new();

struct Config {
    port: u16,
}

fn get_config() -> &'static Mutex<Config> {
    CONFIG.get_or_init(|| Mutex::new(Config { port: 8080 }))
}

// 推荐方案3：thread_local（线程局部存储）
std::thread_local! {
    static THREAD_COUNTER: std::cell::Cell<i32> = std::cell::Cell::new(0);
}

fn thread_increment() {
    THREAD_COUNTER.with(|c| c.set(c.get() + 1));
}
```

| 方案 | 适用场景 | 线程安全 |
|------|----------|----------|
| `static mut` | 几乎不推荐 | 否，需要unsafe |
| `Atomic*` | 简单数值/布尔 | 是，无锁 |
| `OnceLock<Mutex<T>>` | 复杂全局状态 | 是，有锁 |
| `thread_local!` | 线程独立状态 | 是，无共享 |

## 9. 封装unsafe为安全API的原则

封装unsafe代码时，遵循以下原则：

### 原则1：最小unsafe范围

```rust
// 好：unsafe只包裹真正需要的操作
pub fn safe_function(data: &[u8]) -> &[u8] {
    let ptr = data.as_ptr();
    let len = data.len();
    // 其他安全操作...
    unsafe {
        std::slice::from_raw_parts(ptr, len)
    }
}

// 不好：整个函数体都在unsafe中
pub unsafe fn unsafe_function(data: &[u8]) -> &[u8] {
    let ptr = data.as_ptr();
    let len = data.len();
    std::slice::from_raw_parts(ptr, len)
}
```

### 原则2：在安全边界验证前置条件

```rust
pub fn from_raw_parts_safe<T>(ptr: *const T, len: usize) -> Option<&'static [T]> {
    // 安全边界：验证前置条件
    if ptr.is_null() || len == 0 {
        return None;
    }
    // 验证通过后才进入unsafe
    Some(unsafe { std::slice::from_raw_parts(ptr, len) })
}
```

### 原则3：用类型系统维护不变量

```rust
// 用类型标记保证指针非空
pub struct NonNull<T> {
    ptr: *mut T,
}

impl<T> NonNull<T> {
    pub fn new(ptr: *mut T) -> Option<Self> {
        if ptr.is_null() {
            None
        } else {
            Some(Self { ptr })
        }
    }

    pub fn as_ptr(&self) -> *mut T {
        self.ptr
    }
}

// 标准库已经提供了std::ptr::NonNull
```

### 原则4：文档化安全要求

```rust
/// 从裸指针创建一个&'static str
///
/// # Safety
///
/// 调用者必须保证：
/// - `ptr`非空且对齐
/// - `ptr`指向的内存包含有效的UTF-8数据
/// - 从`ptr`开始的`len`字节都在同一块已分配内存中
/// - 这块内存在'static生命周期内不会被释放或修改
pub unsafe fn from_raw_parts_str<'a>(ptr: *const u8, len: usize) -> &'a str {
    let bytes = std::slice::from_raw_parts(ptr, len);
    std::str::from_utf8_unchecked(bytes)
}
```

对照C++：C++没有"安全API"和"不安全API"的区分，所有操作都需要程序员自己保证安全。Rust的unsafe封装模式相当于把C++中"隐含的安全约定"变成了"显式的类型系统约束+文档化的安全要求"。

## 10. 本节小结

- **unsafe的五种能力**：解引用裸指针、调用unsafe函数、访问static mut、实现unsafe trait、访问union字段。unsafe不是关闭安全检查，而是程序员承诺维护安全不变量。
- **裸指针**`*const T`/`*mut T`不受借用检查器约束，创建是安全的，解引用需要unsafe。常用方法：`offset`/`add`/`read`/`write`/`is_null`。
- **transmute**是最强的类型转换，等价于C++的`reinterpret_cast`，应优先使用`to_bits`/`from_bits`等安全替代。
- **extern "C"**指定C ABI，声明外部函数需要unsafe调用。完整的mmap封装展示了"unsafe内部实现，安全外部API"的模式。
- **bindgen**从C头文件生成Rust绑定，**cbindgen**从Rust生成C头文件，**cxx**提供类型安全的C++互操作。
- **static mut**几乎不应使用，替代方案：`Atomic*`（简单值）、`OnceLock<Mutex<T>>`（复杂状态）、`thread_local!`（线程局部）。
- 封装unsafe的四原则：最小unsafe范围、安全边界验证前置条件、用类型系统维护不变量、文档化安全要求。无锁数据结构是unsafe的主要应用场景，对照《../../01-C++技术体系/13-并发异步与组件/06-无锁编程基础.md》理解裸指针与CAS的配合。

---

上一篇：《01-生命周期深入与高阶类型.md》
下一篇：《03-宏编程与编译期计算.md》
