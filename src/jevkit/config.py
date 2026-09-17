"""Settings. Environment variables are per-call overrides; defaults are safe.

JEVKIT_MODEL       model id; pinned to a version so tuned thresholds stay valid
JEVKIT_DISABLE=1   every judgement raises JevUnavailable (callers fall back)
JEVKIT_MOCK=1      deterministic offline answers, for tests and CI
JEVKIT_LOG         JSONL call log path ('' disables)
JEVKIT_TIMEOUT     seconds per HTTP operation
"""
import os
from pathlib import Path

MODEL = os.environ.get("JEVKIT_MODEL", "jev-1.13.0")
TIMEOUT = float(os.environ.get("JEVKIT_TIMEOUT", "10"))
DISABLED = os.environ.get("JEVKIT_DISABLE", "") in ("1", "true", "yes")
MOCK = os.environ.get("JEVKIT_MOCK", "") in ("1", "true", "yes")

_state = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "jevkit"
LOG_PATH = os.environ.get("JEVKIT_LOG", str(_state / "calls.jsonl"))

# Confidence gates. Starting points only; retune from the call log on real
# screens. See Judge.gate().
HIGH = float(os.environ.get("JEVKIT_HIGH", "0.80"))
LOW = float(os.environ.get("JEVKIT_LOW", "0.50"))
YES = float(os.environ.get("JEVKIT_YES", "0.50"))   # Noul threshold for "yes"

# Choice accepts at most 255 options; keep one for the reserved no-match.
MAX_CANDIDATES = 200
# Lines of compacted observation sent as state. Jev's accuracy drops with
# irrelevant detail, and the state limit is 32k tokens.
MAX_STATE_LINES = 300
