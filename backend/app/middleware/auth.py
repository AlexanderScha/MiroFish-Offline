"""
API Key Authentication Middleware

If MIROFISH_API_KEY env var is set, all /api/* requests must include
a matching X-API-Key header. If the env var is empty or unset,
authentication is skipped (open access for local development).
"""

import os
from flask import request, jsonify
from ..utils.logger import get_logger


def check_api_key():
    """before_request handler that enforces API key authentication on /api/* routes.

    Returns None to allow the request through, or a 401 JSON response to block it.
    """
    # Only apply to /api/* routes
    if not request.path.startswith('/api/'):
        return None

    api_key = os.environ.get('MIROFISH_API_KEY', '').strip()

    # If no API key configured, skip authentication (open local access)
    if not api_key:
        return None

    # Check the X-API-Key header
    provided_key = request.headers.get('X-API-Key', '').strip()
    if provided_key != api_key:
        logger = get_logger('mirofish.auth')
        logger.warning("Unauthorized API request from %s to %s", request.remote_addr, request.path)
        return jsonify({"success": False, "error": "Unauthorized - invalid or missing API key"}), 401

    return None
