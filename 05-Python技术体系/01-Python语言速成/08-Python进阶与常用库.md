# Python 进阶与常用库（中高级实战）

> 本节目标：面向已掌握 Python 基础脚本编写的学习者，深入讲解日常中大型工程中反复用到的中高级机制与高频库，包括数据模型/魔术方法、迭代器与生成器、装饰器、描述符与 OO 进阶、类型注解、collections/functools/itertools、并发进阶（线程/进程/协程）、Pythonic 写法与性能优化，以及按场景分类的常用第三方库。学完后能够在工程实践中运用 Python 中高级特性写出高效、可维护的代码。环境搭建、虚拟环境、subprocess、struct 协议解析与 C++ 互调见《07-Python脚本与自动化.md》，本文不重复。对照 C++ 理解：装饰器≈编译期/运行期包装、描述符≈受控成员、生成器≈可暂停的协程式迭代器、上下文管理器≈RAII。

## 本章速览

- [1. 数据模型：魔术方法（对应 C++ 运算符重载）](#1-数据模型魔术方法对应-c-运算符重载)
  - [1.1 dataclass：消灭样板代码（高频，强烈推荐）](#11-dataclass消灭样板代码高频强烈推荐)
- [2. 迭代器与生成器（惰性处理大数据的核心）](#2-迭代器与生成器惰性处理大数据的核心)
  - [2.1 迭代协议](#21-迭代协议)
  - [2.2 生成器表达式与 yield from](#22-生成器表达式与-yield-from)
  - [2.3 itertools：高频惰性工具（C++ 没有的瑞士军刀）](#23-itertools高频惰性工具c-没有的瑞士军刀)
- [3. 闭包、作用域与装饰器（中高级分水岭）](#3-闭包作用域与装饰器中高级分水岭)
  - [3.1 LEGB 作用域与 nonlocal](#31-legb-作用域与-nonlocal)
  - [3.2 装饰器原理（本质是"接收函数返回函数"的闭包 + 语法糖）](#32-装饰器原理本质是接收函数返回函数的闭包--语法糖)
  - [3.3 带参数的装饰器（三层嵌套）](#33-带参数的装饰器三层嵌套)
  - [3.4 标准库自带、工程里天天用的装饰器](#34-标准库自带工程里天天用的装饰器)
  - [3.5 类装饰器与可调用对象](#35-类装饰器与可调用对象)
- [4. 面向对象中高级](#4-面向对象中高级)
  - [4.1 property 与描述符（受控访问的底层）](#41-property-与描述符受控访问的底层)
  - [4.2 三种方法、__slots__、MRO](#42-三种方法__slots__mro)
  - [4.3 元类 metaclass（了解，99% 场景别用）](#43-元类-metaclass了解99-场景别用)
- [5. 类型注解进阶（中大型工程必备，配合 mypy）](#5-类型注解进阶中大型工程必备配合-mypy)
- [6. 三大"宝藏标准库"：collections / functools / itertools](#6-三大宝藏标准库collections--functools--itertools)
  - [6.1 collections（写业务最高频）](#61-collections写业务最高频)
  - [6.2 heapq / bisect（常被遗忘但面试/实战都用）](#62-heapq--bisect常被遗忘但面试实战都用)
  - [6.3 functools 其余高频](#63-functools-其余高频)
- [7. 并发进阶：线程 / 进程 / 协程怎么选](#7-并发进阶线程--进程--协程怎么选)
  - [7.1 决策表（和前篇呼应，这里讲用法）](#71-决策表和前篇呼应这里讲用法)
  - [7.2 线程同步与线程安全队列](#72-线程同步与线程安全队列)
  - [7.3 线程/进程池：concurrent.futures（比裸 Thread 简洁）](#73-线程进程池concurrentfutures比裸-thread-简洁)
  - [7.4 asyncio 协程进阶（高并发 IO 的主力）](#74-asyncio-协程进阶高并发-io-的主力)
  - [7.5 多进程](#75-多进程)
- [8. 高频标准库速查（写工程天天碰）](#8-高频标准库速查写工程天天碰)
  - [8.1 contextlib 两个高频用法](#81-contextlib-两个高频用法)
- [9. 高频第三方库（按场景，装了就能提效）](#9-高频第三方库按场景装了就能提效)
  - [9.1 pydantic v2 模型（配置/报文校验，工程化首选）](#91-pydantic-v2-模型配置报文校验工程化首选)
  - [9.2 FastAPI 给 C++ 后台套一个管理接口（很常见的组合）](#92-fastapi-给-c-后台套一个管理接口很常见的组合)
- [10. Pythonic 写法与性能优化](#10-pythonic-写法与性能优化)
  - [10.1 高频惯用法（更短更快更地道）](#101-高频惯用法更短更快更地道)
  - [10.2 性能优化清单（按收益排序）](#102-性能优化清单按收益排序)
- [11. 快速参考卡片](#11-快速参考卡片)
- [12. 常见问题与坑](#12-常见问题与坑)
- [13. 延伸阅读与官方资料](#13-延伸阅读与官方资料)

---

## 1. 数据模型：魔术方法（对应 C++ 运算符重载）

Python 对象的行为由双下划线方法（dunder）决定，相当于 C++ 重载运算符 + 编译器生成的特殊成员。**高频的就这些，别背全部。**

| 魔术方法 | 触发方式 | 对应 C++ 概念 |
| --- | --- | --- |
| `__init__` / `__new__` | 构造：`__new__` 造对象、`__init__` 初始化 | 构造函数 / operator new |
| `__repr__` / `__str__` | 调试表示 / `str()`、print | operator<< |
| `__len__` | `len(obj)` | size() |
| `__getitem__`/`__setitem__` | `obj[k]` | operator[] |
| `__iter__`/`__next__` | for 迭代、iter() | begin/end 迭代器协议 |
| `__enter__`/`__exit__` | `with` | RAII 构造/析构 |
| `__call__` | `obj()` | operator()（函数对象） |
| `__eq__`/`__lt__`/`__hash__` | `==`/排序/做 dict key | operator== / < / hash |

```python
class Range:
    """实现 __iter__/__getitem__ 后对象就能被 for、sum、切片、解包。"""
    def __init__(self, start, stop, step=1):
        self.start, self.stop, self.step = start, stop, step
    def __len__(self):
        return max(0, (self.stop - self.start + self.step - 1) // self.step)
    def __getitem__(self, i):                       # 支持 r[2]、for r in ...
        if i < 0 or i >= len(self): raise IndexError
        return self.start + i * self.step
    def __repr__(self):
        return f"Range({self.start},{self.stop},{self.step})"

print(list(Range(0, 10, 2)))     # [0,2,4,6,8]
```

> 定义了 `__eq__` 后默认 `__hash__` 会被置 None（对象变不可哈希、不能做 dict key），需要同时自定义 `__hash__`。这是常见坑。

### 1.1 dataclass：消灭样板代码（高频，强烈推荐）

相当于 C++ 的 POD/struct + 自动生成构造、比较、repr：

```python
from dataclasses import dataclass, field
from typing import ClassVar

@dataclass(order=True, frozen=False)   # order: 生成 </<= 比较；frozen: 不可变
class Device:
    addr: int                          # 类型注解即字段
    name: str = "unknown"
    tags: list = field(default_factory=list)   # 可变默认值必须用 default_factory
    count: ClassVar[int] = 0                  # 类变量，不算实例字段

d1 = Device(1, "gw-a"); d2 = Device(1, "gw-a")
print(d1 == d2)          # True：自动生成 __eq__
```

---

## 2. 迭代器与生成器（惰性处理大数据的核心）

### 2.1 迭代协议

- **可迭代对象 Iterable**：实现 `__iter__` 返回一个迭代器；
- **迭代器 Iterator**：实现 `__next__`（返回下一个，耗尽抛 `StopIteration`）且自身 `__iter__` 返回 self。

```python
class Countdown:
    def __init__(self, n): self.n = n
    def __iter__(self):
        cur = self.n
        while cur > 0:
            yield cur          # 有 yield 的函数就是生成器，自动实现迭代协议
            cur -= 1
# 生成器函数每次 next 执行到 yield 暂停并吐出值，下次从暂停处继续——状态被自动保存
```

### 2.2 生成器表达式与 yield from

```python
total = sum(x * x for x in range(1000000))   # 生成器表达式：不建中间 list，省内存
def flat(matrix):
    for row in matrix:
        yield from row        # 等价于 for x in row: yield x，委托子迭代器
```

### 2.3 itertools：高频惰性工具（C++ 没有的瑞士军刀）

| 工具 | 作用 | 例子 |
| --- | --- | --- |
| `chain(it1,it2)` | 串联多个可迭代对象，不拷贝 | `chain(range(3),"ab")` |
| `islice(it,start,stop,step)` | 惰性切片（大数据不能 `lst[::]`） | `islice(f,0,None,2)` |
| `groupby(it,key)` | 相邻按键分组（**通常先排序**） | 按首字母分组 |
| `count/cycle/repeat` | 无限计数/循环/重复 | 自增 id |
| `accumulate` | 前缀累加/累积 | 运行和 |
| `product/permutations/combinations` | 笛卡尔积/排列/组合 | 枚举参数组合 |
| `zip_longest` | 按最长对齐 zip | 缺的补 fillvalue |

```python
from itertools import chain, groupby, islice
rows = chain(load_part1(), load_part2())          # 多段数据当一条流处理
for k, g in groupby(sorted(data), key=lambda x: x[0]):
    print(k, list(g))                              # groupby 只分相邻，故先 sorted
```

> 生成器/迭代器**只能消费一次**，耗尽后再迭代为空；需要复用就转 list 或重建。

---

## 3. 闭包、作用域与装饰器（中高级分水岭）

### 3.1 LEGB 作用域与 nonlocal

查找顺序：Local → Enclosing（外层函数）→ Global → Built-in。闭包=内层函数捕获外层函数的变量（自由变量），延长其生命周期。

```python
def make_counter():
    n = 0
    def inc():
        nonlocal n        # 要修改外层变量必须声明 nonlocal（只读则不用）
        n += 1
        return n
    return inc
c = make_counter(); print(c(), c())   # 1 2
```

### 3.2 装饰器原理（本质是"接收函数返回函数"的闭包 + 语法糖）

```python
import time, functools

def timed(func):
    @functools.wraps(func)          # 保留原函数名/docstring，否则被 wrapper 覆盖
    def wrapper(*args, **kwargs):   # 透传任意参数
        t0 = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            print(f"{func.__name__} cost {time.perf_counter()-t0:.3f}s")
    return wrapper

@timed                              # 等价于 foo = timed(foo)
def foo(): ...
```

### 3.3 带参数的装饰器（三层嵌套）

```python
def retry(times=3):                       # 多一层接收装饰器参数
    def deco(func):
        @functools.wraps(func)
        def wrap(*a, **kw):
            for i in range(times):
                try: return func(*a, **kw)
                except Exception:
                    if i == times-1: raise
        return wrap
    return deco

@retry(times=5)                           # 先 retry(5) 得到真正装饰器
def call_remote(): ...
```

### 3.4 标准库自带、工程里天天用的装饰器

| 装饰器 | 作用 | 备注 |
| --- | --- | --- |
| `@functools.lru_cache(maxsize=128)` | 记忆化缓存返回值 | 递归 DP、重复计算；参数须可哈希 |
| `@functools.cache` | 无限 lru_cache（3.9+） | 等价 `lru_cache(maxsize=None)` |
| `@functools.cached_property` | 只算一次的属性缓存 | 惰性重计算属性 |
| `@functools.singledispatch` | 按第一个参数类型分派（函数版重载） | 替代一堆 if isinstance |
| `@property` | 方法变只读/受控属性 | 描述符，见第 4 章 |
| `@staticmethod/@classmethod` | 静态方法/类方法 | cls 传类，常用于工厂 |
| `@dataclass` | 生成样板 | 见 1.1 |

```python
from functools import singledispatch
@singledispatch
def to_json(x): raise TypeError(type(x))
@to_json.register             # 不同类型走不同实现，比 if-elif 干净
def _(x: int): return str(x)
@to_json.register
def _(x: list): return "[" + ",".join(to_json(i) for i in x) + "]"
```

### 3.5 类装饰器与可调用对象

用类实现装饰器适合需要维护状态的场景（计数、注册器）：

```python
class Registry:
    def __init__(self): self.table = {}
    def __call__(self, name):                 # 实例可当装饰器用
        def deco(cls):
            self.table[name] = cls
            return cls
        return deco
register = Registry()
@register("handler_a")
class HandlerA: ...
```

---

## 4. 面向对象中高级

### 4.1 property 与描述符（受控访问的底层）

`property` 本质是实现了 `__get__/__set__` 的**描述符**。理解描述符就能解释"为什么类属性访问会触发逻辑"（对应 C++ 里手写 getter/setter，但 Python 可后加且不破坏调用方）。

```python
class Celsius:
    def __init__(self, v=0.0): self._f = v * 9/5 + 32
    @property
    def c(self): return (self._f - 32) * 5/9     # 读：obj.c
    @c.setter
    def c(self, v):                              # 写：obj.c = v
        if v < -273.15: raise ValueError("低于绝对零度")
        self._f = v * 9/5 + 32
```

通用描述符（一次写、多个字段复用，做类型校验/单位转换）：

```python
class Typed:
    def __init__(self, typ): self.typ = typ
    def __set_name__(self, owner, name): self.name = "_" + name
    def __get__(self, obj, owner=None): return getattr(obj, self.name, None)
    def __set__(self, obj, val):
        if not isinstance(val, self.typ): raise TypeError(f"{self.name} 需要 {self.typ}")
        setattr(obj, self.name, val)
class Point:
    x = Typed(int); y = Typed(int)      # 描述符实例做类属性，复用校验逻辑
```

### 4.2 三种方法、__slots__、MRO

| 点 | 要点 |
| --- | --- |
| 实例/静态/类方法 | 实例方法首参 `self`（实例）；`@classmethod` 首参 `cls`（类，做**备选构造器**）；`@staticmethod` 两者都不要 |
| `__slots__` | 固定属性集合、**禁用 `__dict__`**，省内存（百万小对象明显）、防手滑加错属性；代价是不能动态加属性、多继承受限 |
| MRO/`super()` | 多继承按 **C3 线性化**确定方法查找顺序，`Cls.__mro__` 可看；`super()` 不是只调父类，而是按 MRO 找下一个，钻石继承靠它协作 |
| Mixin | 用小的功能类组合能力（如 `class LoggerMixin`），优先组合而非深继承 |
| ABC | `abc.ABC` + `@abstractmethod` 定义接口，禁止实例化未实现全部抽象方法的类（类似纯虚类） |

```python
class Point:
    __slots__ = ("x", "y")          # 实例不再有 __dict__，内存大幅下降
    def __init__(self, x, y): self.x, self.y = x, y
```

### 4.3 元类 metaclass（了解，99% 场景别用）

元类是"创建类的类"，能在类定义时改写它（注册、校验、自动加方法），ORM 框架（如 Django/SQLAlchemy 早期）用得多。日常用 `__init_subclass__`、类装饰器、描述符基本能替代，**除非写框架否则不要引入元类**（增加理解成本）。

---

## 5. 类型注解进阶（中大型工程必备，配合 mypy）

注解不影响运行，但 IDE 补全、静态查错、重构都靠它，C++ 工程师尤其应该用起来。

```python
from typing import (Optional, Union, Callable, Iterable, TypeVar, Generic,
                    TypedDict, Literal, overload, Any)

def find(uid: int) -> Optional[str]: ...          # 要么 str 要么 None
Handler = Callable[[int, str], bool]              # (int,str)->bool 的可调用
Mode = Literal["r", "w", "rb"]                    # 限定字面量取值

T = TypeVar("T", int, float)                      # 泛型类型变量，约束为数值
class Stack(Generic[T]):                          # 泛型类（类似 template<T>）
    def push(self, x: T) -> None: ...
    def pop(self) -> T: ...

class User(TypedDict):                            # 字典也有固定键类型
    id: int
    name: str

@overload                                         # 重载：按入参声明不同返回
def parse(x: str) -> str: ...
@overload
def parse(x: bytes) -> bytes: ...
def parse(x): return x.strip()
```

- `Protocol`：**结构化类型（鸭子类型的静态版）**，只要有某方法就满足，不必显式继承（类似 C++20 concept 的味道）。
- 工程建议：公开函数/库代码加注解并跑 `mypy --strict`（逐步收紧）；一次性脚本可从简。

---

## 6. 三大"宝藏标准库"：collections / functools / itertools

### 6.1 collections（写业务最高频）

| 类型 | 解决什么 | 典型用法 |
| --- | --- | --- |
| `defaultdict(factory)` | 访问不存在的 key 自动初始化 | 分组聚合，免 `if k not in d` |
| `Counter` | 计数/词频 | `Counter(lst).most_common(5)` |
| `deque` | 双端队列，**两端 O(1)**，可限长 | 队列/滑动窗口/固定长度历史 |
| `namedtuple` | 不可变、具名字段元组 | 轻量只读记录（也可用 dataclass(frozen)） |
| `OrderedDict` | 保序字典（普通 dict 3.7+ 已保序），另有 move_to_end | LRU |
| `ChainMap` | 逻辑合并多个 dict 不拷贝 | 多层配置（默认+环境+命令行） |

```python
from collections import defaultdict, Counter, deque
groups = defaultdict(list)
for dev in devices: groups[dev.zone].append(dev)      # 一行分组
top = Counter(word for line in lines for word in line.split()).most_common(10)
window = deque(maxlen=100)                            # 满了自动丢最旧，天然滑窗
```

### 6.2 heapq / bisect（常被遗忘但面试/实战都用）

```python
import heapq, bisect
heap = []; heapq.heappush(heap, 3); heapq.heappop(heap)   # 最小堆；TopK 用它
topk = heapq.nlargest(5, items, key=lambda x: x.score)
i = bisect.bisect_left(sorted_list, target)              # 有序表二分插入点 O(logn)
```

### 6.3 functools 其余高频

- `partial(f, x=1)`：固定部分参数得新函数（类似 std::bind）；
- `reduce(f, iter, init)`：归并；`cmp_to_key`：老式比较函数转排序 key。

---

## 7. 并发进阶：线程 / 进程 / 协程怎么选

### 7.1 决策表（和前篇呼应，这里讲用法）

| 场景 | 选择 | 原因 |
| --- | --- | --- |
| 大量等 IO（HTTP/磁盘/子进程） | **asyncio 协程**或 ThreadPool | 等待时让出，单线程可撑大量并发连接 |
| CPU 密集计算 | **ProcessPoolExecutor / multiprocessing** | 绕开 GIL 真并行 |
| 少量阻塞 IO、代码要简单 | ThreadPoolExecutor | 写法最直接 |
| 调用一个不支持 async 的阻塞库 | `loop.run_in_executor` | 把阻塞调用丢线程池，不堵事件循环 |

### 7.2 线程同步与线程安全队列

```python
import threading, queue
q = queue.Queue(maxsize=100)        # 线程安全的阻塞队列，内部已加锁
# Lock / RLock(可重入) / Event(一次性信号) / Semaphore(限流N个) / Condition
done = threading.Event()
def worker():
    while True:
        item = q.get()              # 空了自动阻塞，不用自己写条件变量
        if item is None: break
        process(item); q.task_done()
threading.Thread(target=worker, daemon=True).start()
```

### 7.3 线程/进程池：concurrent.futures（比裸 Thread 简洁）

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
with ThreadPoolExecutor(max_workers=8) as ex:
    futs = {ex.submit(fetch, url): url for url in urls}   # 提交任务
    for fut in as_completed(futs):                        # 谁先完成先处理
        url = futs[fut]
        try: print(url, fut.result(timeout=10))
        except Exception as e: print(url, "failed", e)    # 异常在 result 时抛出
```

### 7.4 asyncio 协程进阶（高并发 IO 的主力）

```python
import asyncio, aiohttp

async def fetch(session, url, sem):
    async with sem:                        # 信号量限制并发数，别一次打爆对端
        async with session.get(url, timeout=10) as r:
            return await r.text()

async def main(urls):
    sem = asyncio.Semaphore(20)
    async with aiohttp.ClientSession() as s:
        tasks = [asyncio.create_task(fetch(s, u, sem)) for u in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)  # 并发+不被单个异常中断
    return results
# asyncio.run(main(urls))
```

| API | 作用 |
| --- | --- |
| `async/await` | 定义/等待协程，await 点才会切换 |
| `create_task` | 立即调度协程为任务 |
| `gather` | 并发跑一批并收集结果（return_exceptions 防一颗老鼠屎） |
| `wait(return_when=FIRST_COMPLETED)` | 按条件等待 |
| `asyncio.Queue` | 协程间生产消费（无锁，单线程） |
| `Semaphore` | 协程并发限流 |
| `run_in_executor` | 阻塞库/CPU 小任务丢线程/进程池 |

> 协程里**绝不能直接调用阻塞函数**（`time.sleep`、同步 requests、重计算），否则整个事件循环卡死：等待用 `await asyncio.sleep`，阻塞 IO 换 aiohttp/httpx 异步版，重活丢 executor。

### 7.5 多进程

```python
from concurrent.futures import ProcessPoolExecutor
with ProcessPoolExecutor() as ex:          # 默认按 CPU 核数
    ex.map(cpu_heavy_func, big_list)       # 参数与返回通过 pickle 跨进程传递（须可序列化）
```

跨进程数据要序列化、内存不共享；超大共享数据用 `multiprocessing.shared_memory` 或初始化为全局一次（配合 initializer），避免每任务拷贝。

---

## 8. 高频标准库速查（写工程天天碰）

| 库 | 高频 API / 用途 |
| --- | --- |
| `pathlib` | `Path(__file__).parent / "a.txt"`，跨平台路径，替代 os.path 字符串拼接 |
| `datetime` | 统一用**时区感知**时间 `datetime.now(timezone.utc)`；`strftime/strptime`；别手算时间 |
| `logging` | `dictConfig` 用字典配置多 handler/分级/轮转（`RotatingFileHandler`），别再 print |
| `json` | `default=` 自定义序列化、`object_hook` 反序列化为对象；`ensure_ascii=False` 保中文 |
| `re` | 编译复用 `re.compile`；命名分组 `(?P<name>…)`；finditer 惰性 |
| `enum` | `class C(Enum)` / `IntEnum`，替代魔法数字 |
| `weakref` | 弱引用，做缓存不阻止对象被 GC，避免内存泄漏 |
| `operator` | itemgetter/attrgetter/methodcaller，配合 sorted/map |
| `io` | StringIO/BytesIO，内存文件流；TextIOWrapper 处理编码 |
| `shutil` | 拷贝/移动/删除目录树、磁盘用量 |
| `tempfile` | 安全临时文件/目录（用完自动清） |
| `contextlib` | `@contextmanager`、`suppress(异常)`、`ExitStack`（动态管理 N 个资源） |
| `copy` | 浅拷贝 copy vs 深拷贝 deepcopy（嵌套结构才需要深拷贝） |

### 8.1 contextlib 两个高频用法

```python
from contextlib import suppress, ExitStack
with suppress(FileNotFoundError):       # 安静地忽略指定异常，省 try/except
    os.remove("tmp")
with ExitStack() as stack:              # 数量在运行期才知道的多个资源统一管理
    files = [stack.enter_context(open(p)) for p in paths]
```

---

## 9. 高频第三方库（按场景，装了就能提效）

> 安装一律在激活的虚拟环境里 `pip install xxx`（环境见《07-Python脚本与自动化.md》）。

| 场景 | 首选库 | 说明 |
| --- | --- | --- |
| HTTP 客户端 | **requests**（同步）、**httpx**（同步+异步、HTTP2） | 接口调用、压测打流 |
| Web/API 服务 | **FastAPI**（异步、自带文档+类型校验，基于 pydantic）、Flask（轻量同步） | 给 C++ 服务套管理接口/原型 |
| 数据校验/配置 | **pydantic v2**（BaseModel 声明式校验）、pyyaml、tomllib(3.11+)、python-dotenv | 配置/报文模型 |
| 数值/表格 | **numpy / pandas** | 压测统计、日志分析（向量化，别写 for） |
| 命令行 CLI | **typer**（基于类型注解，最现代）/ click | 写正规工具 |
| 日志 | **loguru**（零配置、轮转、彩色） | 小项目替代 logging 样板 |
| 测试 | **pytest**（fixture/parametrize/mock） | 见《../07-调试与测试/05-单元测试与测试框架.md》思路 |
| 重试/限流 | **tenacity**（@retry 指数退避） | 网络调用健壮性 |
| 快速 JSON | **orjson/ujson** | 大报文解析比标准库快数倍 |
| 进度条 | **tqdm** | 长任务可视化 |
| 定时/调度 | APScheduler | 进程内定时任务 |
| 性能剖析 | cProfile（标准库）、line_profiler、py-spy（不侵入采样） | 定位热点 |
| 加速计算 | numba（@jit）、Cython、或下沉 C++/pybind11 | 热循环提速 |

### 9.1 pydantic v2 模型（配置/报文校验，工程化首选）

```python
from pydantic import BaseModel, Field, field_validator
class CollectorCfg(BaseModel):
    port: int = Field(ge=1, le=65535)           # 范围校验，越界直接报错
    hosts: list[str]
    timeout: float = 3.0
    @field_validator("hosts")
    @classmethod
    def non_empty(cls, v):
        if not v: raise ValueError("hosts 不能为空")
        return v
cfg = CollectorCfg.model_validate_json(raw)     # 非法配置在入口就被拦下
```

### 9.2 FastAPI 给 C++ 后台套一个管理接口（很常见的组合）

```python
from fastapi import FastAPI
from pydantic import BaseModel
app = FastAPI()
class Stats(BaseModel): conn: int; qps: float
@app.get("/stats", response_model=Stats)        # 类型注解自动校验+生成 OpenAPI 文档
def stats(): return query_engine_stats()        # 内部调用你的 C++ 库/共享内存/接口
# uvicorn main:app 启动；/docs 自动出交互式接口文档
```

---

## 10. Pythonic 写法与性能优化

### 10.1 高频惯用法（更短更快更地道）

```python
for i, v in enumerate(xs, start=1): ...         # 同时要下标和值，别 range(len)
for k, v in d.items(): ...
a, *mid, z = [1,2,3,4]                          # 解包：mid=[2,3]
d = {k: v for k, v in rows if v is not None}    # 推导式建字典
rev = xs[::-1]; chunk = xs[:100]
if 0 <= x < 100: ...                            # 链式比较，C++ 要写两个
x = maybe or default                            # 短路给默认（注意 0/"" 也为假，用 ?? 思路：x if x is not None else d）
match cmd:                                      # 3.10+ 结构化模式匹配，替代长 if-elif
    case "start": start()
    case ["set", key, val]: setv(key, val)
    case _: usage()
```

### 10.2 性能优化清单（按收益排序）

1. **先测量再优化**：`python -m cProfile -s cumtime app.py` 找热点，别凭感觉；
2. **用内置/向量化替代 Python 层循环**：推导式、`map/filter`、numpy/pandas 底层是 C；
3. **局部变量更快**：热循环里把全局/属性访问赋给局部变量；
4. **选对数据结构**：成员判断用 set/dict（O(1)）而非 list（O(n)）；deque 两端操作；heapq 做 TopK；
5. **省内存用生成器**：大文件/大序列逐项处理，不一次性建 list；海量小对象用 `__slots__`/dataclass；
6. **字符串拼接用 `"".join(list)`**，别在循环里 `+=`（不可变对象反复拷贝）；
7. **IO 并发、CPU 多进程**；纯 Python 热循环最后才考虑 numba/Cython/下沉 C++（见《07-Python脚本与自动化.md》第 7 章 pybind11）；
8. 缓存重复计算：`@functools.cache`/`lru_cache`（参数可哈希）。

```python
import cProfile, pstats, io
pr = cProfile.Profile(); pr.enable()
run_workload(); pr.disable()
pstats.Stats(pr).sort_stats("cumulative").print_stats(20)   # 累计耗时 Top20
```

---

## 11. 快速参考卡片

```text
数据模型：__init__/__repr__/__len__/__getitem__/__iter__/__enter__/__call__/__eq__
结构体：优先 @dataclass，可变默认值用 field(default_factory=list)
迭代：yield 生成器惰性省内存；yield from 委托；迭代器只消费一次
itertools：chain/islice/groupby(先sort)/accumulate/product
装饰器：闭包+语法糖；@functools.wraps 保元信息；带参三层；lru_cache/singledispatch
OO：property=描述符；__slots__省内存；super 按 MRO(C3)；Mixin 组合；元类尽量别用
注解：Optional/Callable/TypeVar泛型/Protocol/Literal/TypedDict，跑 mypy
collections：defaultdict分组、Counter计数、deque双端/滑窗、heapq TopK、bisect二分
并发：IO 用 asyncio/线程池，CPU 用进程池绕 GIL；协程里别调阻塞函数
asyncio：create_task + gather(return_exceptions) + Semaphore 限流 + run_in_executor
库：requests/httpx、FastAPI+pydantic、numpy/pandas、typer/loguru/tenacity/orjson/tqdm
性能：cProfile 先测 → 内置/向量化 → set 判存在 → 生成器/slots → join 拼串 → 下沉 C++
```

## 12. 常见问题与坑

| 问题 | 原因与解决 |
| --- | --- |
| 装饰后函数名变成 wrapper、文档丢失 | 没加 `@functools.wraps(func)` |
| 闭包/lambda 在循环里捕获的都是最后一个值 | **晚绑定**：用默认参数 `lambda x=x` 或立即绑定、或工厂函数固定 |
| 生成器第二次遍历是空的 | 迭代器一次性；重建生成器或转 list |
| `groupby` 结果不对 | 它只分**相邻**同键元素，先 `sorted` |
| 对象不能做 dict key / 报 unhashable | 定义 `__eq__` 后 `__hash__` 被清空，需同时实现或设为不可变 |
| dataclass 可变默认值报错/串数据 | 用 `field(default_factory=list)`，不要 `tags: list = []` |
| asyncio 里用 requests/time.sleep 整个卡住 | 阻塞了事件循环；换 httpx/aiohttp、`await asyncio.sleep`，重活 run_in_executor |
| 多进程任务函数报不能 pickle | 进程间靠 pickle 传参；函数要模块级可导入，lambda/闭包/局部函数不行 |
| `from copy import copy` 改了嵌套层仍互相影响 | 浅拷贝只拷外层；嵌套结构用 `deepcopy` |
| 时间处理出现 naive/aware 混用报错 | 统一用带时区的 UTC 时间，展示层再转本地 |
| 多线程计数结果不对 | GIL 不保证 `x+=1` 原子（读-改-写三步）；用 `threading.Lock` 或 `itertools.count`/atomic 思路 |
| 字典/集合在遍历时删除报错 | 遍历时收集待删 key，循环外再删；或遍历副本 `list(d.items())` |
| 注解写了但运行照样传错类型 | 注解运行期不强制；要拦截用 pydantic 或 mypy 静态检查 |

---

## 13. 延伸阅读与官方资料

- Python 官方教程（进阶：数据模型/类/迭代器）：[docs.python.org/zh-cn/3/tutorial](https://docs.python.org/zh-cn/3/tutorial/)
- 数据模型（全部魔术方法权威定义）：[docs.python.org/3/reference/datamodel.html](https://docs.python.org/3/reference/datamodel.html)
- 标准库：itertools [docs.python.org/3/library/itertools.html](https://docs.python.org/3/library/itertools.html)、functools [docs.python.org/3/library/functools.html](https://docs.python.org/3/library/functools.html)、collections [docs.python.org/3/library/collections.html](https://docs.python.org/3/library/collections.html)、asyncio [docs.python.org/3/library/asyncio.html](https://docs.python.org/3/library/asyncio.html)、concurrent.futures [docs.python.org/3/library/concurrent.futures.html](https://docs.python.org/3/library/concurrent.futures.html)
- 类型注解 typing：[docs.python.org/3/library/typing.html](https://docs.python.org/3/library/typing.html)；mypy：[mypy.readthedocs.io](https://mypy.readthedocs.io/)
- pydantic v2：[docs.pydantic.dev](https://docs.pydantic.dev/)；FastAPI：[fastapi.tiangolo.com](https://fastapi.tiangolo.com/)；httpx：[python-httpx.org](https://www.python-httpx.org/)
- 《Python Cookbook（第 3 版）》：中高级惯用法最对味的一本书；性能剖析 cProfile：[docs.python.org/3/library/profile.html](https://docs.python.org/3/library/profile.html)
- 与本知识库联动：环境/工程化/subprocess/struct/C++ 互调见《07-Python脚本与自动化.md》，单测见《../07-调试与测试/05-单元测试与测试框架.md》，C++ 侧线程/内存序见《../04-并发编程/04-原子操作与C++内存模型.md》。

---

上一篇：《07-Python脚本与自动化.md》　｜　模块索引：《../README.md》
