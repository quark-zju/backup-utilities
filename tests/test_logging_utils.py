from __future__ import annotations

from pathlib import Path

from backup_utilities.logging_utils import append_log, daily_log_path


def test_append_log_writes_daily_file_with_source(tmp_path: Path) -> None:
    root = tmp_path / "backup-root"
    path = append_log(root, "tui", "hello log")

    assert path == daily_log_path(root)
    text = path.read_text(encoding="utf-8")
    assert "[tui] hello log" in text
