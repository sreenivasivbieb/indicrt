"""Dataset sources. Each source turns an upstream benchmark into unified Probes."""

from __future__ import annotations

from typing import Iterable

from ..schema import Probe
from . import indicjr, indicsafe, surakshaeval

# name -> module with: INFO dict, load(langs, offline) -> Iterable[Probe]
SOURCES = {
    "indicsafe": indicsafe,
    "indicjr": indicjr,
    "surakshaeval": surakshaeval,
}

DEFAULT_SOURCES = ("indicsafe", "indicjr")  # surakshaeval is gated: opt in with HF_TOKEN


def parse_sources(arg: str | None) -> list[str]:
    if not arg:
        return list(DEFAULT_SOURCES)
    if arg.strip().lower() == "all":
        return list(SOURCES)
    names = [x.strip().lower() for x in arg.split(",") if x.strip()]
    for n in names:
        if n not in SOURCES:
            raise KeyError(f"Unknown source {n!r}. Available: {', '.join(SOURCES)}")
    return names


def load_all(names: Iterable[str], langs: set[str] | None, offline: bool = False) -> list[Probe]:
    out: list[Probe] = []
    for n in names:
        out.extend(SOURCES[n].load(langs, offline=offline))
    return out
