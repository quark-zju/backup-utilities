from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any
from typing import TYPE_CHECKING

from .base import BackupProtocol, DiscoveredUnit, ExportResult, FingerprintResult

if TYPE_CHECKING:
    from ..config import Config

_FOLDER_MIME = "application/vnd.google-apps.folder"
_SHORTCUT_MIME = "application/vnd.google-apps.shortcut"
_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
_GOOGLE_EXPORT_MIME: dict[str, tuple[str, str]] = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pptx",
    ),
    "application/vnd.google-apps.drawing": ("image/png", ".png"),
    "application/vnd.google-apps.script": (
        "application/vnd.google-apps.script+json",
        ".json",
    ),
}


def _sanitize_name(name: str) -> str:
    cleaned = re.sub(r"[\\/\x00-\x1f]", "_", name).strip()
    return cleaned or "unnamed"


def _resolve_token_cache_path() -> Path:
    raw = os.environ.get("BACKUP_GDRIVE_TOKEN_CACHE")
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".cache" / "backup-utilities" / "gdrive_token.json").resolve()


def _resolve_oauth_client_secret_path() -> Path:
    raw = os.environ.get("BACKUP_GDRIVE_CLIENT_SECRET")
    if raw:
        return Path(raw).expanduser().resolve()
    return (
        Path.home() / ".config" / "backup-utilities" / "gdrive_client_secret.json"
    ).resolve()


def _build_drive_service():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except Exception as exc:
        raise RuntimeError(
            "google drive dependencies missing; install google-api-python-client and google-auth-oauthlib"
        ) from exc

    service_account_path = os.environ.get("BACKUP_GDRIVE_SERVICE_ACCOUNT_JSON")
    if service_account_path:
        sa_path = Path(service_account_path).expanduser().resolve()
        if not sa_path.exists():
            raise FileNotFoundError(
                f"service account json not found: {sa_path} (from BACKUP_GDRIVE_SERVICE_ACCOUNT_JSON)"
            )
        creds = service_account.Credentials.from_service_account_file(
            str(sa_path), scopes=_SCOPES
        )
        return build("drive", "v3", credentials=creds, cache_discovery=False)

    token_path = _resolve_token_cache_path()
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), _SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            secret_path = _resolve_oauth_client_secret_path()
            if not secret_path.exists():
                raise FileNotFoundError(
                    "oauth client secret not found; set BACKUP_GDRIVE_CLIENT_SECRET "
                    f"or create {secret_path}"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), _SCOPES)
            creds = flow.run_local_server(port=0)

        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return build("drive", "v3", credentials=creds, cache_discovery=False)


@dataclass(slots=True)
class _Node:
    file_id: str
    name: str
    mime_type: str
    modified_time: str | None
    size: str | None
    md5: str | None
    parents: list[str]
    shortcut_target_id: str | None

    @property
    def is_folder(self) -> bool:
        return self.mime_type == _FOLDER_MIME

    @property
    def is_shortcut(self) -> bool:
        return self.mime_type == _SHORTCUT_MIME

    @property
    def is_google_workspace_doc(self) -> bool:
        return self.mime_type.startswith("application/vnd.google-apps.")


