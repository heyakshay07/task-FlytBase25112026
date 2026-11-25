"""Tiny dependency-free vector index (hashed bag-of-words + char trigrams + synonyms).

It is a stand-in for real embeddings (CLIP / sentence-transformers + Chroma/Qdrant): the
interface - add(id, text) / search(query, k) - is what a production index would expose.
"""
from __future__ import annotations

import math
import re
import zlib
from collections import Counter

SYNONYMS = {
    "truck": "truck pickup f150 hilux lorry", "pickup": "truck pickup f150 hilux",
    "f150": "truck pickup", "car": "car sedan civic camry hatchback",
    "person": "person man woman people intruder individual figure",
    "intruder": "person trespasser intruder climbing tampering",
    "suspicious": "loitering climbing tampering lurking running ladder crowbar",
    "loitering": "loitering lingering lurking hanging pacing",
    "gate": "gate entrance", "fence": "fence perimeter wall",
    "animal": "animal dog cat fox deer stray", "fox": "animal", "car": "car sedan civic camry hatchback vehicle",
    "break": "tampering climbing intrusion ladder crowbar", "burglar": "intruder climbing tampering ladder",
    "intrusion": "climbing tampering intruder ladder", "someone": "person man woman intruder",
    "theft": "tampering climbing intruder", "steal": "tampering climbing intruder",
    "delivery": "courier package van", "package": "courier delivery parcel",
}
DIM = 4096


STOP = set("a an the on in at to of and or is was were all any show me who what where when did do "
           "there trying property near with for from by".split())


def _weighted(text: str) -> Counter:
    """word=1.0, synonym=0.8, char-trigram=0.15 (trigrams only add typo/plural tolerance)."""
    w: Counter = Counter()
    for word in (x for x in re.findall(r"[a-z0-9]+", text.lower()) if x not in STOP):
        w[zlib.crc32(word.encode()) % DIM] += 1.0
        syns = SYNONYMS.get(word, "").split()
        for syn in syns:   # damp big synonym sets so "person" doesn't swamp the query
            w[zlib.crc32(syn.encode()) % DIM] += 1.6 / max(len(syns), 1) ** 0.5
        padded = f"#{word}#"
        for i in range(len(padded) - 2):
            w[zlib.crc32(padded[i:i + 3].encode()) % DIM] += 0.15
    return w


def _vec(text: str) -> dict[int, float]:
    # crc32 (not built-in hash) so vectors are identical across processes
    counts = _weighted(text)
    norm = math.sqrt(sum(c * c for c in counts.values())) or 1.0
    return {k: v / norm for k, v in counts.items()}


class SemanticIndex:
    def __init__(self) -> None:
        self._vecs: dict[int, dict[int, float]] = {}

    def add(self, item_id: int, text: str) -> None:
        self._vecs[item_id] = _vec(text)

    def search(self, query: str, k: int = 5) -> list[tuple[int, float]]:
        q = _vec(query)
        scored = []
        for item_id, v in self._vecs.items():
            small, big = (q, v) if len(q) < len(v) else (v, q)
            s = sum(w * big.get(i, 0.0) for i, w in small.items())
            if s > 0:
                scored.append((item_id, s))
        scored.sort(key=lambda p: -p[1])
        return scored[:k]

    def __len__(self) -> int:
        return len(self._vecs)
