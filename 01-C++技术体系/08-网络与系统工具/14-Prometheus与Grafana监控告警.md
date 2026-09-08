# Prometheus 与 Grafana 监控告警

> 本节目标：建立现代监控告警体系的完整知识——理解 Prometheus 的 Pull 模型与 TSDB 架构、掌握四种指标类型与 PromQL 查询、能够配置 Exporter 与服务发现、熟练使用 Grafana 构建 Dashboard、配置 Alertmanager 告警路由与通知。系统级命令监控配合《10-Linux系统监控命令族.md》，eBPF 深度可观测配合《12-eBPF可观测性技术.md》。以下配置基于 Prometheus 2.53、Grafana 11.1、Alertmanager 0.27，在 Ubuntu 24.04 上验证可用。

## 本章速览

- [0. Prometheus 架构](#0-prometheus-架构)
- [1. 数据模型与指标类型](#1-数据模型与指标类型)
- [2. PromQL 查询语言](#2-promql-查询语言)
- [3. Exporter 安装配置](#3-exporter-安装配置)
- [4. 服务发现](#4-服务发现)
- [5. Grafana Dashboard](#5-grafana-dashboard)
- [6. Alertmanager 告警](#6-alertmanager-告警)
- [7. 快速参考卡片](#7-快速参考卡片)
- [8. 常见问题与坑](#8-常见问题与坑)

---

## 0. Prometheus 架构

### 0.1 核心组件

```text
┌─────────────────────────────────────────────────────────────┐
│                        Prometheus Server                      │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌────────┐  │
│  │ Retrival │──→│   TSDB   │──→│  PromQL  │──→│  HTTP  │  │
│  │ (Pull)   │   │ (存储)   │   │ (查询)   │   │  API   │  │
│  └────┬─────┘   └──────────┘   └──────────┘   └───┬────┘  │
│       │                                               │       │
│       │  ┌──────────────┐                            │       │
│       └──│ Service Disc.│                            │       │
│          │ (服务发现)    │                            │       │
│          └──────────────┘                            │       │
└──────────────────────────────────────────────────────┼───────┘
        │                │                │              │
        ▼                ▼                ▼              ▼
  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
  │node_     │   │mysqld_   │   │redis_    │   │  应用     │
  │exporter  │   │exporter  │   │exporter  │   │  内置     │
  │(机器指标) │   │(MySQL)   │   │(Redis)   │   │  /metrics │
  └──────────┘   └──────────┘   └──────────┘   └──────────┘

  Prometheus ──→ Alertmanager ──→ 邮件/企微/Webhook
  Prometheus ──→ Grafana ──→ Dashboard 展示
```

| 组件 | 职责 |
| --- | --- |
| **Prometheus Server** | 核心：定时 Pull 指标、存储 TSDB、提供 PromQL 查询 API |
| **Exporter** | 被监控端：暴露 `/metrics` HTTP 端点，把第三方指标转为 Prometheus 格式 |
| **Alertmanager** | 告警管理：接收 Prometheus 告警，做分组/抑制/路由/通知 |
| **Grafana** | 可视化：通过 PromQL 查询 Prometheus，渲染 Dashboard |
| **Pushgateway** | （可选）短生命周期任务的指标推送网关（Prometheus 是 Pull 模型） |

### 0.2 Pull 模型

Prometheus 采用 **Pull（拉）模型**：Prometheus Server 主动去 Exporter 的 `/metrics` 端点抓数据，而不是 Exporter 主动推。

Pull 模型的优势：
- **Prometheus 控制抓取节奏**：可以统一配置抓取间隔（`scrape_interval`），避免被监控端压力不均。
- **健康检查内置**：抓不到就是目标挂了，`up` 指标直接反映目标存活。
- **水平扩展简单**：新增目标只需在配置中加地址，不需要被监控端改配置。
- **调试方便**：直接 `curl http://target:9100/metrics` 就能看到原始指标。

Pull 模型的局限：
- 短生命周期任务（如批处理、CI Job）可能在 Prometheus 抓取前就结束了 → 用 Pushgateway。
- 网络隔离/NAT 环境下 Prometheus 无法直接访问目标 → 用联邦集群（federation）或 Pushgateway。

### 0.3 最小配置

```yaml
# /etc/prometheus/prometheus.yml
global:
  scrape_interval: 15s          # 全局抓取间隔
  evaluation_interval: 15s      # 告警规则评估间隔

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['localhost:9093']

rule_files:
  - /etc/prometheus/rules/*.yml

scrape_configs:
  - job_name: 'prometheus'      # 监控 Prometheus 自身
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'node'            # 监控机器指标
    static_configs:
      - targets: ['localhost:9100', '192.168.1.10:9100']
```

启动：

```bash
# Docker 方式（最快）
docker run -d --name prometheus -p 9090:9090 \
  -v /etc/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml \
  prom/prometheus:v2.53.0

# 二进制方式
useradd --no-create-home --shell /bin/false prometheus
./prometheus --config.file=/etc/prometheus/prometheus.yml \
  --storage.tsdb.path=/var/lib/prometheus \
  --storage.tsdb.retention.time=30d
```

访问 `http://localhost:9090` 打开 Prometheus Web UI，`Status → Targets` 查看抓取目标状态。

---

## 1. 数据模型与指标类型

### 1.1 数据模型

Prometheus 的数据模型核心是**时间序列（Time Series）**，由指标名 + 一组标签（Label）唯一标识。

```text
metric_name{label1="value1", label2="value2"} timestamp value
```

| 概念 | 含义 |
| --- | --- |
| `Metric Name` | 指标名，如 `node_cpu_seconds_total`、`http_requests_total` |
| `Label` | 键值对，用于维度区分，如 `{instance="10.0.0.1:9100", mode="idle"}` |
| `Sample` | 一个数据点：时间戳（毫秒）+ 值（float64） |
| `Time Series` | 同一指标名+标签组合的所有 Sample 序列 |
| `Instant Vector` | 某一时刻，多个时间序列的最新值（瞬时向量） |
| `Range Vector` | 一段时间范围内，每个时间序列的所有值（区间向量） |

标签命名规范：
- 标签名用 `_` 分隔小写单词，如 `status_code`、`instance_type`。
- `instance`（目标地址 `host:port`）和 `job`（抓取任务名）是 Prometheus 自动附加的标签。
- 避免高基数标签（如 `user_id`、`request_id`、`ip`），每个标签值组合都是一条独立时间序列，高基数会导致 TSDB 膨胀。

### 1.2 四种指标类型

| 类型 | 含义 | 特点 | 典型指标 |
| --- | --- | --- | --- |
| **Counter** | 只增不减的计数器 | 重启归零，永远单调递增；用 `rate()` 算速率 | `http_requests_total`、`node_cpu_seconds_total` |
| **Gauge** | 可增可减的瞬时值 | 反映当前状态，直接取值 | `node_memory_MemAvailable_bytes`、`go_goroutines` |
| **Histogram** | 直方图：统计样本落在各 bucket 的数量 | 客户端分桶，`_bucket`（累积）、`_sum`、`_count`；可算分位数 | `http_request_duration_seconds` |
| **Summary** | 摘要：客户端直接计算分位数 | 客户端算 φ-quantile，`_sum`、`_count`、`{quantile="0.99"}`；不可聚合 | `rpc_duration_seconds` |

**Counter vs Gauge 选型**：
- 问"总共发生了多少次"→ Counter（请求数、错误数、CPU 时间）
- 问"当前是多少"→ Gauge（内存使用、连接数、温度、队列长度）

**Histogram vs Summary 选型**：

| 维度 | Histogram | Summary |
| --- | --- | --- |
| 分位数计算 | 服务端（Prometheus 用 `histogram_quantile`） | 客户端（应用直接算） |
| 可聚合 | 可以（`sum` 聚合 bucket 后再算分位数） | 不可以（分位数不能平均） |
| 精度 | 受 bucket 边界影响（近似） | 精确（客户端滑动窗口） |
| 性能开销 | 低（只计数） | 中（需维护分位数算法） |
| 适用 | 需要跨实例/服务聚合分位数 | 只看单实例精确分位数 |

> **生产环境优先用 Histogram**：因为 Summary 的分位数无法跨实例聚合（不能把两个实例的 P99 取平均），而 Histogram 可以先聚合 bucket 再算全局分位数。

---

## 2. PromQL 查询语言

### 2.1 基本查询

```promql
# 瞬时向量：所有时间序列的最新值
node_memory_MemAvailable_bytes

# 按标签过滤
node_memory_MemAvailable_bytes{instance="10.0.0.1:9100"}

# 标签匹配符：=（等于）、!=（不等）、=~（正则匹配）、!~（正则不匹配）
node_cpu_seconds_total{mode=~"user|system"}
http_requests_total{status!~"2.."}

# 区间向量：过去 5 分钟的所有数据点
node_memory_MemAvailable_bytes[5m]

# 偏移量：1 小时前的瞬时值
node_memory_MemAvailable_bytes offset 1h
```

时间单位：`s`（秒）、`m`（分）、`h`（时）、`d`（天）、`w`（周）、`y`（年）。

### 2.2 函数

| 函数 | 用途 | 示例 |
| --- | --- | --- |
| `rate()` | Counter 每秒平均增长率（区间向量） | `rate(http_requests_total[5m])` |
| `irate()` | Counter 瞬时增长率（用最后两个点） | `irate(http_requests_total[5m])` |
| `increase()` | Counter 区间内增长量 | `increase(http_requests_total[1h])` |
| `sum()` | 求和聚合 | `sum(rate(http_requests_total[5m]))` |
| `avg()` | 平均聚合 | `avg(node_memory_MemAvailable_bytes)` |
| `max()` / `min()` | 最大/最小 | `max(node_load1)` |
| `count()` | 计数 | `count(up == 0)` |
| `topk()` | 前 K 个 | `topk(5, rate(http_requests_total[5m]))` |
| `histogram_quantile()` | Histogram 算分位数 | `histogram_quantile(0.99, rate(http_request_duration_bucket[5m]))` |
| `label_replace()` | 替换/新增标签 | `label_replace(up, "host", "$1", "instance", "(.*):.*")` |
| `absent()` | 时间序列不存在时返回 1 | `absent(up{job="mysql"})` |
| `clamp_max/min()` | 截断值范围 | `clamp_max(node_load1, 100)` |

### 2.3 rate vs irate

这是 PromQL 最容易混淆的两个函数：

| 函数 | 算法 | 特点 | 适用场景 |
| --- | --- | --- | --- |
| `rate()` | 区间内首尾两点的斜率（线性回归） | 平滑，反映平均速率；会抹平尖峰 | 常规监控、告警（看趋势） |
| `irate()` | 区间内最后两个数据点的斜率 | 灵敏，反映瞬时速率；能捕捉尖峰 | 调试、看瞬时突发 |

> **告警用 `rate()`，调试用 `irate()`**。`irate` 对采样间隔敏感，如果抓取间隔是 15s，`irate` 用的是最后两个 15s 间隔的点，波动会很大；`rate` 用 5m 窗口平均更稳定。

### 2.4 聚合操作

```promql
# sum by：按标签分组求和
sum by (instance) (rate(node_cpu_seconds_total{mode!="idle"}[5m]))

# sum without：排除指定标签后求和
sum without (cpu, mode) (rate(node_cpu_seconds_total[5m]))

# 常用聚合：sum / avg / max / min / count / count_values / bottomk / topk / quantile / stddev / stdvar

# 实例 CPU 使用率（按 instance 聚合所有核）
100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

# 内存使用率
100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)

# 磁盘使用率
100 * (1 - node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay"})
```

### 2.5 常用查询模板

```promql
# 【存活检测】目标是否在线
up == 0

# 【CPU 使用率】过去 5 分钟平均
100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

# 【负载】1 分钟 load average（按核数归一化）
node_load1 / count by (instance) (node_cpu_seconds_total{mode="idle"})

# 【内存使用率】
100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)

# 【Swap 使用率】
100 * (1 - node_memory_SwapFree_bytes / node_memory_SwapTotal_bytes)

# 【磁盘 IO 利用率】
rate(node_disk_io_time_seconds_total[5m]) * 100

# 【网络入站带宽】bps
rate(node_network_receive_bytes_total{device!~"lo|docker.*|veth.*"}[5m]) * 8

# 【网络出站带宽】bps
rate(node_network_transmit_bytes_total{device!~"lo|docker.*|veth.*"}[5m]) * 8

# 【TCP 连接数】
node_netstat_Tcp_CurrEstab

# 【文件描述符使用率】
100 * (node_filefd_allocated / node_filefd_maximum)

# 【HTTP QPS】
sum by (instance, path) (rate(http_requests_total[5m]))

# 【HTTP 错误率】
sum by (instance) (rate(http_requests_total{status=~"5.."}[5m]))
/
sum by (instance) (rate(http_requests_total[5m])) * 100

# 【HTTP P99 延迟】Histogram
histogram_quantile(0.99, sum by (le, path) (rate(http_request_duration_seconds_bucket[5m])))

# 【MySQL 连接数使用率】
100 * (mysql_global_status_threads_connected / mysql_global_variables_max_connections)

# 【Redis 内存使用率】
100 * (redis_memory_used_bytes / redis_memory_max_bytes)
```

---

## 3. Exporter 安装配置

### 3.1 node_exporter — 机器指标

node_exporter 是最常用的 Exporter，暴露 CPU、内存、磁盘、网络、文件系统等机器级指标。

```bash
# 下载安装
wget https://github.com/prometheus/node_exporter/releases/download/v1.8.2/node_exporter-1.8.2.linux-amd64.tar.gz
tar xzf node_exporter-1.8.2.linux-amd64.tar.gz
cp node_exporter-1.8.2.linux-amd64/node_exporter /usr/local/bin/

# systemd 服务
cat > /etc/systemd/system/node_exporter.service << 'EOF'
[Unit]
Description=Node Exporter
After=network.target

[Service]
User=node_exporter
ExecStart=/usr/local/bin/node_exporter \
  --web.listen-address=:9100 \
  --collector.filesystem.mount-points-exclude="^/(sys|proc|dev|run)($|/)" \
  --collector.netdev.device-exclude="lo|docker.*|veth.*"

[Install]
WantedBy=multi-user.target
EOF

useradd --no-create-home --shell /bin/false node_exporter
systemctl daemon-reload
systemctl enable --now node_exporter

# 验证
curl http://localhost:9100/metrics | head -20
```

Prometheus 配置中添加：

```yaml
scrape_configs:
  - job_name: 'node'
    static_configs:
      - targets: ['10.0.0.1:9100', '10.0.0.2:9100']
```

### 3.2 mysqld_exporter — MySQL 指标

```bash
# MySQL 中创建监控用户
CREATE USER 'exporter'@'localhost' IDENTIFIED BY 'xxx' WITH MAX_USER_CONNECTIONS 3;
GRANT PROCESS, REPLICATION CLIENT, SELECT ON *.* TO 'exporter'@'localhost';

# 安装
wget https://github.com/prometheus/mysqld_exporter/releases/download/v0.15.1/mysqld_exporter-0.15.1.linux-amd64.tar.gz
tar xzf mysqld_exporter-0.15.1.linux-amd64.tar.gz
cp mysqld_exporter-0.15.1.linux-amd64/mysqld_exporter /usr/local/bin/

# 配置文件（.my.cnf 格式）
cat > /etc/mysqld_exporter.cnf << 'EOF'
[client]
user=exporter
password=xxx
host=localhost
port=3306
EOF

# systemd 服务
cat > /etc/systemd/system/mysqld_exporter.service << 'EOF'
[Unit]
Description=MySQL Exporter
After=network.target

[Service]
User=mysqld_exporter
ExecStart=/usr/local/bin/mysqld_exporter \
  --config.my-cnf=/etc/mysqld_exporter.cnf \
  --web.listen-address=:9104 \
  --collect.info_schema.processlist \
  --collect.info_schema.innodb_metrics

[Install]
WantedBy=multi-user.target
EOF
```

### 3.3 redis_exporter — Redis 指标

```bash
# 安装
wget https://github.com/oliver006/redis_exporter/releases/download/v1.62.0/redis_exporter-v1.62.0.linux-amd64.tar.gz
tar xzf redis_exporter-v1.62.0.linux-amd64.tar.gz
cp redis_exporter-v1.62.0.linux-amd64/redis_exporter /usr/local/bin/

# systemd 服务
cat > /etc/systemd/system/redis_exporter.service << 'EOF'
[Unit]
Description=Redis Exporter
After=network.target

[Service]
User=redis_exporter
ExecStart=/usr/local/bin/redis_exporter \
  --redis.addr=redis://localhost:6379 \
  --redis.password=xxx \
  --web.listen-address=:9121

[Install]
WantedBy=multi-user.target
EOF
```

### 3.4 应用内置指标

应用自己暴露 `/metrics` 端点是最灵活的方式。Prometheus 官方提供了 Go/Java/Python/Ruby 等语言的客户端库。

Go 示例：

```go
import (
    "github.com/prometheus/client_golang/prometheus"
    "github.com/prometheus/client_golang/prometheus/promhttp"
    "net/http"
)

var (
    httpRequests = prometheus.NewCounterVec(
        prometheus.CounterOpts{
            Name: "http_requests_total",
            Help: "Total HTTP requests",
        },
        []string{"path", "status"},
    )
    httpDuration = prometheus.NewHistogramVec(
        prometheus.HistogramOpts{
            Name:    "http_request_duration_seconds",
            Help:    "HTTP request duration",
            Buckets: prometheus.DefBuckets, // 0.005s ~ 10s
        },
        []string{"path"},
    )
)

func init() {
    prometheus.MustRegister(httpRequests, httpDuration)
}

func main() {
    http.Handle("/metrics", promhttp.Handler())
    http.ListenAndServe(":8080", nil)
}
```

---

## 4. 服务发现

静态配置（`static_configs`）适合少量固定目标；动态环境（容器、K8s、自动扩缩容）需要服务发现。

### 4.1 静态配置

```yaml
scrape_configs:
  - job_name: 'node'
    static_configs:
      - targets: ['10.0.0.1:9100', '10.0.0.2:9100']
        labels:
          env: 'prod'
          region: 'cn-shenzhen'
```

### 4.2 文件服务发现

目标列表写在 JSON/YAML 文件中，Prometheus 定时（默认 5m）重新加载，适合配置管理工具（Ansible/Terraform）维护。

```yaml
# /etc/prometheus/targets/node.yml
- targets: ['10.0.0.1:9100', '10.0.0.2:9100']
  labels:
    env: 'prod'
- targets: ['10.0.1.1:9100']
  labels:
    env: 'staging'
```

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'node'
    file_sd_configs:
      - files: ['/etc/prometheus/targets/*.yml']
        refresh_interval: 30s
```

### 4.3 Consul 服务发现

```yaml
scrape_configs:
  - job_name: 'consul-services'
    consul_sd_configs:
      - server: 'consul-server:8500'
        services: ['web', 'api', 'mysql']  # 只发现指定服务，留空发现全部
    relabel_configs:
      - source_labels: [__meta_consul_service]
        target_label: job
      - source_labels: [__meta_consul_tags]
        regex: .*prod.*
        action: keep    # 只保留带 prod 标签的服务
```

### 4.4 relabel_configs（重标记）

relabel 是 Prometheus 服务发现的核心机制，在抓取前对目标标签进行修改/过滤。

| action | 用途 |
| --- | --- |
| `replace` | 替换标签值（默认 action） |
| `keep` | 保留匹配的目标，丢弃其他 |
| `drop` | 丢弃匹配的目标 |
| `labelmap` | 把匹配的标签名映射为新标签名 |
| `labeldrop` | 删除匹配的标签 |
| `labelkeep` | 只保留匹配的标签 |

常用 relabel 示例：

```yaml
relabel_configs:
  # 1. 用 __address__ 中的 host 部分作为 instance 标签
  - source_labels: [__address__]
    regex: '(.*):\d+'
    target_label: instance
    replacement: '${1}'

  # 2. 只抓取端口为 9100 的目标
  - source_labels: [__meta_consul_service_port]
    regex: '9100'
    action: keep

  # 3. 把 Consul 元数据标签转为 Prometheus 标签
  - source_labels: [__meta_consul_metadata_env]
    target_label: env
```

---

## 5. Grafana Dashboard

### 5.1 安装与配置

```bash
# Docker 方式
docker run -d --name grafana -p 3000:3000 grafana/grafana:11.1.0

# 访问 http://localhost:3000，默认 admin/admin
```

添加 Prometheus 数据源：`Connections → Data sources → Add data source → Prometheus`，URL 填 `http://prometheus:9090`。

### 5.2 Dashboard 核心概念

| 概念 | 含义 |
| --- | --- |
| **Panel** | 面板，Dashboard 的基本单元（图、表、统计数字等） |
| **Query** | 每个 Panel 的 PromQL 查询语句 |
| **Variable** | 变量，用于动态过滤（如 `$instance`、`$job`、`$env`） |
| **Row** | 行，用于分组 Panel（可折叠） |
| **Time Range** | 时间范围（右上角选择，如 Last 1 hour、Last 7 days） |
| **Refresh** | 自动刷新间隔 |

### 5.3 变量配置

变量是 Grafana Dashboard 的灵魂，让一个 Dashboard 适配多实例/多服务。

| 变量类型 | 用途 | 示例 |
| --- | --- | --- |
| `Query` | 用 PromQL 查询动态获取标签值 | `label_values(node_memory_MemTotal_bytes, instance)` |
| `Custom` | 手动定义选项 | `prod,staging,dev` |
| `Interval` | 时间间隔变量 | `1m,5m,15m,1h` |
| `Datasource` | 数据源切换 | 多 Prometheus 实例 |

Query 类型变量常用写法：

```promql
# 获取所有 instance
label_values(up, instance)

# 获取指定 job 的 instance
label_values(up{job="node"}, instance)

# 获取所有 job
label_values(up, job)

# 获取所有 MySQL 实例
label_values(mysql_up, instance)
```

在 Panel 查询中引用变量：

```promql
# $instance 变量（单选）
node_memory_MemAvailable_bytes{instance="$instance"}

# $instance 变量（多选，Regex 模式）
node_memory_MemAvailable_bytes{instance=~"$instance"}

# $interval 变量作为 rate 窗口
rate(http_requests_total[$interval])
```

### 5.4 常用面板类型

| 面板类型 | 适用场景 | 示例 |
| --- | --- | --- |
| **Time series** | 时序折线图（最常用） | CPU 使用率趋势、QPS 趋势 |
| **Stat** | 大数字 + 趋势小图 | 当前 QPS、当前在线人数 |
| **Gauge** | 仪表盘（百分比/量程） | 磁盘使用率、内存使用率 |
| **Table** | 表格 | 各实例指标汇总、TOP N |
| **Bar chart** | 柱状图 | 各服务请求量对比 |
| **Pie chart** | 饼图 | 状态码分布、错误类型占比 |
| **Heatmap** | 热力图 | 延迟分布（Histogram bucket 随时间变化） |
| **Status history** | 状态时间线 | 告警状态变化、服务可用性 |

### 5.5 导入社区模板

Grafana 官网有大量社区贡献的 Dashboard，直接导入即可用：

1. 访问 https://grafana.com/grafana/dashboards/
2. 搜索关键词（如 `node exporter`、`mysql`、`redis`）
3. 复制 Dashboard ID（如 `1860` 是经典 Node Exporter Full）
4. Grafana 中 `Dashboards → New → Import`，粘贴 ID，选择数据源

常用 Dashboard ID：

| 监控对象 | Dashboard ID | 名称 |
| --- | --- | --- |
| Node Exporter | 1860 | Node Exporter Full |
| MySQL | 7362 | MySQL Overview |
| Redis | 763 | Redis Dashboard for Prometheus |
| Nginx | 12708 | NGINX exporter |
| Docker | 12290 | Docker and System Monitoring |
| Prometheus 自身 | 3662 | Prometheus 2.0 Overview |
| Blackbox | 13698 | Blackbox Exporter |

---

## 6. Alertmanager 告警

### 6.1 告警规则

告警规则定义在 Prometheus 中（不是 Alertmanager），Prometheus 定期评估表达式，满足条件时向 Alertmanager 发送告警。

```yaml
# /etc/prometheus/rules/alerts.yml
groups:
  - name: node_alerts
    rules:
      # 实例宕机
      - alert: InstanceDown
        expr: up == 0
        for: 1m                    # 持续 1 分钟才触发（避免瞬时抖动）
        labels:
          severity: critical
        annotations:
          summary: "Instance {{ $labels.instance }} down"
          description: "{{ $labels.instance }} of job {{ $labels.job }} has been down for more than 1 minute."

      # CPU 使用率 > 80%
      - alert: HighCPUUsage
        expr: 100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 80
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High CPU usage on {{ $labels.instance }}"
          description: "CPU usage is {{ $value | printf \"%.2f\" }}% for more than 5 minutes."

      # 内存使用率 > 85%
      - alert: HighMemoryUsage
        expr: 100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) > 85
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High memory usage on {{ $labels.instance }}"
          description: "Memory usage is {{ $value | printf \"%.2f\" }}%."

      # 磁盘使用率 > 90%
      - alert: HighDiskUsage
        expr: 100 * (1 - node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay"}) > 90
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "High disk usage on {{ $labels.instance }} {{ $labels.mountpoint }}"
          description: "Disk usage is {{ $value | printf \"%.2f\" }}%."

      # HTTP 5xx 错误率 > 5%
      - alert: HighHTTPErrorRate
        expr: |
          sum by (instance) (rate(http_requests_total{status=~"5.."}[5m]))
          /
          sum by (instance) (rate(http_requests_total[5m])) * 100 > 5
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "High HTTP 5xx error rate on {{ $labels.instance }}"
          description: "Error rate is {{ $value | printf \"%.2f\" }}%."
```

告警状态流转：`Inactive`（未触发）→ `Pending`（表达式为真但未满 `for` 时间）→ `Firing`（已触发，发送通知）。

### 6.2 Alertmanager 配置

Alertmanager 负责接收 Prometheus 的告警，做**分组（group）、抑制（inhibit）、静默（silence）、路由（route）、通知（receiver）**。

```yaml
# /etc/alertmanager/alertmanager.yml
global:
  resolve_timeout: 5m
  smtp_smarthost: 'smtp.example.com:587'
  smtp_from: 'alertmanager@example.com'
  smtp_auth_username: 'alertmanager@example.com'
  smtp_auth_password: 'xxx'

# 告警模板（可选，自定义通知格式）
templates:
  - '/etc/alertmanager/templates/*.tmpl'

# 路由树
route:
  group_by: ['alertname', 'cluster', 'service']
  group_wait: 30s        # 组内第一条告警等 30s 再发（凑批）
  group_interval: 5m      # 同组新告警间隔
  repeat_interval: 4h     # 重复通知间隔（避免轰炸）
  receiver: 'default'
  routes:
    - matchers:
        - severity = critical
      receiver: 'critical-team'
      repeat_interval: 1h
    - matchers:
        - severity = warning
      receiver: 'warning-team'

# 抑制规则：critical 告警触发时抑制同实例的 warning
inhibit_rules:
  - source_matchers:
      - severity = critical
    target_matchers:
      - severity = warning
    equal: ['instance', 'job']    # 同 instance + job 才抑制

# 通知接收者
receivers:
  - name: 'default'
    email_configs:
      - to: 'oncall@example.com'
        send_resolved: true

  - name: 'critical-team'
    email_configs:
      - to: 'critical@example.com'
        send_resolved: true
    webhook_configs:
      - url: 'http://webhook.example.com/alert'   # 企微/钉钉/飞书机器人
        send_resolved: true

  - name: 'warning-team'
    email_configs:
      - to: 'warning@example.com'
        send_resolved: true
```

### 6.3 通知渠道

| 渠道 | 配置方式 |
| --- | --- |
| 邮件 | `email_configs`（SMTP） |
| 企业微信 | `webhook_configs`（群机器人 Webhook）或 `wechat_configs`（企业微信应用） |
| 钉钉 | `webhook_configs`（自定义机器人） |
| 飞书 | `webhook_configs`（自定义机器人） |
| Slack | `slack_configs` |
| PagerDuty | `pagerduty_configs` |
| 通用 Webhook | `webhook_configs`（POST JSON 到任意 URL） |

企业微信机器人 Webhook 示例（需要在群里添加机器人获取 Webhook URL）：

```yaml
receivers:
  - name: 'wechat-bot'
    webhook_configs:
      - url: 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx'
        send_resolved: true
        # Alertmanager 默认发的是 Alertmanager 格式 JSON，企微需要 markdown 格式
        # 需要用 alertmanager-webhook-adapter 或自定义模板转换
```

> 企微/钉钉/飞书的 Webhook 不直接兼容 Alertmanager 的 JSON 格式，通常需要一个中间适配器（如 `prometheus-webhook-dingtalk`、`alertmanager-wechatrobot-webhook`）把 Alertmanager 的 JSON 转为对应平台的消息格式。

---

## 7. 快速参考卡片

### 7.1 PromQL 常用查询模板

```promql
【存活】
up == 0                                              目标宕机
count(up == 0) by (job)                              各 job 宕机数

【CPU】
100 - avg by(instance)(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100   CPU 使用率
node_load1 / count by(instance)(node_cpu_seconds_total{mode="idle"})             归一化 load

【内存】
100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)           内存使用率
100 * (1 - node_memory_SwapFree_bytes / node_memory_SwapTotal_bytes)              Swap 使用率

【磁盘】
100 * (1 - node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay"})   磁盘使用率
rate(node_disk_io_time_seconds_total[5m]) * 100                                    IO 利用率

【网络】
rate(node_network_receive_bytes_total{device!~"lo|docker.*|veth.*"}[5m]) * 8     入站带宽 bps
rate(node_network_transmit_bytes_total{device!~"lo|docker.*|veth.*"}[5m]) * 8    出站带宽 bps
node_netstat_Tcp_CurrEstab                                                           TCP 连接数

【应用】
sum by(instance, path)(rate(http_requests_total[5m]))                               QPS
sum by(instance)(rate(http_requests_total{status=~"5.."}[5m])) / sum by(instance)(rate(http_requests_total[5m])) * 100   5xx 错误率
histogram_quantile(0.99, sum by(le, path)(rate(http_request_duration_seconds_bucket[5m])))   P99 延迟

【MySQL】
100 * (mysql_global_status_threads_connected / mysql_global_variables_max_connections)   连接数使用率
rate(mysql_global_status_slow_queries[5m])                                            慢查询速率

【Redis】
100 * (redis_memory_used_bytes / redis_memory_max_bytes)                              内存使用率
rate(redis_commands_processed_total[5m])                                               QPS
redis_connected_clients                                                                 连接数
```

### 7.2 指标类型选型

```text
Counter（只增不减）：  请求数、错误数、CPU 时间、字节数、处理时长累计
  → 用 rate()/increase() 算速率/增量

Gauge（可增可减）：    内存使用、连接数、队列长度、温度、在线人数、缓存命中率
  → 直接取值或 avg/max

Histogram（客户端分桶）：请求延迟、响应大小、处理时间
  → 用 histogram_quantile() 算分位数，可跨实例聚合

Summary（客户端算分位）：单实例精确分位数
  → 不可跨实例聚合，优先用 Histogram
```

### 7.3 告警规则模板

```yaml
# 宕机
- alert: InstanceDown
  expr: up == 0
  for: 1m
  labels: { severity: critical }

# CPU > 80%
- alert: HighCPU
  expr: 100 - (avg by(instance)(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 80
  for: 5m
  labels: { severity: warning }

# 内存 > 85%
- alert: HighMemory
  expr: 100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) > 85
  for: 5m
  labels: { severity: warning }

# 磁盘 > 90%
- alert: HighDisk
  expr: 100 * (1 - node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay"}) > 90
  for: 10m
  labels: { severity: critical }

# 5xx 错误率 > 5%
- alert: HighErrorRate
  expr: sum by(instance)(rate(http_requests_total{status=~"5.."}[5m])) / sum by(instance)(rate(http_requests_total[5m])) * 100 > 5
  for: 2m
  labels: { severity: critical }

# P99 延迟 > 1s
- alert: HighLatency
  expr: histogram_quantile(0.99, sum by(le)(rate(http_request_duration_seconds_bucket[5m]))) > 1
  for: 5m
  labels: { severity: warning }
```

### 7.4 常用端口与命令

```text
Prometheus Server:    9090   http://localhost:9090
Alertmanager:         9093   http://localhost:9093
Grafana:              3000   http://localhost:3000 (admin/admin)
node_exporter:        9100   curl http://localhost:9100/metrics
mysqld_exporter:      9104
redis_exporter:       9121
Pushgateway:          9091

# 热加载配置（修改 prometheus.yml 或规则后）
curl -X POST http://localhost:9090/-/reload
# 或发送 SIGHUP
kill -HUP $(pgrep prometheus)

# 查看目标状态
http://localhost:9090/targets

# 查看告警状态
http://localhost:9090/alerts

# 查看 Alertmanager 告警
http://localhost:9093/#/alerts
```

---

## 8. 常见问题与坑

1. **`rate()` 用于 Gauge 类型是错的**：`rate()` 只对 Counter（单调递增）有意义；Gauge 用 `avg_over_time()`、`max_over_time()` 等 `_over_time` 函数。对 Gauge 用 `rate()` 会得到无意义的结果（Gauge 下降时 rate 为负）。
2. **Counter 重启归零导致 `rate()` 出现尖峰**：Counter 在进程重启后从 0 开始，`rate()` 内部会检测到这种"重置"并处理（只取非负增长），但如果抓取间隔太大（如 5m）且重启在间隔内发生，可能计算不准；用 `irate()` 对瞬时更敏感，或确保抓取间隔足够小（≤ 15s）。
3. **Histogram 的 bucket 边界不合适导致分位数不准**：`histogram_quantile` 是基于 bucket 的线性插值，bucket 边界太粗（如默认 bucket 最大 10s，但实际延迟 30s）会导致分位数估算偏差大；根据业务延迟分布自定义 `Buckets`，确保 P99 落在 bucket 范围内而不是最后一个 bucket。
4. **高基数标签导致 TSDB 爆炸**：每个标签值组合都是一条独立时间序列，`user_id`、`request_id`、`ip`、`session_id` 等高基数标签会让时间序列数从几百涨到几百万，TSDB 内存和磁盘暴涨，查询变慢；标签值应该是有限枚举（如 `status`、`method`、`endpoint`、`instance`），不要用唯一 ID。
5. **`up == 0` 告警但服务实际正常**：`up` 反映的是 Prometheus 能否抓到 `/metrics`，抓不到可能是网络不通、防火墙拦截、Exporter 挂了、Exporter 端口错了，不一定是业务服务挂了；排查时先 `curl http://target:port/metrics` 确认 Exporter 本身是否正常。
6. **告警风暴**：一个根因（如网络分区）触发几百条告警，`group_by` 和 `inhibit_rules` 是关键——按 `alertname`/`cluster`/`service` 分组，critical 抑制 warning，`group_wait` 凑批发送；否则告警渠道被淹没，真正重要的告警被忽略。
7. **`for` 时间太短导致告警抖动**：`for: 30s` 的告警在指标瞬时波动时反复触发/恢复，造成告警风暴；常规指标用 `for: 5m`，关键存活检测用 `for: 1m`，只有真正需要快速响应的（如磁盘满）才用更短时间。
8. **Grafana 变量多选时查询报错**：变量多选时，PromQL 中要用 `=~"$var"`（正则匹配）而不是 `="$var"`（精确匹配），因为多选变量的值是 `value1|value2` 的正则形式。
9. **Prometheus 本地存储不是长期存储**：Prometheus 的 TSDB 设计为短期存储（默认 15 天），不适合长期趋势分析和海量数据；长期存储用远程写入（`remote_write`）到 Thanos、Mimir、VictoriaMetrics、Cortex 等分布式存储。
10. **抓取间隔不一致导致 `rate()` 结果偏差**：`rate(http_requests_total[5m])` 假设 5m 窗口内有足够的数据点，如果抓取间隔是 1m，5m 窗口只有 5 个点，统计意义弱；确保 `rate` 窗口至少是抓取间隔的 4-10 倍（如 15s 抓取用 5m 窗口）。
11. **`increase()` 结果不是整数**：`increase()` 是 `rate() * 窗口时长`，由于外推算法（extrapolation），即使 Counter 实际增长了 1，`increase()` 可能返回 1.2 或 0.8；这是正常的，不要期望整数结果。
12. **Alertmanager 的 `repeat_interval` 不生效**：`repeat_interval` 是从**上次发送**开始算的，如果告警在 `repeat_interval` 内有更新（如新标签、同组新告警），会重新计时；确保 `group_by` 合理，避免同组频繁更新导致重复通知。

---

上一篇：《13-netfilter与iptables防火墙.md》
