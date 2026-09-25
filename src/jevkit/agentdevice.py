"""agent-device (Callstack) as the phone's eyes and hands.

Snapshots are read here and compacted for Jev. Actions stay with the agent,
which calls `agent-device press/fill/scroll` itself, except inside `jev run`,
where the runner's AgentDeviceSurface executes one prebuilt action per step.

Every call names its session. The session was opened by the agent with an
explicit `--udid`, so nothing here can pick a different phone.
"""
import json
import os
import shutil
import subprocess

from . import compact


class AgentDeviceUnavailable(RuntimeError):
    pass


def binary():
    b = shutil.which("agent-device")
    if not b:
        raise AgentDeviceUnavailable("agent-device is not on PATH (npm install -g agent-device)")
    return b


def call(args, session, timeout=120):
    """Run one agent-device command with --json; return its `data`."""
    cmd = [binary(), *args, "--json", "--session", session]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=dict(os.environ))
    out = (r.stdout or "").strip()
    try:
        data = json.loads(out)
    except ValueError:
        raise AgentDeviceUnavailable(f"agent-device {args[0]}: {(out or r.stderr)[:300]}")
    if not data.get("success", False):
        err = data.get("error") or {}
        raise AgentDeviceUnavailable(f"agent-device {args[0]}: {err.get('code')}: {err.get('message')}")
    return data.get("data") or {}


def snapshot(session, scope=None, raw=False):
    """-> (candidates, meta). Interactive snapshot unless raw."""
    args = ["snapshot"] + ([] if raw else ["-i"])
    if scope:
        args += ["--scope", scope]
    data = call(args, session)
    meta = {"app": data.get("appBundleId") or data.get("appName"),
            "window_title": data.get("appName"),
            "keyboard": (data.get("keyboard") or {}).get("kind"),
            "refs_generation": data.get("refsGeneration"),
            "note": compact.agent_device_note(data),
            "hidden_below": "scroll-hidden-below" in ((data.get("visibility") or {}).get("reasons") or [])}
    return compact.agent_device_nodes(data), meta
