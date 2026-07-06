"""Corridor Stress Index (CSI).

CSI is a 0-100 composite per corridor:

    CSI = 100 * (0.35*geopolitical + 0.25*maritime + 0.20*market + 0.20*sanctions)

- geopolitical: max event severity in window, exponentially decayed (72h halflife)
- maritime:     AIS shortfall anomaly (convex)
- market:       Brent move + volatility regime
- sanctions:    volume-weighted supplier exposure on the corridor

The factor breakdown is returned with every score. Explainability is the
feature, not an afterthought: a judge can ask "why 78?" and get four numbers.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

from config.settings import CSI_BANDS, CSI_DECAY_HALFLIFE_HOURS, CSI_WEIGHTS
from src.ingestion.ais_tracker import AISTracker
from src.ingestion.market_feed import MarketFeed
from src.ingestion.sanctions import SanctionsWatcher
from src.intelligence.signal_extractor import RiskEvent


@dataclass
class CSIReading:
    corridor_id: str
    score: float
    band: str
    factors: dict[str, float]
    computed_at: float = field(default_factory=time.time)


class RiskEngine:
    def __init__(self, ais: AISTracker, market: MarketFeed, sanctions: SanctionsWatcher):
        self.ais = ais
        self.market = market
        self.sanctions = sanctions
        self._events: list[RiskEvent] = []

    def register_event(self, event: RiskEvent) -> None:
        self._events.append(event)
        if event.event_class == "sanctions_action":
            for sid in event.affected_suppliers:
                self.sanctions.escalate(sid)

    def clear_events(self) -> None:
        self._events = []

    # ── Factor computations ────────────────────────────────────────────
    def _geopolitical(self, corridor_id: str, now: float) -> float:
        best = 0.0
        for ev in self._events:
            if ev.corridor != corridor_id:
                continue
            age_h = (now - ev.ingested_at) / 3600.0
            decay = math.pow(0.5, age_h / CSI_DECAY_HALFLIFE_HOURS)
            best = max(best, ev.severity * ev.confidence * decay)
        return best

    def _maritime(self, corridor_id: str) -> float:
        for t in self.ais.snapshot():
            if t.corridor_id == corridor_id:
                return AISTracker.density_score(t)
        return 0.0

    # ── Public API ─────────────────────────────────────────────────────
    def compute(self, corridor_id: str) -> CSIReading:
        now = time.time()
        factors = {
            "geopolitical": round(self._geopolitical(corridor_id, now), 4),
            "maritime": round(self._maritime(corridor_id), 4),
            "market": self.market.snapshot().stress,
            "sanctions": self.sanctions.corridor_exposure().get(corridor_id, 0.0),
        }
        score = round(100 * sum(CSI_WEIGHTS[k] * v for k, v in factors.items()), 1)
        return CSIReading(corridor_id, score, self.band(score), factors)

    def compute_all(self) -> list[CSIReading]:
        seen = {t.corridor_id for t in self.ais.snapshot()}
        return [self.compute(cid) for cid in sorted(seen)]

    @staticmethod
    def band(score: float) -> str:
        if score >= CSI_BANDS["CRITICAL"]:
            return "CRITICAL"
        if score >= CSI_BANDS["ELEVATED"]:
            return "ELEVATED"
        if score >= CSI_BANDS["WATCH"]:
            return "WATCH"
        return "NORMAL"
