"""
ED-BASE Health Routes
Health check endpoint per PRD §14.
"""

from flask import Blueprint, jsonify
import structlog

from utils import health_check as db_health_check
from services import get_circuit, CircuitState

logger = structlog.get_logger(__name__)

health_bp = Blueprint('health', __name__)


@health_bp.route('/health', methods=['GET'])
def health():
    """
    Health check endpoint.
    
    Checks:
    - Database connectivity
    - Redis connectivity
    - Circuit breaker states
    
    Returns 200 if healthy, 503 if degraded.
    """
    status = {
        'status': 'healthy',
        'checks': {}
    }
    is_healthy = True
    
    # Check database
    db_status = db_health_check()
    status['checks']['database'] = {
        'healthy': db_status['is_healthy'],
        'latency_ms': db_status['latency_ms']
    }
    if not db_status['is_healthy']:
        is_healthy = False
        status['checks']['database']['error'] = 'Database unreachable'
    
    # Check Redis
    try:
        from middleware.rate_limit import get_redis
        redis_client = get_redis()
        redis_client.ping()
        status['checks']['redis'] = {'healthy': True}
    except Exception as e:
        is_healthy = False
        status['checks']['redis'] = {
            'healthy': False,
            'error': 'Redis unreachable'
        }
    
    # Check circuit breakers
    db_circuit = get_circuit('database')
    if db_circuit.state == CircuitState.OPEN:
        is_healthy = False
        status['checks']['circuit_database'] = {
            'healthy': False,
            'state': 'open'
        }
    
    # Set overall status
    if not is_healthy:
        status['status'] = 'degraded'
        return jsonify(status), 503
    
    return jsonify(status), 200


@health_bp.route('/ready', methods=['GET'])
def ready():
    """
    Readiness probe for orchestrators.
    
    Returns 200 if app is ready to accept traffic.
    """
    return jsonify({'ready': True}), 200


@health_bp.route('/live', methods=['GET'])
def live():
    """
    Liveness probe for orchestrators.
    
    Returns 200 if app process is alive.
    """
    return jsonify({'alive': True}), 200
