"""Cross-provider helpers shared by the adapters and the judge: refusal heuristics and
key-safe secret scrubbing. Kept provider-agnostic so OpenAI and Google behave the same.
"""

from __future__ import annotations

import re

#: Conservative, first-person refusal/decline markers. Refusal is a per-run 0/1 signal
#: that goes through the distributional test, so an occasional miss washes out — only a
#: shift in the refusal *rate* is ever flagged. Kept tight to protect the FP north-star.
REFUSAL_MARKERS: tuple[str, ...] = (
    "i can't",
    "i cannot",
    "i can not",
    "i'm not able",
    "i am not able",
    "i'm unable",
    "i am unable",
    "i won't",
    "i will not",
    "i'm sorry, but i can",
)

#: Key-shaped tokens to redact from ANY text before it is shown or logged. Covers OpenAI
#: keys (``sk-``/``sk-proj-``), Google credentials in their several prefixes (``AIza...``
#: API keys, ``ya29.`` / ``AQ.`` OAuth-style tokens), and raw ``Bearer`` headers.
_SECRET_RE = re.compile(
    r"sk-[A-Za-z0-9_\-]{4,}"
    r"|AIza[0-9A-Za-z_\-]{10,}"
    r"|ya29\.[A-Za-z0-9_.\-]{10,}"
    r"|AQ\.[A-Za-z0-9_.\-]{10,}"
    r"|Bearer\s+\S+",
    re.IGNORECASE,
)


def looks_like_refusal(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in REFUSAL_MARKERS)


def scrub_secrets(text: str) -> str:
    """Redact key-shaped tokens so a secret can never reach the terminal or a log."""
    return _SECRET_RE.sub("[redacted]", text or "")
