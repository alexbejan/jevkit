"""Turn observations into short text Jev can judge, and diff them in code.

Three sources today:
  - Cua Driver `get_window_state` elements (desktop)
  - agent-device `snapshot --json` nodes (phone, simulator, emulator)
  - phone-harness `ocr()` boxes or `ui()` nodes (phone, fallback)

Each compactor returns a list of candidates: {"id", "line", **handle}. `line`
is what Jev sees; the handle (element_token, or x/y) stays in code. Ids are
short and stable within one observation only.

Rules from Jev's own jaggedness page: no coordinates in the text, filter
irrelevant detail first, keep counting and diffs in code.
"""
import re

from . import config

# Roles worth showing. Containers without a label add nothing but noise.
INTERACTIVE = {
    "AXButton", "AXCheckBox", "AXRadioButton", "AXPopUpButton", "AXMenuButton",
    "AXTextField", "AXTextArea", "AXSearchField", "AXComboBox", "AXLink",
    "AXTab", "AXSlider", "AXIncrementor", "AXDisclosureTriangle", "AXSwitch",
    "AXCell", "AXRow", "AXMenuItem", "AXToggle", "AXColorWell", "AXDateField",
}
TEXTUAL = {"AXStaticText", "AXHeading", "AXWindow", "AXSheet", "AXDialog", "AXGroup"}
# Menus dwarf every window; the agent uses invoke_menu for those anyway.
SKIP_UNDER = {"AXMenu", "AXMenuBar"}


def _short_role(role):
    return role[2:] if role and role.startswith("AX") else (role or "?")


def cua_elements(elements, include_menus=False, max_lines=None, tree_markdown=None):
    """Cua `elements` -> candidates. Interactive elements always; static text
    only when it carries a value; menu contents skipped unless asked.
    `tree_markdown` (from the same snapshot) supplies labels for rows and
    cells whose text lives in un-indexed children."""
    max_lines = max_lines or config.MAX_STATE_LINES
    child = child_text(tree_markdown) if tree_markdown else {}
    by_index = {e.get("element_index"): e for e in elements}
    out = []

    def under_menu(e):
        seen = 0
        while e is not None and seen < 40:
            if e.get("role") in SKIP_UNDER:
                return True
            e = by_index.get(e.get("parent_index"))
            seen += 1
        return False

    for e in elements:
        role = e.get("role") or ""
        label = (e.get("label") or "").strip()
        value = e.get("value")
        value = "" if value is None else str(value).strip()
        if not label and not value and e.get("element_index") in child:
            label = child[e["element_index"]]
        interactive = role in INTERACTIVE
        if not interactive and not (role in TEXTUAL and (label or value)):
            continue
        if not include_menus and role in ("AXMenuItem",) and under_menu(e):
            continue
        if not include_menus and role in SKIP_UNDER:
            continue
        if not (label or value) and role not in ("AXTextField", "AXTextArea", "AXSearchField"):
            continue
        flags = []
        if e.get("selected") is True:
            flags.append("selected")
        if e.get("enabled") is False:
            flags.append("disabled")
        if e.get("focused") is True:
            flags.append("focused")
        parts = [_short_role(role)]
        if label:
            parts.append(f'"{label[:120]}"')
        if value and value != label:
            parts.append(f"value={value[:160]!r}")
        if flags:
            parts.append("(" + ", ".join(flags) + ")")
        cid = f"e{e.get('element_index')}"
        out.append({"id": cid, "line": f"[{cid}] " + " ".join(parts),
                    "element_index": e.get("element_index"),
                    "element_token": e.get("element_token"), "role": role,
                    "label": label, "value": value, "interactive": interactive,
                    "secure": role == "AXSecureTextField" or bool(CREDENTIAL.search(label))})
        if len(out) >= max_lines:
            break
    return add_row_context(out, lambda c: c["element_index"], by_index, "parent_index",
                           lambda n: (n.get("label") or "").strip() or child.get(n.get("element_index"), ""))


# Fields nobody types into on the agent's behalf: passwords, one-time codes, cards.
CREDENTIAL = re.compile(r"\b(password|passcode|passwort|parol[aă]|pin|one[- ]time code|verification code|"
                        r"card number|cvv|cvc|security code|expiry|iban)\b", re.I)


