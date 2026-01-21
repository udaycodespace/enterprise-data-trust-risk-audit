"""
ED-BASE Routes Package
API route blueprints.
"""

from routes.auth import auth_bp
from routes.health import health_bp
from routes.webhooks import webhooks_bp

__all__ = ['auth_bp', 'health_bp', 'webhooks_bp']
