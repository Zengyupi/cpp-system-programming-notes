# Linux 命令行速查

> 本节目标：系统讲解 Linux 系统高级命令的使用方法，涵盖系统监控、进程管理、网络诊断、文本处理、存储管理、权限管理、包管理与日志管理等方向，学完后能够熟练运用各类命令完成 Linux 系统运维与开发调试工作。

## 本章速览

- [1. 概述](#1-概述)
- [2. 系统信息与监控](#2-系统信息与监控)
  - [2.1 系统信息查看](#21-系统信息查看)
  - [2.2 系统资源监控（实时）](#22-系统资源监控实时)
- [3. 进程管理](#3-进程管理)
  - [3.1 进程查看与操作](#31-进程查看与操作)
  - [3.2 进程状态与资源](#32-进程状态与资源)
- [4. 网络诊断](#4-网络诊断)
  - [4.1 网络连接与路由](#41-网络连接与路由)
  - [4.2 网络连通性测试](#42-网络连通性测试)
  - [4.3 网络流量分析](#43-网络流量分析)
- [5. 文本处理（高级）](#5-文本处理高级)
  - [5.1 流处理工具](#51-流处理工具)
  - [5.2 高级文本工具](#52-高级文本工具)
- [6. 存储与磁盘管理](#6-存储与磁盘管理)
  - [6.1 磁盘与分区](#61-磁盘与分区)
  - [6.2 文件系统检查与修复](#62-文件系统检查与修复)
  - [6.3 文件操作高级](#63-文件操作高级)
- [7. 权限与用户管理](#7-权限与用户管理)
- [8. 包管理](#8-包管理)
  - [8.1 Debian/Ubuntu (APT)](#81-debianubuntu-apt)
  - [8.2 RedHat/CentOS/Fedora (YUM/DNF)](#82-redhatcentosfedora-yumdnf)
  - [8.3 通用源码编译](#83-通用源码编译)
- [9. 日志管理](#9-日志管理)
- [10. 压缩与归档（扩展）](#10-压缩与归档扩展)
- [11. 系统管理与调试（内核级）](#11-系统管理与调试内核级)
- [12. 快捷参考卡片（按场景分类）](#12-快捷参考卡片按场景分类)
- [13. 命令速查索引](#13-命令速查索引)
- [14. 进阶学习路径推荐](#14-进阶学习路径推荐)

---

## 1. 概述

本文档收录 Linux 系统中**高频使用但非基础**的高级命令，涵盖**系统监控**、**进程管理**、**网络诊断**、**文本处理**、**存储管理**、**性能分析**等方向。每个命令均以 **表格 + 代码块** 形式呈现。

**基础命令（如 `ls`、`cd`、`cp`、`mv`、`rm`、`mkdir` 等）不在此文档重复收录。**

---

## 2. 系统信息与监控

### 2.1 系统信息查看

| 命令             | 说明                                       | 常用选项                                     |
| ---------------- | ------------------------------------------ | -------------------------------------------- |
| `uname -a`       | 显示系统内核版本、主机名、架构等全部信息   | `-a`（全部）、`-r`（内核版本）、`-m`（架构） |
| `lsb_release -a` | 显示 Linux 发行版详细信息（Debian/Ubuntu） | `-a`（全部）、`-d`（描述）、`-c`（代号）     |
| `hostnamectl`    | 查看/修改主机名及系统信息（systemd 系统）  | `set-hostname`（修改主机名）                 |
| `uptime`         | 查看系统运行时间、负载均值（1/5/15 分钟）  | -                                            |
| `dmesg`          | 查看内核环缓冲区消息（硬件/驱动日志）      | `-T`（时间戳）、`-w`（实时监控）             |
| `dmidecode`      | 查看硬件 DMI 信息（BIOS、主板、内存槽等）  | `-t`（按类型过滤）                           |
| `lscpu`          | 显示 CPU 架构信息（核心数、频率、缓存）    | -                                            |
| `lsmem`          | 显示内存布局和可用内存信息                 | -                                            |
| `lspci`          | 列出 PCI 设备（显卡、网卡等）              | `-v`（详细）、`-k`（驱动模块）               |
| `lsusb`          | 列出 USB 设备                              | `-t`（树形）、`-v`（详细）                   |

```bash
# 查看内核版本和系统架构
uname -a

# 查看发行版信息（CentOS/RHEL 用 cat /etc/os-release）
lsb_release -a

# 查看系统负载
uptime

# 查看硬件信息（内存条数量/频率）
sudo dmidecode -t memory

# 查看 CPU 详细信息
lscpu
```

### 2.2 系统资源监控（实时）

| 命令      | 说明                                 | 常用选项/交互键                                           |
| --------- | ------------------------------------ | --------------------------------------------------------- |
| `top`     | 实时进程资源监控（CPU/内存）         | `P`（按CPU排序）、`M`（按内存排序）、`q`（退出）          |
| `htop`    | top 增强版（彩色界面，支持鼠标操作） | `F2`（设置）、`F3`（搜索）、`F4`（过滤）、`F5`（树形）    |
| `atop`    | 更详细的系统监控（含磁盘/网络/进程） | `c`（进程）、`d`（磁盘）、`n`（网络）                     |
| `glances` | 跨平台系统监控工具（Web UI 支持）    | `-w`（Web 模式）、`-p`（指定端口）                        |
| `free`    | 查看内存使用（物理内存/交换分区）    | `-h`（人类可读）、`-m`（MB 单位）、`-s 2`（每2秒刷新）    |
| `vmstat`  | 虚拟内存统计（进程/内存/CPU/IO）     | `-s`（统计摘要）、`-d`（磁盘统计）                        |
| `iostat`  | 磁盘 IO 统计                         | `-x`（扩展统计）、`-k`（KB 单位）、间隔/次数              |
| `iotop`   | 按进程实时监控磁盘 IO                | `-o`（仅显示有 IO 的进程）、`-P`（按进程而非线程）        |
| `mpstat`  | 多处理器 CPU 统计                    | `-P ALL`（所有核心）、间隔/次数                           |
| `sar`     | 系统活动报告（需安装 sysstat）       | `-u`（CPU）、`-r`（内存）、`-n DEV`（网络）、`-d`（磁盘） |
| `nmon`    | 性能监控工具（生成数据文件供分析）   | `-f`（写入文件）、`-s`（采样间隔）                        |

```bash
# 实时监控（每2秒刷新，共5次）
vmstat 2 5

# 查看磁盘 IO 扩展统计
iostat -x 1

# 查看所有 CPU 核心使用率
mpstat -P ALL 1

# 查看网络统计（每1秒）
sar -n DEV 1

# 实时监控磁盘 IO 最高的进程
sudo iotop -o
```

---

## 3. 进程管理

### 3.1 进程查看与操作

| 命令              | 说明                                     | 常用选项                                               |
| ----------------- | ---------------------------------------- | ------------------------------------------------------ |
| `ps aux`          | 显示所有进程（BSD 风格）                 | `aux`（所有）、`auxf`（树形）、`auxww`（完整命令行）   |
| `ps -ef`          | 显示所有进程（System V 风格）            | `-ef`（所有）、`-eLf`（线程信息）                      |
| `pgrep`           | 按名称查找进程 PID                       | `-f`（匹配完整命令行）、`-l`（显示名称）、`-u`（用户） |
| `pkill`           | 按名称杀死进程                           | `-f`（匹配完整命令行）、`-9`（强制）、`-u`（用户）     |
| `kill`            | 发送信号给进程（默认 SIGTERM）           | `-9`（SIGKILL）、`-15`（SIGTERM）、`-1`（SIGHUP）      |
| `killall`         | 按名称杀死所有匹配进程                   | `-9`、`-u`（用户）、`-i`（交互确认）                   |
| `nice` / `renice` | 设置/调整进程优先级（-20 最高，19 最低） | `nice -n 10 ./program`、`renice -n 5 -p PID`           |
| `taskset`         | 绑定进程到指定 CPU 核心                  | `-c 0-3`（绑定到核心0-3）、`-p PID`（查询已绑定核心）  |
| `timeout`         | 在指定时间后终止进程                     | `timeout 10s ./program`                                |
| `watch`           | 周期性执行命令并全屏显示结果             | `-n 2`（间隔2秒）、`-d`（高亮变化）                    |

```bash
# 查看所有进程的完整命令行（ww 表示不截断超长命令行；如需环境变量用 ps eww）
ps auxww

# 查找名为 nginx 的所有进程 PID
pgrep -l nginx

# 杀死所有匹配 python 的进程
pkill -f python

# 绑定进程到 CPU 核心 0 和 1
taskset -c 0,1 ./program

# 每2秒查看内存使用情况
watch -n 2 free -h

# 运行程序，10秒后自动终止
timeout 10s ./long_running_program
```

### 3.2 进程状态与资源

| 命令           | 说明                        | 常用选项                                                     |
| -------------- | --------------------------- | ------------------------------------------------------------ |
| `lsof`         | 列出进程打开的文件/网络连接 | `-p PID`（指定进程）、`-i:端口`（端口）、`-u 用户`           |
| `strace`       | 跟踪进程的系统调用和信号    | `-p PID`（附加）、`-c`（汇总）、`-e trace=file`（仅文件操作） |
| `ltrace`       | 跟踪进程的动态库调用        | `-p PID`、`-c`（汇总）、`-e`（过滤库函数）                   |
| `/proc/<PID>/` | 查看进程的虚拟文件系统信息  | `cat /proc/PID/status`、`/proc/PID/fd/`（文件描述符）        |
| `pidstat`      | 按进程输出 CPU/内存/IO 统计 | `-u`（CPU）、`-r`（内存）、`-d`（IO）、间隔/次数             |

```bash
# 查看进程 1234 打开的所有文件
lsof -p 1234

# 查看占用 80 端口的进程
lsof -i :80

# 跟踪进程的系统调用（实时）
strace -p 1234

# 统计进程的系统调用次数
strace -c -p 1234

# 查看进程的 CPU 和内存使用
pidstat -u -r -p 1234 1
```

---

## 4. 网络诊断

### 4.1 网络连接与路由

| 命令       | 说明                                     | 常用选项                                                     |
| ---------- | ---------------------------------------- | ------------------------------------------------------------ |
| `ss`       | Socket 统计（netstat 替代品，更快）      | `-t`（TCP）、`-u`（UDP）、`-l`（监听）、`-n`（数字）、`-p`（进程） |
| `netstat`  | 网络连接/路由/接口统计（逐渐被 ss 替代） | `-tulnp`（常用组合）                                         |
| `ip`       | 网络接口/路由/邻居管理（ifconfig 替代）  | `ip a`（地址）、`ip r`（路由）、`ip neigh`（ARP）            |
| `route`    | 查看/修改路由表                          | `-n`（数字）、`add`/`del`                                    |
| `arp`      | 查看/修改 ARP 缓存                       | `-n`（数字）、`-a`（全部）                                   |
| `nslookup` | DNS 查询工具                             | `-type=A`（A 记录）、`-type=MX`（邮件交换）                  |
| `dig`      | DNS 查询工具（更详细，推荐）             | `+short`（简短）、`+trace`（递归追踪）、`-x`（反向查询）     |
| `host`     | DNS 查询工具（简洁版）                   | `-t A`（A 记录）、`-a`（全部）                               |
| `whois`    | WHOIS 查询（域名注册信息）               | -                                                            |

```bash
# 查看所有 TCP 监听端口及进程
ss -tlnp

# 查看所有连接（含 UDP）
netstat -tulnp

# 查看 IP 地址和接口信息
ip a

# 查看路由表
ip r

# 查询域名 A 记录（简洁输出）
dig +short example.com

# 反向 DNS 查询
dig -x 8.8.8.8

# 追踪 DNS 解析过程
dig +trace example.com
```

### 4.2 网络连通性测试

| 命令          | 说明                                      | 常用选项                                                     |
| ------------- | ----------------------------------------- | ------------------------------------------------------------ |
| `ping`        | ICMP 连通性测试                           | `-c 次数`（停止条件）、`-i 秒`（间隔）、`-s 字节`（包大小）、`-W 秒`（超时） |
| `traceroute`  | 路由追踪（UDP 探测）                      | `-n`（不解析域名）、`-I`（ICMP 探测）、`-T`（TCP 探测）      |
| `tracepath`   | 路由追踪（无需 root，更简单）             | `-n`（不解析域名）                                           |
| `mtr`         | 动态路由追踪 + ping 结合（My TraceRoute） | `-r`（报告模式）、`-c 次数`、`-n`（不解析域名）              |
| `nc` / `ncat` | Netcat，网络调试工具（TCP/UDP 收发）      | `-l`（监听）、`-v`（详细）、`-z`（扫描）、`-p 端口`          |
| `nmap`        | 网络扫描/端口扫描                         | `-sS`（SYN扫描）、`-sT`（TCP扫描）、`-p`（端口范围）、`-O`（操作系统检测） |
| `telnet`      | 远程登录/端口连通性测试                   | `host port`（测试端口）、`^]`（退出）                        |

```text
# 发送 10 个 ping 包，间隔 0.5 秒
ping -c 10 -i 0.5 8.8.8.8

# 路由追踪（不解析域名）
traceroute -n 8.8.8.8

# 动态路由追踪（实时显示）
mtr -n 8.8.8.8

# 测试端口是否开放（TCP）
nc -zv 192.168.1.1 80

# 端口扫描（常见端口）
nmap -sS -p 1-1000 192.168.1.1

# 测试 443 端口连通性
telnet example.com 443
```

### 4.3 网络流量分析

| 命令         | 说明                       | 常用选项                                                     |
| ------------ | -------------------------- | ------------------------------------------------------------ |
| `tcpdump`    | 抓包工具（详见独立文档）   | `-i`、`-w`、`-r`、`-n`、`port` 过滤                          |
| `tshark`     | Wireshark 命令行版         | `-i`（接口）、`-r`（读取）、`-Y`（显示过滤）、`-T fields`（字段提取） |
| `iftop`      | 实时流量监控（按连接显示） | `-i`（接口）、`-n`（不解析域名）、`-P`（显示端口）           |
| `nethogs`    | 按进程显示网络带宽使用     | `-d 1`（刷新间隔）、`-p`（混杂模式）                         |
| `bmon`       | 带宽监控（带图形界面）     | `-i`（接口）、`-p`（协议）                                   |
| `bandwidthd` | 流量统计（Web 图表）       | 需配置 `bandwidthd.conf`                                     |

```bash
# 实时查看网卡流量（按连接）
sudo iftop -i eth0 -n -P

# 按进程查看网络带宽使用
sudo nethogs -d 1

# 抓取 HTTP 流量（ASCII 显示）
sudo tcpdump -i any -A port 80 -c 100

# 使用 tshark 提取 HTTP 请求的 Host 字段
tshark -r capture.pcap -Y "http.request" -T fields -e http.host
```

---

## 5. 文本处理（高级）

### 5.1 流处理工具

| 命令    | 说明                                     | 常用选项/示例                                                |
| ------- | ---------------------------------------- | ------------------------------------------------------------ |
| `awk`   | 强大的文本处理语言（列处理/统计/格式化） | `awk '{print $1}'`、`awk -F: '{print $1}'`（分隔符）、`awk 'NR>1 && $3>100'` |
| `sed`   | 流编辑器（替换/删除/插入/转换）          | `sed 's/old/new/g'`（全局替换）、`sed -i`（直接修改）、`sed '/pattern/d'`（删除行） |
| `grep`  | 文本搜索                                 | `-E`（扩展正则）、`-v`（反选）、`-r`（递归）、`-A/B/C`（上下文行）、`-P`（Perl 正则） |
| `cut`   | 提取列（按分隔符或字符位置）             | `-d:`（分隔符）、`-f1,3`（字段）、`-c1-10`（字符位置）       |
| `sort`  | 排序                                     | `-n`（数字）、`-r`（倒序）、`-k 2`（按第2列）、`-u`（去重）、`-t:`（分隔符） |
| `uniq`  | 去重（必须配合 sort 使用）               | `-c`（计数）、`-d`（重复行）、`-u`（唯一行）                 |
| `wc`    | 行/字/字符统计                           | `-l`（行数）、`-w`（字数）、`-c`（字符数）                   |
| `tr`    | 字符转换/删除                            | `tr 'a-z' 'A-Z'`（大小写转换）、`tr -d '\n'`（删除换行）、`tr -s ' '`（压缩空格） |
| `paste` | 按列拼接文件                             | `-d:`（指定分隔符）                                          |
| `join`  | 按公共字段合并两个文件                   | `-t:`（分隔符）、`-1 1 -2 2`（指定连接列）                   |
| `comm`  | 比较两个排序文件的差异                   | `-1`（不显示文件1独有）、`-2`、`-3`                          |

```bash
# 打印所有进程的 PID（第2列）和完整命令（第11列）
ps aux | awk '{print $2, $11}'

# 按冒号分隔，打印用户名和 UID
awk -F: '{print $1, $3}' /etc/passwd

# 全局替换（将 old 替换为 new，仅修改第2行到第10行）
sed '2,10s/old/new/g' file.txt

# 删除空行
sed '/^$/d' file.txt

# 递归搜索代码中的 TODO
grep -r "TODO" --include="*.c" .

# 按第2列数字排序
sort -t: -k2 -n file.txt

# 统计日志中每个 IP 的访问次数
grep "GET /api" access.log | cut -d' ' -f1 | sort | uniq -c | sort -nr

# 统计文件行数
wc -l file.txt
```

### 5.2 高级文本工具

| 命令              | 说明                                | 常用选项                                                     |
| ----------------- | ----------------------------------- | ------------------------------------------------------------ |
| `jq`              | JSON 处理工具（命令行 JSON 解析器） | `.key`（访问属性）、`.[]`（数组遍历）、`map()`、`select()`、`-r`（原始输出） |
| `yq`              | YAML/XML/CSV 处理工具（jq 风格）    | `yq e '.a.b' file`（v4 语法）、`-i`（原地修改）             |
| `xmlstarlet`      | XML 处理工具                        | `sel`（选择）、`val`（验证）、`ed`（编辑）                   |
| `xargs`           | 将标准输入转为命令参数              | `-n 1`（每次传1个）、`-I {}`（占位符）、`-P 4`（并行执行）   |
| `parallel`        | 并行执行命令（比 xargs 更强大）     | `-j 4`（并行数）、`--dry-run`（预览）                        |
| `tee`             | 同时输出到文件和屏幕                | `-a`（追加模式）                                             |
| `column`          | 格式化列输出                        | `-t`（表格）、`-s`（分隔符）、`-n`（相邻分隔符不合并，适合含空字段的 CSV） |
| `hexdump` / `xxd` | 十六进制查看/转换                   | `-C`（经典格式）、`-b`（八进制）、`xxd -r`（反向转换）       |

```bash
# 解析 JSON（提取 name 字段）
echo '{"name": "test", "value": 123}' | jq '.name'

# 提取数组中所有 id
cat data.json | jq '.[] | .id'

# 使用 xargs 批量删除文件
find . -name "*.tmp" | xargs rm -f

# 并行压缩多个文件
ls *.log | parallel -j 4 gzip {}

# 格式化 /etc/passwd 为表格
cat /etc/passwd | column -t -s: -n

# 查看文件的十六进制内容
xxd file.bin | head -20
```

---

## 6. 存储与磁盘管理

### 6.1 磁盘与分区

| 命令               | 说明                             | 常用选项                                                |
| ------------------ | -------------------------------- | ------------------------------------------------------- |
| `df -h`            | 查看磁盘分区使用情况（人类可读） | `-h`（GB/MB）、`-T`（文件系统类型）、`-i`（inode）      |
| `du -sh`           | 查看目录/文件大小（汇总）        | `-sh *`（各子目录大小）、`-h --max-depth=1`（深度限制） |
| `lsblk`            | 列出块设备（树形结构）           | `-f`（文件系统）、`-m`（权限）、`-p`（完整路径）        |
| `fdisk -l`         | 查看/操作磁盘分区表              | `-l`（列出）、交互式操作（`n`新建、`d`删除、`w`写入）   |
| `parted`           | 磁盘分区工具（支持 GPT）         | `-l`（列出）、`mklabel`、`mkpart`、`resizepart`         |
| `blkid`            | 查看块设备的 UUID 和文件系统类型 | -                                                       |
| `mount` / `umount` | 挂载/卸载文件系统                | `-o`（选项）、`-t`（类型）、`-a`（全部挂载）            |
| `findmnt`          | 查找挂载点（树形/列表）          | `-l`（列表）、`-D`（磁盘空间使用）                      |
| `mkfs`             | 创建文件系统                     | `mkfs.ext4`、`mkfs.xfs`、`-t`（类型）                   |
| `tune2fs`          | 调整 ext2/ext3/ext4 文件系统参数 | `-l`（查看）、`-c`（挂载次数）、`-m`（保留块百分比）    |

```bash
# 查看磁盘使用情况（人类可读）
df -h

# 查看当前目录各子目录大小
du -sh * | sort -hr

# 列出所有块设备及文件系统
lsblk -f

# 查看分区表
sudo fdisk -l /dev/sda

# 查看块设备 UUID
blkid

# 挂载 ISO 文件
sudo mount -o loop ubuntu.iso /mnt/iso

# 查看文件系统参数
sudo tune2fs -l /dev/sda1
```

### 6.2 文件系统检查与修复

| 命令        | 说明                     | 常用选项                                                |
| ----------- | ------------------------ | ------------------------------------------------------- |
| `fsck`      | 文件系统检查与修复       | `-y`（自动修复）、`-f`（强制检查）、`-t`（类型）        |
| `badblocks` | 检查磁盘坏块             | `-s`（进度）、`-v`（详细）、`-w`（写测试）              |
| `smartctl`  | 查看磁盘 S.M.A.R.T. 状态 | `-a`（全部信息）、`-H`（健康状态）、`-t long`（长测试） |

```bash
# 检查并修复文件系统（需要卸载）
sudo fsck -y /dev/sda1

# 检查磁盘坏块（只读）
sudo badblocks -s -v /dev/sda

# 查看磁盘 S.M.A.R.T. 健康状态
sudo smartctl -H /dev/sda
```

### 6.3 文件操作高级

| 命令              | 说明                               | 常用选项                                                     |
| ----------------- | ---------------------------------- | ------------------------------------------------------------ |
| `rsync`           | 高效文件同步/备份（支持远程）      | `-avz`（归档+压缩）、`--delete`（删除目标多余文件）、`-e ssh`（SSH 通道） |
| `scp`             | 通过 SSH 传输文件                  | `-r`（递归）、`-P 端口`、`-C`（压缩）                        |
| `tar`             | 归档压缩工具                       | `-czvf`（创建 gz）、`-xzvf`（解压）、`-cjvf`（创建 bz2）、`-tf`（查看内容） |
| `zip` / `unzip`   | ZIP 格式压缩/解压                  | `-r`（递归）、`-d`（解压目录）                               |
| `gzip` / `gunzip` | gz 压缩/解压                       | `-k`（保留原文件）、`-9`（最大压缩）                         |
| `xz` / `unxz`     | xz 压缩/解压（高压缩率）           | `-k`（保留原文件）、`-9e`（最大压缩）                        |
| `dd`              | 块级复制（备份/写入镜像）          | `if=`（输入文件）、`of=`（输出文件）、`bs=`（块大小）、`status=progress`（进度） |
| `pv`              | 管道进度查看器（显示数据传输进度） | `-p`（进度条）、`-r`（速率）、`-s 大小`（指定总大小）        |
| `ln`              | 创建硬链接/软链接                  | `-s`（软链接）、`-f`（强制覆盖）                             |
| `file`            | 识别文件类型                       | -                                                            |

```bash
# 同步本地目录到远程服务器（增量）
rsync -avz /local/path/ user@host:/remote/path/

# 同步并删除目标多余文件
rsync -avz --delete /local/path/ /backup/path/

# 创建 tar.gz 压缩包
tar -czvf archive.tar.gz /path/to/dir

# 解压 tar.gz
tar -xzvf archive.tar.gz -C /target/dir

# 使用 dd 备份磁盘到文件（含进度）
sudo dd if=/dev/sda of=/backup/sda.img bs=4M status=progress

# 使用 dd 和 pv 显示进度
pv /dev/sda | sudo dd of=/backup/sda.img bs=4M

# 查看压缩包内容（不解压）
tar -tvf archive.tar.gz

# 文件类型识别
file /bin/bash
```

---

## 7. 权限与用户管理

| 命令                    | 说明                     | 常用选项                                                     |
| ----------------------- | ------------------------ | ------------------------------------------------------------ |
| `chown`                 | 修改文件/目录所有者      | `-R`（递归）、`user:group`（同时修改用户和组）               |
| `chgrp`                 | 修改文件/目录所属组      | `-R`（递归）                                                 |
| `chmod`                 | 修改文件/目录权限        | `-R`（递归）、`u+x`（用户添加执行）、`755`（数字模式）、`a=rwx`（全部用户） |
| `setfacl` / `getfacl`   | 设置/查看文件的 ACL 权限 | `-m`（修改）、`-x`（删除）、`-R`（递归）                     |
| `umask`                 | 设置默认文件权限掩码     | `umask 022`（新文件权限为 644）                              |
| `useradd` / `usermod`   | 添加/修改用户            | `-s`（shell）、`-G`（附加组）、`-d`（家目录）、`-m`（创建家目录） |
| `groupadd` / `groupmod` | 添加/修改组              | `-g`（GID）                                                  |
| `passwd`                | 修改用户密码             | `-e`（强制到期）、`-l`（锁定）、`-u`（解锁）                 |
| `chage`                 | 修改用户密码过期信息     | `-l`（查看）、`-M`（最大天数）、`-W`（警告天数）             |
| `sudo`                  | 以 root 身份执行命令     | `-u`（指定用户）、`-i`（交互式 shell）、`-l`（列出权限）     |
| `visudo`                | 安全编辑 /etc/sudoers    | -                                                            |
| `su`                    | 切换用户身份             | `-`（登录 shell）、`-l`（登录）                              |

```bash
# 递归修改目录所有者为 www:www
sudo chown -R www:www /var/www/html

# 递归修改权限为 755
sudo chmod -R 755 /var/www/html

# 查看文件的 ACL 权限
getfacl file.txt

# 为用户添加 ACL 读写权限
setfacl -m u:username:rw file.txt

# 添加新用户并指定 shell 和组
sudo useradd -m -s /bin/bash -G sudo newuser

# 查看用户密码过期信息
sudo chage -l username

# 以 root 身份执行命令
sudo -i
```

---

## 8. 包管理

### 8.1 Debian/Ubuntu (APT)

| 命令             | 说明                   | 常用选项                                          |
| ---------------- | ---------------------- | ------------------------------------------------- |
| `apt update`     | 更新软件包索引         | -                                                 |
| `apt upgrade`    | 升级所有已安装包       | `--dry-run`（模拟）                               |
| `apt install`    | 安装软件包             | `-y`（自动确认）                                  |
| `apt remove`     | 卸载软件包（保留配置） | `--purge`（清除配置）                             |
| `apt purge`      | 卸载软件包并清除配置   | -                                                 |
| `apt autoremove` | 自动移除无用依赖       | -                                                 |
| `apt search`     | 搜索软件包             | -                                                 |
| `apt show`       | 显示软件包详细信息     | -                                                 |
| `apt list`       | 列出软件包             | `--installed`（已安装）、`--upgradable`（可升级） |
| `dpkg`           | 底层包管理工具         | `-i`（安装 .deb）、`-r`（卸载）、`-l`（列出）     |

```bash
# 更新索引并升级所有包
sudo apt update && sudo apt upgrade -y

# 安装多个包
sudo apt install -y nginx mysql-server redis

# 搜索软件包
apt search python3

# 查看包详细信息
apt show nginx

# 安装本地 .deb 文件
sudo dpkg -i package.deb
sudo apt install -f  # 修复依赖
```

### 8.2 RedHat/CentOS/Fedora (YUM/DNF)

| 命令                                        | 说明         | 常用选项                                        |
| ------------------------------------------- | ------------ | ----------------------------------------------- |
| `yum update` / `dnf update`                 | 更新所有包   | `-y`                                            |
| `yum install` / `dnf install`               | 安装包       | `-y`                                            |
| `yum remove` / `dnf remove`                 | 卸载包       | -                                               |
| `yum search` / `dnf search`                 | 搜索包       | -                                               |
| `yum info` / `dnf info`                     | 显示包信息   | -                                               |
| `yum list installed` / `dnf list installed` | 列出已安装包 | -                                               |
| `rpm`                                       | 底层包管理   | `-ivh`（安装）、`-qa`（列出所有）、`-e`（卸载） |

```bash
# CentOS 7 使用 YUM
sudo yum install -y nginx

# CentOS 8+ 使用 DNF
sudo dnf install -y nginx

# 安装本地 RPM
sudo rpm -ivh package.rpm
```

### 8.3 通用源码编译

| 命令           | 说明                                        |
| -------------- | ------------------------------------------- |
| `./configure`  | 生成 Makefile（可指定 `--prefix` 安装路径） |
| `make`         | 编译                                        |
| `make install` | 安装                                        |
| `make clean`   | 清理编译产物                                |
| `make -j N`    | 并行编译（N 为核心数）                      |

```bash
# 典型源码编译安装流程
./configure --prefix=/usr/local/nginx
make -j$(nproc)
sudo make install
```

---

## 9. 日志管理

| 命令         | 说明                     | 常用选项                                                     |
| ------------ | ------------------------ | ------------------------------------------------------------ |
| `journalctl` | 查看 systemd 日志        | `-f`（实时）、`-u unit`（服务）、`-n 100`（行数）、`--since "1 hour ago"` |
| `tail -f`    | 实时查看文件末尾         | `-f`（实时）、`-n`（行数）                                   |
| `head`       | 查看文件开头             | `-n`（行数）                                                 |
| `less`       | 分页查看文件（支持搜索） | `/pattern`（搜索）、`n`（下一个）、`G`（末尾）               |
| `grep`       | 日志过滤（见文本处理）   | -                                                            |
| `logrotate`  | 日志轮转配置             | 配置文件 `/etc/logrotate.conf`                               |

```bash
# 实时查看 systemd 服务日志
journalctl -u nginx -f

# 查看最近 100 条日志
journalctl -n 100

# 查看指定时间范围内的日志
journalctl --since "2026-01-01 00:00:00" --until "2026-01-02 00:00:00"

# 实时查看日志文件
tail -f /var/log/nginx/access.log

# 使用 less 分页查看并搜索
less /var/log/syslog
# 按 / 输入关键字搜索，按 n 跳到下一个
```

---

## 10. 压缩与归档（扩展）

| 命令                       | 说明                       | 常用选项         |
| -------------------------- | -------------------------- | ---------------- |
| `tar`                      | 见存储管理章节             | -                |
| `gzip` / `gunzip`          | gz 压缩                    | `-k`、`-1~9`     |
| `bzip2` / `bunzip2`        | bz2 压缩（比 gz 压缩率高） | `-k`、`-1~9`     |
| `xz` / `unxz`              | xz 压缩（压缩率更高）      | `-k`、`-9e`      |
| `zcat` / `zless` / `zgrep` | 直接查看压缩文件内容       | 无需解压即可查看 |
| `zip` / `unzip`            | ZIP 格式                   | `-r`、`-d`       |

```bash
# 查看 gz 压缩文件内容
zcat file.log.gz

# 在 gz 文件中搜索关键字
zgrep "ERROR" file.log.gz

# 使用 xz 最大压缩
tar -cvJf archive.tar.xz /path  # -J 表示 xz
```

---

## 11. 系统管理与调试（内核级）

| 命令               | 说明                        | 常用选项                                                  |
| ------------------ | --------------------------- | --------------------------------------------------------- |
| `sysctl`           | 查看/修改内核参数           | `-a`（全部）、`-w`（写入）、`-p`（加载配置文件）          |
| `modprobe`         | 加载/卸载内核模块           | `-r`（卸载）、`-v`（详细）、`--show-depends`（显示依赖；新版无 `-l`，查可用模块用 `find /lib/modules/$(uname -r) -name '*.ko*'`） |
| `lsmod`            | 列出已加载内核模块          | -                                                         |
| `insmod` / `rmmod` | 底层模块加载/卸载（不推荐） | -                                                         |
| `dmesg`            | 内核环缓冲区消息            | `-T`、`-w`                                                |
| `systemctl`        | systemd 服务管理            | `start`、`stop`、`restart`、`enable`、`disable`、`status` |
| `service`          | sysvinit 服务管理（兼容）   | `start`、`stop`、`restart`、`status`                      |

```bash
# 查看所有内核参数
sysctl -a | grep net.ipv4

# 修改内核参数（临时）
sudo sysctl -w net.ipv4.ip_forward=1

# 永久生效：先在 /etc/sysctl.conf（或 /etc/sysctl.d/ 下新建文件）中写入
# net.ipv4.ip_forward=1，再执行下面命令加载
sudo sysctl -p

# 列出所有已加载模块
lsmod

# 加载模块
sudo modprobe nf_conntrack

# systemd 服务管理
sudo systemctl restart nginx
sudo systemctl enable nginx
sudo systemctl status nginx
```

---

## 12. 快捷参考卡片（按场景分类）

| 场景            | 命令                                                  |
| --------------- | ----------------------------------------------------- |
| 查看系统负载    | `uptime`、`top`、`htop`                               |
| 查看 CPU 信息   | `lscpu`、`mpstat -P ALL 1`                            |
| 查看内存信息    | `free -h`、`lsmem`、`vmstat -s`                       |
| 查看磁盘使用    | `df -h`、`du -sh *`、`lsblk -f`                       |
| 查看磁盘 IO     | `iostat -x 1`、`iotop -o`                             |
| 查看网络连接    | `ss -tulnp`、`netstat -tulnp`                         |
| 查看网络流量    | `iftop -n`、`nethogs -d 1`                            |
| 抓包分析        | `tcpdump -i any -nn port 80`                          |
| 路由追踪        | `traceroute -n`、`mtr -n`                             |
| DNS 查询        | `dig +short`、`nslookup`、`host`                      |
| 端口扫描        | `nmap -sS -p 1-1000`、`nc -zv`                        |
| 查找进程        | `ps aux \| grep`、`pgrep -l`                          |
| 杀死进程        | `kill`、`pkill`、`killall`                            |
| 查看文件描述符  | `lsof -p PID`、`lsof -i:端口`                         |
| 系统调用追踪    | `strace -p PID`、`strace -c`                          |
| 文本搜索        | `grep -r`、`awk`、`sed`                               |
| JSON 处理       | `jq`                                                  |
| 文件同步        | `rsync -avz`                                          |
| 备份/镜像       | `dd`、`pv`                                            |
| 查看日志        | `journalctl -u service -f`、`tail -f`                 |
| 修改权限        | `chown -R`、`chmod -R`、`setfacl`                     |
| 服务管理        | `systemctl start/stop/restart/status/enable`          |
| 内核参数        | `sysctl -a`、`sysctl -w`                              |
| 包管理 (Ubuntu) | `apt update && apt install`                           |
| 包管理 (CentOS) | `yum install` / `dnf install`                         |
| 源码编译        | `./configure && make -j$(nproc) && sudo make install` |

---

## 13. 命令速查索引

| 分类     | 命令列表                                                     |
| -------- | ------------------------------------------------------------ |
| 系统信息 | `uname`、`lsb_release`、`hostnamectl`、`uptime`、`dmesg`、`dmidecode`、`lscpu`、`lsmem`、`lspci`、`lsusb` |
| 资源监控 | `top`、`htop`、`atop`、`glances`、`free`、`vmstat`、`iostat`、`iotop`、`mpstat`、`sar`、`nmon` |
| 进程管理 | `ps`、`pgrep`、`pkill`、`kill`、`killall`、`nice`、`renice`、`taskset`、`timeout`、`watch`、`lsof`、`strace`、`ltrace`、`pidstat` |
| 网络诊断 | `ss`、`netstat`、`ip`、`route`、`arp`、`nslookup`、`dig`、`host`、`whois`、`ping`、`traceroute`、`tracepath`、`mtr`、`nc`、`nmap`、`telnet`、`tcpdump`、`tshark`、`iftop`、`nethogs` |
| 文本处理 | `awk`、`sed`、`grep`、`cut`、`sort`、`uniq`、`wc`、`tr`、`paste`、`join`、`comm`、`jq`、`yq`、`xmlstarlet`、`xargs`、`parallel`、`tee`、`column`、`hexdump`、`xxd` |
| 存储管理 | `df`、`du`、`lsblk`、`fdisk`、`parted`、`blkid`、`mount`、`umount`、`findmnt`、`mkfs`、`tune2fs`、`fsck`、`badblocks`、`smartctl`、`rsync`、`scp`、`tar`、`zip`、`gzip`、`xz`、`dd`、`pv`、`ln`、`file` |
| 权限管理 | `chown`、`chgrp`、`chmod`、`setfacl`、`getfacl`、`umask`、`useradd`、`usermod`、`groupadd`、`passwd`、`chage`、`sudo`、`visudo`、`su` |
| 包管理   | `apt`、`dpkg`、`yum`、`dnf`、`rpm`、`./configure`、`make`    |
| 日志管理 | `journalctl`、`tail`、`head`、`less`、`grep`、`logrotate`、`zcat`、`zgrep` |
| 系统调试 | `sysctl`、`modprobe`、`lsmod`、`systemctl`、`service`        |

---

## 14. 进阶学习路径推荐

| 阶段     | 命令重点                                                     |
| -------- | ------------------------------------------------------------ |
| 初级进阶 | `grep`、`sed`、`awk`、`find`、`xargs`、`ssh`、`scp`、`rsync`、`tar`、`systemctl`、`journalctl` |
| 中级进阶 | `strace`、`lsof`、`tcpdump`、`ss`、`dig`、`mtr`、`iostat`、`vmstat`、`sar`、`jq`、`parallel` |
| 高级进阶 | `perf`、`bpftrace`、`SystemTap`、`dtrace`、`crash`、`kgdb`、`ebpf` 工具链 |
| 性能调优 | `flamegraph`（火焰图）、`perf record/report`、`async-profiler`、`jmeter`/`ab`（压测） |

---

下一篇：《02-tcpdump网络抓包.md》
