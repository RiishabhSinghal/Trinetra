"""Agent orchestrator: the loop that makes TRINETRA agentic.

  poll signals → extract events → update CSI → on band escalation:
  select scenario → run cascade → run procurement LP → schedule SPR →
  Claude drafts a decision memo grounded ONLY in the computed numbers →
  emit recommendation with measured lead time.

The lead-time instrumentation (signal ingest timestamp → recommendation
emit timestamp) is the headline demo metric.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict

from config.settings import ANTHROPIC_MODEL, ASSUMPTIONS, OFFLINE_MODE
from src.graph.supply_graph import SupplyGraph
from src.ingestion.ais_tracker import AISTracker
from src.ingestion.market_feed import MarketFeed
from src.ingestion.news_feed import NewsFeed
from src.ingestion.sanctions import SanctionsWatcher
from src.intelligence.risk_engine import RiskEngine
from src.intelligence.signal_extractor import SignalExtractor
from src.optimization.procurement import ProcurementOptimizer
from src.optimization.spr import SPRScheduler
from src.scenarios.cascade_model import CascadeModel
from src.scenarios.library import SCENARIOS, Scenario, match_scenario


@dataclass
class Recommendation:
    scenario: dict
    csi: list[dict]
    cascade: dict
    procurement: dict
    spr: dict
    memo: str
    trigger_headline: str
    lead_time_seconds: float
    emitted_at: float = field(default_factory=time.time)


class Orchestrator:
    def __init__(self):
        self.graph = SupplyGraph()
        self.news = NewsFeed()
        self.ais = AISTracker()
        self.market = MarketFeed()
        self.sanctions = SanctionsWatcher()
        self.extractor = SignalExtractor()
        self.risk = RiskEngine(self.ais, self.market, self.sanctions)
        self.cascade_model = CascadeModel(self.graph)
        self.optimizer = ProcurementOptimizer(self.graph)
        self.spr = SPRScheduler()
        self.last_recommendation: Recommendation | None = None

    # ── Steady state ───────────────────────────────────────────────────
    def poll(self) -> list[dict]:
        events = []
        for h in self.news.fetch(limit=8):
            ev = self.extractor.extract(h.text, ingested_at=h.ingested_at)
            self.risk.register_event(ev)
            events.append(ev.to_dict())
        return events

    def csi_all(self) -> list[dict]:
        return [asdict(r) for r in self.risk.compute_all()]

    # ── Crisis path ────────────────────────────────────────────────────
    def inject_and_respond(self, headline: str | None = None) -> Recommendation:
        """The judge-facing trigger: inject an event, run the full pipeline,
        return a recommendation with the measured lead time."""
        h = self.news.inject(headline) if headline else self.news.inject()
        t0 = h.ingested_at

        ev = self.extractor.extract(h.text, ingested_at=t0)
        self.risk.register_event(ev)

        scenario = match_scenario(ev.event_class, ev.severity) or SCENARIOS["hormuz_partial"]
        return self._respond(scenario, trigger=h.text, t0=t0)

    def run_scenario(self, scenario_id: str) -> Recommendation:
        return self._respond(SCENARIOS[scenario_id], trigger=f"manual:{scenario_id}", t0=time.time())

    def _respond(self, scenario: Scenario, trigger: str, t0: float) -> Recommendation:
        # Apply the scenario to the world model
        for cid, flow in scenario.corridor_flows.items():
            self.graph.set_corridor_flow(cid, flow)
            self.ais.apply_disruption(cid, flow)
        self.market.apply_shock(scenario.price_shock_pct)

        cascade = self.cascade_model.run(scenario)
        plan = self.optimizer.solve(cascade.supply_gap_kbd)
        schedule = self.spr.build(cascade.daily_gap_kbd, plan)
        csi = self.csi_all()

        memo = self._draft_memo(scenario, cascade, plan, schedule)
        rec = Recommendation(
            scenario={"id": scenario.id, "name": scenario.name, "notes": scenario.notes,
                      "duration_days": scenario.duration_days},
            csi=csi,
            cascade=asdict(cascade),
            procurement={
                "by_supplier": plan.by_supplier(),
                "covered_kbd": plan.covered_kbd,
                "unmet_kbd": plan.unmet_kbd,
                "weighted_cost_usd_per_bbl": plan.weighted_cost_usd_per_bbl,
                "status": plan.status,
            },
            spr={
                "total_drawn_kb": schedule.total_drawn_kb,
                "min_days_of_cover": schedule.min_days_of_cover,
                "breach": schedule.breach,
                "days": [asdict(d) for d in schedule.days],
            },
            memo=memo,
            trigger_headline=trigger,
            lead_time_seconds=round(time.time() - t0, 1),
        )
        self.last_recommendation = rec
        return rec

    def reset(self) -> None:
        self.graph.reset()
        self.ais.reset()
        self.market.reset()
        self.sanctions.reset()
        self.risk.clear_events()
        self.last_recommendation = None

    # ── Decision memo ──────────────────────────────────────────────────
    def _draft_memo(self, scenario, cascade, plan, schedule) -> str:
        facts = {
            "scenario": scenario.name,
            "supply_gap_kbd": cascade.supply_gap_kbd,
            "brent_peak_usd": cascade.brent_peak_usd,
            "gdp_drag_pp": cascade.gdp_drag_pp,
            "reallocation": plan.by_supplier(),
            "covered_kbd": plan.covered_kbd,
            "unmet_kbd": plan.unmet_kbd,
            "cost_usd_per_bbl": plan.weighted_cost_usd_per_bbl,
            "spr_drawn_kb": schedule.total_drawn_kb,
            "min_days_of_cover": schedule.min_days_of_cover,
            "spr_breach": schedule.breach,
        }
        if not OFFLINE_MODE and os.getenv("ANTHROPIC_API_KEY"):
            try:
                import anthropic

                msg = anthropic.Anthropic().messages.create(
                    model=ANTHROPIC_MODEL,
                    max_tokens=600,
                    system=(
                        "You are the duty officer of India's energy supply chain "
                        "command center. Write a crisp one-page decision memo for the "
                        "Secretary, MoPNG. Use ONLY the numbers provided; never invent "
                        "figures. Sections: SITUATION, IMPACT, RECOMMENDED ACTION, "
                        "RESIDUAL RISK. Plain language, no filler."
                    ),
                    messages=[{"role": "user", "content": json.dumps(facts)}],
                )
                return msg.content[0].text
            except Exception:
                pass
        return self._memo_fallback(facts)

    @staticmethod
    def _memo_fallback(f: dict) -> str:
        lines = [row for row in (
            f"SITUATION: {f['scenario']}. Estimated supply gap {f['supply_gap_kbd']:,.0f} kb/d.",
            f"IMPACT: Brent modeled at ${f['brent_peak_usd']:.0f}/bbl peak; GDP drag {f['gdp_drag_pp']:.2f} pp if unmitigated.",
            "RECOMMENDED ACTION:",
        )]
        for r in f["reallocation"]:
            lines.append(
                f"  • +{r['volume_kbd']:,.0f} kb/d from {r['supplier']} "
                f"(via {r['corridor']}, {r['transit_days']}d transit, ${r['cost_usd_per_bbl']}/bbl)"
            )
        if f["spr_breach"]:
            lines.append(
                f"  • SPR bridge: draw {f['spr_drawn_kb']:,.0f} kb total; pumping/floor "
                f"constraints CANNOT fully bridge the gap (min cover {f['min_days_of_cover']}d). "
                f"Initiate demand restraint: allocate product, curtail non-essential aviation/industrial offtake."
            )
        else:
            lines.append(
                f"  • SPR bridge: draw {f['spr_drawn_kb']:,.0f} kb total; "
                f"reserve floor holds at {f['min_days_of_cover']} days of cover."
            )
        lines.append(
            f"RESIDUAL RISK: {f['unmet_kbd']:,.0f} kb/d unmet by market; "
            f"weighted incremental cost ${f['cost_usd_per_bbl']}/bbl."
        )
        return "\n".join(lines)
