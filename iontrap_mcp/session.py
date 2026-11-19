"""Layout session management: named in-memory layouts backed by ElectrodeSet."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from .common import ElectrodeSet


@dataclass
class LayoutSession:
    name: str
    electrodes: ElectrodeSet = field(default_factory=ElectrodeSet)
    source_path: str | None = None
    created: float = field(default_factory=time.time)

    def summary(self) -> dict:
        kinds: dict[str, int] = {}
        for e in self.electrodes.electrodes:
            kinds[e.kind] = kinds.get(e.kind, 0) + 1
        return {
            "name": self.name,
            "source_path": self.source_path,
            "n_electrodes": len(self.electrodes.electrodes),
            "by_kind": kinds,
            "electrodes": self.electrodes.names,
            "meta": self.electrodes.meta,
        }


class SessionManager:
    def __init__(self):
        self.layouts: dict[str, LayoutSession] = {}

    # ----------------------------------------------------------- lifecycle
    def create(self, name: str) -> LayoutSession:
        if name in self.layouts:
            raise ValueError(f"layout {name!r} already exists")
        sess = LayoutSession(name=name)
        self.layouts[name] = sess
        return sess

    def get(self, name: str) -> LayoutSession:
        try:
            return self.layouts[name]
        except KeyError:
            raise KeyError(
                f"no layout {name!r}; open layouts: {sorted(self.layouts)}"
            ) from None

    def close(self, name: str) -> None:
        self.get(name)
        del self.layouts[name]

    def list(self) -> list[dict]:
        return [s.summary() for s in self.layouts.values()]

    # ------------------------------------------------------------------ I/O
    def save_gds(self, name: str, path: str) -> str:
        import gdstk

        sess = self.get(name)
        lib = gdstk.Library(f"{name}_lib", unit=1e-6, precision=1e-9)
        cell = sess.electrodes.to_cell(lib, "TOP")
        lib.write_gds(path)
        return str(Path(path).resolve())

    def open_gds(self, path: str, name: str | None = None) -> LayoutSession:
        import gdstk

        lib = gdstk.read_gds(path)
        cells = lib.top_level()
        if not cells:
            raise ValueError(f"{path}: no top-level cells")
        es = ElectrodeSet.from_cell(cells[0])
        name = name or Path(path).stem
        if name in self.layouts:
            raise ValueError(f"layout {name!r} already exists; pass another name")
        sess = LayoutSession(name=name, electrodes=es, source_path=str(path))
        self.layouts[name] = sess
        return sess

    def save_json(self, name: str, path: str) -> str:
        self.get(name).electrodes.to_json(path)
        return str(Path(path).resolve())

    def open_json(self, path: str, name: str | None = None) -> LayoutSession:
        es = ElectrodeSet.from_json(path)
        name = name or Path(path).stem
        if name in self.layouts:
            raise ValueError(f"layout {name!r} already exists; pass another name")
        sess = LayoutSession(name=name, electrodes=es, source_path=str(path))
        self.layouts[name] = sess
        return sess
