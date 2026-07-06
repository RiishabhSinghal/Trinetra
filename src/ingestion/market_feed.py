"""Brent price and volatility signal. Live via yfinance (BZ=F), synthetic offline."""

from __future__ import annotations

import random
from dataclasses import dataclass

from config.settings import ASSUMPTIONS, OFFLINE_MODE


@dataclass
class MarketState:
    brent_usd: float
    day_change_pct: float
    vol_20d_pct: float  # annualized-ish rolling volatility proxy

    @property
    def stress(self) -> float:
        """Market stress 0-1: blends the day move and the volatility regime.
        An 8% single-session move (the 2025 episode) maps to ~0.85."""
        move = min(1.0, abs(self.day_change_pct) / 10.0)
        vol = min(1.0, self.vol_20d_pct / 60.0)
        return round(0.65 * move + 0.35 * vol, 4)


class MarketFeed:
    def __init__(self, offline: bool | None = None):
        self.offline = OFFLINE_MODE if offline is None else offline
        self._shock_pct: float = 0.0  # scenario hook

    def apply_shock(self, pct: float) -> None:
        self._shock_pct = pct

    def reset(self) -> None:
        self._shock_pct = 0.0

    def snapshot(self) -> MarketState:
        base = ASSUMPTIONS["brent_baseline_usd"].value
        if not self.offline:
            live = self._fetch_live()
            if live is not None:
                base, day_chg, vol = live
                return MarketState(
                    brent_usd=round(base * (1 + self._shock_pct), 2),
                    day_change_pct=round(day_chg + self._shock_pct * 100, 2),
                    vol_20d_pct=vol,
                )
        rng = random.Random(11)
        day_chg = rng.gauss(0.1, 0.9) + self._shock_pct * 100
        return MarketState(
            brent_usd=round(base * (1 + self._shock_pct), 2),
            day_change_pct=round(day_chg, 2),
            vol_20d_pct=round(28 + abs(self._shock_pct) * 90, 1),
        )

    @staticmethod
    def _fetch_live() -> tuple[float, float, float] | None:
        try:
            import yfinance as yf

            hist = yf.Ticker("BZ=F").history(period="1mo")["Close"]
            if len(hist) < 5:
                return None
            price = float(hist.iloc[-1])
            day_chg = float((hist.iloc[-1] / hist.iloc[-2] - 1) * 100)
            vol = float(hist.pct_change().std() * (252 ** 0.5) * 100)
            return price, day_chg, vol
        except Exception:
            return None
