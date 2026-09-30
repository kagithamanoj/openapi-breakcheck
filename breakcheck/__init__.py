"""Detect breaking changes between two OpenAPI 3.x specifications."""

from breakcheck.diff import BreakingChange, diff_specs, load_spec

__all__ = ["BreakingChange", "diff_specs", "load_spec"]
__version__ = "0.1.0"
