"""IndicSafe (Pattnayak & Chowdhuri, 2026) - MIT licensed.

6,000 human-translated safety prompts: 500 per language x 12 languages, with the
English original for every prompt. Mix of harmful categories and harmless
controls (used to measure over-refusal).

Paper: https://arxiv.org/abs/2603.17915
Repo:  https://github.com/ppattnayak/indicsafe
"""

from __future__ import annotations

import csv
import hashlib

from .. import fetch, langs as L
from ..schema import AMBIGUOUS, BENIGN, HARMFUL, Probe

REPO = "ppattnayak/indicsafe"
SHA = "b889fa49237d255af32a67206f9f7a8c8720bdab"
PATH = "data/Full_translated_prompts.csv"

INFO = {
    "name": "IndicSafe",
    "license": "MIT",
    "paper": "https://arxiv.org/abs/2603.17915",
    "repo": f"https://github.com/{REPO}",
    "commit": SHA,
    "languages": ["hi", "bn", "ta", "te", "ml", "mr", "gu", "kn", "or", "ur", "ne", "pa"],
    "size": "6,000 prompts (500 x 12 languages)",
    "citation": "Pattnayak & Chowdhuri. IndicSafe: A Benchmark for Evaluating Multilingual LLM Safety in South Asia. 2026.",
}

BENIGN_CATS = {"harmless control prompts", "harmless control"}
AMBIGUOUS_CATS = {"tricky ambiguous prompts"}


def _kind(category: str) -> str:
    c = category.strip().lower()
    if c in BENIGN_CATS:
        return BENIGN
    if c in AMBIGUOUS_CATS:
        return AMBIGUOUS
    return HARMFUL


def _slug(category: str) -> str:
    c = category.strip().lower()
    if c in BENIGN_CATS:
        return "harmless_control"
    return c.replace("&", "and").replace("/", "_").replace(" ", "_")


def local_path():
    return fetch.cache_dir() / "indicsafe" / SHA / "prompts.csv"


def load(langs: set[str] | None, offline: bool = False):
    path = local_path()
    if not path.exists():
        if offline:
            raise RuntimeError("IndicSafe not cached; run `indicrt fetch` first")
        fetch.fetch(fetch.github_raw(REPO, SHA, PATH), path)
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                code = L.to_code(row["Language"])
            except KeyError:
                continue
            if langs and code not in langs:
                continue
            text = (row.get("Translated_Prompt") or "").strip()
            if not text:
                continue
            cat = row.get("Category") or row.get("category") or ""
            h = hashlib.sha1(f"{code}|{row.get('Prompt','')}|{text}".encode()).hexdigest()[:10]
            yield Probe(
                id=f"indicsafe-{code}-{h}",
                source="indicsafe",
                lang=code,
                prompt=text,
                kind=_kind(cat),
                category=_slug(cat),
                attack="direct",
                english=(row.get("Prompt") or "").strip() or None,
            )
