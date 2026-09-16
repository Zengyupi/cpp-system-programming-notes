# Linux 系统编程 API 实战

> 本节目标：把《01-操作系统原理.md》中的进程、文件、信号、IPC 等概念落到可编译、可上线的系统调用代码上，统一错误处理范式，讲清 fork/exec/信号/串口等高频踩坑点，覆盖后端、基础架构、嵌入式与工业通讯岗位对 Linux 系统编程 API 的面试与工程要求。原型以 WSL Ubuntu 24.04、glibc 2.39、Linux 6.8 为准，拿不准的签名以 man 2 / man 3 为唯一来源。

## 本章速览

- [1. 系统编程总览与错误处理模型](#1-系统编程总览与错误处理模型)
  - [1.1 系统调用与 glibc 库函数的边界](#11-系统调用与-glibc-库函数的边界)
  - [1.2 返回值约定与 errno 统一错误模式](#12-返回值约定与-errno-统一错误模式)
  - [1.3 线程安全、可重入与异步信号安全](#13-线程安全可重入与异步信号安全)
  - [1.4 EINTR 与 TEMP_FAILURE_RETRY 重试模式](#14-eintr-与-temp_failure_retry-重试模式)
- [2. 文件 IO 与文件描述符](#2-文件-io-与文件描述符)
  - [2.1 open 标志位与 mode 权限](#21-open-标志位与-mode-权限)
  - [2.2 read write lseek 与短读写处理](#22-read-write-lseek-与短读写处理)
  - [2.3 fcntl 与 ioctl](#23-fcntl-与-ioctl)
  - [2.4 dup 族与标准流重定向](#24-dup-族与标准流重定向)
  - [2.5 进程 fd 表、打开文件表与 inode 三层模型](#25-进程-fd-表打开文件表与-inode-三层模型)
  - [2.6 fsync fdatasync 与落盘语义](#26-fsync-fdatasync-与落盘语义)
  - [2.7 sendfile splice 与 mmap 零拷贝](#27-sendfile-splice-与-mmap-零拷贝)
- [3. 进程控制与守护进程](#3-进程控制与守护进程)
  - [3.1 fork 写时复制与分叉后的安全规则](#31-fork-写时复制与分叉后的安全规则)
  - [3.2 exec 族函数的区别与选型](#32-exec-族函数的区别与选型)
  - [3.3 wait waitpid 僵尸进程与孤儿进程](#33-wait-waitpid-僵尸进程与孤儿进程)
  - [3.4 进程组、会话与控制终端](#34-进程组会话与控制终端)
  - [3.5 daemon 双 fork 标准模板](#35-daemon-双-fork-标准模板)
- [4. 信号机制](#4-信号机制)
  - [4.1 signal 与 sigaction 的取舍](#41-signal-与-sigaction-的取舍)
  - [4.2 信号集与 sigprocmask 屏蔽](#42-信号集与-sigprocmask-屏蔽)
  - [4.3 async-signal-safe 处理器编写原则](#43-async-signal-safe-处理器编写原则)
  - [4.4 信号中断与 SA_RESTART](#44-信号中断与-sa_restart)
  - [4.5 signalfd 把信号转成 fd 事件](#45-signalfd-把信号转成-fd-事件)
  - [4.6 SIGCHLD 回收与 SIGPIPE 处理](#46-sigchld-回收与-sigpipe-处理)
- [5. 进程间通信 IPC 全景](#5-进程间通信-ipc-全景)
  - [5.1 匿名管道 pipe 与命名管道 FIFO](#51-匿名管道-pipe-与命名管道-fifo)
  - [5.2 System V 共享内存、消息队列与信号量](#52-system-v-共享内存消息队列与信号量)
  - [5.3 POSIX IPC 及其与 System V 的差异](#53-posix-ipc-及其与-system-v-的差异)
  - [5.4 Unix Domain Socket 与 SCM_RIGHTS 传递 fd](#54-unix-domain-socket-与-scm_rights-传递-fd)
  - [5.5 eventfd 与事件通知](#55-eventfd-与事件通知)
  - [5.6 IPC 选型对比表](#56-ipc-选型对比表)
- [6. termios 串口编程](#6-termios-串口编程)
  - [6.1 struct termios 结构与四个标志位](#61-struct-termios-结构与四个标志位)
  - [6.2 波特率、数据位、校验位与停止位配置](#62-波特率数据位校验位与停止位配置)
  - [6.3 raw 原始模式与 VMIN VTIME 语义](#63-raw-原始模式与-vmin-vtime-语义)
  - [6.4 阻塞模型、非阻塞读与错误恢复](#64-阻塞模型非阻塞读与错误恢复)
  - [6.5 对接 Modbus RTU 的工程要点](#65-对接-modbus-rtu-的工程要点)
- [7. 时间与定时器](#7-时间与定时器)
  - [7.1 clock_gettime 的四种时钟与选型](#71-clock_gettime-的四种时钟与选型)
  - [7.2 timerfd_create 与 timerfd_settime](#72-timerfd_create-与-timerfd_settime)
  - [7.3 sleep nanosleep 与 clock_nanosleep](#73-sleep-nanosleep-与-clock_nanosleep)
- [8. 快速参考卡片](#8-快速参考卡片)
- [9. 常见坑与排查清单](#9-常见坑与排查清单)

---

## 1. 系统编程总览与错误处理模型

### 1.1 系统调用与 glibc 库函数的边界

系统调用是用户态请求内核服务的唯一受控入口：执行`syscall`指令后 CPU 陷入内核态，按系统调用号分发，开销在数百到上千纳秒，热路径上应减少 syscall 次数（`readv`合并缓冲、io_uring 批量提交，详见《../13-并发异步与组件/02-io_uring与异步IO.md》）。glibc 在其上封装库函数，二者边界必须分清：

- `read`、`write`、`open`、`fork`、`mmap`是薄封装，原型在 man 第 2 节；`fopen`、`fread`、`printf`、`malloc`在第 3 节，带用户态缓冲，内部才调`open`/`brk`/`mmap`。`fprintf`返回后数据可能还在 stdio 缓冲区。
- `gettimeofday`、部分时钟的`clock_gettime`、`getcpu`走 vDSO：内核把只读代码与数据映射进进程地址空间，不真正陷入内核，所以取时间远比一般 syscall 便宜。
- 绕过 glibc 可用`syscall(SYS_xxx, ...)`；观察程序实际触发的 syscall 用 strace，详见《../08-网络与系统工具/06-strace系统调用跟踪.md》。

### 1.2 返回值约定与 errno 统一错误模式

绝大多数 syscall 成功返回非负值，失败返回`-1`并设置线程局部变量`errno`。要点：

1. `errno`线程私有，glibc 中展开为`(*__errno_location())`，多线程并发失败互不覆盖；只需包含`<errno.h>`，不要手写 extern 声明。
2. 成功时 errno 不清零，只能在函数明确返回失败后读取；需要跨函数使用必须立刻保存——后续任何库函数（含打日志的 fprintf）都可能改写它。
3. 失败形态不全是`-1`：`fopen`/`malloc`返回`NULL`；pthread 函数直接返回错误码而不设 errno。
4. `perror`直接打印；`strerror`返回静态串、不可重入；多线程用`strerror_r`，注意 POSIX 版返回 int，定义`_GNU_SOURCE`后 glibc 版返回字符串指针，签名不同。

```c
int fd = open("/dev/ttyUSB0", O_RDWR | O_NOCTTY | O_NONBLOCK);
if (fd == -1) {
    int saved = errno;                       /* 立刻保存再使用 */
    fprintf(stderr, "open failed: %s\n", strerror(saved));
    return saved;
}
```

### 1.3 线程安全、可重入与异步信号安全

三个概念严格区分：**线程安全（MT-Safe）**指并发调用无数据竞争，`malloc`/`printf`靠内部锁做到线程安全但不可重入；**可重入**指函数执行中被再次进入仍正确，只依赖调用者传入的状态，对应`strtok_r`/`readdir_r`/`gmtime_r`等`_r`版本；**异步信号安全（AS-Safe）**要求最严，连内部加锁的函数都不行——handler 可能恰好打断在临界区里，再次取锁即自死锁。白名单见`man 7 signal-safety`，仅`_exit`、`write`、`read`、`close`、`kill`、`sigaction`等约三十个，`malloc`、`printf`、`syslog`、`std::mutex`、`std::cout`均不在其列。glibc 用 attributes(7) 标注每个函数的安全等级。

### 1.4 EINTR 与 TEMP_FAILURE_RETRY 重试模式

进程阻塞在慢系统调用期间收到信号、handler 正常返回时，内核让该调用返回`-1`/`EINTR`，是否重试交给用户态。read/write（慢设备）、waitpid、accept、recvfrom、nanosleep、futex 都可能 EINTR；但`select`/`poll`/`epoll_wait`即使设了 SA_RESTART 也**不会**自动重启，磁盘文件 IO 在 Linux 上不会 EINTR。glibc 的`TEMP_FAILURE_RETRY(expr)`宏（需`_GNU_SOURCE`）即“遇 EINTR 重来”，生产代码更推荐显式循环，同时处理短读写与 EAGAIN：

```c
#define RETRY_ON_EINTR(expr) ({             \
    ssize_t __r;                            \
    do { __r = (expr); }                    \
    while (__r == -1 && errno == EINTR);    \
    __r;                                    \
})

/* 循环读到 EOF 或读满 n；返回已读字节数，EOF 时可小于 n */
ssize_t read_full(int fd, void *buf, size_t n)
{
    size_t done = 0; char *p = (char *)buf;
    while (done < n) {
        ssize_t r = read(fd, p + done, n - done);
        if (r == 0) break;                  /* EOF */
        if (r == -1) {
            if (errno == EINTR) continue;
            if (errno == EAGAIN || errno == EWOULDBLOCK) break;
            return -1;
        }
        done += (size_t)r;
    }
    return (ssize_t)done;
}

/* 循环写完全部 n 字节（短写必须续发） */
ssize_t write_full(int fd, const void *buf, size_t n)
{
    size_t done = 0; const char *p = (const char *)buf;
    while (done < n) {
        ssize_t w = write(fd, p + done, n - done);
        if (w == -1) {
            if (errno == EINTR) continue;
            if (errno == EAGAIN || errno == EWOULDBLOCK) continue;
            return -1;
        }
        done += (size_t)w;
    }
    return (ssize_t)done;
}
```

## 2. 文件 IO 与文件描述符

### 2.1 open 标志位与 mode 权限

原型`int open(const char *path, int flags, mode_t mode);`，另有相对目录 fd 的`openat`（避免 TOCTOU，现代代码首选）。访问模式 O_RDONLY/O_WRONLY/O_RDWR 三选一，比较时用`O_ACCMODE`掩码。高频标志：

| 标志 | 要点 |
| --- | --- |
|`O_CREAT`/`O_EXCL`|不存在则创建（必须给 mode）；加 EXCL 时已存在则 EEXIST，可做原子锁文件 |
|`O_TRUNC`|普通文件截断为 0；`O_APPEND`每次 write 前内核原子定位到尾，多进程追加日志必须用 |
|`O_NONBLOCK`|非阻塞，对管道/FIFO/socket/设备有效，对普通磁盘文件基本无效 |
|`O_CLOEXEC`|exec 成功后自动关闭，防 fd 泄漏；`O_NOCTTY`打开终端时不设为控制终端 |
|`O_DIRECTORY`/`O_NOFOLLOW`|非目录则失败/不跟随符号链接；`O_TMPFILE`建无名临时文件 |
|`O_SYNC`/`O_DIRECT`|前者每次写同步落盘（代价高，推荐按需 fsync）；后者绕过 page cache，要求对齐 |

mode 仅创建时生效，最终权限 = mode & ~umask，如 mode 0666 在 umask 022 下得 0644；守护进程通常先`umask(0)`。32 位平台处理大文件需`-D_FILE_OFFSET_BITS=64`。

### 2.2 read write lseek 与短读写处理

`read`返回正数为本次实读字节数（允许小于请求，即短读，管道/套接字上是常态）、0 为 EOF、-1 为错误，因此循环读满是基本功（见 1.4）。`lseek(fd, off, whence)`调整共享偏移，whence 取 SEEK_SET/CUR/END，可越过文件尾制造稀疏空洞；管道与套接字不可 seek（ESPIPE）。两个增强接口：`pread`/`pwrite`按显式偏移 IO 且**不改动共享偏移**，多线程并发安全；`readv`/`writev`一次 syscall 在多段不连续缓冲间 scatter-gather，协议头与负载一次发出，省 syscall 又省拼包内存。

### 2.3 fcntl 与 ioctl

`fcntl`高频命令：`F_DUPFD_CLOEXEC`复制 fd 并一步带 CLOEXEC；`F_GETFD`/`F_SETFD`操作仅有的 fd 私有标志`FD_CLOEXEC`；`F_GETFL`/`F_SETFL`改打开文件状态，创建后只有`O_APPEND`与`O_NONBLOCK`可改（运行时切非阻塞：先 GETFL 再整体 SETFL 回去）；`F_SETLK`/`F_SETLKW`做 POSIX 建议性字节区间锁，随进程退出释放。`ioctl(fd, request, ...)`是设备控制总出口，request 码由方向/类型/序号/参数大小四段经`_IO`/`_IOR`/`_IOW`/`_IOWR`编码，如串口`TCGETS`、485 的`TIOCSRS485`；结构体布局必须与内核头文件完全一致，否则 EFAULT/EINVAL。

### 2.4 dup 族与标准流重定向

`dup`返回最小未用 fd；`dup2(old,new)`把 new 定向到同一打开文件表项（new 已开会先原子关闭）；`dup3`可带 O_CLOEXEC。复制后新旧 fd **共享文件偏移与 O_APPEND 状态**，FD_CLOEXEC 则是各 fd 私有。shell 的`2>&1`就是 dup2：

```c
int logfd = open("/var/log/app.out", O_WRONLY | O_CREAT | O_APPEND, 0644);
dup2(logfd, STDOUT_FILENO);
dup2(logfd, STDERR_FILENO);             /* stdout/stderr 共享同一表项，输出顺序一致 */
if (logfd > STDERR_FILENO) close(logfd);
```

### 2.5 进程 fd 表、打开文件表与 inode 三层模型

文件 IO 的核心模型，内核有三层对象：

1. **进程 fd 表**：每进程一份，下标即 fd，只存 CLOEXEC 标志与指向第二层的指针。
2. **系统打开文件表（open file description，`struct file`）**：全局，记录文件偏移、O_APPEND/O_NONBLOCK、访问模式。dup 与 fork 继承得到的多个 fd 指向同一表项，**共享偏移**。
3. **inode 表**：对应磁盘具体文件与页缓存。两次独立 open 各建第二层表项（偏移互不影响），但共享第三层，互可见对方写入。

由此解释：fork 父子写同一 fd 不互相覆盖（共享偏移）；两个独立 open 的线程各自 lseek+write 会穿插覆盖（必须 O_APPEND 或 pwrite）；dup2 后 close 原 fd 不影响重定向流（表项按引用计数释放）。fd 按“最小可用整数”分配。

### 2.6 fsync fdatasync 与落盘语义

`write`成功只代表数据进了 page cache，掉电即丢。`fsync`刷脏页与**全部**元数据并等设备确认；`fdatasync`只刷数据与“读回数据所必需”的元数据（不刷 atime），WAL 场景更省；新建文件要连**父目录**一起 fsync 才能保证目录项不丢。`O_SYNC`让每次写等价 write+fsync，吞吐极差，应“批量写 + 关键点 fsync”。NFS、虚拟磁盘上 fsync 可能被宿主缓存削弱，工业现场评估掉电安全要算上这层。

### 2.7 sendfile splice 与 mmap 零拷贝

传统“文件→套接字”经四次拷贝、两次上下文切换。零拷贝接口：`sendfile(out,in,off,count)`让数据在内核从页缓存直达 socket（in 必须是普通文件，2.6.33 起 out 可为任意 fd），静态服务与网关标配；`splice`在 fd 与管道间搬运页引用（必须有一端是管道），`tee`在两管道间复制引用，组合可做一份输入多路分发；`mmap`把文件映射进用户空间，缺页时直接对接页缓存，省掉 read 的用户态拷贝。mmap 要点：失败返回`MAP_FAILED`而非 NULL；`MAP_SHARED`写回文件、`MAP_PRIVATE`写时复制；访问超出映射长度报`SIGSEGV`，文件被 ftruncate 截短后访问原区间报`SIGBUS`；首次访问每页有缺页开销，随机小 IO 未必优于 read。新一代统一异步方案 io_uring 见《../13-并发异步与组件/02-io_uring与异步IO.md》。

## 3. 进程控制与守护进程

### 3.1 fork 写时复制与分叉后的安全规则

`fork`调用一次返回两次：父返子 pid、子返 0、失败-1（EAGAIN 多为触及进程/线程数上限）。内核靠写时复制（COW）只复制页表并把页标只读，写入时才逐页复制，所以 fork 瞬间开销主要是页表而非内存体积。子进程继承 fd 表（共享打开文件表项与偏移）、环境变量、cwd、umask、信号屏蔽字、内存映射；不继承 pid、pending 信号被清空、CPU 时间归零、文件锁不继承，且**只复制调用 fork 的那一个线程**。

最后一点是多线程程序 fork 的头号陷阱：其他线程在持锁状态下消失，子进程中 malloc 内部锁、stdio 锁、`std::mutex`永久锁定，再调 malloc/printf 即自死锁。POSIX 规则：多线程程序 fork 到 exec 之间只能用异步信号安全函数，稳妥模式是 fork 后立刻 exec，确需整理状态用`pthread_atfork`。另外 stdio 缓冲是用户态内存、fork 时被复制，若 fork 前未 flush，父子退出各刷一遍导致日志重复——fork 前先`fflush(NULL)`。

### 3.2 exec 族函数的区别与选型

exec 用新映像替换当前映像，成功不返回，失败常见 ENOENT/EACCES/ETXTBSY。pid、fd、cwd、信号屏蔽字不变；被捕获的信号处置重置为 SIG_DFL，SIG_IGN 保持忽略；带 CLOEXEC 的 fd 自动关闭。六个包装加一个真 syscall，区别只在参数组织：

| 函数 | 参数形式 | 搜 PATH | 自带环境 |
| --- | --- | --- | --- |
|`execl`/`execle`|NULL 结尾列表|否|le 带 envp |
|`execlp`/`execvpe`|列表/数组|是|后者带 envp |
|`execv`/`execvp`|argv 数组|否/是|继承 environ |
|`execve`|数组+envp，唯一真 syscall|否|自带 |

记忆：l=list 逐个列、v=vector 数组、p=PATH 搜索、e=environment。argv 必须以 NULL 哨兵收尾，argv[0]按惯例是程序名；首行`#!`由内核解释器机制处理。工程上“子进程跑外部命令”固定 fork→子 execvp→父 waitpid；复杂场景用`posix_spawn`，glibc 内部做了优化，比手写 fork+exec 更快更安全。

### 3.3 wait waitpid 僵尸进程与孤儿进程

进程退出后保留 task_struct 与退出码成为僵尸（Z），等父回收。`waitpid(pid, &status, options)`：pid 为-1 回收任意子进程；`WNOHANG`无子退出立即返 0 不阻塞；status 必须用宏解析——`WIFEXITED`后`WEXITSTATUS`取退出码，`WIFSIGNALED`后`WTERMSIG`取杀身信号。**僵尸**不占内存但占 pid 槽，堆积耗尽 pid，根因永远是父进程没回收；**孤儿**是父先退出，被 reparent 给最近 subreaper（`prctl(PR_SET_CHILD_SUBREAPER)`设置，systemd/容器 init 常用）或 PID 1 托底，本身无害。标准信号不排队，多个子同时退出只产生一个 SIGCHLD，回收必须循环到无余：

```c
while (waitpid(-1, &st, WNOHANG) > 0) { /* 收干全部已退出子进程 */ }
```

### 3.4 进程组、会话与控制终端

进程组是进程集合（pgid=组长 pid），一条管道线同组，shell 靠它整体前后台调度。会话由`setsid`创建：调用者不能是组长，成功后成为新会话首进程、新组长并脱离控制终端。一个会话最多一个前台进程组，Ctrl-C/Ctrl-\\/Ctrl-Z 产生的 SIGINT/SIGQUIT/SIGTSTP 只发前台组，终端挂断向会话首进程发 SIGHUP。相关接口：setpgid、tcsetpgrp。守护进程脱离终端的第一步正是 setsid。

### 3.5 daemon 双 fork 标准模板

守护进程要求：无控制终端、不是会话首进程（杜绝重新获取终端）、cwd 不占可卸载挂载点、umask 确定、标准流不泄漏到启动终端。标准流程：umask→首 fork（父退，保证子非组长）→setsid→再 fork（首进程退，孙进程永非会话首进程）→chdir("/")→0/1/2 重定向 /dev/null：

```c
#define _GNU_SOURCE
#include <fcntl.h>
#include <signal.h>
#include <sys/stat.h>
#include <unistd.h>

int become_daemon(void)
{
    umask(0);
    pid_t pid = fork();
    if (pid == -1) return -1;
    if (pid > 0) _exit(0);                 /* 父退，子非组长 */
    if (setsid() == -1) return -1;         /* 新会话，脱终端 */

    struct sigaction sa, old;              /* 忽略首进程退出时的 SIGHUP */
    sa.sa_handler = SIG_IGN;
    sigemptyset(&sa.sa_mask); sa.sa_flags = 0;
    sigaction(SIGHUP, &sa, &old);

    pid = fork();
    if (pid == -1) return -1;
    if (pid > 0) _exit(0);                 /* 首进程退，孙进程永非会话首进程 */
    sigaction(SIGHUP, &old, NULL);

    if (chdir("/") == -1) return -1;
    int dn = open("/dev/null", O_RDWR);
    if (dn == -1) return -1;
    dup2(dn, STDIN_FILENO);
    dup2(dn, STDOUT_FILENO);
    dup2(dn, STDERR_FILENO);
    if (dn > STDERR_FILENO) close(dn);
    return 0;
}
```

systemd 下推荐`Type=simple`由 systemd 完成上述工作；但嵌入式 SysVinit、自研工业网关仍要求程序自带 daemon 化，模板必须能手写。

## 4. 信号机制

### 4.1 signal 与 sigaction 的取舍

信号是内核异步投递的软中断。标准信号 1~31，SIGKILL/SIGSTOP 不可捕获忽略；32~64 为实时信号，**排队不丢**且可带负载（sigqueue），标准信号同类 pending 期间只留一个。注意 glibc 线程库占用 SIGRTMIN 附近信号，工程上从`SIGRTMIN+2`起用。`signal()`在 System V/BSD 上历史语义不一，可移植代码一律`sigaction`：sa_mask 是 handler 执行期额外屏蔽集；`SA_RESTART`自动重启被中断的慢调用；`SA_SIGINFO`启用带`siginfo_t`的三参 handler（可取发送方 pid/uid/退出码/非法地址）；`SA_NODEFER`不屏蔽自身；`SA_RESETHAND`一次性复位。

### 4.2 信号集与 sigprocmask 屏蔽

`sigset_t`只能用`sigemptyset`/`sigfillset`/`sigaddset`/`sigdelset`/`sigismember`操作，禁止按位运算。`sigprocmask(how,...)`按`SIG_BLOCK`/`SIG_UNBLOCK`/`SIG_SETMASK`改屏蔽字；屏蔽期间信号变 pending（标准信号合并、实时信号排队），解除后投递，`sigpending`可查。屏蔽字用于保护“检查标志+等待”临界区：`sigsuspend(mask)`原子地“临时换屏蔽字并休眠到信号处理返回”，消除信号在检查后、等待前到达而永久丢失的竞争；现代等价物是 signalfd 或 ppoll 的信号掩码参数。屏蔽字 fork 后继承、exec 后保留（捕获处置则重置）。

### 4.3 async-signal-safe 处理器编写原则

信号在任意指令边界异步打断同一线程，handler 必须极短：只操作`volatile sig_atomic_t`标志或调用 signal-safety(7) 白名单函数；不调 printf/malloc/free/syslog/new/delete，不碰 std::string、iostream、任何加锁对象；handler 内若用 errno 必须进入时保存、返回前恢复；复杂逻辑一律“handler 置位、主循环处理”，或用 self-pipe/signalfd 把信号转 fd 并入 epoll（Reactor 模型见《../03-网络编程/02-IO多路复用与Reactor模型.md》）。

### 4.4 信号中断与 SA_RESTART

设 SA_RESTART 后多数慢调用被中断时内核自动重启，但 Linux 上`poll`/`ppoll`/`select`/`pselect`/`epoll_wait`/`epoll_pwait`与`nanosleep`/`clock_nanosleep`**永不自动重启**，必须自处理 EINTR（nanosleep 通过剩余时间参数表达）。实践建议：网络库通常不用 SA_RESTART，统一在封装层处理 EINTR，行为更可控。

### 4.5 signalfd 把信号转成 fd 事件

signalfd 让信号以可读事件出现在 fd 上，与 epoll 统一调度，绕开 handler 的异步限制。固定四步：先 sigprocmask 阻塞目标信号（否则按默认处置投递、fd 收不到）；`signalfd(-1,&mask,SFD_NONBLOCK|SFD_CLOEXEC)`建 fd；加入 epoll；可读时 read 出若干`struct signalfd_siginfo`。屏蔽是进程级的，阻塞后所有线程都不被打断，由事件循环线程统一读取——这是现代进程处理 SIGTERM 优雅退出、SIGCHLD 回收的推荐结构。

### 4.6 SIGCHLD 回收与 SIGPIPE 处理

SIGCHLD 的正确姿势：handler 只置位，waitpid 循环放主流程。完整写法：

```c
#define _GNU_SOURCE
#include <signal.h>
#include <sys/wait.h>

static volatile sig_atomic_t got_sigchld = 0;
static void sigchld_handler(int sig) { (void)sig; got_sigchld = 1; }

void install_sigchld(void)
{
    struct sigaction sa;
    sigemptyset(&sa.sa_mask);
    sa.sa_handler = sigchld_handler;
    sa.sa_flags = SA_RESTART | SA_NOCLDSTOP;   /* 不关心停止事件 */
    sigaction(SIGCHLD, &sa, NULL);
}

void reap_children(void)                        /* 主循环检测到标志后调用 */
{
    if (!got_sigchld) return;
    int st; pid_t pid;
    while ((pid = waitpid(-1, &st, WNOHANG)) > 0) {
        if (WIFEXITED(st))   { /* WEXITSTATUS(st) */ }
        else if (WIFSIGNALED(st)) { /* WTERMSIG(st) 告警 */ }
    }
    got_sigchld = 0;                            /* 循环期间新来的信号会再次置 1 */
}
```

不需要退出码时可`signal(SIGCHLD,SIG_IGN)`让内核自动回收、不产僵尸，但此后 waitpid 取不到状态。SIGPIPE 发生在向“对端已关读端”的管道/套接字写入时，默认**终止进程**——服务器被单个异常客户端拖垮多因于此。三种处理：全局`signal(SIGPIPE,SIG_IGN)`后 write 返回 EPIPE（最常用）；单次`send(...,MSG_NOSIGNAL)`；注意 Linux 没有 SO_NOSIGPIPE（那是 BSD/macOS 选项）。

## 5. 进程间通信 IPC 全景

### 5.1 匿名管道 pipe 与命名管道 FIFO

`pipe2(int fds[2], flags)`建一对相连 fd，[0]读[1]写、半双工，数据走内核环形缓冲（默认 64KiB，fcntl F_SETPIPE_SZ 可调，上限见`/proc/sys/fs/pipe-max-size`）；写满阻塞或 EAGAIN，全部写端关闭后 read 返 0（EOF）。**不超过`PIPE_BUF`（Linux 为 4096）的写原子、多写者不交错**，超出可能穿插。flags 按需带 O_CLOEXEC/O_NONBLOCK。要双向通道用`socketpair(AF_UNIX,SOCK_STREAM,0,sv)`得一对全双工 fd。FIFO 由`mkfifo(path,mode)`建成目录项，无亲缘进程也能 open 通信：阻塞模式下只读 open 会等到写端出现；本质仍是字节流，消息边界靠长度前缀自划。

### 5.2 System V 共享内存、消息队列与信号量

三件套都以 key（`ftok(path,id)`生成或`IPC_PRIVATE`）+ id 标识，最大的坑是**对象存活于内核，不随进程退出释放**，必须显式 IPC_RMID 或重启，`ipcs`查看、`ipcrm`删除。共享内存：`shmget`→`shmat`映射→`shmdt`→`shmctl(IPC_RMID)`，零拷贝带宽最高但不带同步，需配信号量，限额看`kernel.shmmax/shmall/shmmni`。消息队列：`msgget/msgsnd/msgrcv`，消息带 mtype 可按类型优先接收、天然有边界，但两次拷贝且有 msgmax/msgmnb 上限，现代多被 UDS、消息中间件取代。信号量集：`semget/semop/semctl`，一次可原子操作集合中多个量，`SEM_UNDO`让进程异常退出时内核回滚 P/V，避免死锁遗留。

### 5.3 POSIX IPC 及其与 System V 的差异

POSIX 系列以`/名字`标识，API 更一致：消息队列`mq_open/mq_send/mq_receive/mq_notify/mq_unlink`，支持优先级与异步通知（旧 glibc 链-lrt）；共享内存`shm_open`建 fd 后必须`ftruncate`定长再`mmap`，挂在`/dev/shm`（tmpfs），`shm_unlink`删名；信号量命名版`sem_open/sem_post/sem_wait/sem_unlink`，无名版`sem_init`可放共享内存，`sem_timedwait`支持超时。选型：线程间用 pthread 原语；亲缘进程间用匿名 mmap 或 socketpair；跨无亲缘进程且不想引守护进程才用命名 POSIX IPC；System V 仅在维护存量与对接老工业软件时使用。

### 5.4 Unix Domain Socket 与 SCM_RIGHTS 传递 fd

AF_UNIX 不走网络栈、不丢包，SOCK_STREAM 是可靠字节流，SOCK_DGRAM 在 AF_UNIX 下也**可靠保序**。寻址支持路径名（bind 出 socket 文件，用完 unlink）与抽象命名空间（sun_path 首字节'\0'，不产生文件项，Linux 特有）。独有能力：`SCM_RIGHTS`经辅助消息在进程间**传递打开的 fd**（内核复制表项，接收方拿到等价 dup 的新 fd），`SCM_CREDENTIALS`传递对端 pid/uid/gid 做鉴权。最小示例：

```c
#define _GNU_SOURCE
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <string.h>

int send_fd(int sock, int fd_to_send)
{
    struct msghdr msg; struct iovec iov;
    union { struct cmsghdr h; char b[CMSG_SPACE(sizeof(int))]; } c;
    char dummy = 0;                          /* 数据段至少 1 字节 */
    iov.iov_base = &dummy; iov.iov_len = 1;
    memset(&msg, 0, sizeof(msg));
    msg.msg_iov = &iov; msg.msg_iovlen = 1;
    msg.msg_control = c.b; msg.msg_controllen = sizeof(c.b);
    struct cmsghdr *h = CMSG_FIRSTHDR(&msg);
    h->cmsg_level = SOL_SOCKET; h->cmsg_type = SCM_RIGHTS;
    h->cmsg_len = CMSG_LEN(sizeof(int));
    memcpy(CMSG_DATA(h), &fd_to_send, sizeof(int));
    return sendmsg(sock, &msg, 0) == -1 ? -1 : 0;
}

int recv_fd(int sock)
{
    struct msghdr msg; struct iovec iov;
    union { struct cmsghdr h; char b[CMSG_SPACE(sizeof(int))]; } c;
    char dummy;
    iov.iov_base = &dummy; iov.iov_len = 1;
    memset(&msg, 0, sizeof(msg));
    msg.msg_iov = &iov; msg.msg_iovlen = 1;
    msg.msg_control = c.b; msg.msg_controllen = sizeof(c.b);
    if (recvmsg(sock, &msg, 0) == -1) return -1;
    struct cmsghdr *h = CMSG_FIRSTHDR(&msg);
    if (!h || h->cmsg_level != SOL_SOCKET || h->cmsg_type != SCM_RIGHTS) return -1;
    int got; memcpy(&got, CMSG_DATA(h), sizeof(got));
    return got;                              /* 全新 fd，用完 close */
}
```

### 5.5 eventfd 与事件通知

`eventfd(initval,flags)`持有一个 64 位计数器：write 累加（超`UINT64_MAX-1`阻塞或 EAGAIN），read 一次读出并清零（`EFD_SEMAPHORE`下读 1 并减 1，表现为计数信号量）。它不载业务数据，价值是“fd 化唤醒”：消费者把它与网络 fd 一起塞 epoll，生产者写 8 字节即唤醒，比 pipe 省一个 fd、无短读写。同类 signalfd、timerfd 共同构成“万物皆 fd、统一进 epoll/io_uring”的事件驱动范式。

### 5.6 IPC 选型对比表

| 机制 | 方向/边界 | 同步 | 生命周期 | 典型场景 |
| --- | --- | --- | --- | --- |
| pipe/pipe2 | 半双工字节流，≤PIPE_BUF写原子 | 无 | 随 fd | 父子通信、shell 管线 |
| socketpair | 全双工字节流 | 无 | 随 fd | 线程/父子双向通道 |
| FIFO | 半双工字节流 | 无 | 文件系统路径 | 无亲缘简单对接 |
| UDS STREAM/DGRAM | 全双工/可靠数据报，可传 fd | 无 | socket 文件/抽象名 | 本机服务、worker 池 |
| SysV/POSIX shm | 裸内存 | 需自带 | 内核持久到删除 | 大数据零拷贝 |
| SysV 消息队列 | 有边界、可按类型收 | 队列自带 | 内核持久 | 存量任务分发 |
| POSIX mq | 有边界、带优先级 | 队列自带 | 到 mq_unlink | 现代小消息 |
| eventfd/signalfd/timerfd | 8 字节计数/信号/定时 | epoll 统一 | 随 fd | 事件循环唤醒与定时 |

## 6. termios 串口编程

工业通讯（通讯管理机、网关、DTU）与嵌入式岗位中串口是重灾区。Linux 下串口就是终端设备 fd（/dev/ttyUSB0、/dev/ttyS1），open/read/write 操作，线路参数全部由`<termios.h>`与 ioctl 控制。

### 6.1 struct termios 结构与四个标志位

```c
struct termios {
    tcflag_t c_iflag;   /* 输入加工：收到字节如何处理 */
    tcflag_t c_oflag;   /* 输出加工：写出字节如何处理 */
    tcflag_t c_cflag;   /* 控制：波特率、数据位、校验、停止位、流控 */
    tcflag_t c_lflag;   /* 本地：规范/原始、回显、信号字符 */
    cc_t     c_cc[NCCS];/* VMIN/VTIME/VINTR 等控制字符 */
    speed_t  c_ispeed, c_ospeed;
};
```

固定流程：`tcgetattr`取→改→`tcsetattr`设。时机参数：TCSANOW 立即、TCSADRAIN 等输出排空、TCSAFLUSH 排空输出并**丢弃输入残留**（打开后清首帧必备）。tcsetattr 只要部分可设就返成功，严谨做法是回读比对。配套：`tcdrain`等发完、`tcflush(TCIFLUSH/TCOFLUSH/TCIOFLUSH)`清队列。

### 6.2 波特率、数据位、校验位与停止位配置

c_cflag 关键位：`CLOCAL`忽略 modem 控制线（USB 转串口必开）、`CREAD`允许接收；CS5~CS8 数据位（先以 CSIZE 掩码清零）；`PARENB`开校验、`PARODD`奇校验；`CSTOPB`两停止位；`CRTSCTS`硬件流控（Modbus 一般关）。完整可投产配置函数（含 raw 设置）：

```c
#define _DEFAULT_SOURCE
#include <fcntl.h>
#include <termios.h>
#include <unistd.h>
#include <errno.h>

/* databits:5-8；parity:'N'无 'O'奇 'E'偶；stopbits:1/2 */
int serial_configure(int fd, speed_t baud, int databits, char parity, int stopbits)
{
    struct termios t;
    if (tcgetattr(fd, &t) == -1) return -1;
    cfmakeraw(&t);                         /* 一步进 raw，等价手工清加工标志，见 6.3 */
    if (cfsetispeed(&t, baud) == -1 || cfsetospeed(&t, baud) == -1) return -1;

    t.c_cflag |= CLOCAL | CREAD;
    t.c_cflag &= ~CRTSCTS;
    t.c_cflag &= ~CSIZE;
    switch (databits) {
        case 5: t.c_cflag |= CS5; break; case 6: t.c_cflag |= CS6; break;
        case 7: t.c_cflag |= CS7; break; case 8: t.c_cflag |= CS8; break;
        default: errno = EINVAL; return -1;
    }
    switch (parity) {
        case 'N': case 'n': t.c_cflag &= ~PARENB; t.c_iflag &= ~INPCK; break;
        case 'O': case 'o': t.c_cflag |= PARENB | PARODD; t.c_iflag |= INPCK; break;
        case 'E': case 'e': t.c_cflag |= PARENB; t.c_cflag &= ~PARODD;
                            t.c_iflag |= INPCK; break;
        default: errno = EINVAL; return -1;
    }
    if (stopbits == 2) t.c_cflag |= CSTOPB; else t.c_cflag &= ~CSTOPB;

    t.c_cc[VMIN] = 1; t.c_cc[VTIME] = 1;  /* 至少 1 字节、字节间隔 0.1s */
    t.c_cflag &= ~HUPCL;                  /* 关闭时不拉 DTR，避免外设复位 */
    if (tcsetattr(fd, TCSAFLUSH, &t) == -1) return -1;
    tcflush(fd, TCIOFLUSH);               /* 丢打开期间残留 */
    return 0;
}

int serial_open(const char *dev, speed_t baud)
{
    int fd = open(dev, O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (fd == -1) return -1;
    int fl = fcntl(fd, F_GETFL, 0);       /* 需要阻塞读则清 NONBLOCK */
    fcntl(fd, F_SETFL, fl & ~O_NONBLOCK);
    if (serial_configure(fd, baud, 8, 'N', 1) == -1) { close(fd); return -1; }
    return fd;
}
```

### 6.3 raw 原始模式与 VMIN VTIME 语义

终端默认**规范模式**：内核按行缓冲、遇行分隔才交数据，还做大量字符加工；二进制协议必须切非规范（raw）模式。`cfmakeraw`等价于：lflag 关 ICANON（行缓冲）、ECHO 系列（回显）、ISIG（控制字符发信号）、IEXTEN；iflag 关 BRKINT/INPCK/ISTRIP/ICRNL/IXON；oflag 关 OPOST；cflag 设 CS8。每个被关标志对应一类“字节被吞”经典故障：

- `ICRNL`把 0x0D(CR)翻译成 0x0A，帧中 0x0D 凭空变值；
- `IXON`软件流控：0x13(XOFF)/0x11(XON)被内核截留用于暂停/恢复输出，应用永远收不到；
- `ISTRIP`剥掉每个字节最高位，≥0x80 的数据全错；
- `ISIG`下 0x03(Ctrl-C)/0x1C 变成发信号，协议数据“杀死”进程；
- `OPOST`/`ONLCR`输出时把 0x0A 扩成 0x0D 0x0A，写出的帧被插字节。

非规范模式下 read 行为完全由`VMIN`（最少字节）与`VTIME`（0.1 秒为单位）决定：

| VMIN | VTIME | 行为 |
| --- | --- | --- |
| 0 | 0 | 立即返回，无数据返 0（轮询） |
| >0 | 0 | 阻塞到至少 VMIN 字节，无超时 |
| 0 | >0 | 等首字节，之后纯计时，超时返 0 |
| >0 | >0 | 字节间隔超时，间隔超 VTIME 即返回，适合按帧读 |

### 6.4 阻塞模型、非阻塞读与错误恢复

更可控的做法是 fd 设 O_NONBLOCK，配 poll/epoll 的 POLLIN 与软件时间戳做帧间隔判断（VTIME 仅 100ms 粒度，高速率太粗）。返回值区分：`-1/EAGAIN`为当前无数据，正常；USB 转串口拔出常见`-1/EIO`，需关 fd 并按 udev 事件或轮询 open 重连；串口不会 EOF，read 返 0 不是正常现象。写大帧可能短写，余量等 POLLOUT；RS485 半双工发完必须`tcdrain`等最后一位移出移位寄存器再切方向，否则截尾。常见现场问题：用户需在 dialout 组、用 udev 按 ID_PATH 固定设备名、非标准波特率走 BOTHER、tcsetattr“假成功”需回读校验，驱动细节对照《../09-嵌入式开发/05-嵌入式Linux系统与驱动开发.md》。

### 6.5 对接 Modbus RTU 的工程要点

Modbus RTU 是 RS485 主从二进制协议，字段解析见《../../02-网络协议与报文解析/07-Modbus与IEC104工业报文解析.md》，系统编程侧要点：

1. 线路参数固定 8E1 或 8N2，主从严格一致，常用 9600/19200/115200。
2. 靠静默间隔分帧：帧内字节间隔 ≤1.5 字符时间，帧间 ≥3.5 字符时间（9600 约 3.65ms，115200 仅约 0.30ms）。低速率可用 VTIME=1 粗分帧；115200 必须 poll/epoll + `clock_gettime(CLOCK_MONOTONIC)`逐字节打戳按间隔切帧。
3. RS485 方向优先内核自动 RTS：`<linux/serial.h>`的`struct serial_rs485`置`SER_RS485_ENABLED|SER_RS485_RTS_ON_SEND`，ioctl`TIOCSRS485`下发，delay_rts_before/after_send 补偿切换延时；驱动不支持则 GPIO 手动拉方向，发完 tcdrain 再拉回。
4. CRC16（多项式 0xA001）校验失败立即丢帧并等下一个 3.5 字符间隔，残帧绝不拼进下一帧；发送前 tcflush 清历史噪声。
5. 总线串行化：未收齐应答或超时前不得发下一帧，超时典型 100ms~1s，重试次数与退避按现场调。

## 7. 时间与定时器

### 7.1 clock_gettime 的四种时钟与选型

`clock_gettime(clk,&tp)`经 vDSO 加速，是取时首选（`gettimeofday`已过时：微秒精度、仅墙上时间）。选型取决于测间隔还是记时刻：

| 时钟 | 含义 | NTP/改时间 | 计挂起 | 用途 |
| --- | --- | --- | --- | --- |
|`CLOCK_REALTIME`|纪元起墙上时间，可跳变甚至倒退|受步进影响|计|日志/持久化时刻、跨机对齐 |
|`CLOCK_MONOTONIC`|开机起单调钟，仅受 NTP 频率微调不跳变|仅微调|不计|超时、RTT、定时器（首选） |
|`CLOCK_MONOTONIC_RAW`|不受 NTP 调整的硬件原始钟|否|不计|恒速精密测量 |
|`CLOCK_BOOTTIME`|含挂起睡眠的单调钟|仅微调|计|休眠设备的超时统计 |

另有`*_COARSE`版牺牲精度换更快（适合统计采样）与 PROCESS/THREAD_CPUTIME_ID 测 CPU 时间。timespec 差值须借位计算，勿直接转 double 丢精度：

```c
long diff_ms(const struct timespec *a, const struct timespec *b) {
    long s = b->tv_sec - a->tv_sec, ns = b->tv_nsec - a->tv_nsec;
    if (ns < 0) { --s; ns += 1000000000L; }
    return s * 1000L + ns / 1000000L;
}
```

### 7.2 timerfd_create 与 timerfd_settime

旧式 alarm（秒级）、setitimer（靠信号、进程级）在多线程事件循环里难用，fd 化定时是标准答案：

```c
int tfd = timerfd_create(CLOCK_MONOTONIC, TFD_NONBLOCK | TFD_CLOEXEC);
struct itimerspec its;
its.it_value.tv_sec = 5;  its.it_value.tv_nsec = 0;    /* 首次 5s */
its.it_interval.tv_sec = 1; its.it_interval.tv_nsec = 0;/* 周期 1s，置 0 为单次 */
timerfd_settime(tfd, 0, &its, NULL);                   /* TFD_TIMER_ABSTIME 设绝对时刻 */
```

到期后 tfd 可读，read 一个`uint64_t`得到自上次读取以来的**到期次数**（错过多次也不丢信息）后自动清空；并入 epoll 即实现海量定时器。与时间轮方案互补（见《../13-并发异步与组件/08-定时器设计与手撕实现.md》）：超大规模定时用时间轮，少量精确定时用 timerfd。停止即把 it_value 清零再 settime。

### 7.3 sleep nanosleep 与 clock_nanosleep

`sleep`秒级、被打断返回剩余秒数；`nanosleep(&req,&rem)`纳秒级，EINTR 时 rem 写剩余时间需循环续睡，且永不被 SA_RESTART 重启；`clock_nanosleep(CLOCK_MONOTONIC,TIMER_ABSTIME,&abstime,NULL)`按**绝对时间**睡，是周期任务无漂移标准写法——每轮目标时刻加固定周期，调度抖动不累积，注意它直接返回错误码、不走 errno。`usleep`已废弃；多线程禁用 SIGALRM 类进程级定时，统一 timerfd 或 timer_create 配 SIGEV_THREAD_ID 定向投递。

## 8. 快速参考卡片

常用系统调用速查（原型以 man 2 为准）：

| 分类 | 调用 | 用途 |
| --- | --- | --- |
| 文件 |`open/openat`、`read/write`、`pread/pwrite`、`readv/writev`|打开、IO、定点 IO、向量 IO |
| 文件 |`lseek`/`close`/`fsync`/`fdatasync`|偏移、关闭、落盘（close 遇 EINTR 不重试） |
| fd |`fcntl`/`ioctl`/`dup`/`dup2`/`dup3`|标志与锁、设备控制、复制重定向 |
| 零拷贝 |`sendfile`/`splice`/`tee`/`mmap`|减少用户态拷贝 |
| 进程 |`fork`/`execve`/`posix_spawn`、`waitpid`/`_exit`|创建、映像替换、回收、退出 |
| 进程 |`setsid`/`setpgid`/`getpid`|会话、进程组、身份 |
| 信号 |`sigaction`/`sigprocmask`/`sigsuspend`/`sigqueue`|捕获、屏蔽、等待、发送 |
| IPC |`pipe2`/`socketpair`/`mkfifo`|管道类 |
| IPC |`shmget/shmat`、`semop`、`msgget`、`shm_open`/`sem_open`/`mq_open`|SysV 与 POSIX |
| 事件 |`eventfd`/`signalfd`/`timerfd_create`|fd 化通知、信号、定时 |
| 时间 |`clock_gettime`/`clock_nanosleep`|取时、睡眠 |
| 串口 |`tcgetattr/tcsetattr/cfmakeraw/cfsetspeed`、`tcdrain/tcflush/TIOCSRS485`|线路参数、排空清队列、485 方向 |

高频 errno：

| errno | 含义与处置 |
| --- | --- |
|`EAGAIN`/`EWOULDBLOCK`|非阻塞暂无数据/不可写，等 epoll 事件，不是错误 |
|`EINTR`|被信号打断，按策略重试或上抛 |
|`EINPROGRESS`|非阻塞 connect 进行中，等 EPOLLOUT 后 SO_ERROR 取结果 |
|`EPIPE`/`ECONNRESET`|对端关读仍写/连接被 RST 重置 |
|`EBADF`|fd 非法或已关，重复 close、数组越界常见 |
|`EMFILE`/`ENFILE`|进程/系统 fd 耗尽，查 ulimit-n 与 file-max |
|`EADDRINUSE`|端口占用，服务重启需 SO_REUSEADDR |
|`ECHILD`|已无子进程，waitpid 循环退出条件 |
|`ENOENT`/`EACCES`/`EEXIST`|不存在/无权限/已存在 |
|`ENXIO`/`EIO`|设备不存在或拔出，串口重连依据 |

串口配置命令行模板（先于写代码验证参数）：

```bash
stty -F /dev/ttyUSB0 -a                                   # 查看当前参数
# 9600 8N1 raw：-icanon 关行缓冲 -echo 关回显 -ixon 关软流控 -isig 关信号字符
stty -F /dev/ttyUSB0 9600 raw -echo cs8 -cstopb -parenb -ixon -crtscts -isig
cat /dev/ttyUSB0 | xxd                                    # 十六进制监视
printf '\x01\x03\x00\x00\x00\x02\xc4\x0b' > /dev/ttyUSB0 # 发一帧 Modbus 读保持寄存器
```

## 9. 常见坑与排查清单

1. **fork 后子进程死锁在 malloc/printf**：其他线程持有的堆锁、stdio 锁被永久复制，fork 到 exec 之间只能用异步信号安全函数；需复用子进程跑自身代码改用 posix_spawn 或在单线程时期 fork。
2. **stdio 缓冲致日志双份/丢失**：fork 复制未 flush 的用户态缓冲，父子各刷一次；fork 前`fflush(NULL)`。
3. **handler 里调 printf/malloc/syslog**：异步信号不安全，可自死锁或堆损坏；handler 只置 sig_atomic_t 或 write，复杂逻辑转主循环或 signalfd。
4. **僵尸进程堆积**：只 wait 一次收不完同时退出的多个子（标准信号合并）；用 WNOHANG while 循环到 ECHILD，不需要退出码可 SIG_IGN 托底。
5. **EINTR 未重试**：poll/epoll_wait/nanosleep 永不被 SA_RESTART 重启，慢调用统一套重试封装。
6. **fd 泄漏与 CLOEXEC**：未 close 或 exec 时把监听 fd、管道继承给外部程序；创建处一律 O_CLOEXEC/SOCK_CLOEXEC/F_DUPFD_CLOEXEC；排查看`/proc/<pid>/fd`与 lsof（见《../08-网络与系统工具/08-lsof文件句柄排查.md》）。
7. **SysV IPC 不随进程退出释放**：残留内核直到 IPC_RMID/ipcrm/重启，容器部署注意 ipc 命名空间与清理钩子。
8. **串口未 raw 致特殊字节被吞**：ICRNL 改 0x0D、IXON 吞 0x11/0x13、ISTRIP 削高位、ISIG 让 0x03 杀进程、OPOST 插 0x0D；二进制协议第一步就是 cfmakeraw 并逐项核对四组标志。
9. **O_APPEND 与 lseek+write 混淆**：多进程追加必须 O_APPEND（内核原子定位到尾），lseek(SEEK_END)+write 有竞争窗口会互相覆盖。
10. **write 成功不等于落盘**：仅进 page cache；崩溃一致性要 fsync，新建文件还要 fsync 父目录。
11. **strerror 不可重入、errno 被覆盖**：多线程用 strerror_r，失败第一时间保存 errno。
12. **mmap 越界信号混淆**：超映射长度是 SIGSEGV，文件被截短后访问原区间是 SIGBUS，失败判据是 MAP_FAILED 不是 NULL。
13. **SIGPIPE 杀整个服务**：全局 SIG_IGN 或 send 带 MSG_NOSIGNAL，别让单个断连客户端终止进程。
14. **定时器错用 REALTIME**：校时瞬间产生超长/负超时；超时与周期任务一律 CLOCK_MONOTONIC + timerfd 或绝对时间 clock_nanosleep。
15. **VTIME 分帧粒度误判**：单位 0.1s，115200 下 3.5 字符仅约 0.3ms，必须软件打戳分帧；RS485 发完不 tcdrain 就切方向会截帧尾。
16. **exec 后状态误判**：捕获的信号重置默认、忽略保持忽略、屏蔽字保留、CLOEXEC fd 关闭；“父忽略 SIGPIPE、子 exec 外部程序”时要明确是有意继承还是重设。
17. **非阻塞 connect 处理缺失**：EINPROGRESS 后必须等 EPOLLOUT 再 getsockopt(SO_ERROR) 判定，直接当成功或失败都是 bug。
18. **close 后 fd 号被复用**：一线程 close 的 fd 被另一线程 open 复用，旧线程仍在读写形成 use-after-close；fd 生命周期要与共享状态同步，信号 handler 中 close 尤其危险。

---

上一篇：《04-信创国产化技术栈.md》　｜　模块索引：《../README.md》
