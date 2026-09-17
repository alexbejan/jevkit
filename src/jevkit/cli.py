"""`jev`: the command-line door, for agents that talk to the driver from a
shell. Every command prints one JSON object. Exit code 0 even when Jev is
unavailable (the JSON says so); non-zero only for bad arguments.

  jev doctor                              key source, model, driver, log path
  jev snapshot  --pid P --window W        compacted state (and saves it)
  jev classify  --pid P --window W
  jev pick      --pid P --window W --target "the Save button"
  jev verify    --pid P --window W --expect "..." --before before.json
  jev ask       --state-file s.json --questions-file q.json
  jev phone-*   same three, reading phone-harness ocr()/ui() JSON from a file
"""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from . import __version__, compact, config, keys
from .judge import Judge


def _out(obj):
    print(json.dumps(obj, default=str, indent=2))


def _load(path):
    with open(path) as f:
        return json.load(f)


def cmd_doctor(a):
    from . import cua
    try:
        drv = cua.binary()
    except cua.CuaUnavailable:
        drv = None
    src = keys.source()
    rep = {"jevkit": __version__, "model": config.MODEL, "mock": config.MOCK, "disabled": config.DISABLED,
           "key_source": src, "cua_driver": drv, "log": config.LOG_PATH,
           "thresholds": {"high": config.HIGH, "low": config.LOW, "yes": config.YES}}
    if a.live and src:
        try:
            t0 = time.monotonic()
            rep["models"] = Judge().client.models()
            rep["models_ms"] = round((time.monotonic() - t0) * 1000)
        except Exception as e:      # noqa: BLE001 - doctor reports, never raises
            rep["live_error"] = f"{type(e).__name__}: {e}"
    rep["ok"] = bool(src) or config.MOCK
    _out(rep)


def _snap(a):
    from . import cua
    return cua.snapshot(a.pid, a.window, session=a.session, query=a.query)


def cmd_snapshot(a):
    cands, meta = _snap(a)
    rec = {"meta": meta, "candidates": cands}
    if a.save:
        with open(a.save, "w") as f:
            json.dump(rec, f)
    _out({"meta": meta, "lines": compact.lines(cands), "saved": a.save})


def cmd_classify(a):
    cands, meta = _snap(a)
    _out(Judge().classify(cands, meta))


def cmd_pick(a):
    cands, meta = _snap(a)
    r = Judge().pick(a.target, cands, interactive_only=not a.any)
    r["meta"] = meta
    _out(r)


def cmd_verify(a):
    before = _load(a.before)["candidates"]
    cands, meta = _snap(a)
    r = Judge().verify(a.expect, before, cands, meta)
    r["meta"] = meta
    _out(r)


def cmd_ask(a):
    from typesafe_sdk import Choice, Noul, Score
    raw = _load(a.questions_file)
    qs = {}
    for name, q in raw.items():
        t = q.pop("type")
        qs[name] = {"noul": Noul, "choice": Choice, "score": Score}[t](**q)
    _out(Judge().ask(_load(a.state_file), qs))


def _phone(a):
    boxes = _load(a.boxes)
    return compact.phone_boxes(boxes)


def cmd_phone_classify(a):
    _out(Judge().classify(_phone(a)))


def cmd_phone_pick(a):
    _out(Judge().pick(a.target, _phone(a)))


def cmd_phone_verify(a):
    before = compact.phone_boxes(_load(a.before))
    _out(Judge().verify(a.expect, before, _phone(a)))


def cmd_shim(a):
    from . import shim as sh
    me = str((Path(__file__).resolve().parent.parent.parent / "shim" / "cua-driver"))
    link = Path.home() / ".local" / "shims" / "cua-driver"
    resolved = shutil.which("cua-driver")
    _out({"shim_script": me, "link": str(link), "link_exists": link.exists(),
          "path_resolves_to": resolved, "shim_active": bool(resolved and "jevkit" in str(Path(resolved).resolve())),
          "real_driver": sh.real_binary(), "mode": sh.MODE, "classify_on_snapshot": sh.CLASSIFY,
          "install": f"mkdir -p {link.parent} && ln -sf {me} {link} && add 'export PATH=\"$HOME/.local/shims:$PATH\"' as the LAST PATH line of ~/.zshrc"})


def main(argv=None):
    p = argparse.ArgumentParser(prog="jev", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor"); d.add_argument("--live", action="store_true"); d.set_defaults(fn=cmd_doctor)

    def win(sp):
        sp.add_argument("--pid", type=int, required=True)
        sp.add_argument("--window", type=int, required=True)
        sp.add_argument("--session")
        sp.add_argument("--query", help="Cua get_window_state query filter")

    s = sub.add_parser("snapshot"); win(s); s.add_argument("--save"); s.set_defaults(fn=cmd_snapshot)
    c = sub.add_parser("classify"); win(c); c.set_defaults(fn=cmd_classify)
    k = sub.add_parser("pick"); win(k); k.add_argument("--target", required=True)
    k.add_argument("--any", action="store_true", help="also consider non-interactive text"); k.set_defaults(fn=cmd_pick)
    v = sub.add_parser("verify"); win(v); v.add_argument("--expect", required=True)
    v.add_argument("--before", required=True, help="file written by `jev snapshot --save`"); v.set_defaults(fn=cmd_verify)
    q = sub.add_parser("ask"); q.add_argument("--state-file", required=True); q.add_argument("--questions-file", required=True)
    q.set_defaults(fn=cmd_ask)

    pc = sub.add_parser("phone-classify"); pc.add_argument("--boxes", required=True); pc.set_defaults(fn=cmd_phone_classify)
    pk = sub.add_parser("phone-pick"); pk.add_argument("--boxes", required=True); pk.add_argument("--target", required=True)
    pk.set_defaults(fn=cmd_phone_pick)
    pv = sub.add_parser("phone-verify"); pv.add_argument("--boxes", required=True); pv.add_argument("--before", required=True)
    pv.add_argument("--expect", required=True); pv.set_defaults(fn=cmd_phone_verify)

    sh = sub.add_parser("shim", help="where the cua-driver shim is and whether PATH resolves to it"); sh.set_defaults(fn=cmd_shim)

    a = p.parse_args(argv)
    try:
        a.fn(a)
    except FileNotFoundError as e:
        _out({"error": f"file not found: {e.filename}"}); return 2
    except Exception as e:      # noqa: BLE001 - one JSON error object, never a traceback for the agent
        _out({"error": f"{type(e).__name__}: {e}"}); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
