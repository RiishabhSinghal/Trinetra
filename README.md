# 🔱 TRINETRA
**Threat & Risk Intelligence NETwork for Resilient energy Architecture**

AI-driven energy supply chain resilience for import-dependent economies. TRINETRA watches geopolitical and maritime risk continuously, quantifies corridor stress with an explainable index, simulates disruption cascades through refineries and the macro economy, and hands procurement teams a ranked, executable rerouting plan with an SPR drawdown schedule — in seconds, not days.

> India imports 88% of its crude. 42% of it sails through a strait 33 km wide. The reserve lasts 9.5 days. TRINETRA is the third eye on the corridors.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add ANTHROPIC_API_KEY for live LLM extraction (optional)

# The 90-second crisis drill, in the terminal
python scripts/run_demo.py --stage full

# The command center
uvicorn dashboard.serve:app --port 8000   # open http://localhost:8000

# The API
uvicorn src.api.main:app --reload --port 8000   # docs at /docs
```

The whole system runs **fully offline** — every feed has a deterministic fallback, and the LLM layer degrades to a rule-based extractor. Set `TRINETRA_OFFLINE=true` to force it (demo insurance).

## Module Map

| Path | What it is |
|---|---|
| `config/settings.py` | **Assumption registry** — every constant, with a source. Nothing else hard-codes a number |
| `data/network.json` | Ground truth: 8 suppliers, 4 corridors, 6 refineries with grades and capacities |
| `src/ingestion/` | Signal layer: news RSS, AIS density, Brent feed, sanctions watcher |
| `src/intelligence/` | Claude signal extraction → typed events; Corridor Stress Index engine |
| `src/graph/` | NetworkX supply knowledge graph (supplier → corridor → refinery) |
| `src/scenarios/` | Scenario library + explicit-equation cascade model (refinery → pump price → CAD → GDP) |
| `src/optimization/` | Procurement LP (PuLP, grade-constrained) + SPR drawdown scheduler |
| `src/agents/` | The orchestrator: signal → CSI → scenario → optimize → Claude decision memo |
| `src/api/` | FastAPI: `/csi`, `/scenarios/{id}/run`, `/demo/inject`, `/recommendation` |
| `dashboard/` | Streamlit command center: gauges, SPR clock, reallocation table, memo |
| `scripts/run_demo.py` | Stage-by-stage checkpoint runner |

## The Demo Metric

Every event is timestamped at ingest; every recommendation at emit. The delta — **signal-to-recommendation lead time** — is printed on the recommendation itself. That is the number the judging rubric asks for, measured live.

See `IMPLEMENTATION_PLAN.md` for the full 36-hour build plan, demo script, deck structure, and risk register.
