# TRINETRA — Implementation Plan
### Threat & Risk Intelligence NETwork for Resilient energy Architecture
**AI-Driven Energy Supply Chain Resilience for Import-Dependent Economies**

---

## 1. The One-Line Pitch

TRINETRA compresses the signal-to-decision cycle for India's crude supply chain from **days to minutes**: it watches geopolitical and maritime risk continuously, quantifies corridor stress, simulates the cascade of a disruption through refineries and the economy, and hands procurement teams a ranked, executable rerouting plan with an SPR drawdown schedule attached.

**Why it wins:** The judging rubric rewards *lead time from signal to recommendation*. Everything in this build is organized around one measurable claim you can demo live: **"Event injected at T+0. Executable procurement plan on screen at T+90 seconds."**

---

## 2. What Makes This Unique (Positioning Against Other Teams)

Most teams will build one of two things: a news-sentiment dashboard, or a generic "chat with your supply chain" RAG bot. TRINETRA is differentiated on five specific design decisions:

1. **Corridor Stress Index (CSI)** — a proprietary, explainable 0-100 composite score per corridor (Hormuz, Red Sea/Suez, Cape of Good Hope, Malacca) built from four weighted signal families. Judges can see exactly why the number moved. Explainability beats a black-box score.
2. **Deterministic math, LLM narration** — optimization runs on linear programming (PuLP), cascade economics on explicit elasticity equations. Claude is used where LLMs are actually strong: extracting structured signals from unstructured news, and writing the decision memo. No hallucinated numbers, ever. Every assumption is a named constant in `config/settings.py` (the rubric explicitly asks for "assumptions must be explicit and testable").
3. **A real knowledge graph, not a diagram** — supplier → corridor → port → refinery relationships live in a NetworkX graph that the optimizer traverses. Kill a corridor edge and feasible routes recompute automatically.
4. **Grade compatibility as a hard constraint** — Indian refineries are configured for specific crude baskets (sour/heavy vs sweet/light). TRINETRA's optimizer respects API gravity and sulfur constraints per refinery. This one detail signals domain depth that generic teams will miss.
5. **The SPR clock** — every recommendation is framed against India's ~9.5-day strategic reserve. The dashboard shows a literal countdown: "days of cover remaining under this scenario, with and without the recommended action." That is the emotional core of the demo.

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SIGNAL LAYER (ingestion/)                     │
│  News/GDELT RSS   AIS vessel density   Sanctions registry   Brent   │
│      feed              tracker             watcher         futures  │
└───────────┬─────────────────┬────────────────┬──────────────┬──────┘
            ▼                 ▼                ▼              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   INTELLIGENCE LAYER (intelligence/)                 │
│  Claude Signal Extractor ──► structured events (actor, corridor,    │
│                              severity, confidence)                  │
│  Risk Engine ──► Corridor Stress Index (CSI) per corridor           │
└───────────────────────────────┬─────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│              SUPPLY KNOWLEDGE GRAPH (graph/)  · NetworkX             │
│   Supplier ──corridor──► Port ──pipeline──► Refinery ──► Demand     │
│   nodes carry: capacity, grade, freight cost, transit days          │
└───────────────────────────────┬─────────────────────────────────────┘
                                ▼
┌──────────────────────────────┐  ┌───────────────────────────────────┐
│  SCENARIO ENGINE (scenarios/)│  │  OPTIMIZATION LAYER (optimization/)│
│  Event library + cascade     │  │  Procurement LP (PuLP): reroute   │
│  model: refinery runs, pump  │  │  volumes at min cost s.t. grade,  │
│  prices, CAD, GDP drag       │  │  tanker, port constraints         │
│                              │  │  SPR drawdown scheduler            │
└──────────────┬───────────────┘  └────────────────┬──────────────────┘
               └────────────┬─────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│               AGENT ORCHESTRATOR (agents/) · Claude API              │
│   Watches CSI thresholds → triggers scenario → runs optimizer →     │
│   drafts decision memo → pushes alert                               │
└───────────────────────────────┬─────────────────────────────────────┘
                                ▼
