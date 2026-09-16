# Trait 抽象与泛型编程

> 本节目标：掌握 Rust 的 trait 定义与实现、泛型编程与单态化机制、trait bound 与 where 子句、关联类型与泛型参数的取舍、`dyn trait` 对象与对象安全、`impl Trait` 语法、孤儿规则与运算符重载，熟练运用标准库核心 trait，建立与 C++ 虚函数/Concepts 的深度对照。

## 本章速览

- [1. trait 定义与默认方法](#1-trait-定义与默认方法)
  - [1.1 trait 定义与实现](#11-trait-定义与实现)
  - [1.2 默认方法](#12-默认方法)
  - [1.3 trait 作为参数](#13-trait-作为参数)
- [2. 泛型编程与单态化](#2-泛型编程与单态化)
  - [2.1 泛型函数与泛型结构体](#21-泛型函数与泛型结构体)
  - [2.2 单态化：静态分发](#22-单态化静态分发)
  - [2.3 trait bound 与 where 子句](#23-trait-bound-与-where-子句)
- [3. 关联类型 vs 泛型参数](#3-关联类型-vs-泛型参数)
- [4. dyn trait 对象与动态分发](#4-dyn-trait-对象与动态分发)
  - [4.1 对象安全规则](#41-对象安全规则)
  - [4.2 trait 对象的内存布局](#42-trait-对象的内存布局)
- [5. impl Trait 语法](#5-impl-trait-语法)
- [6. 孤儿规则与 trait 实现限制](#6-孤儿规则与-trait-实现限制)
- [7. 运算符重载](#7-运算符重载)
- [8. 标准库必学 trait](#8-标准库必学-trait)
  - [8.1 Display / Debug](#81-display--debug)
  - [8.2 Clone / Copy](#82-clone--copy)
  - [8.3 From / Into / TryFrom](#83-from--into--tryfrom)
  - [8.4 Deref / DerefMut](#84-deref--derefmut)
  - [8.5 Iterator / IntoIterator](#85-iterator--intoiterator)
  - [8.6 Default / Sized](#86-default--sized)
- [9. 对照 C++：虚函数 / Concepts](#9-对照-c虚函数--concepts)
- [10. 综合示例：泛型缓存系统](#10-综合示例泛型缓存系统)
- [11. 快速参考卡片](#11-快速参考卡片)
- [12. 常见坑与编译错误](#12-常见坑与编译错误)
  - [错误 1：the trait bound `T: Trait` is not satisfied](#错误-1the-trait-bound-t-trait-is-not-satisfied)
  - [错误 2：cannot infer type for type parameter](#错误-2cannot-infer-type-for-type-parameter)
  - [错误 3：the trait `Trait` is not implemented for `&T`](#错误-3the-trait-trait-is-not-implemented-for-t)
  - [错误 4：method `method` cannot be called on trait object](#错误-4method-method-cannot-be-called-on-trait-object)
- [13. 本节小结](#13-本节小结)

---

## 1. trait 定义与默认方法

### 1.1 trait 定义与实现

trait 定义了一组方法签名，是 Rust 中实现"接口"和"多态"的核心机制：

```rust
// trait 定义：描述"可以被摘要"的行为
trait Summarizable {
    fn summary(&self) -> String;  // 方法签名，无默认实现
}

// 为具体类型实现 trait
struct Article {
    title: String,
    author: String,
    content: String,
}

impl Summarizable for Article {
    fn summary(&self) -> String {
        format!("{} by {}", self.title, self.author)
    }
}

struct Tweet {
    username: String,
    content: String,
}

impl Summarizable for Tweet {
    fn summary(&self) -> String {
        format!("{}: {}", self.username, self.content)
    }
}

fn main() {
    let article = Article {
        title: String::from("Rust 101"),
        author: String::from("Alice"),
        content: String::from("..."),
    };
    let tweet = Tweet {
        username: String::from("bob"),
        content: String::from("Hello Rust!"),
    };

    println!("{}", article.summary());
    println!("{}", tweet.summary());
}
```

> **对照 C++**：trait 类似于 C++ 的抽象基类（纯虚函数），但有关键差异：(1) trait 可以为**外部类型**实现（只要 trait 或类型在当前 crate 中定义），C++ 中不能为已有的类添加新的基类；(2) Rust 没有继承，trait 不包含数据字段，只能定义方法；(3) trait 方法可以有默认实现，C++ 虚函数也可以有默认实现但需要在基类中定义。

### 1.2 默认方法

trait 中的方法可以有默认实现，实现该 trait 时可以选择覆盖或使用默认：

```rust
trait Greet {
    fn name(&self) -> String;

    // 默认方法：可以调用 trait 中的其他方法
    fn greet(&self) -> String {
        format!("Hello, {}!", self.name())
    }

    // 默认方法也可以不依赖其他方法
    fn farewell(&self) -> String {
        String::from("Goodbye!")
    }
}

struct Person { name: String }

impl Greet for Person {
    fn name(&self) -> String {
        self.name.clone()
    }
    // greet 和 farewell 使用默认实现，无需手动实现
}

struct Robot { id: u32 }

impl Greet for Robot {
    fn name(&self) -> String {
        format!("Robot-{}", self.id)
    }

    // 覆盖默认实现
    fn greet(&self) -> String {
        format!("BEEP BOOP. Unit {} online.", self.id)
    }
}

fn main() {
    let person = Person { name: String::from("Alice") };
    let robot = Robot { id: 42 };

    println!("{}", person.greet());  // Hello, Alice!
    println!("{}", robot.greet());   // BEEP BOOP. Unit 42 online.
    println!("{}", person.farewell()); // Goodbye!
}
```

### 1.3 trait 作为参数

```rust
// 方式1：impl Trait 语法（简洁，适用于简单情况）
fn notify(item: &impl Summarizable) {
    println!("Breaking news! {}", item.summary());
}

// 方式2：trait bound（等价于方式1，但更灵活）
fn notify<T: Summarizable>(item: &T) {
    println!("Breaking news! {}", item.summary());
}

// 多个 trait bound
fn notify_and_debug<T: Summarizable + std::fmt::Debug>(item: &T) {
    println!("{:?}: {}", item, item.summary());
}

// where 子句：当 trait bound 复杂时更清晰
fn some_function<T, U>(t: &T, u: &U)
where
    T: Summarizable + Clone,
    U: Clone + std::fmt::Debug,
{
    // ...
}
```

## 2. 泛型编程与单态化

### 2.1 泛型函数与泛型结构体

```rust
// 泛型函数：返回两个值中较大的一个
fn largest<T: PartialOrd>(list: &[T]) -> &T {
    let mut largest = &list[0];
    for item in list {
        if item > largest {
            largest = item;
        }
    }
    largest
}

// 泛型结构体
struct Point<T> {
    x: T,
    y: T,
}

// 泛型结构体的多类型参数
struct Pair<T, U> {
    first: T,
    second: U,
}

// 泛型枚举
enum Result<T, E> {
    Ok(T),
    Err(E),
}

// 为泛型结构体实现方法
impl<T> Point<T> {
    fn x(&self) -> &T {
        &self.x
    }
}

// 仅为特定类型实现方法
impl Point<f64> {
    fn distance_from_origin(&self) -> f64 {
        (self.x.powi(2) + self.y.powi(2)).sqrt()
    }
}

// 泛型 impl 中的混合类型
impl<T, U> Pair<T, U> {
    fn mixup<V, W>(self, other: Pair<V, W>) -> Pair<T, W> {
        Pair {
            first: self.first,
            second: other.second,
        }
    }
}

fn main() {
    let numbers = vec![34, 50, 25, 100, 65];
    println!("largest = {}", largest(&numbers)); // 100

    let chars = vec!['y', 'm', 'a', 'q'];
    println!("largest = {}", largest(&chars)); // y

    let p = Point { x: 5, y: 10 };
    let p2 = Point { x: 1.0, y: 2.0 };
    println!("distance = {}", p2.distance_from_origin());
}
```

### 2.2 单态化：静态分发

Rust 的泛型采用**单态化**（monomorphization）——编译时为每个具体类型生成专用代码，实现零成本抽象：

```rust
// 源码中的泛型函数
fn largest<T: PartialOrd>(list: &[T]) -> &T { /* ... */ }

// 编译后单态化为两个具体函数（概念上）：
// fn largest_i32(list: &[i32]) -> &i32 { /* ... */ }
// fn largest_char(list: &[char]) -> &char { /* ... */ }
```

单态化的特点：
- **零运行时开销**：与手写具体类型函数性能相同
- **编译时间增加**：每个类型组合生成一份代码
- **二进制体积增大**：多份代码副本
- **静态分发**：调用在编译期确定，无虚函数表查找开销

> **对照 C++**：Rust 的单态化与 C++ 模板实例化完全相同。C++ `template<typename T> T largest(const std::vector<T>&)` 会为每个 `T` 生成实例。关键差异：Rust 的 trait bound 在定义处检查（"早检查"），C++ 模板在实例化处检查（"晚检查"），导致 C++ 模板错误信息往往冗长且指向实例化点而非模板定义。C++20 Concepts 改善了这一点，与 Rust trait bound 类似。

### 2.3 trait bound 与 where 子句

```rust
use std::fmt::Display;

// 直接在泛型参数上写 bound
fn print_pair<T: Display, U: Display>(t: T, u: U) {
    println!("{}, {}", t, u);
}

// where 子句：当 bound 复杂时更易读
fn complex_function<T, U, V>(t: T, u: U, v: V) -> String
where
    T: Display + Clone,
    U: Display + std::fmt::Debug,
    V: IntoIterator<Item = T>,
{
    format!("{}, {:?}, count={}", t, u, v.into_iter().count())
}

// 返回类型中的 trait bound
fn returns_summarizable() -> impl Summarizable {
    Article {
        title: String::from("Test"),
        author: String::from("Author"),
        content: String::from("..."),
    }
}
```

## 3. 关联类型 vs 泛型参数

关联类型（associated type）是 trait 中声明的类型占位符，由实现者指定具体类型：

```rust
// 关联类型：trait 中有一个关联类型 Item
pub trait Iterator {
    type Item;  // 关联类型声明
    fn next(&mut self) -> Option<Self::Item>;
}

// 实现时指定关联类型
struct Counter {
    count: u32,
}

impl Iterator for Counter {
    type Item = u32;  // 指定关联类型为 u32

    fn next(&mut self) -> Option<Self::Item> {
        self.count += 1;
        if self.count < 6 {
            Some(self.count)
        } else {
            None
        }
    }
}

// 对比：用泛型参数实现同样的功能
pub trait IteratorGeneric<T> {
    fn next(&mut self) -> Option<T>;
}

// 泛型版本：一个类型可以为不同 T 实现多次
impl IteratorGeneric<u32> for Counter { /* ... */ }
impl IteratorGeneric<String> for Counter { /* ... */ } // 可以！

// 关联类型版本：一个类型只能实现一次（因为 Item 唯一确定）
// impl Iterator for Counter { type Item = u32; ... }
// impl Iterator for Counter { type Item = String; ... } // 编译错误！
```

| 维度 | 关联类型 | 泛型参数 |
|---|---|---|
| 实现次数 | 每个类型只能实现一次 | 每个类型可以为不同参数实现多次 |
| 使用时标注 | 不需要标注（`impl Iterator`） | 需要标注（`impl IteratorGeneric<u32>`） |
| 适用场景 | 类型唯一确定（如迭代器的 Item） | 类型可以有多种（如 From<T>） |
| 标准库例子 | `Iterator::Item`、`Deref::Target` | `From<T>`、`Into<T>` |

> **选择原则**：如果一个类型对于该 trait 来说是唯一的（如迭代器只能产生一种元素），用关联类型；如果一个类型可以有多种合理实现（如 `From<T>` 可以从多种类型转换），用泛型参数。

## 4. dyn trait 对象与动态分发

当需要在运行时存储不同类型但实现了同一 trait 的值时，使用 **trait 对象**（`dyn Trait`）：

```rust
trait Drawable {
    fn draw(&self);
}

struct Circle { radius: f64 }
struct Square { side: f64 }

impl Drawable for Circle {
    fn draw(&self) { println!("Drawing circle with radius {}", self.radius); }
}

impl Drawable for Square {
    fn draw(&self) { println!("Drawing square with side {}", self.side); }
}

fn main() {
    // trait 对象：Vec<Box<dyn Drawable>> 可以存储不同类型
    let shapes: Vec<Box<dyn Drawable>> = vec![
        Box::new(Circle { radius: 5.0 }),
        Box::new(Square { side: 10.0 }),
    ];

    for shape in &shapes {
        shape.draw();  // 动态分发：运行时通过 vtable 查找方法
    }

    // 函数参数接受 trait 对象
    fn draw_all(shapes: &[Box<dyn Drawable>]) {
        for s in shapes {
            s.draw();
        }
    }
}
```

### 4.1 对象安全规则

不是所有 trait 都可以作为 trait 对象。**对象安全**（object safe）的 trait 必须满足：

1. 方法不能返回 `Self`（因为 Self 的具体类型在运行时未知）
2. 方法不能有泛型参数（因为无法为所有可能的类型生成 vtable 条目）
3. trait 不能包含 `Sized` 约束（`Self: Sized` 的方法可以有，但不能通过 trait 对象调用）

```rust
// 不安全的 trait（不能作为 dyn trait）
trait NotObjectSafe {
    fn new() -> Self;           // 违反规则1：返回 Self
    fn generic<T>(&self, x: T); // 违反规则2：泛型参数
}

// 安全的 trait
trait ObjectSafe {
    fn method(&self);           // OK
    fn with_self(self) where Self: Sized; // OK（有 Sized 约束，不能通过 trait 对象调用）
}
```

### 4.2 trait 对象的内存布局

`dyn Trait` 是一个**胖指针**（fat pointer），包含两个指针：
- **数据指针**：指向实际数据
- **vtable 指针**：指向虚函数表（包含方法指针、drop 函数、大小、对齐等）

```text
Box<dyn Drawable> (16 字节，64位平台)
├── data ptr ──→ Circle { radius: 5.0 }  (堆上)
└── vtable ptr → vtable for Circle as Drawable
                  ├── draw: fn(&Circle)
                  ├── drop: fn(*mut Circle)
                  ├── size: 8
                  └── align: 8
```

> **对照 C++**：`dyn Trait` 等价于 C++ 的虚基类指针/引用。C++ 中每个有虚函数的对象内部包含一个 vptr（虚表指针），指向 vtable。Rust 的 trait 对象将 vptr 外置（胖指针的一部分），数据本身不需要 vptr，这意味着可以为外部类型实现 trait 而不改变其内存布局。C++ 中不能为已有类添加虚函数（需要修改类定义）。

| 维度 | 静态分发（泛型 + trait bound） | 动态分发（dyn trait） |
|---|---|---|
| 性能 | 零开销，编译期确定调用 | vtable 间接调用，微小开销 |
| 类型擦除 | 保留具体类型 | 擦除具体类型，只保留 trait 接口 |
| 存储异构类型 | 不能（`Vec<T>` 只能存一种 T） | 可以（`Vec<Box<dyn Trait>>`） |
| 对象安全 | 无限制 | 必须满足对象安全规则 |
| 编译时间 | 较长（单态化） | 较短 |
| 二进制体积 | 较大（多份代码） | 较小 |
| C++ 对应 | 模板/Concepts（编译期多态） | 虚函数/继承（运行期多态） |

## 5. impl Trait 语法

`impl Trait` 有两种使用位置：参数位置和返回位置。

```rust
// 参数位置：等价于泛型 + trait bound（静态分发）
fn process(item: impl Iterator<Item = u32>) -> u32 {
    item.sum()
}
// 等价于：
// fn process<T: Iterator<Item = u32>>(item: T) -> u32 { item.sum() }

// 返回位置：返回实现了 trait 的具体类型，但隐藏具体类型
fn make_iterator() -> impl Iterator<Item = u32> {
    vec![1, 2, 3].into_iter().map(|x| x * 2)
}

// 返回 impl Trait 的限制：函数中所有返回路径必须是同一个具体类型
// fn maybe_iterator(flag: bool) -> impl Iterator<Item = u32> {
//     if flag {
//         vec![1, 2, 3].into_iter()  // 类型1
//     } else {
//         (0..10).into_iter()         // 类型2，编译错误！
//     }
// }

// 解决方法：返回 trait 对象（动态分发）
fn maybe_iterator(flag: bool) -> Box<dyn Iterator<Item = i32>> {
    if flag {
        Box::new(vec![1, 2, 3].into_iter())
    } else {
        Box::new(0..10)
    }
}
```

`impl Trait` 在返回位置的重要用途是**返回闭包**（闭包类型是匿名的，无法显式写出）：

```rust
fn make_adder(x: i32) -> impl Fn(i32) -> i32 {
    move |y| x + y
}

fn main() {
    let add5 = make_adder(5);
    println!("{}", add5(3)); // 8
}
```

## 6. 孤儿规则与 trait 实现限制

**孤儿规则**（orphan rule）：要为类型 `T` 实现 trait `Tr`，必须满足 `Tr` 或 `T` 至少有一个是在当前 crate 中定义的。不能为外部类型实现外部 trait。

```rust
// 假设 serde::Serialize 和 std::vec::Vec 都是外部定义的
// 不能在自己的 crate 中为 Vec<T> 实现 Serialize（两者都是外部的）
// impl<T> serde::Serialize for Vec<T> { ... } // 编译错误

// 可以：为自己定义的类型实现外部 trait
#[derive(serde::Serialize)]
struct MyType { field: i32 }

// 可以：为外部类型实现自己定义的 trait
trait MyTrait { fn my_method(&self); }
impl MyTrait for Vec<i32> {
    fn my_method(&self) { /* ... */ }
}
```

> **对照 C++**：C++ 没有孤儿规则，可以为任何类型在任何命名空间中添加函数（ADL 查找），但这也导致了"谁都能扩展"的混乱。Rust 的孤儿规则保证了 trait 实现的一致性——不会出现两个 crate 为同一类型实现同一 trait 导致冲突的情况。如果确实需要为外部类型实现外部 trait，使用 **newtype 模式**（用元组结构体包装外部类型）。

```rust
// newtype 模式：绕过孤儿规则
use std::fmt;

struct Wrapper(Vec<String>);  // 包装外部类型 Vec<String>

impl fmt::Display for Wrapper {  // 为自己的类型实现外部 trait
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "[{}]", self.0.join(", "))
    }
}
```

## 7. 运算符重载

Rust 通过 trait 实现运算符重载，每个运算符对应一个标准库 trait：

```rust
use std::ops::{Add, Sub, Mul, Deref, DerefMut};

#[derive(Debug, Clone, Copy)]
struct Complex {
    real: f64,
    imag: f64,
}

impl Complex {
    fn new(real: f64, imag: f64) -> Self {
        Complex { real, imag }
    }
}

// 重载 + 运算符
impl Add for Complex {
    type Output = Complex;

    fn add(self, other: Complex) -> Complex {
        Complex {
            real: self.real + other.real,
            imag: self.imag + other.imag,
        }
    }
}

// 重载 - 运算符
impl Sub for Complex {
    type Output = Complex;
    fn sub(self, other: Complex) -> Complex {
        Complex {
            real: self.real - other.real,
            imag: self.imag - other.imag,
        }
    }
}

// 重载 * 运算符
impl Mul for Complex {
    type Output = Complex;
    fn mul(self, other: Complex) -> Complex {
        Complex {
            real: self.real * other.real - self.imag * other.imag,
            imag: self.real * other.imag + self.imag * other.real,
        }
    }
}

fn main() {
    let a = Complex::new(1.0, 2.0);
    let b = Complex::new(3.0, 4.0);
    println!("{:?}", a + b);  // Complex { real: 4.0, imag: 6.0 }
    println!("{:?}", a * b);  // Complex { real: -5.0, imag: 10.0 }
}
```

常用运算符 trait：

| 运算符 | trait | 运算符 | trait |
|---|---|---|---|
| `+` | `Add` | `+=` | `AddAssign` |
| `-` | `Sub` | `-=` | `SubAssign` |
| `*` | `Mul` | `*=` | `MulAssign` |
| `/` | `Div` | `/=` | `DivAssign` |
| `%` | `Rem` | `%=` | `RemAssign` |
| `&` | `BitAnd` | `\|` | `BitOr` |
| `^` | `BitXor` | `<<` | `Shl` |
| `>>` | `Shr` | `!` | `Not` |
| `*` (解引用) | `Deref` | `[]` (索引) | `Index` |
| `()` (调用) | `Fn/FnMut/FnOnce` | `<`/`>` | `PartialOrd` |

> **对照 C++**：C++ 通过成员函数或全局函数重载运算符（`operator+`），Rust 通过 trait 实现。关键差异：Rust 不能重载任意运算符（只能重载标准库 trait 对应的运算符），也不能改变运算符的优先级和结合性。C++ 可以重载大部分运算符但也有相同限制。Rust 的运算符重载是 trait 的自然应用，更统一。

## 8. 标准库必学 trait

### 8.1 Display / Debug

```rust
use std::fmt;

struct Point { x: i32, y: i32 }

// Debug：面向开发者的调试输出，可用 #[derive(Debug)] 自动生成
#[derive(Debug)]
struct PointDerived { x: i32, y: i32 }

// Display：面向最终用户的格式化输出，必须手动实现
impl fmt::Display for Point {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "({}, {})", self.x, self.y)
    }
}

fn main() {
    let p = Point { x: 1, y: 2 };
    println!("{}", p);       // Display: (1, 2)
    println!("{:?}", p);     // 编译错误：Point 没有实现 Debug

    let pd = PointDerived { x: 1, y: 2 };
    println!("{:?}", pd);    // Debug: PointDerived { x: 1, y: 2 }
    println!("{:#?}", pd);   // 美化 Debug 输出
}
```

| trait | 用途 | 自动派生 | 输出格式 |
|---|---|---|---|
| `Debug` | 调试输出 | `#[derive(Debug)]` | `{:?}` / `{:#?}` |
| `Display` | 用户友好输出 | 不能 | `{}` |

### 8.2 Clone / Copy

（详见《03-所有权借用与生命周期.md》，此处简要回顾）

- `Clone`：显式 `.clone()` 深拷贝，可派生
- `Copy`：隐式位拷贝，要求所有字段都是 Copy，可派生，实现 Copy 必须实现 Clone

### 8.3 From / Into / TryFrom

```rust
struct Number { value: i32 }

// From<T>：从 T 转换为 Self
impl From<i32> for Number {
    fn from(value: i32) -> Self {
        Number { value }
    }
}

// Into<T> 由 From 自动实现（标准库有 blanket impl）
// impl Into<Number> for i32 { ... } // 自动获得

// TryFrom/TryInto：可能失败的转换
use std::convert::TryFrom;

impl TryFrom<Number> for u32 {
    type Error = &'static str;
    fn try_from(n: Number) -> Result<Self, Self::Error> {
        if n.value >= 0 {
            Ok(n.value as u32)
        } else {
            Err("negative number")
        }
    }
}

fn main() {
    let n1 = Number::from(42);       // From
    let n2: Number = 42.into();      // Into（由 From 自动获得）

    let n3 = Number { value: -1 };
    match u32::try_from(n3) {
        Ok(v) => println!("{}", v),
        Err(e) => println!("error: {}", e), // error: negative number
    }

    // 标准库中的 From/Into
    let s: String = "hello".into();  // &str -> String
    let s2 = String::from("hello");  // 等价
}
```

> **设计原则**：优先实现 `From` 而非 `Into`，因为 `Into` 会由标准库自动实现。`?` 运算符会自动调用 `From` 进行错误类型转换，这是错误处理的核心机制，详见《06-错误处理工程化.md》。

### 8.4 Deref / DerefMut

```rust
use std::ops::{Deref, DerefMut};

struct MyBox<T>(T);

impl<T> MyBox<T> {
    fn new(x: T) -> Self { MyBox(x) }
}

impl<T> Deref for MyBox<T> {
    type Target = T;
    fn deref(&self) -> &Self::Target {
        &self.0
    }
}

impl<T> DerefMut for MyBox<T> {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.0
    }
}

fn main() {
    let mut b = MyBox::new(5);
    println!("{}", *b);  // 解引用：*(b.deref()) = 5
    *b += 1;              // 可变解引用：*(b.deref_mut()) += 1
    println!("{}", *b);   // 6

    // Deref coercion：函数参数自动解引用
    fn take_str(s: &str) { println!("{}", s); }
    let s = MyBox::new(String::from("hello"));
    take_str(&s);  // &MyBox<String> → &String → &str（自动解引用链）
}
```

Deref coercion 规则：当 `T: Deref<Target=U>` 时，`&T` 自动转换为 `&U`。可以链式发生（`&Box<String>` → `&String` → `&str`）。这是 Rust 中智能指针和引用透明性的基础。

### 8.5 Iterator / IntoIterator

（详见《07-集合迭代器与闭包.md》，此处简要说明）

- `Iterator`：定义 `next()` 方法，产生 `Option<Self::Item>`，是所有迭代器的核心 trait
- `IntoIterator`：将类型转换为迭代器，`for` 循环自动调用 `into_iter()`
- `FromIterator`：从迭代器收集为集合，`collect()` 方法的基础

### 8.6 Default / Sized

```rust
struct Config {
    host: String,
    port: u16,
    timeout: u32,
}

// 手动实现 Default
impl Default for Config {
    fn default() -> Self {
        Config {
            host: String::from("localhost"),
            port: 8080,
            timeout: 30,
        }
    }
}

fn main() {
    let config = Config::default();
    // 部分字段自定义，其余用默认
    let custom = Config {
        port: 9090,
        ..Config::default()
    };
}
```

`Sized` 是一个特殊的标记 trait，表示类型在编译期大小已知。几乎所有类型都自动实现 `Sized`。`?Sized` 表示"可能是动态大小类型"（如 `str`、`[T]`、`dyn Trait`），用于泛型约束中放宽大小要求：

```rust
// 默认泛型参数有隐式 Sized 约束
fn foo<T>(t: T) { /* T: Sized 隐式 */ }

// 允许动态大小类型（只能通过引用/指针使用）
fn foo_unsized<T: ?Sized>(t: &T) { /* T 可以是 str, [u8], dyn Trait */ }
```

## 9. 对照 C++：虚函数 / Concepts

| 维度 | Rust trait | C++ 虚函数（继承） | C++20 Concepts |
|---|---|---|---|
| 多态类型 | 静态（泛型）+ 动态（dyn） | 动态（虚函数） | 静态（模板） |
| 接口定义 | trait 定义方法签名 | 抽象基类纯虚函数 | concept 定义约束 |
| 实现方式 | `impl Trait for Type` | 类继承基类并覆写 | 模板参数满足 concept |
| 外部类型扩展 | 可以（孤儿规则内） | 不能（不能修改已有类的基类） | 可以（任何类型都可用于模板） |
| 数据字段 | trait 不能包含字段 | 基类可以包含字段 | 不涉及 |
| 默认实现 | 支持（默认方法） | 支持（虚函数有实现） | 不涉及 |
| 编译期检查 | trait bound 在定义处检查 | 虚函数在运行时检查 | concept 在定义处检查 |
| 运行时开销 | 静态分发零开销，动态分发 vtable | vtable 间接调用 | 零开销（模板实例化） |
| 错误信息 | 清晰（指向 trait 定义） | 运行时才发现 | C++20 前冗长，C++20 后改善 |
| 多重继承 | 通过组合多个 trait bound | 支持多重继承（复杂、有菱形问题） | 不涉及 |

> **核心差异**：Rust 的 trait 是"接口优先"的设计——trait 只定义行为，不包含数据，通过组合（而非继承）实现多态。C++ 的面向对象是"类优先"的设计——类同时包含数据和行为，通过继承实现多态，导致了菱形继承、对象切片等复杂问题。Rust 的 trait 系统更接近 Go 的 interface 或 Haskell 的 typeclass，是更现代的抽象机制。

## 10. 综合示例：泛型缓存系统

```rust
use std::collections::HashMap;
use std::hash::Hash;
use std::fmt::Debug;

// 泛型缓存：键 K，值 V
struct Cache<K, V> {
    map: HashMap<K, V>,
    capacity: usize,
}

impl<K: Eq + Hash + Clone + Debug, V: Clone + Debug> Cache<K, V> {
    fn new(capacity: usize) -> Self {
        Cache {
            map: HashMap::new(),
            capacity,
        }
    }

    fn get(&self, key: &K) -> Option<&V> {
        self.map.get(key)
    }

    fn insert(&mut self, key: K, value: V) -> Option<V> {
        if self.map.len() >= self.capacity && !self.map.contains_key(&key) {
            // 简单策略：移除第一个键（实际应用中用 LRU）
            if let Some(first_key) = self.map.keys().next().cloned() {
                self.map.remove(&first_key);
            }
        }
        self.map.insert(key, value)
    }

    fn len(&self) -> usize {
        self.map.len()
    }
}

// trait：可缓存的计算
trait Computable {
    type Input;
    type Output;
    fn compute(&self, input: &Self::Input) -> Self::Output;
}

// 泛型函数：带缓存的计算
fn cached_compute<C, K, V>(
    cache: &mut Cache<K, V>,
    computable: &C,
    input: K,
) -> V
where
    C: Computable<Input = K, Output = V>,
    K: Eq + Hash + Clone + Debug,
    V: Clone + Debug,
{
    if let Some(result) = cache.get(&input) {
        return result.clone();
    }
    let result = computable.compute(&input);
    cache.insert(input, result.clone());
    result
}

// 具体实现：斐波那契计算
struct Fibonacci;

impl Computable for Fibonacci {
    type Input = u64;
    type Output = u64;

    fn compute(&self, input: &u64) -> u64 {
        match input {
            0 => 0,
            1 => 1,
            n => {
                let mut a = 0;
                let mut b = 1;
                for _ in 2..=*n {
                    let temp = a + b;
                    a = b;
                    b = temp;
                }
                b
            }
        }
    }
}

fn main() {
    let mut cache = Cache::new(10);
    let fib = Fibonacci;

    println!("fib(10) = {}", cached_compute(&mut cache, &fib, 10)); // 55
    println!("fib(20) = {}", cached_compute(&mut cache, &fib, 20)); // 6765
    println!("fib(10) cached = {}", cached_compute(&mut cache, &fib, 10)); // 55（命中缓存）
    println!("cache size = {}", cache.len()); // 2
}
```

## 11. 快速参考卡片

| 查询点 | 速答 |
| --- | --- |
| 定义与实现 | `trait Speak { fn s(&self) -> String; }` / `impl Speak for Dog { fn s(&self) -> String { .. } }` |
| 默认方法 | trait 内可给默认实现，类型可覆写或不写 |
| 泛型 vs dyn | 泛型走单态化（零成本，代码膨胀）；`dyn Trait` 动态分发（vtable，一个间接指针开销） |
| bound 三种写法 | `fn f<T: Clone>(t: T)`、`where T: Clone + Debug`、`impl Trait` 参数/返回 |
| 关联类型 vs 泛型参数 | `trait Add { type Output; }`：一个类型只能实现一次；泛型参数版可多次实现 |
| 对象安全（可用 dyn） | 方法不能有泛型参数、不能返回 `Self`（`Box<Self>` 可以）、不能是关联函数 |
| 孤儿规则 | `impl` 只能写在 trait 或类型所在的 crate 内 → 外部类型用 newtype 包装后再实现 |
| 常用可 derive trait | Debug、Clone、Copy、PartialEq/Eq、PartialOrd/Ord、Hash、Default |
| supetrait | `trait A: B`：实现 A 必须先实现 B |
| 静态分发选型 | 单态化优先；需要在集合中存异构对象或减少编译时间时用 `Box<dyn Trait>` |

---

## 12. 常见坑与编译错误

### 错误 1：the trait bound `T: Trait` is not satisfied

```text
error[E0277]: the trait bound `T: MyTrait` is not satisfied
```
**原因**：泛型函数要求 T 实现某个 trait，但调用时传入的类型没有实现。**修复**：为类型实现 trait，或调整 trait bound。

### 错误 2：cannot infer type for type parameter

```text
error[E0282]: type annotations needed
```
**原因**：泛型类型参数无法从上下文推导。**修复**：显式标注类型或使用 turbofish `::<>`。

### 错误 3：the trait `Trait` is not implemented for `&T`

```text
error[E0277]: `&T` doesn't implement `Trait`
```
**原因**：为 T 实现了 trait，但传入的是 &T。**修复**：为 &T 也实现 trait（blanket impl），或调整函数参数为 `&impl Trait`。

### 错误 4：method `method` cannot be called on trait object

```text
error: the `method` method cannot be invoked on a trait object
```
**原因**：trait 对象调用了不满足对象安全的方法（如返回 Self、有泛型参数）。**修复**：给方法加 `where Self: Sized` 约束，或改用泛型静态分发。

## 13. 本节小结

- **trait** 是 Rust 的接口定义机制，支持默认方法，可以为外部类型实现（孤儿规则内）。与 C++ 抽象基类类似但更灵活，没有继承和数据字段。
- **泛型编程**通过单态化实现零成本抽象，trait bound 在定义处检查（早检查），错误信息比 C++ 模板清晰。
- **关联类型**用于类型唯一确定的场景（如 `Iterator::Item`），泛型参数用于类型可多种的场景（如 `From<T>`）。
- **dyn trait** 实现运行时多态（动态分发），通过胖指针（数据指针 + vtable 指针）实现，必须满足对象安全规则。
- **impl Trait** 在参数位置等价于泛型（静态分发），在返回位置隐藏具体类型，是返回闭包的必要手段。
- **孤儿规则**保证 trait 实现的一致性，newtype 模式可绕过限制。
- **运算符重载**通过标准库 trait 实现（`Add`、`Deref` 等），是 trait 的自然应用。
- **标准库核心 trait**：`Display`/`Debug`（格式化）、`Clone`/`Copy`（复制）、`From`/`Into`/`TryFrom`（转换）、`Deref`（解引用与 coercion）、`Iterator`（迭代）、`Default`（默认值）、`Sized`（大小标记）。
- **与 C++ 对照**：Rust trait 系统是"接口优先、组合优于继承"的现代设计，比 C++ 的"类+继承+虚函数"更简洁、更安全，同时支持静态和动态两种分发方式。

---

上一篇：《04-结构体枚举与模式匹配.md》　｜　下一篇：《06-错误处理工程化.md》　｜　模块索引：《../README.md》
