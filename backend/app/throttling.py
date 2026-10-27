import time

from decouple import config
from django.conf import settings
from django.core.cache import cache
from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle

_PERIODS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


class CostControlRoleThrottle(SimpleRateThrottle):
    """
    Custom throttle to enforce budget-based cost control on metered external dependencies
    (LLM inference, embeddings, and transcription).

    Rather than generic abuse prevention, this enforces separate usage budgets per user role:
      - Admin / Editor: Higher quota (a user's tier is their highest role in any workspace).
      - Viewer: Heavily capped quota to control external token and API costs.
    """
    scope = 'cost_control'

    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            # Fall back to IP for unauthenticated requests, though permissions should block them
            return self.get_ident(request)

        # Unique cache key per user and role
        return f"throttle_{self.scope}_{request.user.role}_{request.user.id}"

    def allow_request(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return True

        role = request.user.role

        # Configure rate limit based on role (overridable via env variables)
        if role == 'admin':
            self.rate = config("THROTTLE_RATE_ADMIN", default="60/min")
        elif role == 'editor':
            self.rate = config("THROTTLE_RATE_EDITOR", default="60/min")
        else:  # viewer
            self.rate = config("THROTTLE_RATE_VIEWER", default="10/min")

        self.num_requests, self.duration = self.parse_rate(self.rate)
        return super().allow_request(request, view)


class AuthRateThrottle(AnonRateThrottle):
    """Per-IP limit on register/login to slow credential stuffing and signup spam."""
    scope = "auth"


def workspace_retry_after(workspace_id: int) -> int | None:
    """
    Count one LLM-backed query against the workspace's shared allowance
    (WORKSPACE_QUERY_RATE, e.g. "120/min"). Returns None if it fits, or the seconds
    until the window resets.

    The per-user throttle above cannot stop a noisy neighbour: a team of twenty,
    each under their own limit, can still use all the LLM capacity every other
    workspace shares. This caps the team.

    Called from the view after the workspace has been authorised, not used as a DRF
    throttle class. Throttle classes run before the view, while workspace_id is
    still whatever the client sent, so anyone could spend another tenant's
    allowance, and lock that tenant out, just by naming its id.
    """
    rate = settings.WORKSPACE_QUERY_RATE
    if not rate:
        return None
    count, unit = rate.split("/")
    limit, period = int(count), _PERIODS[unit[0]]
    now = time.time()
    key = f"wsrate:{workspace_id}:{int(now // period)}"
    cache.add(key, 0, timeout=period + 1)
    try:
        used = cache.incr(key)
    except ValueError:  # the window expired between add() and incr()
        cache.set(key, 1, timeout=period + 1)
        used = 1
    if used > limit:
        return max(1, int(period - now % period))
    return None