┌──────────────────────────────┐  ┌───────────────────────────────────┐
│   FastAPI (api/)             │  │   Streamlit Command Center        │
│   REST endpoints for every   │  │   (dashboard/) — map, CSI gauges, │
│   layer, demo injection      │  │   SPR clock, recommendation cards │
└──────────────────────────────┘  └───────────────────────────────────┘
```

**Stack:** Python 3.11 · FastAPI · Streamlit · NetworkX · PuLP · Plotly · Anthropic API (claude-sonnet-4-6) · feedparser/yfinance for live feeds · JSON flat files as the datastore (right-sized for a prototype; the plan names PostGIS + Kafka as the production path).

---

## 4. Build Phases (36-Hour Hackathon Budget)

### Phase 0 — Foundations (Hours 0–2)
| Step | Task | Output |
|---|---|---|
| 0.1 | Repo init, venv, `requirements.txt`, `.env.example` | Runnable skeleton |
| 0.2 | Encode the **assumption registry** in `config/settings.py`: import share (88%), Hormuz transit share (42%), SPR days (9.5), demand (5.4 mb/d), price elasticities | Single source of truth for every number judges will ask about |
| 0.3 | Build `data/network.json`: 8 suppliers, 4 corridors, 5 ports, 6 refineries with real capacities and grade specs | Ground-truth dataset |

**Checkpoint:** `python -c "from config.settings import ASSUMPTIONS"` runs clean.

### Phase 1 — Signal Layer (Hours 2–8)
| Step | Task | Detail |
|---|---|---|
| 1.1 | `news_feed.py` | Pull Reuters/GDELT energy RSS; fall back to a curated replay file of real 2025–26 headlines so the demo never depends on wifi |
| 1.2 | `market_feed.py` | Brent front-month via yfinance; compute rolling volatility and backwardation signal; synthetic fallback |
| 1.3 | `ais_tracker.py` | Corridor vessel-density model. Live AIS is a paid firehose, so the prototype ships a calibrated simulator seeded from published Hormuz transit counts (~20 tankers/day) with stochastic variation; the class interface is identical to a real aisstream.io consumer |
| 1.4 | `sanctions.py` | OFAC SDN-style watcher over a local snapshot; flags supplier exposure |

**Checkpoint:** `python scripts/run_demo.py --stage signals` prints a unified signal frame.

### Phase 2 — Intelligence Layer (Hours 8–14)
| Step | Task | Detail |
|---|---|---|
| 2.1 | `signal_extractor.py` | Claude turns each headline into a typed `RiskEvent` (corridor, event_class, severity 0-1, confidence). Strict JSON schema, deterministic keyword fallback when offline |
| 2.2 | `risk_engine.py` | **CSI = 0.35·geopolitical + 0.25·maritime + 0.20·market + 0.20·sanctions**, exponentially decayed over 72h. Alert bands: WATCH ≥ 40, ELEVATED ≥ 60, CRITICAL ≥ 75 |
| 2.3 | Lead-time instrumentation | Timestamp every event at ingest and every recommendation at emit; the delta is your headline demo metric |

**Checkpoint:** Inject the "Hormuz incident" headline → CSI(Hormuz) jumps from ~38 to ~78 with a printed factor breakdown.

### Phase 3 — Knowledge Graph + Scenario Engine (Hours 14–20)
| Step | Task | Detail |
|---|---|---|
| 3.1 | `supply_graph.py` | Directed NetworkX graph from `network.json`; helpers: `routes_for(supplier)`, `disable_corridor(name)`, `exposed_volume(corridor)` |
| 3.2 | `library.py` | Five prebuilt scenarios: Hormuz 50% closure, Hormuz full closure 14d, Red Sea suspension, OPEC+ 2 mb/d cut, combined Hormuz+Red Sea |
| 3.3 | `cascade_model.py` | Explicit equation chain: supply gap → refinery utilization → product prices (pass-through elasticity) → CAD impact → GDP drag (RBI rule-of-thumb: +$10/bbl ≈ −0.15pp GDP, +0.4pp CPI). Every constant cited in comments |

**Checkpoint:** `run_demo.py --stage scenario --name hormuz_partial` prints day-by-day supply gap and macro table.

### Phase 4 — Optimization Layer (Hours 20–26)
| Step | Task | Detail |
|---|---|---|
| 4.1 | `procurement.py` | LP: minimize (FOB premium + freight + delay penalty) s.t. refinery demand met, supplier spare capacity, corridor availability, grade compatibility, tanker availability. Output: ranked reallocation table with per-barrel cost delta |
| 4.2 | `spr.py` | Drawdown scheduler: bridge the residual gap the market can't cover, subject to max daily withdrawal and a floor reserve; outputs day-by-day schedule + days-of-cover curve |
| 4.3 | Integration test | Scenario → graph → LP → SPR runs end-to-end under 5 seconds |

**Checkpoint:** Hormuz partial closure produces a plan like: "+380 kb/d WAF via Cape, +220 kb/d US Gulf, +150 kb/d ADNOC via Fujairah bypass, SPR bridges 9 days at ≤180 kb/d."

### Phase 5 — Agent Orchestrator + API (Hours 26–30)
| Step | Task | Detail |
|---|---|---|
| 5.1 | `orchestrator.py` | The agent loop: poll signals → update CSI → if band escalates, auto-select matching scenario → run cascade + optimizer → ask Claude to draft a one-page decision memo grounded ONLY in the computed numbers → emit alert |
| 5.2 | `api/main.py` | FastAPI: `/signals`, `/csi`, `/scenarios/{name}/run`, `/recommendation`, `/demo/inject` (the judge-facing trigger) |

**Checkpoint:** `POST /demo/inject` returns a full recommendation payload with `lead_time_seconds` in the response.

### Phase 6 — Command Center Dashboard (Hours 30–34)
| Step | Task | Detail |
|---|---|---|
| 6.1 | Layout | Dark maritime-ops aesthetic. Four zones: corridor map (Plotly geo with flow arcs), CSI gauge row, SPR countdown clock, recommendation cards |
| 6.2 | The demo moment | A "⚡ Inject Hormuz Event" button that runs the whole pipeline live and animates the CSI spike, rerouted arcs, and the SPR clock recovering |
| 6.3 | Decision memo panel | Claude's memo rendered with an "every number traceable" footnote linking to the assumption registry |

### Phase 7 — Deck, Video, Hardening (Hours 34–36)
- 8-slide deck mapped 1:1 to judging criteria (structure below)
- 3-minute demo video script (below)
- Freeze a `demo` branch; rehearse the injection flow 3 times

---

## 5. Demo Script (3 Minutes)

1. **0:00–0:20 — The stake.** "India imports 88% of its crude. 42% sails through a strait 33 km wide. Our reserves last 9.5 days." SPR clock on screen.
2. **0:20–0:50 — Steady state.** Map with live flows, CSI gauges green/amber, feed ticker scrolling real headlines.
3. **0:50–1:40 — The event.** Click Inject. Watch: headline lands → Claude extracts a structured event → CSI(Hormuz) spikes 38→78 → CRITICAL band → scenario auto-fires.
4. **1:40–2:30 — The answer.** Rerouting arcs redraw (WAF via Cape, US Gulf, Fujairah). Recommendation table with cost deltas. SPR schedule bridging the gap. Point at the corner: **"Lead time: 87 seconds."**
5. **2:30–3:00 — The close.** Cascade panel: pump price, CAD, GDP impact avoided. "47 days faster to stabilize, per McKinsey. TRINETRA is how an import-dependent economy buys that time."

## 6. Deck Structure (8 Slides)
1. Title + one-liner
2. Problem: 88 / 42 / 9.5 (three numbers, one map)
3. Architecture (the diagram above, cleaned)
4. The CSI — explainable risk, live
5. Scenario cascade — assumptions on the slide, not hidden
6. Optimizer output — the actual reallocation table
7. Demo metrics: lead time, scenario fidelity, response time (maps to rubric)
8. Scale path: Kafka + PostGIS + real AIS + IOCL/BPCL/HPCL pilot

## 7. Risk Register
| Risk | Mitigation |
|---|---|
| Venue wifi dies | Every feed has a deterministic offline fallback; demo runs fully local |
| LLM latency/quota | Signal extraction cached; keyword fallback path tested |
| LP infeasible on stage | Soft constraints with penalty slack; optimizer always returns a plan + feasibility notes |
| Judges challenge a number | Every constant lives in `config/settings.py` with a source comment |

## 8. Production Path (Slide 8 Talking Points)
Prototype JSON store → PostGIS + TimescaleDB · replay feeds → Kafka + real aisstream/Spire AIS · single-node → corridor-sharded workers · add Petronet LNG + gas corridors · integrate with refiner ERPs (SAP) via iPaaS for closed-loop execution.
