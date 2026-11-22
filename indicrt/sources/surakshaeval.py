"""SurakshaEval (Banerjee et al., AIES 2026) - gated dataset, opt-in.

Human-written, regionally grounded safety questions in 10 Indian languages,
paired with English. The dataset is gated on Hugging Face: accept its terms at
https://huggingface.co/datasets/SurakshaAI/SurakshaEval, then export HF_TOKEN.
indicrt never redistributes it; it downloads with your own token.
"""

from __future__ import annotations

import hashlib
import json
import os

from .. import fetch, langs as L
from ..schema import AMBIGUOUS, HARMFUL, Probe

DATASET = "SurakshaAI/SurakshaEval"

INFO = {
    "name": "SurakshaEval",
    "license": "Gated (accept terms on Hugging Face)",
    "paper": "https://ojs.aaai.org/index.php/AIES/article/view/43143",
    "repo": "https://github.com/debobanerjee/SurakshaEval",
    "dataset": f"https://huggingface.co/datasets/{DATASET}",
    "languages": ["as", "bn", "gu", "hi", "kn", "ml", "mr", "pa", "ta", "te"],
    "size": "human-written regional prompts, 10 languages",
    "citation": "Banerjee et al. SurakshaEval: An Indic Safety Benchmark for Multilingual LLMs. AIES 2026.",
    "gated": True,
}


def _hf_files(token: str) -> list[str]:
    import urllib.request

    req = urllib.request.Request(
        f"https://huggingface.co/api/datasets/{DATASET}",
        headers={"Authorization": f"Bearer {token}", "User-Agent": fetch.USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        info = json.load(r)
    return [s["rfilename"] for s in info.get("siblings", []) if s["rfilename"].endswith((".jsonl", ".json"))]


def load(langs: set[str] | None, offline: bool = False):
    root = fetch.cache_dir() / "surakshaeval"
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    files = sorted(root.rglob("*.json*")) if root.exists() else []
    if not files:
        if offline or not token:
            raise RuntimeError(
                "SurakshaEval is gated. Accept the terms at "
                f"https://huggingface.co/datasets/{DATASET} and set HF_TOKEN, then rerun."
            )
        for rel in _hf_files(token):
            fetch.fetch(
                f"https://huggingface.co/datasets/{DATASET}/resolve/main/{rel}",
                root / rel,
                headers={"Authorization": f"Bearer {token}"},
            )
        files = sorted(root.rglob("*.json*"))
    for p in files:
        with open(p, encoding="utf-8") as f:
            text = f.read()
        rows = [json.loads(x) for x in text.splitlines() if x.strip()] if p.suffix == ".jsonl" else json.loads(text)
        if isinstance(rows, dict):
            rows = rows.get("data") or rows.get("rows") or []
        for r in rows:
            q = r.get("question_indic") or r.get("prompt")
            if not q:
                continue
            try:
                code = L.to_code(r.get("language") or r.get("region") or "")
            except KeyError:
                continue
            if langs and code not in langs:
                continue
            h = hashlib.sha1(f"{code}|{q}".encode()).hexdigest()[:10]
            # Schema per the upstream download script; rows without a risk area are not scored.
            kind = HARMFUL if (r.get("risk_area") or r.get("type_of_harm")) else AMBIGUOUS
            yield Probe(
                id=f"suraksha-{code}-{r.get('id') or h}",
                source="surakshaeval",
                lang=code,
                prompt=q,
                kind=kind,
                category=(r.get("risk_area") or r.get("type_of_harm") or "").strip().lower().replace(" ", "_"),
                attack="direct",
                english=r.get("question_en"),
                meta={"region": r.get("region"), "question_type": r.get("question_type")},
            )
