import json

from jevkit import cli


def run(capsys, *argv):
    code = cli.main(list(argv))
    return code, json.loads(capsys.readouterr().out)


def test_doctor_offline(capsys, monkeypatch):
    from jevkit import keys
    monkeypatch.setattr(keys, "from_keychain", lambda service=None: None)
    code, rep = run(capsys, "doctor")
    assert code == 0 and rep["key_source"] is None and rep["model"].startswith("jev-")


def test_phone_commands_with_mock(capsys, monkeypatch, tmp_path, phone_boxes):
    import jevkit.config as c
    monkeypatch.setattr(c, "MOCK", True)
    boxes = tmp_path / "b.json"; boxes.write_text(json.dumps(phone_boxes))
    before = tmp_path / "a.json"; before.write_text(json.dumps(phone_boxes[:1]))
    code, r = run(capsys, "phone-pick", "--boxes", str(boxes), "--target", "General")
    assert code == 0 and r["candidate"]["text"]
    code, r = run(capsys, "phone-verify", "--boxes", str(boxes), "--before", str(before), "--expect", "list shown")
    assert code == 0 and r["diff"]["changed"]
    code, r = run(capsys, "phone-classify", "--boxes", str(boxes))
    assert code == 0 and r["kind"]


def test_ask_from_files(capsys, monkeypatch, tmp_path):
    import jevkit.config as c
    monkeypatch.setattr(c, "MOCK", True)
    s = tmp_path / "s.json"; s.write_text(json.dumps({"text": "Help! [yes:urgent]"}))
    q = tmp_path / "q.json"; q.write_text(json.dumps({"urgent": {"type": "noul", "instructions": "Is this urgent?"}}))
    code, r = run(capsys, "ask", "--state-file", str(s), "--questions-file", str(q))
    assert code == 0 and r["answers"]["urgent"]["p"] > 0.5


def test_missing_file_is_json_error(capsys):
    code, r = run(capsys, "phone-classify", "--boxes", "/nonexistent.json")
    assert code == 2 and "not found" in r["error"]
