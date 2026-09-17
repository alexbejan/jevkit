from jevkit import keys


def test_explicit_wins(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "env-key")
    assert keys.resolve("arg-key") == "arg-key"
    assert keys.source("arg-key") == "arg"


def test_env_then_keychain(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "  env-key ")
    assert keys.resolve() == "env-key"
    assert keys.source() == "env"
    monkeypatch.delenv("TYPESAFE_API_KEY")
    monkeypatch.setattr(keys, "from_keychain", lambda service=None: "kc-key")
    assert keys.resolve() == "kc-key"
    assert keys.source() == "keychain"


def test_nothing(monkeypatch):
    monkeypatch.setattr(keys, "from_keychain", lambda service=None: None)
    assert keys.resolve() is None
    assert keys.source() is None
