from __future__ import annotations

from pathlib import Path

from backup_utilities.protocols.github import GithubProtocol


def test_export_snapshot_clones_when_no_previous_snapshot(
    monkeypatch, tmp_path: Path
) -> None:
    protocol = GithubProtocol()
    recorded: list[list[str]] = []

    def fake_run(cmd: list[str]) -> str:
        recorded.append(cmd)
        return ""

    def fail_run_git(workdir: Path, cmd: list[str], logger=None) -> str:
        raise AssertionError("git commands should not run without previous snapshot")

    monkeypatch.setattr("backup_utilities.protocols.github._run", fake_run)
    monkeypatch.setattr(GithubProtocol, "_run_git", staticmethod(fail_run_git))

    result = protocol.export_snapshot("github/quark/demo", tmp_path)

    assert result.source_path == tmp_path / "demo.git"
    assert recorded == [
        [
            "gh",
            "repo",
            "clone",
            "quark/demo",
            str(tmp_path / "demo.git"),
            "--",
            "--mirror",
        ]
    ]


def test_export_snapshot_fetches_and_repacks_restored_mirror(
    monkeypatch, tmp_path: Path
) -> None:
    protocol = GithubProtocol()
    previous_snapshot_dir = tmp_path / "previous"
    restored_repo = previous_snapshot_dir / "demo.git"
    (restored_repo / "objects").mkdir(parents=True)
    (restored_repo / "config").write_text("[core]\n", encoding="utf-8")

    git_calls: list[tuple[Path, list[str]]] = []
    logged_messages: list[str] = []

    def fail_clone(cmd: list[str]) -> str:
        raise AssertionError(f"clone should not run: {cmd}")

    def fake_run_git(workdir: Path, cmd: list[str], logger=None) -> str:
        git_calls.append((workdir, cmd))
        if logger is not None:
            logger(f"exec cwd={workdir} cmd={' '.join(cmd)}")
        return ""

    monkeypatch.setattr("backup_utilities.protocols.github._run", fail_clone)
    monkeypatch.setattr(GithubProtocol, "_run_git", staticmethod(fake_run_git))

    result = protocol.export_snapshot(
        "github/quark/demo",
        tmp_path,
        previous_snapshot_dir=previous_snapshot_dir,
        logger=logged_messages.append,
    )

    clone_target = tmp_path / "demo.git"
    assert result.source_path == clone_target
    assert clone_target.exists()
    assert not restored_repo.exists()
    assert git_calls == [
        (
            clone_target,
            ["git", "fetch", "--prune", "--tags", "origin", "+refs/*:refs/*"],
        ),
        (
            clone_target,
            ["git", "repack", "-a", "-d", "--write-bitmap-index"],
        ),
    ]
    assert logged_messages == [
        f"exec cwd={clone_target} cmd=git fetch --prune --tags origin +refs/*:refs/*",
        f"exec cwd={clone_target} cmd=git repack -a -d --write-bitmap-index",
    ]
