"""Mock product catalogue (demo data). Amounts are integer paise. Seeded on startup;
stock is only set on first insert so purchases are not reset by a restart."""
from app.core.database import db

PRODUCTS = [
    {"sku": "SKU-HP-201", "name": "Aurora Wireless Headphones", "category": "Audio", "price": 249900, "stock": 25,
     "description": "Over-ear, 40-hour battery, soft-touch ear cushions."},
    {"sku": "SKU-SP-118", "name": "Pebble Bluetooth Speaker", "category": "Audio", "price": 299900, "stock": 18,
     "description": "Palm-sized speaker with 12 hours of playback."},
    {"sku": "SKU-KB-150", "name": "Compact Mechanical Keyboard", "category": "Desk", "price": 459900, "stock": 12,
     "description": "75% layout, hot-swappable switches, USB-C."},
    {"sku": "SKU-LM-087", "name": "Brass Desk Lamp", "category": "Desk", "price": 129900, "stock": 30,
     "description": "Weighted base, warm light, adjustable arm."},
    {"sku": "SKU-ST-203", "name": "Walnut Laptop Stand", "category": "Desk", "price": 169900, "stock": 20,
     "description": "Folds flat, lifts your screen to eye level."},
    {"sku": "SKU-KT-044", "name": "Copper Electric Kettle 1.5L", "category": "Kitchen", "price": 189900, "stock": 15,
     "description": "Auto shut-off, keeps warm for 30 minutes."},
    {"sku": "SKU-MG-012", "name": "Stoneware Mug Set of 4", "category": "Kitchen", "price": 79900, "stock": 40,
     "description": "Hand-glazed, microwave and dishwasher safe."},
    {"sku": "SKU-CB-072", "name": "Cast Iron Skillet 10 inch", "category": "Kitchen", "price": 139900, "stock": 4,
     "description": "Pre-seasoned and oven safe up to 260°C."},
    {"sku": "SKU-BP-310", "name": "Trailhead Backpack 28L", "category": "Travel", "price": 349900, "stock": 14,
     "description": "Water-resistant, padded laptop sleeve, rain cover."},
    {"sku": "SKU-WB-029", "name": "Steel Water Bottle 750ml", "category": "Travel", "price": 59900, "stock": 60,
     "description": "Double-walled, cold for 24 hours."},
    {"sku": "SKU-NB-105", "name": "Linen Notebook Duo", "category": "Stationery", "price": 34900, "stock": 80,
     "description": "Two A5 notebooks, 120 pages each, lay-flat binding."},
    {"sku": "SKU-PN-061", "name": "Fountain Pen, Matte Green", "category": "Stationery", "price": 89900, "stock": 0,
     "description": "Steel nib, converter included. Back in stock soon."},
]
BY_SKU = {p["sku"]: p for p in PRODUCTS}


async def ensure_seeded(reset_stock: bool = False) -> None:
    for p in PRODUCTS:
        doc = {k: v for k, v in p.items() if k != "sku"}
        stock = doc.pop("stock")
        update = {"$set": doc, "$setOnInsert": {"stock": stock}}
        if reset_stock:
            update = {"$set": {**doc, "stock": stock}}
        await db().products.update_one({"_id": p["sku"]}, update, upsert=True)


def public(p: dict) -> dict:
    return {"sku": p["_id"], "name": p["name"], "description": p["description"], "category": p["category"],
            "price": p["price"], "stock": p["stock"]}


async def list_products() -> list[dict]:
    return [public(p) async for p in db().products.find().sort([("category", 1), ("price", 1)])]
