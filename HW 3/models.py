"""Pydantic models shared by the HW 3 scripts.

CatalogEntry is one product in output/catalog.json. The model fills in ProductAttributes from the
photo (it is the Pydantic AI agent's output_type); build_catalog.py adds the fields that come from the
file itself, so the model is never asked to invent an ID or a path.
"""

from typing import Literal

from pydantic import BaseModel, Field


GarmentType = Literal[
    "t-shirt",
    "long-sleeve t-shirt",
    "crewneck sweatshirt",
    "hoodie",
    "full-zip hoodie",
    "quarter-zip",
    "fleece jacket",
    "jacket",
    "sweater",
    "mock neck",
    "other",
]

DesignPlacement = Literal["full front", "left chest", "center chest", "sleeve", "back", "all-over", "other"]

Affiliation = Literal[
    "Yale University",
    "residential college",
    "graduate or professional school",
    "athletics",
    "family",
    "other",
]

Audience = Literal["student", "graduate student", "parent", "family member", "alumni", "athlete", "fan"]


class ProductAttributes(BaseModel):
    """What the model reads off one catalogue photo."""

    product_name: str = Field(description="Short shop-style name, e.g. 'Yale Dad T-Shirt'.")
    garment_type: GarmentType = Field(description="The kind of garment.")
    base_color: str = Field(description="Main fabric color in plain words, e.g. 'heather grey', 'navy'.")
    print_colors: list[str] = Field(description="Colors of the printed or embroidered design, e.g. ['navy', 'white'].")
    visible_text: list[str] = Field(
        description="Every word printed on the garment, exactly as written, top to bottom, "
        "e.g. ['YALE', 'UNIVERSITY', 'DAD']. Ignore tiny neck-label text. Empty if none."
    )
    graphics: list[str] = Field(
        description="Logos or images in the design, e.g. ['block Y', 'Davenport College shield', 'bulldog']. "
        "Empty if text only."
    )
    design_placement: DesignPlacement = Field(description="Where the main design sits on the garment.")
    garment_brand: str | None = Field(
        description="Maker brand if clearly readable (e.g. Champion, Under Armour, Brooks Brothers), else null."
    )
    affiliation: Affiliation = Field(description="Which part of Yale the design represents.")
    affiliation_detail: str | None = Field(
        description="The specific college, school, sport or family role, e.g. 'Davenport College', "
        "'Hockey', 'Dad'. Null for general Yale designs."
    )
    target_audience: list[Audience] = Field(description="Who this product is most likely made for.")
    matching_description: str = Field(
        description="One sentence on what would identify this exact product on a person in a photo, "
        "including what separates it from similar Yale items."
    )


class CatalogEntry(ProductAttributes):
    """One row of output/catalog.json."""

    product_id: str = Field(description="File name without extension; the stable key for this product.")
    image_file: str = Field(description="Path to the product photo, relative to the HW 3 folder.")
    image_sha256: str = Field(description="Hash of the photo, so re-runs can skip products that have not changed.")
