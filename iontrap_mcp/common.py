"""Shared electrode data model for IonTrapClaw.

This module is the contract between the geometry generators
(``iontrap_mcp.electrodes``) and the field solvers
(``iontrap_mcp.fields``).  Everything is in micrometres unless noted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np

# Layer assignments (GDS layer, datatype)
LAYER_DC = (1, 0)
LAYER_RF = (2, 0)
LAYER_GROUND = (3, 0)
LAYER_TEXT = (10, 0)

_KIND_LAYER = {"dc": LAYER_DC, "rf": LAYER_RF, "ground": LAYER_GROUND}


@dataclass
class Electrode:
    """A named planar electrode made of one or more polygons.

    Attributes
    ----------
    name:
        Unique electrode name, e.g. ``"DC3"`` or ``"RF_L"``.
    polygons:
        List of (N, 2) arrays of x/y vertices in micrometres.
    kind:
        ``"dc"``, ``"rf"`` or ``"ground"``.
    layer:
        (gds_layer, gds_datatype).
    """

    name: str
    polygons: list[np.ndarray]
    kind: str = "dc"
    layer: tuple[int, int] | None = None

    def __post_init__(self):
        self.polygons = [np.asarray(p, dtype=float).reshape(-1, 2) for p in self.polygons]
        if self.layer is None:
            self.layer = _KIND_LAYER.get(self.kind, LAYER_DC)


@dataclass
class ElectrodeSet:
    """An ordered collection of electrodes plus optional metadata."""

    electrodes: list[Electrode] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    # ------------------------------------------------------------- accessors
    @property
    def names(self) -> list[str]:
        return [e.name for e in self.electrodes]

    def by_name(self, name: str) -> Electrode:
        for e in self.electrodes:
            if e.name == name:
                return e
        raise KeyError(f"no electrode named {name!r}; have {self.names}")

    def by_kind(self, kind: str) -> list[Electrode]:
        return [e for e in self.electrodes if e.kind == kind]

    # ------------------------------------------------------------------ gdstk
    def to_cell(self, lib, cell_name: str = "TOP"):
        """Create a gdstk cell containing all electrodes."""
        import gdstk

        cell = lib.new_cell(cell_name)
        for e in self.electrodes:
            for poly in e.polygons:
                cell.add(gdstk.Polygon(poly, layer=e.layer[0], datatype=e.layer[1]))
            # label at centroid of first polygon
            c = e.polygons[0].mean(axis=0)
            cell.add(
                gdstk.Label(
                    e.name, tuple(c), layer=LAYER_TEXT[0], texttype=LAYER_TEXT[1]
                )
            )
        return cell

    @classmethod
    def from_cell(cls, cell) -> "ElectrodeSet":
        """Rebuild an ElectrodeSet from a cell written by :meth:`to_cell`.

        Polygons are grouped by the nearest label on the text layer; polygons
        without a label fall back to ``EL<layer>_<i>``.
        """
        es = cls()
        labels = [
            (lab.text, np.array(lab.origin, dtype=float))
            for lab in getattr(cell, "labels", [])
        ]
        buckets: dict[str, list[np.ndarray]] = {}
        kinds: dict[str, str] = {}
        for i, poly in enumerate(cell.polygons):
            pts = np.asarray(poly.points, dtype=float)
            centroid = pts.mean(axis=0)
            if labels:
                d = [np.hypot(*(centroid - pos)) for _, pos in labels]
                name = labels[int(np.argmin(d))][0]
            else:
                name = f"EL{poly.layer}_{i}"
            layer = (poly.layer, poly.datatype)
            kind = {LAYER_DC: "dc", LAYER_RF: "rf", LAYER_GROUND: "ground"}.get(
                layer, "dc"
            )
            buckets.setdefault(name, []).append(pts)
            kinds[name] = kind
        for name, polys in buckets.items():
            es.electrodes.append(
                Electrode(name=name, polygons=polys, kind=kinds[name])
            )
        return es

    # ------------------------------------------------------------------ json
    def to_json(self, path: str | Path):
        data = {
            "meta": self.meta,
            "electrodes": [
                {
                    "name": e.name,
                    "kind": e.kind,
                    "layer": list(e.layer),
                    "polygons": [p.tolist() for p in e.polygons],
                }
                for e in self.electrodes
            ],
        }
        Path(path).write_text(json.dumps(data, indent=2))

    @classmethod
    def from_json(cls, path: str | Path) -> "ElectrodeSet":
        data = json.loads(Path(path).read_text())
        es = cls(meta=data.get("meta", {}))
        for ed in data["electrodes"]:
            es.electrodes.append(
                Electrode(
                    name=ed["name"],
                    kind=ed.get("kind", "dc"),
                    layer=tuple(ed.get("layer", _KIND_LAYER.get(ed.get("kind", "dc"), LAYER_DC))),
                    polygons=[np.array(p, dtype=float) for p in ed["polygons"]],
                )
            )
        return es
