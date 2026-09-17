"""Score jevkit pick/classify against labeled cases over recorded snapshots.
Usage: .venv/bin/python evals/score.py [--mock] [--snapshots DIR] [--cases FILE]
Writes evals/desktop/results/<date>-<model>.json and prints a summary."""
import json
import os
import statistics
import sys
import time
from pathlib import Path

if "--mock" in sys.argv:
    os.environ["JEVKIT_MOCK"] = "1"

from jevkit import Judge, compact, config   # noqa: E402  (env must be set first)


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


snaps = Path(arg("--snapshots", "evals/desktop/snapshots"))
cases = json.loads(Path(arg("--cases", "evals/desktop/cases.json")).read_text())
j = Judge()
rows, kinds = [], []
t_all = time.monotonic()
for name, spec in cases.items():
    if name.startswith("_"):
        continue
    if "inline" in spec:            # synthetic screen: a list of "[id] line" strings
        cands = [{"id": l.split("]")[0][1:], "line": l, "interactive": True} for l in spec["inline"]]
        meta = {"window_title": spec.get("title")}
    else:
        f = snaps / f"{name}.json"
        if not f.exists():
            print("missing snapshot", f)
            continue
        st = json.loads(f.read_text())["state"]
        cands = compact.cua_elements(st["elements"], tree_markdown=st.get("tree_markdown"))
        meta = {k: st.get(k) for k in ("window_title", "elements_complete", "element_count", "total_element_count")}
    for c in spec.get("pick", []):
        t0 = time.monotonic()
        r = j.pick(c["target"], cands)
        got = r["choice"] or "none"
        rows.append({"window": name, "target": c["target"], "expect": c["expect"], "got": got,
                     "correct": got == c["expect"], "confidence": r.get("confidence"), "gate": r.get("gate"),
                     "ambiguous": r.get("ambiguous"), "ms": round((time.monotonic() - t0) * 1000),
                     "unavailable": r.get("unavailable")})
    if "classify" in spec:
        t0 = time.monotonic()
        r = j.classify(cands, meta)
        exp = spec["classify"]
        ok = r.get("kind") in exp.get("kind", [r.get("kind")])
        if "consequential" in exp:
            ok = ok and r.get("consequential") == exp["consequential"]
        kinds.append({"window": name, "expect": exp, "kind": r.get("kind"), "confidence": r.get("confidence"),
                      "consequential": r.get("consequential"), "p_consequential": r.get("p_consequential"),
                      "dialog_kind": r.get("dialog_kind"), "gate": r.get("gate"), "correct": ok,
                      "ms": round((time.monotonic() - t0) * 1000)})

n = len(rows)
correct = [r for r in rows if r["correct"]]
wrong = [r for r in rows if not r["correct"]]
none_cases = [r for r in rows if r["expect"] == "none"]
summary = {
    "date": time.strftime("%Y-%m-%d"), "model": j.client.model, "mock": config.MOCK,
    "pick": {"n": n, "correct": len(correct), "accuracy": round(len(correct) / n, 3) if n else None,
             "none_cases": len(none_cases), "none_correct": sum(r["correct"] for r in none_cases),
             "median_ms": statistics.median(r["ms"] for r in rows) if rows else None,
             "confidence_when_correct": round(statistics.mean(r["confidence"] for r in correct if r["confidence"] is not None), 3) if correct else None,
             "confidence_when_wrong": round(statistics.mean(r["confidence"] for r in wrong if r["confidence"] is not None), 3) if wrong else None,
             "gate_act_and_wrong": sum(1 for r in wrong if r["gate"] == "act"),
             "gate_act_and_correct": sum(1 for r in correct if r["gate"] == "act")},
    "classify": {"n": len(kinds), "correct": sum(k["correct"] for k in kinds)},
    "thresholds": {"high": config.HIGH, "low": config.LOW, "yes": config.YES},
    "total_s": round(time.monotonic() - t_all, 1),
}
out = Path("evals/desktop/results"); out.mkdir(parents=True, exist_ok=True)
p = out / f"{summary['date']}-{summary['model']}.json"
p.write_text(json.dumps({"summary": summary, "pick": rows, "classify": kinds}, indent=2))
print(json.dumps(summary, indent=2))
print("\nWRONG picks:")
for r in wrong:
    print(f"  [{r['window'][:24]}] {r['target']!r}: expected {r['expect']}, got {r['got']} (conf {r['confidence']}, gate {r['gate']})")
print("\nclassify:")
for k in kinds:
    print(f"  [{k['window'][:30]}] kind={k['kind']} ({k['confidence']}) consequential={k['consequential']} ({k['p_consequential']}) dialog={k['dialog_kind']} ok={k['correct']}")
print("saved", p)
