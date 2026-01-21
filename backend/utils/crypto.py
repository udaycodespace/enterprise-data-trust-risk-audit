"""
ED-BASE Cryptographic Utilities
Secure hashing, HMAC signing, and token handling.

WHY centralized crypto: Consistent algorithms, easy auditing,
single point of security review.
"""

import hashlib
import hmac
import secrets
import base64
import json
from typing import Optional, Any
from datetime import datetime, timezone


def sha256_hash(data: str | bytes) -> str:
    """
    Compute SHA-256 hash of input data.
    
    WHY SHA-256: Industry standard, collision-resistant,
    used for token hashing per PRD §6.
    
    Args:
        data: String or bytes to hash
        
    Returns:
        Lowercase hex digest (64 characters)
    """
    if isinstance(data, str):
        data = data.encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def hmac_sign(data: str | bytes, secret: str) -> str:
    """
    Create HMAC-SHA256 signature for data integrity.
    
    WHY HMAC: Cryptographic integrity verification.
    Used for audit log signing per PRD §13 (Invariant #5).
    
    Args:
        data: Data to sign
        secret: HMAC secret key
        
    Returns:
        Lowercase hex signature (64 characters)
    """
    if isinstance(data, str):
        data = data.encode('utf-8')
    if isinstance(secret, str):
        secret = secret.encode('utf-8')
    
    return hmac.new(
        key=secret,
        msg=data,
        digestmod=hashlib.sha256
    ).hexdigest()


def hmac_verify(data: str | bytes, signature: str, secret: str) -> bool:
    """
    Verify HMAC signature using constant-time comparison.
    
    WHY constant-time: Prevents timing attacks that could
    leak signature information byte-by-byte.
    
    Args:
        data: Original data
        signature: Signature to verify
        secret: HMAC secret key
        
    Returns:
        True if signature is valid
    """
    expected = hmac_sign(data, secret)
    # WHY compare_digest: Constant-time comparison prevents timing attacks
    return hmac.compare_digest(expected, signature)


def generate_token_hash(jwt_token: str) -> str:
    """
    Generate hash of JWT token for session storage.
    
    WHY hash tokens: If database is compromised, attacker
    cannot use stolen hashes to authenticate. They would
    need the original JWT.
    
    Args:
        jwt_token: Raw JWT access token
        
    Returns:
        SHA-256 hash for storage in sessions table
    """
    return sha256_hash(jwt_token)


def generate_request_hash(body: bytes, headers: dict | None = None) -> str:
    """
    Generate hash of request for idempotency verification.
    
    WHY include headers: Some operations may be header-dependent.
    Default to body-only for simplicity.
    
    Args:
        body: Request body bytes
        headers: Optional headers to include in hash
        
    Returns:
        SHA-256 hash of request
    """
    if headers:
        # Include specific headers in hash
        header_data = json.dumps(headers, sort_keys=True).encode('utf-8')
        combined = body + b'|' + header_data
        return sha256_hash(combined)
    return sha256_hash(body)


def generate_idempotency_key() -> str:
    """
    Generate a secure random idempotency key.
    
    WHY 32 bytes: 256 bits of entropy, effectively unguessable.
    
    Returns:
        URL-safe base64 encoded random string
    """
    return secrets.token_urlsafe(32)


def generate_request_id() -> str:
    """
    Generate unique request ID for tracking and debugging.
    
    WHY include timestamp: Enables rough time ordering without
    querying, useful for log correlation.
    
    Returns:
        Unique request identifier
    """
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    random_part = secrets.token_hex(8)
    return f"req_{timestamp}_{random_part}"


def sign_pagination_cursor(cursor_data: dict, secret: str) -> str:
    """
    Create signed pagination cursor to prevent forgery.
    
    WHY signed cursors: Prevents attackers from forging cursors
    to access unauthorized data (PRD §15).
    
    Args:
        cursor_data: Cursor payload (offset, filters, etc.)
        secret: HMAC secret
        
    Returns:
        Base64 encoded signed cursor
    """
    # Serialize cursor data
    payload = json.dumps(cursor_data, sort_keys=True, default=str)
    
    # Create signature
    signature = hmac_sign(payload, secret)
    
    # Combine payload and signature
    combined = {
        'data': cursor_data,
        'sig': signature
    }
    
    # Base64 encode for URL safety
    return base64.urlsafe_b64encode(
        json.dumps(combined).encode('utf-8')
    ).decode('utf-8')


def verify_pagination_cursor(cursor: str, secret: str) -> Optional[dict]:
    """
    Verify and decode signed pagination cursor.
    
    Args:
        cursor: Signed cursor string
        secret: HMAC secret
        
    Returns:
        Cursor data if valid, None if tampered or invalid
    """
    try:
        # Decode base64
        decoded = base64.urlsafe_b64decode(cursor.encode('utf-8'))
        combined = json.loads(decoded)
        
        # Extract components
        cursor_data = combined.get('data')
        signature = combined.get('sig')
        
        if not cursor_data or not signature:
            return None
        
        # Verify signature
        payload = json.dumps(cursor_data, sort_keys=True, default=str)
        if not hmac_verify(payload, signature, secret):
            return None
        
        return cursor_data
        
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


def sign_audit_entry(entry_data: dict, secret: str) -> str:
    """
    Create HMAC signature for audit log entry.
    
    WHY audit signing: Enables tamper detection for Invariant #5.
    If log is modified, signature verification will fail.
    
    Args:
        entry_data: Audit log entry fields
        secret: HMAC secret for audit logs
        
    Returns:
        64-character hex signature
    """
    # Create canonical representation of entry
    # WHY sort_keys: Deterministic serialization
    payload = json.dumps(entry_data, sort_keys=True, default=str)
    return hmac_sign(payload, secret)


def verify_audit_entry(entry_data: dict, signature: str, secret: str) -> bool:
    """
    Verify audit log entry integrity.
    
    Args:
        entry_data: Audit log entry fields
        signature: Stored signature
        secret: HMAC secret
        
    Returns:
        True if entry is unmodified
    """
    expected = sign_audit_entry(entry_data, secret)
    return hmac.compare_digest(expected, signature)


def constant_time_compare(a: str, b: str) -> bool:
    """
    Constant-time string comparison.
    
    WHY: Prevents timing attacks in security-sensitive comparisons.
    
    Args:
        a: First string
        b: Second string
        
    Returns:
        True if strings are equal
    """
    return hmac.compare_digest(a.encode('utf-8'), b.encode('utf-8'))
