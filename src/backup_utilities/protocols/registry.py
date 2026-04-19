from __future__ import annotations

from .base import BackupProtocol
from .github import GithubProtocol


class ProtocolRegistry:
    def __init__(self, protocols: list[BackupProtocol]) -> None:
        self._protocols = protocols

    def protocol_by_name(self, name: str) -> BackupProtocol:
        for protocol in self._protocols:
            if protocol.name == name:
                return protocol
        raise ValueError(f"unknown protocol: {name}")

    def protocol_for_unit(self, unit_id: str) -> BackupProtocol:
        for protocol in self._protocols:
            if protocol.can_handle(unit_id):
                return protocol
        raise ValueError(f"no protocol for unit: {unit_id}")


def default_registry() -> ProtocolRegistry:
    return ProtocolRegistry(protocols=[GithubProtocol()])
