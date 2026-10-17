"""Receipts: a recorded purchase with photos of the material.

The buyer who recorded the purchase adds the photos (up to models.receipt.MAX_PHOTOS)
and can remove them. Both sides of the sale see the receipt: the buyer, the seller,
the parent or guardian supervising an under-18 seller, and admins.
"""
import base64

from flask import Blueprint, Response, jsonify, request

from auth_utils import get_user_from_token
from models import receipt as receipts
from models.user import get_user_by_id
from routes.buyer_routes import decode_photo
from i18n import _

receipt_bp = Blueprint("receipt_bp", __name__)


def may_see(payload, receipt):
    """Whether this logged-in user is one of the people a receipt is for."""
    user_id = payload["userId"]
    if user_id in (receipt["buyerId"], receipt["sellerId"]) or (payload.get("role") == "admin" and payload.get("twoStep")):
        return True
    seller = get_user_by_id(receipt["sellerId"])
    return bool(seller and seller.get("isMinor") and seller.get("guardianStatus") == "approved"
                and seller.get("guardianId") == user_id)


def readable_receipt(transaction_id):
    """(payload, receipt) for a receipt this user may see, else (None, error response)."""
    payload = get_user_from_token()
    if not payload:
        return None, (jsonify({"message": _("Unauthorized")}), 401)
    receipt = receipts.get_receipt(transaction_id)
    # Someone else's receipt answers like a missing one: ids say nothing about other sales
    if not receipt or not may_see(payload, receipt):
        return None, (jsonify({"message": _("Receipt not found")}), 404)
    return payload, receipt


def own_receipt(transaction_id):
    """The receipt if the logged-in buyer recorded it (only they change its photos)."""
    payload, receipt = readable_receipt(transaction_id)
    if payload is None:
        return None, receipt
    if receipt["buyerId"] != payload["userId"] or payload.get("role") not in ("buyer", "both"):
        return None, (jsonify({"message": _("Only the buyer who recorded this purchase can change its photos")}), 403)
    return receipt, None


@receipt_bp.route("/receipts/<int:transaction_id>", methods=["GET"])
def show_receipt(transaction_id):
    payload, receipt = readable_receipt(transaction_id)
    if payload is None:
        return receipt
    receipt["canAddPhotos"] = (receipt["buyerId"] == payload["userId"]
                               and payload.get("role") in ("buyer", "both"))
    receipt["maxPhotos"] = receipts.MAX_PHOTOS
    return jsonify({"receipt": receipt}), 200


@receipt_bp.route("/receipts/<int:transaction_id>/photos", methods=["POST"])
def add_receipt_photo(transaction_id):
    receipt, error = own_receipt(transaction_id)
    if error:
        return error
    if len(receipt["photoIds"]) >= receipts.MAX_PHOTOS:
        return jsonify({"message": _("A receipt can have {count} photos at most", count=receipts.MAX_PHOTOS)}), 400

    mime_type, raw = decode_photo((request.get_json(silent=True) or {}).get("photo"))
    if mime_type is None:
        return jsonify({"message": raw}), 400
    photo_id = receipts.add_photo(transaction_id, mime_type, base64.b64encode(raw).decode("ascii"))
    return jsonify({"message": _("Photo saved"), "photoId": photo_id}), 201


@receipt_bp.route("/receipts/<int:transaction_id>/photos/<int:photo_id>", methods=["DELETE"])
def remove_receipt_photo(transaction_id, photo_id):
    receipt, error = own_receipt(transaction_id)
    if error:
        return error
    if not receipts.delete_photo(transaction_id, photo_id):
        return jsonify({"message": _("Photo not found")}), 404
    return jsonify({"message": _("Photo removed")}), 200


@receipt_bp.route("/receipt-photos/<int:photo_id>", methods=["GET"])
def receipt_photo(photo_id):
    """A receipt photo, for the people who may see that receipt."""
    payload = get_user_from_token()
    if not payload:
        return jsonify({"message": _("Unauthorized")}), 401
    photo = receipts.get_photo(photo_id)
    receipt = receipts.get_receipt(photo["transactionId"]) if photo else None
    if not receipt or not may_see(payload, receipt):
        return jsonify({"message": _("Photo not found")}), 404
    response = Response(base64.b64decode(photo["imageData"]), mimetype=photo["mimeType"])
    response.headers["Cache-Control"] = "private, max-age=86400"  # photos never change; new ones get new ids
    return response


@receipt_bp.route("/seller/sales", methods=["GET"])
def seller_sales():
    """The seller's receipts: purchases buyers recorded with them."""
    payload = get_user_from_token()
    if not payload or payload.get("role") not in ("seller", "both"):
        return jsonify({"message": _("Unauthorized")}), 401
    return jsonify({"sales": receipts.sales_of(payload["userId"])}), 200
