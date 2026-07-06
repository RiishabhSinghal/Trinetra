"""Supply knowledge graph: supplier → corridor → refinery.

A directed NetworkX graph, not a picture. The optimizer traverses it, and
disabling a corridor recomputes feasible routes automatically. Node and edge
attributes carry the economics (freight, transit days, capacities, grades).
"""

from __future__ import annotations

import json
import os

import networkx as nx

from config.settings import DATA_DIR


class SupplyGraph:
    def __init__(self, path: str | None = None):
        with open(path or os.path.join(DATA_DIR, "network.json")) as f:
            self.raw = json.load(f)
        self.g = nx.DiGraph()
        self._build()

    def _build(self) -> None:
        for c in self.raw["corridors"]:
            self.g.add_node(f"corridor:{c['id']}", kind="corridor", enabled=True, **c)
        for s in self.raw["suppliers"]:
            self.g.add_node(f"supplier:{s['id']}", kind="supplier", **s)
            self.g.add_edge(
                f"supplier:{s['id']}",
                f"corridor:{s['corridor']}",
                freight=self.raw["freight_usd_per_bbl"][s["corridor"]],
            )
        for r in self.raw["refineries"]:
            self.g.add_node(f"refinery:{r['id']}", kind="refinery", **r)
            for c in self.raw["corridors"]:
                self.g.add_edge(f"corridor:{c['id']}", f"refinery:{r['id']}",
                                transit_days=c["transit_days_to_india"])

    # ── Scenario hooks ─────────────────────────────────────────────────
    def set_corridor_flow(self, corridor_id: str, flow_factor: float) -> None:
        """1.0 = fully open, 0.0 = closed. Partial closures scale capacity."""
        node = f"corridor:{corridor_id}"
        self.g.nodes[node]["flow_factor"] = max(0.0, min(1.0, flow_factor))
        self.g.nodes[node]["enabled"] = flow_factor > 0.0

    def reset(self) -> None:
        for n, d in self.g.nodes(data=True):
            if d["kind"] == "corridor":
                d["flow_factor"], d["enabled"] = 1.0, True

    # ── Queries ────────────────────────────────────────────────────────
    def corridor_flow(self, corridor_id: str) -> float:
        return self.g.nodes[f"corridor:{corridor_id}"].get("flow_factor", 1.0)

    def suppliers(self) -> list[dict]:
        return [d for _, d in self.g.nodes(data=True) if d["kind"] == "supplier"]

    def refineries(self) -> list[dict]:
        return [d for _, d in self.g.nodes(data=True) if d["kind"] == "refinery"]

    def exposed_volume_kbd(self, corridor_id: str) -> float:
        """Current import volume that transits the corridor (bypass excluded)."""
        total = 0.0
        for s in self.suppliers():
            if s["corridor"] == corridor_id:
                total += s["current_kbd"] - s.get("bypass_available_kbd", 0)
        return max(0.0, total)

    def supplier_effective_capacity(self, supplier: dict) -> float:
        """Max deliverable kb/d given the supplier's corridor state and any
        bypass infrastructure (e.g., ADNOC's Fujairah line skips Hormuz)."""
        flow = self.corridor_flow(supplier["corridor"])
        through_corridor = (supplier["current_kbd"] + supplier["spare_kbd"]) * flow
        bypass = supplier.get("bypass_available_kbd", 0) * (1.0 if flow < 1.0 else 0.0)
        return through_corridor + bypass

    def freight_usd(self, supplier: dict) -> float:
        return self.raw["freight_usd_per_bbl"][supplier["corridor"]]

    def transit_days(self, supplier: dict) -> int:
        for c in self.raw["corridors"]:
            if c["id"] == supplier["corridor"]:
                return c["transit_days_to_india"]
        return 15
