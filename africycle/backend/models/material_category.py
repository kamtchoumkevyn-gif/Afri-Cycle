"""
MaterialCategory model — matches the MaterialCategory class in the diagram:
    name, description, referencePhotoUrl
"""
from utils.storage import read_all, write_all, next_id

COLLECTION = "material_categories"


def create_category(name: str, description: str = "", reference_photo_url: str = "") -> dict | None:
    if not name or not name.strip():
        return None

    records = read_all(COLLECTION)

    if any(r["name"].lower() == name.strip().lower() for r in records):
        return None  # category already exists

    record = {
        "id": next_id(records),
        "name": name.strip(),
        "description": description,
        "referencePhotoUrl": reference_photo_url,
    }
    records.append(record)
    write_all(COLLECTION, records)
    return record


def get_all_categories() -> list:
    return read_all(COLLECTION)


def get_category_by_id(category_id: int) -> dict | None:
    records = read_all(COLLECTION)
    return next((r for r in records if r["id"] == category_id), None)


def get_category_by_name(name: str) -> dict | None:
    records = read_all(COLLECTION)
    return next((r for r in records if r["name"].lower() == name.lower()), None)


def update_category(category_id: int, description: str = None, reference_photo_url: str = None) -> bool:
    records = read_all(COLLECTION)
    for r in records:
        if r["id"] == category_id:
            if description is not None:
                r["description"] = description
            if reference_photo_url is not None:
                r["referencePhotoUrl"] = reference_photo_url
            write_all(COLLECTION, records)
            return True
    return False


def delete_category(category_id: int) -> bool:
    records = read_all(COLLECTION)
    filtered = [r for r in records if r["id"] != category_id]
    if len(filtered) == len(records):
        return False
    write_all(COLLECTION, filtered)
    return True