from __future__ import annotations

import asyncio
from pathlib import Path

from backup_utilities.config import Config, write_config
from backup_utilities.layout import init_root
from backup_utilities.ui_textual.app import BackupTextualApp


def _make_root(tmp_path: Path) -> Path:
    root = tmp_path / "backup-root"
    init_root(root)
    write_config(
        root,
        Config(
            unit_include=["github/quark/demo"],
        ),
    )
    return root


def test_search_enter_moves_focus_to_table(tmp_path: Path) -> None:
    async def _run() -> None:
        app = BackupTextualApp(_make_root(tmp_path))

        async with app.run_test() as pilot:
            app.action_focus_search()
            await pilot.pause()

            await pilot.press("enter")
            await pilot.pause()

            assert app.query_one("#units_table").has_focus

    asyncio.run(_run())


def test_search_escape_clears_text_before_switching_focus(tmp_path: Path) -> None:
    async def _run() -> None:
        app = BackupTextualApp(_make_root(tmp_path))

        async with app.run_test() as pilot:
            search = app.query_one("#search")
            app.action_focus_search()
            search.value = "demo"
            await pilot.pause()

            await pilot.press("escape")
            await pilot.pause()

            assert search.has_focus
            assert search.value == ""

            await pilot.press("escape")
            await pilot.pause()

            assert app.query_one("#units_table").has_focus

    asyncio.run(_run())


def test_search_escape_switches_focus_when_empty(tmp_path: Path) -> None:
    async def _run() -> None:
        app = BackupTextualApp(_make_root(tmp_path))

        async with app.run_test() as pilot:
            app.action_focus_search()
            await pilot.pause()

            await pilot.press("escape")
            await pilot.pause()

            assert app.query_one("#units_table").has_focus

    asyncio.run(_run())


def test_table_escape_returns_focus_to_search(tmp_path: Path) -> None:
    async def _run() -> None:
        app = BackupTextualApp(_make_root(tmp_path))

        async with app.run_test() as pilot:
            app.action_focus_table()
            await pilot.pause()

            await pilot.press("escape")
            await pilot.pause()

            assert app.query_one("#search").has_focus

    asyncio.run(_run())
