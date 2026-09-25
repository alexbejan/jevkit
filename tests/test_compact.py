from jevkit import compact


def test_finder_compacts_and_skips_menus(finder):
    c = compact.cua_elements(finder["elements"], tree_markdown=finder["tree_markdown"])
    assert 0 < len(c) < finder["element_count"]
    roles = {x["role"] for x in c}
    assert "AXMenuItem" not in roles          # 123 menu items in the fixture, none sent
    assert all(x["element_token"] for x in c)
    assert all("x" not in x["line"].split("]")[1][:3] for x in c)   # no coordinates in text
    labels = " ".join(x["line"] for x in c)
    assert "Recents" in labels and "Applications" in labels
    cell = next(x for x in c if "Applications" in x["line"])
    assert cell["role"] == "AXCell" and cell["interactive"]


def test_settings_keeps_checkboxes(settings):
    c = compact.cua_elements(settings["elements"])
    assert any(x["role"] == "AXCheckBox" for x in c)
    assert len(c) <= 300


def test_include_menus_flag(finder):
    with_menus = compact.cua_elements(finder["elements"], include_menus=True, max_lines=10_000)
    without = compact.cua_elements(finder["elements"], max_lines=10_000)
    assert len(with_menus) > len(without)


def test_phone_boxes_reading_order_and_flags(phone_boxes):
    c = compact.phone_boxes(phone_boxes)
    assert [x["text"] for x in c] == ["Settings", "General", "Accessibility", "Privacy & Security"]
    assert c[0]["id"] == "t0" and c[0]["x"] == 200
    assert "low-ocr-confidence" in c[3]["line"]
    assert "low-ocr-confidence" not in c[1]["line"]


def test_diff_strips_ids(phone_boxes):
    a = compact.phone_boxes(phone_boxes)
    b = compact.phone_boxes(phone_boxes[1:])      # "Settings" scrolled away, ids shift
    d = compact.diff(a, b)
    assert d["removed"] == ["'Settings'"]
    assert d["added"] == []
    assert d["unchanged"] == 3 and d["changed"]
    assert not compact.diff(a, a)["changed"]


def test_truncated_note():
    assert compact.truncated_note({"elements_complete": False})
    assert compact.truncated_note({"degraded_reason": "ax_window_unresolved"})
    assert compact.truncated_note({"elements_complete": True}) is None
    # Cua flags some complete walks as incomplete; trust the counts when both are present.
    assert compact.truncated_note({"elements_complete": False, "element_count": 241, "total_element_count": 241}) is None
    assert compact.truncated_note({"elements_complete": False, "element_count": 2000, "total_element_count": 5000})


def test_child_text_parses_markdown(finder):
    ct = compact.child_text(finder["tree_markdown"])
    assert ct[3].startswith("Recents") and "Applications" in ct[8]
    assert 6 in ct and ct[6] == "Favorites"        # header row with only a static child


def _ad_fixture():
    import json
    from pathlib import Path
    return json.loads((Path(__file__).parent / "fixtures" / "agent_device_settings.json").read_text())


def test_agent_device_settings_rows():
    snap = _ad_fixture()
    c = compact.agent_device_nodes(snap)
    labels = [x["label"] for x in c]
    assert "General" in labels and "Accessibility" in labels
    general = next(x for x in c if x["label"] == "General")
    assert general["interactive"] and general["ref"] == f"@e8~s{snap['refsGeneration']}"
    assert general["line"].startswith("[e8] Cell ")
    assert not any(x["role"] in ("application", "other", "collectionview") for x in c)
    assert any(x["field"] for x in c)                 # the search field
    assert compact.agent_device_note(snap) is None


def test_agent_device_note_flags_bad_snapshots():
    assert compact.agent_device_note({"truncated": True})
    assert compact.agent_device_note({"snapshotQuality": {"state": "sparse"}})


def test_row_context_separates_repeated_labels():
    snap = {"refsGeneration": 7, "nodes": [
        {"index": 0, "ref": "e1", "type": "Table"},
        {"index": 1, "ref": "e2", "type": "Cell", "parentIndex": 0, "label": "Coldplay row"},
        {"index": 2, "ref": "e3", "type": "StaticText", "parentIndex": 1, "label": "Coldplay"},
        {"index": 3, "ref": "e4", "type": "Button", "parentIndex": 1, "label": "Buy"},
        {"index": 4, "ref": "e5", "type": "Cell", "parentIndex": 0, "label": "Muse row"},
        {"index": 5, "ref": "e6", "type": "StaticText", "parentIndex": 4, "label": "Muse"},
        {"index": 6, "ref": "e7", "type": "Button", "parentIndex": 4, "label": "Buy"},
        {"index": 7, "ref": "e8", "type": "Button", "parentIndex": 0, "label": "Done"},
    ]}
    c = {x["id"]: x for x in compact.agent_device_nodes(snap)}
    assert "in the row of 'Coldplay'" in c["e4"]["line"]
    assert "in the row of 'Muse'" in c["e7"]["line"]
    assert "row of" not in c["e8"]["line"]            # unique labels stay as they are


def test_credential_fields_are_marked():
    snap = {"nodes": [
        {"index": 0, "ref": "e1", "type": "SecureTextField", "label": "Code"},
        {"index": 1, "ref": "e2", "type": "TextField", "label": "Password"},
        {"index": 2, "ref": "e3", "type": "TextField", "label": "iMessage"},
    ]}
    c = {x["id"]: x for x in compact.agent_device_nodes(snap)}
    assert c["e1"]["secure"] and c["e2"]["secure"] and not c["e3"]["secure"]
