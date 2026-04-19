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
uv run backup tui
```

## 依赖说明

- GitHub 协议依赖：`gh` CLI（需先 `gh auth login`）
- 加密实现：`AES-256-GCM + scrypt`（通过 `cryptography`）
- TUI 依赖：系统需安装 `whiptail`
