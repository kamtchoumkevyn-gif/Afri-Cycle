from flask import Blueprint, jsonify, request

import directions
from auth_utils import get_user_from_token
from extensions import limiter
from routes.notification_routes import to_number

directions_bp = Blueprint("directions_bp", __name__)


def per_user():
    """Rate-limit by account rather than by address (many people can share one address)."""
    payload = get_user_from_token()
    return f"user-{payload['userId']}" if payload else (request.remote_addr or "anonymous")


def parse_point(text):
    try:
        lat_text, lng_text = str(text).split(",")
    except ValueError:
        return None
    lat, lng = to_number(lat_text, -90, 90), to_number(lng_text, -180, 180)
    return [lat, lng] if lat is not None and lng is not None else None


@directions_bp.route("/directions", methods=["GET"])
@limiter.limit("30 per minute", key_func=per_user)
def get_directions():
    """Road route from ?from=lat,lng to ?to=lat,lng, on foot (default) or by car/motorbike
    (?mode=car), with turn-by-turn instructions."""
    if not get_user_from_token():
        return jsonify({"message": "Unauthorized"}), 401

    start, end = parse_point(request.args.get("from")), parse_point(request.args.get("to"))
    mode = request.args.get("mode", "foot")
    if not start or not end:
        return jsonify({"message": "from and to must be 'latitude,longitude'"}), 400
    if mode not in directions.PROFILES:
        return jsonify({"message": "mode must be foot or car"}), 400
    if directions.straight_km(start, end) > directions.MAX_KM:
        return jsonify({"message": f"Directions are only given for trips under {directions.MAX_KM} km"}), 400

    try:
        route = directions.get_route(start, end, mode, referer=request.url_root)
    except directions.NoRoute:
        return jsonify({"message": "No road route was found between you and the buyer."}), 404
    except directions.RoutingUnavailable:
        return jsonify({"message": "Directions aren't available right now. Try again in a minute."}), 502
    return jsonify(route), 200
