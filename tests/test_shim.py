"""The shim against a fake `cua-driver` that records argv and replays canned
JSON. Jev is the deterministic mock. No network, no real driver."""
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "src"
FIX = Path(__file__).parent / "fixtures"

FAKE = r'''#!/usr/bin/env python3
import json, sys, os
log = os.environ["FAKE_LOG"]
open(log, "a").write(json.dumps(sys.argv[1:]) + "\n")
a = sys.argv[1:]
if a[:1] == ["--version"]:
    print("cua-driver 9.9.9-fake"); sys.exit(0)
if a[:1] == ["list-tools"]:
    print("click: Click\nzoom: Zoom"); sys.exit(0)
if a[:2] == ["call", "get_window_state"]:
    print(open(os.environ["FAKE_SNAPSHOT"]).read()); sys.exit(0)
if a[:1] == ["call"]:
    print(json.dumps({"effect": "confirmed", "route": "accessibility", "args": json.loads(a[2]) if len(a) > 2 else {}})); sys.exit(0)
print("unknown"); sys.exit(3)
'''


@pytest.fixture
def env(tmp_path, monkeypatch):
    fake = tmp_path / "cua-driver"
    fake.write_text(FAKE)
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    e = dict(os.environ)
    e.update({"JEVKIT_REAL_CUA": str(fake), "FAKE_LOG": str(tmp_path / "argv.log"),
              "FAKE_SNAPSHOT": str(FIX / "cua_finder_window.json"), "JEVKIT_MOCK": "1",
              "JEVKIT_LOG": str(tmp_path / "calls.jsonl"), "XDG_STATE_HOME": str(tmp_path / "state"),
              "PYTHONPATH": str(SRC), "JEVKIT_SHIM_SETTLE": "0"})
    e.pop("TYPESAFE_API_KEY", None)
    return e


def shim(env, *argv):
    r = subprocess.run([sys.executable, "-m", "jevkit.shim", *argv], capture_output=True, text=True, env=env)
    return r.returncode, r.stdout, r.stderr


def argv_log(env):
    return [json.loads(l) for l in open(env["FAKE_LOG"]).read().splitlines()]


def test_passthrough(env):
    code, out, _ = shim(env, "--version")
    assert code == 0 and "fake" in out
    code, out, _ = shim(env, "list-tools")
    assert "jev_pick:" in out and "zoom:" in out
    code, out, _ = shim(env, "describe", "jev_verify")
    assert code == 0 and "jev_verify" in out


def test_snapshot_caches_and_classifies(env):
    code, out, _ = shim(env, "call", "get_window_state", json.dumps({"pid": 1, "window_id": 2, "include_screenshot": False}))
    d = json.loads(out)
    assert code == 0 and d["element_count"] == 241            # driver payload intact
    assert d["jev"]["cached"] and d["jev"]["kind"]
    assert (Path(env["XDG_STATE_HOME"]) / "jevkit" / "shim" / "1-2.json").exists()
    assert argv_log(env)[-1][:2] == ["call", "get_window_state"]


def test_action_without_expect_is_untouched(env):
    code, out, _ = shim(env, "call", "click", json.dumps({"pid": 1, "window_id": 2, "element_token": "s1:3"}))
    d = json.loads(out)
    assert code == 0 and "jev" not in d
    assert argv_log(env) == [["call", "click", json.dumps({"pid": 1, "window_id": 2, "element_token": "s1:3"})]]


def test_action_with_expect_is_stripped_and_verified(env):
    shim(env, "call", "get_window_state", json.dumps({"pid": 1, "window_id": 2}))
    code, out, _ = shim(env, "call", "click", json.dumps({"pid": 1, "window_id": 2, "element_token": "s1:3",
                                                          "jev_expect": "Recents is selected"}))
    d = json.loads(out)
    assert code == 0 and d["effect"] == "confirmed"
    assert "jev_expect" not in d["args"]                      # never reaches the driver
    assert d["jev"]["expect"] == "Recents is selected" and "gate" in d["jev"]
    calls = argv_log(env)
    assert calls[1][1] == "click" and "jev_expect" not in calls[1][2]
    assert calls[2][1] == "get_window_state"                  # after-snapshot, not before


def test_virtual_tools(env):
    code, out, _ = shim(env, "call", "jev_pick", json.dumps({"pid": 1, "window_id": 2, "target": "Recents"}))
    d = json.loads(out)
    assert code == 0 and d["candidate"]["element_token"] and d["gate"]
    code, out, _ = shim(env, "call", "jev_classify", json.dumps({"pid": 1, "window_id": 2}))
    assert json.loads(out)["kind"]
    code, out, _ = shim(env, "call", "jev_verify", json.dumps({"pid": 1, "window_id": 2, "expect": "x"}))
    assert "diff" in json.loads(out)
    code, out, _ = shim(env, "call", "jev_pick", json.dumps({"target": "x"}))
    assert code == 2 and json.loads(out)["code"] == "invalid_arguments"


def test_off_mode_forwards_everything(env):
    env = dict(env, JEVKIT_SHIM="off")
    code, out, _ = shim(env, "call", "get_window_state", json.dumps({"pid": 1, "window_id": 2}))
    assert "jev" not in json.loads(out)
    code, out, _ = shim(env, "list-tools")
    assert "jev_pick" not in out
