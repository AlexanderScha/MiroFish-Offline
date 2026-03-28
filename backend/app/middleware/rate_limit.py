"""
Simple In-Memory Rate Limiter

Tracks requests per IP using a sliding window approach.
No external dependencies required.
"""

import time
import threading
from flask import request, jsonify
from ..utils.logger import get_logger

# Lock for thread-safe access to the request tracker
_lock = threading.Lock()

# Dict of { ip: [timestamp, timestamp, ...] }
_request_log = {}

# --- Configuration ---
# General limit: 200 requests per 60 seconds
GENERAL_LIMIT = 200
GENERAL_WINDOW = 60  # seconds

# Strict limit for LLM-heavy / upload endpoints: 10 requests per 60 seconds
STRICT_LIMIT = 10
STRICT_WINDOW = 60  # seconds

# Paths that get the stricter rate limit (matched as prefixes)
STRICT_PATHS = (
    '/api/graph/ontology/generate',
    '/api/graph/build',
    '/api/report/generate',
    '/api/report/chat',
    '/api/simulation/generate-profiles',
    '/api/simulation/interview',
)


def _cleanup_old_entries(entries, window):
    """Remove timestamps older than the window."""
    cutoff = time.time() - window
    # Find the first index that is within the window
    i = 0
    while i < len(entries) and entries[i] < cutoff:
        i += 1
    return entries[i:]


def _is_strict_path(path):
    """Check if the request path matches a strict-rate-limit endpoint."""
    for prefix in STRICT_PATHS:
        if path.startswith(prefix):
            return True
    return False


def check_rate_limit():
    """before_request handler that enforces per-IP rate limits on /api/* routes.

    Returns None to allow the request, or a 429 JSON response to reject it.
    """
    # Only rate-limit API routes
    if not request.path.startswith('/api/'):
        return None

    ip = request.remote_addr or '127.0.0.1'
    now = time.time()

    # Determine which limit applies
    strict = _is_strict_path(request.path)
    limit = STRICT_LIMIT if strict else GENERAL_LIMIT
    window = STRICT_WINDOW if strict else GENERAL_WINDOW

    # Use a composite key so general and strict limits are tracked independently
    key = f"{ip}:strict" if strict else f"{ip}:general"

    with _lock:
        entries = _request_log.get(key, [])
        entries = _cleanup_old_entries(entries, window)

        if len(entries) >= limit:
            _request_log[key] = entries
            logger = get_logger('mirofish.ratelimit')
            logger.warning("Rate limit exceeded for %s on %s (%d/%d in %ds)",
                           ip, request.path, len(entries), limit, window)
            return jsonify({
                "success": False,
                "error": f"Rate limit exceeded. Max {limit} requests per {window}s for this endpoint."
            }), 429

        entries.append(now)
        _request_log[key] = entries

    return None
