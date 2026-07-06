"""TRINETRA REST API.

Run:  uvicorn src.api.main:app --reload --port 8000
Docs: http://localhost:8000/docs
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.agents.orchestrator import Orchestrator
from src.scenarios.library import SCENARIOS

app = FastAPI(
    title="TRINETRA",
    description="AI-driven energy supply chain resilience for import-dependent economies",
    version="0.1.0",
)
orch = Orchestrator()


class InjectRequest(BaseModel):
    headline: str | None = None


@app.get("/health")
def health():
    return {"status": "watching", "system": "TRINETRA"}


@app.get("/signals")
def signals():
    """Poll feeds, extract events, return the structured signal frame."""
    return {"events": orch.poll()}


@app.get("/csi")
def csi():
    """Corridor Stress Index for every corridor, with factor breakdowns."""
    return {"readings": orch.csi_all()}


@app.get("/scenarios")
def scenarios():
    return {s.id: {"name": s.name, "notes": s.notes} for s in SCENARIOS.values()}


@app.post("/scenarios/{scenario_id}/run")
def run_scenario(scenario_id: str):
    if scenario_id not in SCENARIOS:
        raise HTTPException(404, f"Unknown scenario: {scenario_id}")
    return asdict(orch.run_scenario(scenario_id))


@app.post("/demo/inject")
def demo_inject(req: InjectRequest):
    """The judge-facing trigger: inject a crisis headline, get the full
    recommendation back with the measured signal-to-recommendation lead time."""
    return asdict(orch.inject_and_respond(req.headline))


@app.get("/recommendation")
def recommendation():
    if orch.last_recommendation is None:
        raise HTTPException(404, "No recommendation yet. POST /demo/inject first.")
    return asdict(orch.last_recommendation)


@app.post("/reset")
def reset():
    orch.reset()
    return {"status": "reset to steady state"}
