# Shell 脚本编程

> 本节目标：系统讲解 Bash Shell 脚本编程的核心语法与实用技巧，包括变量、条件判断、循环、函数、输入输出、错误处理、字符串操作与脚本模板，学完后能够独立编写健壮的 Shell 自动化脚本。

## 本章速览

- [1. 概述](#1-概述)
- [2. 变量与数据类型](#2-变量与数据类型)
  - [2.1 变量定义与使用](#21-变量定义与使用)
  - [2.2 特殊变量](#22-特殊变量)
  - [2.3 数组](#23-数组)
  - [2.4 关联数组（字典）](#24-关联数组字典)
- [3. 条件判断](#3-条件判断)
  - [3.1 test 命令和 `\[ \]` 与 `\[\[ \]\]`](#31-test-命令和---与--)
  - [3.2 if 语句](#32-if-语句)
  - [3.3 case 语句](#33-case-语句)
- [4. 循环结构](#4-循环结构)
  - [4.1 for 循环](#41-for-循环)
  - [4.2 while 循环](#42-while-循环)
  - [4.3 until 循环（条件为假时执行）](#43-until-循环条件为假时执行)
  - [4.4 循环控制](#44-循环控制)
- [5. 函数](#5-函数)
  - [5.1 函数定义与调用](#51-函数定义与调用)
  - [5.2 函数中的特殊变量](#52-函数中的特殊变量)
- [6. 输入输出](#6-输入输出)
  - [6.1 输出](#61-输出)
  - [6.2 输入](#62-输入)
  - [6.3 重定向与管道](#63-重定向与管道)
- [7. 错误处理](#7-错误处理)
  - [7.1 退出码](#71-退出码)
  - [7.2 set 选项（脚本级错误处理）](#72-set-选项脚本级错误处理)
  - [7.3 trap 信号捕获](#73-trap-信号捕获)
- [8. 字符串操作](#8-字符串操作)
  - [8.1 字符串截取与替换](#81-字符串截取与替换)
  - [8.2 默认值与空值处理（参数展开）](#82-默认值与空值处理参数展开)
- [9. 算术运算](#9-算术运算)
- [10. 常用内置命令](#10-常用内置命令)
- [11. 命令行参数解析](#11-命令行参数解析)
  - [11.1 使用 getopts（推荐）](#111-使用-getopts推荐)
  - [11.2 手动解析（简单场景）](#112-手动解析简单场景)
- [12. 实用脚本模板](#12-实用脚本模板)
  - [12.1 通用脚本模板](#121-通用脚本模板)
  - [12.2 安全脚本模板（带错误处理）](#122-安全脚本模板带错误处理)
- [13. 常用 Shell 脚本模式](#13-常用-shell-脚本模式)
  - [13.1 并发执行](#131-并发执行)
  - [13.2 进度条](#132-进度条)
  - [13.3 配置文件读取](#133-配置文件读取)
- [14. 快速参考卡片](#14-快速参考卡片)
- [15. 常见错误与调试](#15-常见错误与调试)
  - [15.1 常见错误](#151-常见错误)
  - [15.2 调试技巧](#152-调试技巧)

---

## 1. 概述

本文档涵盖 Shell 脚本编写的核心命令、语法结构和最佳实践。基于 **Bash**（Bourne Again Shell），这是 Linux 下最常用的 Shell 解释器。

**脚本基本结构：**

```bash
#!/bin/bash
# 脚本说明：描述脚本功能
# 作者：xxx
# 版本：1.0

set -e  # 遇到错误立即退出（可选）
set -x  # 调试模式，打印每条执行的命令（可选）

# 脚本主体
echo "Hello World"
```

**脚本执行方式：**

```bash
bash script.sh          # 通过 bash 执行（推荐）
./script.sh             # 需要执行权限（chmod +x script.sh）
source script.sh        # 在当前 Shell 执行（环境变量会保留）
. script.sh             # source 的简写
```

---

## 2. 变量与数据类型

### 2.1 变量定义与使用

| 语法                     | 说明                           | 示例                                                         |
| ------------------------ | ------------------------------ | ------------------------------------------------------------ |
| `变量名=值`              | 定义变量（等号两边不能有空格） | `name="John"`                                                |
| `$变量名` 或 `${变量名}` | 引用变量（推荐加 `{}`）        | `echo $name`、`echo ${name}`                                 |
| `readonly 变量名`        | 定义只读变量                   | `readonly PI=3.14`                                           |
| `unset 变量名`           | 删除变量                       | `unset name`                                                 |
| `export 变量名`          | 导出为环境变量（子进程可见）   | `export PATH=$PATH:/usr/local/bin`                           |
| `declare` / `typeset`    | 声明变量类型                   | `declare -i count=10`（整数）、`declare -r`（只读）、`declare -a`（数组） |

```bash
#!/bin/bash
# 变量定义
name="Alice"
age=25
readonly GENDER="female"

# 变量引用
echo "Name: $name, Age: ${age}"

# 命令替换（两种方式）
current_date=$(date +%Y-%m-%d)   # 推荐方式
current_time=`date +%H:%M:%S`    # 旧方式

# 算术运算（需用 $((...))）
sum=$((10 + 20))
echo "Sum: $sum"

# 导出环境变量
export MY_PATH="/opt/myapp"
```

### 2.2 特殊变量

| 变量           | 说明                                   | 示例                        |
| -------------- | -------------------------------------- | --------------------------- |
| `$0`           | 脚本名称                               | `./script.sh`               |
| `$1` - `$9`    | 位置参数（第1-9个参数）                | `./script.sh arg1 arg2`     |
| `${10}` 及以上 | 位置参数（需加花括号）                 | `${10}`                     |
| `$#`           | 参数个数                               | `3`                         |
| `$@`           | 所有参数（每个参数独立引用）           | `"$@"` → `"arg1" "arg2"`    |
| `$*`           | 所有参数（所有参数作为一个字符串）     | `"$*"` → `"arg1 arg2 arg3"` |
| `$$`           | 当前脚本的进程 ID（PID）               | `12345`                     |
| `$?`           | 上一条命令的退出码（0 成功，非0 失败） | `0` 或 `1`                  |
| `$!`           | 后台运行的最后一个进程的 PID           | -                           |
| `$_`           | 上一条命令的最后一个参数               | -                           |

```bash
#!/bin/bash
echo "脚本名称: $0"
echo "参数个数: $#"
echo "所有参数: $@"
echo "第一个参数: $1"
echo "第二个参数: ${2:-default}"  # 如果参数不存在，使用默认值
echo "脚本 PID: $$"
```

### 2.3 数组

| 语法                       | 说明         | 示例                        |
| -------------------------- | ------------ | --------------------------- |
| `数组名=(元素1 元素2 ...)` | 定义数组     | `arr=(apple banana orange)` |
| `数组名[索引]=值`          | 赋值指定索引 | `arr[3]="grape"`            |
| `${数组名[索引]}`          | 访问元素     | `echo ${arr[0]}`            |
| `${数组名[@]}`             | 获取所有元素 | `echo ${arr[@]}`            |
| `${#数组名[@]}`            | 获取数组长度 | `len=${#arr[@]}`            |
| `${!数组名[@]}`            | 获取所有索引 | `echo ${!arr[@]}`           |
| `unset 数组名[索引]`       | 删除元素     | `unset arr[1]`              |

```bash
#!/bin/bash
# 定义数组
fruits=("apple" "banana" "orange" "grape")

# 访问元素
echo "第一个水果: ${fruits[0]}"
echo "所有水果: ${fruits[@]}"

# 遍历数组
for fruit in "${fruits[@]}"; do
    echo "水果: $fruit"
done

# 获取数组长度
echo "数组长度: ${#fruits[@]}"

# 添加元素
fruits+=("watermelon")
```

### 2.4 关联数组（字典）

| 语法                | 说明         | 示例                 |
| ------------------- | ------------ | -------------------- |
| `declare -A 数组名` | 声明关联数组 | `declare -A user`    |
| `数组名[键]=值`     | 赋值         | `user[name]="Alice"` |
| `${数组名[键]}`     | 访问         | `echo ${user[name]}` |
| `${!数组名[@]}`     | 获取所有键   | `echo ${!user[@]}`   |
| `${数组名[@]}`      | 获取所有值   | `echo ${user[@]}`    |

```bash
#!/bin/bash
declare -A user
user[name]="Alice"
user[age]=25
user[city]="Beijing"

# 访问
echo "Name: ${user[name]}"

# 遍历键值
for key in "${!user[@]}"; do
    echo "$key: ${user[$key]}"
done
```

---

## 3. 条件判断

### 3.1 test 命令和 `[ ]` 与 `[[ ]]`

| 语法               | 说明                                                  |
| ------------------ | ----------------------------------------------------- |
| `[ 条件 ]`         | 传统测试命令（POSIX 兼容）                            |
| `[[ 条件 ]]`       | 增强测试命令（Bash 特有，支持正则和字符串比较，推荐） |
| `(( 算术表达式 ))` | 算术判断（C 风格）                                    |

**文件测试运算符：**

| 运算符    | 说明               | 示例                  |
| --------- | ------------------ | --------------------- |
| `-f 文件` | 是否为普通文件     | `[ -f /etc/passwd ]`  |
| `-d 目录` | 是否为目录         | `[ -d /tmp ]`         |
| `-e 文件` | 文件是否存在       | `[ -e /path ]`        |
| `-L 文件` | 是否为符号链接     | `[ -L /bin/sh ]`      |
| `-r 文件` | 是否可读           | `[ -r file.txt ]`     |
| `-w 文件` | 是否可写           | `[ -w file.txt ]`     |
| `-x 文件` | 是否可执行         | `[ -x script.sh ]`    |
| `-s 文件` | 文件大小是否非零   | `[ -s file.txt ]`     |
| `-nt`     | 文件1是否比文件2新 | `[ file1 -nt file2 ]` |
| `-ot`     | 文件1是否比文件2旧 | `[ file1 -ot file2 ]` |

**字符串比较：**

| 运算符      | 说明                            | 示例                       |
| ----------- | ------------------------------- | -------------------------- |
| `-z 字符串` | 字符串是否为空                  | `[ -z "$name" ]`           |
| `-n 字符串` | 字符串是否非空                  | `[ -n "$name" ]`           |
| `==` / `=`  | 字符串相等（`[[ ]]` 中用 `==`） | `[[ "$str1" == "$str2" ]]` |
| `!=`        | 字符串不等                      | `[[ "$str1" != "$str2" ]]` |
| `<` / `>`   | 字符串小于/大于（字典序）       | `[[ "$a" < "$b" ]]`        |
| `=~`        | 正则表达式匹配（`[[ ]]` 中）    | `[[ "$str" =~ ^[0-9]+$ ]]` |

**数值比较：**

| 运算符 | 说明     | 示例            |
| ------ | -------- | --------------- |
| `-eq`  | 等于     | `[ $a -eq $b ]` |
| `-ne`  | 不等于   | `[ $a -ne $b ]` |
| `-gt`  | 大于     | `[ $a -gt $b ]` |
| `-ge`  | 大于等于 | `[ $a -ge $b ]` |
| `-lt`  | 小于     | `[ $a -lt $b ]` |
| `-le`  | 小于等于 | `[ $a -le $b ]` |

```bash
#!/bin/bash
# 文件判断
if [[ -f "/etc/passwd" ]]; then
    echo "/etc/passwd 是普通文件"
fi

# 字符串判断
str1="hello"
str2="world"
if [[ -n "$str1" && "$str1" != "$str2" ]]; then
    echo "str1 非空且不等于 str2"
fi

# 正则匹配
if [[ "$str1" =~ ^[a-z]+$ ]]; then
    echo "str1 全部是小写字母"
fi

# 数值比较（使用 (( ))）
a=10
b=20
if (( a > b )); then
    echo "a > b"
elif (( a < b )); then
    echo "a < b"
else
    echo "a == b"
fi
```

### 3.2 if 语句

```bash
#!/bin/bash
# 基本 if
if [[ 条件 ]]; then
    # 条件成立时执行
fi

# if-else
if [[ 条件 ]]; then
    # 条件成立时执行
else
    # 条件不成立时执行
fi

# if-elif-else
if [[ 条件1 ]]; then
    # 条件1成立
elif [[ 条件2 ]]; then
    # 条件2成立
else
    # 所有条件都不成立
fi

# 示例
read -p "输入数字: " num
if (( num % 2 == 0 )); then
    echo "$num 是偶数"
else
    echo "$num 是奇数"
fi
```

### 3.3 case 语句

```bash
#!/bin/bash
# 语法
case $变量 in
    模式1)
        命令
        ;;
    模式2)
        命令
        ;;
    *)
        默认命令
        ;;
esac

# 示例
read -p "输入操作 (start|stop|restart): " action
case $action in
    start|Start|START)
        echo "启动服务..."
        ;;
    stop|Stop|STOP)
        echo "停止服务..."
        ;;
    restart|Restart|RESTART)
        echo "重启服务..."
        ;;
    *)
        echo "未知操作: $action"
        exit 1
        ;;
esac
```

---

## 4. 循环结构

### 4.1 for 循环

```bash
#!/bin/bash
# 遍历列表
for item in apple banana orange; do
    echo "水果: $item"
done

# 遍历数字范围
for i in {1..10}; do
    echo "数字: $i"
done

# 遍历数字范围（步长）
for i in {1..10..2}; do  # 1,3,5,7,9
    echo "奇数: $i"
done

# C 风格 for 循环
for ((i=0; i<10; i++)); do
    echo "i = $i"
done

# 遍历文件
for file in *.txt; do
    echo "处理文件: $file"
done

# 遍历命令输出
for user in $(cut -d: -f1 /etc/passwd | head -5); do
    echo "用户: $user"
done

# 遍历数组
arr=("a" "b" "c")
for item in "${arr[@]}"; do
    echo "数组元素: $item"
done
```

### 4.2 while 循环

```bash
#!/bin/bash
# 基本 while
count=1
while (( count <= 5 )); do
    echo "count = $count"
    ((count++))
done

# 读取文件逐行处理
while IFS= read -r line; do
    echo "行: $line"
done < /etc/passwd

# 无限循环
while true; do
    echo "按 Ctrl+C 退出"
    sleep 1
done

# 使用条件
while [[ -z "$input" ]]; do
    read -p "请输入（不能为空）: " input
done
echo "输入了: $input"
```

### 4.3 until 循环（条件为假时执行）

```bash
#!/bin/bash
# until 循环：条件为 false 时执行
count=1
until (( count > 5 )); do
    echo "count = $count"
    ((count++))
done
# 等价于 while (( count <= 5 ))
```

### 4.4 循环控制

| 关键字     | 说明                     | 示例                          |
| ---------- | ------------------------ | ----------------------------- |
| `break`    | 跳出整个循环             | `break`、`break 2`（跳出2层） |
| `continue` | 跳过当前迭代，进入下一次 | `continue`、`continue 2`      |
| `exit`     | 退出整个脚本             | `exit 1`（带退出码）          |
| `return`   | 从函数返回               | `return 0`（函数中）          |

```bash
#!/bin/bash
for i in {1..10}; do
    if (( i == 5 )); then
        break  # 跳出循环
    fi
    echo "i = $i"
done

for i in {1..5}; do
    if (( i == 3 )); then
        continue  # 跳过第3次
    fi
    echo "i = $i"
done
```

---

## 5. 函数

### 5.1 函数定义与调用

| 语法                        | 说明                           |
| --------------------------- | ------------------------------ |
| `function 函数名 { 命令; }` | 定义函数（带 function 关键字） |
| `函数名() { 命令; }`        | 定义函数（推荐，POSIX 兼容）   |
| `函数名 参数1 参数2`        | 调用函数并传递参数             |
| `return 退出码`             | 从函数返回（0-255）            |
| `local 变量名=值`           | 定义局部变量                   |

```bash
#!/bin/bash
# 定义函数（两种方式）
function say_hello {
    echo "Hello, $1!"
}

greet() {
    local name="$1"  # 局部变量
    echo "Welcome, $name!"
}

# 调用函数
say_hello "Alice"
greet "Bob"

# 函数返回值
add() {
    local sum=$(( $1 + $2 ))
    return $sum  # 返回 0-255
}
add 10 20
echo "返回值: $?"  # 30（但注意返回值范围限制）

# 函数中输出结果（捕获输出）
add2() {
    echo $(( $1 + $2 ))
}
result=$(add2 10 20)
echo "结果: $result"  # 30
```

### 5.2 函数中的特殊变量

| 变量        | 说明                           |
| ----------- | ------------------------------ |
| `$1` - `$9` | 函数参数（不同于脚本参数）     |
| `$#`        | 函数参数个数                   |
| `$@`        | 所有函数参数                   |
| `$*`        | 所有函数参数（作为一个字符串） |

```bash
#!/bin/bash
# 函数参数处理
show_args() {
    echo "参数个数: $#"
    echo "所有参数: $@"
    echo "第一个参数: $1"
    echo "第二个参数: $2"
}
show_args a b c d
```

---

## 6. 输入输出

### 6.1 输出

| 语法                 | 说明                       | 示例                                        |
| -------------------- | -------------------------- | ------------------------------------------- |
| `echo "文本"`        | 输出文本（自动换行）       | `echo "Hello"`                              |
| `echo -n "文本"`     | 输出文本（不换行）         | `echo -n "Prompt: "`                        |
| `echo -e "文本"`     | 启用转义字符（`\n`、`\t`） | `echo -e "Line1\nLine2"`                    |
| `printf "格式" 参数` | 格式化输出（类似 C 语言）  | `printf "Name: %s, Age: %d\n" "$name" $age` |

```bash
#!/bin/bash
# printf 示例
name="Alice"
age=25
printf "%-10s %5d\n" "$name" $age
# 输出: Alice         25
```

### 6.2 输入

| 语法                  | 说明                 | 示例                        |
| --------------------- | -------------------- | --------------------------- |
| `read 变量`           | 读取用户输入         | `read name`                 |
| `read -p "提示" 变量` | 带提示读取输入       | `read -p "输入名字: " name` |
| `read -s 变量`        | 静默读取（密码输入） | `read -s -p "密码: " pwd`   |
| `read -t 秒数 变量`   | 超时读取             | `read -t 5 name`            |
| `read -n 字符数 变量` | 读取指定字符数       | `read -n 1 key`             |
| `read -a 数组`        | 读取到数组           | `read -a arr`               |

```bash
#!/bin/bash
read -p "请输入姓名: " name
read -s -p "请输入密码: " password
echo
read -p "请输入多个值: " -a values
echo "姓名: $name"
echo "第一个值: ${values[0]}"
```

### 6.3 重定向与管道

| 语法             | 说明                               |
| ---------------- | ---------------------------------- |
| `命令 > 文件`    | 覆盖输出到文件                     |
| `命令 >> 文件`   | 追加输出到文件                     |
| `命令 2> 文件`   | 错误输出到文件                     |
| `命令 2>&1`      | 错误输出重定向到标准输出           |
| `命令 &> 文件`   | 所有输出重定向到文件               |
| `命令 < 文件`    | 从文件读取输入                     |
| `命令1 \| 命令2` | 管道（命令1的输出作为命令2的输入） |
| `tee 文件`       | 同时输出到屏幕和文件               |
| `<<EOF ... EOF`  | Here Document（多行输入）          |
| `<<< "字符串"`   | Here String（字符串作为输入）      |
| `命令1 <(命令2)` | 进程替换（命令2的输出作为临时文件）|

```bash
#!/bin/bash
# 重定向
ls > list.txt        # 覆盖写入
ls >> list.txt       # 追加写入
ls 2> error.log      # 错误输出
ls > output.log 2>&1 # 所有输出

# 管道
ps aux | grep nginx

# Here Document（多行文本）
cat <<EOF
这是多行文本
第二行
第三行
EOF

# Here String
grep "error" <<< "$log_content"

# tee 示例
echo "Hello" | tee -a log.txt  # 屏幕显示并追加到文件

# 进程替换：比较两个命令的输出（无需中间文件）
diff <(ls dir1) <(ls dir2)

# 进程替换：comm 要求输入已排序，可边排序边比较
comm <(sort a.txt) <(sort b.txt)
```

---

## 7. 错误处理

### 7.1 退出码

```bash
#!/bin/bash
# 检查命令执行结果（注意：$? 会被后续命令覆盖，必须先保存）
command_not_exists 2>/dev/null
rc=$?
if [[ $rc -eq 0 ]]; then
    echo "命令成功"
else
    echo "命令失败，退出码: $rc"
fi

# 脚本中主动退出
if [[ ! -f "/etc/passwd" ]]; then
    echo "错误: 文件不存在" >&2  # 输出到标准错误
    exit 1
fi
```

### 7.2 set 选项（脚本级错误处理）

| 选项                | 说明                         | 示例              |
| ------------------- | ---------------------------- | ----------------- |
| `set -e`            | 遇到错误立即退出             | `set -e`          |
| `set -u`            | 使用未定义变量时报错         | `set -u`          |
| `set -x`            | 调试模式，打印每条命令       | `set -x`          |
| `set -o pipefail`   | 管道中任何命令失败都返回失败 | `set -o pipefail` |
| `set +e` / `set +x` | 取消对应选项                 | `set +e`          |

```bash
#!/bin/bash
set -euo pipefail  # 常用组合：严格模式

# 命令失败会导致脚本退出
false
echo "这行不会执行"

# 允许命令失败（临时关闭 -e）
set +e
false
set -e
```

### 7.3 trap 信号捕获

```bash
#!/bin/bash
# 捕获信号
trap 'echo "脚本被中断"; exit 1' INT TERM  # Ctrl+C 时执行
trap 'echo "脚本退出时执行"' EXIT
trap 'echo "发生错误: 行号 $LINENO"' ERR

# 清理临时文件
cleanup() {
    rm -f /tmp/tempfile_$$
    echo "清理完成"
}
trap cleanup EXIT

# 创建临时文件
touch /tmp/tempfile_$$
echo "脚本执行中..."
sleep 10
```

---

## 8. 字符串操作

### 8.1 字符串截取与替换

| 语法                  | 说明                 | 示例              |
| --------------------- | -------------------- | ----------------- |
| `${#字符串}`          | 获取字符串长度       | `${#str}`         |
| `${字符串:开始}`      | 从开始位置截取到末尾 | `${str:2}`        |
| `${字符串:开始:长度}` | 截取指定长度         | `${str:2:3}`      |
| `${字符串#模式}`      | 删除最短前缀匹配     | `${str#*.}`       |
| `${字符串##模式}`     | 删除最长前缀匹配     | `${str##*/}`      |
| `${字符串%模式}`      | 删除最短后缀匹配     | `${str%.*}`       |
| `${字符串%%模式}`     | 删除最长后缀匹配     | `${str%%.*}`      |
| `${字符串/旧/新}`     | 替换第一个匹配       | `${str/foo/bar}`  |
| `${字符串//旧/新}`    | 替换所有匹配         | `${str//foo/bar}` |
| `${字符串/#旧/新}`    | 替换开头匹配         | `${str/#foo/bar}` |
| `${字符串/%旧/新}`    | 替换结尾匹配         | `${str/%foo/bar}` |
| `${字符串,,}`         | 转为小写             | `${str,,}`        |
| `${字符串^^}`         | 转为大写             | `${str^^}`        |

```bash
#!/bin/bash
str="hello-world-foo-bar"

# 长度
echo "长度: ${#str}"  # 19

# 截取
echo "从第6位: ${str:6}"      # "world-foo-bar"
echo "从第6位取5个: ${str:6:5}" # "world"

# 删除前缀（## 最长匹配）
file="/path/to/file.txt"
echo "文件名: ${file##*/}"  # "file.txt"
echo "路径: ${file%/*}"     # "/path/to"
echo "扩展名: ${file##*.}"  # "txt"
echo "不含扩展名: ${file%.*}" # "/path/to/file"

# 替换
str2="foo bar foo"
echo "${str2/foo/baz}"     # "baz bar foo"
echo "${str2//foo/baz}"    # "baz bar baz"

# 大小写转换
name="Hello World"
echo "${name,,}"  # "hello world"
echo "${name^^}"  # "HELLO WORLD"
```

### 8.2 默认值与空值处理（参数展开）

| 语法              | 说明                                       | 示例                                    |
| ----------------- | ------------------------------------------ | --------------------------------------- |
| `${var:-默认值}`  | var 为空或未定义时返回默认值（不修改 var） | `echo ${name:-"guest"}`                 |
| `${var-默认值}`   | var 未定义时返回默认值（var 为空串不生效） | `echo ${name-"guest"}`                  |
| `${var:=默认值}`  | 为空或未定义时，赋值并返回默认值           | `: ${COUNT:=10}`                        |
| `${var:+替代值}`  | var 非空时返回替代值（否则返回空）         | `echo ${debug:+"调试模式"}`             |
| `${var:?错误信息}`| 为空或未定义时报错并退出脚本               | `: ${INPUT:?"必须提供 INPUT 参数"}`     |

```bash
#!/bin/bash
# 常见用法：为可能未传的变量提供默认值
timeout=${TIMEOUT:-30}
echo "超时时间: ${timeout}s"

# 调试开关
debug=""
[[ -n ${debug:+x} ]] && echo "debug 已开启"

# 必填参数检查（未定义直接报错退出）
: "${API_KEY:?请先设置 API_KEY 环境变量}"
```

---

## 9. 算术运算

```bash
#!/bin/bash
# 方式1: $(( ... ))（推荐）
a=10
b=20
sum=$((a + b))
diff=$((a - b))
prod=$((a * b))
div=$((b / a))
mod=$((b % a))
echo "sum=$sum, diff=$diff, prod=$prod, div=$div, mod=$mod"

# 方式2: let 命令
let "sum = a + b"
let "a++"

# 方式3: expr（旧方式）
sum=$(expr $a + $b)

# 位运算
and=$((a & b))
or=$((a | b))
xor=$((a ^ b))
shift=$((a << 2))

# 逻辑运算
if (( a > 5 && b < 30 )); then
    echo "条件成立"
fi

# 自增自减
((a++))
((b--))
((a += 5))
```

---

## 10. 常用内置命令

| 命令           | 说明                   | 示例                          |
| -------------- | ---------------------- | ----------------------------- |
| `echo`         | 输出文本               | `echo "Hello"`                |
| `printf`       | 格式化输出             | `printf "Name: %s\n" "$name"` |
| `read`         | 读取输入               | `read -p "输入: " var`        |
| `test` / `[ ]` | 条件测试               | `[ -f file ]`                 |
| `[[ ]]`        | 增强条件测试           | `[[ "$str" == "hello" ]]`     |
| `(( ))`        | 算术运算               | `(( a = 10 + 20 ))`           |
| `let`          | 算术运算               | `let "a = 10 + 20"`           |
| `export`       | 导出环境变量           | `export PATH`                 |
| `source` / `.` | 执行脚本（当前 shell） | `source env.sh`               |
| `exec`         | 替换当前进程           | `exec bash`                   |
| `shift`        | 左移位置参数           | `shift 2`（去掉前2个参数）    |
| `getopts`      | 解析命令行选项         | `while getopts "ab:c:" opt`   |
| `trap`         | 信号捕获               | `trap 'cleanup' EXIT`         |
| `wait`         | 等待后台进程完成       | `wait $pid`                   |
| `sleep`        | 暂停指定秒数           | `sleep 5`                     |
| `type`         | 显示命令类型           | `type ls`                     |

---

## 11. 命令行参数解析

### 11.1 使用 getopts（推荐）

```bash
#!/bin/bash
# getopts 示例
usage() {
    echo "用法: $0 [-h] [-v] [-f 文件] [-n 数字]"
    echo "  -h       显示帮助"
    echo "  -v       详细模式"
    echo "  -f 文件  指定配置文件"
    echo "  -n 数字  指定数量"
    exit 0
}

verbose=0
config_file=""
count=5

while getopts "hvf:n:" opt; do
    case $opt in
        h)
            usage
            ;;
        v)
            verbose=1
            ;;
        f)
            config_file="$OPTARG"
            ;;
        n)
            count="$OPTARG"
            ;;
        \?)
            echo "无效选项: -$OPTARG" >&2
            exit 1
            ;;
    esac
done

shift $((OPTIND - 1))  # 移除已解析的选项

echo "verbose: $verbose"
echo "config_file: $config_file"
echo "count: $count"
echo "剩余参数: $@"
```

### 11.2 手动解析（简单场景）

```bash
#!/bin/bash
# 手动解析
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            usage
            shift
            ;;
        -f|--file)
            file="$2"
            shift 2
            ;;
        -v|--verbose)
            verbose=1
            shift
            ;;
        *)
            echo "未知参数: $1"
            exit 1
            ;;
    esac
done
```

---

## 12. 实用脚本模板

### 12.1 通用脚本模板

```bash
#!/bin/bash
# ==================================================
# 脚本名称: ${0##*/}
# 功能描述: 脚本功能的简要描述
# 作者: xxx
# 版本: 1.0
# 创建日期: $(date +%Y-%m-%d)
# ==================================================

set -euo pipefail  # 严格模式

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'  # No Color

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

# 脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 使用说明
usage() {
    cat <<EOF
用法: $0 [选项] [参数]

选项:
    -h, --help      显示此帮助信息
    -f, --file FILE 指定文件路径
    -v, --verbose   输出详细信息
    -n, --number N  指定数字 (默认: 10)

示例:
    $0 -f /path/to/file -n 20 -v
EOF
    exit 0
}

# 参数解析
file=""
verbose=0
number=10

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            usage
            ;;
        -f|--file)
            file="$2"
            shift 2
            ;;
        -v|--verbose)
            verbose=1
            shift
            ;;
        -n|--number)
            number="$2"
            shift 2
            ;;
        *)
            log_error "未知参数: $1"
            usage
            ;;
    esac
done

# 主函数
main() {
    log_info "脚本开始执行"
    log_info "脚本目录: $SCRIPT_DIR"

    if [[ -n "$file" ]]; then
        log_info "文件: $file"
        if [[ ! -f "$file" ]]; then
            log_error "文件不存在: $file"
            exit 1
        fi
    fi

    if (( verbose )); then
        log_info "详细模式已启用"
    fi

    log_info "数字: $number"

    # 执行实际逻辑...

    log_info "脚本执行完成"
}

# 执行主函数
main "$@"
```

### 12.2 安全脚本模板（带错误处理）

```bash
#!/bin/bash
set -euo pipefail

# 错误处理函数
error_exit() {
    echo "错误: $1" >&2
    exit "${2:-1}"
}

# 检查命令是否存在
check_command() {
    if ! command -v "$1" &>/dev/null; then
        error_exit "命令 '$1' 未找到，请安装后重试"
    fi
}

# 检查必要命令
check_command "curl"
check_command "jq"

# 使用 trap 清理
cleanup() {
    if [[ -n "${tmp_file:-}" && -f "$tmp_file" ]]; then
        rm -f "$tmp_file"
    fi
    echo "清理完成"
}
trap cleanup EXIT

# 创建临时文件
tmp_file=$(mktemp)
echo "临时文件: $tmp_file"

# 执行操作
echo "执行关键操作..."
# ... 实际操作 ...
```

---

## 13. 常用 Shell 脚本模式

### 13.1 并发执行

```bash
#!/bin/bash
# 后台并行执行
for url in "http://example.com" "http://google.com" "http://github.com"; do
    {
        curl -s -o /dev/null -w "%{http_code} %{url_effective}\n" "$url"
    } &
done
wait  # 等待所有后台进程完成

# 使用 xargs 并行
echo "file1 file2 file3" | xargs -n 1 -P 4 gzip
```

### 13.2 进度条

```bash
#!/bin/bash
show_progress() {
    local total=$1
    local current=$2
    local percent=$((current * 100 / total))
    local bar_len=50
    local filled=$((percent * bar_len / 100))
    local empty=$((bar_len - filled))
    local bar
    local space
    printf -v bar '%*s' "$filled" ''      # 生成 filled 个空格
    printf -v space '%*s' "$empty" ''     # 生成 empty 个空格
    printf "\r[%s%s] %3d%%" "${bar// /#}" "$space" "$percent"
}

# 使用示例
total=100
for i in $(seq 1 $total); do
    show_progress $total $i
    sleep 0.1
done
echo
```

### 13.3 配置文件读取

```bash
#!/bin/bash
# 读取 .env 或 .conf 文件
load_config() {
    local config_file="$1"
    if [[ -f "$config_file" ]]; then
        # 使用 source（注意：文件须是合法 shell 语法）
        source "$config_file"
        # 或手动解析
        # while IFS='=' read -r key value; do
        #     [[ -z "$key" ]] || [[ "$key" == \#* ]] && continue
        #     export "$key"="$value"
        # done < "$config_file"
    else
        echo "配置文件不存在: $config_file"
        exit 1
    fi
}
```

---

## 14. 快速参考卡片

| 分类       | 常用语法                             |
| ---------- | ------------------------------------ |
| 变量定义   | `name="value"`                       |
| 变量引用   | `$name` 或 `${name}`                 |
| 命令替换   | `$(command)` 或 `` `command` ``      |
| 算术运算   | `$((a + b))`                         |
| 条件判断   | `[[ 条件 ]]`、`(( a > b ))`          |
| if 语句    | `if [[ 条件 ]]; then ... fi`         |
| for 循环   | `for i in {1..10}; do ... done`      |
| while 循环 | `while [[ 条件 ]]; do ... done`      |
| 函数定义   | `func() { ... }`                     |
| 函数调用   | `func arg1 arg2`                     |
| 退出码     | `$?`                                 |
| 错误退出   | `exit 1`                             |
| 严格模式   | `set -euo pipefail`                  |
| 调试模式   | `set -x`                             |
| 读取输入   | `read -p "提示" var`                 |
| 字符串长度 | `${#str}`                            |
| 子串截取   | `${str:2:3}`                         |
| 删除前缀   | `${str#pattern}`、`${str##pattern}`  |
| 删除后缀   | `${str%pattern}`、`${str%%pattern}`  |
| 替换       | `${str/old/new}`、`${str//old/new}`  |
| 大小写转换 | `${str,,}`、`${str^^}`               |
| 默认值     | `${var:-default}`、`${var:=default}` |
| 参数个数   | `$#`                                 |
| 所有参数   | `$@`、`$*`                           |

---

## 15. 常见错误与调试

### 15.1 常见错误

| 错误                      | 原因                 | 解决方案                                 |
| ------------------------- | -------------------- | ---------------------------------------- |
| `command not found`       | 命令不存在或路径不对 | 检查命令名或使用绝对路径                 |
| `bad substitution`        | 变量语法错误         | 检查 `${}` 是否正确                      |
| `[: too many arguments`   | `[ ]` 中未加引号     | 使用 `[[ ]]` 或加引号 `[ "$var" = "x" ]` |
| `unary operator expected` | 变量为空导致         | 使用 `[[ ]]` 或加引号                    |
| `Permission denied`       | 脚本没有执行权限     | `chmod +x script.sh`                     |

### 15.2 调试技巧

```bash
#!/bin/bash
# 1. 使用 -x 调试模式
bash -x script.sh

# 2. 在脚本中设置
set -x
# ... 调试代码 ...
set +x

# 3. 打印调试信息
echo "DEBUG: 变量值 = $var"

# 4. 使用 trap 跟踪函数调用
trap 'echo "执行: $BASH_COMMAND"' DEBUG

# 5. 检查语法错误（不执行）
bash -n script.sh
```

---

上一篇：《03-Git版本控制.md》　｜　模块索引：《../README.md》
