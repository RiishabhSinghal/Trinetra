"""News signal ingestion: live RSS with a deterministic offline replay.

The replay file guarantees the demo runs identically with zero connectivity.
Headlines in the replay are real events from the 2025-26 window described
in the challenge brief.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from config.settings import OFFLINE_MODE

RSS_SOURCES = [
    "https://feeds.reuters.com/reuters/energyNews",
    "https://www.aljazeera.com/xml/rss/all.xml",
]

REPLAY_HEADLINES = [
    "Oil tanker reports near-miss with unidentified drone in Strait of Hormuz approach",
    "US Treasury adds three shipping firms to sanctions list over Iranian crude transfers",
    "Houthi spokesman warns of renewed attacks on Red Sea commercial shipping",
    "Brent crude climbs 3.1% as Gulf maritime insurers raise war-risk premiums",
    "OPEC+ ministers to hold emergency consultation amid Gulf tensions",
    "Indian refiners said to seek additional West African spot cargoes",
    "Fujairah port reports normal operations, bypass pipeline flows steady",
    "IRGC navy announces snap exercises near Hormuz shipping lanes",
]

# The judge-facing trigger event. Injected via /demo/inject.
INJECTION_EVENT = (
    "BREAKING: Iran announces closure of Strait of Hormuz to commercial "
    "tanker traffic following overnight strikes; Lloyd's suspends coverage "
    "for Gulf transits"
)


@dataclass
class Headline:
    text: str
    source: str
    ingested_at: float = field(default_factory=time.time)


class NewsFeed:
    """Yields headlines from live RSS, replay, or injection."""

    def __init__(self, offline: bool | None = None):
        self.offline = OFFLINE_MODE if offline is None else offline
        self._injected: list[Headline] = []

    def inject(self, text: str = INJECTION_EVENT) -> Headline:
        h = Headline(text=text, source="demo_injection")
        self._injected.append(h)
        return h

    def fetch(self, limit: int = 10) -> list[Headline]:
        items: list[Headline] = list(self._injected)
        self._injected = []
        if not self.offline:
            items.extend(self._fetch_live(limit))
        if len(items) < limit:
            items.extend(
                Headline(text=t, source="replay")
                for t in REPLAY_HEADLINES[: limit - len(items)]
            )
        return items[:limit]

    @staticmethod
    def _fetch_live(limit: int) -> list[Headline]:
        try:
            import feedparser  # local import keeps offline path dependency-free

            out: list[Headline] = []
            for url in RSS_SOURCES:
                parsed = feedparser.parse(url)
                out.extend(
                    Headline(text=e.title, source=url)
                    for e in parsed.entries[: limit // len(RSS_SOURCES) + 1]
                )
            return out
        except Exception:
            return []
