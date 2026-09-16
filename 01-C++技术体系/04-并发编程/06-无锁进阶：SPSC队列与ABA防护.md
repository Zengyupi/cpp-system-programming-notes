# 无锁进阶：SPSC 队列与 ABA 防护

> 本节目标：掌握单生产者单消费者（SPSC）无锁环形队列的 acquire/release 实现与伪共享处理；理解 ABA 问题与 tagged pointer 解法、MPMC 无锁队列的设计思路（Vyukov 序列号方案）；掌握 hazard pointer 与 RCU 两种内存安全回收机制及其适用场景。本篇承接《04-原子操作与C++内存模型.md》的内存序知识，偏概念与适用场景；完整无锁数据结构与组件实现见《../13-并发异步与组件/06-无锁编程基础.md》《../13-并发异步与组件/07-原子操作与无锁组件.md》；线程池与并发模式见《05-线程池与并发实战模式.md》。

## 本章速览

- [1. 无锁 SPSC 环形队列](#1-无锁-spsc-环形队列)
- [2. 无锁进阶](#2-无锁进阶)
  - [2.1 ABA 问题与 tagged pointer](#21-aba-问题与-tagged-pointer)
  - [2.2 MPMC 无锁队列设计思路](#22-mpmc-无锁队列设计思路)
  - [2.3 Hazard Pointer 与 RCU](#23-hazard-pointer-与-rcu)
- [3. 快速参考卡片](#3-快速参考卡片)
- [4. 常见坑](#4-常见坑)

---

## 1. 无锁 SPSC 环形队列

单生产者单消费者时，两个索引分别只被一端写入，可用 acquire/release 精确同步：

```cpp
#include <atomic>
#include <cstddef>

template <typename T, std::size_t N>       // N 必须是 2 的幂：用 & (N-1) 代替 %
class SpscQueue {
    static_assert((N & (N - 1)) == 0, "N 必须是 2 的幂");
public:
    bool push(const T& v) {                       // 仅生产者线程调用
        auto t = tail_.load(std::memory_order_relaxed);
        auto h = head_.load(std::memory_order_acquire);   // 看消费者释放了多少空间
        if (t - h == N) return false;                     // 满
        buf_[t & (N - 1)] = v;
        tail_.store(t + 1, std::memory_order_release);    // 发布：写数据在更新索引之前
        return true;
    }
    bool pop(T& v) {                              // 仅消费者线程调用
        auto h = head_.load(std::memory_order_relaxed);
        auto t = tail_.load(std::memory_order_acquire);   // 同步生产者已发布的数据
        if (h == t) return false;                         // 空
        v = buf_[h & (N - 1)];
        head_.store(h + 1, std::memory_order_release);    // 释放空间
        return true;
    }
private:
    T buf_[N];
    alignas(64) std::atomic<std::size_t> head_{0};  // 伪共享处理：两个索引分缓存行
    alignas(64) std::atomic<std::size_t> tail_{0};
};
// MPMC（多生产者多消费者）复杂得多，需要 CAS 索引分配，见下节。
```

三个设计要点必须能口述：

1. **写数据在更新索引之前**：生产者先写 `buf_[t & (N-1)]` 再 release store `tail_`，消费者 acquire load `tail_` 后读数据——数据与索引通过 release/acquire 建立 happens-before；
2. **容量必须是 2 的幂**：用位与 `& (N-1)` 代替取模，一条指令完成回绕；
3. **两个索引各归一端写**：head 只被消费者写、tail 只被生产者写，因此自身读可以用 relaxed；跨端读才需要 acquire。

---

## 2. 无锁进阶

> 本节讲概念与适用场景，完整无锁数据结构实现交叉引用《../13-并发异步与组件/06-无锁编程基础.md》《../13-并发异步与组件/07-原子操作与无锁组件.md》。

### 2.1 ABA 问题与 tagged pointer

**ABA 问题**：CAS 操作只比较"值是否相等"，但值从 A 变成 B 又变回 A 时，CAS 会误认为"没变过"，导致逻辑错误。

```text
经典 ABA 场景（无锁栈 push/pop）：
  栈: top → A → B → C
  线程 1: pop() 准备 CAS(top, A, B)  —— 读到 top=A，next=B
  线程 2: pop() → 返回 A
          pop() → 返回 B
          push(A) → 栈变为 top → A → C  （A 被重新插入！）
  线程 1: CAS(top, A, B) 成功！
          但 B 已经被 pop 并可能被释放/重用 → top→B 是悬垂指针！
```

**解决方案：tagged pointer（标记指针）**

把指针和一个版本号（tag/counter）打包成一个原子变量，每次修改时版本号递增。ABA 时即使指针相同，版本号也不同，CAS 失败。

```cpp
#include <atomic>
#include <cstdint>

// 利用 64 位指针高 16 位未使用（x86_64 只用低 48 位），存版本号
struct TaggedPtr {
    std::uint64_t raw;
    static constexpr std::uint64_t PTR_MASK = 0x0000FFFFFFFFFFFF;
    static constexpr std::uint64_t TAG_SHIFT = 48;

    void* ptr() const { return reinterpret_cast<void*>(raw & PTR_MASK); }
    std::uint16_t tag() const { return static_cast<std::uint16_t>(raw >> TAG_SHIFT); }

    static TaggedPtr make(void* p, std::uint16_t t) {
        return { (reinterpret_cast<std::uint64_t>(p) & PTR_MASK)
               | (static_cast<std::uint64_t>(t) << TAG_SHIFT) };
    }
};

// 无锁栈的 pop（带 tag 防 ABA）
struct Node { int data; Node* next; };

class LockFreeStack {
    std::atomic<TaggedPtr> top_;
public:
    LockFreeStack() : top_(TaggedPtr::make(nullptr, 0)) {}

    void push(int v) {
        Node* node = new Node{v, nullptr};
        TaggedPtr old_top = top_.load(std::memory_order_relaxed);
        do {
            node->next = static_cast<Node*>(old_top.ptr());
            TaggedPtr new_top = TaggedPtr::make(node, old_top.tag() + 1);  // tag 递增
        } while (!top_.compare_exchange_weak(old_top, new_top,
                    std::memory_order_release, std::memory_order_relaxed));
    }

    bool pop(int& out) {
        TaggedPtr old_top = top_.load(std::memory_order_acquire);
        while (old_top.ptr()) {
            Node* node = static_cast<Node*>(old_top.ptr());
            TaggedPtr new_top = TaggedPtr::make(node->next, old_top.tag() + 1);
            if (top_.compare_exchange_weak(old_top, new_top,
                    std::memory_order_acq_rel, std::memory_order_acquire)) {
                out = node->data;
                // 注意：此处不能直接 delete node！可能有其他线程正在访问
                // 需要 hazard pointer 或延迟回收（见 2.3）
                return true;
            }
            // CAS 失败：old_top 被刷新为最新值（含最新 tag），重试
        }
        return false;  // 栈空
    }
};
```

| 方案 | 原理 | 优点 | 缺点 |
| --- | --- | --- | --- |
| tagged pointer | 指针 + 版本号打包 | 简单，性能好 | 依赖指针高位未用（64 位限定），tag 可能溢出回绕 |
| 双重 CAS (DCAS) | 同时 CAS 指针和版本号两个变量 | 不依赖指针布局 | 大多数硬件不支持 DCAS，需用 CAS2 模拟 |
|  hazard pointer | 记录正在访问的指针，回收前检查 | 不依赖指针布局，安全 | 实现复杂，有内存延迟回收开销 |
| RCU | 读端无锁，写端复制修改 + 延迟释放 | 读端极快，适合读多写少 | 写端复杂，需要 grace period 机制 |

### 2.2 MPMC 无锁队列设计思路

MPMC（Multi-Producer Multi-Consumer）无锁队列比 SPSC 复杂得多，因为多个生产者同时写 tail、多个消费者同时读 head，都需要 CAS 竞争。

**经典设计：基于数组的 MPMC 队列（Dmitry Vyukov 风格）**

```text
核心思想：每个槽位有一个 sequence 号，生产者/消费者通过 sequence 协调

数组 buf[N]，每个元素带 seq[i]（原子计数器）：
  初始：seq[i] = i

生产者 enqueue(v):
  pos = tail.load(relaxed)
  cell = pos % N
  seq = seq[cell].load(acquire)
  diff = seq - pos
  if diff == 0:        // 该槽位可写
      if CAS(tail, pos, pos+1):  // 抢占这个位置
          buf[cell] = v
          seq[cell].store(pos+1, release)  // 标记已写入
          return true
  elif diff < 0: return false  // 队列满
  else: retry  // 其他生产者正在写，重试

消费者 dequeue(&v):
  pos = head.load(relaxed)
  cell = pos % N
  seq = seq[cell].load(acquire)
  diff = seq - (pos+1)
  if diff == 0:        // 该槽位有数据
      if CAS(head, pos, pos+1):
          *v = buf[cell]
          seq[cell].store(pos+N, release)  // 标记已读取，可被下一轮生产者写
          return true
  elif diff < 0: return false  // 队列空
  else: retry
```

| 维度 | SPSC 队列 | MPMC 队列 |
| --- | --- | --- |
| 生产者数 | 1 | 多 |
| 消费者数 | 1 | 多 |
| 索引更新 | 直接 store（无竞争） | CAS 循环（有竞争） |
| 内存序 | acquire/release 即可 | acquire/release + CAS acq_rel |
| 性能 | 极高（接近无开销） | 较高（CAS 竞争） |
| 实现难度 | 简单 | 复杂 |
| 典型用途 | 单线程生产 + 单线程消费的流水线 | 线程池任务队列、通用消息队列 |

> MPMC 无锁队列的完整实现（含内存回收、缓存行对齐、批量操作）参见《../13-并发异步与组件/07-原子操作与无锁组件.md》。生产环境建议直接使用成熟库：`boost::lockfree::queue`、`moodycamel::ConcurrentQueue`、Intel TBB `concurrent_queue`。

### 2.3 Hazard Pointer 与 RCU

无锁数据结构的核心难题之一是**内存安全回收**：一个线程刚从链表中摘下节点准备 delete，另一个线程可能正在读取该节点——直接 delete 会导致 use-after-free。

**Hazard Pointer（危险指针）**

```text
原理：
  1. 每个线程有一个 hazard pointer 列表，记录"我正在访问的指针"
  2. 读节点前：把节点指针存入自己的 hazard list
  3. 删节点前：把节点加入"待回收列表"，不立即 delete
  4. 定期扫描：遍历所有线程的 hazard list，如果待回收节点不在任何 hazard list 中，才安全 delete

回收流程：
  线程 A: pop 节点 X → X 加入 retire_list
  线程 B: 读 X 前 → hp[B] = X（标记危险）
  扫描: X 在 hp[B] 中 → 不回收，等下一轮
  线程 B: 读完 X → hp[B] = nullptr
  扫描: X 不在任何 hazard list 中 → delete X ✓
```

```cpp
#include <atomic>
#include <vector>
#include <unordered_set>

// 简化版 hazard pointer 框架
class HazardPointer {
public:
    static HazardPointer& instance() {
        static HazardPointer hp;
        return hp;
    }

    // 线程声明正在访问 ptr
    void protect(void* ptr) {
        auto& my_hazards = hazards_[std::this_thread::get_id()];
        my_hazards.insert(ptr);
    }

    // 线程取消保护
    void unprotect(void* ptr) {
        auto& my_hazards = hazards_[std::this_thread::get_id()];
        my_hazards.erase(ptr);
    }

    // 延迟回收：加入待删列表
    void retire(void* ptr) {
        retire_list_.push_back(ptr);
        try_reclaim();
    }

private:
    void try_reclaim() {
        // 收集所有 hazard 指针
        std::unordered_set<void*> all_hazards;
        for (auto& [tid, hz] : hazards_)
            for (void* p : hz) all_hazards.insert(p);

        // 回收不在 hazard 列表中的节点
        std::vector<void*> remaining;
        for (void* p : retire_list_) {
            if (all_hazards.count(p))
                remaining.push_back(p);  // 还在被访问，留到下一轮
            else
                delete p;  // 安全回收
        }
        retire_list_.swap(remaining);
    }

    std::unordered_map<std::thread::id, std::unordered_set<void*>> hazards_;
    std::vector<void*> retire_list_;
};
```

**RCU（Read-Copy-Update）**

```text
核心思想（读多写极少的场景）：
  读端：完全无锁，直接读指针（RCU read-side critical section）
  写端：
    1. 复制要修改的数据结构（Copy）
    2. 修改副本
    3. 原子地替换旧指针为新指针（rcu_assign_pointer）
    4. 等待一个 grace period（所有已开始的读端都结束）
    5. 释放旧数据结构

为什么读端可以无锁？
  写端不修改旧数据，只替换指针。正在读旧数据的线程继续读旧的（一致的快照），
  新的读线程看到新指针。旧数据在 grace period 后才释放，保证没有线程正在读它。

grace period：
  所有线程都经历过一次"静止点"（quiescent state，即不在 RCU 读端临界区中）。
  之后可以确定没有线程还持有旧数据的引用。
```

| 特性 | Hazard Pointer | RCU |
| --- | --- | --- |
| 读端开销 | 存 hazard pointer（一次写） | 几乎为零（rcu_read_lock 通常是编译器屏障） |
| 写端开销 | 加入 retire list + 定期扫描 | 复制数据 + 等待 grace period |
| 回收延迟 | 不确定（取决于扫描频率） | 一个 grace period（通常几毫秒） |
| 适用场景 | 通用无锁数据结构 | 读极多写极少（路由表、配置热更新） |
| 标准支持 | 无（需自行实现或用库） | Linux 内核有完整实现；用户态有 liburcu |

---

## 3. 快速参考卡片

按"我要实现 XX → 选什么"：

| 需求 | 推荐 |
| --- | --- |
| 单生产者单消费者高频队列 | 手写 SPSC 环形队列（本篇第 1 节，acquire/release） |
| 通用多生产者多消费者队列 | `moodycamel::ConcurrentQueue` / `boost::lockfree::queue` / TBB `concurrent_queue` |
| 线程池任务队列（有锁即可） | `mutex` + `std::queue`，竞争成为瓶颈再换无锁 |
| 防 ABA | tagged pointer（指针 + 版本号）；或直接用带 epoch/hp 的库 |
| 无锁结构的内存回收 | hazard pointer（通用）/ RCU（读多写少，liburcu） |
| 高性能环形缓冲（网络收发） | 《../13-并发异步与组件/09-网络缓冲区设计.md》 |

内存序速查：

| 场景 | 内存序 |
| --- | --- |
| 不携带其他数据的纯计数 | `relaxed` |
| 发布/读取共享数据（标志位、索引） | `release` 写 + `acquire` 读 |
| CAS 循环里改共享数据 | `acq_rel` |
| 多变量间需要全序（默认） | `seq_cst` |

---

## 4. 常见坑

| 问题 | 原因与解决方案 |
| --- | --- |
| atomic 全 relaxed，但其他线程读到旧数据 | relaxed 只保证单变量原子，不建 happens-before。解决：携带数据的标志/索引用 acquire/release 配对，别把 relaxed 当同步用 |
| `volatile` 当多线程同步 | volatile 不是内存屏障，CPU 乱序依旧。解决：用 `std::atomic` 或锁 |
| 双重检查锁定（DCLP）不加 atomic 崩溃 | `if (!p) { lock; if (!p) p = new T; }` 中 new 的写序可能重排。解决：C++11 起用局部 static；或 `std::atomic<T*>` + acquire/release（完整推导见《05-线程池与并发实战模式.md》3.3 节） |
| 无锁队列偶发崩溃，复现困难 | 大概率 ABA：CAS 只比较值，A→B→A 后误认为没变。解决：tagged pointer 或 hazard pointer |
| 伪共享导致多线程比单线程还慢 | 不同变量在同一缓存行，一个核写使其他核缓存失效。解决：`alignas(64)` 隔离或 padding（SPSC 的 head/tail 必须分缓存行） |
| 自写 MPMC 队列在压力下丢任务 | 序列号协议写错（seq 初始化、diff 判断）。解决：对照 Vyukov 原版逐行核对；生产环境直接用成熟库 |
| CAS 循环用 `compare_exchange_strong` 后忘记重读依赖数据 | CAS 失败时旧值被刷新，但通过旧指针读到的 next 可能已失效。解决：失败分支重新 load，不要复用旧读取结果 |

---

上一篇：《05-线程池与并发实战模式.md》　｜　模块索引：《../README.md》
