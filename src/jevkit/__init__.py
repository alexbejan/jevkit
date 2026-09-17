"""jevkit: TypeSafe Jev as a bounded judgement layer for computer use.

Jev never acts and never invents. Code builds the observation, code builds the
candidate list, Jev returns typed answers with probabilities, code decides.

Public surface:
    Judge            verify / pick / classify / ask, with confidence gating
    JevUnavailable   raised when Jev is disabled, unconfigured or unreachable
    compact          observation compactors (Cua elements, phone OCR) and diffs
"""
from .client import JevUnavailable, Jev, MockJev
from .judge import Judge, gate
from . import compact

__all__ = ["Judge", "Jev", "MockJev", "JevUnavailable", "gate", "compact"]
__version__ = "0.1.0"
