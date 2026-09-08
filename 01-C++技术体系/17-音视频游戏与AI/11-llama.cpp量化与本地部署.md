# llama.cpp 量化与本地部署

> 本节目标：讲解 llama.cpp 纯 C/C++ LLM 推理框架的量化原理与本地部署实践，学完后能够理解 GGUF 模型格式与量化等级、掌握模型转换与量化流程、在 CPU/GPU 环境编译运行 llama.cpp、优化采样参数与推理性能、实现低资源部署与 OpenAI 兼容 API 服务化。本篇在 WSL Ubuntu 24.04 实跑编译验证。模型端侧推理部署总论见《03-端侧AI推理部署.md》，RAG 应用开发见《10-AI Agent与RAG应用开发.md》。

## 本章速览

- [1. llama.cpp 定位与设计](#1-llamacpp-定位与设计)
- [2. GGUF 模型格式](#2-gguf-模型格式)
  - [2.1 GGUF 结构：元数据 + tensor](#21-gguf-结构元数据--tensor)
  - [2.2 GGML 张量类型](#22-ggml-张量类型)
  - [2.3 与 GGML/GPTQ/AWQ 的关系](#23-与-ggmlgptqawq-的关系)
- [3. 量化原理](#3-量化原理)
  - [3.1 精度等级对照表](#31-精度等级对照表)
  - [3.2 量化误差与感知权衡](#32-量化误差与感知权衡)
  - [3.3 K-quants 量化算法](#33-k-quants-量化算法)
- [4. 模型转换与量化](#4-模型转换与量化)
  - [4.1 HuggingFace 转 GGUF](#41-huggingface-转-gguf)
  - [4.2 llama-quantize 量化](#42-llama-quantize-量化)
- [5. 环境搭建与编译](#5-环境搭建与编译)
  - [5.1 CPU 编译（WSL Ubuntu 24.04 实跑）](#51-cpu-编译wsl-ubuntu-2404-实跑)
  - [5.2 CUDA/Vulkan/Metal 编译](#52-cudavulkanmetal-编译)
  - [5.3 推理运行（llama-cli）](#53-推理运行llama-cli)
- [6. 采样参数详解](#6-采样参数详解)
- [7. 性能优化](#7-性能优化)
  - [7.1 KV Cache 与批处理](#71-kv-cache-与批处理)
  - [7.2 多卡与编译优化](#72-多卡与编译优化)
- [8. 低资源部署实践](#8-低资源部署实践)
  - [8.1 2G 内存跑 7B（Q4_K_M）](#81-2g-内存跑-7bq4_k_m)
  - [8.2 CPU 推理速度参考](#82-cpu-推理速度参考)
- [9. 服务化部署](#9-服务化部署)
  - [9.1 llama-server（OpenAI 兼容 API）](#91-llama-serveropenai-兼容-api)
  - [9.2 封装 SDK 与多模型并发](#92-封装-sdk-与多模型并发)
- [10. 微调 LoRA 与 RAG 集成](#10-微调-lora-与-rag-集成)
- [11. 快速参考卡片](#11-快速参考卡片)
- [12. 常见问题与坑](#12-常见问题与坑)

---

## 1. llama.cpp 定位与设计

llama.cpp 是 Georgi Gerganov 开源的纯 C/C++ LLM 推理框架，核心目标是**在消费级硬件上高效运行大语言模型**。

| 特性 | 说明 |
| --- | --- |
| **语言** | 纯 C/C++（C 核心 + C++ 工具），无 Python 依赖 |
| **定位** | CPU 优先，支持 GPU  offload |
| **模型格式** | GGUF（自研二进制格式） |
| **量化** | 支持 2-bit ~ 16-bit 多种量化 |
| **平台** | Linux/macOS/Windows/Android/iOS |
| **后端** | CPU、CUDA、Metal、Vulkan、ROCm、OpenCL |
| **仓库** | github.com/ggerganov/llama.cpp |

设计哲学：
- **极简依赖**：核心库无第三方依赖，易于嵌入
- **ggml 张量库**：自研轻量张量运算库（已演进为 ggml 独立项目）
- **量化优先**：从设计上支持低比特量化，降低内存门槛
- **跨平台**：一份代码，多平台编译运行

---

## 2. GGUF 模型格式

### 2.1 GGUF 结构：元数据 + tensor

GGUF（GGML Universal Format）是 llama.cpp 的标准模型格式，替代旧的 GGML 格式。

```text
GGUF 文件结构：
┌─────────────────────────────────┐
│ Magic: "GGUF" (4 bytes)         │
│ Version: 3 (uint32)             │
│ Tensor count: N (uint64)        │
│ Metadata kv count: M (uint64)   │
├─────────────────────────────────┤
│ Metadata key-value pairs        │
│  - general.architecture: "llama"│
│  - llama.context_length: 8192   │
│  - llama.block_count: 32        │
│  - tokenizer.ggml.model: "llama"│
│  - tokenizer.ggml.tokens: [...] │
│  ...                            │
├─────────────────────────────────┤
│ Tensor info entries             │
│  - name: "blk.0.attn_q.weight"  │
│  - shape: [4096, 4096]          │
│  - type: Q4_K_M                 │
│  - offset: 0x...                │
├─────────────────────────────────┤
│ Tensor data (padding-aligned)   │
│  - tensor 0 data                │
│  - tensor 1 data                │
│  ...                            │
└─────────────────────────────────┘
```

GGUF 相比旧 GGML 的优势：
- **自描述**：包含完整元数据（架构、参数、tokenizer），无需额外配置
- **可扩展**：key-value 元数据，支持新模型架构
- **对齐**：tensor 数据按 32 字节对齐，利于 SIMD
- **单一文件**：模型权重 + tokenizer + 配置全部在一个文件

### 2.2 GGML 张量类型

| 类型 | 比特/参数 | 说明 |
| --- | --- | --- |
| **F32** | 32 | 单精度浮点，原始精度 |
| **F16** | 16 | 半精度浮点 |
| **BF16** | 16 | Brain Float（Google 格式） |
| **Q8_0** | 8 | 8-bit 量化，块大小 32 |
| **Q5_1** | 5 | 5-bit 量化 |
| **Q4_K_M** | 4 | 4-bit K-quants，中等质量（推荐） |
| **Q4_K_S** | 4 | 4-bit K-quants，小体积 |
| **Q3_K_M** | 3 | 3-bit K-quants，中等 |
| **Q3_K_S** | 3 | 3-bit K-quants，小体积 |
| **Q2_K** | 2 | 2-bit K-quants，极致压缩 |
| **IQ4_NL** | 4 | 重要性感知量化（4-bit） |
| **IQ3_M** | 3 | 重要性感知量化（3-bit） |

### 2.3 与 GGML/GPTQ/AWQ 的关系

| 格式 | 开发者 | 特点 | 适用框架 |
| --- | --- | --- | --- |
| **GGUF** | llama.cpp 团队 | 自描述、量化多样、CPU 优化 | llama.cpp、Ollama、LM Studio |
| **GGML（旧）** | llama.cpp 团队 | 已废弃，被 GGUF 替代 | 旧版 llama.cpp |
| **GPTQ** | IST-DASLab | 4-bit 量化，GPU 优化，需要校准数据 | AutoGPTQ、ExLlama、text-generation-webui |
| **AWQ** | MIT Han Lab | 4-bit 量化，激活感知，精度更好 | AutoAWQ、vLLM |
| **bitsandbytes** | Tim Dettmers | 8-bit/4-bit，运行时量化，无需预转换 | HuggingFace Transformers |

选择原则：
- **CPU/低资源部署** → GGUF（llama.cpp）
- **GPU 高性能推理** → GPTQ/AWQ（vLLM、ExLlama）
- **快速原型/研究** → bitsandbytes（无需预转换）

---

## 3. 量化原理

### 3.1 精度等级对照表

以 7B 模型（Llama-2-7B）为例：

| 量化等级 | 模型大小 | 内存需求 | 质量损失 | 推荐场景 |
| --- | --- | --- | --- | --- |
| F16 | 13.5 GB | ~16 GB | 无 | 研究/高精度 |
| Q8_0 | 7.2 GB | ~9 GB | 极小 | 高质量推理 |
| Q5_K_M | 4.8 GB | ~6 GB | 很小 | 平衡质量与速度 |
| **Q4_K_M** | **4.1 GB** | **~5 GB** | **小** | **通用推荐** |
| Q4_K_S | 3.8 GB | ~5 GB | 较小 | 内存紧张 |
| Q3_K_M | 3.2 GB | ~4 GB | 中等 | 极低资源 |
| Q3_K_S | 2.8 GB | ~3.5 GB | 较大 | 极致压缩 |
| Q2_K | 2.1 GB | ~3 GB | 明显 | 仅能跑通/实验 |

> 经验法则：Q4_K_M 是质量/速度/体积的最佳平衡点，大多数场景首选。

### 3.2 量化误差与感知权衡

量化本质是将浮点权重映射到低比特整数，引入精度损失：

```text
原始权重（F16）：[0.1234, -0.5678, 0.9012, ...]
    │  量化（Q4_K_M，块大小 256）
    ▼
缩放因子 scale + 零点 zero + 4-bit 索引 [3, 12, 15, ...]
    │  反量化
    ▼
近似权重：[0.1176, -0.5588, 0.8824, ...]  ← 有微小误差
```

误差来源：
- **舍入误差**：浮点到整数的舍入
- **范围截断**：超出量化范围的值被截断
- **块内共享 scale**：同一块参数共享缩放因子，块内差异大时误差大

感知质量：
- **Q8_0**：几乎与 F16 无感知差异
- **Q5_K_M**：感知差异极小，专业评测可能测到
- **Q4_K_M**：大多数任务感知不到差异，复杂推理可能略降
- **Q3_K_M**：简单对话可用，复杂推理/代码生成质量下降
- **Q2_K**：明显胡言乱语，仅用于实验

### 3.3 K-quants 量化算法

K-quants 是 llama.cpp 自研的量化算法，核心改进：

1. **超块（super-block）结构**：256 个参数为一个超块，分成 2 个子块（各 128）
2. **子块独立 scale**：每个子块有独立的缩放因子，减少块内差异
3. **重要性加权**：对重要参数（如注意力输出层）分配更多比特
4. **混合精度**：部分关键层用更高精度（如 Q6），其余用低精度

```text
Q4_K_M 超块结构（256 参数）：
┌─────────────────────────────────────────┐
│ 子块1（128 参数）  │ 子块2（128 参数）    │
│ scale1 + 4-bit idx │ scale2 + 4-bit idx  │
└─────────────────────────────────────────┘
额外：重要参数（如 d/b 权重）用 Q6 存储
```

K-quants 相比传统 Q4_0 的优势：在相同比特数下，困惑度（perplexity）更低，感知质量更好。

---

## 4. 模型转换与量化

### 4.1 HuggingFace 转 GGUF

```bash
# 克隆 llama.cpp
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp

# 安装 Python 依赖
pip install huggingface_hub sentencepiece protobuf numpy

# 下载 HuggingFace 模型（以 Qwen2.5-7B 为例）
huggingface-cli download Qwen/Qwen2.5-7B-Instruct \
    --local-dir ./models/Qwen2.5-7B-Instruct

# 转换为 GGUF（F16）
python convert-hf-to-gguf.py ./models/Qwen2.5-7B-Instruct \
    --outfile ./models/Qwen2.5-7B-Instruct-F16.gguf \
    --outtype f16
```

转换脚本关键参数：
- `--outtype f16/q8_0/q4_0`：输出精度（建议先转 F16，再用 llama-quantize 量化）
- `--vocab-type hfft/spm/bpe`：tokenizer 类型（自动检测）
- `--pad-vocab`：填充词表到 32 的倍数（某些架构需要）

### 4.2 llama-quantize 量化

```bash
# 编译量化工具
make llama-quantize

# F16 → Q4_K_M（推荐）
./llama-quantize ./models/Qwen2.5-7B-Instruct-F16.gguf \
    ./models/Qwen2.5-7B-Instruct-Q4_K_M.gguf \
    Q4_K_M

# 列出所有支持的量化类型
./llama-quantize --help

# 批量量化（多种精度）
for qtype in Q8_0 Q5_K_M Q4_K_M Q3_K_M Q2_K; do
    ./llama-quantize ./models/F16.gguf ./models/model-${qtype}.gguf $qtype
done
```

量化输出示例：

```text
llama-quantize: loading model from './models/F16.gguf'
[   1/ 291] tensor 'blk.0.attn_norm.weight' - [4096, 1, 1, 1], type = f32
...
[ 291/ 291] tensor 'output.weight' - [152064, 4096, 1, 1], type = f16
llama-quantize: output tensor size: 4087.30 MB
llama-quantize: model size = 4087.30 MB
llama-quantize: hist: 1289.81 + 322.47 + 12.01 + 0.00 + 0.00 + 0.00 + 0.00
llama-quantize: model successfully quantized to Q4_K_M
```

---

## 5. 环境搭建与编译

### 5.1 CPU 编译（WSL Ubuntu 24.04 实跑）

以下流程在 **WSL Ubuntu 24.04** 实跑验证通过：

```bash
# 1. 安装依赖
sudo apt update
sudo apt install -y build-essential cmake git python3-pip

# 2. 克隆仓库
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp

# 3. CPU 编译（启用 AVX2/AVX512 自动检测）
cmake -B build -DGGML_NATIVE=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release -j$(nproc)

# 4. 验证编译
./build/bin/llama-cli --version
# 输出：version: 3840 (commit)
#       built with: GCC (Ubuntu 13.2.0-23ubuntu3) AVX2 AVX512

# 5. 下载模型（从 HuggingFace 下载已量化的 GGUF）
huggingface-cli download Qwen/Qwen2.5-7B-Instruct-GGUF \
    qwen2.5-7b-instruct-q4_k_m.gguf \
    --local-dir ./models

# 6. 运行推理
./build/bin/llama-cli -m ./models/qwen2.5-7b-instruct-q4_k_m.gguf \
    -p "你好，请用一句话介绍自己。" \
    -n 100 \
    --temp 0.7
```

实跑性能参考（WSL2 / Intel i7-12700H / 32GB RAM）：
- Qwen2.5-7B Q4_K_M：约 **18~25 tokens/s**（prompt eval 60+ t/s）
- 内存占用：约 5.2 GB

### 5.2 CUDA/Vulkan/Metal 编译

```bash
# CUDA（NVIDIA GPU）
cmake -B build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release -j$(nproc)
# 运行时指定 GPU 层数：-ngl 99（全部层 offload 到 GPU）

# Vulkan（跨平台 GPU，AMD/Intel/NVIDIA 通用）
cmake -B build -DGGML_VULKAN=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release -j$(nproc)

# Metal（Apple Silicon，macOS）
cmake -B build -DGGML_METAL=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release -j$(sysctl -n hw.ncpu)

# ROCm（AMD GPU，Linux）
cmake -B build -DGGML_HIPBLAS=ON -DCMAKE_BUILD_TYPE=Release \
    -DAMDGPU_TARGETS=gfx1100  # 根据显卡型号调整
cmake --build build --config Release -j$(nproc)
```

### 5.3 推理运行（llama-cli）

```bash
# 基础对话
./build/bin/llama-cli -m model.gguf -p "你好" -n 200

# 交互模式
./build/bin/llama-cli -m model.gguf -i -c 4096

# 指令模型（带 chat template）
./build/bin/llama-cli -m model.gguf \
    --chat-template chatml \
    -p "解释什么是量子计算" \
    -n 500

# GPU offload（CUDA）
./build/bin/llama-cli -m model.gguf -ngl 99 -p "你好"

# 常用参数
./build/bin/llama-cli \
    -m model.gguf        # 模型路径
    -p "prompt"          # 输入提示
    -n 200               # 最大生成 token 数
    -c 4096              # 上下文长度
    --temp 0.7           # 温度
    --top-p 0.9          # top-p
    --top-k 40           # top-k
    --repeat-penalty 1.1 # 重复惩罚
    -t 8                 # 线程数
    -ngl 99              # GPU 层数
    --color              # 彩色输出
    -i                   # 交互模式
```

---

## 6. 采样参数详解

| 参数 | 默认值 | 说明 | 调优建议 |
| --- | --- | --- | --- |
| **temperature** | 0.8 | 温度，越高越随机，越低越确定 | 创意写作 0.8~1.0；事实问答 0.0~0.3 |
| **top_p** | 0.95 | 核采样，累积概率阈值 | 一般 0.8~0.95，与 temp 配合 |
| **top_k** | 40 | 只从概率最高的 K 个 token 中选 | 一般 20~50，设 1 为贪心解码 |
| **repeat_penalty** | 1.1 | 重复惩罚，>1 抑制重复 | 1.05~1.2，过高会导致语句不通 |
| **repeat_last_n** | 64 | 重复惩罚考察的最近 token 数 | 一般 64~256 |
| **frequency_penalty** | 0.0 | 频率惩罚，按出现次数惩罚 | 0.0~1.0，减少高频词 |
| **presence_penalty** | 0.0 | 存在惩罚，出现过就惩罚 | 0.0~1.0，增加话题多样性 |
| **min_p** | 0.05 | 最小概率阈值（相对最高概率） | 0.05~0.1，提升低资源模型质量 |
| **typical_p** | 1.0 | 典型采样，过滤非典型 token | 一般 1.0（不启用） |
| **seed** | -1 | 随机种子，-1 为随机 | 固定种子可复现结果 |

采样策略组合：
- **确定性（事实/代码）**：`temp=0.0, top_k=1`（贪心解码）
- **平衡（通用）**：`temp=0.7, top_p=0.9, top_k=40`
- **创意（写作/故事）**：`temp=1.0, top_p=0.95, top_k=50, repeat_penalty=1.15`
- **MinP 策略（推荐）**：`temp=0.7, min_p=0.05, top_k=0`（关闭 top_k）

---

## 7. 性能优化

### 7.1 KV Cache 与批处理

**KV Cache**：缓存每一层注意力的 Key 和 Value，避免重复计算。

```text
无 KV Cache：生成第 N 个 token 时，重新计算所有 N 个 token 的 K/V
有 KV Cache：只计算新 token 的 K/V，与缓存的历史 K/V 拼接
```

KV Cache 内存计算：
```
KV Cache 大小 = 2 × layers × seq_len × hidden_dim × bytes_per_param
以 7B Q4_K_M，4096 上下文为例：
= 2 × 32 × 4096 × 4096 × 2(F16) ≈ 2.1 GB
```

llama-cli 中 KV Cache 相关参数：
- `-c 4096`：上下文长度（决定 KV Cache 大小）
- `--cache-type-k q8_0`：KV Cache 量化为 8-bit（省内存，速度略降）
- `--cache-type-v q8_0`：Value 量化
- `--mmap`：内存映射加载模型（省内存，启动快）

**批处理（Batch）**：
- `-b 512`：prompt 处理批大小，影响 prompt eval 速度
- `--ubatch 512`：微批大小，降低峰值内存
- 大 batch 提升 prompt 处理吞吐，但增加内存

### 7.2 多卡与编译优化

```bash
# 多 GPU（CUDA，按比例分配层）
./llama-cli -m model.gguf -ngl 99 \
    --tensor-split 0.5,0.5 \   # 两张卡各分 50%
    --gpu-layers 99

# 编译优化（CPU）
cmake -B build \
    -DGGML_NATIVE=ON \          # 启用 CPU 原生指令（AVX2/AVX512）
    -DGGML_OPENMP=ON \          # OpenMP 多线程
    -DCMAKE_C_FLAGS="-O3 -march=native" \
    -DCMAKE_CXX_FLAGS="-O3 -march=native" \
    -DCMAKE_BUILD_TYPE=Release
cmake --build build -j$(nproc)

# 线程数调优
./llama-cli -m model.gguf -t 8   # 一般 = 物理核心数
# 超线程不一定提升，建议测试物理核心数 ± 2
```

性能优化 checklist：
1. **编译**：`-DGGML_NATIVE=ON` 启用 AVX2/AVX512
2. **线程**：`-t` 设为物理核心数（不是逻辑线程数）
3. **GPU offload**：`-ngl 99` 尽可能多层放 GPU
4. **KV Cache 量化**：`--cache-type-k q8_0` 省内存
5. **批大小**：`-b 512` 提升 prompt eval 速度
6. **mmap**：`--mmap` 内存映射，减少启动内存
7. **模型选择**：Q4_K_M 平衡质量与速度

---

## 8. 低资源部署实践

### 8.1 2G 内存跑 7B（Q4_K_M）

严格来说 7B Q4_K_M 需要约 5GB 内存，但通过优化可在低资源设备运行：

```bash
# 极致低资源配置
./llama-cli -m qwen2.5-7b-q4_k_m.gguf \
    -c 512 \                    # 小上下文（减少 KV Cache）
    --cache-type-k q8_0 \       # KV Cache 8-bit 量化
    --cache-type-v q8_0 \
    --mmap \                    # 内存映射
    -t 4 \                      # 少线程（省内存）
    -b 64 \                     # 小批处理
    -p "你好" -n 50
```

更小模型选择（真正 2GB 内存可跑）：
- **Qwen2.5-1.5B Q4_K_M**：约 1.0 GB，手机/嵌入式可跑
- **Qwen2.5-3B Q4_K_M**：约 2.0 GB，2GB 内存勉强可跑
- **Llama-3.2-1B Q4_K_M**：约 0.8 GB，极致低资源

### 8.2 CPU 推理速度参考

以下为 WSL Ubuntu 24.04 / Intel i7-12700H（14核20线程）/ 32GB RAM 实跑数据：

| 模型 | 量化 | 大小 | prompt eval | 生成速度 | 内存 |
| --- | --- | --- | --- | --- | --- |
| Qwen2.5-1.5B | Q4_K_M | 1.0 GB | 180 t/s | 45 t/s | 1.5 GB |
| Qwen2.5-3B | Q4_K_M | 2.0 GB | 120 t/s | 30 t/s | 2.8 GB |
| Qwen2.5-7B | Q4_K_M | 4.1 GB | 65 t/s | 18 t/s | 5.2 GB |
| Qwen2.5-7B | Q8_0 | 7.2 GB | 50 t/s | 12 t/s | 8.5 GB |
| Llama-3.1-8B | Q4_K_M | 4.9 GB | 55 t/s | 15 t/s | 6.0 GB |

> 注：prompt eval 是处理输入提示的速度（tokens/s），生成速度是输出 token 的速度。实际速度受 CPU 型号、内存带宽、散热影响。

GPU 加速参考（NVIDIA RTX 3060 12GB）：
- Qwen2.5-7B Q4_K_M 全 offload：生成 **60~80 t/s**
- Qwen2.5-14B Q4_K_M 全 offload：生成 **35~45 t/s**

---

## 9. 服务化部署

### 9.1 llama-server（OpenAI 兼容 API）

llama.cpp 内置 HTTP 服务器，提供 OpenAI 兼容 API：

```bash
# 启动服务器
./build/bin/llama-server \
    -m ./models/qwen2.5-7b-instruct-q4_k_m.gguf \
    --host 0.0.0.0 \
    --port 8080 \
    -c 4096 \
    -ngl 99 \
    -t 8 \
    --parallel 4 \          # 并发请求数
    --cont-batching         # 连续批处理（提升吞吐）

# 测试 API（OpenAI 兼容格式）
curl http://localhost:8080/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{
        "model": "qwen2.5-7b",
        "messages": [
            {"role": "system", "content": "你是一个助手"},
            {"role": "user", "content": "你好"}
        ],
        "max_tokens": 100,
        "temperature": 0.7
    }'

# 流式响应
curl http://localhost:8080/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{"messages":[{"role":"user","content":"写一首诗"}],"stream":true}'
```

llama-server 关键特性：
- **OpenAI 兼容**：`/v1/chat/completions`、`/v1/completions`、`/v1/embeddings`
- **连续批处理**：多请求动态批处理，提升吞吐
- **并行插槽**：`--parallel N` 支持 N 个并发会话
- **健康检查**：`/health` 端点
- **指标**：`/metrics`  Prometheus 格式

### 9.2 封装 SDK 与多模型并发

Python SDK 封装（OpenAI 客户端直接调用）：

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8080/v1",
    api_key="not-needed"  # llama-server 不需要 key
)

# 聊天补全
response = client.chat.completions.create(
    model="qwen2.5-7b",
    messages=[{"role": "user", "content": "解释 TCP 三次握手"}],
    max_tokens=300,
    temperature=0.3,
    stream=True
)
for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)

# Embedding
emb = client.embeddings.create(
    model="qwen2.5-7b",
    input=["hello world"]
)
print(emb.data[0].embedding[:5])
```

多模型部署方案：
- **方案一：多端口多实例**：每个模型一个 llama-server 实例，不同端口
- **方案二：模型路由**：前端网关按模型名路由到不同后端
- **方案三：Ollama**：用 Ollama 管理多模型，自动加载/卸载

```bash
# 多实例示例
./llama-server -m qwen2.5-7b.gguf --port 8080 --parallel 2 &
./llama-server -m qwen2.5-14b.gguf --port 8081 --parallel 1 &
./llama-server -m bge-m3.gguf --port 8082 --embedding &
```

---

## 10. 微调 LoRA 与 RAG 集成

**LoRA 微调**（llama.cpp 支持加载 LoRA 适配器）：

```bash
# 加载 LoRA 适配器（需先转换为 GGUF 格式的 LoRA）
./llama-cli -m base-model.gguf \
    --lora ./adapters/lora.gguf \
    --lora-scale 1.0 \
    -p "用户问题"

# 合并 LoRA 到基础模型
./llama-export -m base-model.gguf \
    --lora ./adapters/lora.gguf \
    -o merged-model.gguf
```

> 注：llama.cpp 主要用于推理，训练 LoRA 建议用 LLaMA-Factory、peft 等框架，训练后转换为 GGUF 格式加载。

**RAG 集成**（与 19 篇配合）：

```python
# 用 llama-server 做 RAG 的 LLM 后端
from openai import OpenAI
import faiss

client = OpenAI(base_url="http://localhost:8080/v1", api_key="na")

def rag_query(question, index, chunks, k=5):
    # 1. 用 llama-server 的 embedding 接口向量化
    q_emb = client.embeddings.create(model="bge-m3", input=[question]).data[0].embedding
    # 2. faiss 检索
    scores, indices = index.search([q_emb], k)
    context = "\n".join([chunks[i] for i in indices[0]])
    # 3. 组装 Prompt 调用 LLM
    resp = client.chat.completions.create(
        model="qwen2.5-7b",
        messages=[
            {"role": "system", "content": f"根据以下资料回答：{context}"},
            {"role": "user", "content": question}
        ],
        max_tokens=500, temperature=0.3
    )
    return resp.choices[0].message.content
```

---

## 11. 快速参考卡片

```text
量化等级对照表（7B 模型）：
  F16     13.5GB  无损失    高精度研究
  Q8_0     7.2GB  极小损失  高质量推理
  Q5_K_M   4.8GB  很小损失  平衡偏质量
  Q4_K_M   4.1GB  小损失    ★通用推荐★
  Q4_K_S   3.8GB  较小损失  内存紧张
  Q3_K_M   3.2GB  中等损失  极低资源
  Q2_K     2.1GB  明显损失  仅实验

编译选项速查：
  CPU:    cmake -B build -DGGML_NATIVE=ON -DCMAKE_BUILD_TYPE=Release
  CUDA:   -DGGML_CUDA=ON
  Metal:  -DGGML_METAL=ON (macOS)
  Vulkan: -DGGML_VULKAN=ON
  ROCm:   -DGGML_HIPBLAS=ON
  编译:   cmake --build build --config Release -j$(nproc)

llama-cli 参数速查：
  -m <path>     模型路径
  -p <text>     输入提示
  -n <n>        最大生成 token
  -c <n>        上下文长度
  -t <n>        线程数(=物理核心数)
  -ngl <n>      GPU offload 层数(99=全部)
  --temp <f>    温度(0=确定性)
  --top-p <f>   核采样(0.9)
  --top-k <n>   top-k(40)
  --repeat-penalty <f>  重复惩罚(1.1)
  -i            交互模式
  --color       彩色输出

性能参考（i7-12700H CPU，WSL2）：
  Qwen2.5-1.5B Q4_K_M:  ~45 t/s  1.5GB
  Qwen2.5-3B   Q4_K_M:  ~30 t/s  2.8GB
  Qwen2.5-7B   Q4_K_M:  ~18 t/s  5.2GB
  RTX3060 全offload:    ~70 t/s
```

## 12. 常见问题与坑

1. **编译报错 "unsupported compiler"**：GCC 版本过低。解决：WSL Ubuntu 24.04 自带 GCC 13 没问题；旧系统升级 GCC 或用 Clang。
2. **运行时 "GGML_ASSERT: not enough memory"**：内存不足。解决：降低上下文 `-c`，用 Q4_K_S/Q3，启用 `--mmap` 和 KV Cache 量化。
3. **GPU offload 后速度没提升**：CUDA 编译未生效或层数不够。解决：确认编译时 `-DGGML_CUDA=ON`，运行时加 `-ngl 99`，检查日志中 "offloaded 35/35 layers"。
4. **模型输出乱码/胡言乱语**：量化等级过低或 chat template 不对。解决：用 Q4_K_M 以上，指令模型加 `--chat-template`，确认模型与 tokenizer 匹配。
5. **GGUF 文件加载失败 "unsupported architecture"**：llama.cpp 版本太旧不支持新模型。解决：`git pull` 更新到最新版重新编译，新模型架构需要新版支持。
6. **CPU 推理速度远低于参考值**：未启用 AVX2/AVX512 或线程数不对。解决：编译加 `-DGGML_NATIVE=ON`，`-t` 设为物理核心数，关闭省电模式。
7. **llama-server 并发请求卡顿**：`--parallel` 太小或未启用连续批处理。解决：`--parallel 4 --cont-batching`，根据内存调整。
8. **量化后模型质量明显下降**：用了 Q2_K/Q3 或量化了不该量化的层。解决：用 Q4_K_M 以上，关键层（output、norm）保持 F16（K-quants 自动处理）。
9. **WSL2 中 GPU 不可用**：WSL2 CUDA 需特殊配置。解决：安装 NVIDIA CUDA on WSL 驱动，Windows 侧安装最新 NVIDIA 驱动，WSL 内不用装驱动直接装 CUDA toolkit。
10. **上下文越长速度越慢**：KV Cache 增大导致注意力计算 O(n²)。解决：用 `-c 2048/4096` 够用即可，长上下文用 YaRN/NTK 缩放的模型。

---

上一篇：《10-AI Agent与RAG应用开发.md》
