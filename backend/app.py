"""
ED-BASE Flask Application
Application factory with security-first configuration.
"""

import os
import sys
from flask import Flask, g
from flask_cors import CORS
import structlog

from config import get_config, validate_config
from utils import init_connection_pool, generate_request_id
from middleware import register_error_handlers, init_redis
from routes import auth_bp, health_bp, webhooks_bp

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger(__name__)


def create_app() -> Flask:
    """
    Flask application factory.
    
    WHY factory pattern: Enables testing with different configs,
    clean initialization order, and proper cleanup.
    """
    config = get_config()
    
    # Validate configuration
    errors = validate_config(config)
    if errors:
        for error in errors:
            logger.critical("Configuration error", error=error)
        if config.is_production:
            sys.exit(1)
    
    # Create Flask app
    app = Flask(__name__)
    app.config['SECRET_KEY'] = config.secret_key or 'dev-only-secret-key'
    
    # CORS configuration
    CORS(app, origins=config.cors_origins, supports_credentials=True)
    
    # Initialize database pool
    try:
        init_connection_pool(config.database)
        logger.info("Database connection pool initialized")
    except Exception as e:
        logger.error("Failed to initialize database", error=str(e))
        if config.is_production:
            sys.exit(1)
    
    # Initialize Redis
    try:
        init_redis()
        logger.info("Redis initialized")
    except Exception as e:
        logger.warning("Failed to initialize Redis", error=str(e))
    
    # Register error handlers (Invariant #9)
    register_error_handlers(app)
    
    # Request hooks
    @app.before_request
    def before_request():
        """Set up request context."""
        g.request_id = generate_request_id()
    
    @app.after_request
    def after_request(response):
        """Add security and tracking headers."""
        response.headers['X-Request-ID'] = g.get('request_id', 'unknown')
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        return response
    
    # Register blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(webhooks_bp)
    
    logger.info(
        "Application initialized",
        env=config.env,
        debug=config.debug
    )
    
    return app


# Application instance for WSGI servers
app = create_app()


if __name__ == '__main__':
    config = get_config()
    app.run(
        host=config.host,
        port=config.port,
        debug=config.debug
    )
