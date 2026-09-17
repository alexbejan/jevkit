import json
import os
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _offline(monkeypatch, tmp_path):
    """No network, no real key, no shared log during tests."""
    monkeypatch.setenv("JEVKIT_LOG", str(tmp_path / "calls.jsonl"))
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    import jevkit.config as c
    monkeypatch.setattr(c, "LOG_PATH", str(tmp_path / "calls.jsonl"))
    monkeypatch.setattr(c, "MOCK", False)
    monkeypatch.setattr(c, "DISABLED", False)


@pytest.fixture
def finder():
    return json.loads((FIX / "cua_finder_window.json").read_text())


@pytest.fixture
def settings():
    return json.loads((FIX / "cua_settings_window.json").read_text())


@pytest.fixture
def phone_boxes():
    # Shape of phone-harness ocr(): global points, reading order not guaranteed.
    return [
        {"text": "Settings", "confidence": 0.99, "source": "pixels", "x": 200, "y": 60, "w": 80, "h": 20},
        {"text": "General", "confidence": 0.98, "source": "pixels", "x": 120, "y": 300, "w": 70, "h": 18},
        {"text": "Accessibility", "confidence": 0.97, "source": "pixels", "x": 130, "y": 340, "w": 110, "h": 18},
        {"text": "Privacy & Security", "confidence": 0.5, "source": "pixels", "x": 150, "y": 380, "w": 150, "h": 18},
        {"text": "", "confidence": 0.9, "source": "pixels", "x": 0, "y": 0, "w": 0, "h": 0},
    ]
