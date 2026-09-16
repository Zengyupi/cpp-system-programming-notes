# -*- coding: utf-8 -*-
"""曾庆松 C++ 开发工程师简历生成脚本(单页 A4)"""
import re
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor

W, H = A4
M = 40  # 页边距

pdfmetrics.registerFont(TTFont('YH', r'C:\Windows\Fonts\msyh.ttc', subfontIndex=0))
pdfmetrics.registerFont(TTFont('YHB', r'C:\Windows\Fonts\msyhbd.ttc', subfontIndex=0))

DEEP = HexColor('#1B3A6B')   # 深蓝
BRIGHT = HexColor('#2E6FD8') # 亮蓝
LIGHT = HexColor('#EAF1FB')  # 浅蓝底
GRAY = HexColor('#5A6472')
DARK = HexColor('#24303F')
LINE = HexColor('#C9D6E8')

BODY = 8.3
LEAD = 11.25

def sw(t, f, s):
    return pdfmetrics.stringWidth(t, f, s)

TOK = re.compile(r'[A-Za-z0-9_@.\-/:+&#%()]+|\s+|.')

def tokenize(segs):
    out = []
    for text, font, size, color in segs:
        for m in TOK.finditer(text):
            t = m.group(0)
            if t.isspace():
                out.append((' ', font, size, color))
            else:
                out.append((t, font, size, color))
    return out

def draw_rich(c, segs, x, y, width, leading=LEAD, hang=0, size=BODY):
    """绘制富文本段落,自动换行;返回下一段落基线 y"""
    toks = tokenize(segs)
    lines, cur, curw = [], [], 0.0
    for tok, f, s, col in toks:
        w = sw(tok, f, s)
        if cur and curw + w > width:
            lines.append(cur)
            cur, curw = [], 0.0
            if tok == ' ':
                continue
        if not cur and tok == ' ':
            continue
        cur.append((tok, f, s, col, curw))
        curw += w
    if cur:
        lines.append(cur)
    for i, line in enumerate(lines):
        lx = x + (hang if i > 0 else 0)
        for tok, f, s, col, off in line:
            c.setFont(f, s)
            c.setFillColor(col)
            c.drawString(lx + off, y - i * leading, tok)
    return y - len(lines) * leading

def seg(text, font='YH', size=BODY, color=DARK):
    return (text, font, size, color)

def bold(text, size=BODY, color=DEEP):
    return (text, 'YHB', size, color)

def num(text):
    """蓝色加粗量化数据"""
    return (text, 'YHB', BODY, BRIGHT)

def bullet(segs, c, y, width, x=M):
    """带蓝色方块符号 + 悬挂缩进的条目"""
    sym = ('▪ ', 'YH', 7.2, BRIGHT)
    hang = sw('▪ ', 'YH', 7.2)
    return draw_rich(c, [sym] + segs, x, y, width, hang=hang)

def section(c, y, title):
    """分节标题:蓝色方块竖条 + 加粗标题 + 细分隔线"""
    c.setFillColor(DEEP)
    c.rect(M, y - 3.2, 3.5, 13.5, fill=1, stroke=0)
    c.setFillColor(DEEP)
    c.setFont('YHB', 12.2)
    c.drawString(M + 9.5, y, title)
    c.setStrokeColor(LINE)
    c.setLineWidth(0.7)
    c.line(M, y - 7.5, W - M, y - 7.5)
    return y - 22

def job_header(c, y, company, role, date, width):
    c.setFillColor(DARK)
    c.setFont('YHB', 9.6)
    c.drawString(M, y, company)
    c.setFillColor(GRAY)
    c.setFont('YH', 8.3)
    c.drawString(M + sw(company, 'YHB', 9.6) + 6, y, role)
    c.setFillColor(GRAY)
    c.setFont('YH', 8.3)
    c.drawRightString(W - M, y, date)
    return y - LEAD - 2.5

def proj_header(c, y, name, tag):
    c.setFillColor(DARK)
    c.setFont('YHB', 9.4)
    c.drawString(M, y, name)
    nw = sw(name, 'YHB', 9.4)
    c.setFillColor(GRAY)
    c.setFont('YH', 7.6)
    c.drawString(M + nw + 7, y + 0.6, tag)
    return y - 12.5

def proj_stack(c, y, text):
    c.setFillColor(GRAY)
    c.setFont('YH', 7.8)
    c.drawString(M, y, text)
    return y - LEAD

c = canvas.Canvas(r'f:\桌面\学习内容\个人\曾庆松-C++开发工程师(Rust正在学习)-简历.pdf', pagesize=A4)
c.setTitle('曾庆松 - C++开发工程师 - 简历')

# ============ 页首色带 ============
BAND_H = 62
c.setFillColor(DEEP)
c.rect(0, H - BAND_H, W, BAND_H, fill=1, stroke=0)
c.setFillColor(BRIGHT)
c.rect(0, H - BAND_H - 4, W, 4, fill=1, stroke=0)

