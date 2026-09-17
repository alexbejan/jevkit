"""Read-only access to Cua Driver for snapshots. Actions never go through
here; the agent (or the shim) keeps calling `cua-driver` itself."""
import json
import shutil
import subprocess

from . import compact


class CuaUnavailable(RuntimeError):
    pass


def binary():
    b = shutil.which("cua-driver")
    if not b:
        raise CuaUnavailable("cua-driver is not on PATH")
    return b


def call(tool, timeout=30, **kw):
    r = subprocess.run([binary(), "call", tool, json.dumps(kw)], capture_output=True, text=True, timeout=timeout)
    out = (r.stdout or r.stderr).strip()
    try:
        data = json.loads(out)
    except ValueError:
        raise CuaUnavailable(f"cua-driver {tool}: {out[:300]}")
    if isinstance(data, dict) and data.get("code") in ("invalid_arguments", "refused", "window_id_not_found"):
        raise CuaUnavailable(f"cua-driver {tool} refused: {data}")
    return data


def snapshot(pid, window_id, session=None, query=None, max_elements=None):
    """Tree-only window state -> (candidates, meta). Cheap: no screenshot."""
    kw = {"pid": pid, "window_id": window_id, "include_screenshot": False}
    if session:
        kw["session"] = session
    if query:
        kw["query"] = query
    if max_elements:
        kw["max_elements"] = max_elements
    st = call("get_window_state", **kw)
    meta = {k: st.get(k) for k in ("snapshot_id", "window_title", "app_name", "element_count",
                                   "elements_complete", "degraded_reason", "total_element_count")}
    return compact.cua_elements(st.get("elements", []), tree_markdown=st.get("tree_markdown")), meta


def windows():
    d = call("get_accessibility_tree")
    return d.get("windows", [])
