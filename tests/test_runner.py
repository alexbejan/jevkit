import re

from jevkit import compact
from jevkit.runner import DEFAULT_FORBID, Runner


class Scripted:
    """Answers run/classify/verify questions from a script keyed by tag."""
    model = "scripted"

    def __init__(self, moves):
        self.moves, self.calls = list(moves), []

    def ask(self, state, questions, tag="ask"):
        self.calls.append((tag, state, sorted(questions)))
        if tag == "classify":
            return {"kind": {"type": "choice", "choice": "normal", "confidence": 0.9, "probabilities": {}},
                    "consequential": {"type": "noul", "p": 0.1}, "keyboard": {"type": "noul", "p": 0.1},
                    "modal": {"type": "noul", "p": 0.1}, "unsaved": {"type": "noul", "p": 0.1},
                    "dialog_kind": {"type": "choice", "choice": "none", "confidence": 0.9, "probabilities": {}}}
        if tag == "verify":
            return {k: {"type": "noul", "p": p} for k, p in
                    (("landed", 0.9), ("unchanged", 0.1), ("dialog", 0.1), ("error", 0.1), ("auth", 0.1))}
        if tag == "run":
            mv, conf, met = self.moves.pop(0) if self.moves else ("unsure", 0.9, 0.0)
            return {"move": {"type": "choice", "choice": mv, "confidence": conf, "probabilities": {mv: conf, "o1": round((1 - conf) / 2, 3), "o2": round((1 - conf) / 2, 3)}},
                    "goal_met": {"type": "noul", "p": met}, "stuck": {"type": "noul", "p": 0.1}}
        raise AssertionError(tag)


class FakeSurface:
    """Three screens: Settings list -> General -> About."""
    SCREENS = [
        [{"text": "Settings"}, {"text": "General"}, {"text": "Send Feedback"}, {"text": "Sign In"}],
        [{"text": "General"}, {"text": "About"}, {"text": "Software Update"}],
        [{"text": "About"}, {"text": "iPhone 11 Pro"}, {"text": "iOS 27.0"}],
    ]

    def __init__(self):
        self.i, self.executed = 0, []

    def observe(self):
        return compact.phone_boxes([dict(b, x=10, y=20 * n) for n, b in enumerate(self.SCREENS[self.i])]), {"window_title": f"s{self.i}"}

    def actions(self, cands, texts):
        return [{"id": f"tap_{c['id']}", "kind": "tap", "line": f"[tap_{c['id']}] tap {c['text']!r}", "call": c["text"]} for c in cands]

    def execute(self, action):
        self.executed.append(action["call"])
        self.i = min(self.i + 1, len(self.SCREENS) - 1)
        return {"ok": True}

    def settle(self):
        pass


def test_forbidden_labels_never_reach_the_menu():
    s = FakeSurface()
    r = Runner(s, judge=_judge(Scripted([("tap_t1", 0.95, 0.0)])))
    menu = r._menu(*s.observe()[:1], texts=())
    lines = " ".join(m["line"] for m in menu)
    assert "General" in lines and "Send Feedback" not in lines and "Sign In" not in lines
    assert not any(m["id"] in ("done", "unsure", "none") for m in menu)   # those are answers, not moves


def _judge(client):
    from jevkit import Judge
    return Judge(client)


def test_run_completes_when_goal_met():
    s = FakeSurface()
    j = Scripted([("tap_t1", 0.95, 0.05), ("tap_t1", 0.93, 0.1), ("none", 0.9, 0.95)])
    r = Runner(s, judge=_judge(j)).run("open Settings > General > About and read the model")
    assert r["status"] == "done" and s.executed == ["General", "About"]
    assert r["steps"] == 3 and "iPhone 11 Pro" in " ".join(r["final_screen"])
    assert r["trace"][0]["verify"]["landed"] is True


def test_run_stops_on_low_confidence_or_unknown_id():
    s = FakeSurface()
    r = Runner(s, judge=_judge(Scripted([("tap_t1", 0.45, 0.0)]))).run("x")   # below the low line: no act
    assert r["status"] == "unsure" and s.executed == []
    s = FakeSurface()
    r = Runner(s, judge=_judge(Scripted([("tap_t999", 0.99, 0.0)]))).run("x")
    assert r["status"] == "unsure" and s.executed == []


def test_run_respects_max_steps_and_stuck_detection():
    class Stuck(FakeSurface):
        def execute(self, action):
            self.executed.append(action["call"]); return {}
    s = Stuck()
    r = Runner(s, judge=_judge(Scripted([("tap_t1", 0.95, 0.0)] * 6)), max_steps=6).run("x")
    assert r["status"] == "stuck" and len(s.executed) == 2


def test_run_blocks_on_auth_screen():
    class Auth(Scripted):
        def ask(self, state, questions, tag="ask"):
            if tag == "classify":
                d = super().ask(state, questions, tag); d["kind"]["choice"] = "auth"; return d
            return super().ask(state, questions, tag)
    s = FakeSurface()
    r = Runner(s, judge=_judge(Auth([("tap_t1", 0.95, 0.0)]))).run("x")
    assert r["status"] == "blocked" and s.executed == []


def test_default_forbid_covers_the_consent_list():
    for w in ("Send", "Pay Now", "Delete", "Sign in", "Log In", "Allow", "Call", "Buy", "Confirm", "Share"):
        assert DEFAULT_FORBID.search(w), w
    for w in ("Submit", "General", "Next", "Search", "Downloads"):
        assert not DEFAULT_FORBID.search(w), w


def test_none_or_low_goal_met_never_claims_done():
    s = FakeSurface()
    r = Runner(s, judge=_judge(Scripted([("tap_t999", 0.73, 0.57)]))).run("open the Appearance pane")
    assert r["status"] == "unsure" and s.executed == []
    s = FakeSurface()
    r = Runner(s, judge=_judge(Scripted([("tap_t1", 0.9, 0.9)]))).run("x")
    assert r["status"] == "done" and s.executed == []   # goal_met is the only way to finish, and it wins before acting


def test_clear_leader_acts_below_high_threshold():
    s = FakeSurface()
    j = Scripted([("tap_t1", 0.61, 0.1), ("tap_t1", 0.95, 0.1), ("tap_t1", 0.9, 0.95)])
    r = Runner(s, judge=_judge(j)).run("x")
    assert r["status"] == "done" and s.executed == ["General", "About"]


def test_likely_done_when_goal_met_leans_yes_and_no_move_is_confident():
    s = FakeSurface()
    r = Runner(s, judge=_judge(Scripted([("tap_t1", 0.26, 0.64)]))).run("x")
    assert r["status"] == "likely_done" and s.executed == []
