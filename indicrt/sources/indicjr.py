"""IndicJR / Indic Jailbreak Robustness (Pattnayak & Chowdhuri, 2026) - MIT licensed.

~45k prompts across 12 Indic & South Asian languages:
  * attacked-benign: benign tasks wrapped in override instructions
    (format override, "SECRET-MODE", role-play, translate-then-do), including
    cross-lingual and romanized wrappers (E2 transfer)
  * clean-benign: same tasks without wrappers (over-refusal baseline)
  * clean-harmful: unsafe topics carrying a canary token for leakage checks

Paper: https://arxiv.org/abs/2602.16832
Repo:  https://github.com/ppattnayak/indicjr
"""

from __future__ import annotations

import ast
import hashlib
import json

from .. import fetch
from ..schema import BENIGN, HARMFUL, INJECTED, Probe

REPO = "ppattnayak/indicjr"
SHA = "6db30deb1677636e865af6fbecef024526d91650"
LANGS = ["hi", "bn", "ta", "te", "ml", "mr", "gu", "kn", "or", "ur", "ne", "pa"]

INFO = {
    "name": "IndicJR (IJR)",
    "license": "MIT",
    "paper": "https://arxiv.org/abs/2602.16832",
    "repo": f"https://github.com/{REPO}",
    "commit": SHA,
    "languages": LANGS,
    "size": "~45,000 prompts (JSON + FREE tracks)",
    "citation": "Pattnayak & Chowdhuri. IndicJR: A Judge-Free Benchmark of Jailbreak Robustness in South Asian Languages. 2026.",
}

# (track, split) -> path template. "core" files are small; "full" adds the large JSON-track sets.
FILES = {
    ("free", "attacked"): "prompts_free/{lang}.jsonl",
    ("free", "benign"): "prompts_free/clean_benign_{lang}.jsonl",
    ("free", "harmful"): "prompts_free/clean_harmful_{lang}.jsonl",
    ("json", "attacked_e1"): "prompts_json/{lang}.E1.jsonl",
    ("json", "attacked_e2"): "prompts_json/{lang}.E2xfer.jsonl",
    ("json", "benign"): "prompts_json_clean_benign_clean_harmful/benign/{lang}.jsonl",
    ("json", "harmful"): "prompts_json_clean_benign_clean_harmful/harmful/{lang}.jsonl",
}


def _path(lang: str, rel: str):
    return fetch.cache_dir() / "indicjr" / SHA / rel.format(lang=lang)


def _meta(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            v = ast.literal_eval(raw)
            return v if isinstance(v, dict) else {}
        except (ValueError, SyntaxError):
            return {}
    return {}


def _rows(lang: str, key, offline: bool):
    rel = FILES[key]
    p = _path(lang, rel)
    if not p.exists():
        if offline:
            raise RuntimeError("IndicJR not cached; run `indicrt fetch` first")
        fetch.fetch(fetch.github_raw(REPO, SHA, rel.format(lang=lang)), p)
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _hid(*parts) -> str:
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:10]


def load(langs: set[str] | None, offline: bool = False):
    for lang in LANGS:
        if langs and lang not in langs:
            continue
        for key in FILES:
            track, split = key
            for r in _rows(lang, key, offline):
                text = r.get("final_prompt") or r.get("prompt") or r.get("content") or ""
                if not text.strip():
                    continue
                meta = _meta(r.get("metadata"))
                meta.update({"track": track, "mode": r.get("mode", ""), "severity": r.get("severity", "")})
                if split.startswith("attacked"):
                    fam = r.get("family", "")
                    attack = fam
                    if meta.get("xfer_source"):
                        attack = f"{fam}_xfer"
                    yield Probe(
                        id=r.get("id") or f"ijr-{lang}-{_hid(text)}",
                        source="indicjr",
                        lang=lang,
                        prompt=text,
                        kind=INJECTED,
                        category=f"override_{fam}",
                        attack=attack,
                        meta=meta,
                    )
                elif split == "benign":
                    yield Probe(
                        id=r.get("prompt_id") or f"ijr-{lang}-cb-{track}-{_hid(text)}",
                        source="indicjr",
                        lang=lang,
                        prompt=text,
                        kind=BENIGN,
                        category=f"clean_benign_{r.get('ttype', 'task')}",
                        attack="direct",
                        meta=meta,
                    )
                else:
                    canary = r.get("canary")
                    canary = canary if canary and canary != "None" else None
                    meta["score"] = "canary"  # judge-free scoring: leaking the canary = failure
                    yield Probe(
                        id=r.get("prompt_id") or f"ijr-{lang}-ch-{track}-{_hid(text)}",
                        source="indicjr",
                        lang=lang,
                        prompt=text,
                        kind=HARMFUL,
                        category=r.get("intent") or "clean_harmful",
                        attack="direct",
                        canary=canary,
                        meta=meta,
                    )
