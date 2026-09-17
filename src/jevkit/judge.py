"""The judgement API. Returns plain dicts; never acts.

gate(confidence) -> "act" | "caution" | "stop"
    act      high confidence: continue the batch
    caution  re-snapshot, look at a screenshot, or ask
    stop     do not act on this answer; report

Every result carries `gate`, the raw probabilities, and `unavailable=True`
when Jev could not answer, so callers can fall back without try/except.
"""
from . import compact, config, questions
from .client import JevUnavailable, default_client


def gate(confidence, high=None, low=None):
    high = config.HIGH if high is None else high
    low = config.LOW if low is None else low
    if confidence >= high:
        return "act"
    if confidence >= low:
        return "caution"
    return "stop"


def _noul_conf(p):
    # A Noul has no confidence field; distance from 0.5 is the honest proxy.
    return abs(p - 0.5) * 2


class Judge:
    def __init__(self, client=None):
        self.client = client or default_client()

    def _ask(self, state, qs, tag):
        try:
            return self.client.ask(state, qs, tag=tag), None
        except JevUnavailable as e:
            return None, str(e)

    # -- verify ---------------------------------------------------------------

    def verify(self, expect, before, after, meta=None, before_meta=None):
        """before/after: candidate lists from jevkit.compact; meta/before_meta:
        snapshot metadata (window_title is used). Returns
        {landed, p_landed, unchanged, dialog, error, auth, gate, diff, note}."""
        d = compact.diff(before, after)
        t_before = (before_meta or {}).get("window_title")
        t_after = (meta or {}).get("window_title")
        if t_before != t_after and (t_before or t_after):
            d["title_before"], d["title_after"], d["changed"] = t_before, t_after, True
        note = compact.truncated_note(meta or {})
        if not d["changed"] and not note:
            # Nothing moved. Do not spend a call; the answer is deterministic.
            return {"landed": False, "p_landed": 0.0, "unchanged": True, "dialog": False,
                    "error": False, "auth": False, "gate": "stop", "diff": d, "note": "no change",
                    "unavailable": False}
        state = {"expect": expect, "added": d["added"][:120], "removed": d["removed"][:120],
                 "after": compact.lines(after)[:config.MAX_STATE_LINES]}
        if "title_after" in d:
            state["before"] = {"window_title": t_before}
            state["after_window_title"] = t_after
        ans, err = self._ask(state, questions.verify(expect), "verify")
        if ans is None:
            return {"landed": None, "gate": "caution", "diff": d, "note": note, "unavailable": True, "error_text": err}
        p = ans["landed"]["p"]
        out = {"landed": p >= config.YES, "p_landed": p,
               "unchanged": ans["unchanged"]["p"] >= config.YES,
               "dialog": ans["dialog"]["p"] >= config.YES,
               "error": ans["error"]["p"] >= config.YES,
               "auth": ans["auth"]["p"] >= config.YES,
               "gate": gate(_noul_conf(p)), "diff": d, "note": note, "unavailable": False,
               "raw": ans}
        if out["auth"] or out["error"]:
            out["gate"] = "stop"       # never batch through a credential or error screen
        elif out["dialog"] and out["gate"] == "act":
            out["gate"] = "caution"
        return out

    # -- pick -----------------------------------------------------------------

    def pick(self, target, candidates, interactive_only=True):
        """Choose one candidate for a description. Returns the candidate dict
        plus {choice, confidence, probabilities, ambiguous, gate}; `choice`
        is None when Jev picked `none` or the id is unknown (fail closed)."""
        pool = [c for c in candidates if c.get("interactive", True)] if interactive_only else list(candidates)
        if not pool:
            return {"choice": None, "candidate": None, "gate": "stop", "note": "no candidates", "unavailable": False}
        pool = pool[:config.MAX_CANDIDATES]
        state = {"target": target, "elements": compact.lines(pool)}
        ans, err = self._ask(state, questions.pick(target, pool), "pick")
        if ans is None:
            return {"choice": None, "candidate": None, "gate": "caution", "unavailable": True, "error_text": err}
        a = ans["target"]
        by_id = {c["id"]: c for c in pool}
        cid = a["choice"]
        cand = by_id.get(cid)            # unknown or `none` -> None, fail closed
        amb = ans["ambiguous"]["p"] >= config.YES
        g = gate(a["confidence"])
        if cand is None:
            g = "stop"
        elif amb and g == "act":
            g = "caution"
        return {"choice": cid if cand else None, "candidate": cand, "confidence": a["confidence"],
                "probabilities": a["probabilities"], "ambiguous": amb, "gate": g,
                "unavailable": False}

    # -- classify -------------------------------------------------------------

    def classify(self, candidates, meta=None):
        """One fan-out over the screen. Returns kind, flags, and gate."""
        note = compact.truncated_note(meta or {})
        state = {"screen": compact.lines(candidates)[:config.MAX_STATE_LINES]}
        qs = {**questions.classify(), **questions.dialog_kind()}
        ans, err = self._ask(state, qs, "classify")
        if ans is None:
            return {"kind": None, "gate": "caution", "unavailable": True, "error_text": err, "note": note}
        k = ans["kind"]
        dk = ans["dialog_kind"]
        out = {"kind": k["choice"], "confidence": k["confidence"], "probabilities": k["probabilities"],
               "consequential": ans["consequential"]["p"] >= config.YES,
               "p_consequential": ans["consequential"]["p"],
               "keyboard": ans["keyboard"]["p"] >= config.YES,
               "modal": ans["modal"]["p"] >= config.YES,
               "unsaved": ans["unsaved"]["p"] >= config.YES,
               "dialog_kind": None if dk["choice"] == questions.NONE else dk["choice"],
               "dialog_confidence": dk["confidence"],
               "gate": gate(k["confidence"]), "note": note, "unavailable": False, "raw": ans}
        if out["kind"] == "auth" or out["dialog_kind"] in ("auth", "consequential"):
            out["gate"] = "stop"
        return out

    # -- raw ------------------------------------------------------------------

    def ask(self, state, qs, tag="ask"):
        ans, err = self._ask(state, qs, tag)
        if ans is None:
            return {"unavailable": True, "error_text": err}
        return {"unavailable": False, "answers": ans}
