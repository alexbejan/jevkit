"""`jev run`: Jev chooses every step of a bounded task, code owns the rest.

The loop, per Cua's jev-use boundary:

    observe -> classify (stop on auth / error / consequential dialog)
            -> build a MENU of complete, legal actions from what is visible
            -> Jev picks ONE menu id (plus: is the goal already met?)
            -> execute that one prebuilt action through the surface
            -> verify -> record -> repeat

Jev never supplies coordinates, tokens, tool names, or text. Text it may
"type" comes only from the caller's `texts` list. Labels matching the
forbidden list (send, pay, delete, sign in, allow, ...) are removed from the
menu before Jev sees it, so they cannot be chosen. A `done` and an `unsure`
item are always present.

A Surface adapts one device. It must provide:
    observe() -> (candidates, meta)          candidates from jevkit.compact
    actions(candidates, texts) -> [Action]   legal moves for this screen
    execute(action) -> dict                   perform one prebuilt action
    settle()                                  wait for the UI, optional
Action = {"id", "line", "kind", "call": <anything execute understands>}.
"""
import hashlib
import json
import re
import time
from pathlib import Path

from typesafe_sdk import Choice, Noul

from . import compact, config
from .judge import Judge, gate

DEFAULT_FORBID = re.compile(
    r"\b(send|pay|buy|purchase|checkout|delete|remove|erase|reset|sign ?in|log ?in|sign ?out|"
    r"log ?out|allow|call|subscribe|confirm|unsubscribe|transfer|share)\b", re.I)
RUNS = Path(config.LOG_PATH).parent / "runs" if config.LOG_PATH else None


def _screen_hash(cands):
    return hashlib.sha1("\n".join(compact.lines(cands)).encode()).hexdigest()[:12]


