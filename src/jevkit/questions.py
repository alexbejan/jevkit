"""Question builders. Literal wording, explicit criteria, a no-match option
whenever nothing may fit. Ids are for code; meaning lives in the text.

Jev reads instructions literally. Boundary cases go in the criteria."""
from typesafe_sdk import Choice, Noul, Score

NONE = "none"


def verify(expect):
    """Did the expected change land? State carries the expectation, the
    lines that appeared and disappeared, and the current screen."""
    return {
        "landed": Noul(
            instructions=f"Compare `before` and `after`. Did this expected outcome happen: {expect!r}? "
                         "Judge from the `added`, `removed` and `after` lines only.",
            criteria={"true": "The added or after lines show the expected outcome.",
                      "false": "The expected outcome is absent, or the screen is unchanged."}),
        "unchanged": Noul(
            instructions="Is the screen effectively unchanged between `before` and `after` "
                         "(nothing meaningful added or removed)?"),
        "dialog": Noul(
            instructions="Does `after` show a new dialog, sheet, alert or popup that was not in `before`?"),
        "error": Noul(
            instructions="Does `after` show an error, warning, failure or 'could not' message?"),
        "auth": Noul(
            instructions="Does `after` ask for a password, passcode, PIN, passkey, sign-in or "
                         "two-factor code?"),
    }


def pick(target, candidates):
    """Which candidate is the one described? Always includes `none`."""
    criteria = {c["id"]: c["line"] for c in candidates}
    criteria[NONE] = "No listed candidate matches the description."
    return {
        "target": Choice(
            instructions=f"Which listed element best matches this description: {target!r}? "
                         f"Pick `{NONE}` if none of them does. Prefer an interactive element "
                         "(button, link, row, field) over plain text with the same words.",
            criteria=criteria),
        "ambiguous": Noul(
            instructions=f"Do two or more listed elements match {target!r} equally well?"),
    }


def classify():
    """One fan-out over the current screen. Nouls are independent so several
    may be true at once; `kind` is the one-word summary."""
    return {
        "kind": Choice(
            instructions="What kind of screen is this?",
            criteria={
                "normal": "Ordinary app content with no blocking overlay.",
                "dialog": "A dialog, sheet, alert or confirmation is in front.",
                "permission": "The OS or app asks to allow access (camera, location, notifications, files).",
                "auth": "A sign-in, password, passcode, PIN, passkey or two-factor prompt.",
                "loading": "Content is loading, spinning or empty while waiting.",
                "error": "An error or failure message dominates.",
                "paywall": "A purchase, subscription or upgrade offer blocks the content.",
                "empty": "No content is shown at all (blank or placeholder).",
            }),
        "consequential": Noul(
            instructions="Is there a visible control that would send a message, place a call, pay, "
                         "purchase, delete, sign in, sign out, or change settings if activated? "
                         "Look for words like Send, Pay, Buy, Delete, Remove, Confirm, Sign in, Allow.",
            criteria={"true": "Such a control is visible and enabled.",
                      "false": "No such control is visible."}),
        "keyboard": Noul(instructions="Is a software keyboard or text-entry focus visible?"),
        "modal": Noul(instructions="Is something blocking interaction with the content behind it?"),
        "unsaved": Noul(instructions="Is there an indication of unsaved changes or a draft in progress?"),
    }


def dialog_kind():
    return {
        "dialog_kind": Choice(
            instructions="If a dialog is showing, what kind is it?",
            criteria={
                "benign": "Tips, cookies, onboarding, 'what's new', rating prompts; safe to dismiss.",
                "blocking": "Must be answered to continue but has no external effect (e.g. choose a format).",
                "consequential": "Confirming would send, pay, delete, sign out or change an account or settings.",
                "auth": "Asks for credentials or a code.",
                NONE: "No dialog is showing.",
            })
    }


def severity(dimension, levels):
    """A Score over ordered, described levels. `levels` are concrete situations."""
    return {dimension: Score(instructions=f"Rate `{dimension}` on the described levels.",
                             criteria=list(levels))}
