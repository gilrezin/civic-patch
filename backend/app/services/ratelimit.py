"""Tiny in-memory per-user rate limiter for generation requests."""

from __future__ import annotations

import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, limit: int, window_s: float = 600.0) -> None:
        self.limit = limit
        self.window_s = window_s
        self._events: dict[int, deque[float]] = defaultdict(deque)

    def check(self, user_id: int) -> float | None:
        """Return None if allowed (and record the event) or seconds until the next slot."""
        now = time.monotonic()
        q = self._events[user_id]
        while q and now - q[0] > self.window_s:
            q.popleft()
        if len(q) >= self.limit:
            return max(1.0, self.window_s - (now - q[0]))
        q.append(now)
        return None

    def refund(self, user_id: int) -> None:
        q = self._events.get(user_id)
        if q:
            q.pop()
