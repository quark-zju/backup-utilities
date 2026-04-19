from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class DiscoveredUnit:
    unit_id: str
    default_selected: bool
    default_encrypt: bool
    details: dict[str, str | bool | None]


@dataclass(slots=True)
class FingerprintResult:
    fingerprint: str
    protocol_metadata: dict[str, object]


@dataclass(slots=True)
class ExportResult:
    source_path: Path


class BackupProtocol(ABC):
    name: str

    @abstractmethod
    def can_handle(self, unit_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def discover(self, **kwargs: object) -> list[DiscoveredUnit]:
        raise NotImplementedError

    @abstractmethod
    def compute_fingerprint(self, unit_id: str) -> FingerprintResult:
        raise NotImplementedError

    @abstractmethod
    def export_snapshot(self, unit_id: str, staging_dir: Path) -> ExportResult:
        raise NotImplementedError
