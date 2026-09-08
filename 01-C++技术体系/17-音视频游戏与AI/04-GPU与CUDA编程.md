# GPU 与 CUDA 编程

> 本节目标：讲解 GPU 并行计算架构与 CUDA 编程模型，学完后能够理解 GPU 与 CPU 的架构差异、掌握 CUDA 线程层次与内存模型、编写带共享内存优化的核函数、了解 CUDA 流与事件、性能优化方法论及 TensorRT 推理优化原理。对应岗位方向：AI 推理引擎、高性能计算（HPC）、算子优化。

## 本章速览

- [1. GPU 与 CPU 架构对比](#1-gpu-与-cpu-架构对比)
- [2. CUDA 线程层次](#2-cuda-线程层次)
- [3. CUDA 内存模型](#3-cuda-内存模型)
  - [3.1 共享内存分块矩阵乘（核心优化示例）](#31-共享内存分块矩阵乘核心优化示例)
  - [3.2 归约（Reduction）示例](#32-归约reduction示例)
- [4. 内存拷贝与异步流](#4-内存拷贝与异步流)
  - [4.1 基本内存管理](#41-基本内存管理)
  - [4.2 CUDA Stream 与事件](#42-cuda-stream-与事件)
- [5. 常用 CUDA 库](#5-常用-cuda-库)
  - [5.1 cuBLAS GEMM 调用示例](#51-cublas-gemm-调用示例)
- [6. TensorRT 推理优化](#6-tensorrt-推理优化)
- [7. GPU 性能优化方法论](#7-gpu-性能优化方法论)
  - [7.1 定位瓶颈：计算受限 vs 带宽受限](#71-定位瓶颈计算受限-vs-带宽受限)
  - [7.2 核心优化清单](#72-核心优化清单)
  - [7.3 Warp Divergence 与 Bank Conflict](#73-warp-divergence-与-bank-conflict)
- [8. 调试与错误检查](#8-调试与错误检查)
- [9. GPU 编程模型对比](#9-gpu-编程模型对比)
- [10. 学习路径](#10-学习路径)
- [11. 快速参考卡片](#11-快速参考卡片)
- [12. 常见问题与坑](#12-常见问题与坑)

---

## 1. GPU 与 CPU 架构对比

| 维度 | CPU | GPU |
| ---- | --------- | ------------ |
| 核心数 | 少（几~几十核） | 多（上千核） |
| 单核性能 | 强（复杂逻辑、大缓存、分支预测） | 弱（简单计算、小缓存） |
| 擅长 | 串行、分支、控制、低延迟 | 并行、密集计算、高吞吐 |
| 适用 | 通用逻辑、控制流 | 矩阵运算、图像、深度学习、科学计算 |
| 内存 | 大容量 DDR（几十~几百 GB），延迟低 | 高带宽 HBM/GDDR（几百 GB/s~TB/s），容量较小 |

GPU 采用 **SIMT**（Single Instruction Multiple Threads，单指令多线程）模型：海量线程同时执行相同指令处理不同数据。一个 SM（Streaming Multiprocessor，流式多处理器）包含多个 CUDA 核心、共享内存、寄存器文件，以 Warp（32 线程）为调度单位。

```text
GPU 架构层次：
GPU Device
 └── SM（Streaming Multiprocessor，几十个~上百个）
      ├── CUDA Core（整数/浮点单元，每 SM 几十个~上百个）
      ├── Tensor Core（矩阵乘加，AI 加速）
      ├── 寄存器文件（Register File，每 SM 几万个 32 位寄存器）
      ├── Shared Memory / L1 Cache（片上，低延迟）
      └── Warp Scheduler（以 32 线程为一组调度）
```

**关键认知**：GPU 不是"更快的 CPU"，而是"吞吐量优先的并行处理器"。延迟敏感的串行逻辑在 CPU 上跑，数据并行的密集计算 offload 到 GPU。

---

## 2. CUDA 线程层次

```text
Grid（网格，一个核函数启动的所有线程）
 ├── Block（线程块，Grid 的一维/二维/三维划分）
 │    ├── Thread（线程，Block 的一维/二维/三维划分）
 │    └── ...
 └── Block
      └── ...
```

| 概念 | 说明 | 典型规模 |
| ------ | ----------- | ------ |
| Thread | 最小执行单元，有唯一 threadIdx | — |
| Block | 线程组，共享内存单元，Block 内可同步 | 每 Block 最多 1024 线程，常用 128/256/512 |
| Grid | 所有 Block 集合 | 可含数十万个 Block |
| Warp | 硬件调度单位，32 线程一组 | 由硬件自动组成，Block 大小应为 32 的倍数 |

线程唯一索引计算（一维 Grid/Block）：
```cpp
__global__ void add(int* a, int* b, int* c, int n) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx < n) c[idx] = a[idx] + b[idx];
}
// 启动：Grid 大小 = ceil(n/256) 个 Block，每 Block 256 线程
add<<<(n + 255) / 256, 256>>>(d_a, d_b, d_c, n);
```

二维/三维索引用于图像处理、矩阵运算：
```cpp
int row = blockIdx.y * blockDim.y + threadIdx.y;
int col = blockIdx.x * blockDim.x + threadIdx.x;
```

---

## 3. CUDA 内存模型

| 内存 | 位置 | 速度 | 作用域 | 容量 |
| ------------- | -- | ----- | ------- | ---- |
| 寄存器 Register | 片上 | 最快（1 周期） | 单线程 | 每线程有限（用多了降低占用率） |
| 共享内存 Shared | 片上 | 快（~10 周期） | Block 内 | 每 SM 几十~一百多 KB |
| L1/L2 缓存 | 片上 | 快 | 自动缓存全局内存访问 | — |
| 全局内存 Global | 显存 | 慢（~300~500 周期） | 所有线程/Host | 几 GB~几十 GB |
| 常量内存 Constant | 显存 | 快（有缓存，广播高效） | 只读，所有线程 | 64 KB |
| 纹理内存 Texture | 显存 | 快（有缓存，适合 2D 局部访问） | 只读 | — |

### 3.1 共享内存分块矩阵乘（核心优化示例）

朴素矩阵乘每个元素多次读全局内存，带宽瓶颈严重。用共享内存做分块（tiling），把数据从全局内存加载到片上共享内存，重复利用：

```cpp
#define TILE 16

__global__ void matmul_shared(float* A, float* B, float* C, int N) {
    __shared__ float As[TILE][TILE];   // Block 内共享，减少全局内存访问
    __shared__ float Bs[TILE][TILE];

    int row = blockIdx.y * TILE + threadIdx.y;
    int col = blockIdx.x * TILE + threadIdx.x;
    float sum = 0.0f;

    // 逐块加载：把 A 的一行条带和 B 的一列条带搬到共享内存
    for (int t = 0; t < (N + TILE - 1) / TILE; ++t) {
        int aCol = t * TILE + threadIdx.x;
        int aRow = blockIdx.y * TILE + threadIdx.y;
        int bRow = t * TILE + threadIdx.y;
        int bCol = blockIdx.x * TILE + threadIdx.x;

        As[threadIdx.y][threadIdx.x] = (aRow < N && aCol < N) ? A[aRow * N + aCol] : 0.0f;
        Bs[threadIdx.y][threadIdx.x] = (bRow < N && bCol < N) ? B[bRow * N + bCol] : 0.0f;
        __syncthreads();                // Block 内同步：等所有线程加载完

        for (int k = 0; k < TILE; ++k)
            sum += As[threadIdx.y][k] * Bs[k][threadIdx.x];
        __syncthreads();                // 等所有线程用完共享内存，再加载下一块
    }
    if (row < N && col < N) C[row * N + col] = sum;
}
```

**要点**：
- `__shared__` 变量在 Block 内所有线程共享，生命周期与 Block 相同；
- `__syncthreads()` 是 Block 内屏障，必须所有线程都到达（不能放在分支里，否则死锁）；
- 分块大小通常 16 或 32，需兼顾共享内存容量和占用率。

### 3.2 归约（Reduction）示例

求和、求最大值等归约操作是常见并行模式，核心是"分治 + 共享内存"：

```cpp
__global__ void reduce_sum(float* input, float* output, int n) {
    __shared__ float sdata[256];
    int tid = threadIdx.x;
    int idx = blockIdx.x * blockDim.x * 2 + threadIdx.x;

    // 每个线程先加载两个元素（减少一半 Block 数）
    sdata[tid] = (idx < n ? input[idx] : 0.0f) + (idx + blockDim.x < n ? input[idx + blockDim.x] : 0.0f);
    __syncthreads();

    // 树状归约：步长从 128 递减到 1
    for (int s = blockDim.x / 2; s > 0; s >>= 1) {
        if (tid < s) sdata[tid] += sdata[tid + s];
        __syncthreads();
    }
    if (tid == 0) output[blockIdx.x] = sdata[0];   // 每 Block 一个部分和
}
// 最终对 output 数组再做一次归约或在 CPU 上求和
```

---

## 4. 内存拷贝与异步流

### 4.1 基本内存管理

```cpp
cudaMalloc(&d_a, size);                          // 分配显存
cudaMemcpy(d_a, h_a, size, cudaMemcpyHostToDevice);  // 主机→设备
cudaMemcpy(h_c, d_c, size, cudaMemcpyDeviceToHost);  // 设备→主机
cudaFree(d_a);                                    // 释放
```

**优化要点**：
- 减少 Host↔Device 拷贝次数：一次性拷大数据，避免小数据频繁拷贝；
- 用 **Pinned Memory（页锁定内存）**：`cudaMallocHost(&h_a, size)`，DMA 直接传输，带宽更高；
- 用 **CUDA Stream（流）** 实现计算与拷贝重叠。

### 4.2 CUDA Stream 与事件

Stream 是 GPU 上的命令队列，同一 Stream 内命令顺序执行，不同 Stream 可并行：

```cpp
cudaStream_t stream;
cudaStreamCreate(&stream);

// 在指定 stream 上异步执行（不阻塞 CPU）
cudaMemcpyAsync(d_a, h_a, size, cudaMemcpyHostToDevice, stream);
kernel<<<grid, block, 0, stream>>>(d_a, d_b, d_c, n);  // 第 3 个参数是 shared memory 大小，第 4 个是 stream
cudaMemcpyAsync(h_c, d_c, size, cudaMemcpyDeviceToHost, stream);

cudaEvent_t start, stop;
cudaEventCreate(&start); cudaEventCreate(&stop);
cudaEventRecord(start, stream);
// ... 执行核函数 ...
cudaEventRecord(stop, stream);
cudaEventSynchronize(stop);
float ms = 0;
cudaEventElapsedTime(&ms, start, stop);   // 精确计时（毫秒）

cudaStreamDestroy(stream);
```

**流水线重叠**：把数据分成多块，在不同 Stream 上"拷贝一块→计算一块→拷回一块"，实现 H2D 拷贝、核函数计算、D2H 拷贝三者并行，隐藏拷贝延迟。

---

## 5. 常用 CUDA 库

| 库 | 用途 | 典型场景 |
| ------ | ----------------- | ---- |
| cuBLAS | 矩阵运算（GEMM 等 BLAS 接口） | 深度学习全连接层、科学计算 |
| cuDNN | 深度学习算子（卷积、池化、归一化、激活） | 训练/推理框架后端 |
| cuFFT | 快速傅里叶变换 | 信号处理、图像、谱方法 |
| Thrust | 并行算法库（类似 STL，sort/reduce/transform） | 快速开发并行算法 |
| CUB | 底层并行原语（reduce、scan、sort） | 高性能自定义核函数 |
| NCCL | 多 GPU 集合通信（all-reduce、broadcast） | 分布式训练 |
| TensorRT | 推理优化引擎（层融合、量化、自动调优） | 生产部署 |

### 5.1 cuBLAS GEMM 调用示例

```cpp
#include <cublas_v2.h>
cublasHandle_t handle;
cublasCreate(&handle);

float alpha = 1.0f, beta = 0.0f;
// C = alpha * A * B + beta * C，注意 cuBLAS 是列主序
cublasSgemm(handle, CUBLAS_OP_N, CUBLAS_OP_N,
            N, N, N, &alpha, d_A, N, d_B, N, &beta, d_C, N);
cublasDestroy(handle);
```

---

## 6. TensorRT 推理优化

TensorRT 是 NVIDIA 的推理优化引擎，把训练好的网络编译优化为针对特定 GPU 的高性能引擎。

| 优化手段 | 原理 | 收益 |
| ------ | ---- | ---- |
| **层融合（Layer Fusion）** | Conv+BN+ReLU、多个小算子合并成一个 kernel | 减少 kernel launch 开销与显存往返 |
| **精度量化** | FP32 → FP16/INT8，利用 Tensor Core | 吞吐常提升 2~4 倍，显存减半 |
| **Kernel Auto-Tuning** | 针对当前 GPU 和输入形状从多种算法中选最快 | 选到最优 cuDNN/cuBLAS 实现 |
| **显存复用** | 生命周期不重叠的张量共用显存 | 显著降低显存占用 |
| **动态形状 Profile** | 为动态 batch/尺寸预设 min/opt/max | 支持变长输入同时保持优化 |

```cpp
// TensorRT 构建流程（概念性）
IBuilder* builder = createInferBuilder(logger);
INetworkDefinition* network = builder->createNetworkV2(0);
// 用 ONNX parser 解析模型
nvonnxparser::IParser* parser = nvonnxparser::createParser(*network, logger);
parser->parseFromFile("model.onnx", ...);

IBuilderConfig* config = builder->createBuilderConfig();
config->setFlag(BuilderFlag::kFP16);              // 启用 FP16
// config->setFlag(BuilderFlag::kINT8);           // 启用 INT8（需校准）
config->setMemoryPoolLimit(MemoryPoolType::kWORKSPACE, 1 << 30);

IHostMemory* serialized = builder->buildSerializedNetwork(*network, *config);
// 序列化后存盘，运行时反序列化为 ICudaEngine，创建 IExecutionContext 执行 enqueueV3
```

> **engine 与硬件/版本强绑定**：在 A 卡、TRT 8.6 编译的 engine，换到 B 卡或不同 TRT 版本可能加载失败。生产环境应在目标机型上构建 engine。

---

## 7. GPU 性能优化方法论

### 7.1 定位瓶颈：计算受限 vs 带宽受限

- **计算受限（Compute-Bound）**：Arithmetic Intensity（每字节内存访问对应的浮点运算数）高，优化方向是提高指令吞吐、利用 Tensor Core；
- **带宽受限（Memory-Bound）**：Arithmetic Intensity 低，优化方向是合并访问、共享内存复用、减少全局内存读写；
- 用 `nvprof` / `Nsight Compute` 查看 Achieved Occupancy、Memory Throughput、Compute Throughput 判断瓶颈。

### 7.2 核心优化清单

```text
1. 合并内存访问（Coalesced）：一个 Warp 的线程访问连续的全局内存地址
2. 用共享内存减少全局内存访问（分块/tiling）
3. 避免 Bank Conflict：共享内存 32 个 bank，多线程访问同一 bank 会串行化
4. 提高占用率（Occupancy）：活跃 Warp 数 / 最大 Warp 数，受寄存器和共享内存限制
5. 减少分支分歧（Warp Divergence）：同一 Warp 内线程走不同分支会串行执行
6. 用常量内存/纹理内存的缓存特性优化只读数据访问
7. 用 Stream 重叠拷贝与计算，隐藏 PCIe 传输延迟
8. 避免频繁 cudaMalloc/cudaFree，用显存池预分配
```

### 7.3 Warp Divergence 与 Bank Conflict

| 概念 | 说明 | 优化 |
| ------------- | ---------------- | ---- |
| Warp Divergence | 同一 Warp 32 线程遇到 if/else 走不同路径，硬件串行执行各分支 | 尽量让 Warp 内线程走相同路径，或用 Warp 级原语（`__shfl_*`） |
| Bank Conflict | 共享内存分为 32 个 bank（每 bank 4 字节），同一 Warp 多线程访问同一 bank 导致冲突 | 调整数组布局（如加 padding）、使用 `__ldg()` 只读缓存 |
| Occupancy | 每 SM 活跃 Warp 比例，过低则无法隐藏延迟 | 减少每线程寄存器用量、减小共享内存占用、合理设置 Block 大小 |

---

## 8. 调试与错误检查

CUDA 核函数错误不会直接抛出，必须主动检查：

```cpp
// 核函数启动后检查
kernel<<<grid, block>>>(...);
cudaError_t err = cudaGetLastError();   // 检查启动错误（如参数、配置）
if (err != cudaSuccess) printf("Kernel launch failed: %s\n", cudaGetErrorString(err));
cudaDeviceSynchronize();                 // 同步，检查执行期错误
err = cudaGetLastError();
if (err != cudaSuccess) printf("Kernel execution failed: %s\n", cudaGetErrorString(err));
```

**调试工具**：
- `cuda-gdb`：在 GPU 上设断点、单步、查看变量；
- `cuda-memcheck` / `compute-sanitizer`：检查越界、未初始化、竞态；
- Nsight Systems：时间线分析，看核函数、内存拷贝、Stream 重叠；
- Nsight Compute：逐核函数性能分析，看占用率、内存带宽、指令吞吐。

---

## 9. GPU 编程模型对比

| 模型 | 厂商/平台 | 特点 |
| --- | --- | --- |
| **CUDA** | NVIDIA | 生态最成熟、库最丰富、AI/HPC 事实标准，仅支持 NVIDIA GPU |
| OpenCL | 跨平台（NVIDIA/AMD/Intel/FPGA） | 通用性好但编程较繁琐，AI 生态弱 |
| Vulkan Compute | 跨平台图形 API 的计算管线 | 适合图形+计算混合，移动端可用 |
| Metal | Apple | iOS/macOS  GPU 编程，与 Swift/Objective-C 集成好 |
| ROCm | AMD | AMD GPU 的类 CUDA 平台，HIP 可从 CUDA 迁移 |
| SYCL | 跨平台（Intel oneAPI 等） | 单源 C++ 并行编程，标准演进中 |

---

## 10. 学习路径

```text
入门（1~2 周）：CUDA 编程模型、线程层次、简单向量加减、内存拷贝
  ↓
基础（2~3 周）：共享内存、同步、矩阵乘分块、归约、Stream 与事件
  ↓
进阶（3~4 周）：cuBLAS/cuDNN/Thrust 使用、性能分析工具、Occupancy 调优
  ↓
深入（持续）：自定义高性能 kernel、TensorRT 插件、多 GPU NCCL、算子融合
```

推荐资源：CUDA C++ Programming Guide（官方）、《CUDA C++ Best Practices Guide》、NVIDIA Developer Blog、GPU Gems 系列。

---

## 11. 快速参考卡片

```text
架构：CPU 低延迟串行 / GPU 高吞吐并行；SIMT 以 Warp(32线程) 调度
线程：Grid > Block > Thread；idx = blockIdx.x*blockDim.x + threadIdx.x；Block 大小取 32 倍数
内存：寄存器(最快/单线程) > 共享内存(Block内/片上) > 全局内存(慢/所有线程)
共享内存：__shared__ + __syncthreads() 分块复用；注意 bank conflict
拷贝：减少 H2D/D2H 次数；pinned memory；Stream 异步重叠计算与拷贝
库：cuBLAS(矩阵) / cuDNN(深度学习) / cuFFT / Thrust / CUB / TensorRT(推理)
优化：合并访问 + 共享内存 + 高占用率 + 避免 warp divergence + Stream 重叠
调试：cudaGetLastError + cudaDeviceSynchronize；Nsight Systems/Compute；compute-sanitizer
```

## 12. 常见问题与坑

1. **全局内存访问不连续**：带宽利用率极低，必须保证 Warp 内线程访问连续地址。
2. **共享内存 bank conflict**：性能反而下降，调整数组布局或加 padding。
3. **频繁 `cudaMemcpy` 小数据**：拷贝开销超过计算，应批量传输或用 pinned memory。
4. **未检查 `cudaGetLastError()`**：核函数启动错误被忽略，表现为"结果全是 0"。
5. **忽视 warp divergence**：分支导致串行执行，用 Warp 级原语或重构分支。
6. **寄存器用太多导致占用率低**：每线程寄存器过多使 SM 上活跃 Warp 减少，无法隐藏延迟。
7. **`__syncthreads()` 放在分支里**：部分线程不到达屏障导致死锁，必须所有线程都执行到。
8. **TensorRT engine 换机器加载失败**：engine 绑定 GPU 型号和 TRT 版本，在目标机构建。
9. **CPU 和 GPU 指针混用**：`cudaMalloc` 返回的是设备指针，不能在 CPU 上直接解引用。
10. **忘记 `cudaDeviceSynchronize()` 就计时**：核函数是异步启动的，不同步测得的时间不准确。

---

上一篇：《03-端侧AI推理部署.md》
下一篇：《05-图形学与游戏引擎.md》
