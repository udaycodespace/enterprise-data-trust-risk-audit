"""
ED-BASE Configuration Module
Centralized, environment-based configuration with secure defaults.

WHY environment variables: Secrets never in code. 12-factor app compliance.
WHY dataclass: Type safety and IDE support for configuration.
"""

import os
from dataclasses import dataclass, field
from typing import Optional
from functools import lru_cache


@dataclass(frozen=True)
class DatabaseConfig:
    """Database connection configuration per PRD §14."""
    
    # WHY connection string from env: Never hardcode credentials
    url: str = field(default_factory=lambda: os.environ.get(
        'DATABASE_URL', 
        'postgresql://localhost:5432/edbase'
    ))
    
    # Pool configuration per PRD §14
    # WHY these values: Balance between resource usage and availability
    pool_min: int = 5      # Minimum connections always ready
    pool_max: int = 20     # Maximum concurrent connections
    pool_idle_timeout: int = 600    # 10 minutes - close idle connections
    pool_max_lifetime: int = 3600   # 1 hour - prevent stale connections
    
    # Query timeouts per PRD §14
    default_timeout: int = 30       # 30s for normal queries
    payment_timeout: int = 10       # 10s for payment operations (fail fast)
    
    # WHY SSL required: Network is hostile (PRD §3)
    ssl_required: bool = True


@dataclass(frozen=True)
class RedisConfig:
    """Redis configuration for rate limiting per PRD §8."""
    
    url: str = field(default_factory=lambda: os.environ.get(
        'REDIS_URL',
        'redis://localhost:6379/0'
    ))
    
    # Connection pool settings
    max_connections: int = 50
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0


@dataclass(frozen=True)
class RateLimitConfig:
    """Rate limiting thresholds per PRD §8."""
    
    # Per-IP limits
    ip_requests_per_minute: int = 100
    
    # Per-User limits
    user_requests_per_minute: int = 50
    
    # Per-Endpoint limits
    login_requests_per_minute: int = 10
    payment_requests_per_minute: int = 5
    
    # Sliding window size in seconds
    window_size: int = 60
    
    # WHY fingerprint components: Don't trust X-Forwarded-For alone (PRD §8)
    use_user_agent_fingerprint: bool = True
    use_custom_fingerprint: bool = True


@dataclass(frozen=True)
class AuthConfig:
    """Authentication configuration per PRD §6."""
    
    # Supabase credentials
    supabase_url: str = field(default_factory=lambda: os.environ.get(
        'SUPABASE_URL', ''
    ))
    supabase_anon_key: str = field(default_factory=lambda: os.environ.get(
        'SUPABASE_ANON_KEY', ''
    ))
    supabase_service_role_key: str = field(default_factory=lambda: os.environ.get(
        'SUPABASE_SERVICE_ROLE_KEY', ''
    ))
    
    # JWT settings
    jwt_secret: str = field(default_factory=lambda: os.environ.get(
        'JWT_SECRET', ''
    ))
    jwt_algorithm: str = 'HS256'
    access_token_expire_minutes: int = 15  # Short-lived per PRD §6
    refresh_token_expire_days: int = 7
    
    # Account lockout settings
    max_failed_attempts: int = 5
    lockout_duration_minutes: int = 15
    
    # WHY clock skew tolerance: Distributed systems have clock drift (PRD §11)
    clock_skew_tolerance_seconds: int = 300  # ±5 minutes


@dataclass(frozen=True)
class AuditConfig:
    """Audit logging configuration per PRD §13."""
    
    # HMAC key for signing audit logs (Invariant #5)
    hmac_secret: str = field(default_factory=lambda: os.environ.get(
        'AUDIT_HMAC_SECRET', ''
    ))
    
    # Retention per PRD §13
    hot_retention_days: int = 90
    cold_retention_years: int = 7


@dataclass(frozen=True)
class CircuitBreakerConfig:
    """Circuit breaker configuration per PRD §14."""
    
    # WHY 5 failures: Balance between sensitivity and noise tolerance
    failure_threshold: int = 5
    
    # WHY 30s reset: Give service time to recover
    reset_timeout_seconds: int = 30
    
    # WHY half-open: Test if service recovered before fully closing
    half_open_max_calls: int = 1


@dataclass(frozen=True)
class PaymentConfig:
    """Payment configuration per PRD §11."""
    
    stripe_api_key: str = field(default_factory=lambda: os.environ.get(
        'STRIPE_API_KEY', ''
    ))
    stripe_webhook_secret: str = field(default_factory=lambda: os.environ.get(
        'STRIPE_WEBHOOK_SECRET', ''
    ))
    
    # WHY clock skew tolerance: Prevent webhook replay attacks while
    # allowing for network delays (PRD §11)
    webhook_clock_tolerance_seconds: int = 300  # ±5 minutes


@dataclass(frozen=True)
class AppConfig:
    """Main application configuration."""
    
    # Environment
    env: str = field(default_factory=lambda: os.environ.get('FLASK_ENV', 'production'))
    debug: bool = field(default_factory=lambda: os.environ.get('FLASK_DEBUG', 'false').lower() == 'true')
    
    # WHY secret key from env: Never hardcode secrets
    secret_key: str = field(default_factory=lambda: os.environ.get(
        'FLASK_SECRET_KEY', ''
    ))
    
    # Server settings
    host: str = '0.0.0.0'
    port: int = 5000
    
    # CORS settings
    cors_origins: list = field(default_factory=lambda: os.environ.get(
        'CORS_ORIGINS', 'http://localhost:3000'
    ).split(','))
    
    # WHY strict: Security > convenience (prompt rules)
    # These should NEVER be True in production
    @property
    def is_production(self) -> bool:
        return self.env == 'production'
    
    # Nested configs
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    audit: AuditConfig = field(default_factory=AuditConfig)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    payment: PaymentConfig = field(default_factory=PaymentConfig)


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    """
    Get application configuration singleton.
    
    WHY cached: Configuration should be immutable after startup.
    Reloading config mid-request could cause inconsistencies.
    """
    return AppConfig()


def validate_config(config: AppConfig) -> list[str]:
    """
    Validate configuration completeness.
    Returns list of validation errors.
    
    WHY validation: Fail fast on startup if misconfigured.
    Better to crash at startup than fail silently in production.
    """
    errors = []
    
    if config.is_production:
        # Critical secrets must be set in production
        if not config.secret_key:
            errors.append("FLASK_SECRET_KEY is required in production")
        if not config.auth.supabase_url:
            errors.append("SUPABASE_URL is required in production")
        if not config.auth.supabase_service_role_key:
            errors.append("SUPABASE_SERVICE_ROLE_KEY is required in production")
        if not config.auth.jwt_secret:
            errors.append("JWT_SECRET is required in production")
        if not config.audit.hmac_secret:
            errors.append("AUDIT_HMAC_SECRET is required in production")
        if not config.payment.stripe_webhook_secret:
            errors.append("STRIPE_WEBHOOK_SECRET is required in production")
        
        # Security settings validation
        if config.debug:
            errors.append("FLASK_DEBUG must be false in production")
    
    return errors
