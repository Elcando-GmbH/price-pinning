"""pricepinning: detect stocks whose price has stopped moving, typically after a cash takeover offer."""

__version__ = "0.1.0"

from .core import DEFAULT_LONG, DEFAULT_SHORT, MAX_RATIO, PinningResult, check, is_pinned, pinning_frame

__all__ = [
    "DEFAULT_LONG",
    "DEFAULT_SHORT",
    "MAX_RATIO",
    "PinningResult",
    "check",
    "is_pinned",
    "pinning_frame",
]
