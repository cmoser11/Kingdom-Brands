"""
csv_reader.py
Reads products/products.csv and returns a list of Product objects,
each containing its variants.
"""

import csv
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Variant:
    option1_name:  str
    option1_value: str
    option2_name:  str
    option2_value: str
    option3_name:  str
    option3_value: str
    sku:           str
    barcode:       str
    quantity:      int


@dataclass
class Product:
    handle:           str
    title:            str
    description:      str
    price:            str
    compare_at_price: str
    cost_per_item:    str
    vendor:           str
    product_type:     str
    collections:      str
    tags:             str
    photo_url:        str
    weight:           str
    status:           str
    variants:         List[Variant] = field(default_factory=list)


def load_products(csv_path: str) -> List[Product]:
    """
    Parse products.csv into a list of Product objects.

    Product-level fields (Description, Price, Photo URL, etc.) are read
    from the FIRST row that belongs to each handle; subsequent rows for
    the same handle only contribute a new Variant.
    """
    products: dict[str, Product] = {}
    order: List[str] = []

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            handle = row["Handle"].strip()
            if not handle:
                continue

            if handle not in products:
                # Strip surrounding quotes that Shopify sometimes adds to titles
                title = row["Title"].strip().strip('"')
                products[handle] = Product(
                    handle=handle,
                    title=title,
                    description=row.get("Description", "").strip(),
                    price=row.get("Price", "0.00").strip() or "0.00",
                    compare_at_price=row.get("Compare At Price", "").strip(),
                    cost_per_item=row.get("Cost Per Item", "").strip(),
                    vendor=row.get("Vendor", "").strip(),
                    product_type=row.get("Type", "").strip(),
                    collections=row.get("Collections", "").strip(),
                    tags=row.get("Tags", "").strip(),
                    photo_url=row.get("Photo URL", "").strip(),
                    weight=row.get("Weight (lb)", "0.0").strip() or "0.0",
                    status=row.get("Status", "Active").strip() or "Active",
                )
                order.append(handle)

            variant = Variant(
                option1_name=row.get("Option1 Name", "").strip(),
                option1_value=row.get("Option1 Value", "").strip(),
                option2_name=row.get("Option2 Name", "").strip(),
                option2_value=row.get("Option2 Value", "").strip(),
                option3_name=row.get("Option3 Name", "").strip(),
                option3_value=row.get("Option3 Value", "").strip(),
                sku=row.get("SKU", "").strip(),
                barcode=row.get("Barcode", "").strip(),
                quantity=int(row.get("On hand (current)", "0").strip() or 0),
            )
            products[handle].variants.append(variant)

    return [products[h] for h in order]
