# backup-utilities

面向“备份单元”的增量备份工具。当前已实现 GitHub 协议，产物默认为每单元少量文件：
- `metadata.json`（明文元数据）
- `payload.tar.zst` 或 `payload.tar.zst.enc`（可选加密载荷）

## 核心概念

- 备份单元：独立判断变化、独立打包和校验的最小对象（例如 `github/owner/repo`）。
- 增量策略：通过来源指纹判断是否变化，未变化单元直接跳过。
- 加密策略：仅加密 payload，metadata 保持明文；默认可按规则或单元覆盖。

## 环境变量

- `BACKUP_ROOT`：备份根目录。
  - 若已设置，可省略命令中的 `--root`。
  - 若同时提供 `--root`，以 `--root` 为准。
- `BACKUP_PASSPHRASE`：加密/解密口令。
  - 若未设置，仅在交互式 TTY 下提示输入。
  - 非交互场景（如管道/CI）未设置时会报错。
  - 进程启动后会读取到内存并从环境变量中移除，避免后续子进程继承。
  - 口令会在进程内缓存，后续操作可复用。
- TUI 口令输入：当触发需要口令的备份时弹窗输入（不回显）。
- 解密时若复用口令失败，会提示重新输入并自动重试一次。
- `BACKUP_PLAIN_TRACEBACK=1`：Textual TUI 异常时输出朴素 Python traceback（便于复制粘贴）。

## 使用示例

### 0. GitHub 登录（首次使用）

```bash
gh auth login
```

### 1. 初始化与查看状态

```bash
export BACKUP_ROOT=/path/to/backup-root
uv run backup init
uv run backup status
```

### 2. 发现并选择备份单元

```bash
# discover 是协议路由入口；当前支持 github
uv run backup discover github --limit 50

# 也可显式指定账号/组织
uv run backup discover github --user your-github-user --limit 50

# 选择或排除单元
uv run backup select add github/owner/repo
uv run backup select remove github/owner/repo
```

### 3. 配置单元加密策略

```bash
uv run backup select encrypt github/owner/repo
uv run backup select decrypt github/owner/repo
```

### 4. 执行与校验备份

```bash
# 加密备份建议先设置口令环境变量
export BACKUP_PASSPHRASE='your-passphrase'

uv run backup run
uv run backup verify
```

### 5. 手动解密单元载荷

```bash
uv run backup decrypt-unit --unit github/owner/repo --out /tmp/github-owner-repo.tar.zst
```

### 6. 启动 TUI

```bash
# 首次请先同步依赖（包含 textual）
uv sync
uv run backup tui
```

### 7. Textual TUI 快捷键（MVP）

```text
Tab    在搜索框与列表间切换焦点
Esc    搜索框聚焦时切回列表
Down   搜索框聚焦时切回列表
Space  切换当前行选中
a      全选当前可见项
n      全不选当前可见项
b      对选中项串行执行 backup
e      对选中项执行 force encrypt（已是 encrypt 跳过）
d      对选中项执行 force decrypt（已是 decrypt 跳过）
x      从 selected 中移除（带确认）
m      手动添加 unit
f      discover 后批量添加
Ctrl+P 清空进程内口令缓存
r      刷新列表
q      退出
```

### 8. 搜索语法（MVP）

- 自由文本：按 `unit_id` 子串过滤，多个词为 AND
- 冒号条件：
  - `mtime:<op><date>`：上次备份时间
  - `ctime:<op><date>`：上次检查时间
- 运算符：`> >= < <= = !=`
- 日期：`YYYY-M-D` 或 `YYYY-MM-DD`

示例：

```text
github/foo
github mtime:>2026-1-1
ctime:>=2026-04-01
mtime:>=2026-01-01 ctime:<2026-06-01
```

说明：TUI 列表中的 `Last Snapshot Time` 仅显示 `Y-m-d` 日期，不显示具体时分秒。

## 依赖说明

- GitHub 协议依赖：`gh` CLI（需先 `gh auth login`）
- 加密实现：`AES-256-GCM + scrypt`（通过 `cryptography`）
- TUI 依赖：`textual`

## 日志

- CLI 与 TUI 共用同一套日志逻辑，写入 `<BACKUP_ROOT>/logs/`。
- 日志文件按日期聚合：`YYYY-MM-DD.log`（例如 `2026-04-19.log`）。
- 每行包含本地时间戳、来源（`cli` / `tui`）与消息。
