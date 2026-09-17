"""A transparent front for `cua-driver` that adds Jev judgements.

Install it ahead of the real binary on PATH (see `jev shim status`). Every
invocation is forwarded unchanged to the real driver. Three things are added,
all of them opt-in per call and all of them harmless on failure:

1. `call get_window_state ...`
   Forwarded. The compacted tree is cached for this (pid, window_id) as the
   "before" state of the next action, and a `jev` key is appended with a
   classify verdict (kind, consequential, dialog_kind, gate) unless
   JEVKIT_SHIM_CLASSIFY=0.

2. `call <action> {... "jev_expect": "<postcondition>"}`
   `jev_expect` is stripped, the action is forwarded, a fresh tree-only
   snapshot is taken, and a `jev` key with the verify verdict is appended:
   {landed, p_landed, dialog, error, auth, gate, diff, note}. Actions without
   `jev_expect` are forwarded untouched (JEVKIT_SHIM=always verifies every
   action with a generic expectation instead).

   Ordering note: the shim never snapshots BEFORE an action, because a new
   snapshot would invalidate the element_token the agent is about to use.
   "before" is the last snapshot that went through the shim.

3. Virtual tools that the real driver does not have:
     jev_pick      {pid, window_id, target, session?, any?}  -> candidate + element_token
     jev_classify  {pid, window_id, session?}                -> screen verdict
     jev_verify    {pid, window_id, expect, session?}        -> verdict vs cached before
   `describe` and `list-tools` know about them.

The real driver's stdout is preserved byte for byte when it is not JSON or
when nothing is added. Exit codes pass through. JEVKIT_SHIM=off disables
everything except forwarding.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import compact, config
from .judge import Judge

ACTIONS = {"click", "double_click", "right_click", "type_text", "type_text_chars", "press_key",
           "hotkey", "set_value", "invoke_menu", "scroll", "drag", "browser_click", "browser_type",
           "browser_navigate", "browser_pointer"}
VIRTUAL = {
    "jev_pick": "Choose one element of a window by description. Input {pid, window_id, target, session?, any?}. "
                "Returns the chosen candidate with its element_token (from a fresh snapshot), confidence, "
                "probabilities and gate (act|caution|stop). `choice` is null when nothing matches.",
    "jev_classify": "Classify a window: kind (normal|dialog|permission|auth|loading|error|paywall|empty), "
                    "consequential (a send/pay/delete/sign-in control is visible), dialog_kind, gate. "
                    "Input {pid, window_id, session?}.",
    "jev_verify": "Verify a postcondition against the last snapshot seen by the shim. Input {pid, window_id, "
                  "expect, session?}. Returns {landed, p_landed, dialog, error, auth, gate, diff, note}.",
}
STATE = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "jevkit" / "shim"
MODE = os.environ.get("JEVKIT_SHIM", "auto")          # auto | always | off
CLASSIFY = os.environ.get("JEVKIT_SHIM_CLASSIFY", "1") not in ("0", "false", "no")


def real_binary():
    forced = os.environ.get("JEVKIT_REAL_CUA")
    if forced:
        return forced
    me = Path(sys.argv[0]).resolve()
    here = Path(__file__).resolve()
    for d in os.environ.get("PATH", "").split(os.pathsep):
        cand = Path(d) / "cua-driver"
        if cand.is_file() and os.access(cand, os.X_OK):
            r = cand.resolve()
            if r == me or r == here or "jevkit" in str(r):
                continue
            return str(cand)
    return None


def _cache_path(pid, wid):
    return STATE / f"{pid}-{wid}.json"


def _cache_write(pid, wid, cands, meta):
    try:
        STATE.mkdir(parents=True, exist_ok=True)
        _cache_path(pid, wid).write_text(json.dumps({"ts": time.time(), "candidates": cands, "meta": meta}))
    except OSError:
        pass


def _cache_read(pid, wid):
    try:
        return json.loads(_cache_path(pid, wid).read_text())
    except (OSError, ValueError):
        return None


def _forward(real, argv):
    r = subprocess.run([real] + argv, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def _snapshot(real, pid, wid, session):
    kw = {"pid": pid, "window_id": wid, "include_screenshot": False}
    if session:
        kw["session"] = session
    code, out, err = _forward(real, ["call", "get_window_state", json.dumps(kw)])
    st = json.loads(out)
    if not isinstance(st, dict) or "elements" not in st:
        raise RuntimeError(f"snapshot failed: {out[:200] or err[:200]}")
    meta = {k: st.get(k) for k in ("snapshot_id", "window_title", "app_name", "element_count",
                                   "elements_complete", "degraded_reason", "total_element_count")}
    return compact.cua_elements(st["elements"], tree_markdown=st.get("tree_markdown")), meta


def _emit(code, out, err, extra=None):
    if extra is not None:
        try:
            data = json.loads(out)
            if isinstance(data, dict):
                data["jev"] = extra
                out = json.dumps(data, indent=2)
        except ValueError:
            pass
    sys.stdout.write(out)
    if err:
        sys.stderr.write(err)
    return code


def _safe(fn):
    try:
        return fn()
    except Exception as e:      # noqa: BLE001 - never break the driver call
        return {"unavailable": True, "error_text": f"{type(e).__name__}: {e}"}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    real = real_binary()
    if real is None:
        sys.stderr.write("jevkit shim: real cua-driver not found on PATH (set JEVKIT_REAL_CUA)\n")
        return 127

    if MODE == "off" or not argv:
        return _emit(*_forward(real, argv))

    if argv[0] == "list-tools":
        code, out, err = _forward(real, argv[1:] and argv or argv)
        if code == 0 and out and not out.lstrip().startswith("{"):
            out = out.rstrip("\n") + "\n" + "\n".join(f"{k}: {v}" for k, v in VIRTUAL.items()) + "\n"
        return _emit(code, out, err)

    if argv[0] == "describe" and len(argv) > 1 and argv[1] in VIRTUAL:
        sys.stdout.write(f"name: {argv[1]}\n\ndescription:\n{VIRTUAL[argv[1]]}\n\n(jevkit virtual tool; served by the shim)\n")
        return 0

    if argv[0] != "call" or len(argv) < 2:
        return _emit(*_forward(real, argv))

    tool = argv[1]
    try:
        args = json.loads(argv[2]) if len(argv) > 2 and argv[2].strip() else {}
    except ValueError:
        return _emit(*_forward(real, argv))
    if not isinstance(args, dict):
        return _emit(*_forward(real, argv))
    pid, wid, session = args.get("pid"), args.get("window_id"), args.get("session")

    # -- virtual tools ----------------------------------------------------------
    if tool in VIRTUAL:
        if pid is None or wid is None:
            sys.stdout.write(json.dumps({"code": "invalid_arguments", "detail": "pid and window_id are required", "tool": tool}))
            return 2

        def run():
            j = Judge()
            if tool == "jev_verify":
                before = _cache_read(pid, wid)
                if not before:
                    return {"unavailable": True, "error_text": "no cached snapshot for this window; call get_window_state first"}
                after, meta = _snapshot(real, pid, wid, session)
                _cache_write(pid, wid, after, meta)
                r = j.verify(args.get("expect", ""), before["candidates"], after, meta, before.get("meta"))
                r["meta"] = meta
                return r
            cands, meta = _snapshot(real, pid, wid, session)
            _cache_write(pid, wid, cands, meta)
            if tool == "jev_pick":
                r = j.pick(args.get("target", ""), cands, interactive_only=not args.get("any"))
            else:
                r = j.classify(cands, meta)
            r["meta"] = meta
            return r
        sys.stdout.write(json.dumps(_safe(run), default=str, indent=2))
        return 0

    # -- get_window_state: forward, cache, classify -----------------------------
    if tool == "get_window_state":
        code, out, err = _forward(real, argv)
        extra = None
        if code == 0 and pid is not None and wid is not None:
            def run():
                st = json.loads(out)
                if "elements" not in st:
                    return None
                meta = {k: st.get(k) for k in ("snapshot_id", "window_title", "app_name", "element_count",
                                               "elements_complete", "degraded_reason", "total_element_count")}
                cands = compact.cua_elements(st["elements"], tree_markdown=st.get("tree_markdown"))
                _cache_write(pid, wid, cands, meta)
                if not CLASSIFY:
                    return {"cached": True}
                r = Judge().classify(cands, meta)
                r.pop("raw", None)
                r["cached"] = True
                return r
            extra = _safe(run)
        return _emit(code, out, err, extra)

    # -- actions: strip jev_expect, forward, verify -----------------------------
    expect = args.pop("jev_expect", None)
    if tool in ACTIONS and expect is not None:
        argv = ["call", tool, json.dumps(args)]
    code, out, err = _forward(real, argv)
    if tool not in ACTIONS or pid is None:
        return _emit(code, out, err)
    if expect is None and MODE != "always":
        return _emit(code, out, err)
    if wid is None:
        return _emit(code, out, err, {"unavailable": True, "error_text": "window_id needed to verify"})
    if expect is None:
        expect = f"the {tool} action took effect on the window"

    def run():
        before = _cache_read(pid, wid)
        time.sleep(float(os.environ.get("JEVKIT_SHIM_SETTLE", "0.6")))
        after, meta = _snapshot(real, pid, wid, session)
        _cache_write(pid, wid, after, meta)
        if not before:
            r = Judge().classify(after, meta)
            r.pop("raw", None)
            r["note"] = "no cached before-state; classified the after-state instead"
            return r
        r = Judge().verify(expect, before["candidates"], after, meta, before.get("meta"))
        r.pop("raw", None)
        r["expect"] = expect
        return r
    return _emit(code, out, err, _safe(run))


if __name__ == "__main__":
    sys.exit(main())