class GoogleDriveProtocol(BackupProtocol):
    name = "google-drive"

    def can_handle(self, unit_id: str) -> bool:
        return unit_id.startswith("gdrive/")

    def should_encrypt_auto(
        self, *, protocol_metadata: dict[str, object], cfg: Config
    ) -> bool | None:
        # Google Drive data defaults to encrypted payloads under auto policy.
        return True

    def discover(self, **kwargs: object) -> list[DiscoveredUnit]:
        limit = int(kwargs.get("limit", 1000))
        service = _build_drive_service()
        query = f"mimeType='{_FOLDER_MIME}' and 'root' in parents and trashed=false"
        fields = "nextPageToken, files(id,name,modifiedTime,shared)"
        files = self._list_files_paginated(
            service,
            query=query,
            fields=fields,
            page_size=min(limit, 1000),
            limit=limit,
        )
        out: list[DiscoveredUnit] = []
        for item in files:
            folder_id = str(item["id"])
            folder_name = str(item.get("name", folder_id))
            out.append(
                DiscoveredUnit(
                    unit_id=f"gdrive/folder/{folder_id}",
                    default_selected=True,
                    default_encrypt=True,
                    details={
                        "name": folder_name,
                        "modified_time": item.get("modifiedTime"),
                        "shared": bool(item.get("shared", False)),
                    },
                )
            )
        return out

    def compute_fingerprint(self, unit_id: str) -> FingerprintResult:
        folder_id = self._parse_unit_id(unit_id)
        service = _build_drive_service()
        root = self._get_node(service, folder_id)
        if not root.is_folder:
            raise ValueError(f"unit is not a folder: {unit_id}")

        nodes = self._collect_subtree(service, folder_id)
        digest = sha256()
        for node in sorted(nodes, key=lambda x: x.file_id):
            digest.update(node.file_id.encode("utf-8"))
            digest.update(b"\t")
            digest.update(node.mime_type.encode("utf-8"))
            digest.update(b"\t")
            digest.update((node.modified_time or "").encode("utf-8"))
            digest.update(b"\t")
            digest.update((node.size or "").encode("utf-8"))
            digest.update(b"\t")
            digest.update((node.md5 or "").encode("utf-8"))
            digest.update(b"\n")

        return FingerprintResult(
            fingerprint=digest.hexdigest(),
            protocol_metadata={
                "folder_id": folder_id,
                "folder_name": root.name,
                "item_count": len(nodes),
                "modified_time": root.modified_time,
            },
        )

    def export_snapshot(
        self,
        unit_id: str,
        staging_dir: Path,
        previous_snapshot_dir: Path | None = None,
        logger=None,
    ) -> ExportResult:
        folder_id = self._parse_unit_id(unit_id)
        service = _build_drive_service()
        root = self._get_node(service, folder_id)
        if not root.is_folder:
            raise ValueError(f"unit is not a folder: {unit_id}")

        nodes = self._collect_subtree(service, folder_id)

        root_dir = staging_dir / _sanitize_name(root.name)
        root_dir.mkdir(parents=True, exist_ok=True)
        local_paths: dict[str, Path] = {folder_id: root_dir}
        used_names: dict[Path, set[str]] = {root_dir: set()}

        folders = sorted(
            [node for node in nodes if node.is_folder and node.file_id != folder_id],
            key=lambda n: n.file_id,
        )
        files = sorted(
            [node for node in nodes if not node.is_folder], key=lambda n: n.file_id
        )

        for node in folders:
            parent_dir = self._find_parent_path(node.parents, local_paths)
            if parent_dir is None:
                continue
            folder_path = parent_dir / self._unique_name(
                parent_dir, _sanitize_name(node.name), used_names
            )
            folder_path.mkdir(parents=True, exist_ok=True)
            local_paths[node.file_id] = folder_path
            used_names.setdefault(folder_path, set())

        manifest: list[dict[str, Any]] = []
        for node in files:
            parent_dir = self._find_parent_path(node.parents, local_paths)
            if parent_dir is None:
                continue
            filename = self._unique_name(
                parent_dir,
                _sanitize_name(node.name),
                used_names,
            )
            destination = parent_dir / filename

            entry: dict[str, Any] = {
                "id": node.file_id,
                "name": node.name,
                "mime_type": node.mime_type,
                "path": str(destination.relative_to(staging_dir)),
            }
            if node.is_shortcut:
                shortcut_text = {
                    "type": "shortcut",
                    "target_id": node.shortcut_target_id,
                }
                destination = destination.with_suffix(
                    destination.suffix + ".shortcut.json"
                )
                destination.write_text(
                    json.dumps(
                        shortcut_text, ensure_ascii=True, sort_keys=True, indent=2
                    )
                    + "\n",
                    encoding="utf-8",
                )
                entry["path"] = str(destination.relative_to(staging_dir))
                entry["export"] = "shortcut-json"
            elif node.is_google_workspace_doc:
                export_spec = _GOOGLE_EXPORT_MIME.get(node.mime_type)
                if export_spec is None:
                    destination = destination.with_suffix(
                        destination.suffix + ".gdoc.json"
                    )
                    payload = {
                        "type": "unsupported-google-workspace-doc",
                        "mime_type": node.mime_type,
                        "file_id": node.file_id,
                    }
                    destination.write_text(
                        json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2)
                        + "\n",
                        encoding="utf-8",
                    )
                    entry["path"] = str(destination.relative_to(staging_dir))
                    entry["export"] = "placeholder-json"
                else:
                    mime_type, suffix = export_spec
                    if not destination.name.endswith(suffix):
                        destination = destination.with_name(destination.name + suffix)
                    self._download_export(service, node.file_id, mime_type, destination)
                    entry["path"] = str(destination.relative_to(staging_dir))
                    entry["export"] = mime_type
            else:
                self._download_media(service, node.file_id, destination)
                entry["export"] = "media"

            manifest.append(entry)

        manifest_path = staging_dir / "_gdrive_manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "unit_id": unit_id,
                    "root_folder_id": folder_id,
                    "root_folder_name": root.name,
                    "items": manifest,
                },
                ensure_ascii=True,
                sort_keys=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return ExportResult(source_path=staging_dir)

    @staticmethod
    def _parse_unit_id(unit_id: str) -> str:
        chunks = unit_id.split("/")
        if len(chunks) != 3 or chunks[0] != "gdrive" or chunks[1] != "folder":
            raise ValueError(f"invalid google drive unit_id: {unit_id}")
        folder_id = chunks[2].strip()
        if not folder_id:
            raise ValueError(f"invalid google drive unit_id: {unit_id}")
        return folder_id

    @staticmethod
    def _list_files_paginated(
        service,
        *,
        query: str,
        fields: str,
        page_size: int,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            response = (
                service.files()
                .list(
                    q=query,
                    fields=fields,
                    pageSize=page_size,
                    pageToken=page_token,
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                )
                .execute()
            )
            files = response.get("files", [])
            if isinstance(files, list):
                out.extend([x for x in files if isinstance(x, dict)])
            if limit is not None and len(out) >= limit:
                return out[:limit]
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return out

    @staticmethod
    def _get_node(service, file_id: str) -> _Node:
        raw = (
            service.files()
            .get(
                fileId=file_id,
                fields=(
                    "id,name,mimeType,modifiedTime,size,md5Checksum,parents,"
                    "shortcutDetails(targetId)"
                ),
                supportsAllDrives=True,
            )
            .execute()
        )
        return _Node(
            file_id=str(raw["id"]),
            name=str(raw.get("name", raw["id"])),
            mime_type=str(raw.get("mimeType", "")),
            modified_time=str(raw.get("modifiedTime"))
            if raw.get("modifiedTime")
            else None,
            size=str(raw.get("size")) if raw.get("size") else None,
            md5=str(raw.get("md5Checksum")) if raw.get("md5Checksum") else None,
            parents=[str(x) for x in raw.get("parents", []) if isinstance(x, str)],
            shortcut_target_id=(
                str(raw["shortcutDetails"]["targetId"])
                if isinstance(raw.get("shortcutDetails"), dict)
                and raw["shortcutDetails"].get("targetId")
                else None
            ),
        )

    def _collect_subtree(self, service, folder_id: str) -> list[_Node]:
        root = self._get_node(service, folder_id)
        out: list[_Node] = [root]
        seen = {root.file_id}
        queue = [folder_id]
        while queue:
            current_parent = queue.pop(0)
            children = self._list_files_paginated(
                service,
                query=f"'{current_parent}' in parents and trashed=false",
                fields=(
                    "nextPageToken, files(id,name,mimeType,modifiedTime,size,md5Checksum,parents,"
                    "shortcutDetails(targetId))"
                ),
                page_size=1000,
            )
            for raw in children:
                node = _Node(
                    file_id=str(raw["id"]),
                    name=str(raw.get("name", raw["id"])),
                    mime_type=str(raw.get("mimeType", "")),
                    modified_time=(
                        str(raw.get("modifiedTime"))
                        if raw.get("modifiedTime")
                        else None
                    ),
                    size=str(raw.get("size")) if raw.get("size") else None,
                    md5=str(raw.get("md5Checksum")) if raw.get("md5Checksum") else None,
                    parents=[
                        str(x) for x in raw.get("parents", []) if isinstance(x, str)
                    ],
                    shortcut_target_id=(
                        str(raw["shortcutDetails"]["targetId"])
                        if isinstance(raw.get("shortcutDetails"), dict)
                        and raw["shortcutDetails"].get("targetId")
                        else None
                    ),
                )
                if node.file_id in seen:
                    continue
                seen.add(node.file_id)
                out.append(node)
                if node.is_folder:
                    queue.append(node.file_id)
        return out

    @staticmethod
    def _find_parent_path(parents: list[str], known: dict[str, Path]) -> Path | None:
        for parent_id in parents:
            if parent_id in known:
                return known[parent_id]
        return None

    @staticmethod
    def _unique_name(
        parent_dir: Path, name: str, used_names: dict[Path, set[str]]
    ) -> str:
        used = used_names.setdefault(parent_dir, set())
        candidate = name
        idx = 1
        while candidate in used:
            candidate = f"{name} ({idx})"
            idx += 1
        used.add(candidate)
        return candidate

    @staticmethod
    def _download_media(service, file_id: str, destination: Path) -> None:
        from googleapiclient.http import MediaIoBaseDownload

        destination.parent.mkdir(parents=True, exist_ok=True)
        request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
        with destination.open("wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

    @staticmethod
    def _download_export(
        service, file_id: str, mime_type: str, destination: Path
    ) -> None:
        from googleapiclient.http import MediaIoBaseDownload

        destination.parent.mkdir(parents=True, exist_ok=True)
        request = service.files().export_media(fileId=file_id, mimeType=mime_type)
        with destination.open("wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
