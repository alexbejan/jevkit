import json

from typesafe_sdk import Choice, Noul

from jevkit import Judge, JevUnavailable, MockJev, compact, gate
from jevkit.client import Jev


class Scripted:
    """A client that answers from a script and records what it was asked."""
    model = "scripted"

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def ask(self, state, questions, tag="ask"):
        self.calls.append((tag, state, questions))
        return {k: v for k, v in self.answers.items() if k in questions}


def noul(p):
    return {"type": "noul", "p": p}


def choice(c, conf, opts):
    return {"type": "choice", "choice": c, "confidence": conf,
            "probabilities": {o: (conf if o == c else (1 - conf) / max(1, len(opts) - 1)) for o in opts}}


def test_gate_thresholds():
    assert gate(0.95) == "act" and gate(0.6) == "caution" and gate(0.2) == "stop"
    assert gate(0.6, high=0.5) == "act"


def test_verify_no_diff_never_calls(phone_boxes):
    s = Scripted({})
    a = compact.phone_boxes(phone_boxes)
    r = Judge(s).verify("anything", a, a)
    assert r["gate"] == "stop" and r["landed"] is False and r["note"] == "no change"
    assert s.calls == []


def test_verify_landed(phone_boxes):
    s = Scripted({"landed": noul(0.92), "unchanged": noul(0.05), "dialog": noul(0.1),
                  "error": noul(0.05), "auth": noul(0.02)})
    before = compact.phone_boxes(phone_boxes[:1])
    after = compact.phone_boxes(phone_boxes)
    r = Judge(s).verify("the General row is visible", before, after)
    assert r["landed"] and r["gate"] == "act"
    tag, state, qs = s.calls[0]
    assert tag == "verify" and "'General'" in state["added"] and "expect" in state
    assert set(qs) == {"landed", "unchanged", "dialog", "error", "auth"}


def test_verify_auth_forces_stop(phone_boxes):
    s = Scripted({"landed": noul(0.9), "unchanged": noul(0.1), "dialog": noul(0.9),
                  "error": noul(0.1), "auth": noul(0.8)})
    r = Judge(s).verify("x", compact.phone_boxes(phone_boxes[:1]), compact.phone_boxes(phone_boxes))
    assert r["auth"] and r["gate"] == "stop"


def test_verify_dialog_downgrades_to_caution(phone_boxes):
    s = Scripted({"landed": noul(0.95), "unchanged": noul(0.1), "dialog": noul(0.9),
                  "error": noul(0.1), "auth": noul(0.1)})
    r = Judge(s).verify("x", compact.phone_boxes(phone_boxes[:1]), compact.phone_boxes(phone_boxes))
    assert r["dialog"] and r["gate"] == "caution"


def test_pick_returns_candidate_and_fails_closed(finder):
    cands = compact.cua_elements(finder["elements"], tree_markdown=finder["tree_markdown"])
    target = next(c for c in cands if "Applications" in c["line"])
    ids = [c["id"] for c in cands] + ["none"]
    s = Scripted({"target": choice(target["id"], 0.9, ids), "ambiguous": noul(0.1)})
    r = Judge(s).pick("the Applications sidebar row", cands)
    assert r["candidate"]["element_token"] == target["element_token"] and r["gate"] == "act"
    # 'none' and unknown ids never yield a candidate
    for bad in ("none", "e99999"):
        s = Scripted({"target": choice(bad, 0.9, ids), "ambiguous": noul(0.1)})
        r = Judge(s).pick("x", cands)
        assert r["candidate"] is None and r["choice"] is None and r["gate"] == "stop"


def test_pick_ambiguous_caps_gate(finder):
    cands = compact.cua_elements(finder["elements"], tree_markdown=finder["tree_markdown"])
    ids = [c["id"] for c in cands] + ["none"]
    first = next(c for c in cands if c["interactive"])
    s = Scripted({"target": choice(first["id"], 0.95, ids), "ambiguous": noul(0.8)})
    assert Judge(s).pick("x", cands)["gate"] == "caution"


def test_pick_state_has_no_tokens_or_frames(finder):
    cands = compact.cua_elements(finder["elements"], tree_markdown=finder["tree_markdown"])
    s = Scripted({"target": choice("none", 0.5, ["none"]), "ambiguous": noul(0.1)})
    Judge(s).pick("x", cands)
    text = json.dumps(s.calls[0][1])
    assert "element_token" not in text and "frame" not in text and "s0000" not in text


def test_classify_auth_stops(settings):
    cands = compact.cua_elements(settings["elements"])
    kinds = ["normal", "dialog", "permission", "auth", "loading", "error", "paywall", "empty"]
    dk = ["benign", "blocking", "consequential", "auth", "none"]
    s = Scripted({"kind": choice("auth", 0.9, kinds), "consequential": noul(0.7), "keyboard": noul(0.2),
                  "modal": noul(0.8), "unsaved": noul(0.1), "dialog_kind": choice("none", 0.9, dk)})
    r = Judge(s).classify(cands, {"elements_complete": False})
    assert r["kind"] == "auth" and r["gate"] == "stop" and r["consequential"]
    assert r["dialog_kind"] is None and "incomplete" in r["note"]


def test_unavailable_never_raises(phone_boxes):
    class Down:
        def ask(self, *a, **k):
            raise JevUnavailable("down")
    a, b = compact.phone_boxes(phone_boxes[:1]), compact.phone_boxes(phone_boxes)
    j = Judge(Down())
    assert j.verify("x", a, b)["unavailable"] and j.verify("x", a, b)["gate"] == "caution"
    assert j.pick("x", b)["unavailable"] and j.classify(b)["unavailable"]
    assert j.ask({"a": 1}, {"q": Noul(instructions="?")})["unavailable"]


def test_mock_client_is_deterministic(phone_boxes):
    j = Judge(MockJev())
    b = compact.phone_boxes(phone_boxes)
    r = j.pick("General", b)
    assert r["candidate"] is not None and r["gate"] == "act"
    a = j.ask({"note": "[yes:dialog]"}, {"d": Noul(instructions="Is there a dialog?"),
                                        "e": Noul(instructions="Is there an error?"),
                                        "k": Choice(instructions="?", criteria={"none": None, "x": None})})
    assert a["answers"]["d"]["p"] > 0.5 > a["answers"]["e"]["p"] and a["answers"]["k"]["choice"] == "x"


def test_live_client_without_key_is_unavailable(monkeypatch):
    from jevkit import keys
    monkeypatch.setattr(keys, "from_keychain", lambda service=None: None)
    try:
        Jev().ask({"x": 1}, {"q": Noul(instructions="?")})
    except JevUnavailable as e:
        assert "API key" in str(e)
    else:
        raise AssertionError("expected JevUnavailable")


def test_log_has_no_state_text(phone_boxes, tmp_path):
    import jevkit.config as c
    j = Judge(MockJev())
    j.pick("Privacy & Security", compact.phone_boxes(phone_boxes))
    lines = open(c.LOG_PATH).read().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["tag"] == "pick" and "state_sha" in rec and "Privacy" not in lines[0]


def test_verify_title_change_counts(phone_boxes):
    s = Scripted({"landed": noul(0.9), "unchanged": noul(0.1), "dialog": noul(0.1),
                  "error": noul(0.1), "auth": noul(0.1)})
    a = compact.phone_boxes(phone_boxes)
    r = Judge(s).verify("Recents is open", a, a, {"window_title": "Recents"}, {"window_title": "Documents"})
    assert r["landed"] and r["diff"]["title_after"] == "Recents"
    assert s.calls[0][1]["after_window_title"] == "Recents"
