"""STMatch router entry point using the shared public matcher adapter."""

from .public_match_adapter import run_public_match

ROUTER = "STMatch"


def run_stmatch(*args, **kwargs):
    kwargs["matcher"] = "STMatch"
    return run_public_match(*args, **kwargs)
