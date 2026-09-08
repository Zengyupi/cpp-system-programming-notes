# STL 容器与算法

> 本节目标：掌握 STL 容器的底层数据结构与选型决策——vector 的连续存储与扩容、deque 的中控数组、list 的双向链表、关联容器的红黑树、无序容器的哈希表；理解迭代器失效的精确规则与复杂度权衡；熟练运用排序、查找、集合运算等常用算法及 erase-remove 惯用法。学完能根据访问模式与性能特征选择正确容器，并避免迭代器失效等典型坑。前置《01-语言基础与类型系统.md》，关联《04-内存管理与智能指针.md》的 RAII 与《05-模板与泛型编程.md》的迭代器萃取。

## 本章速览

- [1. 概述](#1-概述)
  - [1.1 STL 六大组件](#11-stl-六大组件)
  - [1.2 与 C 手写数据结构的对比](#12-与-c-手写数据结构的对比)
- [2. 容器分类总览](#2-容器分类总览)
  - [2.1 序列容器（元素顺序 = 插入顺序）](#21-序列容器元素顺序--插入顺序)
  - [2.2 关联容器（有序，红黑树实现——主流实现事实标准）](#22-关联容器有序红黑树实现主流实现事实标准)
  - [2.3 无序关联容器（C++11，哈希表）](#23-无序关联容器c11哈希表)
  - [2.4 容器适配器（不是完整容器，包装既有容器）](#24-容器适配器不是完整容器包装既有容器)
- [3. 容器速查对比大表](#3-容器速查对比大表)
  - [3.1 序列容器](#31-序列容器)
  - [3.2 关联/无序容器](#32-关联无序容器)
  - [3.3 三个必须理解的底层机制](#33-三个必须理解的底层机制)
- [4. 选型决策：按场景选容器](#4-选型决策按场景选容器)
- [5. 迭代器失效规则（重中之重）](#5-迭代器失效规则重中之重)
  - [5.1 失效规则总表](#51-失效规则总表)
  - [5.2 安全删除惯用法](#52-安全删除惯用法)
  - [5.3 与失效相关的经典事故](#53-与失效相关的经典事故)
- [6. 常用算法分类](#6-常用算法分类)
  - [6.1 查找](#61-查找)
  - [6.2 排序与整理](#62-排序与整理)
  - [6.3 变换与数值](#63-变换与数值)
  - [6.4 删除：remove-erase 惯用法（必懂）](#64-删除remove-erase-惯用法必懂)
  - [6.5 集合操作（输入必须有序）](#65-集合操作输入必须有序)
- [7. 算法 + lambda 实战片段](#7-算法--lambda-实战片段)
- [8. string 补充](#8-string-补充)
  - [8.1 SSO（小字符串优化）](#81-sso小字符串优化)
  - [8.2 数值转换](#82-数值转换)
- [9. 快速参考卡片](#9-快速参考卡片)
- [10. 常见问题与坑](#10-常见问题与坑)

---

## 1. 概述

### 1.1 STL 六大组件

| 组件 | 作用 | 代表 |
|---|---|---|
| 容器（Container） | 组织和存储数据 | `vector`、`map`、`unordered_map` |
| 算法（Algorithm） | 与容器解耦的通用操作 | `sort`、`find`、`accumulate` |
| 迭代器（Iterator） | 容器与算法之间的粘合剂（统一遍历接口） | `begin()`/`end()`，五类迭代器 |
| 仿函数（Functor） | 行为像函数的对象，提供操作策略 | lambda、`std::greater<int>` |
| 适配器（Adapter） | 改装既有组件的接口 | `stack`、`queue`、`priority_queue`、`std::bind` |
| 分配器（Allocator） | 定制容器的内存来源 | `std::allocator`（默认）、内存池分配器 |

**核心设计思想（泛型编程）**：算法不认识容器，只认识迭代器。`std::sort` 既能排 vector 也能排原生数组——数据与操作通过"一段可遍历的区间"解耦。

### 1.2 与 C 手写数据结构的对比

| 维度 | C 手写 | STL |
|---|---|---|
| 内存管理 | 手工 malloc/realloc/free | 容器自管（RAII） |
| 正确性 | 边界/释放 bug 高发 | 迭代器失效规则需要学，但可推理 |
| 复用 | 每个项目一套链表 | 一次学习处处使用 |
| 性能 | 理论可极致优化 | 高度优化的模板代码，通常更快（内联） |

## 2. 容器分类总览

### 2.1 序列容器（元素顺序 = 插入顺序）

| 容器 | 底层结构 | 核心特点 |
|---|---|---|
| `vector` | 动态数组（连续内存） | 随机访问 O(1)，尾部操作均摊 O(1)，**默认首选** |
| `array`（C++11） | 定长数组（栈/全局，聚合类型） | 零开销替代 C 数组，带 size()、可拷贝 |
| `deque` | 分段连续（中控 map + 定长块） | 两端 O(1)，中间 O(n)，随机访问 O(1)（两级寻址） |
| `list` | 双向链表 | 任意位置 O(1) 插删（已知位置），splice O(1)，无随机访问 |
| `forward_list`（C++11） | 单向链表 | 比 list 更省内存（每节点 1 指针），设计目标是最小空间开销 |

### 2.2 关联容器（有序，红黑树实现——主流实现事实标准）

| 容器 | 特点 |
|---|---|
| `set` / `multiset` | 有序不重复 / 有序可重复集合 |
| `map` / `multimap` | 有序键值对 / 一键多值；遍历按 key 升序 |
| 共同特征 | 插入/删除/查找均 O(log n)；迭代器按序遍历；**键是 const 的** |

### 2.3 无序关联容器（C++11，哈希表）

| 容器 | 特点 |
|---|---|
| `unordered_set` / `unordered_multiset` | 哈希集合 |
| `unordered_map` / `unordered_multimap` | 哈希键值表 |
| 共同特征 | 均摊 O(1) 查找/插删，最坏 O(n)（哈希冲突/被恶意构造）；无序遍历；rehash 使迭代器失效 |

### 2.4 容器适配器（不是完整容器，包装既有容器）

| 适配器 | 默认底层 | 语义 |
|---|---|---|
| `stack` | deque | LIFO 栈：push/pop/top |
| `queue` | deque | FIFO 队列：push/pop/front/back |
| `priority_queue` | vector + 堆算法 | 优先级队列：top 为最大（可换比较器） |

```cpp
std::priority_queue<int, std::vector<int>, std::greater<int>> pq;  // 小顶堆
```

## 3. 容器速查对比大表

### 3.1 序列容器

| 容器 | 随机访问 | 头部插/删 | 中间插/删 | 尾部插/删 | 查找(无序) | 迭代器稳定性 | 内存特点 |
|---|---|---|---|---|---|---|---|
| `vector` | O(1) | O(n) | O(n) | 均摊 O(1) | O(n) | 扩容全失效 | 连续、缓存最友好；扩容按倍率（实现定义：libstdc++/libc++ 2 倍，MSVC 1.5 倍） |
| `array` | O(1) | — | — | — | O(n) | 无失效（不可变长） | 栈上，零分配 |
| `deque` | O(1) | O(1) | O(n) | O(1) | O(n) | 两端插入仅迭代器失效（引用不失效）；中间全失效 | 分段连续；头部插入不用搬移全部元素 |
| `list` | 无 | O(1) | O(1)（已持有迭代器） | O(1) | O(n) | 仅被删元素失效 | 每节点 2 指针 + 前驱后继，缓存不友好 |
| `forward_list` | 无 | O(1)（head 后） | O(1)（前驱之后） | — | O(n) | 仅被删元素失效 | 每节点 1 指针，最小开销 |

### 3.2 关联/无序容器

| 容器 | 底层 | 插入/删除 | 查找 | 有序遍历 | 范围查询 | 迭代器稳定性 | 内存特点 |
|---|---|---|---|---|---|---|---|
| `set/map` | 红黑树 | O(log n) | O(log n) | 是 | `lower/upper_bound` O(log n) | 仅被删元素失效 | 每节点 3 指针+颜色位 |
| `multiset/multimap` | 红黑树 | O(log n) | O(log n) | 是 | 是 | 仅被删元素失效 | 同上 |
| `unordered_set/map` | 开链哈希表 | 均摊 O(1) | 均摊 O(1)，最坏 O(n) | 否 | 否 | 插入引发 rehash → 迭代器全失效；**引用/指针永不因插入失效** | 桶数组+链节点；负载因子超 `max_load_factor`（默认 1.0）触发 rehash |

### 3.3 三个必须理解的底层机制

**vector 扩容**：容量不足时分配更大新内存（倍率实现定义）→ 元素搬移（noexcept 移动构造存在则移动，否则拷贝，见「06-现代C++新特性.md」3.5）→ 释放旧内存。代价是 O(n) 均摊 O(1)。

```cpp
std::vector<int> v;
v.reserve(1000);            // 预知规模时一次性分配，避免反复扩容
v.size();                   // 0：reserve 不改变 size
v.capacity();               // 1000
// shrink_to_fit() 可请求退还多余容量（非强制，视实现而定）
```

**deque 分段结构**：

```text
中控数组(map)：存各块地址
+----+----+----+----+
| P0 | P1 | P2 |    |
+--+-+--+-+--+-+----+
   |    |    |
   v    v    v
 [块0:_ _ a b] [块1:c d _ _] [块2:_ _ _ _]
        ^front      ^back
首块向前生长、末块向后生长 → 两端插入 O(1) 且无需搬移旧元素
随机访问需两级寻址：先算块号再算块内偏移（仍是 O(1)）
```

**unordered 的桶与 rehash**：元素按 `hash(key) % bucket_count` 挂到桶链上。`load_factor = size / bucket_count`，超过 `max_load_factor`（默认 1.0）即 rehash（桶数扩大，全部元素重新分桶）。已知规模时 `reserve(n)` 一次到位。

## 4. 选型决策：按场景选容器

| 场景 | 首选 | 理由 |
|---|---|---|
| 默认/不确定 | `vector` | 缓存友好 + 尾部均摊 O(1)，综合性能几乎总是最好 |
| 需要下标随机访问 | `vector` / `array`（定长） | O(1) |
| 双端进出 | `deque` | 两端 O(1) |
| 频繁中间插删（已持有位置） | `list` | O(1)，且不影响其他迭代器 |
| 有序遍历 / 范围查询（如"所有 18~25 岁"） | `map` / `set` | 红黑树天然有序 |
| 纯查找（key→value） | `unordered_map` | 均摊 O(1) |
| 去重 | `unordered_set`（无序）/ `set`（需有序） | |
| 栈 / 队列 / 优先队列 | `stack` / `queue` / `priority_queue` | 语义明确 |
| 定长小数组（如 RGB、坐标） | `std::array` | 零分配可拷贝 |

**为什么默认 vector？** 现代 CPU 的内存访问成本远高于指令执行。链表每个节点都是一次 cache miss；vector 连续内存让预取器全速工作。实测中"10 万元素 vector 中间插删"常常快于 list。**结论：先 vector，实测证明瓶颈再换。**

## 5. 迭代器失效规则（重中之重）

### 5.1 失效规则总表

| 容器 | 插入时 | 删除时 |
|---|---|---|
| `vector` | 扩容 → **全部失效**；不扩容 → 插入点**及之后**失效 | 被删点**及之后**失效 |
| `deque` | 两端插入 → 迭代器失效但**引用/指针不失效**；中间插入 → **全部失效** | 两端删除 → 仅被删元素；中间删除 → 全部失效（包括引用） |
| `list` / `forward_list` | 不失效 | **仅被删元素**失效 |
| `set` / `map` / `multi*` | 不失效 | **仅被删元素**失效 |
| `unordered_*` | 引发 rehash → 迭代器**全部失效**；未引发 rehash → 主流实现迭代器仍有效（标准严格措辞仅保证"引用不失效"，是否失效迭代器视实现而定）。**引用/指针永不因插入失效** | **仅被删元素**失效 |

记忆口诀：**节点式容器（list/map/set）天生稳定；连续内存（vector）一动全抖；deque 看位置；unordered 看 rehash。**

### 5.2 安全删除惯用法

```cpp
// 错误：erase 后 it 已失效，++it 是 UB
for (auto it = v.begin(); it != v.end(); ++it)
    if (pred(*it)) v.erase(it);            // UB！

// 正确（vector/list/map 通用）：用 erase 的返回值接住"下一个"
for (auto it = v.begin(); it != v.end(); ) {
    if (pred(*it)) it = v.erase(it);       // erase 返回被删元素的下一个
    else           ++it;
}

// C++20：一行搞定（首选）
std::erase_if(v, pred);
std::erase(v, 42);                         // 按值删
// 注意 map/set 的 erase_if 重载谓词接收的是 (key, value) pair
std::erase_if(m, [](const auto& kv) { return kv.second == 0; });
```

```cpp
// list/map 也可以先记 next 再删（C++11 起同样推荐 erase 惯用法）
auto next = std::next(it);
c.erase(it);
it = next;
```

### 5.3 与失效相关的经典事故

```cpp
// 事故1：遍历中 push_back 导致扩容失效
for (auto& x : v) {
    if (x < 0) v.push_back(-x);     // 扩容 → 隐藏的迭代器全部失效 → UB
}   // 正确：先收集到临时 vector，循环结束后统一插入

// 事故2：保存的指针/引用因扩容失效
int* p = &v[0];                      // 指向内部内存
v.push_back(99);                     // 可能扩容搬移
*p = 1;                              // 悬垂！需要"稳定地址"时用 deque/list 或 reserve 到底

// 事故3：把 end() 缓存下来
auto end = v.end();
v.push_back(1);
// *end;   // end 在扩容后失效，永远重新调用 v.end()
```

## 6. 常用算法分类

算法都在 `<algorithm>`（数值的在 `<numeric>`），区间一律是**左闭右开** `[first, last)`。

### 6.1 查找

| 算法 | 复杂度 | 要求 | 说明 |
|---|---|---|---|
| `find` / `find_if` | O(n) | — | 线性找第一个满足的 |
| `count` / `count_if` | O(n) | — | 计数 |
| `binary_search` | O(log n) | **已排序** | 只返回 bool |
| `lower_bound` | O(log n) | 已排序 | 第一个 **>= x** 的位置 |
| `upper_bound` | O(log n) | 已排序 | 第一个 **> x** 的位置 |
| `equal_range` | O(log n) | 已排序 | 同时返回两者（等值区间） |
| `find_if` + 谓词 | O(n) | — | 自定义条件的事实标准 |

```cpp
std::vector<int> v{1, 3, 5, 7, 9};
bool hit  = std::binary_search(v.begin(), v.end(), 5);      // true
auto it   = std::lower_bound(v.begin(), v.end(), 5);        // 指向 5
auto ins  = std::lower_bound(v.begin(), v.end(), 6);        // 指向 7：插入 6 的位置
// 范围查询"所有 3~7 的元素"：
auto [lo, hi] = std::equal_range(v.begin(), v.end(), 5);
```

### 6.2 排序与整理

| 算法 | 复杂度 | 特点 |
|---|---|---|
| `sort` | O(n log n) | 快排混合实现，**不稳定** |
| `stable_sort` | O(n log² n)（有余内存则 n log n） | **稳定**：相等元素保持原相对顺序 |
| `nth_element` | 平均 O(n) | 只保证第 n 大就位，两侧无序：Top-K 神器 |
| `partial_sort` | O(n log k) | 前 k 个有序 |
| `is_sorted` / `is_sorted_until` | O(n) | 检查 |

```cpp
std::sort(v.begin(), v.end());                          // 升序
std::sort(v.begin(), v.end(), std::greater<int>{});     // 降序
std::sort(v.begin(), v.end(), [](int a, int b) {        // 自定义：绝对值升序
    return std::abs(a) < std::abs(b);
});

// 只要前 10 大，不需要全排
std::nth_element(v.begin(), v.begin() + 9, v.end(), std::greater<int>{});
// v[9] 即第 10 大；v[0..9] 均 >= v[9] 但内部无序
```

**自定义比较函数的契约**：`comp(a,b)` 表示"a 排在 b 前"，必须满足严格弱序。**`return a <= b` 会导致 UB**（越界崩溃的经典成因之一）。

### 6.3 变换与数值

| 算法 | 说明 |
|---|---|
| `transform` | 逐元素映射到目标区间 |
| `copy` / `copy_if` / `move` | 拷贝/条件拷贝/搬移 |
| `for_each` | 对每个元素执行函数 |
| `accumulate`（`<numeric>`） | 折叠求和/自定义聚合，**从左到右确定顺序** |
| `reduce`（C++17） | 可乱序/可并行，要求操作满足结合律 |
| `iota`（`<numeric>`） | 填充递增序列 |

```cpp
std::vector<int> v{1, 2, 3, 4};
auto total = std::accumulate(v.begin(), v.end(), 0);            // 10：int 求和
std::vector<std::string> parts{"a", "b", "c"};
auto joined = std::accumulate(parts.begin(), parts.end(), std::string{});   // "abc"：拼接

std::vector<int> sq(v.size());
std::transform(v.begin(), v.end(), sq.begin(), [](int x) { return x * x; });

// C++17 并行版（execution policy 需编译器+后端支持，GCC 需链接 TBB）
#include <execution>
auto sum = std::reduce(std::execution::par, v.begin(), v.end(), 0);
```

### 6.4 删除：remove-erase 惯用法（必懂）

`std::remove` **根本不删除任何东西**——它只是把"要保留的元素"前移，返回新区间的逻辑末尾：

```text
v = [3, 1, 4, 1, 5, 9, 2, 6]        要 remove 所有 1
     3     4     5  9  2  6        保留元素被前移覆盖
v = [3, 4, 5, 9, 2, 6, ?, ?]
                  ^新逻辑 end       后面两个是"垃圾值"，size 仍是 8
需要 v.erase(new_end, v.end()) 才真正删掉，size 变 6
```

```cpp
auto new_end = std::remove_if(v.begin(), v.end(),
                              [](int x) { return x % 2 == 0; });
v.erase(new_end, v.end());          // remove-erase 惯用法（C++20 前）

std::erase_if(v, [](int x) { return x % 2 == 0; });   // C++20：一行等价
```

为什么这么设计？因为算法不认识容器，无法调用 `erase`（那是成员函数）——泛型解耦的代价由惯用法弥补。

### 6.5 集合操作（输入必须有序）

```cpp
std::vector<int> a{1, 2, 3, 5}, b{2, 3, 4}, out;
std::set_intersection(a.begin(), a.end(), b.begin(), b.end(),
                      std::back_inserter(out));   // {2,3}
// 同族：set_union / set_difference / set_symmetric_difference / merge / includes
```

`std::back_inserter(out)`：输出迭代器适配器，自动 push_back，无需预留空间。

## 7. 算法 + lambda 实战片段

```cpp
// 1. 按字符串长度排序（长度相同按字典序）
std::vector<std::string> words{"banana", "kiwi", "apple", "fig"};
std::sort(words.begin(), words.end(), [](const auto& a, const auto& b) {
    if (a.size() != b.size()) return a.size() < b.size();
    return a < b;
});

// 2. 词频统计（有序输出）
std::map<std::string, int> freq;
for (const auto& w : words) ++freq[w];            // operator[] 缺省插入 0 再自增
for (const auto& [word, n] : freq)                // C++17 结构化绑定
    std::cout << word << ' ' << n << '\n';

// 3. 找第一个满足条件的元素（不用手写循环）
auto it = std::find_if(students.begin(), students.end(),
                       [](const Student& s) { return s.score >= 90; });
if (it != students.end()) honor(*it);

// 4. 一行判断"是否全部/存在/都不"
bool allAdult = std::all_of(v.begin(), v.end(), [](int x){ return x >= 18; });
bool anyBad   = std::any_of(v.begin(), v.end(), [](int x){ return x < 0; });
bool noneZero = std::none_of(v.begin(), v.end(), [](int x){ return x == 0; });
```

## 8. string 补充

`std::string` 本质是 `basic_string<char>`——一个特殊的容器：连续存储、可动态增长、但接口按字符串习惯设计（+=、find、substr）。

### 8.1 SSO（小字符串优化）

| 要点 | 说明 |
|---|---|
| 机制 | 短字符串（一般 15/22 字符，**阈值视实现而定**）直接存在对象内部的栈缓冲，不分配堆 |
| 意义 | 大量短字符串场景零堆分配，性能与 C 字符串接近 |
| 推论 | 移动 string 不一定比拷贝快（SSO 区域只能逐字节拷） |
| 推论 | `std::move` 长字符串后原串清空（实现惯例，标准保证"有效但未指定"） |

### 8.2 数值转换

| 方法 | 方向 | 版本 | 特点 |
|---|---|---|---|
| `std::stoi / stof / stod` | 字符串→数 | C++11 | 方便，非法输入抛 `invalid_argument`/`out_of_range` |
| `std::to_string` | 数→字符串 | C++11 | 方便但慢 |
| `std::atoi`（C） | 字符串→数 | C | 无错误报告（失败返回 0），不要用 |
| `sprintf`/`snprintf`（C） | 数→字符串 | C | 缓冲区风险 |
| **`std::from_chars` / `to_chars`** | 双向 | **C++17** | `<charconv>`：无分配、无 locale、无异常，**最快**；返回 `from_chars_result{ptr, ec}` 需检查 |

```cpp
#include <charconv>
double d = 3.14;
char buf[32];
auto [ptr, ec] = std::to_chars(buf, buf + sizeof buf, d);   // ec == std::errc{} 即成功

int n{};
auto [p, ec2] = std::from_chars(buf, buf + std::strlen(buf), n);  // 解析区间 [first, last)
if (ec2 == std::errc{}) use(n);                                   // 成功
// 高性能解析（日志、协议）首选 from_chars；一般业务用 stoi 即可
```

## 9. 快速参考卡片

| 我想要…… | 用这个 |
|---|---|
| 动态数组，下标访问 | `vector`（+ `reserve` 预分配） |
| 定长数组 | `std::array<T, N>` |
| 双端队列 | `deque` |
| 中间频繁插删 | `list`（先实测！） |
| key→value 查找 | `unordered_map` |
| 有序遍历/范围查询 | `map` + `lower_bound`/`upper_bound` |
| 去重 | `unordered_set`（无需序）/ `set`（需序） |
| 栈 / 队列 / 堆 | `stack` / `queue` / `priority_queue` |
| 查找（未排序/已排序） | `find_if` / `binary_search` + `lower_bound` |
| 只要前 K 大 | `nth_element`（无序）/ `partial_sort`（前 K 有序） |
| 稳定排序 | `stable_sort` |
| 删除满足条件的元素 | C++20 `std::erase_if`；否则 remove-erase 惯用法 |
| 求和/聚合 | `accumulate`（确定顺序）/ `reduce`（可并行，C++17） |
| 逐元素变换 | `transform` |
| 输出到容器尾部 | `std::back_inserter` |
| 集合交并差 | `set_intersection` 等族（输入需有序） |
| 高性能数值转换 | `from_chars` / `to_chars`（C++17） |
| 遍历 map | `for (const auto& [k, v] : m)`（C++17） |

## 10. 常见问题与坑

| 问题 | 原因与解决方案 |
|---|---|
| `m[key]` 统计后 map 变大了一堆默认值 | `operator[]` 在 key 不存在时**默认构造并插入**。只读查询用 `find()` 或 `at()`（不存在时 at 抛 `out_of_range`） |
| 范围 for 里 `push_back` 程序崩了 | vector 扩容使隐藏迭代器失效（UB）。先写临时容器收集，循环外再插入 |
| 遍历时 erase 没用惯用法，偶发崩溃 | erase 使迭代器失效，`++it` 变 UB。用 `it = c.erase(it)`，或 C++20 `erase_if` |
| `remove` 之后 size 没变、垃圾数据还在 | remove 只做逻辑搬移。必须再 `erase(new_end, end())`；C++20 直接用 `std::erase` |
| `unordered_map` 用自定义 struct 做 key 编译报错 | 需要同时提供 `std::hash<Key>` 特化和 `operator==`。或传自定义 Hash/Equal 模板参数 |
| `reserve` 之后 `v[5]` 崩溃 | reserve 只保证 capacity 不改变 size，元素仍未构造。要"分配+默认构造"用 `resize` |
| 比较函数写了 `<=`，sort 崩溃 | 违反严格弱序（a<=b 且 b<=a 同时成立）是 UB。改成 `<`（或 `>`） |
| `vector<bool>` 行为诡异（`auto x = v[0]` 得到代理对象） | 它是位压缩特化，`operator[]` 返回代理引用，不是 bool。用 `vector<char>` 或 `std::bitset` |
| 在 set/map 里想改 key | 键是 const（改键会破坏树序）。删了重插；或改 value 部分（map 的 second 可改） |
| 迭代器与 `end()` 用 `<` 比较，list 上编译不过 | 只有随机访问迭代器支持 `<`。统一用 `!=` |
| 保存了 `&v[0]` 或 `v.data()`，之后 push_back，指针悬垂 | 扩容搬移使旧地址失效。需要稳定地址时用 deque/list 或预先 reserve |
| unordered_map 遍历顺序不稳定 | 哈希表本无序，rehash 后顺序还会变。依赖顺序的需求改用 map |
| `for (auto kv : m)` 每轮拷贝 pair | 加引用：`const auto&`。pair<string, vector<int>> 的拷贝相当可观 |
| multimap 找某 key 的所有值用 find 只拿到一个 | 用 `equal_range(key)` 拿到整段区间 |
| stack/queue 没有 clear() | 适配器刻意精简接口。清空可用 `s = {}` 或反复 pop |

---

上一篇：《02-面向对象与对象模型.md》
下一篇：《04-内存管理与智能指针.md》
