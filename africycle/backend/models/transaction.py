"""
Transaction model — matches the Transaction class in the diagram:
    buyerId, sellerPhoneNumber, materialCategoryId, weightKg, pricePerKilo,
    photoUrl, latitude, longitude, confirmedBySeller, timestamp
    +logTransaction(buyerId, sellerPhoneNumber, materialCategoryId, weightKg,
                     pricePerKilo, photoUrl): boolean
"""
from datetime import datetime
from utils.storage import read_all, write_all, next_id

COLLECTION = "transactions"


def log_transaction(buyer_id: str, seller_phone_number: str, material_category_id: str,
                     weight_kg: float, price_per_kilo: float, photo_url: str = "",
                     latitude: float = None, longitude: float = None) -> dict | None:
    """
    Records a completed (or pending-confirmation) material handover.
    Returns None if weight or price are missing/invalid.
    """
    if weight_kg is None or weight_kg <= 0:
        return None
    if price_per_kilo is None or price_per_kilo < 0:
        return None

    records = read_all(COLLECTION)
    record = {
        "id": next_id(records),
        "buyerId": buyer_id,
        "sellerPhoneNumber": seller_phone_number,
        "materialCategoryId": material_category_id,
        "weightKg": weight_kg,
        "pricePerKilo": price_per_kilo,
        "photoUrl": photo_url,
        "latitude": latitude,
        "longitude": longitude,
        "confirmedBySeller": False,
        "timestamp": datetime.utcnow().isoformat(),
    }
    records.append(record)
    write_all(COLLECTION, records)
    return record


def get_transaction_by_id(transaction_id: int) -> dict | None:
    records = read_all(COLLECTION)
    return next((r for r in records if r["id"] == transaction_id), None)


def get_transactions_for_buyer(buyer_id: str) -> list:
    records = read_all(COLLECTION)
    txns = [r for r in records if r["buyerId"] == buyer_id]
    return sorted(txns, key=lambda r: r["timestamp"], reverse=True)


def get_transactions_for_seller(seller_phone_number: str) -> list:
    records = read_all(COLLECTION)
    txns = [r for r in records if r["sellerPhoneNumber"] == seller_phone_number]
    return sorted(txns, key=lambda r: r["timestamp"], reverse=True)


def confirm_transaction(transaction_id: int) -> bool:
    """Called when the seller confirms the transaction actually took place."""
    records = read_all(COLLECTION)
    for r in records:
        if r["id"] == transaction_id:
            r["confirmedBySeller"] = True
            write_all(COLLECTION, records)
            return True
    return False


def total_weight_for_material(material_category_id: str, confirmed_only: bool = True) -> float:
    """Simple aggregate, handy for admin stats later."""
    records = read_all(COLLECTION)
    matching = [
        r for r in records
        if r["materialCategoryId"] == material_category_id
        and (not confirmed_only or r["confirmedBySeller"])
    ]
    return sum(r["weightKg"] for r in matching)