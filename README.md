# backup-utilities

面向个人使用的单元化增量备份工具（Python）。

支持：
- GitHub 仓库（mirror 备份）
- Google Drive 目录
- 本地加密备份（metadata 明文，payload 可加密）
- Textual TUI 日常操作

## 快速开始

```bash
# GitHub 登录（如要备份 GitHub）
gh auth login

# 启动 TUI
uv run backup tui

# 按 f 列举可备份 repo，选择后按 Enter 确认
# 按 b 开始备份，私有 repo 默认使用密码加密
```

默认备份目录是当前工作目录下的 `./backup`。
如需指定其他路径，可设置 `BACKUP_ROOT`。

## Google Drive 首次使用

按官方 quickstart 先完成 OAuth 客户端配置并下载密钥 JSON：  
https://developers.google.com/workspace/drive/api/quickstart/python#set-up-environment

然后将密钥文件放到默认路径：`~/.config/backup-utilities/gdrive_client_secret.json`。

## 文档

- 详细命令与环境变量：[docs/quick-reference.md](docs/quick-reference.md)
- 技术细节与行为说明：[docs/technical-notes.md](docs/technical-notes.md)
