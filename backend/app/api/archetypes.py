"""
Archetype API Routes
CRUD operations for agent personality archetypes
"""

from flask import request, jsonify
from . import archetypes_bp
from ..services.archetypes import ArchetypeManager
from ..utils.logger import get_logger

logger = get_logger('mirofish.api.archetypes')


@archetypes_bp.route('/list', methods=['GET'])
def list_archetypes():
    """List all available archetypes, optionally filtered by category."""
    category = request.args.get('category')
    archetypes = ArchetypeManager.list_archetypes(category=category)
    return jsonify({
        "success": True,
        "data": archetypes,
        "count": len(archetypes)
    })


@archetypes_bp.route('/<key>', methods=['GET'])
def get_archetype(key: str):
    """Get a specific archetype by key."""
    archetype = ArchetypeManager.get_archetype(key)
    if not archetype:
        return jsonify({
            "success": False,
            "error": f"Archetype not found: {key}"
        }), 404

    d = archetype.to_dict()
    d["key"] = key
    return jsonify({
        "success": True,
        "data": d
    })


@archetypes_bp.route('', methods=['POST'])
def create_archetype():
    """Create a new custom archetype."""
    data = request.get_json() or {}

    key = data.pop('key', None)
    if not key:
        return jsonify({
            "success": False,
            "error": "Please provide 'key' (unique identifier for the archetype)"
        }), 400

    required = ['name', 'description', 'personality_traits', 'mbti_pool',
                'age_range', 'speaking_style', 'prompt_modifier']
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({
            "success": False,
            "error": f"Missing required fields: {missing}"
        }), 400

    # Defaults
    data.setdefault('activity_level', 0.5)
    data.setdefault('sentiment_bias', 0.0)
    data.setdefault('stance_tendency', 'neutral')
    data.setdefault('category', 'general')

    try:
        archetype = ArchetypeManager.create_archetype(key, data)
        d = archetype.to_dict()
        d["key"] = key
        return jsonify({
            "success": True,
            "data": d
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400


@archetypes_bp.route('/<key>', methods=['DELETE'])
def delete_archetype(key: str):
    """Delete a custom archetype. Built-in archetypes cannot be deleted."""
    if not ArchetypeManager.delete_archetype(key):
        return jsonify({
            "success": False,
            "error": f"Cannot delete archetype: {key} (built-in or not found)"
        }), 400

    return jsonify({
        "success": True,
        "message": f"Archetype deleted: {key}"
    })