def add_row_context(cands, index_of, nodes, parent_key, label_of, limit=2, max_row=8):
    """A label that appears more than once says nothing about which one is
    meant ("Buy", "Buy", "Buy"). Append the text of the row it sits in, taken
    from its siblings (or, failing that, its parent), so each reads apart:
    `Button "Buy" (in the row of 'Coldplay', 'Oct 2')`. Code does the
    grouping; Jev only reads the result. A parent with more than `max_row`
    children is a page or a list, not a row, so it lends no context."""
    counts = {}
    for c in cands:
        key = (c.get("label") or "").strip().lower()
        if key:
            counts[key] = counts.get(key, 0) + 1
    children = {}
    for i, n in nodes.items():
        children.setdefault(n.get(parent_key), []).append(i)
    for c in cands:
        key = (c.get("label") or "").strip().lower()
        if counts.get(key, 0) < 2:
            continue
        me = nodes.get(index_of(c)) or {}
        parent = me.get(parent_key)
        texts = []
        siblings = children.get(parent, [])
        if len(siblings) > max_row:
            continue
        for sib in siblings:
            if sib == index_of(c):
                continue
            t = (label_of(nodes[sib]) or "").strip()
            if t and t.lower() != key and t not in texts:
                texts.append(t[:60])
            if len(texts) >= limit:
                break
        if not texts and parent in nodes:
            t = (label_of(nodes[parent]) or "").strip()
            if t and t.lower() != key:
                texts.append(t[:60])
        if texts:
            c["row"] = texts
            c["line"] += " (in the row of " + ", ".join(repr(t) for t in texts) + ")"
    return cands


# agent-device roles (XCUIElementType names on Apple, normalised names elsewhere).
AD_PRESS = {"button", "link", "switch", "checkbox", "radio", "radiobutton", "tab", "tabbaritem", "cell",
            "menuitem", "segmentedcontrol", "key", "slider", "stepper", "picker", "pickerwheel",
            "toggle", "image", "icon"}
AD_FIELD = {"textfield", "securetextfield", "searchfield", "textview", "textarea", "textbox", "edittext"}
AD_TEXT = {"statictext", "text", "heading", "navigationbar", "alert", "sheet", "dialog"}


def _ad_role(n):
    return re.sub(r"[^a-z0-9]", "", (n.get("type") or n.get("role") or "").lower())


def agent_device_nodes(snapshot, max_lines=None):
    """agent-device `snapshot --json` data (the `data` object) -> candidates.
    The handle is the ref, pinned to this snapshot's generation (`@e8~s479811`)
    so a stale ref fails loudly instead of pressing whatever moved there.
    Offscreen, disabled-looking and unlabelled container nodes are dropped."""
    max_lines = max_lines or config.MAX_STATE_LINES
    nodes = {n["index"]: n for n in snapshot.get("nodes", []) if "index" in n}
    gen = snapshot.get("refsGeneration")
    out = []
    for n in snapshot.get("nodes", []):
        if n.get("visibleToUser") is False or not n.get("ref"):
            continue
        role = _ad_role(n)
        label = (n.get("label") or "").strip()
        value = n.get("value")
        value = "" if value is None else str(value).strip()
        field = role in AD_FIELD or n.get("editable") is True
        interactive = field or role in AD_PRESS or (n.get("hittable") is True and role not in ("other", "application", "window", "collectionview", "scrollview", "table", "group"))
        if not interactive and not (role in AD_TEXT and (label or value)):
            continue
        if not (label or value or n.get("identifier")) and not field:
            continue
        flags = []
        if n.get("selected") is True:
            flags.append("selected")
        if n.get("enabled") is False:
            flags.append("disabled")
        if n.get("hittable") is False and interactive:
            flags.append("not tappable now")
        parts = [n.get("type") or n.get("role") or "?"]
        if label:
            parts.append(f'"{label[:120]}"')
        elif n.get("identifier"):
            parts.append(f"id={n['identifier'][:80]!r}")
        if value and value != label:
            parts.append(f"value={value[:160]!r}")
        if flags:
            parts.append("(" + ", ".join(flags) + ")")
        base = n["ref"] if n["ref"].startswith("@") else "@" + n["ref"]
        ref = f"{base}~s{gen}" if gen is not None and "~s" not in base else base
        cid = base[1:]
        out.append({"id": cid, "line": f"[{cid}] " + " ".join(parts), "ref": ref, "index": n["index"],
                    "role": role, "label": label, "value": value,
                    "interactive": interactive and n.get("enabled") is not False,
                    "field": field, "secure": role == "securetextfield" or bool(CREDENTIAL.search(label))})
        if len(out) >= max_lines:
            break
    return add_row_context(out, lambda c: c["index"], nodes, "parentIndex",
                           lambda n: (n.get("label") or n.get("value") or "").strip())


