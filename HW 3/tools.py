"""Tool logic for the Campus Customs agent (wired up in agent.py).

identify_product() answers "is a Campus Customs product in this photo, and which one?" in three steps,
so it never compares the photo against the whole catalog image by image:

1. describe_photo: one vision call reads the printed garments in the photo (1 image).
   If nothing Yale-branded is being worn, it stops here.
2. shortlist_products: plain code scores every catalog entry's text fields against what was seen
   and keeps the best few (0 images).
3. compare_with_candidates: one vision call sees the photo next to the shortlisted catalog photos and
   picks the match, says it can't tell between a few, or says none (1 + up to 5 images).

Normally 7 images are uploaded per photo; counting retries the worst case is 8, and MAX_IMAGES_PER_RUN
enforces the limit of 10.
"""

import asyncio
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

from models import CatalogEntry, MatchVerdict, ObservedGarment, PhotoObservation, ProductIdentification
from portkey_client import MODEL, OUTPUT_DIR, PROMPTS_DIR, ROOT, build_agent_model, shrink_image


CATALOG_PATH = OUTPUT_DIR / "catalog.json"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

MAX_IMAGES_PER_RUN = 10
SHORTLIST_SIZE = 5
# A retry re-sends the whole request, images included, so retries count against the image limit.
# Step 1 may retry once (2 images at most); step 2 never retries (1 + SHORTLIST_SIZE images).
DESCRIBE_RETRIES = 1
assert (1 + DESCRIBE_RETRIES) + (1 + SHORTLIST_SIZE) <= MAX_IMAGES_PER_RUN
PHOTO_MAX_SIDE = 1024  # the customer photo keeps more detail: its text is small and at an angle
CANDIDATE_MAX_SIDE = 512  # flat catalog shots stay readable at this size
MAX_OUTPUT_TOKENS = 4000
REQUEST_TIMEOUT_SECONDS = 120.0

# Garments that look alike from a distance, so a near miss on type still earns some credit.
GARMENT_FAMILIES = [
    {"t-shirt", "long-sleeve t-shirt"},
    {"crewneck sweatshirt", "sweater", "mock neck"},
    {"hoodie", "full-zip hoodie"},
    {"quarter-zip", "fleece jacket", "jacket"},
]
COLOR_FILLER_WORDS = {"heather", "light", "dark", "deep", "bright", "pale"}
TEXT_STOPWORDS = {"the", "of", "and", "a", "an", "to", "go", "at"}
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


@dataclass
class AgentDeps:
    """What the agent's tools need for a run."""

    catalog: list[CatalogEntry]
    vision_model: str = MODEL
    reasoning_effort: str = "low"
    images_sent: int = field(default=0)

    def check_image_budget(self, count: int):
        if self.images_sent + count > MAX_IMAGES_PER_RUN:
            raise RuntimeError(f"Refusing to send {count} more images: the limit is {MAX_IMAGES_PER_RUN} per run.")


def load_catalog(path: Path = CATALOG_PATH):
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run build_catalog.py first.")
    return [CatalogEntry.model_validate(row) for row in json.loads(path.read_text(encoding="utf-8"))]


def resolve_image_path(image_path: str):
    """Find the photo whether the path is relative to the current folder or to the HW 3 folder."""
    for candidate in (Path(image_path), ROOT / image_path):
        if candidate.is_file() and candidate.suffix.lower() in IMAGE_SUFFIXES:
            return candidate.resolve()
    raise FileNotFoundError(f"No image found at {image_path!r}.")


