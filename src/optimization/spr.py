"""Strategic Petroleum Reserve drawdown scheduler.

The market covers what it can (procurement LP); the SPR bridges two things:
  1. the residual gap the LP could not source, and
  2. the transit lag: rerouted barrels take 9-28 days to arrive, so even a
     fully covered plan needs the reserve for the first leg.

Constraints: max daily pumping rate, and a policy floor (never drain below
25% — the reserve is also a deterrence asset).
"""

from __future__ import annotations

from dataclasses import dataclass

from config.settings import ASSUMPTIONS
from src.optimization.procurement import ProcurementPlan


@dataclass
class SPRDay:
    day: int
    gap_kbd: float
    arrivals_kbd: float
    drawdown_kbd: float
    shortfall_kbd: float
    reserve_kb: float
    days_of_cover: float


@dataclass
class SPRSchedule:
    days: list[SPRDay]
    total_drawn_kb: float
    min_days_of_cover: float
    breach: bool  # True if shortfall could not be covered within constraints

    def worst_day(self) -> SPRDay:
        return min(self.days, key=lambda d: d.days_of_cover)


class SPRScheduler:
    def build(self, daily_gap_kbd: list[float], plan: ProcurementPlan) -> SPRSchedule:
        A = ASSUMPTIONS
        reserve = A["spr_total_kb"].value
        floor = reserve * A["spr_floor_share"].value
        max_draw = A["spr_max_drawdown_kbd"].value
        demand = A["national_demand_kbd"].value

        # Arrival profile: each supplier's volume lands after its transit time
        arrivals = [0.0] * len(daily_gap_kbd)
        for row in plan.by_supplier():
            for d in range(len(daily_gap_kbd)):
                if d + 1 >= row["transit_days"]:
                    arrivals[d] += row["volume_kbd"]

        days, total_drawn, breach = [], 0.0, False
        for i, gap in enumerate(daily_gap_kbd):
            residual = max(0.0, gap - arrivals[i])
            headroom_kb = max(0.0, reserve - floor)
            draw = min(residual, max_draw, headroom_kb)  # kb/d vs kb: 1 day step
            shortfall = round(residual - draw, 1)
            if shortfall > 0.5:
                breach = True
            reserve -= draw
            total_drawn += draw
            days.append(SPRDay(
                day=i + 1,
                gap_kbd=round(gap, 1),
                arrivals_kbd=round(arrivals[i], 1),
                drawdown_kbd=round(draw, 1),
                shortfall_kbd=shortfall,
                reserve_kb=round(reserve, 1),
                days_of_cover=round(reserve / demand, 2),
            ))

        return SPRSchedule(
            days=days,
            total_drawn_kb=round(total_drawn, 1),
            min_days_of_cover=round(min(d.days_of_cover for d in days), 2),
            breach=breach,
        )
