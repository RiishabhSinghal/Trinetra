"""Disruption scenario library.

Each scenario declares corridor flow factors, a price shock, and a duration.
The orchestrator maps live RiskEvents onto these; judges can also run any
scenario manually from the API or dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from config.settings import ASSUMPTIONS


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    corridor_flows: dict[str, float]  # corridor_id -> flow factor
    price_shock_pct: float            # fractional Brent jump
    duration_days: int
    supply_cut_kbd: float = 0.0       # non-corridor cuts (e.g., OPEC+ action)
    notes: str = ""
    triggers: tuple = field(default=())  # event classes that auto-select this


SCENARIOS: dict[str, Scenario] = {
    "hormuz_partial": Scenario(
        id="hormuz_partial",
        name="Hormuz 50% Closure (10 days)",
        corridor_flows={"hormuz": 0.5},
        price_shock_pct=ASSUMPTIONS["hormuz_partial_price_shock"].value,
        duration_days=10,
        notes="Escorted-convoy regime; insurers restrict but do not suspend.",
        triggers=("closure_threat", "military_incident", "insurance_disruption"),
    ),
    "hormuz_full": Scenario(
        id="hormuz_full",
        name="Hormuz Full Closure (14 days)",
        corridor_flows={"hormuz": 0.0},
        price_shock_pct=ASSUMPTIONS["hormuz_full_price_shock"].value,
        duration_days=14,
        notes="Lloyd's coverage suspended; only Fujairah/Yanbu bypasses flow.",
        triggers=("closure_actual",),
    ),
    "red_sea_suspension": Scenario(
        id="red_sea_suspension",
        name="Red Sea Shipping Suspension (21 days)",
        corridor_flows={"red_sea": 0.15},
        price_shock_pct=0.06,
        duration_days=21,
        notes="Urals and Suez-routed volumes divert via Cape (+12 days).",
        triggers=("attack_on_shipping",),
    ),
    "opec_cut": Scenario(
        id="opec_cut",
        name="OPEC+ Emergency Cut (2 mb/d, 30 days)",
        corridor_flows={},
        price_shock_pct=0.09,
        duration_days=30,
        supply_cut_kbd=400,  # India-attributable share of a 2 mb/d global cut
        notes="Term allocations trimmed pro-rata; spot premiums widen.",
        triggers=("opec_supply_action",),
    ),
    "compound_gulf": Scenario(
        id="compound_gulf",
        name="Compound: Hormuz 50% + Red Sea Suspension",
        corridor_flows={"hormuz": 0.5, "red_sea": 0.15},
        price_shock_pct=0.20,
        duration_days=14,
        notes="The stress case: both western corridors impaired simultaneously.",
    ),
}


def match_scenario(event_class: str, severity: float) -> Scenario | None:
    """Map a live event to the scenario it most plausibly opens."""
    if event_class == "closure_actual" or severity >= 0.9:
        return SCENARIOS["hormuz_full"]
    for sc in SCENARIOS.values():
        if event_class in sc.triggers:
            return sc
    return None
