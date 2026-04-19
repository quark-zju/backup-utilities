# TUI Textual 重构计划（草案）

## 1. 背景与目标

当前 `whiptail` 版本适合简单流程，但在以下方面受限：
- 多区域实时刷新（搜索框 + 列表 + 状态栏）
- 复杂选择语义（过滤后隐藏项仍保持选中）
- 键盘快捷键与批量操作反馈
- 后台任务执行时的 UI 连续可用性

目标：基于 `textual` 实现一个可维护、可扩展的主力 TUI，保留现有 CLI 作为稳定底座。

---

## 2. 产品范围（MVP）

MVP 功能：
- 搜索框：按 `unit_id` 子串过滤列表
- 列表（table）：显示
  - `Unit ID`
  - `Encrypt Policy`（auto/forced-encrypt/forced-decrypt）
  - `Last Snapshot Time`
  - `Payload Size`
  - `Last Verify Time`（先支持无值）
- 选择语义：
  - 可逐条选择
  - 全选可见项 / 全不选可见项
  - 过滤条件变化后，隐藏项仍保留原选择状态
  - 显示提示：例如 `selected 12 (visible 5, hidden 7)`
- 批量操作（针对 selected）：
  - `Backup`
  - `Encrypt`（已 forced-encrypt 跳过）
  - `Decrypt`（已 forced-decrypt 跳过）
  - `Remove`（需确认）
- 全局操作：
  - `Add unit manually`
  - `Discover units`（先支持 github）

非 MVP（后续）：
- 多条件过滤（协议、加密状态、更新时间范围）
- 列排序/自定义列
- 多任务并发调度面板

---

## 3. 交互信息架构

主界面分区建议：
1. 顶部：搜索框 + 快捷键提示
2. 中部：Unit table（支持光标移动/多选）
3. 底部：状态栏（总数、可见数、选中数、隐藏选中数）
4. 右下/底部弹层：操作结果和错误提示

关键提示文案：
- 当过滤导致有隐藏选中项：
  - `当前已选 12 项，其中 7 项未显示（受过滤条件影响）`

---

## 4. 快捷键草案

建议默认快捷键：
- `/`：聚焦搜索框
- `j` / `k` 或 `Down` / `Up`：移动列表焦点
- `Space`：切换当前行选中
- `a`：全选可见项
- `n`：全不选可见项
- `b`：对已选执行 backup
- `e`：对已选执行 encrypt
- `d`：对已选执行 decrypt
- `x`：对已选执行 remove（弹确认）
- `m`：手动添加 unit
- `f`：discover 并批量添加
- `r`：刷新列表
- `q`：退出

说明：快捷键最终以 `textual` 绑定为准，可在实现阶段提供可配置化入口。

---

## 5. 状态模型（核心）

建议集中状态（单一数据源）：
- `all_units: dict[unit_id, UnitRow]`
- `query: str`
- `visible_ids: list[str]`
- `selected_ids: set[str]`
- `focused_id: str | None`
- `running_jobs: dict[job_id, JobState]`

派生状态：
- `selected_visible_count`
- `selected_hidden_count = len(selected_ids - set(visible_ids))`

选择语义规则：
- 过滤变化只影响 `visible_ids`，不修改 `selected_ids`
- `全选/全不选` 仅作用于 `visible_ids`

---

## 6. 架构与模块拆分建议

目录建议（新增）：
- `src/backup_utilities/ui_textual/`
  - `app.py`：Textual App 入口
  - `state.py`：状态与派生逻辑
  - `actions.py`：批量动作编排（调用现有 core）
  - `widgets/`
    - `search_bar.py`
    - `unit_table.py`
    - `status_bar.py`
    - `dialogs.py`

边界原则：
- UI 层只做展示与事件分发
- 核心业务复用已有模块（`runner/config/selectors/discovery/...`）
- 避免在 UI 层直接拼 shell 命令

---

## 7. 依赖决策

建议引入依赖：
- `textual`（主 TUI 框架）

理由：
- 当前交互需求（搜索 + 表格 + 多选 + 快捷键 + 状态提示）与 Textual 能力高度匹配
- 长期维护成本低于继续叠加 `whiptail`

兼容策略：
- 短期保留 `whiptail` 版 `backup tui`（例如改名为 `backup tui-legacy`）
- 新版入口可暂命名 `backup tui2` 或直接替换 `backup tui`（待确认）

---

## 8. 实施阶段计划

Phase A：基础框架
- 接入 `textual` 依赖
- App 框架 + 空表格 + 状态栏 + 快捷键骨架

Phase B：列表与选择
- 加载 units
- 搜索过滤
- 持久选择语义（含隐藏选中提示）

Phase C：批量动作
- backup/encrypt/decrypt/remove
- 结果统计与错误反馈

Phase D：新增单元
- 手动添加
- discover + 批量添加

Phase E：收尾
- 文档、快捷键帮助、异常提示统一
- 决定 legacy 入口保留策略

---

## 9. 测试计划

手工场景：
- 空列表、少量列表、大量列表（>500）
- 过滤前后选择保持
- 批量动作跳过逻辑正确（encrypt/decrypt）
- remove 二次确认
- discover 失败/超时错误提示

自动化建议：
- `state.py` 的纯逻辑单元测试（过滤、选择、派生统计）
- `actions.py` 的业务调用测试（mock core）

---

## 10. 待确认决策（请你拍板）

1. 命令入口策略：
- A. `backup tui` 直接切换到 Textual（推荐）
- B. 新增 `backup tui2`，旧版保留

2. 列定义（MVP）：
- A. 先用本文 5 列
- B. 增加 `Protocol` 与 `Last Verify Status`

3. remove 语义：
- A. 仅从 selected 中移除（当前语义）
- B. 额外支持删除本地备份文件（高风险，不建议 MVP）

4. 批量 backup 执行模式：
- A. 串行（推荐，先稳）
- B. 并行（更快，但 UI 与错误处理复杂）

5. legacy whiptail：
- A. 过渡期保留 1~2 个版本
- B. 直接移除

---

## 11. 建议默认答案（供快速推进）

- 入口：A（直接切换 `backup tui`）
- 列：A（先 5 列）
- remove：A（仅从 selected 移除）
- backup 执行：A（串行）
- legacy：A（短期保留）

