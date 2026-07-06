"""Corridor vessel-density tracking.

Live AIS (aisstream.io / Spire) is a paid firehose, so the prototype ships a
calibrated simulator seeded from published corridor transit counts. The class
interface is identical to a production consumer: `snapshot()` returns per-
corridor transit rates and an anomaly score, so swapping in real AIS is a
one-class change.
"""

from __future__ import annotations

import json
import math
import os
import random
from dataclasses import dataclass

from config.settings import DATA_DIR


@dataclass
class CorridorTraffic:
    corridor_id: str
    baseline_per_day: float
    observed_per_day: float

    @property
    def anomaly(self) -> float:
        """0 = normal flow, 1 = full stoppage. Only shortfalls count."""
        if self.baseline_per_day <= 0:
            return 0.0
        shortfall = max(0.0, 1.0 - self.observed_per_day / self.baseline_per_day)
        return min(1.0, shortfall)


class AISTracker:
    def __init__(self, seed: int = 7):
        with open(os.path.join(DATA_DIR, "network.json")) as f:
            self._corridors = json.load(f)["corridors"]
        self._rng = random.Random(seed)
        # disruption factor per corridor: 1.0 = normal, 0.0 = closed
        self._flow_factor: dict[str, float] = {c["id"]: 1.0 for c in self._corridors}

    def apply_disruption(self, corridor_id: str, flow_factor: float) -> None:
        """Scenario hook: throttle a corridor (0.5 = half flow, 0.0 = closed)."""
        self._flow_factor[corridor_id] = max(0.0, min(1.0, flow_factor))

    def reset(self) -> None:
        self._flow_factor = {k: 1.0 for k in self._flow_factor}

    def snapshot(self) -> list[CorridorTraffic]:
        out = []
        for c in self._corridors:
            base = c["baseline_tankers_per_day"]
            noise = self._rng.gauss(0, 0.06 * base)  # ±6% day-to-day variation
            observed = max(0.0, base * self._flow_factor[c["id"]] + noise)
            out.append(CorridorTraffic(c["id"], base, observed))
        return out

    @staticmethod
    def density_score(traffic: CorridorTraffic) -> float:
        """Convex anomaly→risk mapping: small dips barely register,
        large shortfalls escalate fast."""
        return round(math.pow(traffic.anomaly, 0.7), 4)
