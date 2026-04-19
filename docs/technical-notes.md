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

- 路径：`<BACKUP_ROOT>/logs/YYYY-MM-DD.log`
- 来源标签：`cli` / `tui` / `runner`
