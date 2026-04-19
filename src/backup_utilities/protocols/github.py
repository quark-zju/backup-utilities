from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from .base import BackupProtocol, DiscoveredUnit, ExportResult, FingerprintResult


@dataclass(slots=True)
class _RepoIdentity:
    owner: str
    repo: str


def _run(cmd: list[str]) -> str:
    res = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{res.stderr.strip()}")
    return res.stdout


class GithubProtocol(BackupProtocol):
    name = "github"

    def can_handle(self, unit_id: str) -> bool:
        return unit_id.startswith("github/")

    def discover(self, **kwargs: object) -> list[DiscoveredUnit]:
        user = str(kwargs.get("user", ""))
        limit = int(kwargs.get("limit", 1000))
        if not user:
            raise ValueError("discover github needs --user")

        out = _run(
            [
                "gh",
                "repo",
                "list",
                user,
                "--limit",
                str(limit),
                "--json",
                "nameWithOwner,isFork,visibility,pushedAt",
            ]
        )
        raw = json.loads(out)
        units: list[DiscoveredUnit] = []
        for item in raw:
            name_with_owner = str(item["nameWithOwner"])
            owner, repo = name_with_owner.split("/", maxsplit=1)
            is_fork = bool(item.get("isFork", False))
            visibility = str(item.get("visibility", "UNKNOWN"))
            units.append(
                DiscoveredUnit(
                    unit_id=f"github/{owner}/{repo}",
                    default_selected=not is_fork,
                    default_encrypt=visibility.upper() == "PRIVATE",
                    details={
                        "fork": is_fork,
                        "visibility": visibility,
                        "pushed_at": item.get("pushedAt"),
                    },
                )
            )
        return units

    def compute_fingerprint(self, unit_id: str) -> FingerprintResult:
        ident = self._parse_unit_id(unit_id)
        refs_lines = _run(
            [
                "gh",
                "api",
                "--paginate",
                f"repos/{ident.owner}/{ident.repo}/git/refs",
                "--jq",
                ".[] | [.ref, .object.sha] | @tsv",
            ]
        )

        refs: dict[str, str] = {}
        for line in refs_lines.splitlines():
            if not line.strip():
                continue
            ref, oid = line.split("\t", maxsplit=1)
            refs[ref] = oid

        digest = sha256()
        for ref in sorted(refs):
            digest.update(ref.encode("utf-8"))
            digest.update(b"\t")
            digest.update(refs[ref].encode("utf-8"))
            digest.update(b"\n")

        repo_meta_out = _run(
            [
                "gh",
                "api",
                f"repos/{ident.owner}/{ident.repo}",
                "--jq",
                "{pushed_at: .pushed_at, default_branch: .default_branch, private: .private}",
            ]
        )
        repo_meta = json.loads(repo_meta_out)

        return FingerprintResult(
            fingerprint=digest.hexdigest(),
            protocol_metadata={
                "repo": f"{ident.owner}/{ident.repo}",
                "default_branch": repo_meta.get("default_branch"),
                "pushed_at": repo_meta.get("pushed_at"),
                "private": bool(repo_meta.get("private", False)),
                "refs": refs,
            },
        )

    def export_snapshot(self, unit_id: str, staging_dir: Path) -> ExportResult:
        ident = self._parse_unit_id(unit_id)
        clone_target = staging_dir / f"{ident.repo}.git"
        _run(
            [
                "gh",
                "repo",
                "clone",
                f"{ident.owner}/{ident.repo}",
                str(clone_target),
                "--",
                "--mirror",
            ]
        )
        return ExportResult(source_path=clone_target)

    @staticmethod
    def _parse_unit_id(unit_id: str) -> _RepoIdentity:
        chunks = unit_id.split("/")
        if len(chunks) != 3 or chunks[0] != "github":
            raise ValueError(f"invalid github unit_id: {unit_id}")
        return _RepoIdentity(owner=chunks[1], repo=chunks[2])
