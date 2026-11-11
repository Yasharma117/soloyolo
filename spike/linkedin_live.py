"""Live LinkedIn sync. It grew into spike/live.py, which takes Instagram and X the same way; these are the names
`python -m spike linkedin-token` and older callers use."""
from __future__ import annotations

from .live import MAX_BODY, authorized, token, token_path  # noqa: F401
from .live import parse_linkedin as parse  # noqa: F401
