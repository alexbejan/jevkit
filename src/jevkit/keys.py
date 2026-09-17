"""Where the TypeSafe API key comes from.

Order: explicit argument, then the TYPESAFE_API_KEY environment variable, then
the macOS Keychain item with service TYPESAFE_API_KEY. The key is never
written to disk by this package, never logged, and never put in a command
argument (the Keychain read uses `security`, which returns it on stdout).

Store it once with:
    security add-generic-password -a "$USER" -s TYPESAFE_API_KEY -w '<key>' -U
"""
import os
import shutil
import subprocess

ENV = "TYPESAFE_API_KEY"
KEYCHAIN_SERVICE = "TYPESAFE_API_KEY"


def from_keychain(service=KEYCHAIN_SERVICE):
    """The Keychain item's password, or None when absent or not on macOS."""
    if not shutil.which("security"):
        return None
    try:
        r = subprocess.run(["security", "find-generic-password", "-s", service, "-w"],
                           capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    key = r.stdout.strip()
    return key if r.returncode == 0 and key else None


def resolve(explicit=None):
    """The key to use, or None. Empty strings count as unset."""
    if explicit:
        return explicit
    env = os.environ.get(ENV, "").strip()
    if env:
        return env
    return from_keychain()


def source(explicit=None):
    """Which source would supply the key: 'arg' | 'env' | 'keychain' | None."""
    if explicit:
        return "arg"
    if os.environ.get(ENV, "").strip():
        return "env"
    if from_keychain():
        return "keychain"
    return None