c.setFillColor(HexColor('#FFFFFF'))
c.setFont('YHB', 25)
c.drawString(M, H - 42, '曾庆松')
c.setFont('YH', 10.5)
c.drawString(M + sw('曾庆松', 'YHB', 25) + 12, H - 40, 'C++ / Rust 开发工程师')

right_l1 = '电话 18379221443  ·  邮箱 2698067866@qq.com'
right_l2 = '出生 2001.10  ·  现居深圳'
c.setFont('YH', 8.6)
c.drawRightString(W - M, H - 30, right_l1)
c.drawRightString(W - M, H - 45, right_l2)

y = H - BAND_H - 4 - 20

# ============ GitHub 行 ============
gh = [seg('GitHub  ', 'YH', 9.0, GRAY),
      ('github.com/Zengyupi/cpp-system-programming-notes', 'YHB', 9.0, BRIGHT),
      seg('  （204 篇技术笔记开源 · 长期维护）', 'YH', 8.3, GRAY)]
y = draw_rich(c, gh, M, y, W - 2 * M) - 9

# ============ 四格信息栏 ============
GRID_H = 49
grid_top = y + 8
c.setFillColor(LIGHT)
c.rect(M, grid_top - GRID_H, W - 2 * M, GRID_H, fill=1, stroke=0)
cells = [
    ('求职意向', ['C++ / Rust 开发工程师']),
    ('对口方向', ['Linux 后端 / 工业通讯', '存储 / 量化 / 自动驾驶', 'Qt 客户端 / 嵌入式']),
    ('期望城市', ['深圳']),
    ('技术视野', ['C++20 协程 / io_uring', '低延迟 / 高性能']),
]
cw = (W - 2 * M) / 4
for i, (label, values) in enumerate(cells):
    cx = M + i * cw
    if i > 0:
        c.setStrokeColor(LINE)
        c.setLineWidth(0.7)
        c.line(cx, grid_top - GRID_H + 6, cx, grid_top - 6)
    c.setFillColor(GRAY)
    c.setFont('YH', 6.8)
    c.drawString(cx + 12, grid_top - 13, label)
    vy = grid_top - 25
    for v in values:
        c.setFillColor(DEEP)
        c.setFont('YHB', 8.2)
        c.drawString(cx + 12, vy, v)
        vy -= 10.5
y = grid_top - GRID_H - 15

# ============ 专业技能 ============
y = section(c, y, '专业技能')
skills = [
    [bold('编程语言：'), seg('熟练使用 C++（C++11/17/20），掌握 STL 容器与算法、模板泛型、RAII 与智能指针、原子操作与内存序；熟悉 Rust（所有权、Trait、生命周期、async 异步），具备双语言系统编程基础；了解 Go 与 JavaScript')],
    [bold('Linux 系统编程：'), seg('熟悉 Linux 开发环境与常用命令（awk/sed/grep 文本处理、ss/ps/top 排障），掌握信号处理与进程线程控制；掌握管道、共享内存、信号量等进程间通信，熟悉文件 I/O 与串口编程（termios），有工业设备串口接入经验；了解 x86/ARM 汇编，能结合 GDB/objdump 反汇编分析程序行为；熟悉编译链接、ELF 与 C++ 对象模型')],
    [bold('网络编程：'), seg('熟悉 Socket 编程与 select/poll/epoll I/O 多路复用，理解 Reactor 事件驱动模型；熟悉 TCP/IP、HTTP、WebSocket 协议；了解 C++20 协程与 io_uring')],
    [bold('数据存储：'), seg('熟悉 MySQL（事务、索引优化），有海量数据迁移与一致性核对经验；了解 Redis 缓存场景、MongoDB、PostgreSQL')],
    [bold('工程工具：'), seg('熟练使用 CMake、Git、Shell 完成构建与部署，了解 Docker 容器化；能用 GDB、Valgrind 定位内存泄漏与性能问题，掌握 perf 与火焰图分析 CPU 热点，了解 ASan/TSan、strace')],
    [bold('Python 工具链：'), seg('编写数据批处理、日志分析、构建测试辅助等自动化脚本，掌握 ctypes / pybind11 C++ 混合编程')],
    [bold('工业通信：'), seg('熟悉 Modbus、IEC 104、IEC 61850 工业协议的设备接入、现场对接与通信问题排查')],
    [bold('AI 辅助开发：'), seg('熟练使用 Claude Code、Codex、ChatGPT 等工具，显著提升开发与排障效率')],
    [bold('技术文档：'), seg('坚持系统化技术写作，GitHub 开源 '), num('204 篇'), seg(' 技术笔记（Markdown），具备规范的技术文档与 README 写作能力')],
]
for s in skills:
    y = draw_rich(c, s, M, y, W - 2 * M) - 3.6
y -= 7

