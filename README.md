# backup-utilities

面向个人使用的单元化增量备份工具（Python）。

支持：
- GitHub 仓库（mirror 备份）
- Google Drive 目录
- 本地加密备份（metadata 明文，payload 可加密）
- Textual TUI 日常操作

## 快速开始

```bash
# 1) 安装依赖
uv sync

# 2) 设置备份根目录
export BACKUP_ROOT=~/backup

# 3) 初始化
uv run backup init

# 4) GitHub 登录（如要备份 GitHub）
gh auth login

# 5) 启动 TUI
uv run backup tui
```

建议先在 TUI 里按 `f` 做 discover，再批量 add 并执行 backup。

## Google Drive 首次使用

按官方 quickstart 先完成 OAuth 客户端配置并下载密钥 JSON：  
https://developers.google.com/workspace/drive/api/quickstart/python#set-up-environment

然后将密钥文件放到默认路径，或设置环境变量 `BACKUP_GDRIVE_CLIENT_SECRET`。

## 文档

- 详细命令与环境变量：[`docs/quick-reference.md`](/home/quark/src/backup-utilities/docs/quick-reference.md)
- 技术细节与行为说明：[`docs/technical-notes.md`](/home/quark/src/backup-utilities/docs/technical-notes.md)
