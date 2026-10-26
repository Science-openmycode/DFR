"""FMM router entry point.

The implementation lives in :mod:`public_match_adapter` so FMM and STMatch
share the same audited input/output contract.  This module keeps the named
router entry requested by the experiment layout.
"""

from .public_match_adapter import run_public_match

ROUTER = "FMM"


def run_fmm(*args, **kwargs):
    kwargs["matcher"] = "FMM"
    return run_public_match(*args, **kwargs)
