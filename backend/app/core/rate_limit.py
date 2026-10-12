"""In-process sliding-window rate limiter.

Adequate for a single-process prototype. For multi-worker or multi-node
deployment, swap `_WINDOWS` for Redis - `_consume` is the only function that
touches the store.

Implementation note: the dependency is a closure, not a callable class
instance. FastAPI resolves a dependency's annotations through its
`__globals__`, which a class instance does not have; combined with
`from __future__ import annotations` that would leave `request: Request`
unresolved and FastAPI would treat it as a request-body field.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import HTTPException, Request, status

from ..config import get_settings

settings = get_settings()

_WINDOW_SECONDS = 60.0
_WINDOWS: dict[str, deque] = defaultdict(deque)
_LOCK = threading.Lock()
#: Prevents unbounded growth from one-off keys.
_MAX_TRACKED_KEYS = 20_000


def _client_key(request: Request, bucket: str) -> str:
    # Prefer the authenticated subject so one NAT'd village does not share a bucket.
    subject = getattr(request.state, "user_id", None)
    if subject:
        return f"{bucket}:user:{subject}"
    client = request.client.host if request.client else "unknown"
    return f"{bucket}:ip:{client}"


def _consume(key: str, limit: int) -> None:
    now = time.monotonic()
    with _LOCK:
        if len(_WINDOWS) > _MAX_TRACKED_KEYS:
            _WINDOWS.clear()
        window = _WINDOWS[key]
        while window and now - window[0] > _WINDOW_SECONDS:
            window.popleft()
        if len(window) >= limit:
            retry_after = max(1, int(_WINDOW_SECONDS - (now - window[0])))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many attempts from this device. Please wait {retry_after} seconds and try again.",
                headers={"Retry-After": str(retry_after)},
            )
        window.append(now)


def rate_limiter(bucket: str, limit_per_minute: int | None = None) -> Callable[[Request], None]:
    """Build a FastAPI dependency limiting `bucket` to N requests per minute."""
    limit = limit_per_minute or settings.rate_limit_default_per_minute

    def dependency(request: Request) -> None:
        if not settings.rate_limit_enabled:
            return
        _consume(_client_key(request, bucket), limit)

    return dependency


def reset_rate_limits() -> None:
    """Test helper."""
    with _LOCK:
        _WINDOWS.clear()


auth_rate_limit = rate_limiter("auth", settings.rate_limit_auth_per_minute)
register_rate_limit = rate_limiter("register", settings.rate_limit_register_per_minute)
conversation_rate_limit = rate_limiter("conversation", settings.rate_limit_conversation_per_minute)
default_rate_limit = rate_limiter("default", settings.rate_limit_default_per_minute)
