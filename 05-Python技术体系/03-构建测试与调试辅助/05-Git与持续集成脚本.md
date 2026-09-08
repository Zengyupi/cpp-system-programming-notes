# Git与持续集成脚本

> 本节目标：掌握用 Python 调用 git/GitPython 做批量操作、从提交记录生成 changelog、提交信息与分支保护校验、release 打包签名脚本、pre-commit 钩子编写，以及在 GitHub Actions/GitLab CI 中运行 Python 质量脚本的方法，能够用 Python 自动化 C++/Rust 项目的版本管理和 CI 流程。

## 本章速览

- [1. 工程场景：Python 在 Git 与 CI 中的角色](#1-工程场景python-在-git-与-ci-中的角色)
- [2. 调用 git 与 GitPython](#2-调用-git-与-gitpython)
  - [2.1 subprocess 调用 git](#21-subprocess-调用-git)
  - [2.2 GitPython 高级操作](#22-gitpython-高级操作)
- [3. 批量 Git 操作](#3-批量-git-操作)
  - [3.1 子模块批量更新](#31-子模块批量更新)
  - [3.2 多仓库批量操作](#32-多仓库批量操作)
- [4. 从提交记录生成 Changelog](#4-从提交记录生成-changelog)
- [5. 提交信息与分支保护校验](#5-提交信息与分支保护校验)
  - [5.1 Conventional Commits 校验](#51-conventional-commits-校验)
  - [5.2 分支命名与保护校验](#52-分支命名与保护校验)
- [6. Release 打包与签名脚本](#6-release-打包与签名脚本)
- [7. pre-commit 钩子编写](#7-pre-commit-钩子编写)
- [8. CI 中的 Python 质量脚本](#8-ci-中的-python-质量脚本)
  - [8.1 GitHub Actions](#81-github-actions)
  - [8.2 GitLab CI](#82-gitlab-ci)
- [9. 完整实战：版本发布自动化脚本](#9-完整实战版本发布自动化脚本)
- [10. 常见坑与避坑指南](#10-常见坑与避坑指南)
- [11. 本节小结](#11-本节小结)

---

## 1. 工程场景：Python 在 Git 与 CI 中的角色

C++/Rust 项目的版本管理和 CI 流程涉及大量重复性操作：生成 changelog、校验提交信息、打包 release、运行代码质量检查、管理子模块。这些操作用 shell 脚本可以写，但一旦涉及条件判断、JSON 解析、正则校验、跨平台兼容，Python 更可靠。

Python 在 Git 与 CI 中的角色是**自动化编排器**：用 `subprocess` 调用 git 命令或用 GitPython 库操作仓库，解析提交记录，校验提交信息格式，打包并签名发布产物，编写 pre-commit 钩子，在 CI 中运行代码质量检查。

典型场景：

- **Changelog 生成**：从 git log 自动生成符合 Keep a Changelog 格式的变更日志
- **提交信息校验**：pre-commit 钩子检查提交信息是否符合 Conventional Commits 规范
- **Release 打包**：自动打 tag、编译、打包、计算校验和、生成 release notes
- **子模块管理**：批量更新、检出、状态检查多个 git submodule
- **CI 质量门禁**：在 GitHub Actions/GitLab CI 中运行 Python 脚本检查代码格式、静态分析、测试覆盖率

## 2. 调用 git 与 GitPython

### 2.1 subprocess 调用 git

最简单可靠的方式是用 `subprocess.run` 调用 git 命令，输出用 `--format` 或 `--porcelain` 选项变成机器可读格式。

```python
import subprocess
from pathlib import Path
from dataclasses import dataclass

@dataclass
class GitCommit:
    hash: str
    short_hash: str
    author: str
    email: str
    date: str
    subject: str
    body: str

def git_run(args: list[str], cwd: Path | None = None,
            check: bool = True, timeout: int = 30) -> str:
    """运行 git 命令，返回 stdout。"""
    cmd = ["git"] + args
    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True,
        timeout=timeout, encoding="utf-8", errors="replace",
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败:\n{result.stderr}")
    return result.stdout.strip()

def get_log(repo: Path, since: str | None = None,
            until: str | None = None, max_count: int | None = None) -> list[GitCommit]:
    """获取提交记录，用固定格式便于解析。"""
    format_str = "%H%x1f%h%x1f%an%x1f%ae%x1f%ad%x1f%s%x1f%b%x1e"
    args = ["log", f"--format={format_str}", "--date=short"]
    if since:
        args.append(f"--since={since}")
    if until:
        args.append(f"--until={until}")
    if max_count:
        args.extend(["-n", str(max_count)])

    output = git_run(args, cwd=repo)
    commits = []
    for entry in output.split("\x1e"):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split("\x1f")
        if len(parts) >= 6:
            commits.append(GitCommit(
                hash=parts[0],
                short_hash=parts[1],
                author=parts[2],
                email=parts[3],
                date=parts[4],
                subject=parts[5],
                body=parts[6] if len(parts) > 6 else "",
            ))
    return commits

def get_current_branch(repo: Path) -> str:
    """获取当前分支名。"""
    return git_run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo)

def get_changed_files(repo: Path, ref: str = "HEAD") -> list[str]:
    """获取相对于 ref 的变更文件列表。"""
    output = git_run(["diff", "--name-only", ref], cwd=repo)
    return [line for line in output.splitlines() if line]

def get_staged_files(repo: Path) -> list[str]:
    """获取已暂存的文件。"""
    output = git_run(["diff", "--cached", "--name-only"], cwd=repo)
    return [line for line in output.splitlines() if line]

def is_dirty(repo: Path) -> bool:
    """检查工作区是否有未提交的变更。"""
    output = git_run(["status", "--porcelain"], cwd=repo)
    return bool(output.strip())
```

### 2.2 GitPython 高级操作

GitPython（`pip install GitPython`）是 git 的 Python 绑定，提供面向对象的 API，比 subprocess 更方便处理复杂操作。

```python
from git import Repo, GitCommandError

def open_repo(repo_path: Path) -> Repo:
    """打开仓库。"""
    return Repo(repo_path)

def get_branches(repo: Repo) -> list[str]:
    """获取所有本地分支。"""
    return [b.name for b in repo.branches]

def get_tags(repo: Repo) -> list[str]:
    """获取所有标签。"""
    return [t.name for t in repo.tags]

def create_branch(repo: Repo, name: str, base: str = "HEAD"):
    """创建分支。"""
    repo.git.branch(name, base)

def checkout(repo: Repo, ref: str):
    """检出分支或提交。"""
    repo.git.checkout(ref)

def commit(repo: Repo, message: str, files: list[str] | None = None):
    """提交。"""
    if files:
        repo.index.add(files)
    else:
        repo.index.add("*")
    repo.index.commit(message)

def get_diff(repo: Repo, ref_a: str, ref_b: str) -> str:
    """获取两个引用之间的 diff。"""
    return repo.git.diff(f"{ref_a}..{ref_b}")

def list_submodules(repo: Repo) -> list[dict]:
    """列出子模块状态。"""
    submodules = []
    for sm in repo.submodules:
        submodules.append({
            "name": sm.name,
            "path": sm.path,
            "url": sm.url,
            "commit": sm.hexsha,
            "branch": sm.branch,
        })
    return submodules
```

**GitPython vs subprocess 选择**：
- 简单命令、需要精确控制输出格式：subprocess
- 复杂操作（分支管理、索引操作、对象访问）：GitPython
- CI 环境中不想装额外依赖：subprocess

## 3. 批量 Git 操作

### 3.1 子模块批量更新

C++/Rust 项目常用 git submodule 管理第三方依赖。批量更新子模块是常见操作。

```python
def update_all_submodules(repo_path: Path, recursive: bool = True,
                          init: bool = True) -> dict:
    """批量更新所有子模块。"""
    results = {}

    # 先获取子模块列表
    output = git_run(["submodule", "status"], cwd=repo_path)
    submodules = []
    for line in output.splitlines():
        if not line.strip():
            continue
        # 格式: <status><hash> <path> [(branch)]
        parts = line.strip().split()
        if len(parts) >= 2:
            submodules.append({
                "status": parts[0][0],  # ' '=正常, '-'=未初始化, '+'=不同提交, 'U'=冲突
                "hash": parts[0][1:],
                "path": parts[1],
            })

    for sm in submodules:
        print(f"更新子模块: {sm['path']} (状态: {sm['status']})")
        try:
            args = ["submodule", "update"]
            if init:
                args.append("--init")
            if recursive:
                args.append("--recursive")
            args.append("--", sm["path"])
            git_run(args, cwd=repo_path, timeout=120)
            results[sm["path"]] = "success"
        except RuntimeError as e:
            results[sm["path"]] = f"failed: {e}"
            print(f"  失败: {e}")

    return results

def check_submodule_consistency(repo_path: Path) -> list[dict]:
    """检查子模块是否有未提交的变更或与记录不一致。"""
    issues = []
    output = git_run(["submodule", "foreach", "--recursive",
                      "git status --porcelain"], cwd=repo_path)

    current_sm = None
    for line in output.splitlines():
        if line.startswith("Entering "):
            current_sm = line[len("Entering "):].strip("'")
        elif line.strip() and current_sm:
            issues.append({
                "submodule": current_sm,
                "change": line.strip(),
            })

    return issues
```

### 3.2 多仓库批量操作

monorepo 或多仓库项目中，需要对多个仓库执行相同操作（fetch、pull、status）。

```python
from pathlib import Path

class MultiRepoManager:
    """多仓库批量管理器。"""

    def __init__(self, repos: list[Path]):
        self.repos = repos

    @classmethod
    def from_parent_dir(cls, parent: Path, pattern: str = "*") -> "MultiRepoManager":
        """从父目录下发现所有 git 仓库。"""
        repos = []
        for d in parent.glob(pattern):
            if d.is_dir() and (d / ".git").exists():
                repos.append(d)
        return cls(repos)

    def fetch_all(self):
        """所有仓库执行 fetch。"""
        for repo in self.repos:
            print(f"fetch: {repo.name}")
            try:
                git_run(["fetch", "--all", "--prune"], cwd=repo, timeout=60)
            except RuntimeError as e:
                print(f"  失败: {e}")

    def status_all(self) -> dict[str, str]:
        """所有仓库检查状态。"""
        statuses = {}
        for repo in self.repos:
            branch = get_current_branch(repo)
            dirty = is_dirty(repo)
            ahead_behind = git_run(
                ["rev-list", "--left-right", "--count", f"origin/{branch}...{branch}"],
                cwd=repo, check=False,
            )
            statuses[repo.name] = {
                "branch": branch,
                "dirty": dirty,
                "ahead_behind": ahead_behind.strip() if ahead_behind else "N/A",
            }
        return statuses

    def pull_all(self, rebase: bool = True):
        """所有仓库执行 pull。"""
        for repo in self.repos:
            print(f"pull: {repo.name}")
            if is_dirty(repo):
                print(f"  跳过（工作区有变更）")
                continue
            try:
                args = ["pull"]
                if rebase:
                    args.append("--rebase")
                git_run(args, cwd=repo, timeout=120)
            except RuntimeError as e:
                print(f"  失败: {e}")
```

## 4. 从提交记录生成 Changelog

按照 Conventional Commits 规范解析提交记录，生成 Keep a Changelog 格式的变更日志。

```python
import re
from collections import defaultdict
from datetime import datetime

# Conventional Commits 格式: type(scope): subject
COMMIT_PATTERN = re.compile(
    r'^(?P<type>feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)'
    r'(?:\((?P<scope>[\w/.-]+)\))?'
    r'(?P<breaking>!)?:\s+(?P<subject>.+)$'
)

# 类型到 changelog 分类的映射
TYPE_TO_SECTION = {
    "feat": "Added",
    "fix": "Fixed",
    "perf": "Performance",
    "refactor": "Changed",
    "docs": "Documentation",
    "build": "Build",
    "ci": "CI",
    "test": "Tests",
    "chore": "Misc",
    "revert": "Reverted",
    "style": "Style",
}

SECTION_ORDER = [
    "Breaking Changes", "Added", "Changed", "Deprecated",
    "Removed", "Fixed", "Performance", "Documentation",
    "Build", "CI", "Tests", "Misc", "Reverted", "Style",
]

def parse_commit(commit: GitCommit) -> dict | None:
    """解析 Conventional Commits 格式的提交。"""
    m = COMMIT_PATTERN.match(commit.subject)
    if not m:
        return None

    data = m.groupdict()
    is_breaking = data["breaking"] == "!" or "BREAKING CHANGE" in commit.body

    return {
        "type": data["type"],
        "scope": data["scope"],
        "subject": data["subject"],
        "breaking": is_breaking,
        "hash": commit.short_hash,
        "author": commit.author,
        "date": commit.date,
        "body": commit.body,
    }

def generate_changelog(repo: Path, since_tag: str | None = None,
                       version: str = "Unreleased") -> str:
    """生成 changelog。"""
    # 获取提交记录
    if since_tag:
        commits = get_log(repo, since=f"{since_tag}..HEAD")
    else:
        commits = get_log(repo, max_count=200)

    # 解析并分类
    sections = defaultdict(list)
    unparsed = []

    for commit in commits:
        parsed = parse_commit(commit)
        if not parsed:
            unparsed.append(commit)
            continue

        if parsed["breaking"]:
            sections["Breaking Changes"].append(parsed)
        else:
            section = TYPE_TO_SECTION.get(parsed["type"], "Misc")
            sections[section].append(parsed)

    # 生成 Markdown
    lines = []
    today = datetime.now().strftime("%Y-%m-%d")
    lines.append(f"## [{version}] - {today}")
    lines.append("")

    for section in SECTION_ORDER:
        if section not in sections:
            continue
        lines.append(f"### {section}")
        lines.append("")
        for item in sections[section]:
            scope = f"**{item['scope']}:** " if item["scope"] else ""
            lines.append(f"- {scope}{item['subject']} ({item['hash']})")
        lines.append("")

    if unparsed:
        lines.append("### Other Commits")
        lines.append("")
        for commit in unparsed:
            lines.append(f"- {commit.subject} ({commit.short_hash})")
        lines.append("")

    return "\n".join(lines)

def update_changelog_file(repo: Path, changelog_path: Path,
                          version: str, since_tag: str | None = None):
    """更新 CHANGELOG.md 文件，在顶部插入新版本。"""
    new_section = generate_changelog(repo, since_tag, version)

    if changelog_path.exists():
        old_content = changelog_path.read_text(encoding="utf-8")
        # 在标题行后插入
        header_end = old_content.find("\n\n")
        if header_end > 0:
            header = old_content[:header_end + 2]
            rest = old_content[header_end + 2:]
            new_content = header + new_section + "\n" + rest
        else:
            new_content = new_section + "\n" + old_content
    else:
        new_content = "# Changelog\n\n" + new_section

    changelog_path.write_text(new_content, encoding="utf-8")
    print(f"Changelog 已更新: {changelog_path}")
```

## 5. 提交信息与分支保护校验

### 5.1 Conventional Commits 校验

pre-commit 或 CI 中校验提交信息格式。

```python
import re
import sys
from pathlib import Path

def validate_commit_message(message: str) -> list[str]:
    """校验提交信息是否符合 Conventional Commits 规范。"""
    errors = []
    lines = message.strip().splitlines()

    if not lines:
        errors.append("提交信息为空")
        return errors

    subject = lines[0]

    # 1. 主题行长度
    if len(subject) > 72:
        errors.append(f"主题行过长 ({len(subject)} > 72 字符)")

    # 2. 格式校验
    m = COMMIT_PATTERN.match(subject)
    if not m:
        errors.append(
            "主题行不符合 Conventional Commits 格式。\n"
            "  期望格式: <type>(<scope>): <subject>\n"
            "  示例: feat(net): add TCP keepalive support\n"
            "  合法类型: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert"
        )
    else:
        # 3. 主题首字母不大写（约定）
        if m.group("subject") and m.group("subject")[0].isupper():
            errors.append("主题首字母不应大写")

        # 4. 主题末尾不加句号
        if subject.endswith("."):
            errors.append("主题末尾不应加句号")

    # 5. 正文与主题之间有空行
    if len(lines) > 1 and lines[1].strip():
        errors.append("主题行与正文之间应有空行")

    # 6. 正文每行不超过 100 字符
    for i, line in enumerate(lines[1:], 2):
        if len(line) > 100:
            errors.append(f"第 {i} 行过长 ({len(line)} > 100 字符)")

    return errors

def validate_commit_message_file(msg_file: Path) -> bool:
    """从 git commit message 文件读取并校验。"""
    message = msg_file.read_text(encoding="utf-8")
    # 去掉注释行
    message = "\n".join(
        line for line in message.splitlines() if not line.startswith("#")
    )

    errors = validate_commit_message(message)
    if errors:
        print("提交信息校验失败:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return False
    return True

# 作为 commit-msg 钩子使用:
# ln -s ../../scripts/validate_commit_msg.py .git/hooks/commit-msg
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: validate_commit_msg.py <commit_message_file>")
        sys.exit(1)
    success = validate_commit_message_file(Path(sys.argv[1]))
    sys.exit(0 if success else 1)
```

### 5.2 分支命名与保护校验

```python
import re

BRANCH_PATTERN = re.compile(
    r'^(main|master|develop|release/[\d.]+|hotfix/[\w.-]+|'
    r'feature/[\w.-]+|bugfix/[\w.-]+|chore/[\w.-]+|'
    r'dependabot/[\w./-]+)$'
)

def validate_branch_name(branch: str) -> list[str]:
    """校验分支命名规范。"""
    errors = []
    if not BRANCH_PATTERN.match(branch):
        errors.append(
            f"分支名 '{branch}' 不符合规范。\n"
            "  允许的格式:\n"
            "  - main, master, develop\n"
            "  - feature/<name>\n"
            "  - bugfix/<name>\n"
            "  - hotfix/<name>\n"
            "  - release/<version>\n"
            "  - chore/<name>"
        )
    return errors

def check_protected_branch_rules(repo: Path) -> list[str]:
    """检查是否违反分支保护规则（本地预检）。"""
    issues = []
    branch = get_current_branch(repo)

    # 保护分支不允许直接提交
    if branch in ("main", "master"):
        issues.append(
            f"禁止直接向 {branch} 提交，请通过 Pull Request 合并"
        )

    # 保护分支不允许 force push（本地无法完全阻止，但可警告）
    if branch in ("main", "master", "develop"):
        # 检查是否有 rebase/amend 操作
        try:
            git_run(["rev-parse", "@{u}"], cwd=repo)  # 检查是否有上游
        except RuntimeError:
            pass  # 没有上游分支，跳过

    return issues
```

## 6. Release 打包与签名脚本

```python
import hashlib
import json
import subprocess
import tarfile
from datetime import datetime
from pathlib import Path

def create_release_archive(source_dir: Path, output_path: Path,
                           include: list[str] | None = None,
                           exclude: list[str] | None = None) -> Path:
    """创建 release 压缩包。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tarfile.open(output_path, "w:gz") as tar:
        for item in source_dir.iterdir():
            # 排除规则
            if exclude and any(item.match(pat) for pat in exclude):
                continue
            if include and not any(item.match(pat) for pat in include):
                continue
            tar.add(item, arcname=item.name)

    return output_path

def compute_checksums(file_path: Path) -> dict[str, str]:
    """计算文件的 SHA256 和 MD5 校验和。"""
    sha256 = hashlib.sha256()
    md5 = hashlib.md5()

    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
            md5.update(chunk)

    return {"sha256": sha256.hexdigest(), "md5": md5.hexdigest()}

def sign_file(file_path: Path, key_id: str | None = None) -> Path:
    """用 GPG 签名文件。"""
    sig_path = file_path.with_suffix(file_path.suffix + ".asc")
    cmd = ["gpg", "--armor", "--detach-sign"]
    if key_id:
        cmd.extend(["--local-user", key_id])
    cmd.append(str(file_path))

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"GPG 签名失败: {result.stderr}")
    return sig_path

def create_git_tag(repo: Path, version: str, message: str | None = None,
                   sign: bool = False) -> str:
    """创建 git tag。"""
    args = ["tag", "-a", version]
    if sign:
        args = ["tag", "-s", version]
    if message:
        args.extend(["-m", message])
    else:
        args.extend(["-m", f"Release {version}"])

    git_run(args, cwd=repo)
    git_run(["push", "origin", version], cwd=repo)
    return version

def generate_release_notes(repo: Path, version: str,
                           since_tag: str | None = None) -> str:
    """生成 release notes（基于 changelog）。"""
    changelog = generate_changelog(repo, since_tag, version)
    # release notes 可以加上下载链接和校验和的占位
    notes = f"# Release {version}\n\n{changelog}\n"
    notes += "## 下载\n\n"
    notes += "| 文件 | SHA256 |\n"
    notes += "|------|--------|\n"
    notes += "| `<artifact>.tar.gz` | `<sha256>` |\n"
    return notes

def full_release_process(repo: Path, version: str, build_dir: Path,
                         output_dir: Path, sign: bool = False,
                         gpg_key: str | None = None) -> dict:
    """完整的 release 流程：打 tag → 打包 → 校验和 → 签名。"""
    print(f"开始 release {version}")

    # 1. 检查工作区干净
    if is_dirty(repo):
        raise RuntimeError("工作区有未提交的变更，请先提交或暂存")

    # 2. 更新 changelog
    last_tag = git_run(["describe", "--tags", "--abbrev=0"], cwd=repo, check=False)
    update_changelog_file(repo, repo / "CHANGELOG.md", version,
                          since_tag=last_tag if last_tag else None)

    # 3. 提交 changelog 并打 tag
    git_run(["add", "CHANGELOG.md"], cwd=repo)
    git_run(["commit", "-m", f"chore: release {version}"], cwd=repo)
    create_git_tag(repo, version, message=f"Release {version}", sign=sign)

    # 4. 打包构建产物
    archive_name = f"myapp-{version}-linux-x86_64.tar.gz"
    archive_path = create_release_archive(
        build_dir, output_dir / archive_name,
        include=["bin", "lib", "config", "README.md", "LICENSE"],
        exclude=["*.o", "*.a", "CMakeFiles", "*.cmake"],
    )

    # 5. 计算校验和
    checksums = compute_checksums(archive_path)
    checksum_file = archive_path.with_name(archive_path.name + ".sha256")
    checksum_file.write_text(f"{checksums['sha256']}  {archive_name}\n", encoding="utf-8")

    # 6. 签名
    sig_file = None
    if sign:
        sig_file = sign_file(archive_path, gpg_key)

    # 7. 生成 release notes
    release_notes = generate_release_notes(repo, version, last_tag if last_tag else None)
    notes_path = output_dir / f"RELEASE_NOTES_{version}.md"
    notes_path.write_text(release_notes, encoding="utf-8")

    result = {
        "version": version,
        "tag": version,
        "archive": str(archive_path),
        "archive_size": archive_path.stat().st_size,
        "checksums": checksums,
        "checksum_file": str(checksum_file),
        "signature": str(sig_file) if sig_file else None,
        "release_notes": str(notes_path),
    }

    print(f"\nRelease {version} 完成:")
    for k, v in result.items():
        print(f"  {k}: {v}")

    return result
```

## 7. pre-commit 钩子编写

pre-commit 钩子在提交前运行检查，可以用 Python 脚本实现。

```python
#!/usr/bin/env python3
"""pre-commit 钩子：检查 C++ 代码格式和基本问题。

用法: 放在 .git/hooks/pre-commit，或用 pre-commit 框架管理。
"""
import subprocess
import sys
from pathlib import Path

def get_staged_cpp_files() -> list[Path]:
    """获取已暂存的 C++ 源文件。"""
    output = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True, text=True,
    ).stdout.strip()
    if not output:
        return []
    exts = {".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx", ".c"}
    return [Path(line) for line in output.splitlines() if Path(line).suffix in exts]

def check_clang_format(files: list[Path]) -> list[str]:
    """检查代码格式（clang-format）。"""
    errors = []
    for f in files:
        result = subprocess.run(
            ["clang-format", "--dry-run", "--Werror", str(f)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            errors.append(f"{f}: 格式不符合 .clang-format")
    return errors

def check_no_debug_code(files: list[Path]) -> list[str]:
    """检查是否有调试代码残留（printf、std::cout、TODO/FIXME）。"""
    errors = []
    for f in files:
        content = f.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("//"):
                continue  # 跳过注释
            if "printf(" in stripped and "//" not in stripped.split("printf(")[0]:
                errors.append(f"{f}:{i}: 残留 printf")
            if "std::cout" in stripped and "//" not in stripped.split("std::cout")[0]:
                errors.append(f"{f}:{i}: 残留 std::cout")
    return errors

def check_file_encoding(files: list[Path]) -> list[str]:
    """检查文件是否为 UTF-8 编码。"""
    errors = []
    for f in files:
        raw = f.read_bytes()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            errors.append(f"{f}: 不是 UTF-8 编码")
    return errors

def check_no_conflict_markers(files: list[Path]) -> list[str]:
    """检查是否有未解决的合并冲突标记。"""
    errors = []
    markers = ["<<<<<<<", "=======", ">>>>>>>"]
    for f in files:
        content = f.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(content.splitlines(), 1):
            if any(line.startswith(m) for m in markers):
                errors.append(f"{f}:{i}: 未解决的合并冲突标记")
    return errors

def main():
    files = get_staged_cpp_files()
    if not files:
        sys.exit(0)

    print(f"pre-commit 检查: {len(files)} 个 C++ 文件")
    all_errors = []

    all_errors.extend(check_clang_format(files))
    all_errors.extend(check_no_debug_code(files))
    all_errors.extend(check_file_encoding(files))
    all_errors.extend(check_no_conflict_markers(files))

    if all_errors:
        print("\npre-commit 检查失败:")
        for error in all_errors:
            print(f"  - {error}")
        print(f"\n共 {len(all_errors)} 个问题，请修复后重新提交")
        print("（可用 git commit --no-verify 跳过，但不推荐）")
        sys.exit(1)

    print("pre-commit 检查通过")
    sys.exit(0)

if __name__ == "__main__":
    main()
```

## 8. CI 中的 Python 质量脚本

### 8.1 GitHub Actions

在 GitHub Actions workflow 中运行 Python 质量脚本。

```yaml
# .github/workflows/quality.yml
name: Code Quality

on:
  pull_request:
    branches: [main, develop]
  push:
    branches: [main, develop]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # 需要完整历史来生成 changelog

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install GitPython pylint

      - name: Validate commit messages
        run: |
          python scripts/validate_commit_messages.py \
            --base origin/${{ github.base_ref }} \
            --head ${{ github.sha }}

      - name: Check code formatting
        run: python scripts/check_format.py --diff

      - name: Run static analysis
        run: python scripts/run_static_analysis.py

      - name: Generate changelog preview
        if: github.event_name == 'pull_request'
        run: |
          python scripts/generate_changelog.py \
            --since origin/${{ github.base_ref }} \
            --output changelog_preview.md

      - name: Upload changelog preview
        if: github.event_name == 'pull_request'
        uses: actions/upload-artifact@v4
        with:
          name: changelog-preview
          path: changelog_preview.md
```

对应的 Python 脚本示例——校验 PR 中所有提交的信息：

```python
#!/usr/bin/env python3
"""校验 PR 中所有提交的信息是否符合 Conventional Commits。"""
import argparse
import subprocess
import sys

def get_pr_commits(base: str, head: str) -> list[str]:
    """获取 PR 中的所有提交 hash。"""
    output = subprocess.run(
        ["git", "rev-list", f"{base}..{head}"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return output.splitlines() if output else []

def get_commit_message(commit_hash: str) -> str:
    """获取提交信息。"""
    return subprocess.run(
        ["git", "log", "-1", "--format=%B", commit_hash],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args()

    commits = get_pr_commits(args.base, args.head)
    if not commits:
        print("没有找到提交")
        sys.exit(0)

    print(f"校验 {len(commits)} 个提交的信息...")
    all_errors = []

    for commit_hash in commits:
        message = get_commit_message(commit_hash)
        errors = validate_commit_message(message)  # 复用前面定义的函数
        if errors:
            short_hash = commit_hash[:7]
            all_errors.append((short_hash, message.splitlines()[0], errors))

    if all_errors:
        print(f"\n{len(all_errors)} 个提交信息不符合规范:")
        for short_hash, subject, errors in all_errors:
            print(f"\n  {short_hash}: {subject}")
            for error in errors:
                print(f"    - {error}")
        sys.exit(1)

    print("所有提交信息符合规范")
    sys.exit(0)

if __name__ == "__main__":
    main()
```

### 8.2 GitLab CI

```yaml
# .gitlab-ci.yml
stages:
  - quality
  - build
  - release

variables:
  PYTHON_VERSION: "3.11"

code_quality:
  stage: quality
  image: python:${PYTHON_VERSION}-slim
  before_script:
    - pip install GitPython
  script:
    - python scripts/validate_commit_messages.py --base $CI_MERGE_REQUEST_DIFF_BASE_SHA --head $CI_COMMIT_SHA
    - python scripts/check_format.py --all
    - python scripts/check_license_headers.py
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"

release_package:
  stage: release
  image: python:${PYTHON_VERSION}-slim
  before_script:
    - apt-get update && apt-get install -y g++ cmake ninja-build gpg
    - pip install GitPython
  script:
    - python scripts/release.py --version $CI_COMMIT_TAG --sign
  artifacts:
    paths:
      - dist/*.tar.gz
      - dist/*.sha256
      - dist/*.asc
  rules:
    - if: $CI_COMMIT_TAG
```

## 9. 完整实战：版本发布自动化脚本

整合以上能力，实现一个完整的版本发布自动化脚本。

```python
#!/usr/bin/env python3
"""版本发布自动化脚本。

用法:
  python release.py --version 1.2.0 --dry-run
  python release.py --version 1.2.0 --sign --key mykey@example.com
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

class ReleaseManager:
    """版本发布管理器。"""

    def __init__(self, repo: Path, version: str, dry_run: bool = False,
                 sign: bool = False, gpg_key: str | None = None):
        self.repo = repo.resolve()
        self.version = version
        self.dry_run = dry_run
        self.sign = sign
        self.gpg_key = gpg_key
        self.dist_dir = self.repo / "dist"
        self.build_dir = self.repo / "build" / "release"
        self.steps: list[str] = []

    def _run(self, description: str, func, *args, **kwargs):
        """执行一个发布步骤。"""
        print(f"\n[{len(self.steps) + 1}] {description}")
        if self.dry_run:
            print("  (dry-run: 跳过实际执行)")
            self.steps.append(f"[DRY-RUN] {description}")
            return None
        try:
            result = func(*args, **kwargs)
            self.steps.append(f"[OK] {description}")
            return result
        except Exception as e:
            self.steps.append(f"[FAIL] {description}: {e}")
            print(f"  失败: {e}")
            raise

    def preflight_check(self):
        """发布前检查。"""
        # 检查在正确的分支
        branch = get_current_branch(self.repo)
        if branch not in ("main", "master", "release"):
            raise RuntimeError(f"请在 main/master/release 分支上发布，当前: {branch}")

        # 检查工作区干净
        if is_dirty(self.repo):
            raise RuntimeError("工作区有未提交的变更")

        # 检查 tag 不存在
        tags = git_run(["tag", "-l", self.version], cwd=self.repo)
        if tags:
            raise RuntimeError(f"tag {self.version} 已存在")

        # 检查必要的构建目录
        if not self.build_dir.exists():
            print(f"  警告: 构建目录 {self.build_dir} 不存在，将跳过打包")

        print("  预检通过")

    def update_changelog(self):
        """更新 changelog。"""
        last_tag = git_run(["describe", "--tags", "--abbrev=0"], cwd=self.repo, check=False)
        update_changelog_file(
            self.repo, self.repo / "CHANGELOG.md",
            self.version, since_tag=last_tag if last_tag else None,
        )

    def commit_and_tag(self):
        """提交 changelog 并打 tag。"""
        git_run(["add", "CHANGELOG.md"], cwd=self.repo)
        git_run(["commit", "-m", f"chore(release): {self.version}"], cwd=self.repo)
        create_git_tag(
            self.repo, self.version,
            message=f"Release {self.version}\n\n见 CHANGELOG.md",
            sign=self.sign,
        )

    def build(self):
        """构建 release 版本。"""
        from build_integration import CMakeBuilder  # 复用构建模块
        builder = CMakeBuilder(self.repo, self.build_dir, build_type="Release")
        code, output = builder.configure()
        if code != 0:
            raise RuntimeError(f"配置失败: {output[-500:]}")
        code, output = builder.build(jobs=8)
        if code != 0:
            raise RuntimeError(f"构建失败: {output[-500:]}")

    def package(self):
        """打包发布产物。"""
        if not self.build_dir.exists():
            print("  构建目录不存在，跳过打包")
            return None

        self.dist_dir.mkdir(parents=True, exist_ok=True)
        archive_name = f"myapp-{self.version}-linux-x86_64.tar.gz"
        archive_path = create_release_archive(
            self.build_dir, self.dist_dir / archive_name,
            include=["bin", "lib", "share"],
            exclude=["*.o", "*.obj", "CMakeFiles", "*.cmake", "*.ninja"],
        )

        # 校验和
        checksums = compute_checksums(archive_path)
        checksum_file = archive_path.with_name(archive_path.name + ".sha256")
        checksum_file.write_text(
            f"{checksums['sha256']}  {archive_name}\n", encoding="utf-8"
        )

        # 签名
        sig_file = None
        if self.sign:
            sig_file = sign_file(archive_path, self.gpg_key)

        result = {
            "archive": str(archive_path),
            "size": archive_path.stat().st_size,
            "sha256": checksums["sha256"],
            "checksum_file": str(checksum_file),
            "signature": str(sig_file) if sig_file else None,
        }
        print(f"  打包完成: {archive_path} ({result['size'] / 1024:.1f} KB)")
        return result

    def push(self):
        """推送到远程。"""
        git_run(["push", "origin", "HEAD"], cwd=self.repo)
        git_run(["push", "origin", self.version], cwd=self.repo)

    def run(self) -> dict:
        """执行完整发布流程。"""
        print(f"{'='*60}")
        print(f"版本发布: {self.version}")
        print(f"仓库: {self.repo}")
        print(f"模式: {'dry-run' if self.dry_run else '实际执行'}")
        print(f"{'='*60}")

        self._run("发布前检查", self.preflight_check)
        self._run("更新 CHANGELOG", self.update_changelog)
        self._run("构建 release", self.build)
        self._run("打包产物", self.package)
        self._run("提交并打 tag", self.commit_and_tag)
        self._run("推送到远程", self.push)

        summary = {
            "version": self.version,
            "timestamp": datetime.now().isoformat(),
            "dry_run": self.dry_run,
            "steps": self.steps,
            "success": all(s.startswith("[OK]") or s.startswith("[DRY-RUN]") for s in self.steps),
        }

        # 保存发布记录
        record_path = self.dist_dir / f"release_{self.version}.json"
        if not self.dry_run:
            record_path.parent.mkdir(parents=True, exist_ok=True)
            record_path.write_text(
                json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
            )

        print(f"\n{'='*60}")
        print(f"发布{'（模拟）' if self.dry_run else ''}完成: {self.version}")
        print(f"{'='*60}")
        return summary

def main():
    parser = argparse.ArgumentParser(description="版本发布自动化")
    parser.add_argument("--version", required=True, help="发布版本号，如 1.2.0")
    parser.add_argument("--repo", type=Path, default=Path("."), help="仓库路径")
    parser.add_argument("--dry-run", action="store_true", help="模拟执行，不实际修改")
    parser.add_argument("--sign", action="store_true", help="GPG 签名 tag 和产物")
    parser.add_argument("--key", type=str, help="GPG key ID")
    args = parser.parse_args()

    # 版本号格式校验
    if not __import__("re").match(r'^\d+\.\d+\.\d+$', args.version):
        print(f"版本号格式错误: {args.version}（期望 x.y.z）")
        sys.exit(1)

    manager = ReleaseManager(
        args.repo, args.version,
        dry_run=args.dry_run, sign=args.sign, gpg_key=args.key,
    )

    try:
        result = manager.run()
        sys.exit(0 if result["success"] else 1)
    except Exception as e:
        print(f"\n发布失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

## 10. 常见坑与避坑指南

| 坑 | 现象 | 解决方案 |
|---|---|---|
| git 命令输出编码问题 | 中文提交信息乱码 | 设 `encoding="utf-8", errors="replace"`，或 `git config core.quotepath false` |
| CI 中 git 历史不完整 | `git log` 只能看到部分提交 | `actions/checkout` 设 `fetch-depth: 0` |
| pre-commit 钩子未生效 | 钩子脚本没有执行权限 | `chmod +x .git/hooks/pre-commit`，或用 pre-commit 框架管理 |
| tag 推送失败 | `git push --tags` 被拒绝 | 检查分支保护规则，release tag 可能需要特殊权限 |
| GPG 签名在 CI 中失败 | 没有私钥或 pinentry 交互 | 用 `gpg --batch --yes --passphrase` 非交互模式，或用 CI secret 导入 key |
| 子模块递归更新超时 | 大子模块 clone 超时 | 增大 timeout，或用 `--depth 1` 浅克隆 |
| changelog 重复条目 | 同一个提交出现在多个版本 | 用 `--since <last_tag>..HEAD` 严格限定范围 |
| 多仓库操作状态混乱 | 一个仓库失败后后续状态不一致 | 每个仓库独立 try/except，记录成功/失败，最后汇总 |
| release 脚本误操作 | dry-run 没开就执行了实际发布 | 默认 dry-run，加 `--execute` 才实际执行；关键操作前加确认提示 |

## 11. 本节小结

- git 操作可以用 `subprocess.run`（简单可靠）或 GitPython（面向对象，复杂操作），CI 环境推荐 subprocess 避免额外依赖
- 批量操作包括子模块更新、多仓库 fetch/pull/status，每个操作独立异常处理并记录结果
- Changelog 生成基于 Conventional Commits 规范解析提交，按类型分类输出 Keep a Changelog 格式
- 提交信息校验检查格式、长度、首字母、句号，分支保护校验检查分支命名和保护分支直接提交
- Release 流程包括：预检 → 更新 changelog → 构建 → 打包 → 校验和 → 签名 → 打 tag → 推送，支持 dry-run 模式
- pre-commit 钩子检查代码格式、调试代码残留、编码、合并冲突标记，失败时阻止提交
- GitHub Actions/GitLab CI 中运行 Python 质量脚本需要完整 git 历史（fetch-depth: 0）和 Python 环境
- 完整发布脚本整合了预检、changelog、构建、打包、签名、tag、推送全流程，支持 dry-run 和异常处理

跨模块参考：
- 《01-构建流程集成.md》
- 《../02-文件文本与批处理自动化/04-子进程与命令编排.md》

---

上一篇：《04-调试与性能分析辅助.md》
