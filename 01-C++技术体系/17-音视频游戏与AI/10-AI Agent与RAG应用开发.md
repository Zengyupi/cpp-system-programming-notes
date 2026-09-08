# AI Agent 与 RAG 应用开发

> 本节目标：从应用开发视角讲解 AI Agent 与 RAG（检索增强生成）的完整技术栈，学完后能够理解 Agent 的 LLM+工具+记忆+规划架构、掌握 RAG 的文档切分/向量化/检索/Prompt 组装全流程、对比向量数据库选型与 Embedding 模型、使用 LangChain 构建 Chain/Agent/Tool、实现 Ollama+llama.cpp+faiss 全本地 RAG。本篇是"开发 AI Agent 应用"视角，区别于 03 模块"用 AI 辅助写代码"。模型端侧推理部署见《03-端侧AI推理部署.md》，本地大模型量化见《11-llama.cpp量化与本地部署.md》。

## 本章速览

- [1. AI Agent 概念与架构](#1-ai-agent-概念与架构)
  - [1.1 Agent 核心四要素](#11-agent-核心四要素)
  - [1.2 与"AI 辅助编程"的区别](#12-与ai-辅助编程的区别)
- [2. RAG 原理与全流程](#2-rag-原理与全流程)
  - [2.1 检索增强生成原理](#21-检索增强生成原理)
  - [2.2 文档切分策略](#22-文档切分策略)
  - [2.3 向量化与相似度计算](#23-向量化与相似度计算)
- [3. 向量数据库](#3-向量数据库)
  - [3.1 faiss 本地向量索引](#31-faiss-本地向量索引)
  - [3.2 Milvus/Qdrant/Chroma 对比](#32-milvusqdrantchroma-对比)
  - [3.3 HNSW/IVF 索引原理](#33-hnswivf-索引原理)
- [4. Embedding 模型](#4-embedding-模型)
  - [4.1 主流模型对比](#41-主流模型对比)
  - [4.2 维度与相似度选择](#42-维度与相似度选择)
- [5. LangChain 架构](#5-langchain-架构)
  - [5.1 Chain/Agent/Tool/Memory/Retriever](#51-chainagenttoolmemoryretriever)
  - [5.2 LCEL（LangChain Expression Language）](#52-lcellangchain-expression-language)
- [6. Agent 框架与工具调用](#6-agent-框架与工具调用)
  - [6.1 ReAct 模式](#61-react-模式)
  - [6.2 Function Calling 工具调用](#62-function-calling-工具调用)
  - [6.3 多轮规划](#63-多轮规划)
- [7. 全本地 RAG 部署](#7-全本地-rag-部署)
  - [7.1 Ollama + llama.cpp + faiss 架构](#71-ollama--llamacpp--faiss-架构)
  - [7.2 完整实现代码](#72-完整实现代码)
- [8. 工程实践](#8-工程实践)
  - [8.1 文档预处理（清洗/切分/去重）](#81-文档预处理清洗切分去重)
  - [8.2 检索质量评估](#82-检索质量评估)
  - [8.3 重排序（Reranker）](#83-重排序reranker)
- [9. 快速参考卡片](#9-快速参考卡片)
- [10. 常见问题与坑](#10-常见问题与坑)

---

## 1. AI Agent 概念与架构

### 1.1 Agent 核心四要素

AI Agent 是能够自主感知环境、做出决策并执行动作的智能体，核心由四要素组成：

```text
┌─────────────────────────────────────────────────────┐
│                     AI Agent                         │
│                                                      │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐        │
│  │  LLM 大脑 │──>│  规划器   │──>│  工具调用 │        │
│  │ (推理决策)│   │ (任务分解)│   │ (执行动作)│        │
│  └──────────┘   └──────────┘   └────┬─────┘        │
│       ^                              │              │
│       │         ┌──────────┐         │ 结果         │
│       └─────────│  记忆模块 │<────────┘              │
│                 │(短期/长期)│                        │
│                 └──────────┘                        │
└─────────────────────────────────────────────────────┘
```

| 要素 | 说明 | 实现方式 |
| --- | --- | --- |
| **LLM（大脑）** | 推理、决策、自然语言理解与生成 | GPT-4、Claude、Qwen、Llama 等 |
| **工具（Tools）** | Agent 可调用的外部能力 | 搜索引擎、计算器、数据库、API、代码执行 |
| **记忆（Memory）** | 存储历史交互和知识 | 短期（对话上下文）、长期（向量数据库） |
| **规划（Planning）** | 任务分解与多步推理 | ReAct、Chain-of-Thought、Tree-of-Thought |

典型 Agent 循环：

```text
1. 感知：接收用户输入 + 记忆中的上下文
2. 推理：LLM 分析当前状态，决定下一步动作
3. 行动：调用工具（搜索/计算/查询/执行代码）
4. 观察：获取工具返回结果
5. 循环：回到步骤 2，直到任务完成或达到最大轮次
6. 回答：生成最终自然语言回复
```

### 1.2 与"AI 辅助编程"的区别

| 维度 | 03 模块：AI 辅助编程 | 本篇：AI Agent 应用开发 |
| --- | --- | --- |
| **视角** | 使用者视角——用 AI 工具写代码 | 开发者视角——构建 AI 应用产品 |
| **核心** | Cursor/Copilot 等工具的使用技巧 | Agent/RAG 架构设计与工程实现 |
| **产出** | 代码片段、代码审查、调试建议 | 智能客服、知识库问答、自动化 Agent |
| **技术栈** | Prompt 工程、AI IDE 配置 | LangChain、向量数据库、Embedding、工具调用 |
| **关注点** | 如何让 AI 更好地辅助编码 | 如何构建可靠、可评估、可部署的 AI 系统 |
| **示例** | "用 Cursor 重构这段 C++ 代码" | "开发一个基于企业文档的 RAG 问答系统" |

---

## 2. RAG 原理与全流程

### 2.1 检索增强生成原理

RAG（Retrieval-Augmented Generation）在 LLM 生成回答前，先从外部知识库检索相关文档，作为上下文注入 Prompt，从而减少幻觉、补充私有知识。

```text
用户问题
   │
   ▼
┌──────────┐    向量化     ┌──────────────┐
│ 问题编码  │ ───────────> │  向量检索     │
│ (Embed)  │              │ (Top-K 召回)  │
└──────────┘              └──────┬───────┘
                                 │ 相关文档片段
                                 ▼
┌──────────────────────────────────────────┐
│         Prompt 组装                       │
│  系统提示 + 检索文档 + 用户问题            │
└──────────────────┬───────────────────────┘
                   │
                   ▼
┌──────────┐    生成     ┌──────────┐
│   LLM    │ ─────────> │  回答     │
│ (生成器) │            │ (带引用)  │
└──────────┘            └──────────┘
```

RAG 相比微调（Fine-tuning）的优势：
- **知识可更新**：更新知识库即可，无需重新训练
- **可溯源**：回答可引用具体文档片段
- **成本低**：无需 GPU 训练，适合私有数据
- **减少幻觉**：基于检索事实生成

### 2.2 文档切分策略

文档切分（Chunking）是 RAG 质量的关键，切分过大丢失精度，过小丢失上下文。

| 策略 | 说明 | 适用场景 |
| --- | --- | --- |
| **固定长度切分** | 按字符数/token 数切分，可重叠 | 通用、简单 |
| **递归字符切分** | 按段落→句子→字符递归切分 | 结构化文档（Markdown/HTML） |
| **语义切分** | 按语义边界切分（Embedding 相似度突变点） | 高质量需求 |
| **文档结构切分** | 按标题层级（H1/H2/H3）切分 | 技术文档、手册 |
| **父子切分** | 小块检索、大块返回（Parent-Child） | 平衡精度与上下文 |

```python
from langchain.text_splitter import RecursiveCharacterTextSplitter

# 递归字符切分（推荐）
splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,        # 每块最大字符数
    chunk_overlap=50,      # 相邻块重叠字符数
    separators=["\n\n", "\n", "。", "！", "？", " ", ""],
    length_function=len,
)
chunks = splitter.split_text(long_document)
```

切分参数经验值：
- **通用问答**：chunk_size=500~1000，overlap=50~100
- **代码文档**：chunk_size=800~1500（代码块需完整），overlap=100~200
- **长文档摘要**：chunk_size=1000~2000，overlap=200

### 2.3 向量化与相似度计算

向量化将文本块转换为高维向量（Embedding），相似度计算用于检索。

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('BAAI/bge-large-zh-v1.5')
vectors = model.encode(chunks, normalize_embeddings=True)
# vectors.shape = (num_chunks, embedding_dim)
```

| 相似度 | 公式 | 适用场景 |
| --- | --- | --- |
| **Cosine（余弦）** | `cos(a,b) = a·b / (|a|·|b|)` | 最常用，向量归一化后等价于内积 |
| **IP（内积）** | `IP(a,b) = a·b` | 向量已归一化时等价于 cosine，计算更快 |
| **L2（欧氏距离）** | `L2(a,b) = ||a-b||` | 未归一化向量，faiss 默认 |

选择原则：
- Embedding 模型输出归一化向量 → 用 cosine/IP
- 未归一化 → 用 L2
- 中文模型（bge/m3e）通常归一化，用 cosine

---

## 3. 向量数据库

### 3.1 faiss 本地向量索引

faiss 是 Facebook 开源的向量检索库，C++ 实现，Python 绑定，适合本地/小规模场景。

```python
import faiss
import numpy as np

# 构建索引
dimension = 1024  # bge-large 维度
index = faiss.IndexFlatIP(dimension)  # 内积精确检索
index.add(vectors)  # vectors: (N, 1024) float32

# 检索
query_vec = model.encode(["用户问题"], normalize_embeddings=True)
scores, indices = index.search(query_vec, k=5)  # Top-5
for i, idx in enumerate(indices[0]):
    print(f"Top-{i+1} (score={scores[0][i]:.4f}): {chunks[idx][:100]}")

# 保存/加载
faiss.write_index(index, "index.faiss")
index = faiss.read_index("index.faiss")
```

### 3.2 Milvus/Qdrant/Chroma 对比

| 维度 | faiss | Chroma | Qdrant | Milvus |
| --- | --- | --- | --- | --- |
| **定位** | 本地库 | 轻量嵌入式 | 生产级向量数据库 | 分布式向量数据库 |
| **部署** | 库（pip install） | 嵌入式/客户端-服务器 | Docker/二进制 | Docker/K8s 集群 |
| **语言** | C++/Python | Python | Rust | C++/Go |
| **规模** | 百万级（单机） | 百万级 | 亿级 | 十亿级（分布式） |
| **过滤** | 需自行实现 | 支持 metadata 过滤 | 支持 payload 过滤 | 支持标量过滤 |
| **更新** | 全量重建 | 支持增量 | 支持增量 | 支持增量 |
| **适用** | 原型/本地/嵌入式 | 原型/小应用 | 中小生产 | 大规模生产 |

选型建议：
- **个人项目/原型**：faiss 或 Chroma
- **中小生产（单节点）**：Qdrant
- **大规模分布式**：Milvus

### 3.3 HNSW/IVF 索引原理

精确检索（Flat）在百万级向量时太慢，需要近似最近邻（ANN）索引。

**HNSW（Hierarchical Navigable Small World）**：
- 多层图结构，上层稀疏、下层稠密
- 检索时从上层入口开始，贪心向下层搜索
- 查询速度快，内存占用较高
- 参数：`M`（每层最大连接数，默认16）、`efConstruction`（构建时搜索宽度，默认200）、`efSearch`（查询时搜索宽度）

```python
# faiss HNSW 索引
index = faiss.IndexHNSWFlat(dimension, 32)  # M=32
index.hnsw.efConstruction = 200
index.hnsw.efSearch = 64
index.add(vectors)
```

**IVF（Inverted File）**：
- 先用 k-means 聚类得到 nlist 个中心
- 每个向量归属到最近的中心（倒排桶）
- 查询时只搜索 nprobe 个最近的桶
- 参数：`nlist`（聚类数，通常 sqrt(N)）、`nprobe`（搜索桶数）

```python
# faiss IVF + PQ 压缩索引
quantizer = faiss.IndexFlatIP(dimension)
index = faiss.IndexIVFPQ(quantizer, dimension, 100, 8, 8)
index.train(vectors)  # IVF 需要训练
index.add(vectors)
index.nprobe = 10
```

| 索引 | 速度 | 精度 | 内存 | 适用 |
| --- | --- | --- | --- | --- |
| Flat | 慢 | 100% | 高 | 小数据（<10万） |
| HNSW | 快 | 高 | 高 | 中数据，高精度 |
| IVF | 中 | 中 | 中 | 中大数据 |
| IVF-PQ | 很快 | 较低 | 很低 | 大数据，内存受限 |

---

## 4. Embedding 模型

### 4.1 主流模型对比

| 模型 | 维度 | 语言 | 特点 | 部署方式 |
| --- | --- | --- | --- | --- |
| **text-embedding-3-large** | 3072 | 多语言 | OpenAI，效果最好 | API |
| **text-embedding-3-small** | 1536 | 多语言 | OpenAI，性价比高 | API |
| **bge-large-zh-v1.5** | 1024 | 中文 | BAAI，中文检索SOTA | 本地（sentence-transformers） |
| **bge-m3** | 1024 | 多语言 | 支持稠密+稀疏+多向量 | 本地 |
| **m3e-large** | 1024 | 中文 | Moka，中文通用 | 本地 |
| **gte-large-zh** | 1024 | 中文 | 阿里，中文通用 | 本地 |
| **nomic-embed-text** | 768 | 多语言 | 开源，长上下文（8192） | 本地/Ollama |

中文场景推荐：
- **追求效果**：bge-large-zh-v1.5 或 bge-m3
- **资源受限**：bge-small-zh（384维）或 m3e-base
- **需要API**：OpenAI text-embedding-3-small

### 4.2 维度与相似度选择

```python
# bge-large-zh-v1.5 使用示例（中文检索效果最好）
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('BAAI/bge-large-zh-v1.5')

# 重要：bge 系列需要在查询前加 "为这个句子生成表示以用于检索相关文章："
# （instruction 对检索质量影响很大）
instruction = "为这个句子生成表示以用于检索相关文章："
query_vec = model.encode([instruction + query], normalize_embeddings=True)
doc_vecs = model.encode(chunks, normalize_embeddings=True)
```

维度选择经验：
- **384维**：快速原型、移动端、内存受限
- **768维**：平衡速度与精度
- **1024维**：生产推荐，中文检索精度高
- **1536+维**：极致精度，API 场景

---

## 5. LangChain 架构

### 5.1 Chain/Agent/Tool/Memory/Retriever

| 组件 | 说明 |
| --- | --- |
| **Chain** | 组合多个步骤的流水线（LLMChain、RetrievalQA、SequentialChain） |
| **Agent** | 使用 LLM 决定调用哪些工具、按什么顺序 |
| **Tool** | Agent 可调用的函数/API（搜索、计算器、数据库查询） |
| **Memory** | 存储对话历史（ConversationBufferMemory、ConversationSummaryMemory） |
| **Retriever** | 文档检索接口（VectorStoreRetriever、MultiQueryRetriever） |

```python
from langchain_openai import ChatOpenAI
from langchain.tools import Tool
from langchain.agents import initialize_agent, AgentType
from langchain.memory import ConversationBufferMemory

llm = ChatOpenAI(model="gpt-4o", temperature=0)

# 定义工具
def search_knowledge(query):
    # 从向量数据库检索
    docs = retriever.get_relevant_documents(query)
    return "\n".join([d.page_content for d in docs])

tools = [
    Tool(name="知识库检索", func=search_knowledge,
         description="查询企业内部知识库，回答产品/流程/技术问题"),
    Tool(name="计算器", func=lambda x: str(eval(x)),
         description="数学计算，输入数学表达式"),
]

memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

agent = initialize_agent(
    tools, llm, agent=AgentType.OPENAI_FUNCTIONS,
    memory=memory, verbose=True
)
agent.run("产品A的退货政策是什么？如果退货金额超过1000需要什么审批？")
```

### 5.2 LCEL（LangChain Expression Language）

LCEL 是 LangChain 的声明式组合语言，用 `|` 管道符组合组件，支持流式、并行、错误处理。

```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

# RAG Chain（LCEL 风格）
prompt = ChatPromptTemplate.from_template("""
根据以下上下文回答问题。如果上下文没有相关信息，回答"不知道"。
上下文：{context}
问题：{question}
""")

def format_docs(docs):
    return "\n\n".join([d.page_content for d in docs])

rag_chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)

# 调用
answer = rag_chain.invoke("如何配置产品A的网络？")

# 流式输出
for chunk in rag_chain.stream("如何配置产品A的网络？"):
    print(chunk, end="", flush=True)
```

LCEL 优势：
- **声明式**：代码即流水线，可读性强
- **流式**：自动支持 token 级流式输出
- **并行**：`RunnableParallel` 并行执行多个步骤
- **可观测**：集成 LangSmith 追踪

---

## 6. Agent 框架与工具调用

### 6.1 ReAct 模式

ReAct（Reasoning + Acting）是 Agent 的经典推理模式，交替进行思考和行动。

```text
问题：2024年北京的人口乘以2是多少？

Thought: 我需要先查询2024年北京的人口，然后乘以2。
Action: 搜索[2024年北京人口]
Observation: 2024年北京常住人口约2185.8万人。
Thought: 现在我知道人口是2185.8万，乘以2等于4371.6万。
Action: 计算器[2185.8 * 2]
Observation: 4371.6
Thought: 计算完成，答案是4371.6万人。
Final Answer: 2024年北京人口的2倍约为4371.6万人。
```

ReAct 的 Prompt 模板包含：工具描述、使用格式、少量示例（Few-shot）。

### 6.2 Function Calling 工具调用

现代 LLM（GPT-4、Claude、Qwen2 等）原生支持 Function Calling，比 ReAct 更可靠。

```python
# 定义工具 schema（OpenAI Function Calling 格式）
tools = [
    {
        "type": "function",
        "function": {
            "name": "query_database",
            "description": "查询订单数据库",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "订单号"},
                    "status": {"type": "string", "enum": ["pending", "shipped", "delivered"]}
                },
                "required": ["order_id"]
            }
        }
    }
]

# 调用 LLM
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "查询订单A12345的状态"}],
    tools=tools,
)

# 解析工具调用
tool_call = response.choices[0].message.tool_calls[0]
args = json.loads(tool_call.function.arguments)
result = query_database(**args)  # 实际执行

# 将结果返回给 LLM 生成最终回答
final = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "user", "content": "查询订单A12345的状态"},
        response.choices[0].message,
        {"role": "tool", "tool_call_id": tool_call.id, "content": str(result)}
    ]
)
```

### 6.3 多轮规划

复杂任务需要多轮规划，常见策略：

| 策略 | 说明 |
| --- | --- |
| **ReAct** | 边想边做，每步决定下一个动作 |
| **Plan-and-Execute** | 先制定完整计划，再逐步执行 |
| **Tree-of-Thought** | 探索多条推理路径，选择最优 |
| **Reflexion** | 执行后自我反思，修正后重试 |
| **Multi-Agent** | 多个 Agent 协作（规划者+执行者+审查者） |

```python
# Plan-and-Execute 示例（LangGraph）
from langgraph.graph import StateGraph

# 状态：{plan: [], current_step: int, results: [], final_answer: str}
def planner(state):
    # LLM 生成任务计划（步骤列表）
    state["plan"] = llm.invoke(f"分解任务：{state['task']}").steps
    return state

def executor(state):
    # 执行当前步骤
    step = state["plan"][state["current_step"]]
    result = agent.invoke(step)
    state["results"].append(result)
    state["current_step"] += 1
    return state

def should_continue(state):
    return "executor" if state["current_step"] < len(state["plan"]) else "final"

graph = StateGraph(dict)
graph.add_node("planner", planner)
graph.add_node("executor", executor)
graph.add_edge("planner", "executor")
graph.add_conditional_edges("executor", should_continue)
```

---

## 7. 全本地 RAG 部署

### 7.1 Ollama + llama.cpp + faiss 架构

全本地 RAG 不依赖任何外部 API，数据不出本机：

```text
┌─────────────────────────────────────────────────────┐
│                   用户查询                            │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│  Embedding 模型（Ollama: nomic-embed-text）          │
│  查询向量化                                          │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│  faiss 向量索引（本地文件）                            │
│  Top-K 检索                                          │
└──────────────────────┬──────────────────────────────┘
                       │ 相关文档片段
┌──────────────────────▼──────────────────────────────┐
│  Prompt 组装 → LLM（Ollama: qwen2.5:7b / llama3.1） │
│  llama.cpp 后端，CPU/GPU 本地推理                     │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                   生成回答                            │
└─────────────────────────────────────────────────────┘
```

### 7.2 完整实现代码

```python
# local_rag.py —— 全本地 RAG（Ollama + faiss）
import faiss
import numpy as np
import requests
import json

OLLAMA_URL = "http://localhost:11434/api"
EMBED_MODEL = "nomic-embed-text"
LLM_MODEL = "qwen2.5:7b"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

def embed(texts):
    """调用 Ollama Embedding API"""
    results = []
    for text in texts:
        resp = requests.post(f"{OLLAMA_URL}/embed", json={
            "model": EMBED_MODEL, "input": text
        })
        results.append(resp.json()["embeddings"][0])
    return np.array(results, dtype=np.float32)

def split_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """简单按段落+固定长度切分"""
    paragraphs = text.split("\n\n")
    chunks = []
    current = ""
    for p in paragraphs:
        if len(current) + len(p) > size and current:
            chunks.append(current.strip())
            current = current[-overlap:] + p
        else:
            current += "\n\n" + p
    if current.strip():
        chunks.append(current.strip())
    return chunks

def build_index(documents):
    """构建 faiss 索引"""
    chunks = []
    for doc in documents:
        chunks.extend(split_text(doc))
    vectors = embed(chunks)
    # 归一化后用内积（等价 cosine）
    faiss.normalize_L2(vectors)
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    return index, chunks

def query_rag(question, index, chunks, k=5):
    """RAG 查询"""
    q_vec = embed([question])
    faiss.normalize_L2(q_vec)
    scores, indices = index.search(q_vec, k)
    context = "\n\n".join([f"[片段{i+1}]\n{chunks[idx]}"
                           for i, idx in enumerate(indices[0])])
    prompt = f"""请根据以下上下文回答问题。如果上下文中没有答案，请回答"根据现有资料无法确定"。

上下文：
{context}

问题：{question}

回答："""
    resp = requests.post(f"{OLLAMA_URL}/generate", json={
        "model": LLM_MODEL, "prompt": prompt, "stream": False
    })
    return resp.json()["response"]

# 使用
if __name__ == "__main__":
    docs = [open("handbook.md", encoding="utf-8").read()]
    index, chunks = build_index(docs)
    faiss.write_index(index, "handbook.index")
    answer = query_rag("如何申请年假？", index, chunks)
    print(answer)
```

---

## 8. 工程实践

### 8.1 文档预处理（清洗/切分/去重）

```python
import re
from hashlib import md5

def clean_text(text):
    """文档清洗"""
    # 去除多余空白
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    # 去除 HTML 标签
    text = re.sub(r'<[^>]+>', '', text)
    # 去除 URL（可选）
    # text = re.sub(r'https?://\S+', '', text)
    return text.strip()

def deduplicate(chunks):
    """基于 MD5 去重"""
    seen = set()
    unique = []
    for c in chunks:
        h = md5(c.encode()).hexdigest()
        if h not in seen:
            seen.add(h)
            unique.append(c)
    return unique

# 完整预处理流水线
raw_docs = load_documents()
cleaned = [clean_text(d) for d in raw_docs]
all_chunks = []
for doc in cleaned:
    all_chunks.extend(split_text(doc))
all_chunks = deduplicate(all_chunks)
```

### 8.2 检索质量评估

RAG 评估指标：

| 指标 | 说明 | 方法 |
| --- | --- | --- |
| **Recall@K** | 相关文档在 Top-K 中的比例 | 人工标注相关文档 |
| **MRR** | 第一个相关文档的排名倒数 | 人工标注 |
| **Faithfulness** | 回答是否基于检索上下文（无幻觉） | LLM-as-Judge |
| **Answer Relevance** | 回答是否切题 | LLM-as-Judge |
| **Context Precision** | 相关文档是否排在前面 | 人工标注 |

```python
# LLM-as-Judge 评估忠实度
def evaluate_faithfulness(question, context, answer):
    prompt = f"""请判断回答是否完全基于上下文，没有编造信息。
上下文：{context}
问题：{question}
回答：{answer}
如果回答完全基于上下文，输出"忠实"；如果有编造，输出"不忠实"并说明。"""
    return llm.invoke(prompt)
```

### 8.3 重排序（Reranker）

向量检索（粗召回）后，用 Cross-Encoder 做精排（Rerank），显著提升 Top-K 精度。

```python
from sentence_transformers import CrossEncoder

# 粗召回：faiss 取 Top-20
scores, indices = index.search(q_vec, 20)
candidates = [chunks[i] for i in indices[0]]

# 精排：Cross-Encoder 对 (query, doc) 对打分
reranker = CrossEncoder('BAAI/bge-reranker-large')
pairs = [(question, doc) for doc in candidates]
rerank_scores = reranker.predict(pairs)

# 取精排 Top-5
top_indices = np.argsort(rerank_scores)[::-1][:5]
final_docs = [candidates[i] for i in top_indices]
```

常用 Reranker 模型：
- **bge-reranker-large**：BAAI，中文效果好
- **bge-reranker-v2-m3**：多语言，支持长文本
- **Cohere Rerank**：API，效果好但收费

Rerank 对质量提升显著（通常 Recall@5 提升 10~20%），但增加延迟，建议粗召回 20~50 条后精排 Top-3~5。

---

## 9. 快速参考卡片

```text
RAG 流程图：
  文档 → 清洗 → 切分(chunk) → Embedding → 向量库(索引)
  查询 → Embedding → 向量检索(Top-K) → Rerank → Prompt组装 → LLM → 回答

向量库选型表：
  faiss:     本地库，百万级，原型/嵌入式
  Chroma:    轻量，百万级，原型/小应用
  Qdrant:    Rust实现，亿级，中小生产
  Milvus:    分布式，十亿级，大规模生产

LangChain 组件速查：
  Chain:    LLMChain/RetrievalQA/SequentialChain
  Agent:    initialize_agent(OPENAI_FUNCTIONS/REACT)
  Tool:     Tool(name, func, description)
  Memory:   ConversationBufferMemory/SummaryMemory
  Retriever: VectorStoreRetriever/MultiQueryRetriever
  LCEL:     prompt | llm | parser，支持stream/parallel

faiss 代码模板：
  index = faiss.IndexFlatIP(dim)       # 精确内积
  index = faiss.IndexHNSWFlat(dim, 32) # HNSW近似
  faiss.normalize_L2(vecs)             # 归一化
  index.add(vecs); index.search(q, k)  # 检索
  faiss.write_index(index, path)       # 保存
```

## 10. 常见问题与坑

1. **检索结果不相关**：切分策略不当或 Embedding 模型不匹配。解决：用递归字符切分，中文用 bge-large-zh，加 Reranker。
2. **回答幻觉（编造信息）**：LLM 不基于检索内容回答。解决：Prompt 中明确"只根据上下文回答，不知道就说不知道"，加 Faithfulness 评估。
3. **上下文窗口溢出**：检索片段太多超过 LLM 上下文。解决：控制 Top-K（3~5），用 map-reduce 或 refine 策略处理长文档。
4. **Embedding 维度不匹配**：文档和查询用不同模型编码。解决：统一模型，索引构建和查询用同一个 Embedding 模型。
5. **bge 模型检索效果差**：忘记加 instruction 前缀。解决：查询前加 "为这个句子生成表示以用于检索相关文章："。
6. **faiss 内存不足**：百万级向量用 Flat 索引占内存大。解决：用 HNSW 或 IVF-PQ 压缩索引，降低维度。
7. **Agent 工具调用死循环**：LLM 反复调用同一个工具无进展。解决：设置最大迭代次数（max_iterations=5），加早期停止条件。
8. **文档更新后索引未更新**：全量重建索引成本高。解决：用支持增量更新的向量库（Qdrant/Milvus），或按文档 ID 增量更新。
9. **多语言混合检索效果差**：中文文档用英文 Embedding 模型。解决：用多语言模型（bge-m3、text-embedding-3）或分语言建索引。
10. **RAG 延迟高**：Embedding + 检索 + LLM 全链路慢。解决：Embedding 批量预计算，检索用 HNSW，LLM 流式输出，Rerank 只对 Top-20 精排。

---

上一篇：《09-ROS2实操要点.md》
下一篇：《11-llama.cpp量化与本地部署.md》
