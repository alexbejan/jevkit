"""One live smoke test. Runs only with JEVKIT_LIVE=1 and a resolvable key."""
import os

import pytest

from jevkit import Judge, compact, keys
from jevkit.client import Jev

live = pytest.mark.skipif(os.environ.get("JEVKIT_LIVE") != "1" or not keys.resolve(),
                          reason="set JEVKIT_LIVE=1 and a TypeSafe key")


@live
def test_live_pick_and_verify(finder, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", keys.resolve())
    j = Judge(Jev())
    cands = compact.cua_elements(finder["elements"], tree_markdown=finder["tree_markdown"])
    r = j.pick("the Applications row in the Finder sidebar", cands)
    assert r["candidate"] is not None and "Applications" in r["candidate"]["line"]
    before = [c for c in cands if "Applications" not in c["line"]]
    v = j.verify("the Applications row is now visible in the sidebar", before, cands)
    assert v["landed"] is True
    k = j.classify(cands)
    assert k["kind"] in ("normal", "dialog", "empty")
