"""One thin door to TypeSafe. Everything above it works on plain dicts.

Jev.ask(state, questions) -> {name: answer}, where answer is one of
    {"type": "noul",   "p": float}
    {"type": "choice", "choice": str, "confidence": float, "probabilities": {..}}
    {"type": "score",  "score": float, "confidence": float, "probabilities": {..}}

Every call is appended to a JSONL log (timing, usage, model, question ids,
answers, and a hash of the state; never the state itself, never the key) so
thresholds can be tuned later from real traffic.

MockJev answers offline and deterministically: nouls say yes to instructions
containing a "[yes]" marker in state, choices pick the first non-reserved
option, scores return the middle level. It exists so every caller and test
can run without a credential, the same way jev-use's mock path does.
"""
import hashlib
import json
import os
import time
from pathlib import Path

from . import config, keys


class JevUnavailable(RuntimeError):
    """Jev cannot answer right now: disabled, no key, or the service failed.
    Callers must fall back to the non-Jev path; this is never a verdict."""


def _digest(state):
    return hashlib.sha256(json.dumps(state, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _log(record):
    if not config.LOG_PATH:
        return
    try:
        p = Path(config.LOG_PATH)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except OSError:
        pass


def _normalise(answers):
    out = {}
    for name, a in answers.items():
        if hasattr(a, "noul"):
            out[name] = {"type": "noul", "p": float(a.noul)}
        elif hasattr(a, "choice"):
            out[name] = {"type": "choice", "choice": a.choice, "confidence": float(a.confidence),
                         "probabilities": dict(a.probabilities)}
        elif hasattr(a, "score"):
            out[name] = {"type": "score", "score": float(a.score), "confidence": float(a.confidence),
                         "probabilities": dict(a.probabilities)}
    return out


class Jev:
    """Live client. Construct lazily; raises JevUnavailable on first use if
    there is no key or the package is disabled."""

    def __init__(self, api_key=None, model=None, timeout=None):
        self._key = api_key
        self.model = model or config.MODEL
        self.timeout = timeout or config.TIMEOUT
        self._client = None

    def _connect(self):
        if config.DISABLED:
            raise JevUnavailable("JEVKIT_DISABLE is set")
        key = keys.resolve(self._key)
        if not key:
            raise JevUnavailable("no TypeSafe API key: set TYPESAFE_API_KEY or add the "
                                 "Keychain item (see jevkit.keys)")
        from typesafe_sdk import TypeSafeClient
        self._client = TypeSafeClient(api_key=key, model=self.model, timeout=self.timeout)

    def ask(self, state, questions, tag="ask"):
        """questions: {name: typesafe_sdk.Noul|Choice|Score}."""
        if self._client is None:
            self._connect()
        from typesafe_sdk import TypeSafeAPIConnectionError, TypeSafeAPITimeoutError, TypeSafeError
        t0 = time.monotonic()
        try:
            resp = self._client.system_one(state=state, questions=questions)
        except (TypeSafeAPIConnectionError, TypeSafeAPITimeoutError) as e:
            _log({"ts": time.time(), "tag": tag, "ok": False, "error": type(e).__name__,
                  "ms": round((time.monotonic() - t0) * 1000), "questions": sorted(questions)})
            raise JevUnavailable(f"TypeSafe unreachable: {e}") from e
        except TypeSafeError as e:
            _log({"ts": time.time(), "tag": tag, "ok": False, "error": type(e).__name__,
                  "ms": round((time.monotonic() - t0) * 1000), "questions": sorted(questions)})
            raise JevUnavailable(f"TypeSafe error: {e}") from e
        answers = _normalise(resp.answers)
        usage = getattr(resp, "usage", None)
        _log({"ts": time.time(), "tag": tag, "ok": True, "model": resp.model,
              "ms": round((time.monotonic() - t0) * 1000),
              "input_tokens": getattr(usage, "input_tokens", None),
              "state_sha": _digest(state), "answers": answers})
        return answers

    def models(self):
        if self._client is None:
            self._connect()
        return [m.name for m in self._client.models.list().models]


class MockJev:
    """Deterministic offline stand-in. Choices pick the first option that is
    not the reserved no-match id; nouls answer 0.9 when the question's
    instructions mention a word found in a `[yes:<word>]` marker in state,
    else 0.1; scores return the middle level."""

    model = "mock"

    def ask(self, state, questions, tag="ask"):
        text = json.dumps(state, default=str)
        yes_words = [w for w in _markers(text)]
        out = {}
        for name, q in questions.items():
            kind = getattr(q, "__struct_config__", None) and type(q).__name__.lower()
            if kind == "noul":
                instr = json.dumps(getattr(q, "instructions", ""), default=str).lower()
                p = 0.9 if any(w in instr for w in yes_words) else 0.1
                out[name] = {"type": "noul", "p": p}
            elif kind == "choice":
                opts = list(q.criteria)
                pick = next((o for o in opts if o != "none"), opts[0])
                probs = {o: (0.85 if o == pick else 0.15 / max(1, len(opts) - 1)) for o in opts}
                out[name] = {"type": "choice", "choice": pick, "confidence": 0.85, "probabilities": probs}
            elif kind == "score":
                levels = [json.dumps(c, default=str) if not isinstance(c, str) else c for c in q.criteria]
                mid = levels[len(levels) // 2]
                out[name] = {"type": "score", "score": len(levels) // 2, "confidence": 0.6,
                             "probabilities": {lv: (0.6 if lv == mid else 0.4 / max(1, len(levels) - 1)) for lv in levels}}
        _log({"ts": time.time(), "tag": tag, "ok": True, "model": "mock", "ms": 0,
              "state_sha": _digest(state), "answers": out})
        return out

    def models(self):
        return ["mock"]


def _markers(text):
    import re
    return [m.lower() for m in re.findall(r"\[yes:([^\]]+)\]", text)]


def default_client():
    return MockJev() if config.MOCK else Jev()