class Runner:
    def __init__(self, surface, judge=None, forbid=DEFAULT_FORBID, max_steps=12, max_seconds=180,
                 act_confidence=None, max_menu=None, done_confidence=0.85):
        self.surface = surface
        self.judge = judge or Judge()
        self.forbid = forbid
        self.max_steps = max_steps
        self.max_seconds = max_seconds
        self.act_confidence = config.HIGH if act_confidence is None else act_confidence
        self.max_menu = max_menu or config.MAX_CANDIDATES
        self.done_confidence = done_confidence

    # -- one step -------------------------------------------------------------

    def _menu(self, cands, texts):
        acts = [a for a in self.surface.actions(cands, texts) if not self.forbid.search(a["line"])]
        return acts[: self.max_menu - 1]

    def _choose(self, goal, cands, menu, history):
        # Exact lookups belong in code: which visible items does the goal name verbatim?
        gl = goal.lower()
        named = [c["line"] for c in cands
                 if (c.get("text") or c.get("label") or "").strip() and len((c.get("text") or c.get("label")).strip()) > 2
                 and re.search(r"\b" + re.escape((c.get("text") or c.get("label")).strip().lower()) + r"\b", gl)]
        state = {"goal": goal,
                 "screen": compact.lines(cands)[: config.MAX_STATE_LINES],
                 "items_named_in_goal_now_visible": named[:10],
                 "recent_steps": history[-4:],
                 "moves": [a["line"] for a in menu]}
        criteria = {a["id"]: a["line"] for a in menu}      # `stuck` is the abstain; no `none` here
        qs = {
            "move": Choice(
                instructions="Which single listed move is the best next step toward `goal` from the current "
                             "`screen`? The goal may name several steps in order: take the earliest step "
                             "that is not done yet. If the item for that step is visible on the screen, tap "
                             "or click it; scroll only when it is not visible. "
                             "`items_named_in_goal_now_visible` lists visible items whose text appears in the "
                             "goal; if the next step's item is among them, choose the move that taps or clicks it. "
                             "Do not repeat a move from `recent_steps` that did not change the screen.",
                criteria=criteria),
            "stuck": Noul(
                instructions="Is it true that none of the listed `moves` would bring the screen closer to `goal`? "
                             "Scrolling to reveal items not yet visible counts as progress when the goal names "
                             "something that is not on the screen.",
                criteria={"true": "No listed move helps: the screen is unrelated to the goal and scrolling would not reveal it.",
                          "false": "At least one listed move opens, selects or reveals (by scrolling) something the goal needs."}),
            "goal_met": Noul(
                instructions="Is the end result described by `goal` already fully reached on the current "
                             "`screen`? A control that would reach it (a button, row or link named like "
                             "the goal) does not count; the destination or content itself must be showing.",
                criteria={"true": "The goal's end result is showing now (e.g. the named pane, page or "
                                  "content is open, or the requested value is visible).",
                          "false": "Only a way to get there is visible, or something the goal asks for "
                                   "is still missing."}),
        }
        return self.judge.ask(state, qs, tag="run")

    # -- the loop -------------------------------------------------------------

    def run(self, goal, texts=()):
        t0 = time.time()
        history, trace = [], []
        last_hash, same_count = None, 0
        status, reason = "max_steps", None
        cands, meta = [], {}
        for step in range(1, self.max_steps + 1):
            if time.time() - t0 > self.max_seconds:
                status, reason = "timeout", f"{self.max_seconds}s"
                break
            cands, meta = self.surface.observe()
            k = self.judge.classify(cands, meta)
            rec = {"step": step, "title": meta.get("window_title"), "lines": len(cands),
                   "kind": k.get("kind"), "consequential": k.get("consequential"), "dialog_kind": k.get("dialog_kind")}
            if k.get("unavailable"):
                status, reason = "unavailable", k.get("error_text"); trace.append(rec); break
            if k.get("kind") == "auth" or k.get("dialog_kind") in ("auth", "consequential") or k.get("kind") == "error":
                status, reason = "blocked", f"screen is {k.get('kind')} / dialog {k.get('dialog_kind')}"; trace.append(rec); break
            h = _screen_hash(cands)
            same_count = same_count + 1 if h == last_hash else 0
            last_hash = h
            if same_count >= 2:
                status, reason = "stuck", "screen unchanged after two actions"; trace.append(rec); break

            menu = self._menu(cands, texts)
            a = self._choose(goal, cands, menu, history)
            if a.get("unavailable"):
                status, reason = "unavailable", a.get("error_text"); trace.append(rec); break
            mv, met, stuck = a["answers"]["move"], a["answers"]["goal_met"]["p"], a["answers"]["stuck"]["p"]
            by_id = {m["id"]: m for m in menu}
            choice = by_id.get(mv["choice"])          # `none` or unknown id -> None, fail closed
            top = sorted(mv["probabilities"].items(), key=lambda kv: -kv[1])[:3]
            rec.update({"menu": len(menu), "choice": mv["choice"], "confidence": round(mv["confidence"], 3),
                        "top": [(k, round(v, 3)) for k, v in top],
                        "goal_met_p": round(met, 3), "stuck_p": round(stuck, 3), "gate": gate(mv["confidence"])})
            if met >= self.done_confidence:
                status, reason = "done", f"goal_met p={met:.2f}"; trace.append(rec); break
            # Act on a confident pick, or on a clear leader when Jev also says a move exists.
            p1 = top[0][1] if top else 0.0
            p2 = top[1][1] if len(top) > 1 else 0.0
            clear_leader = p1 >= config.LOW and stuck < 0.5 and p1 >= 2.0 * p2
            if choice is None or stuck >= 0.8 or not (mv["confidence"] >= self.act_confidence or clear_leader):
                # No confident move left. If Jev also leans toward the goal being met, say so:
                # OCR noise (e.g. "¡OS Version") keeps goal_met below the strict bar on real phones.
                if met >= config.YES:
                    status, reason = "likely_done", f"goal_met p={met:.2f}, no confident next move"
                else:
                    status, reason = "unsure", f"choice={mv['choice']} confidence={mv['confidence']:.2f} top={top} stuck={stuck:.2f}"
                trace.append(rec); break

            before = cands
            rec["action"] = choice["line"]
            try:
                rec["result"] = self.surface.execute(choice)
            except Exception as e:      # noqa: BLE001 - a failed action ends the run, never crashes it
                status, reason = "action_failed", f"{type(e).__name__}: {e}"; trace.append(rec); break
            self.surface.settle()
            after, meta2 = self.surface.observe()
            v = self.judge.verify(f"the screen changed as a result of: {choice['line']}", before, after, meta2, meta)
            d = v.get("diff", {})
            # OCR noise flips a line or two between identical screens; ask for real movement.
            changed = bool(d.get("title_after")) or (len(d.get("added", [])) + len(d.get("removed", [])) >= 3)
            rec["verify"] = {x: v.get(x) for x in ("landed", "p_landed", "dialog", "error", "auth", "gate", "note")}
            rec["verify"]["changed"] = changed
            history.append(f"step {step}: {choice['line']} -> " + ("changed the screen" if changed else "no visible change"))
            trace.append(rec)
            if v.get("auth") or v.get("error"):
                status, reason = "blocked", "auth or error after action"; break
        result = {"status": status, "reason": reason, "goal": goal, "steps": len(trace),
                  "seconds": round(time.time() - t0, 1), "final_screen": compact.lines(cands)[:80],
                  "final_title": meta.get("window_title"), "trace": trace}
        if RUNS:
            try:
                RUNS.mkdir(parents=True, exist_ok=True)
                p = RUNS / f"{time.strftime('%Y%m%d-%H%M%S')}.json"
                p.write_text(json.dumps(result, indent=2, default=str))
                result["trace_path"] = str(p)
            except OSError:
                pass
        return result


