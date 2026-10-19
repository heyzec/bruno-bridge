"""Constants and the error type shared across bruno_bridge."""

import re

DEFAULT_ENV = "test"
DEFAULT_TIMEOUT = 30.0

METHODS = ("get", "post", "put", "patch", "delete", "head", "options")
VAR_PATTERN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


class BruError(Exception):
    """A request cannot be read or resolved."""
