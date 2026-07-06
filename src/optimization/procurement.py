"""Adaptive procurement optimizer.

Linear program (PuLP/CBC):

  minimize   Σ  x[s,r] · (fob_premium[s] + freight[s] + delay_penalty[s] + crisis_premium)
  subject to Σ_s x[s,r]           ≥ replacement demand share per refinery r
             Σ_r x[s,r]           ≤ incremental capacity of supplier s
             x[s,r] = 0           if supplier grade violates refinery window
             slack penalized      so a plan always returns, with a feasibility note

Grade compatibility is a hard constraint: sweet-configured refineries can't
absorb 2.9%-sulfur Basrah, and the model knows it. Delay penalty prices the
working-capital and stockout cost of long transits ($0.08/bbl/day).
"""

from __future__ import annotations

from dataclasses import dataclass

import pulp

from config.settings import ASSUMPTIONS
from src.graph.supply_graph import SupplyGraph

DELAY_PENALTY_USD_PER_BBL_DAY = 0.08
SLACK_PENALTY = 500.0  # per kb/d unmet: forces the LP to try everything first


@dataclass
class Allocation:
    supplier_id: str
    supplier_name: str
    refinery_id: str
    volume_kbd: float
    corridor: str
    cost_usd_per_bbl: float
    transit_days: int


@dataclass
class ProcurementPlan:
    allocations: list[Allocation]
    covered_kbd: float
    unmet_kbd: float
    weighted_cost_usd_per_bbl: float
    status: str

    def by_supplier(self) -> list[dict]:
        agg: dict[str, dict] = {}
        for a in self.allocations:
            d = agg.setdefault(a.supplier_id, {
                "supplier": a.supplier_name, "corridor": a.corridor,
                "volume_kbd": 0.0, "cost_usd_per_bbl": a.cost_usd_per_bbl,
                "transit_days": a.transit_days,
            })
            d["volume_kbd"] += a.volume_kbd
        return sorted(agg.values(), key=lambda d: -d["volume_kbd"])


class ProcurementOptimizer:
    def __init__(self, graph: SupplyGraph):
        self.graph = graph

    @staticmethod
    def _grade_ok(supplier: dict, refinery: dict) -> bool:
        g, w = supplier["grade"], refinery["grade_window"]
        return w["api_min"] <= g["api"] <= w["api_max"] and g["sulfur"] <= w["sulfur_max"]

    def _incremental_capacity(self, supplier: dict) -> float:
        """kb/d the supplier can add beyond what still flows to India."""
        effective = self.graph.supplier_effective_capacity(supplier)
        still_flowing = supplier["current_kbd"] * self.graph.corridor_flow(supplier["corridor"])
        return max(0.0, effective - still_flowing)

    def solve(self, supply_gap_kbd: float) -> ProcurementPlan:
        suppliers = self.graph.suppliers()
        refineries = self.graph.refineries()
        crisis_prem = ASSUMPTIONS["spot_premium_crisis_usd"].value

        # Distribute the replacement requirement across refineries by capacity
        total_cap = sum(r["capacity_kbd"] for r in refineries)
        need = {r["id"]: supply_gap_kbd * r["capacity_kbd"] / total_cap for r in refineries}

        prob = pulp.LpProblem("procurement_reroute", pulp.LpMinimize)
        x, cost = {}, {}
        for s in suppliers:
            for r in refineries:
                if not self._grade_ok(s, r):
                    continue
                key = (s["id"], r["id"])
                x[key] = pulp.LpVariable(f"x_{s['id']}_{r['id']}", lowBound=0)
                cost[key] = (
                    s["fob_premium_usd"]
                    + self.graph.freight_usd(s)
                    + self.graph.transit_days(s) * DELAY_PENALTY_USD_PER_BBL_DAY
                    + crisis_prem
                )
        slack = {r["id"]: pulp.LpVariable(f"slack_{r['id']}", lowBound=0) for r in refineries}

        prob += (
            pulp.lpSum(x[k] * cost[k] for k in x)
            + pulp.lpSum(slack[rid] * SLACK_PENALTY for rid in slack)
        )
        for r in refineries:
            prob += (
                pulp.lpSum(x[k] for k in x if k[1] == r["id"]) + slack[r["id"]]
                >= need[r["id"]]
            ), f"demand_{r['id']}"
        for s in suppliers:
            prob += (
                pulp.lpSum(x[k] for k in x if k[0] == s["id"])
                <= self._incremental_capacity(s)
            ), f"capacity_{s['id']}"

        prob.solve(pulp.PULP_CBC_CMD(msg=False))

        name = {s["id"]: s for s in suppliers}
        allocations = [
            Allocation(
                supplier_id=sid, supplier_name=name[sid]["name"], refinery_id=rid,
                volume_kbd=round(v.value(), 1), corridor=name[sid]["corridor"],
                cost_usd_per_bbl=round(cost[(sid, rid)], 2),
                transit_days=self.graph.transit_days(name[sid]),
            )
            for (sid, rid), v in x.items() if v.value() and v.value() > 0.5
        ]
        covered = sum(a.volume_kbd for a in allocations)
        unmet = round(sum(s.value() for s in slack.values()), 1)
        wcost = (
            round(sum(a.volume_kbd * a.cost_usd_per_bbl for a in allocations) / covered, 2)
            if covered else 0.0
        )
        return ProcurementPlan(
            allocations=allocations,
            covered_kbd=round(covered, 1),
            unmet_kbd=unmet,
            weighted_cost_usd_per_bbl=wcost,
            status=pulp.LpStatus[prob.status],
        )
