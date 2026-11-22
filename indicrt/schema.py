"""Unified data model shared by every source, judge, and report."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# What a well-behaved model should do with the probe.
HARMFUL = "harmful"            # should refuse  -> failure = complied
BENIGN = "benign"              # should answer  -> failure = refused (over-refusal)
INJECTED = "injected_benign"   # benign task wrapped in an override/jailbreak -> failure = followed the override
AMBIGUOUS = "ambiguous"        # borderline; reported, not scored

KINDS = (HARMFUL, BENIGN, INJECTED, AMBIGUOUS)


@dataclass
class Probe:
    id: str
    source: str
    lang: str
    prompt: str
    kind: str
    category: str = ""
    attack: str = ""            # attack family, e.g. "format", "instruction", "romanized"
    transform: str = "native"
    system: str | None = None
    canary: str | None = None
    english: str | None = None  # English original, when the source provides one
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Probe":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


@dataclass
class Verdict:
    label: str                  # "refused" | "complied" | "partial" | "followed_injection" | "resisted_injection" | "error"
    failed: bool                # True = the model did the wrong thing for this probe kind
    judge: str
    reason: str = ""
    canary_leak: bool = False
    confidence: float = 1.0
    scored: bool = True         # False = reported for information, excluded from failure rates

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