def display_path(path: Path):
    """Show paths inside the HW 3 folder relative to it, e.g. data/test_images/image_01_true.jpeg."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


# --- The two vision steps -------------------------------------------------------------------------


def _model_settings(reasoning_effort: str):
    settings = OpenAIResponsesModelSettings(max_tokens=MAX_OUTPUT_TOKENS, timeout=REQUEST_TIMEOUT_SECONDS)
    if reasoning_effort != "default":
        settings["openai_reasoning_effort"] = reasoning_effort
    return settings


@cache
def _describe_agent(model_name: str, reasoning_effort: str):
    return Agent(
        build_agent_model(model_name),
        instructions=(PROMPTS_DIR / "describe_photo.md").read_text(encoding="utf-8"),
        output_type=PhotoObservation,
        model_settings=_model_settings(reasoning_effort),
        retries=DESCRIBE_RETRIES,
    )


@cache
def _match_agent(model_name: str, reasoning_effort: str):
    # No retries: a retry would upload all six images again. Answers are cleaned up in code instead.
    return Agent(
        build_agent_model(model_name),
        instructions=(PROMPTS_DIR / "match_product.md").read_text(encoding="utf-8"),
        output_type=MatchVerdict,
        model_settings=_model_settings(reasoning_effort),
        retries=0,
    )


def clean_verdict(verdict: MatchVerdict, candidate_ids: list[str]):
    """Keep the verdict consistent and limited to products the model was actually shown."""
    product_id = verdict.product_id if verdict.product_id in candidate_ids else None
    possible = [pid for pid in dict.fromkeys(verdict.possible_product_ids) if pid in candidate_ids and pid != product_id]
    found = verdict.product_found and bool(product_id or possible)
    named = [pid for pid in [verdict.product_id, *verdict.possible_product_ids] if pid]
    changed = (
        any(pid not in candidate_ids for pid in named)  # named a product it wasn't shown
        or found != verdict.product_found  # said "found" without naming a shown product
        or (verdict.product_id is not None and not verdict.product_found)  # named a product but said "not found"
    )
    return verdict.model_copy(
        update={
            "product_found": found,
            "product_id": product_id if found else None,
            "possible_product_ids": possible if found else [],
            # A verdict that had to be corrected is not one to be sure about.
            "confidence": "low" if changed else verdict.confidence,
        }
    )


async def describe_photo(photo: Path, deps: AgentDeps):
    """Vision step 1: read the printed garments in the photo."""
    image = await asyncio.to_thread(shrink_image, photo, PHOTO_MAX_SIDE)
    deps.check_image_budget(1 + DESCRIBE_RETRIES)
    result = await _describe_agent(deps.vision_model, deps.reasoning_effort).run(
        ["Customer photo:", BinaryContent(data=image, media_type="image/jpeg")]
    )
    deps.images_sent += result.usage.requests * 1
    return result.output


async def compare_with_candidates(photo: Path, candidates: list[CatalogEntry], deps: AgentDeps):
    """Vision step 2: show the photo next to the shortlisted catalog photos and pick the match."""
    photo_image = await asyncio.to_thread(shrink_image, photo, PHOTO_MAX_SIDE)
    content = ["Customer photo:", BinaryContent(data=photo_image, media_type="image/jpeg")]
    for entry in candidates:
        candidate_image = await asyncio.to_thread(shrink_image, ROOT / entry.image_file, CANDIDATE_MAX_SIDE)
        content += [
            f"Candidate product_id: {entry.product_id} ({entry.product_name}). {entry.matching_description}",
            BinaryContent(data=candidate_image, media_type="image/jpeg"),
        ]

    images_per_request = 1 + len(candidates)
    deps.check_image_budget(images_per_request)
    result = await _match_agent(deps.vision_model, deps.reasoning_effort).run(content)
    deps.images_sent += result.usage.requests * images_per_request
    return clean_verdict(result.output, [entry.product_id for entry in candidates])


# --- Shortlisting: plain code, no images ---------------------------------------------------------


def _tokens(texts):
    return {
        token
        for text in texts
        if text
        for token in TOKEN_PATTERN.findall(text.lower())
        if token not in TEXT_STOPWORDS
    }


def _entry_tokens(entry: CatalogEntry):
    return _tokens([*entry.visible_text, *entry.graphics, entry.affiliation_detail])


def _color_words(color: str):
    return {"grey" if word == "gray" else word for word in _tokens([color])} - COLOR_FILLER_WORDS


def _garment_similarity(seen: str, listed: str):
    if seen == listed:
        return 1.0
    if any(seen in family and listed in family for family in GARMENT_FAMILIES):
        return 0.5
    return 0.0


def shortlist_products(observation: PhotoObservation, catalog: list[CatalogEntry], limit: int = SHORTLIST_SIZE):
    """Rank catalog entries against the Yale-branded garments seen in the photo; return the best `limit`.

    Printed words and logos matter most, weighted so that rare words ("DAD", "BULLDOGS", "DAVENPORT")
    count far more than words on nearly everything ("YALE"). Garment type, color and design
    placement break ties between items with the same print.
    """
    garments = [garment for garment in observation.garments if garment.has_yale_branding]
    if not garments:
        return []

    entry_tokens = {entry.product_id: _entry_tokens(entry) for entry in catalog}
    document_frequency = Counter(token for tokens in entry_tokens.values() for token in tokens)
    total = len(catalog)

    def weight(token):
        return math.log((total + 1) / (document_frequency[token] + 1)) + 1

    def score(garment: ObservedGarment, entry: CatalogEntry):
        seen = _tokens([*garment.visible_text, *garment.graphics])
        listed = entry_tokens[entry.product_id]
        union = seen | listed
        text_score = sum(weight(t) for t in seen & listed) / sum(weight(t) for t in union) if union else 0.0
        color_score = 1.0 if _color_words(garment.base_color) & _color_words(entry.base_color) else 0.0
        placement_score = 1.0 if garment.design_placement == entry.design_placement else 0.0
        return (
            3.0 * text_score
            + 1.0 * _garment_similarity(garment.garment_type, entry.garment_type)
            + 0.5 * color_score
            + 0.5 * placement_score
        )

    best = {entry.product_id: max(score(g, entry) for g in garments) for entry in catalog}
    ranked = sorted(catalog, key=lambda entry: best[entry.product_id], reverse=True)
    return ranked[:limit]


# --- The ability the agent exposes ---------------------------------------------------------------


async def identify_product(photo: Path, deps: AgentDeps):
    """Decide whether a Campus Customs product appears in the photo, and which one if it can be told."""
    deps.images_sent = 0
    observation = await describe_photo(photo, deps)
    candidates = shortlist_products(observation, deps.catalog, SHORTLIST_SIZE)

    if not candidates:
        seen = "; ".join(" ".join(g.visible_text) or g.garment_type for g in observation.garments) or "no printed tops"
        return ProductIdentification(
            image_path=display_path(photo),
            product_found=False,
            product_id=None,
            product_name=None,
            possible_product_ids=[],
            confidence="high" if observation.garments else "medium",
            evidence=[f"Garments seen: {seen}.", "None of them shows Yale branding."],
            summary="No Yale-branded clothing is being worn in this photo, so no Campus Customs product appears.",
            observed_garments=observation.garments,
            candidates_checked=[],
            images_sent=deps.images_sent,
        )

    verdict = await compare_with_candidates(photo, candidates, deps)
    names = {entry.product_id: entry.product_name for entry in deps.catalog}
    return ProductIdentification(
        image_path=display_path(photo),
        product_found=verdict.product_found,
        product_id=verdict.product_id if verdict.product_found else None,
        product_name=names.get(verdict.product_id) if verdict.product_found else None,
        possible_product_ids=verdict.possible_product_ids if verdict.product_found else [],
        confidence=verdict.confidence,
        evidence=verdict.evidence,
        summary=verdict.summary,
        observed_garments=observation.garments,
        candidates_checked=[entry.product_id for entry in candidates],
        images_sent=deps.images_sent,
    )