# ============ 工作经历 ============
y = section(c, y, '工作经历')
y = job_header(c, y, '深圳市中科力联科技有限公司', 'C++ 开发工程师', '2025.07 – 2026.07', W - 2 * M)
y = bullet([seg('通讯管理机服务端开发（C++）：实现多类工业设备的 HTTP、WebSocket 接入与数据转发，按客户现场需求定制功能')], c, y, W - 2 * M) - 2.3
y = bullet([seg('开发 Modbus RTU over TCP 及多协议规约工具，支持各类报文抓包分析与解析，快速定位现场通信问题')], c, y, W - 2 * M) - 2.3
y = bullet([seg('独立完成 Modbus、IEC 104、IEC 61850 工业协议现场对接与通信链路排查，版本维护期间'), num('零重大故障')], c, y, W - 2 * M) - 2.3
y = bullet([seg('参与报文结构设计（长度字段 + 消息体）与跨系统数据一致性核对，保障现场稳定交付')], c, y, W - 2 * M) - 6

y = job_header(c, y, '深圳市齐信汽车技术有限公司', '开发实习生', '2024.11 – 2025.03', W - 2 * M)
y = bullet([seg('负责 JSON、XML、Protobuf 多格式数据的解析、清洗与校验')], c, y, W - 2 * M) - 2.3
y = bullet([seg('编写 Python 批量入库脚本，完成 '), num('50–100 万条'), seg(' 数据迁移至 MySQL 并核对数据一致性')], c, y, W - 2 * M) - 6.5

# ============ 项目经历 ============
y = section(c, y, '项目经历')
y = proj_header(c, y, '基于 Muduo 的高并发 WebServer', '个人项目')
y = proj_stack(c, y, '技术栈：C++17 · Muduo · epoll · HTTP/1.1 · MySQL · CMake')
y = bullet([seg('基于 Reactor 多线程模型实现完整 HTTP/1.1 请求解析、静态资源访问与登录注册功能')], c, y, W - 2 * M) - 2.3
y = bullet([seg('epoll 多路复用配合线程池，引入 MySQL 连接池复用连接，单服务支持'), num('千级并发')], c, y, W - 2 * M) - 2.3
y = bullet([seg('使用 ab 压测针对性优化，'), num('QPS 提升 40%'), seg('；定位并修复短连接文件句柄泄漏、TCP 粘包等底层问题')], c, y, W - 2 * M) - 6

y = proj_header(c, y, 'Qt 跨平台 TCP 网络聊天室', '个人项目')
y = proj_stack(c, y, '技术栈：C++ · Qt5 · QTcpSocket / QTcpServer · JSON · 多线程 · CMake')
y = bullet([seg('C/S 架构实现群聊、私聊、心跳保活与断线重连，自定义消息头（长度字段 + 消息体）解决 TCP 粘包/分包问题')], c, y, W - 2 * M) - 2.3
y = bullet([seg('网络层与 UI 界面分层解耦，JSON 封装通信报文，支持 Windows / Linux 双平台编译运行')], c, y, W - 2 * M) - 6

y = proj_header(c, y, '高并发核心组件手写实践', '个人项目')
y = proj_stack(c, y, '技术栈：C++17 · 互斥锁 / 条件变量 / 原子操作 · 无锁编程')
y = bullet([seg('手写线程池、内存池、定时器与 LRU 缓存，覆盖同步原语、内存管理与缓存淘汰策略')], c, y, W - 2 * M) - 2.3
y = bullet([seg('结合 '), num('204 篇'), seg(' 技术笔记沉淀设计思路，输出配套设计文档与测试用例')], c, y, W - 2 * M) - 6.5

# ============ 教育背景与荣誉(两栏) ============
y = section(c, y, '教育背景与荣誉')
col_split = M + 285

# 左栏:教育
lx = M
c.setFillColor(DARK)
c.setFont('YHB', 9.4)
c.drawString(lx, y, '东华理工大学 · 网络工程（本科）')
c.setFillColor(GRAY)
c.setFont('YH', 8.3)
c.drawRightString(col_split - 4, y, '2021.09 – 2025.07')
ly = y - LEAD - 2
ly = bullet([num('专业排名前 20%'), seg('，主修 C/C++ 程序设计、计算机网络、操作系统、数据结构与算法、计算机组成原理')], c, ly, col_split - lx - 14, x=lx) - 2.3
ly = bullet([seg('算法竞赛：蓝桥杯省级二等奖、传智杯一等奖（可查）')], c, ly, col_split - lx - 14, x=lx)

# 右栏:荣誉
rx = col_split + 16
rw = W - M - rx
c.setFillColor(DEEP)
c.setFont('YHB', 9.4)
c.drawString(rx, y, '荣誉与证书')
ry = y - LEAD - 2
ry = bullet([seg('高考数学 '), num('130/150'), seg('（可查）、全国数学竞赛三等奖')], c, ry, rw, x=rx) - 2.3
ry = bullet([seg('软考中级：软件设计师（已通过，可查）')], c, ry, rw, x=rx) - 2.3
ry = bullet([seg('优秀学生干部奖学金（2021）、校三等奖学金（可查）')], c, ry, rw, x=rx)

# 中间分隔线(按两栏实际高度)
c.setStrokeColor(LINE)
c.setLineWidth(0.7)
bottom = min(ly, ry) - 6.5
c.line(col_split + 5, y + 6, col_split + 5, bottom)

c.save()
print(f'PDF generated. Education ends: left={ly:.1f}, right={ry:.1f} (bottom limit ~30)')
