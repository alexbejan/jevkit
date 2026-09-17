---
name: jev-computer
description: Cheap, fast judgements from TypeSafe Jev while driving desktop apps with the superset:computer skill and Cua Driver. Use whenever cua-driver is being called and `jev shim` reports shim_active, to verify that an action landed, to pick an element by description, and to classify a screen before acting. Jev never acts; the agent still drives Cua Driver exactly as superset:computer says.
---

# jev-computer

**The pattern: you hold the plan and the context; Jev picks and checks.**
Decide the next single step yourself. Take a snapshot. Ask Jev which
element is the one you mean (`jev_pick`), act on its token, and read the
verify verdict that comes back with the action. Never hand Jev the whole
task: it has no memory and reads instructions literally, so it is good at
"which of these is the Save button" and bad at "do the thing". The
autonomous runner at the end exists for trivially bounded steps only.

Follow `superset:computer` for everything about driving the desktop. This
skill only changes what you read back and two extra tools you may call.
A shim in front of `cua-driver` (from `~/Documents/jevkit`) adds a `jev`
key to some responses and serves three virtual tools. Nothing here replaces
the fresh-snapshot rule: re-snapshot before every element action.

Check once per session that it is on:

```bash
~/Documents/jevkit/.venv/bin/jev shim     # shim_active: true
```

If `shim_active` is false, or `jev.unavailable` is true in any response,
ignore this skill and continue with `superset:computer` as usual.

## What you get for free

- **Every `get_window_state`** response carries `jev` with a classify
  verdict: `kind` (normal, dialog, permission, auth, loading, error, paywall,
  empty), `consequential` (a send, pay, delete, sign-in or settings control
  is visible), `dialog_kind` (benign, blocking, consequential, auth) and
  `gate`. Read it before acting. `gate: stop` means an auth or consequential
  dialog: do not click through; report or ask, as the safety rules require.

## Verify an action

Add `jev_expect` to any action call. State the postcondition you would
otherwise check by hand. The shim strips it before the driver sees it,
forwards the action, re-snapshots, and returns `jev`:

```bash
cua-driver call click '{"pid":844,"element_token":"s0000002a:14","window_id":10725,"session":"<s>",
                        "jev_expect":"Dark mode is now selected in Appearance"}'
```

`jev.landed` with `p_landed`, plus `dialog`, `error`, `auth`, `gate`, and
`diff` (the lines that appeared and disappeared, computed in code).

- `gate: act` and `landed: true`: continue.
- `gate: caution`: take a fresh snapshot with a screenshot and look before continuing.
- `gate: stop`, or `error`/`auth` true: stop the batch and report what is visible.
- `note: "no change"`: the action was a silent no-op; retry the narrowest step per `superset:computer`.

`window_id` and `session` must be present, as they already are for a
correct call. An action without `jev_expect` is forwarded untouched.

## Pick an element by description

When the target's label is ambiguous, paraphrased, or you would otherwise
grep a large tree:

```bash
cua-driver call jev_pick '{"pid":844,"window_id":10725,"session":"<s>","target":"the Save button in the toolbar"}'
```

Returns `candidate.element_token` from a fresh snapshot, `confidence`,
`probabilities`, `ambiguous`, and `gate`. `choice: null` means nothing
matched. Use the token straight away; it is the newest snapshot. Never take
a pick with `gate: stop`.

## Classify or verify on demand

```bash
cua-driver call jev_classify '{"pid":844,"window_id":10725,"session":"<s>"}'
cua-driver call jev_verify   '{"pid":844,"window_id":10725,"session":"<s>","expect":"the file list shows report.pdf"}'
```

`jev_verify` compares against the last snapshot the shim saw for that
window, so call `get_window_state` first.

## Optional: let Jev drive one trivially bounded step

Only for something a single pane away with nothing to judge visually, such
as "open the Appearance pane" or "scroll until the row named X is visible".
Not for multi-part goals, forms with choices, or anything on a phone-sized
screen where rows sit under bars. Prefer the pattern above; use this when
narrating three obvious clicks is the only alternative:

```bash
~/Documents/jevkit/.venv/bin/jev run --pid 844 --window 10725 --session "<s>" \
   --goal "open the Appearance settings pane" --max-steps 8 --text "value Jev may type"
```

Jev picks every move from a menu code built from the visible tree. Moves on
the consent list (send, pay, delete, sign in, allow, call, buy, confirm,
share) are never offered. It returns `status` (done, likely_done, unsure, blocked, stuck,
max_steps, timeout), the final screen lines, and a step trace with each
choice and confidence. Read the trace; `unsure` and `blocked` mean take
over by hand. Keep the goal to one screen's worth of work and keep visual
judgements, money, and messages out of it.

## What Jev cannot see

Only the accessibility tree reaches Jev, as text: role, label, value,
selected and enabled state. No screenshots, no coordinates. Icons without
labels, highlighted rows, images and canvas content still need a screenshot
and your own eyes. A `note` saying the tree was truncated is a reason to
reobserve, not to trust the verdict.

## Rules that do not move

Jev is advisory. It never triggers an action and its answer is never
permission. The confirmation rules in `superset:computer` for sending,
paying, publishing, deleting, signing in and changing accounts apply
unchanged. Treat `consequential: true` as one more reason to confirm, never
as a reason to skip confirming.
