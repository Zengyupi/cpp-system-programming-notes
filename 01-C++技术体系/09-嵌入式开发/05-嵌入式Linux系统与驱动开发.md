# 嵌入式Linux系统与驱动开发

> 本节目标：掌握嵌入式 Linux 的完整启动链（BootROM→SPL→U-Boot→内核→rootfs）、设备树的描述与匹配机制、字符设备驱动框架、交叉编译与根文件系统构建；深入 Flash 文件系统的选型（FATFS/LittleFS/JFFS2/UBIFS/SquashFS）与挂载使用；掌握嵌入式 Linux 驱动进阶——platform 驱动框架、I2C/SPI 子系统驱动编写、中断下半部 workqueue/tasklet、内核模块编写与加载。学完后能独立完成嵌入式 Linux 板级移植与驱动开发。

---

## 本章速览

- [1. 嵌入式 Linux 系统与启动](#1-嵌入式-linux-系统与启动)
  - [1.1 启动链](#11-启动链)
  - [1.2 设备树（Device Tree）：描述"板上有什么硬件"](#12-设备树device-tree描述板上有什么硬件)
  - [1.3 字符设备驱动框架](#13-字符设备驱动框架)
  - [1.4 交叉编译与 sysroot](#14-交叉编译与-sysroot)
  - [1.5 根文件系统：Buildroot vs Yocto](#15-根文件系统buildroot-vs-yocto)
- [2. Flash 文件系统选型与使用](#2-flash-文件系统选型与使用)
  - [2.1 文件系统对比与选型](#21-文件系统对比与选型)
  - [2.2 选型决策](#22-选型决策)
  - [2.3 挂载与使用示例](#23-挂载与使用示例)
- [3. 嵌入式 Linux 驱动进阶](#3-嵌入式-linux-驱动进阶)
  - [3.1 platform 驱动框架](#31-platform-驱动框架)
  - [3.2 I2C / SPI 子系统驱动编写](#32-i2c--spi-子系统驱动编写)
  - [3.3 中断下半部：workqueue 与 tasklet](#33-中断下半部workqueue-与-tasklet)
  - [3.4 内核模块编写与加载](#34-内核模块编写与加载)

---

## 1. 嵌入式 Linux 系统与启动

### 1.1 启动链

```text
上电
 ▼
BootROM（芯片固化，不可改）：决定从 eMMC/SD/NAND/UART/USB 启动，加载 SPL
 ▼
SPL（一级，片内 SRAM 运行）：初始化 DDR 控制器，把主 U-Boot 从存储搬进 DDR
 ▼
U-Boot（二级）：初始化时钟/外设，提供命令行，加载内核 zImage + 设备树 dtb +（可选）initramfs
 ▼            支持 tftp/nfs 网络启动（开发期极方便）、bootm/bootz、环境变量 bootcmd/bootargs
Linux 内核：解压、初始化各子系统与驱动（靠 dtb 知道有什么硬件），挂载 rootfs
 ▼
init（PID 1）：systemd / SysV init / BusyBox init，启动守护进程与业务程序
```

| 阶段 | 关键产物 |
| --- | --- |
| BootROM/SPL | 芯片厂商提供，u-boot-spl / MLO |
| Bootloader | U-Boot（主流）、barebox |
| 内核 | Image/zImage/bzImage + **.dtb 设备树** |
| 根文件系统 | Buildroot/Yocto 生成（含 libc、busybox、应用） |

### 1.2 设备树（Device Tree）：描述"板上有什么硬件"

设备树把硬件信息从内核代码里抽出来，用文本 `.dts` 描述、编译成二进制 `.dtb` 供内核解析（`dts→dtc→dtb`，可反编译 `dtc -I dtb -O dts`）。

```dts
/ {
    chosen {                          // 内核参数与控制台
        bootargs = "console=ttymxc0,115200 root=/dev/mmcblk1p2 rw";
        stdout-path = &uart1;
    };
    soc {
        uart1: serial@02020000 {
            compatible = "fsl,imx6ul-uart", "fsl,imx6q-uart"; // ★驱动匹配依据
            reg = <0x02020000 0x4000>;     // 寄存器基址与长度
            interrupts = <GIC_SPI 26 IRQ_TYPE_LEVEL_HIGH>;    // 中断号/触发方式
            clocks = <&clks IMX6UL_CLK_UART1_IPG>;
            status = "okay";               // okay 启用 / disabled 关闭
            pinctrl-0 = <&pinctrl_uart1>;  // 引脚复用
        };
        i2c1: i2c@021a0000 {
            #address-cells = <1>; #size-cells = <0>;
            clock@68 { compatible = "si5351"; reg = <0x68>; }; // 从机地址
        };
    };
};
```

| 概念 | 说明 |
| --- | --- |
| `compatible` | 驱动与设备匹配的 key，驱动 of_match_table 里写同样字符串即绑定 |
| `reg/interrupts/clocks` | 资源（地址、中断、时钟），驱动里用 platform_get_resource/of_ 函数取 |
| `aliases/chosen` | 别名、启动参数与控制台 |
| `pinctrl` | 引脚复用与电气配置 |
| overlay | 不重编主 dts，运行期叠加设备节点（配扩展板常用） |
| 查看 | `/proc/device-tree/` 下可看到解析后的节点；`ls /sys/bus/platform/devices` |

### 1.3 字符设备驱动框架

```c
// 一个最小字符设备驱动骨架：用户态 open/read/write 最终调到这些函数
#include <linux/module.h>
#include <linux/fs.h>
#include <linux/cdev.h>
#include <linux/device.h>

static dev_t devno;
static struct cdev my_cdev;
static struct class *my_class;

static int   my_open (struct inode *i, struct file *f){ return 0; }
static ssize_t my_read (struct file *f, char __user *buf, size_t n, loff_t *off){
    // copy_to_user：内核→用户，不能直接解引用用户指针
    return 0;
}
static ssize_t my_write(struct file *f, const char __user *buf, size_t n, loff_t *off){
    // copy_from_user：用户→内核
    return n;
}
static int   my_release(struct inode *i, struct file *f){ return 0; }
static const struct file_operations fops = {
    .owner = THIS_MODULE, .open = my_open, .read = my_read,
    .write = my_write, .release = my_release,
};
static int __init my_init(void){
    alloc_chrdev_region(&devno, 0, 1, "mydev");   // 动态申请主/次设备号
    cdev_init(&my_cdev, &fops); cdev_add(&my_cdev, devno, 1);
    my_class = class_create(THIS_MODULE, "mycls");
    device_create(my_class, NULL, devno, NULL, "mydev"); // 自动生成 /dev/mydev
    return 0;
}
static void __exit my_exit(void){
    device_destroy(my_class, devno); class_destroy(my_class);
    cdev_del(&my_cdev); unregister_chrdev_region(devno, 1);
}
module_init(my_init); module_exit(my_exit);
MODULE_LICENSE("GPL");
```

> 用户态→系统调用（open/read/write）→VFS→`file_operations`→驱动操作硬件。中断用 `request_irq`，阻塞用等待队列/wait_event，与用户态同步用阻塞 read、poll/epoll、fasync 或 ioctl。内核态不能用 libc、不能浮点、栈很小（几 KB）。

### 1.4 交叉编译与 sysroot

```bash
# 交叉工具链命名：架构-厂商-内核-库
#   arm-none-eabi-      裸机（无 OS，newlib）
#   arm-linux-gnueabihf- ARM Linux，硬浮点（hf）
#   aarch64-linux-gnu-  64 位 ARM
arm-linux-gnueabihf-gcc -O2 app.c -o app          # 编译
# --sysroot 指定目标板的头文件/库根目录，避免链接到主机 x86 库
./configure --host=arm-linux-gnueabihf --prefix=/usr --sysroot=$HOME/sysroot
file app        # 确认是 ELF 32-bit LSB executable, ARM
# 板上调试：gdbserver :9999 ./app；主机 arm-linux-gnueabihf-gdb 后 target remote <板IP>:9999
```

### 1.5 根文件系统：Buildroot vs Yocto

| 维度 | Buildroot | Yocto/OpenEmbedded |
| --- | --- | --- |
| 定位 | 简单快速、Makefile + Kconfig | 企业级框架，recipe/layer/bitbake |
| 上手 | 半天出镜像 | 学习曲线陡 |
| 定制 | 改 package 配置 | 写 .bb recipe、自己的 layer |
| 适合 | 中小项目、快速原型、学习 | 量产产品、长期维护、多板多产品 |
| 产物 | zImage+dtb+rootfs 一把出 | image/SDK，可复现构建 |

> BusyBox 用一个二进制 + 软链接实现上百个常用命令，是最小 rootfs 的基础；libc 可选 glibc（全、大）/musl（小）/uClibc-ng（小）。

---

## 2. Flash 文件系统选型与使用

嵌入式设备的存储介质主要是 NOR/NAND Flash、eMMC、SD 卡。Flash 有"先擦后写、擦写次数有限（万~十万次）、按块擦除"的物理特性，文件系统需要针对这些特性做磨损均衡和坏块管理。

### 2.1 文件系统对比与选型

| 维度 | FATFS / FAT32 | LittleFS | JFFS2 | UBIFS | SquashFS |
| --- | --- | --- | --- | --- | --- |
| **类型** | 通用文件系统（MCU/Linux 都有） | 专为 MCU 设计的小文件系统 | Linux Flash 文件系统 | Linux Flash 文件系统（UBI 层上） | 只读压缩文件系统 |
| **磨损均衡** | 无（需额外实现） | 有（动态磨损均衡） | 有（日志结构） | 有（UBI 层提供） | 不适用（只读） |
| **压缩** | 无 | 无 | 有（zlib） | 有（zlib/LZO/ZSTD） | 有（gzip/LZO/XZ/ZSTD） |
| **只读/可写** | 可写 | 可写 | 可写 | 可写 | **只读** |
| **启动速度** | 快（简单） | 快 | 慢（挂载时扫描全分区） | 较快（UBI 索引） | 极快（只读压缩，按需解压） |
| **内存占用** | 极小（~2KB RAM） | 小（~2KB RAM） | 大（节点缓存，与文件数成正比） | 中（比 JFFS2 小） | 极小（按需解压到页缓存） |
| **掉电安全** | 差（需写时复制） | **强**（copy-on-write + CRC，掉电回滚到上一一致状态） | 较强（日志结构） | 较强 | 不适用（只读） |
| **适用介质** | SD/eMMC/USB（块设备） | NOR/NAND/ SPI Flash（裸 Flash） | NAND/NOR（MTD 原始 Flash） | NAND（UBI 层，推荐 NAND） | 任意（只读根文件系统） |
| **典型场景** | SD 卡数据交换、U盘 | MCU 上 SPI Flash 存配置/日志 | 老款 NAND Flash 设备 | 大容量 NAND Flash 量产产品 | 只读 rootfs（系统分区）+ 可写数据分区 |

### 2.2 选型决策

```text
存储介质是什么？
├─ SD/eMMC/USB（块设备，有自己的 FTL 磨损均衡）
│   ├─ 需要可写数据 → FAT32/exFAT（兼容性好）或 ext4（Linux 完整功能）
│   └─ 只读系统分区 → SquashFS（压缩省空间、启动快、不可篡改）
└─ 裸 SPI NOR/NAND Flash（无 FTL，需文件系统自己做磨损均衡）
    ├─ MCU（无 OS/RTOS，资源紧）→ LittleFS（掉电安全、磨损均衡、极小 RAM）
    ├─ Linux + 小容量 NOR → JFFS2（简单，但挂载慢）
    └─ Linux + 大容量 NAND → UBIFS（UBI 层管理坏块/磨损，挂载快，推荐）
```

> **最佳实践**：嵌入式 Linux 设备常做"双分区"——系统分区用 SquashFS（只读、压缩、安全），数据分区用 UBIFS/ext4（可写、磨损均衡）。这样系统升级只替换 SquashFS 镜像，用户数据不丢。

### 2.3 挂载与使用示例

#### LittleFS（MCU 上 SPI Flash）

```c
#include "lfs.h"
#include "spi_flash.h"

static lfs_t lfs;
static struct lfs_config cfg;

// LittleFS 需要的底层操作：读/写/擦除/同步（对接 SPI Flash 驱动）
static int flash_read(const struct lfs_config *c, lfs_block_t block,
                      lfs_off_t off, void *buf, lfs_size_t size) {
    return spi_flash_read(block * c->block_size + off, buf, size);
}
static int flash_prog(const struct lfs_config *c, lfs_block_t block,
                      lfs_off_t off, const void *buf, lfs_size_t size) {
    return spi_flash_program(block * c->block_size + off, buf, size);
}
static int flash_erase(const struct lfs_config *c, lfs_block_t block) {
    return spi_flash_erase_sector(block * c->block_size);
}
static int flash_sync(const struct lfs_config *c) { return 0; }

void littlefs_init(void) {
    cfg.read  = flash_read;
    cfg.prog  = flash_prog;
    cfg.erase = flash_erase;
    cfg.sync  = flash_sync;
    cfg.read_size  = 16;      // 最小读单位
    cfg.prog_size  = 16;      // 最小写单位（页大小）
    cfg.block_size = 4096;    // 擦除块大小（扇区）
    cfg.block_count = 512;    // 总块数（512 * 4K = 2MB）
    cfg.cache_size = 16;
    cfg.lookahead_size = 16;
    cfg.block_cycles = 500;    // 磨损均衡参数（块擦写次数阈值）

    int err = lfs_mount(&lfs, &cfg);
    if (err) {
        lfs_format(&lfs, &cfg);   // 首次使用或损坏时格式化
        lfs_mount(&lfs, &cfg);
    }

    // 写文件
    lfs_file_t f;
    lfs_file_open(&lfs, &f, "config.json", LFS_O_WRONLY | LFS_O_CREAT);
    lfs_file_write(&lfs, &f, "{\"ip\":\"192.168.1.1\"}", 20);
    lfs_file_close(&lfs, &f);

    // 读文件
    lfs_file_open(&lfs, &f, "config.json", LFS_O_RDONLY);
    char buf[64];
    lfs_ssize_t n = lfs_file_read(&lfs, &f, buf, sizeof(buf));
    lfs_file_close(&lfs, &f);
}
```

#### UBIFS（Linux NAND Flash）

```bash
# 1. 准备 UBI 卷（假设 MTD 分区 /dev/mtd3 是 NAND 数据分区）
ubiformat /dev/mtd3              # 格式化 MTD 分区为 UBI 格式
ubiattach /dev/ubi_ctrl -m 3     # 附加 MTD3 到 UBI，创建 /dev/ubi0
ubimkvol /dev/ubi0 -N data -m    # 在 ubi0 上创建名为 data 的卷，使用全部空间
# 卷设备为 /dev/ubi0_0

# 2. 格式化并挂载
mkfs.ubifs -m 2048 -e 124KiB -c 4096 -r /tmp/rootfs /tmp/rootfs.ubifs
#   -m: min I/O size（NAND 页大小）
#   -e: logical erase block size
#   -c: max logical erase block count
mount -t ubifs ubi0:data /mnt/data

# 3. 写入 /etc/fstab 实现开机自动挂载
# ubi0:data  /mnt/data  ubifs  defaults  0  0
```

#### SquashFS（只读根文件系统）

```bash
# 制作 SquashFS 镜像
mksquashfs /tmp/rootfs /tmp/rootfs.sqfs -comp xz -b 256K -noappend
#   -comp xz: 用 xz 压缩（压缩率最高，解压稍慢；也可用 gzip/lzo/zstd）
#   -b 256K: 块大小

# 烧录到 Flash 分区后，U-Boot bootargs 指定：
# root=/dev/mtdblock4 rootfstype=squashfs ro

# 或作为 loop 设备挂载（开发调试）
mount -t squashfs -o loop /tmp/rootfs.sqfs /mnt/rootfs
```

---

## 3. 嵌入式 Linux 驱动进阶

字符设备驱动是基础，但实际嵌入式 Linux 驱动大多基于总线框架（platform/I2C/SPI）编写，并需要处理中断的"顶半部/底半部"。

### 3.1 platform 驱动框架

platform 总线是 Linux 为"无标准总线的片上外设"（UART/I2C/SPI 控制器、定时器等）设计的虚拟总线。设备信息来自设备树，驱动通过 `compatible` 匹配。

```c
#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/of.h>
#include <linux/io.h>
#include <linux/interrupt.h>

struct my_dev {
    void __iomem *base;      // 寄存器映射后的虚拟地址
    int irq;                  // 中断号
    struct cdev cdev;
    dev_t devno;
};

// 中断处理（顶半部）
static irqreturn_t my_irq(int irq, void *dev_id) {
    struct my_dev *dev = dev_id;
    u32 status = readl(dev->base + 0x0C);  // 读中断状态寄存器
    writel(status, dev->base + 0x0C);       // 写 1 清中断
    // 底半部处理（见 3.3）：调度 workqueue
    // schedule_work(&dev->work);
    return IRQ_HANDLED;
}

static int my_probe(struct platform_device *pdev) {
    struct my_dev *dev;
    struct resource *res;

    dev = devm_kzalloc(&pdev->dev, sizeof(*dev), GFP_KERNEL);
    if (!dev) return -ENOMEM;

    // 从设备树获取寄存器资源并映射
    res = platform_get_resource(pdev, IORESOURCE_MEM, 0);
    dev->base = devm_ioremap_resource(&pdev->dev, res);
    if (IS_ERR(dev->base)) return PTR_ERR(dev->base);

    // 从设备树获取中断号
    dev->irq = platform_get_irq(pdev, 0);
    if (dev->irq < 0) return dev->irq;

    // 注册中断（共享中断用 IRQF_SHARED）
    devm_request_irq(&pdev->dev, dev->irq, my_irq,
                     IRQF_TRIGGER_RISING, "mydev", dev);

    // 注册字符设备（省略，同 1.3）
    platform_set_drvdata(pdev, dev);
    dev_info(&pdev->dev, "probed\n");
    return 0;
}

static int my_remove(struct platform_device *pdev) {
    // devm_ 分配的资源自动释放
    return 0;
}

// 设备树匹配表：与 dts 中的 compatible 对应
static const struct of_device_id my_of_match[] = {
    { .compatible = "mycompany,mydev-1.0", },
    { /* sentinel */ }
};
MODULE_DEVICE_TABLE(of, my_of_match);

static struct platform_driver my_driver = {
    .probe  = my_probe,
    .remove = my_remove,
    .driver = {
        .name = "mydev-driver",
        .of_match_table = my_of_match,
    },
};
module_platform_driver(my_driver);  // 等价于 module_init + module_exit
MODULE_LICENSE("GPL");
```

对应的设备树节点：

```dts
mydev@40001000 {
    compatible = "mycompany,mydev-1.0";
    reg = <0x40001000 0x1000>;
    interrupts = <GIC_SPI 30 IRQ_TYPE_EDGE_RISING>;
    status = "okay";
};
```

### 3.2 I2C / SPI 子系统驱动编写

#### I2C 设备驱动

I2C 设备驱动通过 `i2c_driver` 注册，匹配方式同样是 `compatible`（设备树）或 `id_table`。

```c
#include <linux/i2c.h>
#include <linux/module.h>

struct sensor_dev {
    struct i2c_client *client;
    int temp;
};

// 读 I2C 寄存器的封装
static int sensor_read_reg(struct i2c_client *client, u8 reg, u8 *val) {
    // i2c_smbus_read_byte_data: 写寄存器地址 + 读 1 字节
    s32 ret = i2c_smbus_read_byte_data(client, reg);
    if (ret < 0) return ret;
    *val = (u8)ret;
    return 0;
}

static int sensor_probe(struct i2c_client *client) {
    struct sensor_dev *dev;
    u8 id;

    dev = devm_kzalloc(&client->dev, sizeof(*dev), GFP_KERNEL);
    if (!dev) return -ENOMEM;
    dev->client = client;

    // 读芯片 ID 寄存器，确认硬件存在
    if (sensor_read_reg(client, 0x00, &id) < 0 || id != 0x5A) {
        dev_err(&client->dev, "wrong chip id: 0x%02x\n", id);
        return -ENODEV;
    }

    i2c_set_clientdata(client, dev);
    dev_info(&client->dev, "sensor probed\n");
    return 0;
}

static const struct of_device_id sensor_of_match[] = {
    { .compatible = "mycompany,temp-sensor", },
    { }
};
MODULE_DEVICE_TABLE(of, sensor_of_match);

static struct i2c_driver sensor_driver = {
    .probe = sensor_probe,
    .driver = {
        .name = "temp-sensor",
        .of_match_table = sensor_of_match,
    },
};
module_i2c_driver(sensor_driver);
MODULE_LICENSE("GPL");
```

设备树中 I2C 从机节点：

```dts
&i2c1 {
    temp-sensor@48 {
        compatible = "mycompany,temp-sensor";
        reg = <0x48>;     // I2C 7 位地址
    };
};
```

#### SPI 设备驱动

SPI 驱动与 I2C 类似，用 `spi_driver` 注册，数据传输用 `spi_sync`/`spi_write_then_read`。

```c
#include <linux/spi/spi.h>

static int flash_read_id(struct spi_device *spi, u8 *id, size_t len) {
    u8 tx[4] = {0x9F, 0, 0, 0};  // JEDEC ID 命令
    u8 rx[4];
    struct spi_transfer t = {
        .tx_buf = tx, .rx_buf = rx, .len = 4,
    };
    struct spi_message m;
    spi_message_init(&m);
    spi_message_add_tail(&t, &m);
    spi_sync(spi, &m);          // 同步传输（阻塞）
    memcpy(id, &rx[1], len);    // rx[0] 是哑字节，rx[1..3] 是 ID
    return 0;
}
```

### 3.3 中断下半部：workqueue 与 tasklet

Linux 中断处理分"顶半部"（hardirq，快速响应、关中断）和"底半部"（softirq/tasklet/workqueue，可延迟、开中断执行）。

| 底半部机制 | 执行上下文 | 可睡眠 | 可并发 | 适用场景 |
| --- | --- | --- | --- | --- |
| **softirq** | 中断上下文（软中断） | 否 | 是（同类型可在多 CPU 并发） | 网络协议栈、块设备（高频、性能关键） |
| **tasklet** | 中断上下文（基于 softirq） | 否 | 否（同类型不并发，更简单） | 驱动中中等频率的延迟处理 |
| **workqueue** | 内核线程上下文（进程上下文） | **是**（可睡眠、可调度） | 是（取决于 worker 数量） | 需要睡眠、调用可能阻塞的函数（如 I2C/SPI 传输、mutex） |

> **选择原则**：底半部需要睡眠/调用阻塞函数 → 用 workqueue；纯原子操作、不睡眠 → 用 tasklet 或直接在 hardirq 完成。嵌入式驱动中 workqueue 最常用。

#### workqueue 示例

```c
#include <linux/workqueue.h>

struct my_dev {
    void __iomem *base;
    int irq;
    struct work_struct work;     // 工作项
    struct workqueue_struct *wq; // 专用工作队列（也可用系统全局队列 system_wq）
};

// 底半部：在工作线程中执行，可睡眠、可调用阻塞函数
static void my_work_handler(struct work_struct *work) {
    struct my_dev *dev = container_of(work, struct my_dev, work);
    // 这里可以做耗时操作：读 I2C/SPI、处理数据、更新 sysfs 等
    u32 data = readl(dev->base + 0x10);
    process_data(data);
}

static irqreturn_t my_irq(int irq, void *dev_id) {
    struct my_dev *dev = dev_id;
    u32 status = readl(dev->base + 0x0C);
    writel(status, dev->base + 0x0C);  // 清中断
    // 调度底半部：把 work 加入工作队列，立即返回
    queue_work(dev->wq, &dev->work);
    return IRQ_HANDLED;
}

static int my_probe(struct platform_device *pdev) {
    struct my_dev *dev = devm_kzalloc(&pdev->dev, sizeof(*dev), GFP_KERNEL);
    // ... 寄存器映射、中断注册（同 3.1） ...

    INIT_WORK(&dev->work, my_work_handler);  // 初始化工作项
    dev->wq = create_singlethread_workqueue("mywq");  // 创建单线程工作队列
    if (!dev->wq) return -ENOMEM;

    return 0;
}
```

#### tasklet 示例（不睡眠场景）

```c
#include <linux/interrupt.h>

struct my_dev {
    struct tasklet_struct tasklet;
};

static void my_tasklet(unsigned long data) {
    struct my_dev *dev = (struct my_dev *)data;
    // 不睡眠的快速处理：更新统计、操作寄存器等
}

static irqreturn_t my_irq(int irq, void *dev_id) {
    struct my_dev *dev = dev_id;
    // 清中断
    tasklet_schedule(&dev->tasklet);  // 调度 tasklet
    return IRQ_HANDLED;
}

// probe 中：
tasklet_init(&dev->tasklet, my_tasklet, (unsigned long)dev);
```

### 3.4 内核模块编写与加载

```makefile
# Makefile：内核模块的标准编译方式
obj-m += my_driver.o
# 如果有多个源文件：my_driver-objs := main.o i2c.o spi.o

KDIR ?= /lib/modules/$(shell uname -r)/build
# 交叉编译时指定：KDIR=/path/to/linux-source ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf-

all:
	make -C $(KDIR) M=$(PWD) modules

clean:
	make -C $(KDIR) M=$(PWD) clean
```

```bash
# 编译（本机）
make

# 交叉编译（ARM）
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- KDIR=/path/to/linux

# 加载模块
insmod my_driver.ko
# 或自动解决依赖
modprobe my_driver

# 查看已加载模块
lsmod | grep my_driver

# 查看模块信息（作者、许可、依赖、vermagic）
modinfo my_driver.ko

# 卸载模块
rmmod my_driver

# 查看内核日志（驱动中 dev_info/dev_err 的输出）
dmesg | tail -20
# 实时跟踪
dmesg -w
```

> **常见坑**：① 模块的 `vermagic`（内核版本+编译器+SMP 等）必须与目标内核一致，否则 `insmod` 报 `Invalid module format`；② 驱动中用 `printk` 不如用 `dev_info/dev_err`（自动带设备名、支持动态调试）；③ `copy_to_user/copy_from_user` 可能失败（用户地址无效），必须检查返回值；④ 内核栈只有 8KB/16KB，禁止大局部数组和深递归；⑤ 用 `devm_` 系列函数（`devm_kzalloc`/`devm_ioremap`/`devm_request_irq`）自动管理资源，probe 失败或 remove 时自动释放，减少泄漏。

---

上一篇：《04-中断系统与RTOS原理.md》
下一篇：《06-低功耗可靠性与OTA升级.md》
