# Git 版本控制

> 本节目标：系统讲解 Git 分布式版本控制系统的核心命令与工作流，包括配置、基础操作、分支管理、远程仓库、历史查看、撤销恢复、标签、子模块与高级操作，学完后能够熟练使用 Git 进行代码版本管理与团队协作。

## 本章速览

- [1. 概述](#1-概述)
- [2. 配置命令](#2-配置命令)
  - [2.1 用户配置](#21-用户配置)
  - [2.2 仓库级别配置](#22-仓库级别配置)
- [3. 基础操作](#3-基础操作)
  - [3.1 文件状态与工作流](#31-文件状态与工作流)
  - [3.2 文件生命周期](#32-文件生命周期)
- [4. 分支管理](#4-分支管理)
  - [4.1 分支基本操作](#41-分支基本操作)
  - [4.2 Merge vs Rebase](#42-merge-vs-rebase)
- [5. 远程仓库操作](#5-远程仓库操作)
  - [5.1 远程仓库基本操作](#51-远程仓库基本操作)
  - [5.2 多远程仓库](#52-多远程仓库)
- [6. 查看历史](#6-查看历史)
- [7. 撤销与恢复](#7-撤销与恢复)
  - [7.1 reset 三种模式对比](#71-reset-三种模式对比)
- [8. 标签管理](#8-标签管理)
- [9. 子模块](#9-子模块)
- [10. .gitignore 配置](#10-gitignore-配置)
- [11. 高级操作](#11-高级操作)
  - [11.1 交互式变基（整理提交历史）](#111-交互式变基整理提交历史)
  - [11.2 Bisect（二分查找 Bug）](#112-bisect二分查找-bug)
  - [11.3 Git Hooks（钩子脚本）](#113-git-hooks钩子脚本)
  - [11.4 Reflog（恢复丢失的提交）](#114-reflog恢复丢失的提交)
  - [11.5 Git Worktree（多分支同时工作）](#115-git-worktree多分支同时工作)
- [12. 常用工作流](#12-常用工作流)
  - [12.1 功能分支工作流](#121-功能分支工作流)
  - [12.2 修复紧急 Bug 工作流](#122-修复紧急-bug-工作流)
- [13. 快速参考卡片](#13-快速参考卡片)
  - [13.1 按场景速查](#131-按场景速查)
  - [13.2 命令简写速查](#132-命令简写速查)
- [14. 常见问题与解决方案](#14-常见问题与解决方案)

---

## 1. 概述

Git 是目前最流行的分布式版本控制系统，用于跟踪代码变更、协作开发和版本管理。

**基本调用格式：**

```bash
git [命令] [选项] [参数]
```

**常用启动/初始化方式：**

```bash
git init                              # 初始化本地仓库
git clone <仓库地址> [目录名]           # 克隆远程仓库
git clone -b <分支名> <仓库地址>        # 克隆指定分支
```

---

## 2. 配置命令

### 2.1 用户配置

| 命令                                     | 说明             | 示例                                                    |
| ---------------------------------------- | ---------------- | ------------------------------------------------------- |
| `git config --global user.name`          | 设置全局用户名   | `git config --global user.name "张三"`                  |
| `git config --global user.email`         | 设置全局用户邮箱 | `git config --global user.email "zhangsan@example.com"` |
| `git config --global core.editor`        | 设置默认编辑器   | `git config --global core.editor vim`                   |
| `git config --global init.defaultBranch` | 设置默认分支名   | `git config --global init.defaultBranch main`           |
| `git config --list`                      | 查看所有配置     | `git config --list`                                     |
| `git config <配置项>`                    | 查看指定配置     | `git config user.name`                                  |

```bash
# 设置用户名和邮箱（必须）
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"

# 设置别名（提高效率）
git config --global alias.st status
git config --global alias.co checkout
git config --global alias.br branch
git config --global alias.cm commit
git config --global alias.lg "log --oneline --graph --all"

# 设置换行符处理（跨平台协作）
git config --global core.autocrlf input  # Mac/Linux
git config --global core.autocrlf true   # Windows

# 查看所有配置
git config --list
```

### 2.2 仓库级别配置

| 命令                  | 说明                   | 示例                                          |
| --------------------- | ---------------------- | --------------------------------------------- |
| `git config --local`  | 当前仓库配置           | `git config --local user.name "Project User"` |
| `git config --system` | 系统级配置（所有用户） | `git config --system core.autocrlf false`     |
| `git config --global` | 用户级配置（当前用户） | `git config --global core.editor vim`         |

**配置优先级：** `local` > `global` > `system`

---

## 3. 基础操作

### 3.1 文件状态与工作流

| 命令                           | 说明                                    | 示例                                                  |
| ------------------------------ | --------------------------------------- | ----------------------------------------------------- |
| `git status`                   | 查看当前状态                            | `git status`（简写：`git st`）                        |
| `git status -s`                | 查看简洁状态                            | `git status -s`                                       |
| `git add <文件>`               | 将文件添加到暂存区                      | `git add main.c`                                      |
| `git add .`                    | 添加所有变更到暂存区                    | `git add .`                                           |
| `git add -A`                   | 添加所有变更（含删除）                  | `git add -A`                                          |
| `git add -p`                   | 交互式选择添加                          | `git add -p`                                          |
| `git commit -m "消息"`         | 提交暂存区变更                          | `git commit -m "feat: add login"`                     |
| `git commit -a -m "消息"`      | 跳过暂存区，直接提交所有变更            | `git commit -a -m "fix bug"`                          |
| `git commit --amend`           | 修改最近一次提交（消息或内容）          | `git commit --amend -m "new message"`                 |
| `git commit --amend --no-edit` | 修改最近一次提交（仅修改内容）          | `git add forgotten.c && git commit --amend --no-edit` |
| `git reset -- <文件>`          | 从暂存区移除文件                        | `git reset -- main.c`                                 |
| `git reset HEAD <文件>`        | 将文件从暂存区移除（同 `git reset --`） | `git reset HEAD main.c`                               |
| `git restore --staged <文件>`  | 从暂存区移除文件（新语法）              | `git restore --staged main.c`                         |
| `git restore <文件>`           | 丢弃工作区的修改（慎用）                | `git restore main.c`                                  |
| `git checkout -- <文件>`       | 丢弃工作区的修改（旧语法）              | `git checkout -- main.c`                              |

```bash
# 工作流示例
echo "# My Project" > README.md
git status                      # 查看状态（红色：未跟踪）
git add README.md               # 添加到暂存区
git status                      # 绿色：已暂存
git commit -m "docs: add README" # 提交
git log --oneline               # 查看提交历史
```

### 3.2 文件生命周期

```bash
工作区 (Working)  -->  暂存区 (Staging)  -->  本地仓库 (Local)
        |                       |                     |
   git add              git commit               git push
   git restore           git reset               git pull
   (丢弃修改)            (撤销暂存)
```

---

## 4. 分支管理

### 4.1 分支基本操作

| 命令                                  | 说明                               | 示例                              |
| ------------------------------------- | ---------------------------------- | --------------------------------- |
| `git branch`                          | 列出所有本地分支（当前分支带 `*`） | `git branch`                      |
| `git branch -r`                       | 列出远程分支                       | `git branch -r`                   |
| `git branch -a`                       | 列出所有分支（含远程）             | `git branch -a`                   |
| `git branch <分支名>`                 | 创建分支                           | `git branch feature-login`        |
| `git branch -d <分支名>`              | 删除分支（已合并）                 | `git branch -d feature-login`     |
| `git branch -D <分支名>`              | 强制删除分支（未合并）             | `git branch -D feature-login`     |
| `git branch -m <新分支名>`            | 重命名当前分支                     | `git branch -m new-name`          |
| `git branch -M <新分支名>`            | 强制重命名（覆盖同名分支）         | `git branch -M new-name`          |
| `git branch -vv`                      | 查看本地分支与远程分支的关联       | `git branch -vv`                  |
| `git checkout <分支名>`               | 切换到指定分支                     | `git checkout develop`            |
| `git switch <分支名>`                 | 切换到指定分支（新语法，推荐）     | `git switch develop`              |
| `git checkout -b <分支名>`            | 创建并切换到新分支                 | `git checkout -b feature-login`   |
| `git switch -c <分支名>`              | 创建并切换到新分支（新语法）       | `git switch -c feature-login`     |
| `git merge <分支名>`                  | 将指定分支合并到当前分支           | `git merge feature-login`         |
| `git merge --no-ff <分支名>`          | 合并时强制创建提交节点             | `git merge --no-ff feature-login` |
| `git merge --abort`                   | 取消合并（冲突时）                 | `git merge --abort`               |
| `git rebase <分支名>`                 | 将当前分支变基到指定分支           | `git rebase main`                 |
| `git rebase -i HEAD~N`                | 交互式变基（合并/修改 N 个提交）   | `git rebase -i HEAD~3`            |
| `git rebase --continue`               | 继续变基（解决冲突后）             | `git rebase --continue`           |
| `git rebase --abort`                  | 取消变基                           | `git rebase --abort`              |
| `git cherry-pick <commit>`            | 将指定提交应用到当前分支           | `git cherry-pick abc123`          |
| `git cherry-pick <commit1> <commit2>` | 应用多个提交                       | `git cherry-pick abc123 def456`   |

```bash
# 分支操作示例
git branch feature-login          # 创建分支
git checkout feature-login        # 切换到新分支
# ... 开发 ...
git add . && git commit -m "login feature"
git checkout main                 # 切回主分支
git merge feature-login           # 合并功能分支
git branch -d feature-login       # 删除已合并的分支

# 交互式变基（合并最近3个提交）
git rebase -i HEAD~3
# 在编辑器中：将 pick 改为 squash 或 fixup
```

### 4.2 Merge vs Rebase

| 操作         | 特点                       | 适用场景                     |
| ------------ | -------------------------- | ---------------------------- |
| `git merge`  | 保留完整历史，产生合并提交 | 公共分支、团队协作           |
| `git rebase` | 线性历史，无合并提交       | 本地分支、准备提交前整理历史 |

```bash
# Merge（保留历史）
git checkout main
git merge feature/login
# 结果：产生一个合并提交

# Rebase（线性历史）
git checkout feature/login
git rebase main
# 结果：将 feature/login 的提交移到 main 的最新提交之后
```

---

## 5. 远程仓库操作

### 5.1 远程仓库基本操作

| 命令                                 | 说明                     | 示例                                                         |
| ------------------------------------ | ------------------------ | ------------------------------------------------------------ |
| `git remote -v`                      | 查看远程仓库地址         | `git remote -v`                                              |
| `git remote add <名称> <地址>`       | 添加远程仓库             | `git remote add origin git@github.com:user/repo.git`         |
| `git remote set-url <名称> <新地址>` | 修改远程仓库地址         | `git remote set-url origin https://github.com/user/repo.git` |
| `git remote remove <名称>`           | 删除远程仓库             | `git remote remove origin`                                   |
| `git remote show <名称>`             | 查看远程仓库详细信息     | `git remote show origin`                                     |
| `git push <远程名> <分支名>`         | 推送到远程仓库           | `git push origin main`                                       |
| `git push -u <远程名> <分支名>`      | 推送并设置上游（关联）   | `git push -u origin main`                                    |
| `git push --force`                   | 强制推送（慎用）         | `git push --force origin main`                               |
| `git push --force-with-lease`        | 安全强制推送（推荐）     | `git push --force-with-lease origin main`                    |
| `git push --all`                     | 推送所有分支             | `git push --all origin`                                      |
| `git push --tags`                    | 推送所有标签             | `git push --tags`                                            |
| `git pull <远程名> <分支名>`         | 拉取并合并远程分支       | `git pull origin main`                                       |
| `git pull --rebase`                  | 拉取并使用 rebase 合并   | `git pull --rebase origin main`                              |
| `git fetch <远程名>`                 | 获取远程更新（不合并）   | `git fetch origin`                                           |
| `git fetch --all`                    | 获取所有远程更新         | `git fetch --all`                                            |
| `git clone <地址>`                   | 克隆远程仓库             | `git clone https://github.com/user/repo.git`                 |
| `git clone -b <分支> <地址>`         | 克隆指定分支             | `git clone -b develop https://github.com/user/repo.git`      |
| `git clone --depth 1 <地址>`         | 浅克隆（只克隆最新提交） | `git clone --depth 1 https://github.com/user/repo.git`       |

```bash
# 推送代码到远程仓库
git push -u origin main           # 首次推送并设置上游
git push                          # 后续直接使用（已关联）
git push origin feature-login     # 推送功能分支

# 拉取最新代码
git pull                          # 默认拉取当前分支
git pull --rebase                 # 使用 rebase 方式拉取（推荐）

# 获取远程更新但不合并
git fetch origin                  # 获取远程所有分支更新
git log origin/main..HEAD         # 查看本地领先于远程的提交（尚未推送）
git log HEAD..origin/main         # 查看远程领先于本地的提交（尚未拉取）
```

### 5.2 多远程仓库

```bash
# 添加多个远程（如 GitHub + Gitee）
git remote add github https://github.com/user/repo.git
git remote add gitee https://gitee.com/user/repo.git

# 分别推送
git push github main
git push gitee main

# 同时推送到所有远程（别名）
git remote add all https://github.com/user/repo.git
git remote set-url --add all https://gitee.com/user/repo.git
git push all main
```

---

## 6. 查看历史

| 命令                           | 说明                               | 示例                              |
| ------------------------------ | ---------------------------------- | --------------------------------- |
| `git log`                      | 查看提交历史                       | `git log`                         |
| `git log --oneline`            | 查看简洁提交历史（一行一个提交）   | `git log --oneline`               |
| `git log --graph`              | 查看图形化分支历史                 | `git log --graph --oneline --all` |
| `git log -p`                   | 查看提交历史及变更内容             | `git log -p`                      |
| `git log -N`                   | 查看最近 N 次提交                  | `git log -5`                      |
| `git log --author="张三"`      | 按作者筛选                         | `git log --author="张三"`         |
| `git log --since="2026-01-01"` | 按时间筛选                         | `git log --since="2026-01-01"`    |
| `git log --grep="关键字"`      | 按提交消息关键字筛选               | `git log --grep="fix"`            |
| `git log -S"字符串"`           | 按代码变更内容筛选                 | `git log -S"function_name"`       |
| `git log <分支1>..<分支2>`     | 查看分支2有而分支1没有的提交       | `git log main..feature`（feature 领先 main 的提交） |
| `git show <commit>`            | 查看指定提交的详细变更             | `git show abc123`                 |
| `git show HEAD~1`              | 查看上一个提交的变更               | `git show HEAD~1`                 |
| `git diff`                     | 查看工作区与暂存区的差异           | `git diff`                        |
| `git diff --staged`            | 查看暂存区与上次提交的差异         | `git diff --staged`               |
| `git diff <分支1> <分支2>`     | 查看两个分支的差异                 | `git diff main develop`           |
| `git diff <commit1> <commit2>` | 查看两个提交的差异                 | `git diff abc123 def456`          |
| `git blame <文件>`             | 查看文件每一行的最后修改信息       | `git blame main.c`                |
| `git reflog`                   | 查看所有操作记录（恢复丢失的提交） | `git reflog`                      |

```bash
# 查看历史示例
git log --oneline --graph --all --decorate
# 效果：显示完整的分支图和提交摘要

# 查看最近3次提交的详细变更
git log -3 -p

# 查看文件每一行的修改人
git blame main.c | head -20

# 恢复误删的提交（通过 reflog）
git reflog
git reset --hard HEAD@{5}  # 恢复到第5条记录
```

---

## 7. 撤销与恢复

| 命令                          | 说明                                     | 示例                          |
| ----------------------------- | ---------------------------------------- | ----------------------------- |
| `git reset --soft <commit>`   | 撤销提交，保留工作区和暂存区             | `git reset --soft HEAD~1`     |
| `git reset --mixed <commit>`  | 撤销提交，保留工作区，重置暂存区（默认） | `git reset HEAD~1`            |
| `git reset --hard <commit>`   | 撤销提交，丢弃所有更改（慎用）           | `git reset --hard HEAD~1`     |
| `git reset HEAD <文件>`       | 从暂存区移除文件                         | `git reset HEAD main.c`       |
| `git restore --staged <文件>` | 从暂存区移除文件（新语法）               | `git restore --staged main.c` |
| `git restore <文件>`          | 丢弃工作区修改（新语法）                 | `git restore main.c`          |
| `git checkout -- <文件>`      | 丢弃工作区修改（旧语法）                 | `git checkout -- main.c`      |
| `git revert <commit>`         | 创建一个新提交来撤销指定提交             | `git revert abc123`           |
| `git stash`                   | 暂存当前未提交的修改                     | `git stash`                   |
| `git stash push -m "描述"`      | 暂存并添加描述（推荐语法）        | `git stash push -m "WIP: login"` |
| `git stash save "描述"`         | 同上（旧语法，Git 2.16 起已废弃） | `git stash save "WIP: login"`    |
| `git stash pop`               | 恢复最近一次暂存并删除记录               | `git stash pop`               |
| `git stash apply`             | 恢复最近一次暂存（保留记录）             | `git stash apply`             |
| `git stash list`              | 列出所有暂存记录                         | `git stash list`              |
| `git stash drop`              | 删除最近一次暂存记录                     | `git stash drop`              |
| `git stash clear`             | 清空所有暂存记录                         | `git stash clear`             |

```bash
# 撤销最近一次提交（保留修改）
git reset --soft HEAD~1
# 修改文件后重新提交
git commit -m "修正后的提交"

# 撤销并丢弃修改（慎用）
git reset --hard HEAD~1

# 安全撤销：创建一个反向提交
git revert abc123  # 会产生一个新的提交

# 临时切换分支时暂存修改
git stash push -m "WIP: unfinished work"
git checkout other-branch
# ... 完成其他工作 ...
git switch -
git stash pop  # 恢复之前的修改
```

### 7.1 reset 三种模式对比

| 模式              | HEAD 位置 | 暂存区 | 工作区 | 使用场景                     |
| ----------------- | --------- | ------ | ------ | ---------------------------- |
| `--soft`          | ✅ 移动    | ✅ 保留 | ✅ 保留 | 修改提交信息/重新组织提交    |
| `--mixed`（默认） | ✅ 移动    | ❌ 重置 | ✅ 保留 | 将文件从暂存区移出，重新 add |
| `--hard`          | ✅ 移动    | ❌ 重置 | ❌ 丢弃 | 丢弃所有修改（慎用）         |

---

## 8. 标签管理

| 命令                                  | 说明                        | 示例                                   |
| ------------------------------------- | --------------------------- | -------------------------------------- |
| `git tag`                             | 列出所有标签                | `git tag`                              |
| `git tag -l "v*"`                     | 按模式匹配列出标签          | `git tag -l "v*"`                      |
| `git tag <标签名>`                    | 创建轻量标签                | `git tag v1.0.0`                       |
| `git tag -a <标签名> -m "描述"`       | 创建附注标签（推荐）        | `git tag -a v1.0.0 -m "Release 1.0.0"` |
| `git show <标签名>`                   | 查看标签详细信息            | `git show v1.0.0`                      |
| `git push <远程名> <标签名>`          | 推送标签到远程              | `git push origin v1.0.0`               |
| `git push --tags`                     | 推送所有标签到远程          | `git push --tags`                      |
| `git tag -d <标签名>`                 | 删除本地标签                | `git tag -d v1.0.0`                    |
| `git push <远程名> --delete <标签名>` | 删除远程标签                | `git push origin --delete v1.0.0`      |
| `git checkout <标签名>`               | 切换到标签（detached HEAD） | `git checkout v1.0.0`                  |

```bash
# 创建版本标签
git tag -a v2.0.0 -m "正式发布 v2.0.0"
git push origin v2.0.0

# 在 CI/CD 中自动打标签
git tag -a v1.0.${BUILD_NUMBER} -m "Build ${BUILD_NUMBER}"
git push --tags
```

---

## 9. 子模块

| 命令                             | 说明                     | 示例                                                         |
| -------------------------------- | ------------------------ | ------------------------------------------------------------ |
| `git submodule add <URL> [路径]` | 添加子模块               | `git submodule add https://github.com/lib/lib.git external/lib` |
| `git submodule init`             | 初始化子模块配置         | `git submodule init`                                         |
| `git submodule update`           | 拉取子模块代码           | `git submodule update --init --recursive`                    |
| `git clone --recursive <URL>`    | 克隆主仓库并初始化子模块 | `git clone --recursive https://github.com/user/repo.git`     |
| `git submodule foreach <命令>`   | 对每个子模块执行命令     | `git submodule foreach git pull origin main`                 |
| `git submodule sync`             | 同步子模块 URL 配置      | `git submodule sync`                                         |

```bash
# 首次克隆主仓库并包含子模块
git clone --recursive https://github.com/user/repo.git

# 已有仓库，初始化子模块
git submodule update --init --recursive

# 更新所有子模块到远程分支最新（推荐）
git submodule update --remote --recursive
# 注意：子模块默认处于 detached HEAD 状态，直接 git pull 会报错
# （"You are not currently on a branch"），应使用上面的 update --remote

# 若确实要在子模块内用 git pull，需先切到分支
git submodule foreach 'git checkout main && git pull origin main'
```

---

## 10. .gitignore 配置

```text
# .gitignore 示例

# 编译产物
*.o
*.exe
*.dll
*.so
*.a
*.out
*.class

# 构建目录
/build/
/dist/
/target/
/bin/
/obj/
/build*/

# IDE 配置文件
.idea/
.vscode/
*.swp
*.swo
*~
.DS_Store

# 依赖管理
node_modules/
vendor/
# 注意：应用程序项目通常【应提交】lock 文件以保证构建可重现，
# 仅库（library）项目才常忽略它们。按需取消下行注释
# *.lock
# package-lock.json
# yarn.lock

# 日志文件
*.log
*.tmp
*.temp

# 环境配置文件（含敏感信息）
.env
.env.*
!.env.example
*.pem
*.key
*.crt

# 特定语言
# Python
__pycache__/
*.pyc
*.pyo

# C/C++
*.d
*.dep
*.gcda
*.gcno
*.gcov
```

| 命令                      | 说明                 | 示例                         |
| ------------------------- | -------------------- | ---------------------------- |
| `git check-ignore <文件>` | 检查文件是否被忽略   | `git check-ignore -v main.o` |
| `git add -f <文件>`       | 强制添加被忽略的文件 | `git add -f ignored_file`    |
| `git status --ignored`    | 显示被忽略的文件     | `git status --ignored`       |

```bash
# 常用 .gitignore 操作
# 查看哪些文件被忽略
git status --ignored

# 强制添加被忽略的文件
git add -f config/local.env

# 查看具体哪个规则忽略了文件
git check-ignore -v build/main.o
```

---

## 11. 高级操作

### 11.1 交互式变基（整理提交历史）

```bash
# 交互式变基最近3次提交
git rebase -i HEAD~3

# 常用操作指令（在编辑器中使用）
# pick   = 保留提交
# reword = 修改提交消息
# edit   = 修改提交内容
# squash = 合并到上一个提交（保留提交消息）
# fixup  = 合并到上一个提交（丢弃提交消息）
# drop   = 删除提交

# 示例：合并多个提交
# 将第二个和第三个提交改为 squash
pick 123456 第一次提交
squash 789012 第二次提交（合并到上面）
squash 345678 第三次提交（合并到上面）

# 保存后，编辑合并后的提交消息
```

### 11.2 Bisect（二分查找 Bug）

```bash
# 使用二分查找定位引入 bug 的提交
git bisect start
git bisect bad HEAD          # 当前版本有 bug
git bisect good v1.0.0       # v1.0.0 版本正常
# Git 自动切换到中间提交，测试后标记
git bisect good              # 当前版本正常
git bisect bad               # 当前版本有 bug
# 重复直到找到有问题的提交
git bisect reset             # 退出 bisect 模式
```

### 11.3 Git Hooks（钩子脚本）

| 钩子名称             | 触发时机             | 用途                   |
| -------------------- | -------------------- | ---------------------- |
| `pre-commit`         | commit 前            | 代码格式检查、lint     |
| `prepare-commit-msg` | 提交消息编辑器打开前 | 自动生成提交消息模板   |
| `commit-msg`         | 提交消息编辑后       | 检查提交消息格式       |
| `post-commit`        | commit 后            | 通知、日志记录         |
| `pre-push`           | push 前              | 运行测试、检查         |
| `post-merge`         | merge 后             | 更新依赖、重新生成文件 |

```bash
# 示例：pre-commit 钩子
# 文件位置：.git/hooks/pre-commit
#!/bin/bash
# 运行代码格式检查
npm run lint
if [ $? -ne 0 ]; then
    echo "❌ Lint 检查失败，请修复后重新提交"
    exit 1
fi
```

### 11.4 Reflog（恢复丢失的提交）

```bash
# 查看所有操作记录
git reflog

# 恢复到某个状态
git reset --hard HEAD@{10}   # 恢复到第10条记录的位置

# 找回被删除的分支
git reflog
git checkout -b recovered-branch HEAD@{5}
```

### 11.5 Git Worktree（多分支同时工作）

```bash
# 创建新的 worktree
git worktree add ../project-feature feature-branch

# 列出所有 worktree
git worktree list

# 移除 worktree
git worktree remove ../project-feature

# 清理不再存在的 worktree
git worktree prune
```

---

## 12. 常用工作流

### 12.1 功能分支工作流

```bash
# 1. 从主分支创建功能分支
git checkout main
git pull origin main
git checkout -b feature/awesome-feature

# 2. 开发并提交
git add .
git commit -m "feat: add awesome feature"

# 3. 定期合并主分支的更新
git fetch origin
git merge main
# 或
git rebase main

# 4. 推送到远程
git push -u origin feature/awesome-feature

# 5. 创建 PR/MR，合并后删除本地分支
git checkout main
git pull origin main
git branch -d feature/awesome-feature
```

### 12.2 修复紧急 Bug 工作流

```bash
# 1. 从主分支创建 hotfix 分支
git checkout main
git checkout -b hotfix/critical-bug

# 2. 修复并提交
git add .
git commit -m "fix: critical bug in production"

# 3. 合并到主分支
git checkout main
git merge --no-ff hotfix/critical-bug
git tag -a v2.0.1 -m "Hotfix v2.0.1"
git push origin main --tags

# 4. 同步到开发分支（如果有）
git checkout develop
git merge main

# 5. 删除 hotfix 分支
git branch -d hotfix/critical-bug
```

---

## 13. 快速参考卡片

### 13.1 按场景速查

| 场景         | 命令                                                    |
| ------------ | ------------------------------------------------------- |
| 初始化仓库   | `git init`                                              |
| 克隆仓库     | `git clone <URL>`                                       |
| 查看状态     | `git status` / `git status -s`                          |
| 添加文件     | `git add .` / `git add -A` / `git add <文件>`           |
| 提交         | `git commit -m "message"`                               |
| 提交所有     | `git commit -a -m "message"`                            |
| 修改最近提交 | `git commit --amend`                                    |
| 查看历史     | `git log --oneline --graph --all`                       |
| 查看差异     | `git diff` / `git diff --staged`                        |
| 创建分支     | `git branch <分支名>` / `git switch -c <分支名>`        |
| 切换分支     | `git switch <分支名>` / `git checkout <分支名>`         |
| 合并分支     | `git merge <分支名>`                                    |
| 变基         | `git rebase <分支名>`                                   |
| 删除分支     | `git branch -d <分支名>`                                |
| 推送         | `git push` / `git push -u origin <分支>`                |
| 拉取         | `git pull` / `git pull --rebase`                        |
| 获取更新     | `git fetch`                                             |
| 撤销暂存     | `git reset HEAD <文件>` / `git restore --staged <文件>` |
| 丢弃修改     | `git restore <文件>` / `git checkout -- <文件>`         |
| 撤销提交     | `git reset --soft HEAD~1` / `git revert <commit>`       |
| 暂存修改     | `git stash` / `git stash pop`                           |
| 打标签       | `git tag -a v1.0 -m "msg"` / `git push --tags`          |
| 查看远程     | `git remote -v`                                         |

### 13.2 命令简写速查

| 完整命令                          | 简写     |
| --------------------------------- | -------- |
| `git status`                      | `git st` |
| `git checkout`                    | `git co` |
| `git branch`                      | `git br` |
| `git commit`                      | `git cm` |
| `git log --oneline --graph --all` | `git lg` |
| `git push`                        | `git ps` |
| `git pull`                        | `git pl` |

> 注：简写需通过 `git config` 设置别名

---

## 14. 常见问题与解决方案

| 问题                         | 解决方案                                                     |
| ---------------------------- | ------------------------------------------------------------ |
| 提交信息写错了               | `git commit --amend -m "新消息"`                             |
| 忘记添加文件就提交了         | `git add <文件> && git commit --amend --no-edit`             |
| 误把文件删除了               | `git restore <文件>` 或 `git checkout -- <文件>`             |
| 误提交到错误分支             | `git reset HEAD~1` 然后 `git stash`，切换分支后 `git stash pop` |
| 合并冲突了                   | 手动解决冲突 → `git add .` → `git commit`                    |
| 不小心 commit 到 main 分支了 | `git reset HEAD~1`，创建新分支再提交                         |
| 误删分支了                   | `git reflog` 找到提交 → `git checkout -b <分支名> <commit>`  |
| 想撤销已推送的提交           | `git revert <commit>` 然后 `git push`（安全）或 `git reset --hard` + `git push --force`（慎用） |
| 提交历史太乱想整理           | `git rebase -i HEAD~N` 进行交互式变基                        |
| 忘记添加 .gitignore 了       | 添加规则后 `git rm -r --cached .` 然后重新 add               |
| 想合并多个提交               | `git rebase -i HEAD~N` 将 `pick` 改为 `squash` 或 `fixup`    |
| 拉了远程代码导致冲突         | `git stash` → `git pull` → `git stash pop` → 解决冲突        |

---

上一篇：《02-依赖管理与包管理器.md》　｜　下一篇：《04-Shell脚本编程.md》　｜　模块索引：《../README.md》
