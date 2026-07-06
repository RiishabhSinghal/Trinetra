"""Web console entrypoint.

Serves the TRINETRA command console (dashboard/web/) on top of the existing
API without modifying src/api/main.py. Routes registered here resolve before
the static mount, so all API endpoints keep working.

Run:   uvicorn dashboard.serve:app --port 8000
Open:  http://localhost:8000
"""

from __future__ import annotations

import os
from dataclasses import asdict

from fastapi.staticfiles import StaticFiles

from config.settings import ASSUMPTIONS, CSI_BANDS, CSI_WEIGHTS
from src.api.main import app, orch

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


@app.get("/assumptions")
def assumptions():
    """The audit trail: every constant the model reasons with, with sources."""
    return {
        "assumptions": [
            {"key": k, "value": a.value, "unit": a.unit, "source": a.source}
            for k, a in ASSUMPTIONS.items()
        ],
        "csi_weights": CSI_WEIGHTS,
        "csi_bands": CSI_BANDS,
    }


@app.get("/market")
def market():
    """Live market strip: Brent, day change, volatility, stress score."""
    m = orch.market.snapshot()
    return {**asdict(m), "stress": m.stress}


# Mounted last: API routes above take precedence, everything else is the console.
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="console")
