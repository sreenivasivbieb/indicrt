"""Build the probe set, send it to the target, judge each reply, and write results."""

from __future__ import annotations

import json
import random
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from . import judges, sources, transforms
from .schema import AMBIGUOUS, INJECTED, Probe


@dataclass
class Plan:
    sources: list[str]
    langs: set[str] | None
    transforms: list[str] = field(default_factory=lambda: ["native"])
    kinds: set[str] | None = None
    sample: int | None = 25          # per (source, lang, kind, attack, transform) group; None = everything
    seed: int = 7
    include_ambiguous: bool = False
    offline: bool = False


def build(plan: Plan) -> list[Probe]:
    base = sources.load_all(plan.sources, plan.langs, offline=plan.offline)
    if plan.kinds:
        base = [p for p in base if p.kind in plan.kinds]
    elif not plan.include_ambiguous:
        base = [p for p in base if p.kind != AMBIGUOUS]
    out: list[Probe] = []
    for t in plan.transforms:
        for p in base:
            q = transforms.apply(p, t)
            if q is not None:
                out.append(q)
    if plan.sample:
        rng = random.Random(plan.seed)
        groups: dict[tuple, list[Probe]] = defaultdict(list)
        for p in out:
            groups[(p.source, p.lang, p.kind, p.attack.split("_")[0], p.transform)].append(p)
        # sample the same base prompts across transforms so native vs romanized compare like for like
        picked: list[Probe] = []
        chosen_base: dict[tuple, set[str]] = {}
        for key in sorted(groups, key=lambda k: (k[4] != "native",) + k):
            items = groups[key]
            bkey = key[:4]
            if bkey in chosen_base:
                sel = [p for p in items if p.id.split("~")[0] in chosen_base[bkey]]
                if len(sel) < min(plan.sample, len(items)):
                    rest = [p for p in items if p not in sel]
                    sel += rng.sample(rest, min(plan.sample - len(sel), len(rest)))
            else:
                sel = rng.sample(items, min(plan.sample, len(items)))
                chosen_base[bkey] = {p.id.split("~")[0] for p in sel}
            picked.extend(sel)
        out = picked
    return out


def _system_for(p: Probe, user_system: str | None) -> str | None:
    if p.kind == INJECTED:
        return f"{user_system}\n\n{judges.INJECTION_SYSTEM_CONTRACT}" if user_system else judges.INJECTION_SYSTEM_CONTRACT
    return user_system or p.system


def run(
    probes: list[Probe],
    target,
    out_dir: Path,
    *,
    refusal_judge=None,
    system: str | None = None,
    workers: int = 4,
    resume: bool = True,
    quiet: bool = False,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    res_path = out_dir / "results.jsonl"
    done: set[str] = set()
    if resume and res_path.exists():
        for line in res_path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                if r.get("verdict", {}).get("label") != "error":
                    done.add(r["probe"]["id"])
            except (json.JSONDecodeError, KeyError):
                pass
    todo = [p for p in probes if p.id not in done]
    refusal_judge = refusal_judge or judges.KeywordJudge()
    lock = threading.Lock()
    n, total, t0 = 0, len(todo), time.time()

    def one(p: Probe):
        sys_prompt = _system_for(p, system)
        err, resp = None, None
        t = time.time()
        try:
            resp = target.generate(p.prompt, system=sys_prompt, lang=p.lang)
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
        latency = round(time.time() - t, 3)
        v = judges.judge(p, resp, refusal_judge, error=err)
        return {"probe": p.to_dict(), "system": sys_prompt, "response": resp, "error": err,
                "latency_s": latency, "verdict": v.to_dict(), "target": target.spec}

    mode = "a" if resume else "w"
    with open(res_path, mode, encoding="utf-8") as f, ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = [ex.submit(one, p) for p in todo]
        for fut in as_completed(futs):
            rec = fut.result()
            with lock:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                n += 1
                if not quiet and (n % max(10, total // 20) == 0 or n == total):
                    rate = n / max(time.time() - t0, 1e-6)
                    print(f"\r  {n}/{total} probes  ({rate:.1f}/s)", end="", file=sys.stderr)
    if not quiet and total:
        print(file=sys.stderr)
    if not quiet and done:
        print(f"  resumed: {len(done)} probes already done", file=sys.stderr)
    return res_path


def load_results(out_dir: Path) -> list[dict]:
    p = out_dir / "results.jsonl" if out_dir.is_dir() else out_dir
    latest: dict[str, dict] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            latest[r["probe"]["id"]] = r  # last write wins (resumed reruns)
    return list(latest.values())