def agent_device_note(snapshot):
    """A reobserve trigger, like truncated_note for Cua."""
    if snapshot.get("truncated"):
        return "snapshot truncated"
    q = (snapshot.get("snapshotQuality") or {}).get("state")
    if q and q != "healthy":
        return f"snapshot quality: {q}"
    return None


_MD_LINE = re.compile(r'^(\s*)- (?:\[(\d+)\] )?(AX\w+)(?: "([^"]*)")?(?: = "([^"]*)")?(?: \(([^)]*)\))?')


def child_text(tree_markdown):
    """Cua only indexes actionable elements; a cell's visible label is often an
    un-indexed AXStaticText child in `tree_markdown`. Map element_index ->
    text gathered from its un-indexed descendants (static text and image
    descriptions), so a label-less row still reads as "Applications"."""
    out = {}
    stack = []            # (indent, element_index or None)
    for raw in (tree_markdown or "").splitlines():
        m = _MD_LINE.match(raw)
        if not m:
            continue
        indent = len(m.group(1))
        idx = int(m.group(2)) if m.group(2) else None
        role, label, value, paren = m.group(3), m.group(4), m.group(5), m.group(6)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if idx is None:
            text = value or label or (paren if role == "AXImage" else None)
            if text:
                owner = next((i for _, i in reversed(stack) if i is not None), None)
                if owner is not None:
                    out.setdefault(owner, []).append(text.strip())
        stack.append((indent, idx))
    return {k: " / ".join(dict.fromkeys(v)) for k, v in out.items()}


def phone_boxes(boxes, max_lines=None):
    """phone-harness ocr() boxes ({text, confidence, x, y, w, h, source}) or
    ui() nodes ({text, desc, id, clickable, x, y, ...}) -> candidates in
    reading order (top to bottom, left to right)."""
    max_lines = max_lines or config.MAX_STATE_LINES
    rows = []
    for b in boxes:
        text = (b.get("text") or b.get("desc") or b.get("id") or "").strip()
        if not text:
            continue
        rows.append((b.get("y", 0), b.get("x", 0), text, b))
    rows.sort(key=lambda r: (round(r[0] / 12), r[1]))   # ~one text line per bucket
    out = []
    for i, (_, _, text, b) in enumerate(rows[:max_lines]):
        cid = f"t{i}"
        flags = []
        if b.get("clickable"):
            flags.append("tappable")
        if b.get("source") == "pixels" and b.get("confidence", 1.0) < 0.6:
            flags.append("low-ocr-confidence")
        line = f"[{cid}] {text[:160]!r}" + (" (" + ", ".join(flags) + ")" if flags else "")
        out.append({"id": cid, "line": line, "text": text, "x": b.get("x"), "y": b.get("y"),
                    "w": b.get("w"), "h": b.get("h"), "interactive": bool(b.get("clickable", True))})
    return out


def lines(candidates):
    return [c["line"] for c in candidates]


def _key(line):
    # Drop the per-observation id so the same element matches across snapshots.
    return line.split("] ", 1)[1] if "] " in line else line


def diff(before, after):
    """Set difference of candidate lines, ids stripped. Counting stays here."""
    b = {_key(c["line"]) for c in before}
    a = {_key(c["line"]) for c in after}
    return {"added": sorted(a - b), "removed": sorted(b - a),
            "unchanged": len(a & b), "changed": bool(a ^ b)}


def truncated_note(meta):
    """A reobserve trigger. Cua reports incomplete walks; surface it."""
    total, got = meta.get("total_element_count"), meta.get("element_count")
    if meta.get("elements_complete") is False and (total is None or got is None or got < total):
        return "accessibility tree incomplete (truncated walk)"
    if meta.get("degraded_reason"):
        return f"degraded: {meta['degraded_reason']}"
    return None
