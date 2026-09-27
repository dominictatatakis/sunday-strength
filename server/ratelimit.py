"""A small in-process rate limiter. Stdlib only, in keeping with the rest.

Deliberately not backed by Redis or the database. This runs in one Uvicorn
process on a single Render instance, so a dict is the honest fit; adding a
dependency and a network round-trip to protect a login form would be worse
engineering, not better security.

Two consequences to know about:

- State is per process and lost on restart. An attacker who could force
  restarts could reset the counters — but a restart takes far longer than the
  window, so it buys them nothing.
- If this ever runs multiple workers, each keeps its own counters and the
  effective limit multiplies by the worker count. Move to a shared store then,
  not before.
"""

from __future__ import annotations

import threading
import time

_hits: dict[str, list[float]] = {}
_lock = threading.Lock()
_last_sweep = 0.0


def _sweep(now: float, horizon: float = 3600.0) -> None:
    """Drop keys nobody has touched in an hour, so the dict cannot grow
    without bound on a long-running process."""
    global _last_sweep
    if now - _last_sweep < 300:
        return
    _last_sweep = now
    for key in [k for k, v in _hits.items() if not v or now - v[-1] > horizon]:
        _hits.pop(key, None)


def hit(key: str, limit: int, window: int) -> bool:
    """Record an attempt. True if it is allowed, False if over the limit.

    Sliding window: only attempts inside `window` seconds count, so a blocked
    caller recovers gradually rather than waiting for a fixed reset.
    """
    now = time.time()
    with _lock:
        _sweep(now)
        recent = [t for t in _hits.get(key, []) if now - t < window]
        recent.append(now)
        _hits[key] = recent
        return len(recent) <= limit


def clear() -> None:
    """Test hook — the limiter is process-global, so tests must reset it."""
    with _lock:
        _hits.clear()
