"""Record tree-only snapshots of every visible window, for offline evals.
Read-only: get_accessibility_tree + get_window_state with no screenshot.
Usage: .venv/bin/python evals/record.py [--out evals/desktop/snapshots]"""
import json
import re
import sys
import time
from pathlib import Path

from jevkit import cua

out = Path(sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "evals/desktop/snapshots")
out.mkdir(parents=True, exist_ok=True)
seen = 0
for w in cua.windows():
    if not w.get("title") and w.get("app_name") not in ("Finder",):
        continue
    try:
        st = cua.call("get_window_state", pid=w["pid"], window_id=w["window_id"], include_screenshot=False)
    except cua.CuaUnavailable as e:
        print("skip", w["app_name"], w["window_id"], e)
        continue
    if "elements" not in st or st.get("element_count", 0) < 5:
        continue
    slug = re.sub(r"[^a-z0-9]+", "-", f"{w['app_name']}-{w['title'][:40]}".lower()).strip("-")
    p = out / f"{slug}-{w['window_id']}.json"
    p.write_text(json.dumps({"recorded": time.time(), "window": w, "state": st}))
    print("recorded", p.name, st.get("element_count"), "elements")
    seen += 1
print(seen, "windows")
