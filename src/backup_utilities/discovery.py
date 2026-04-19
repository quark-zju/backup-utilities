from __future__ import annotations

from .protocols import ProtocolRegistry
from .protocols.base import DiscoveredUnit


def discover_units(
    registry: ProtocolRegistry,
    protocol_name: str,
    *,
    user: str | None = None,
    limit: int | None = None,
) -> list[DiscoveredUnit]:
    protocol = registry.protocol_by_name(protocol_name)
    kwargs: dict[str, object] = {}
    if user:
        kwargs["user"] = user
    if limit is not None:
        kwargs["limit"] = limit
    return protocol.discover(**kwargs)


def format_discovered(units: list[DiscoveredUnit]) -> list[str]:
    lines: list[str] = []
    for item in units:
        lines.append(
            "\t".join(
                [
                    item.unit_id,
                    f"default_selected={item.default_selected}",
                    f"default_encrypt={item.default_encrypt}",
                    f"details={item.details}",
                ]
            )
        )
    return lines
