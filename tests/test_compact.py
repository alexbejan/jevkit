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
