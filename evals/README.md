# Evals

Recorded, offline, repeatable. `evals/record.py` snapshots every visible
window (tree only, no screenshot) into `evals/desktop/snapshots/` (git-ignored:
real windows carry personal data). `evals/desktop/cases.json` holds labeled
cases: paraphrased pick targets, absent targets that must return `none`, and
expected screen kinds. `evals/score.py` runs them against Jev and writes a
dated result file.

```bash
.venv/bin/python evals/record.py            # read-only, current desktop
.venv/bin/python evals/score.py             # live; add --mock for the machinery only
```

## Results

### 2026-09-17, jev-1.13.0, 6 windows (Finder, System Settings, Safari, Device Hub, Superset, a TCC permission dialog)

| Metric | Value |
|---|---|
| Pick accuracy | 30 / 31 (96.8%) |
| Absent target returned `none` | 7 / 7 |
| Classify kind correct | 5 / 5 |
| Mean confidence when correct | 0.98 |
| Confidence on the one miss | 0.56 (gated `caution`) |
| Confident and wrong (`gate: act`) | 0 |
| Median pick latency (from Romania) | 324 ms |
| Input tokens per call | 1,500 to 2,400 |

The miss: "Documents under Favorites" picked the "Favorites" header row
(e6) over the Documents cell (e12). Two elements matched parts of the
phrase; the ambiguity flag did not fire, but confidence did. Default
thresholds (high 0.80, low 0.50) held: nothing wrong passed as `act`.

`consequential` runs warm: 0.70 on a Finder window (Eject and Trash are
visible), 0.54 on a Safari toolbar. Treat it as a reason to look, not as a
verdict, until more windows are labeled. Its 0.85 on the permission dialog
and 0.80 on System Settings toggles are the cases that matter, and both fired.

Six windows is a start, not a certificate. Grow the set by recording more
desktops and labeling `cases.json`; keep results per model version.
