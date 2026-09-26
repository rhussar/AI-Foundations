"""Pydantic models shared by the HW 3 scripts.

CatalogEntry is one product in output/catalog.json. The model fills in ProductAttributes from the
photo (it is the Pydantic AI agent's output_type); build_catalog.py adds the fields that come from the
file itself, so the model is never asked to invent an ID or a path.

ProductIdentification is the agent's answer to "is a Campus Customs product in this photo, and which
one?". PhotoObservation and MatchVerdict are what the two vision steps inside that tool return.
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


# --- Problem 3: product identification ---------------------------------------------------------

Confidence = Literal["high", "medium", "low"]


class ObservedGarment(BaseModel):
    """One printed garment seen on a person in a photo (vision step 1)."""

    worn_by: str = Field(description="Who is wearing it, in a few words, e.g. 'smiling man in front of the sign'.")
    garment_type: GarmentType = Field(description="The kind of garment.")
    base_color: str = Field(description="Main fabric color in plain words, e.g. 'heather grey', 'navy'.")
    visible_text: list[str] = Field(
        description="Every word printed on the garment, exactly as written, top to bottom. Empty if none is readable."
    )
    graphics: list[str] = Field(description="Logos or images on the garment, e.g. ['block Y', 'bulldog'].")
    design_placement: DesignPlacement = Field(description="Where the main design sits on the garment.")
    has_yale_branding: bool = Field(
        description="True only if the garment itself shows Yale branding: the word Yale, a Yale college or school "
        "name or crest, 'Bulldogs', or a Yale block Y. A Yale building in the background does not count."
    )


class PhotoObservation(BaseModel):
    """Everything printed that people in the photo are wearing on their upper body (vision step 1)."""

    garments: list[ObservedGarment] = Field(
        description="One item per visible upper-body garment that has a print, logo or text. Empty if none."
    )


class MatchVerdict(BaseModel):
    """The model's decision after comparing the photo with the shortlisted catalog photos (vision step 2)."""

    product_found: bool = Field(description="True if one of the candidate products appears in the photo.")
    product_id: str | None = Field(
        description="The candidate's product_id if you can tell exactly which product it is, else null."
    )
    possible_product_ids: list[str] = Field(
        description="If a candidate product appears but you can't tell which one, the product_ids it could be. "
        "Otherwise empty."
    )
    confidence: Confidence = Field(description="How sure you are of the decision.")
    evidence: list[str] = Field(
        description="Specific things you can see that support the decision, e.g. 'navy YALE text over DAD on the chest'."
    )
    summary: str = Field(description="One or two sentences explaining the decision.")


class ProductIdentification(BaseModel):
    """The agent's structured answer for one photo: saved to output/identify_product.json."""

    image_path: str = Field(description="The photo that was checked.")
    product_found: bool = Field(description="Whether a Campus Customs product appears in the photo.")
    product_id: str | None = Field(description="The exact catalog product, if it can be told apart; else null.")
    product_name: str | None = Field(description="Catalog name of product_id, for people reading the result.")
    possible_product_ids: list[str] = Field(
        description="When a product is found but can't be pinned down, the catalog products it could be."
    )
    confidence: Confidence = Field(description="How sure the agent is of the decision.")
    evidence: list[str] = Field(description="What in the photo supports the decision.")
    summary: str = Field(description="Plain-language explanation of the decision.")
    observed_garments: list[ObservedGarment] = Field(description="What the agent saw people wearing.")
    candidates_checked: list[str] = Field(description="Catalog products shortlisted and compared with the photo.")
    images_sent: int = Field(description="Images uploaded to the model for this photo (capped at 10).")
