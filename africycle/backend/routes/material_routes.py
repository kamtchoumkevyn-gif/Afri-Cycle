from flask import Blueprint, jsonify
from auth_utils import get_user_from_token
from models.material_category import get_all_categories

material_bp = Blueprint("material_bp", __name__)


@material_bp.route("/material-categories", methods=["GET"])
def list_categories():
    if not get_user_from_token():
        return jsonify({"message": "Unauthorized"}), 401
    return jsonify({"categories": get_all_categories()}), 200
