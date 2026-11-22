"""indicrt command line."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from . import __version__, judges, langs as L, report, runner, sources, targets, transforms

EXAMPLES = """examples:
  indicrt run --target openai:gpt-4o-mini --langs hi,ta --transforms native,romanized
  indicrt run --target ollama:llama3.1 --sample 10
  indicrt run --target http://localhost:8000/chat --system-file my_bot_prompt.txt
  indicrt run --target compat:sarvam-m@https://api.sarvam.ai/v1 --judge llm:openai:gpt-4o-mini
  indicrt export --format promptfoo --out promptfoo-indic/
  indicrt garak-install && garak --target_type openai --target_name gpt-4o-mini --spec probes.indic.HarmfulHi
"""


def _plan(a, sample_default=25) -> runner.Plan:
    kinds = {k.strip() for k in a.kinds.split(",")} if getattr(a, "kinds", None) else None
    sample = None if getattr(a, "full", False) else (a.sample if a.sample is not None else sample_default)
    return runner.Plan(
        sources=sources.parse_sources(a.sources),
        langs=L.parse_langs(a.langs),
        transforms=transforms.parse(a.transforms),
        kinds=kinds,
        sample=sample or None,
        seed=a.seed,
        include_ambiguous=getattr(a, "include_ambiguous", False),
    )


def _add_selection(p):
    p.add_argument("--langs", help="comma list of language codes (default: all). e.g. hi,ta,bn")
    p.add_argument("--sources", help="comma list: indicsafe,indicjr,surakshaeval or 'all' (default: indicsafe,indicjr)")
    p.add_argument("--transforms", default="native",
                   help=f"comma list of {', '.join(transforms.TRANSFORMS)} or 'all' (default: native)")
    p.add_argument("--kinds", help="comma list of harmful,benign,injected_benign,ambiguous")
    p.add_argument("--sample", type=int, default=None, help="prompts per (source, language, kind, attack, transform) group (default 25)")
    p.add_argument("--full", action="store_true", help="use every prompt (large: ~50k per transform)")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--include-ambiguous", action="store_true", help="also send borderline prompts (reported, not scored)")


def cmd_sources(a):
    for name, mod in sources.SOURCES.items():
        i = mod.INFO
        star = " (default)" if name in sources.DEFAULT_SOURCES else " (opt-in)"
        print(f"{name}{star}\n  {i['name']} - {i['size']}\n  license: {i['license']}\n  languages: {', '.join(i['languages'])}"
              f"\n  paper: {i['paper']}\n  repo: {i['repo']}" + (f"\n  commit: {i['commit']}" if i.get("commit") else "") + "\n")


def cmd_fetch(a):
    names = sources.parse_sources(a.sources)
    probes = sources.load_all(names, L.parse_langs(a.langs))
    c = Counter((p.source, p.kind) for p in probes)
    for (s, k), n in sorted(c.items()):
        print(f"  {s:<14}{k:<17}{n:>7}")
    from . import fetch

    print(f"cached in {fetch.cache_dir()}")


def cmd_plan(a):
    probes = runner.build(_plan(a))
    print(f"{len(probes)} probes")
    by_lang = Counter(p.lang for p in probes)
    by_kind = Counter(p.kind for p in probes)
    by_t = Counter(p.transform for p in probes)
    print("  by language: " + ", ".join(f"{L.name(k)} {v}" for k, v in sorted(by_lang.items())))
    print("  by kind:     " + ", ".join(f"{k} {v}" for k, v in sorted(by_kind.items())))
    print("  by transform:" + ", ".join(f" {k} {v}" for k, v in sorted(by_t.items())))
    if a.show:
        for p in probes[: a.show]:
            print(f"\n[{p.id}] {p.lang} {p.kind} {p.transform}\n{p.prompt[:300]}")


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-")[:60]


def _target_factory(a):
    return lambda spec: targets.make(spec, temperature=0.0, max_tokens=256, timeout=a.timeout)


def cmd_run(a):
    target = targets.make(a.target, temperature=a.temperature, max_tokens=a.max_tokens, timeout=a.timeout)
    rj = judges.make(a.judge, _target_factory(a))
    system = Path(a.system_file).read_text(encoding="utf-8") if a.system_file else a.system
    out = Path(a.out) if a.out else Path("runs") / f"{datetime.now():%Y%m%d-%H%M%S}-{_slug(a.target)}"
    probes = runner.build(_plan(a))
    if not probes:
        sys.exit("No probes selected. Check --langs/--sources/--kinds.")
    print(f"indicrt {__version__}: {len(probes)} probes -> {a.target}  (judge: {rj.name})", file=sys.stderr)
    (out).mkdir(parents=True, exist_ok=True)
    (out / "run.json").write_text(json.dumps({
        "target": a.target, "judge": a.judge or "keyword", "argv": sys.argv[1:], "probes": len(probes),
        "system_prompt_set": bool(system), "version": __version__,
        "sources": {n: sources.SOURCES[n].INFO for n in sources.parse_sources(a.sources)},
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    runner.run(probes, target, out, refusal_judge=rj, system=system, workers=a.workers,
               resume=not a.no_resume, quiet=a.quiet)
    results = [r for r in runner.load_results(out) if r["probe"]["id"] in {p.id for p in probes}]
    s = report.write_all(out, results)
    print(report.terminal(s))
    print(f"\n  report: {out / 'report.html'}\n  data:   {out / 'results.jsonl'}")
    return _gate(a, s)


def _gate(a, s) -> int:
    o = s["overall"]
    bad = []
    if a.fail_under is not None and (o["safety_score"] or 0) < a.fail_under:
        bad.append(f"safety score {o['safety_score']} < {a.fail_under}")
    if a.max_over_refusal is not None and (o["over_refusal_rate"] or 0) > a.max_over_refusal:
        bad.append(f"over-refusal {o['over_refusal_rate']} > {a.max_over_refusal}")
    if a.max_injection is not None and (o["injection_follow_rate"] or 0) > a.max_injection:
        bad.append(f"injection follow rate {o['injection_follow_rate']} > {a.max_injection}")
    if s["errors"] and s["errors"] > 0.2 * max(s["probes"], 1):
        print(f"\n  warning: {s['errors']} of {s['probes']} requests failed - check the target", file=sys.stderr)
    if bad:
        print("\nFAILED: " + "; ".join(bad), file=sys.stderr)
        return 1
    return 0


def cmd_report(a):
    out = Path(a.run_dir)
    results = runner.load_results(out)
    s = report.write_all(out, results)
    print(report.terminal(s))
    print(f"\n  report: {out / 'report.html'}")
    return _gate(a, s)


def cmd_compare(a):
    rows = []
    for d in a.runs:
        s = json.loads((Path(d) / "summary.json").read_text(encoding="utf-8"))
        rows.append((d, s))
    langs = sorted({l for _, s in rows for l in s["languages"]})
    head = f"{'Language':<11}" + "".join(f"{', '.join(s['targets'])[:22]:>24}" for _, s in rows)
    print("Safety score by language (higher is better)\n" + head)
    for l in langs:
        cells = []
        for _, s in rows:
            v = s["languages"].get(l, {}).get("safety_score")
            cells.append(f"{'-' if v is None else f'{v:.1f}':>24}")
        print(f"{L.name(l):<11}" + "".join(cells))
    print(f"{'OVERALL':<11}" + "".join(f"{str(s['overall']['safety_score']):>24}" for _, s in rows))


def cmd_export(a):
    from . import export

    probes = runner.build(_plan(a))
    out = Path(a.out)
    if a.format == "promptfoo":
        export.to_promptfoo(probes, out, provider=a.provider, llm_rubric=a.llm_rubric)
        print(f"wrote {len(probes)} tests to {out}/  ->  cd {out} && npx promptfoo@latest eval")
    elif a.format == "jsonl":
        export.to_jsonl(probes, out)
        print(f"wrote {len(probes)} probes to {out}")
    elif a.format == "csv":
        export.to_csv(probes, out)
        print(f"wrote {len(probes)} probes to {out}")


def cmd_garak_install(a):
    from .integrations import garak_plugin

    for p in garak_plugin.install(a.garak_dir):
        print(f"installed {p}")
    print("try:  garak --target_type openai --target_name gpt-4o-mini --spec probes.indic.HarmfulHi,probes.indic.InjectedHi")


def cmd_garak_uninstall(a):
    from .integrations import garak_plugin

    for p in garak_plugin.uninstall(a.garak_dir):
        print(f"removed {p}")


def cmd_romanize(a):
    lang = L.to_code(a.lang)
    print(transforms.romanize(a.text, lang))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="indicrt", description="Red-team LLM apps in Indian languages.",
                                 epilog=EXAMPLES, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"indicrt {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("sources", help="list datasets, licenses and citations")
    p.set_defaults(fn=cmd_sources)

    p = sub.add_parser("fetch", help="download and cache datasets")
    p.add_argument("--sources")
    p.add_argument("--langs")
    p.set_defaults(fn=cmd_fetch)

    p = sub.add_parser("plan", help="show which probes a run would send (dry run)")
    _add_selection(p)
    p.add_argument("--show", type=int, default=0, help="print the first N prompts")
    p.set_defaults(fn=cmd_plan)

    p = sub.add_parser("run", help="run probes against a target and write a report",
                       description=targets.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target", "-t", required=True, help="e.g. openai:gpt-4o-mini, ollama:llama3.1, http://localhost:8000/chat")
    p.add_argument("--judge", default="keyword", help="keyword (default) or llm:<target-spec>")
    _add_selection(p)
    p.add_argument("--system", help="system prompt to test with (your product's prompt)")
    p.add_argument("--system-file", help="read the system prompt from a file")
    p.add_argument("--out", "-o", help="output directory (default runs/<time>-<target>)")
    p.add_argument("--workers", "-w", type=int, default=4)
    p.add_argument("--max-tokens", type=int, default=400)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--timeout", type=float, default=120)
    p.add_argument("--no-resume", action="store_true", help="start fresh instead of continuing an existing --out")
    p.add_argument("--quiet", "-q", action="store_true")
    for q in (p,):
        q.add_argument("--fail-under", type=float, help="exit 1 if safety score < this (CI gate)")
        q.add_argument("--max-over-refusal", type=float, help="exit 1 if over-refusal rate > this (0-1)")
        q.add_argument("--max-injection", type=float, help="exit 1 if injection follow rate > this (0-1)")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("report", help="rebuild the report for a run directory")
    p.add_argument("run_dir")
    p.add_argument("--fail-under", type=float)
    p.add_argument("--max-over-refusal", type=float)
    p.add_argument("--max-injection", type=float)
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("compare", help="compare safety scores across runs (models or versions)")
    p.add_argument("runs", nargs="+")
    p.set_defaults(fn=cmd_compare)

    p = sub.add_parser("export", help="export probes for promptfoo or as JSONL/CSV")
    p.add_argument("--format", "-f", choices=["promptfoo", "jsonl", "csv"], required=True)
    p.add_argument("--out", "-o", required=True)
    p.add_argument("--provider", default="openai:gpt-4o-mini", help="promptfoo provider id to put in the config")
    p.add_argument("--llm-rubric", action="store_true", help="add promptfoo llm-rubric assertions to harmful tests")
    _add_selection(p)
    p.set_defaults(fn=cmd_export)

    p = sub.add_parser("garak-install", help="install indic.* probes and detectors into garak")
    p.add_argument("--garak-dir", help="path to the garak package directory (auto-detected)")
    p.set_defaults(fn=cmd_garak_install)
    p = sub.add_parser("garak-uninstall", help="remove indic.* plugins from garak")
    p.add_argument("--garak-dir")
    p.set_defaults(fn=cmd_garak_uninstall)

    p = sub.add_parser("romanize", help="romanize Indic text the way the 'romanized' transform does")
    p.add_argument("--lang", "-l", required=True)
    p.add_argument("text")
    p.set_defaults(fn=cmd_romanize)

    a = ap.parse_args(argv)
    try:
        return a.fn(a) or 0
    except (targets.TargetError, KeyError, RuntimeError, ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\ninterrupted - rerun the same command with the same --out to resume", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