# -- desktop surface over Cua Driver ------------------------------------------

class CuaSurface:
    """One window through the real driver. Menu: click each interactive
    element, type each allowed text into each text field, scroll down/up."""
    TYPABLE = {"AXTextField", "AXTextArea", "AXSearchField", "AXComboBox"}

    def __init__(self, pid, window_id, session=None, settle_s=0.8):
        self.pid, self.wid, self.session, self.settle_s = pid, window_id, session, settle_s
        from . import cua
        self.cua = cua

    def observe(self):
        return self.cua.snapshot(self.pid, self.wid, session=self.session)

    def actions(self, cands, texts):
        acts = []
        for c in cands:
            if not c.get("interactive") or c["role"] in ("AXWindow",):
                continue
            base = c["line"].split("] ", 1)[1]
            if c["role"] in self.TYPABLE:
                for i, t in enumerate(texts):
                    acts.append({"id": f"type{i}_{c['id']}", "kind": "type", "line": f"[type{i}_{c['id']}] type {t!r} into {base}",
                                 "call": ("set_value", {"element_token": c["element_token"], "value": t})})
            acts.append({"id": f"click_{c['id']}", "kind": "click", "line": f"[click_{c['id']}] click {base}",
                         "call": ("click", {"element_token": c["element_token"]})})
        acts.append({"id": "scroll_down", "kind": "scroll", "line": "[scroll_down] scroll down to see items further down the list",
                     "call": ("scroll", {"direction": "down", "amount": 5})})
        acts.append({"id": "scroll_up", "kind": "scroll", "line": "[scroll_up] scroll up to see items further up the list",
                     "call": ("scroll", {"direction": "up", "amount": 5})})
        return acts

    def execute(self, action):
        tool, kw = action["call"]
        kw = dict(kw, pid=self.pid, window_id=self.wid)
        if self.session:
            kw["session"] = self.session
        return self.cua.call(tool, **kw)

    def settle(self):
        time.sleep(self.settle_s)
