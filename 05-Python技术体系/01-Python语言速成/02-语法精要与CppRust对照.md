# 语法精要与CppRust对照

> 本节目标：从C++/Rust的值语义世界观切换到Python的引用语义世界观，掌握缩进、变量、数字、字符串、容器、切片、推导式、控制流等核心语法，并通过对照示例建立"看到C++/Rust写法就能想到Python等价写法"的条件反射。

## 本章速览

- [1. 工程场景：为什么语法差异会导致隐蔽bug](#1-工程场景为什么语法差异会导致隐蔽bug)
- [2. 缩进与表达式风格](#2-缩进与表达式风格)
- [3. 变量即引用：最核心的心智模型切换](#3-变量即引用最核心的心智模型切换)
  - [3.1 值语义vs引用语义](#31-值语义vs引用语义)
  - [3.2 is与==](#32-is与)
  - [3.3 可变与不可变](#33-可变与不可变)
  - [3.4 函数传参本质](#34-函数传参本质)
- [4. 数字：整除与浮点陷阱](#4-数字整除与浮点陷阱)
- [5. 字符串与字节：str/bytes/编码](#5-字符串与字节strbytes编码)
- [6. 容器：list/tuple/dict/set](#6-容器listtupledictset)
  - [6.1 list与tuple](#61-list与tuple)
  - [6.2 dict与set](#62-dict与set)
  - [6.3 复杂度与选型](#63-复杂度与选型)
- [7. 切片与推导式](#7-切片与推导式)
- [8. 控制流与for-else](#8-控制流与for-else)
- [9. C++/Rust→Python写法对照表](#9-crustpython写法对照表)
- [10. 常见坑](#10-常见坑)
- [11. 本节小结](#11-本节小结)

---

## 1. 工程场景：为什么语法差异会导致隐蔽bug

C++/Rust工程师写Python时最容易犯的错误不是语法错误，而是**基于值语义的想当然导致的隐蔽bug**：传入list被函数内部修改、用`==`比较身份、`a = b`后修改a发现b也变了。本节的核心目标是建立正确的Python心智模型，而非死记语法规则。

## 2. 缩进与表达式风格

Python用缩进定义代码块，不用花括号。约定4个空格，禁止Tab与空格混用。

```python
def parse_packet(data: bytes) -> dict:
    if len(data) < 4:
        raise ValueError("报文太短")
    return {"header": data[:4], "payload": data[4:]}
```

表达式与语句有明确区分：表达式有返回值（`1+2`、`a if cond else b`、`lambda`），语句没有（`if/for/def/class`）。Python 3.8+支持海象运算符`:=`在表达式中赋值。

```python
if (n := len(data)) > 100:
    print(f"数据过长: {n}")

# 多行语句用括号隐式续行（推荐），不用反斜杠
total = (item1 + item2 + item3)
```

## 3. 变量即引用：最核心的心智模型切换

### 3.1 值语义vs引用语义

这是整个Python语法中最重要的概念。

**C++值语义**：变量就是对象，赋值是拷贝。
```cpp
std::vector<int> a = {1,2,3};
std::vector<int> b = a;  // 拷贝，独立对象
b.push_back(4);           // 不影响a
```

**Rust值语义**：赋值默认移动（非Copy类型），`.clone()`才是深拷贝。

**Python引用语义**：变量是对象的标签，赋值是贴标签。
```python
a = [1, 2, 3]
b = a          # b和a指向同一个list！
b.append(4)
print(a)       # [1, 2, 3, 4] —— a也变了
print(a is b)  # True
```

正确复制方式：
```python
b = a.copy()           # 浅拷贝
c = list(a)            # 浅拷贝
d = a[:]               # 浅拷贝
import copy; e = copy.deepcopy(a)  # 深拷贝（嵌套结构）
```

### 3.2 is与==

- `==`：值相等，调用`__eq__`。对应C++`operator==`、Rust`PartialEq`。
- `is`：身份相等，比较内存地址（`id()`）。对应C++比较指针是否相同。

```python
a = [1, 2, 3]
b = [1, 2, 3]
print(a == b)   # True（值相等）
print(a is b)   # False（不同对象）
```

**工程规则**：比较值用`==`（99%场景）；比较`None`必须用`is None`（PEP 8）；永远不要用`is`比较整数或字符串（小整数缓存可能导致意外结果）。

### 3.3 可变与不可变

| 不可变 | 可变 |
|--------|------|
| int, float, str, bytes, tuple, frozenset | list, dict, set, 自定义类实例 |

不可变对象一旦创建不能修改，所谓"修改"是创建新对象。可变对象可以原地修改。

```python
s = "hello"
s = s.upper()   # 创建新字符串"HELLO"，原对象被GC

lst = [1, 2]
lst.append(3)   # 原地修改
```

### 3.4 函数传参本质

Python传参是**传递对象引用**（call by sharing），既不是C++的值传递也不是引用传递。

```python
def modify_list(lst: list) -> None:
    lst.append(4)      # 原地修改可变对象，影响外部
    lst = [1, 2]       # 重新绑定局部变量，不影响外部

def modify_int(x: int) -> None:
    x = x + 1          # int不可变，创建新对象绑定局部变量

a = [1, 2, 3]
modify_list(a)
print(a)               # [1, 2, 3, 4]

b = 10
modify_int(b)
print(b)               # 10（不变）
```

**规则**：可变对象的原地修改影响外部；不可变对象的"修改"不影响外部；函数内重新赋值永远不影响外部。

## 4. 数字：整除与浮点陷阱

Python的`int`是任意精度，不会溢出。`/`总是返回`float`，`//`是地板除（向下取整）。

```python
print(7 / 2)     # 3.5（float）
print(7 // 2)    # 3（地板除）
print(-7 // 2)   # -4（向下取整！C++是向零取整得-3）
print(-7 % 2)    # 1（取模结果符号与除数一致）
```

C++对照：C++整数除法向零取整（`-7/2=-3`），Python向下取整（`-7//2=-4`）。需要C++行为时用`int(-7/2)`。

浮点精度陷阱与C++`double`相同（IEEE 754）：
```python
print(0.1 + 0.2)        # 0.30000000000000004
import math
print(math.isclose(0.1 + 0.2, 0.3))  # True（正确比较方式）
from decimal import Decimal
print(Decimal("0.1") + Decimal("0.2"))  # 0.3（精确十进制）
```

## 5. 字符串与字节：str/bytes/编码

Python 3的`str`是Unicode字符串（每个字符是一个码点），`bytes`是原始字节序列。这与C++`std::string`（字节序列）和Rust`String`（UTF-8字节）都不同。

```python
s = "你好"
print(len(s))        # 2（字符数，不是字节数）

b = s.encode("utf-8")           # str→bytes
print(b)                         # b'\xe4\xbd\xa0\xe5\xa5\xbd'（6字节）
print(s == b.decode("utf-8"))   # True

# bytes索引返回整数，不是字符
print(b[0])         # 228
```

`bytes`不可变，需要修改时用`bytearray`。网络/文件/报文处理中必须明确编码解码。

```python
# 报文解析：前2字节长度（大端）+文本
def parse_text(data: bytes, encoding: str = "utf-8") -> str:
    length = int.from_bytes(data[:2], "big")
    return data[2:2+length].decode(encoding)
```

字符串常用操作：`split()`/`join()`/`find()`/`replace()`/`strip()`/`upper()`/`startswith()`/f-string格式化。

```python
parts = "a,b,c".split(",")       # ["a","b","c"]
joined = "-".join(parts)          # "a-b-c"
name, temp = "device-01", 36.5
print(f"{name}: {temp:.1f}°C")   # device-01: 36.5°C
```

## 6. 容器：list/tuple/dict/set

### 6.1 list与tuple

`list`对应C++`std::vector`、Rust`Vec`，动态数组，随机访问O(1)，尾部追加O(1)摊销。

```python
lst = [1, 2, 3]
lst.append(4)        # 尾部追加
lst.insert(0, 0)     # 指定位置插入（O(n)）
lst.pop()            # 弹出尾部
lst.remove(2)        # 删除第一个值为2的元素
print(2 in lst)      # 成员测试（O(n)）
lst.sort()           # 原地排序
lst.reverse()        # 原地反转
```

`tuple`是不可变list，单元素必须带逗号`(42,)`。支持解包和多返回值。

```python
a, b, c = (1, 2, 3)   # 解包
a, b = b, a            # 交换变量（无需临时变量）

def get_coords() -> tuple[int, int]:
    return 10, 20      # 等价return (10, 20)
x, y = get_coords()
```

### 6.2 dict与set

`dict`对应C++`std::unordered_map`、Rust`HashMap`，哈希表，平均O(1)查找。Python 3.7+保持插入顺序。

```python
d = {"name": "GW-01", "port": 8080}
d["ip"] = "192.168.1.1"     # 插入/更新
print(d.get("mac", "N/A"))   # 带默认值的查找
print("name" in d)            # O(1)成员测试
del d["port"]                 # 删除
for k, v in d.items():        # 遍历键值对
    print(k, v)

# 计数与分组的标准模式
from collections import defaultdict
counts = defaultdict(int)
for proto in ["TCP", "UDP", "TCP"]:
    counts[proto] += 1
```

`set`对应C++`std::unordered_set`、Rust`HashSet`，O(1)成员测试，元素唯一。

```python
s = {1, 2, 3}
s.add(4)
print(3 in s)         # O(1)
a, b = {1,2,3}, {3,4,5}
print(a | b)          # 并集 {1,2,3,4,5}
print(a & b)          # 交集 {3}
print(a - b)          # 差集 {1,2}
```

### 6.3 复杂度与选型

| 操作 | list | dict | set |
|------|------|------|-----|
| 索引/键访问 | O(1) | O(1)平均 | 不支持 |
| 成员测试`in` | O(n) | O(1)平均 | O(1)平均 |
| 尾部追加 | O(1)摊销 | N/A | O(1)平均 |
| 删除 | O(n) | O(1)平均 | O(1)平均 |

**选型规则**：按索引访问用list；键值对映射用dict；去重/O(1)成员测试用set；固定不可变、可哈希做dict key用tuple。

## 7. 切片与推导式

切片`seq[start:stop:step]`是序列操作的瑞士军刀。

```python
lst = [0,1,2,3,4,5,6,7,8,9]
print(lst[2:5])     # [2,3,4]（不包含stop）
print(lst[:5])      # [0,1,2,3,4]
print(lst[::2])     # [0,2,4,6,8]（步长2）
print(lst[::-1])    # [9,8,...,0]（反转）
print(lst[-3:])     # [7,8,9]（最后3个）
print(lst[:])       # 整个序列的浅拷贝
```

推导式一行搞定过滤+转换，是Pythonic代码的标志。

```python
# list推导式
squares = [x**2 for x in range(10)]
evens = [x for x in range(20) if x % 2 == 0]

# dict推导式
square_map = {x: x**2 for x in range(5)}

# set推导式
unique_lens = {len(w) for w in ["hello", "hi", "hey"]}

# 生成器表达式（惰性，不占内存）
gen = (x**2 for x in range(1000000))
```

工程场景——从日志行提取ERROR时间戳：
```python
error_times = [
    line.split()[1]
    for line in log_lines
    if "ERROR" in line
]
```

## 8. 控制流与for-else

```python
# if-elif-else
if score >= 90: grade = "A"
elif score >= 60: grade = "B"
else: grade = "F"

# for遍历可迭代对象
for i in range(5): print(i)
for idx, val in enumerate(["a","b","c"]): print(idx, val)
for k, v in {"x":1}.items(): print(k, v)

# while
while count < 3: count += 1
```

**for-else**：循环正常结束（没有break）时执行else块，搜索场景中替代`found`标志变量。

```python
def find_device(devices: list, target: str) -> bool:
    for dev in devices:
        if dev["name"] == target:
            print(f"找到: {target}")
            return True
    else:
        print(f"未找到: {target}")  # 循环遍历完都没break时执行
        return False
```

## 9. C++/Rust→Python写法对照表

| 场景 | C++ | Rust | Python |
|------|-----|------|--------|
| 变量声明 | `int x = 42;` | `let x = 42;` | `x = 42` |
| 打印 | `std::cout << x;` | `println!("{}", x);` | `print(x)` |
| 格式化 | `fmt::format("{}", v);` | `format!("{}", v);` | `f"{v}"` |
| 动态数组 | `std::vector<int>{1,2,3}` | `vec![1,2,3]` | `[1, 2, 3]` |
| 追加 | `v.push_back(4);` | `v.push(4);` | `v.append(4)` |
| 长度 | `v.size();` | `v.len()` | `len(v)` |
| 哈希表 | `std::unordered_map<K,V>` | `HashMap::new()` | `{}` |
| 插入键值 | `m["k"] = 1;` | `m.insert("k", 1);` | `m["k"] = 1` |
| 安全查找 | `m.find(k)!=m.end()` | `m.contains_key(k)` | `"k" in m` |
| 带默认取值 | `m.count(k)?m[k]:def` | `m.get(k).unwrap_or(def)` | `m.get(k, def)` |
| 哈希集合 | `std::unordered_set<int>` | `HashSet::new()` | `set()` |
| 成员测试 | `s.count(x)>0` | `s.contains(&x)` | `x in s` |
| 分割/连接 | boost::split / accumulate | `split`/`join` | `split`/`join` |
| 遍历 | `for(auto& x:v)` | `for x in &v` | `for x in v:` |
| 带索引遍历 | 手动维护idx | `iter().enumerate()` | `enumerate(v)` |
| 排序 | `std::sort(...)` | `v.sort();` | `v.sort()` |
| 过滤+转换 | copy_if+transform | `filter().map().collect()` | 推导式 |
| 函数定义 | `int add(int a,int b){...}` | `fn add(a:i32,b:i32)->i32{...}` | `def add(a,b):...` |
| 返回多值 | struct/pair/out参数 | `return (a,b);` | `return a, b` |
| 异常 | throw/try-catch | Result/match | raise/try-except |
| 文件读取 | `std::ifstream` | `fs::read_to_string` | `open().read()` |
| 命令行参数 | argc, argv | `env::args()` | `sys.argv` |
| 休眠 | `sleep_for(1s)` | `sleep(Duration::from_secs(1))` | `time.sleep(1)` |
| 类型转换 | `static_cast<int>(x)` | `x as i32` | `int(x)` |
| 范围循环 | `for(int i=0;i<n;++i)` | `for i in 0..n` | `for i in range(n):` |
| 交换变量 | `std::swap(a,b);` | `mem::swap(&mut a,&mut b);` | `a, b = b, a` |
| 深拷贝 | 拷贝构造 | `.clone()` | `copy.deepcopy(x)` |

## 10. 常见坑

**坑1：可变默认参数**
```python
# 错误：默认参数在定义时求值一次，所有调用共享
def add_item(item, lst=[]):
    lst.append(item); return lst
# 正确：用None做哨兵
def add_item(item, lst=None):
    if lst is None: lst = []
    lst.append(item); return lst
```

**坑2：循环变量泄漏**
```python
for i in range(3): pass
print(i)  # 2 —— Python的for循环变量泄漏到外部作用域
```

**坑3：整数缓存导致is比较异常**
```python
a, b = 256, 256
print(a is b)   # True（CPython缓存-5到256）
a, b = 257, 257
print(a is b)   # False —— 永远用==比较整数
```

**坑4：循环中+拼接字符串（O(n²)）**
```python
# 错误
result = ""
for s in large_list: result += s
# 正确：join是O(n)
result = "".join(large_list)
```

**坑5：dict遍历时修改**
```python
# 错误：遍历时删除key会RuntimeError
# 正确：先收集要删除的key
to_del = [k for k, v in d.items() if v == 2]
for k in to_del: del d[k]
```

## 11. 本节小结

- **引用语义是核心**：变量是对象的标签，`a = b`不是拷贝。需要复制用`.copy()`或`copy.deepcopy()`。
- **is vs ==**：比较值用`==`，比较`None`用`is None`，不要用`is`比较数字/字符串。
- **可变/不可变**：list/dict/set可变，int/str/tuple/bytes不可变。函数传参传递对象引用，可变对象的原地修改影响外部。
- **数字**：`/`返回float，`//`地板除（负数与C++行为不同）；int不溢出；float比较用`math.isclose`。
- **str vs bytes**：str是Unicode字符串，bytes是原始字节。网络/报文处理必须明确编码解码。
- **容器选型**：list（有序可重复）、tuple（不可变）、dict（键值对O(1)）、set（去重O(1)成员测试）。
- **切片与推导式**：切片是序列操作利器，推导式一行搞定过滤+转换，生成器表达式惰性不占内存。
- **for-else**：搜索场景替代`found`标志，循环正常结束时执行else。

---

上一篇：《01-环境工具链与运行模型.md》
下一篇：《03-函数模块与包.md》
