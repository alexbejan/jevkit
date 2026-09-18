# Set up Cua Driver + Jev on a new Mac

Paste everything below the line into a Claude Code session running inside
Superset on the new Mac. Before you paste, replace `<YOUR_TYPESAFE_KEY>` with
the TypeSafe API key you were given. The key goes into macOS Keychain only. It
is never written to a file.

What you get: the Superset `computer` skill drives macOS apps through Cua
Driver. A shim called `jevkit` sits in front of the driver and adds cheap,
typed judgements from TypeSafe Jev (which element did you mean, did the
action land, what kind of screen is this). Optionally, `phone-harness` gives
the same thing for an iPhone or Android.

Prerequisites you must do by hand: a Mac with Superset installed and a
terminal that has been granted Accessibility and Screen Recording in System
Settings, Privacy & Security. Cua Driver will prompt for its own permissions
on first run.

---

Set up Cua Driver with the jevkit Jev shim on this Mac, end to end, and verify
it works. Work through the steps in order. Do not skip verification steps.
Never print, log, or write the API key anywhere except the Keychain command.

## 1. Tools

Make sure `uv`, `git`, and `gh` are installed. Install missing ones with
Homebrew (`brew install uv git gh`). Install Homebrew first if it is missing.
Ensure `~/.local/bin` exists and is on PATH in `~/.zshrc`.

## 2. Cua Driver

If `cua-driver --version` does not work, install it:

```bash
/bin/bash -c "$(curl -fsSL https://cua.ai/driver/install.sh)"
```

Confirm `~/.local/bin/cua-driver` exists and `cua-driver --version` prints a
version. If the driver asks for Accessibility or Screen Recording permission,
tell me exactly which System Settings pane to open and wait for me to grant it
before continuing.

## 3. jevkit

```bash
git clone https://github.com/alexbejan/jevkit ~/Documents/jevkit
cd ~/Documents/jevkit
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e '.[dev]'
```

The path `~/Documents/jevkit` matters. phone-harness and the skill text assume
it. Do not clone it anywhere else.

## 4. TypeSafe key

Store the key in Keychain. This is the only place it may go:

```bash
security add-generic-password -a "$USER" -s TYPESAFE_API_KEY -w '<YOUR_TYPESAFE_KEY>' -U
```

Then verify it is picked up and a live call succeeds:

```bash
~/Documents/jevkit/.venv/bin/jev doctor --live
```

`key_source` must be `keychain` and `ok` must be `true`. If `key_source` is
null, the terminal was denied Keychain access. Tell me, and I will approve the
Keychain prompt.

## 5. The shim

The shim is a `cua-driver` executable that sits first on PATH, forwards every
call to the real driver, and adds a `jev` key to responses.

```bash
mkdir -p ~/.local/shims
ln -sf ~/Documents/jevkit/shim/cua-driver ~/.local/shims/cua-driver
```

Then add this as the LAST PATH line of `~/.zshrc` so it wins over
`~/.local/bin`:

```bash
export PATH="$HOME/.local/shims:$PATH"
```

Open a fresh shell and verify:

```bash
~/Documents/jevkit/.venv/bin/jev shim
```

`shim_active` must be `true`, `link_exists` must be `true`, and `real_driver`
must point at `~/.local/bin/cua-driver`. If `path_resolves_to` is not the shim,
the PATH line is in the wrong place in `~/.zshrc`. Fix it.

## 6. The skill

Register the companion skill so Claude Code loads it alongside the managed
Superset `computer` skill:

```bash
mkdir -p ~/.claude/skills
ln -sfn ~/Documents/jevkit/skills/jev-computer ~/.claude/skills/jev-computer
```

Then add this block to `~/.claude/CLAUDE.md` (create the file if needed):

```markdown
## Browsing and desktop

When I ask you to browse, open, read, search, log in to, or do something on a
website on my behalf, drive Safari on this Mac through the `superset:computer`
skill (Cua Driver) with the `jev-computer` skill. Safari has my logins; the
Chrome that `chrome-devtools` and `agent-browser` launch is a separate empty
profile and is not me. Safari recipe: see "Browsing in Safari" in
`~/.claude/skills/jev-computer/SKILL.md`.

Use `chrome-devtools` or `agent-browser` only for testing a local dev server
or a page where being logged out is fine, or when I name them.
```

## 7. Run the tests

```bash
cd ~/Documents/jevkit && .venv/bin/pytest -q
```

All tests must pass. Report the count.

## 8. End-to-end check on a real window

Read `~/.claude/skills/superset/skills/computer/SKILL.md` and
`~/.claude/skills/jev-computer/SKILL.md`. Then, following those skills:

1. Open System Settings.
2. Start a Cua Driver session on it and call `get_window_state`. Confirm the
   response carries a `jev` key with a `kind` and a `gate`.
3. Call `jev_pick` with target "the search field at the top of the sidebar".
   Confirm it returns a candidate token with a confidence.
4. Click that token with `jev_expect` set to "the search field is focused".
   Confirm the response carries `jev.landed`.
5. End the session and quit System Settings.

Do not click anything that sends, pays, deletes, or signs in. If any `gate`
is `stop`, stop and tell me what is on screen.

## 9. Optional: phone-harness

Only do this if I say I want phone control. Follow
`https://github.com/alexbejan/phone-harness/blob/devicehub/install.md`
("Common" section, then the iPhone or Android section), clone on the
`devicehub` branch, then turn Jev on:

```bash
phone-harness config set jev.enabled true
phone-harness --doctor
```

## 10. Report

Give me a short summary: the Cua Driver version, the `jev doctor` output with
the key redacted, the `jev shim` output, the test count, and what happened in
the System Settings check. List anything that needed a permission I have not
granted yet.
