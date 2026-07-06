"""Sanctions exposure watcher.

Production would sync the OFAC SDN list and EU consolidated list nightly.
The prototype evaluates supplier exposure from flags in the network dataset
plus events raised by the intelligence layer (e.g., a headline naming new
designations lifts the exposure score for tagged suppliers).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from config.settings import DATA_DIR


@dataclass
class SanctionsExposure:
    supplier_id: str
    corridor_id: str
    volume_kbd: float
    exposure: float  # 0-1


class SanctionsWatcher:
    def __init__(self):
        with open(os.path.join(DATA_DIR, "network.json")) as f:
            self._suppliers = json.load(f)["suppliers"]
        self._escalation: dict[str, float] = {}

    def escalate(self, supplier_id: str, delta: float = 0.3) -> None:
        """Intelligence-layer hook: a new designation headline raises exposure."""
        cur = self._escalation.get(supplier_id, 0.0)
        self._escalation[supplier_id] = min(1.0, cur + delta)

    def reset(self) -> None:
        self._escalation = {}

    def snapshot(self) -> list[SanctionsExposure]:
        out = []
        for s in self._suppliers:
            base = 0.45 if s.get("sanctions_watch") else 0.05
            exp = min(1.0, base + self._escalation.get(s["id"], 0.0))
            out.append(
                SanctionsExposure(s["id"], s["corridor"], s["current_kbd"], round(exp, 3))
            )
        return out

    def corridor_exposure(self) -> dict[str, float]:
        """Volume-weighted exposure per corridor, 0-1."""
        acc: dict[str, list[tuple[float, float]]] = {}
        for e in self.snapshot():
            acc.setdefault(e.corridor_id, []).append((e.volume_kbd, e.exposure))
        return {
            cid: round(sum(v * x for v, x in pairs) / max(1.0, sum(v for v, _ in pairs)), 4)
            for cid, pairs in acc.items()
        }
