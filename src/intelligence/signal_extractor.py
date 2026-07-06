"""Headline → structured RiskEvent extraction.

Claude does what LLMs are actually good at here: reading unstructured text
and emitting a strict typed record. The numeric layers downstream never see
free text. A deterministic keyword extractor provides the offline fallback,
so the demo is quota-proof and wifi-proof.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict

from config.settings import ANTHROPIC_MODEL, OFFLINE_MODE

EVENT_CLASSES = [
    "military_incident", "closure_threat", "closure_actual", "sanctions_action",
    "attack_on_shipping", "insurance_disruption", "opec_supply_action",
    "port_disruption", "benign",
]

_SYSTEM = """You extract structured energy-supply risk events from headlines.
Respond with ONLY a JSON object, no prose:
{"corridor": one of ["hormuz","red_sea","cape","malacca","none"],
 "event_class": one of %s,
 "severity": float 0-1 (0.9+ only for actual closures or coverage suspension),
 "affected_suppliers": list of ["saudi","iraq","uae","kuwait","russia","wafrica","usgulf","latam"],
 "confidence": float 0-1}""" % json.dumps(EVENT_CLASSES)

# Deterministic fallback rules: (keyword set, corridor, class, severity)
_RULES = [
    ({"closure", "hormuz"}, "hormuz", "closure_actual", 1.0),
    ({"lloyd", "suspends"}, "hormuz", "insurance_disruption", 0.90),
    ({"hormuz", "drone"}, "hormuz", "military_incident", 0.55),
    ({"hormuz", "exercises"}, "hormuz", "military_incident", 0.45),
    ({"hormuz"}, "hormuz", "closure_threat", 0.40),
    ({"red", "sea"}, "red_sea", "attack_on_shipping", 0.55),
    ({"houthi"}, "red_sea", "attack_on_shipping", 0.55),
    ({"sanctions"}, "none", "sanctions_action", 0.50),
    ({"opec"}, "none", "opec_supply_action", 0.45),
    ({"war-risk", "premiums"}, "hormuz", "insurance_disruption", 0.50),
]


@dataclass
class RiskEvent:
    headline: str
    corridor: str
    event_class: str
    severity: float
    affected_suppliers: list[str] = field(default_factory=list)
    confidence: float = 0.6
    extracted_by: str = "fallback"
    ingested_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


class SignalExtractor:
    def __init__(self, offline: bool | None = None):
        self.offline = OFFLINE_MODE if offline is None else offline
        self._client = None
        if not self.offline and os.getenv("ANTHROPIC_API_KEY"):
            try:
                import anthropic

                self._client = anthropic.Anthropic()
            except Exception:
                self._client = None

    def extract(self, headline: str, ingested_at: float | None = None) -> RiskEvent:
        ev = self._extract_llm(headline) if self._client else None
        ev = ev or self._extract_rules(headline)
        if ingested_at:
            ev.ingested_at = ingested_at
        return ev

    # ── LLM path ───────────────────────────────────────────────────────
    def _extract_llm(self, headline: str) -> RiskEvent | None:
        try:
            msg = self._client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=300,
                system=_SYSTEM,
                messages=[{"role": "user", "content": headline}],
            )
            raw = msg.content[0].text.strip().removeprefix("```json").removesuffix("```")
            d = json.loads(raw)
            return RiskEvent(
                headline=headline,
                corridor=d.get("corridor", "none"),
                event_class=d.get("event_class", "benign"),
                severity=float(d.get("severity", 0.0)),
                affected_suppliers=d.get("affected_suppliers", []),
                confidence=float(d.get("confidence", 0.6)),
                extracted_by="claude",
            )
        except Exception:
            return None

    # ── Deterministic path ─────────────────────────────────────────────
    @staticmethod
    def _extract_rules(headline: str) -> RiskEvent:
        low = headline.lower()
        for keywords, corridor, cls, sev in _RULES:
            if all(k in low for k in keywords):
                conf = 0.9 if sev >= 0.9 else 0.6
                return RiskEvent(headline, corridor, cls, sev, confidence=conf)
        return RiskEvent(headline, "none", "benign", 0.05)
