# Technical Notes

## 备份产物

每个 unit 目录只保留少量文件：
- `metadata.json`
- `payload.tar.zst` 或 `payload.tar.zst.enc`

`payload.path` 使用相对 unit 目录路径（例如 `payload.tar.zst.enc`）。

## 增量策略

- 通过 protocol 指纹比较决定是否变化。
- 指纹相同则跳过备份，不重写 payload。
- `check.last_check_time` 记录最近一次增量检查时间。

## 加密状态

- 单一真实状态：`payload.encrypted`。
- `select encrypt/decrypt` 会立即重写 payload 与 metadata。
- `auto(initial)` 仅在 unit 尚无 payload 状态时参与首次决策。

## 搜索字段

- `mtime`：上次备份时间（`snapshot_time`）。
- `ctime`：上次增量检查时间（缺失时回退到 `snapshot_time`）。

## Google Drive 说明

- 使用 Google 官方 API 客户端（`google-api-python-client` / `google-auth-oauthlib`）。
- unit identity 使用 `gdrive/folder/<folder_id>`（稳定 ID）。
- UI 会显示更易读名称（如 `gdrive/<folder_name> [<folder_id>]`）。

## 日志

- 路径：`<BACKUP_ROOT>/logs/YYYY-MM-DD.log`（默认 `./backup/logs/YYYY-MM-DD.log`）
- 来源标签：`cli` / `tui` / `runner`

## Keyring 密码管理

- 作用域：按配置 `global.uuid` 绑定每个备份根目录的密码存储上下文。
- 系统 keyring 条目键：
  - `service=backup-utilities`
  - `username=<global.uuid>`
- 系统 keyring 中存放的是“加密后的密码密文”，不是明文。
- 本地密钥文件路径：`~/.config/backup-utilities/keyring-keys/<global.uuid>.key`
  - 该文件用于解密 keyring 中密文。
  - 文件权限会尝试收紧到 `0600`（POSIX）。

### 写入与读取策略

- 用户输入密码后（包括 TUI/CLI 口令提示路径），会缓存到内存并尝试写入 keyring。
- 读取顺序：环境变量 `BACKUP_PASSPHRASE` -> 进程内缓存 -> keyring -> 交互式输入。
- 若 keyring 中有密文但本地 `.key` 缺失，读取会返回不可用，不会自动新建 key 覆盖旧关系。
- 若 keyring 读取或解密失败，会回退到交互式输入流程（允许提示时）。

### TUI 行为

- `Ctrl+E`：
  - 当前未加载密码时：弹出一次输入框设置密码，并尝试写入 keyring。
  - 当前已加载密码时：清空内存缓存，并同步尝试删除 keyring 条目。
- 状态栏会显示 `passphrase=loaded|unloaded`。

### 运行时 backend 说明

- `keyring` backend 由运行时环境决定（例如 `SecretService` / `KWallet` / `fail`）。
- `uv run` 与系统 Python 可能使用不同 backend；排查时请在实际运行环境里检查：
  - `python -c "import keyring; print(keyring.get_keyring())"`
  - `uv run python -c "import keyring; print(keyring.get_keyring())"`
