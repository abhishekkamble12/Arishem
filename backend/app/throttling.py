from rest_framework.throttling import SimpleRateThrottle
from decouple import config

class CostControlRoleThrottle(SimpleRateThrottle):
    """
    Custom throttle to enforce budget-based cost control on metered external dependencies
    (LLM inference, embeddings, and transcription).
    
    Rather than generic abuse prevention, this enforces separate usage budgets per user role:
      - Admin / Editor: Higher quota for operational administration & ingestion.
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
            self.rate = config("THROTTLE_RATE_ADMIN", default="100/min")
        elif role == 'editor':
            self.rate = config("THROTTLE_RATE_EDITOR", default="60/min")
        else:  # viewer
            self.rate = config("THROTTLE_RATE_VIEWER", default="10/min")
            
        self.num_requests, self.duration = self.parse_rate(self.rate)
        return super().allow_request(request, view)
