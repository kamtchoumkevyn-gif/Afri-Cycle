"""
BuyerPrices model — matches the BuyerPrices class in the diagram:
    materialCategoryId, buyerId, pricePerKilo, updatedAt
    +setPrice(materialCategoryId, newPrice): boolean
"""
from datetime import datetime
from utils.storage import read_all, write_all, next_id

COLLECTION = "buyer_prices"


def set_price(buyer_id: str, material_category_id: str, new_price: float) -> dict | None:
    """
    Creates or updates the price a buyer offers for a material category.
    Returns the updated/created record, or None if new_price is invalid.
    """
    if new_price is None or new_price < 0:
        return None

    records = read_all(COLLECTION)
    existing = next(
        (r for r in records
         if r["buyerId"] == buyer_id and r["materialCategoryId"] == material_category_id),
        None
    )

    if existing:
        existing["pricePerKilo"] = new_price
        existing["updatedAt"] = datetime.utcnow().isoformat()
        write_all(COLLECTION, records)
        return existing

    record = {
        "id": next_id(records),
        "buyerId": buyer_id,
        "materialCategoryId": material_category_id,
        "pricePerKilo": new_price,
        "updatedAt": datetime.utcnow().isoformat(),
    }
    records.append(record)
    write_all(COLLECTION, records)
    return record


def get_price(buyer_id: str, material_category_id: str) -> dict | None:
    records = read_all(COLLECTION)
    return next(
        (r for r in records
         if r["buyerId"] == buyer_id and r["materialCategoryId"] == material_category_id),
        None
    )


def get_prices_for_buyer(buyer_id: str) -> list:
    records = read_all(COLLECTION)
    return [r for r in records if r["buyerId"] == buyer_id]


def get_prices_for_material(material_category_id: str) -> list:
    """Used by seller_routes.py to sort buyers by price for a given material."""
    records = read_all(COLLECTION)
    prices = [r for r in records if r["materialCategoryId"] == material_category_id]
    return sorted(prices, key=lambda r: r["pricePerKilo"], reverse=True)