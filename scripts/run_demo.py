"""Stage-by-stage CLI runner. Each phase checkpoint in the plan maps here.

  python scripts/run_demo.py --stage signals
  python scripts/run_demo.py --stage csi
  python scripts/run_demo.py --stage scenario --name hormuz_partial
  python scripts/run_demo.py --stage full          # the 90-second drill
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents.orchestrator import Orchestrator


def main() -> None:
    ap = argparse.ArgumentParser(description="TRINETRA demo runner")
    ap.add_argument("--stage", choices=["signals", "csi", "scenario", "full"], default="full")
    ap.add_argument("--name", default="hormuz_partial", help="scenario id for --stage scenario")
    args = ap.parse_args()

    orch = Orchestrator()

    if args.stage == "signals":
        for ev in orch.poll():
            print(f"[{ev['event_class']:<22}] sev={ev['severity']:.2f} "
                  f"corridor={ev['corridor']:<8} :: {ev['headline'][:80]}")
        return

    if args.stage == "csi":
        orch.poll()
        for r in orch.csi_all():
            print(f"{r['corridor_id']:<10} CSI={r['score']:>5}  band={r['band']:<9} "
                  f"factors={r['factors']}")
        return

    if args.stage == "scenario":
        rec = orch.run_scenario(args.name)
        _print_recommendation(rec)
        return

    # full drill: steady state → inject → respond
    print("═" * 70)
    print(" TRINETRA CRISIS DRILL — signal to recommendation")
    print("═" * 70)
    orch.poll()
    print("\nSteady-state CSI:")
    for r in orch.csi_all():
        print(f"  {r['corridor_id']:<10} {r['score']:>5}  {r['band']}")
    print("\n⚡ Injecting Hormuz closure event ...\n")
    rec = orch.inject_and_respond()
    _print_recommendation(rec)


def _print_recommendation(rec) -> None:
    print(f"SCENARIO : {rec.scenario['name']}")
    print(f"LEAD TIME: {rec.lead_time_seconds}s (signal → executable recommendation)")
    print(f"\nPost-event CSI:")
    for r in rec.csi:
        print(f"  {r['corridor_id']:<10} {r['score']:>5}  {r['band']}")
    c = rec.cascade
    print(f"\nCASCADE  : gap {c['supply_gap_kbd']:,.0f} kb/d "
          f"({c['gap_share_of_demand']:.0%} of demand) · Brent ${c['brent_peak_usd']:.0f} "
          f"· GDP -{c['gdp_drag_pp']:.2f}pp · cover if idle: {c['days_of_cover_unmitigated']}d")
    print("\nREALLOCATION:")
    for row in rec.procurement["by_supplier"]:
        print(f"  +{row['volume_kbd']:>6,.0f} kb/d  {row['supplier']:<38} "
              f"via {row['corridor']:<8} {row['transit_days']:>2}d  ${row['cost_usd_per_bbl']}/bbl")
    print(f"  covered {rec.procurement['covered_kbd']:,.0f} kb/d · "
          f"unmet {rec.procurement['unmet_kbd']:,.0f} kb/d · "
          f"weighted Δcost ${rec.procurement['weighted_cost_usd_per_bbl']}/bbl")
    s = rec.spr
    print(f"\nSPR      : draw {s['total_drawn_kb']:,.0f} kb total · "
          f"min cover {s['min_days_of_cover']}d · breach={s['breach']}")
    print("\n" + "─" * 70)
    print(rec.memo)


if __name__ == "__main__":
    main()
