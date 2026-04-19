# Quick Reference

## 常用环境变量

- `BACKUP_ROOT`：备份根目录（默认 `./backup`）。
- `BACKUP_PATH`：兼容旧写法，仍可用。
- `BACKUP_PASSPHRASE`：加密/解密口令。
- `BACKUP_PLAIN_TRACEBACK=1`：TUI 异常时输出朴素 traceback。
- `BACKUP_GDRIVE_CLIENT_SECRET`：Google OAuth 客户端密钥 JSON 路径。
- `BACKUP_GDRIVE_TOKEN_CACHE`：Google OAuth token 缓存路径。
- `BACKUP_GDRIVE_SERVICE_ACCOUNT_JSON`：Service Account JSON 路径（可选）。

## 常用命令

```bash
# 初始化（可选；多数命令会在备份目录不存在时自动初始化）
uv run backup init

# 状态
uv run backup status

# Discover
uv run backup discover github --limit 50
uv run backup discover google-drive --limit 50

# 选择单元
uv run backup select add github/owner/repo
uv run backup select add gdrive/folder/<folder_id>

# 执行备份/校验
uv run backup run
uv run backup verify

# 立即切换 payload 加密状态（会直接改 metadata + payload）
uv run backup select encrypt <unit_id>
uv run backup select decrypt <unit_id>

# 启动 TUI
uv run backup tui
```

## TUI 快捷键（核心）

- `/` 搜索框
- `Space` 选中/取消
- `a` 全选可见项
- `n` 取消可见项
- `b` backup
- `e` 立即加密
- `d` 立即解密
- `f` discover + 批量 add
- `m` 手动 add
- `x` remove（从 selected 移除）
- `v` toggle exclude
- `p` 验证当前口令（不落盘解密）
- `Ctrl+E` 设置或清除口令缓存
- `?` Keys 面板
- `q` 退出
