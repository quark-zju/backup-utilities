from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from typing import TYPE_CHECKING

from .base import BackupProtocol, DiscoveredUnit, ExportResult, FingerprintResult

if TYPE_CHECKING:
    from ..config import Config


@dataclass(slots=True)
class _RepoIdentity:
    owner: str
    repo: str


def _run(cmd: list[str]) -> str:
    res = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{res.stderr.strip()}")
    return res.stdout


def _infer_authenticated_user() -> str:
    try:
        login = _run(["gh", "api", "user", "--jq", ".login"]).strip()
        if login:
            return login
    except Exception:
        pass

    res = subprocess.run(
        ["gh", "auth", "status"], check=False, capture_output=True, text=True
    )
    text = "\n".join([res.stdout, res.stderr])
    match = re.search(r"Logged in to github\\.com account\\s+([^\\s]+)", text)
    if match:
        return match.group(1)

    raise ValueError(
        "cannot infer GitHub user from gh auth state; pass --user or run gh auth login"
    )


class GithubProtocol(BackupProtocol):
    name = "github"

    def can_handle(self, unit_id: str) -> bool:
        return unit_id.startswith("github/")

    def should_encrypt_auto(
        self, *, protocol_metadata: dict[str, object], cfg: Config
    ) -> bool | None:
        if (
            bool(protocol_metadata.get("private", False))
            and cfg.github_default_private_encrypt
        ):
            return True
        return None

    def discover(self, **kwargs: object) -> list[DiscoveredUnit]:
        user_value = kwargs.get("user")
        user = str(user_value) if user_value else ""
        limit = int(kwargs.get("limit", 1000))
        if not user:
            user = _infer_authenticated_user()

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
            is_private = visibility.upper() == "PRIVATE"
            units.append(
                DiscoveredUnit(
                    unit_id=f"github/{owner}/{repo}",
                    default_selected=not is_fork,
                    default_encrypt=is_private,
                    details={
                        "fork": is_fork,
                        "visibility": visibility,
                        "private": is_private,
                        "pushed_at": item.get("pushedAt"),
                    },
                )
            )
        return units

    def compute_fingerprint(self, unit_id: str) -> FingerprintResult:
        ident = self._parse_unit_id(unit_id)
        empty_repo = False
        try:
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
        except RuntimeError as exc:
            message = str(exc)
            if "Git Repository is empty" in message and "HTTP 409" in message:
                refs_lines = ""
                empty_repo = True
            else:
                raise

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
                "empty_repo": empty_repo,
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
