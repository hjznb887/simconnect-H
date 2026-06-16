"""Deprecated — use stress_subscribe.py"""
from __future__ import annotations

import sys
import warnings

warnings.warn(
    "stress_subscribe_weather.py is deprecated; use examples/stress_subscribe.py",
    DeprecationWarning,
    stacklevel=2,
)

from stress_subscribe import main

if __name__ == "__main__":
    sys.exit(main())
