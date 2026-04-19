from __future__ import annotations

from pathlib import Path

from .config import load_config
from .protocols import ProtocolRegistry
from .protocols.base import DiscoveredUnit
from .storage import metadata_path, read_json, write_json_atomic


def _known_unit_ids(root: Path) -> set[str]:
    known: set[str] = set()
    try:
        cfg = load_config(root)
    except FileNotFoundError:
        cfg = None
    if cfg is not None:
        known.update(cfg.unit_include)
        known.update(cfg.unit_exclude)

    units_root = root / "units"
    if units_root.exists():
        for meta_path in units_root.rglob("metadata.json"):
            rel = meta_path.parent.relative_to(units_root)
            known.add(rel.as_posix())
    return known


def discover_units(
    registry: ProtocolRegistry,
    protocol_name: str,
    *,
    root: Path | None = None,
    user: str | None = None,
    limit: int | None = None,
) -> list[DiscoveredUnit]:
    protocol = registry.protocol_by_name(protocol_name)
    kwargs: dict[str, object] = {}
    if user:
        kwargs["user"] = user
    if limit is not None:
        kwargs["limit"] = limit
    discovered = protocol.discover(**kwargs)
    if root is None:
        return discovered
    known = _known_unit_ids(root)
    return [item for item in discovered if item.unit_id not in known]


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


def write_partial_metadata_from_discovered(
    *,
    root: Path,
    protocol_name: str,
    discovered: list[DiscoveredUnit],
    chosen_unit_ids: list[str],
) -> None:
    by_id = {item.unit_id: item for item in discovered}
    for unit_id in chosen_unit_ids:
        item = by_id.get(unit_id)
        if item is None:
            continue

        path = metadata_path(root, unit_id)
        meta = read_json(path) if path.exists() else {}
        payload = meta.get("payload")
        if isinstance(payload, dict) and isinstance(payload.get("encrypted"), bool):
            # Existing full metadata already has effective encryption state.
            continue

        meta["unit_id"] = unit_id
        meta["protocol"] = protocol_name
        meta["protocol_metadata"] = dict(item.details)
        meta["meta_state"] = "partial"
        write_json_atomic(path, meta)
