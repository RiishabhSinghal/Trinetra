"""TRINETRA Command Center.

Run:  streamlit run dashboard/app.py
Dark maritime-ops aesthetic. One button matters: ⚡ INJECT HORMUZ EVENT.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config.settings import ASSUMPTIONS, CSI_BANDS
from src.agents.orchestrator import Orchestrator

st.set_page_config(page_title="TRINETRA · Energy Resilience Command", layout="wide")

INK, PANEL, AMBER, RED, GREEN, CYAN = "#0B1220", "#111A2C", "#FFB830", "#FF4D4D", "#3DDC97", "#00C2FF"
st.markdown(f"""<style>
.stApp {{ background: {INK}; color: #E8EEF7; }}
[data-testid="stMetric"] {{ background: {PANEL}; border: 1px solid #1E2A44;
  border-radius: 10px; padding: 12px 16px; }}
h1, h2, h3 {{ color: #E8EEF7 !important; letter-spacing: .02em; }}
.memo {{ background:{PANEL}; border-left:3px solid {CYAN}; padding:16px;
  border-radius:6px; white-space:pre-wrap; font-family:ui-monospace,monospace;
  font-size:0.85rem; }}
</style>""", unsafe_allow_html=True)


@st.cache_resource
def get_orchestrator() -> Orchestrator:
    return Orchestrator()


orch = get_orchestrator()

# ── Header ─────────────────────────────────────────────────────────────
left, right = st.columns([3, 1])
with left:
    st.title("🔱 TRINETRA — Energy Supply Chain Resilience")
    st.caption("88% import dependence · 42% via Hormuz · 9.5 days of reserve. The third eye watches the corridors.")
with right:
    if st.button("⚡ INJECT HORMUZ EVENT", type="primary", use_container_width=True):
        with st.spinner("Signal → CSI → scenario → optimizer → memo ..."):
            st.session_state["rec"] = orch.inject_and_respond()
    if st.button("↺ Reset to steady state", use_container_width=True):
        orch.reset()
        st.session_state.pop("rec", None)

rec = st.session_state.get("rec")

# ── CSI gauge row ──────────────────────────────────────────────────────
st.subheader("Corridor Stress Index")
readings = rec.csi if rec else orch.csi_all()

cols = st.columns(len(readings))
for col, r in zip(cols, readings):
    color = GREEN if r["score"] < CSI_BANDS["WATCH"] else AMBER if r["score"] < CSI_BANDS["CRITICAL"] else RED
    with col:
        fig = go.Figure(go.Indicator(
            mode="gauge+number", value=r["score"],
            title={"text": f"{r['corridor_id'].upper()} · {r['band']}", "font": {"size": 14}},
            gauge={"axis": {"range": [0, 100]}, "bar": {"color": color},
                   "bgcolor": PANEL,
                   "threshold": {"line": {"color": RED, "width": 3}, "value": CSI_BANDS["CRITICAL"]}},
        ))
        fig.update_layout(height=180, margin=dict(l=10, r=10, t=40, b=5),
                          paper_bgcolor="rgba(0,0,0,0)", font_color="#E8EEF7")
        st.plotly_chart(fig, use_container_width=True)
        st.caption(" · ".join(f"{k[:3]} {v:.2f}" for k, v in r["factors"].items()))

# ── Crisis view ────────────────────────────────────────────────────────
if rec:
    c, p, s = rec.cascade, rec.procurement, rec.spr
    scen, memo, lead = rec.scenario, rec.memo, rec.lead_time_seconds

    st.error(f"**{scen['name']}** — {scen['notes']}  ·  ⏱ Signal → recommendation lead time: **{lead}s**")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Supply gap", f"{c['supply_gap_kbd']:,.0f} kb/d", f"{c['gap_share_of_demand']:.0%} of demand")
    m2.metric("Brent (peak)", f"${c['brent_peak_usd']:.0f}", f"+${c['brent_delta_usd']:.0f}/bbl")
    m3.metric("GDP drag", f"-{c['gdp_drag_pp']:.2f} pp", f"CPI +{c['cpi_push_pp']:.2f} pp", delta_color="inverse")
    m4.metric("Market covers", f"{p['covered_kbd']:,.0f} kb/d", f"unmet {p['unmet_kbd']:,.0f} kb/d")
    m5.metric("Min days of cover", f"{s['min_days_of_cover']}", "SPR floor holds" if not s["breach"] else "BREACH", delta_color="normal" if not s["breach"] else "inverse")

    a, b = st.columns([1.2, 1])
    with a:
        st.subheader("Recommended reallocation")
        st.dataframe(pd.DataFrame(p["by_supplier"]).rename(columns={
            "supplier": "Supplier", "corridor": "Corridor", "volume_kbd": "Volume kb/d",
            "cost_usd_per_bbl": "Δcost $/bbl", "transit_days": "Transit days"}),
            use_container_width=True, hide_index=True)

        st.subheader("SPR bridge")
        spr_df = pd.DataFrame(s["days"])
        fig = go.Figure()
        fig.add_trace(go.Bar(x=spr_df["day"], y=spr_df["gap_kbd"], name="Gap", marker_color=RED, opacity=0.6))
        fig.add_trace(go.Bar(x=spr_df["day"], y=spr_df["arrivals_kbd"], name="Rerouted arrivals", marker_color=CYAN, opacity=0.7))
        fig.add_trace(go.Scatter(x=spr_df["day"], y=spr_df["days_of_cover"] * 100, name="Days of cover ×100",
                                 line=dict(color=AMBER, width=3), yaxis="y"))
        fig.update_layout(barmode="overlay", height=300, paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor=PANEL, font_color="#E8EEF7",
                          legend=dict(orientation="h"), margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    with b:
        st.subheader("Decision memo")
        st.markdown(f'<div class="memo">{memo}</div>', unsafe_allow_html=True)
        st.caption("Every figure traceable to config/settings.py — the assumption registry.")
else:
    st.info("Steady state. Corridors flowing, reserves full. Press **⚡ INJECT HORMUZ EVENT** to run the crisis drill.")
    with st.expander("Assumption registry (what the model believes, and why)"):
        st.dataframe(pd.DataFrame(
            [{"Assumption": k, "Value": a.value, "Unit": a.unit, "Source": a.source}
             for k, a in ASSUMPTIONS.items()]),
            use_container_width=True, hide_index=True)
