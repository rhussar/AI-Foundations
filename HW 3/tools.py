"""Tool logic for the Campus Customs agent (wired up in agent.py).

Every model instruction comes from prompts/prompts.md: the agent's system prompt is the top part, and
each step below loads its own "##" section from the "# Tool step instructions" part.

Ability 1: identify_product() answers "is a Campus Customs product in this photo, and which one?" in
three steps, so it never compares the photo against the whole catalog image by image:

1. describe_photo: one vision call reads the printed garments in the photo (1 image).
   If nothing Yale-branded is being worn, it stops here.
2. shortlist_products: plain code scores every catalog entry's text fields against what was seen
   and keeps the best few (0 images).
3. compare_with_candidates: one vision call sees the photo next to the shortlisted catalog photos and
   picks the match, says it can't tell between a few, or says none (1 + up to 5 images).

Normally 7 images are uploaded per photo; counting retries the worst case is 8, and MAX_IMAGES_PER_RUN
enforces the limit of 10.

Ability 2: judge_ad() answers "how well would this ad video get this customer to shop at Campus
Customs?":

1. load_profile: read and check the customer profile JSON (code).
2. analyze_video: once per video, whoever the customer is (cached on disk):
   - extract_frames: about one frame per second, near-duplicates dropped, at most 10 (code)
   - watch_video: one vision call describes the frames
   - listen_to_audio: one call tries to hear the soundtrack; if the model can't take audio, the
     analysis says so instead of guessing
   - match_featured_products: the Yale garments seen are matched to catalog products (code)
3. judge_for_customer: one text-only call judges the ad against the profile (no images).
"""

import asyncio
import hashlib
import io
import json
import math
import re
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

import cv2
import imageio_ffmpeg
from PIL import Image
from pydantic_ai import Agent, BinaryContent, ModelRetry
from pydantic_ai.models.openai import OpenAIChatModelSettings, OpenAIResponsesModelSettings

from models import (
    AdEffectiveness,
    AdJudgement,
    AudioObservation,
    CatalogEntry,
    CustomerProfile,
    MatchVerdict,
    ObservedGarment,
    PhotoObservation,
    ProductIdentification,
    VideoAnalysis,
    VideoObservation,
)
from portkey_client import MODEL, OUTPUT_DIR, PROMPTS_DIR, ROOT, build_agent_model, shrink_image


PROMPT_PATH = PROMPTS_DIR / "prompts.md"
TOOL_SECTION_HEADING = "# Tool step instructions"
CATALOG_PATH = OUTPUT_DIR / "catalog.json"
VIDEO_CACHE_DIR = OUTPUT_DIR / "cache"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".avi"}

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

MAX_VIDEO_FRAMES = 10
FRAME_MAX_SIDE = 768
# Frames closer than this (Bhattacharyya distance between color histograms, 0 = identical) add
# nothing new, so they aren't sent.
DUPLICATE_FRAME_DISTANCE = 0.08
AUDIO_SAMPLE_RATE = 16000
# A garment in the ad counts as a catalog product only if its printed text matches strongly and the
# garment type matches too (see _catalog_scorer: text is worth up to 3, garment type up to 1).
FEATURED_PRODUCT_MIN_SCORE = 3.5

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
    use_cache: bool = True
    images_sent: int = field(default=0)
    input_tokens: int = field(default=0)  # tool-step tokens, for cost reporting
    output_tokens: int = field(default=0)

    def record_usage(self, usage, images_per_request: int = 0):
        # usage.requests includes retries, and each retry re-sends the images.
        self.images_sent += usage.requests * images_per_request
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens

    def reset_usage(self):
        self.images_sent = self.input_tokens = self.output_tokens = 0

    def check_image_budget(self, count: int):
        if self.images_sent + count > MAX_IMAGES_PER_RUN:
            raise RuntimeError(f"Refusing to send {count} more images: the limit is {MAX_IMAGES_PER_RUN} per run.")


# --- Files and prompts ---------------------------------------------------------------------------


def load_system_prompt():
    """The agent's system prompt: prompts.md above the tool step instructions."""
    return PROMPT_PATH.read_text(encoding="utf-8").split(TOOL_SECTION_HEADING)[0].split("<!--")[0].strip()


@cache
def load_prompt_section(heading: str):
    """The instructions for one tool step: the '## heading' section of prompts.md."""
    tool_part = PROMPT_PATH.read_text(encoding="utf-8").split(TOOL_SECTION_HEADING, 1)[1]
    sections = {}
    for block in tool_part.split("\n## ")[1:]:
        title, _, body = block.partition("\n")
        sections[title.strip()] = body.strip()
    if heading not in sections:
        raise KeyError(f"prompts.md has no '## {heading}' section. Found: {list(sections)}")
    return sections[heading]


def load_catalog(path: Path = CATALOG_PATH):
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run build_catalog.py first.")
    return [CatalogEntry.model_validate(row) for row in json.loads(path.read_text(encoding="utf-8"))]


def resolve_path(path_text: str, suffixes: set[str], kind: str):
    """Find a file whether its path is relative to the current folder or to the HW 3 folder."""
    for candidate in (Path(path_text), ROOT / path_text):
        if candidate.is_file() and candidate.suffix.lower() in suffixes:
            return candidate.resolve()
    raise FileNotFoundError(f"No {kind} found at {path_text!r}.")


def resolve_image_path(image_path: str):
    return resolve_path(image_path, IMAGE_SUFFIXES, "image")


def display_path(path: Path):
    """Show paths inside the HW 3 folder relative to it, e.g. data/test_images/image_01_true.jpeg."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def load_profile(path: Path):
    try:
        return CustomerProfile.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise ValueError(f"{display_path(path)} is not a valid customer profile: {error}") from error


# --- Model calls ---------------------------------------------------------------------------------


def _model_settings(reasoning_effort: str, api: str = "responses"):
    settings_type = OpenAIChatModelSettings if api == "chat" else OpenAIResponsesModelSettings
    settings = settings_type(max_tokens=MAX_OUTPUT_TOKENS, timeout=REQUEST_TIMEOUT_SECONDS)
    if reasoning_effort != "default":
        settings["openai_reasoning_effort"] = reasoning_effort
    return settings


@cache
def _step_agent(heading: str, output_type, model_name: str, reasoning_effort: str, retries: int, api: str = "responses"):
    """One small agent per tool step, with its instructions from prompts.md."""
    return Agent(
        build_agent_model(model_name, api=api),
        instructions=load_prompt_section(heading),
        output_type=output_type,
        model_settings=_model_settings(reasoning_effort, api),
        retries=retries,
    )


# --- Catalog scoring: plain code, no images ------------------------------------------------------


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


def _catalog_scorer(catalog: list[CatalogEntry]):
    """Return score(garment, entry): how well a seen garment matches a catalog entry, from 0 to 5.

    Printed words and logos matter most (up to 3), weighted so that rare words ("DAD", "BULLDOGS",
    "DAVENPORT") count far more than words on nearly everything ("YALE"). Garment type (up to 1),
    color (0.5) and design placement (0.5) break ties between items with the same print.
    """
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

    return score


def shortlist_products(observation: PhotoObservation, catalog: list[CatalogEntry], limit: int = SHORTLIST_SIZE):
    """Rank catalog entries against the Yale-branded garments seen in the photo; return the best `limit`."""
    garments = [garment for garment in observation.garments if garment.has_yale_branding]
    if not garments:
        return []
    score = _catalog_scorer(catalog)
    best = {entry.product_id: max(score(g, entry) for g in garments) for entry in catalog}
    return sorted(catalog, key=lambda entry: best[entry.product_id], reverse=True)[:limit]


def match_featured_products(garments: list[ObservedGarment], catalog: list[CatalogEntry]):
    """The closest catalog product for each Yale-branded garment seen in an ad, if it matches strongly."""
    score = _catalog_scorer(catalog)
    featured = []
    for garment in garments:
        if not garment.has_yale_branding:
            continue
        best = max(catalog, key=lambda entry: score(garment, entry))
        if score(garment, best) >= FEATURED_PRODUCT_MIN_SCORE and best.product_id not in featured:
            featured.append(best.product_id)
    return featured


# --- Ability 1: identify a product in a photo ----------------------------------------------------


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
    agent = _step_agent(
        "identify_product: read the photo", PhotoObservation, deps.vision_model, deps.reasoning_effort, DESCRIBE_RETRIES
    )
    result = await agent.run(["Customer photo:", BinaryContent(data=image, media_type="image/jpeg")])
    deps.record_usage(result.usage, images_per_request=1)
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
    # No retries: a retry would upload all six images again. Answers are cleaned up in code instead.
    agent = _step_agent(
        "identify_product: compare with candidates", MatchVerdict, deps.vision_model, deps.reasoning_effort, 0
    )
    result = await agent.run(content)
    deps.record_usage(result.usage, images_per_request)
    return clean_verdict(result.output, [entry.product_id for entry in candidates])


async def identify_product(photo: Path, deps: AgentDeps):
    """Decide whether a Campus Customs product appears in the photo, and which one if it can be told."""
    deps.reset_usage()
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


# --- Ability 2: judge an ad video for a customer ------------------------------------------------


def extract_frames(video: Path, max_frames: int = MAX_VIDEO_FRAMES):
    """Take about one frame per second (at most max_frames), dropping frames that barely differ.

    Returns the video's duration and a list of (time in seconds, JPEG bytes).
    """
    capture = cv2.VideoCapture(str(video))
    try:
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = capture.get(cv2.CAP_PROP_FPS) or 24.0
        if frame_count <= 0:
            raise ValueError(f"Could not read any frames from {display_path(video)}.")
        duration = frame_count / fps
        count = min(max_frames, max(1, round(duration)))
        # The middle of each equal slice, so the very first and last frames (often fades) are skipped.
        indexes = [min(frame_count - 1, round((k + 0.5) * frame_count / count)) for k in range(count)]

        frames = []
        last_histogram = None
        for index in indexes:
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if not ok:
                continue
            histogram = cv2.calcHist([cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)], [0, 1], None, [32, 32], [0, 180, 0, 256])
            cv2.normalize(histogram, histogram)
            if last_histogram is not None and (
                cv2.compareHist(last_histogram, histogram, cv2.HISTCMP_BHATTACHARYYA) < DUPLICATE_FRAME_DISTANCE
            ):
                continue
            last_histogram = histogram

            image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            image.thumbnail((FRAME_MAX_SIDE, FRAME_MAX_SIDE))
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=85)
            frames.append((round(index / fps, 1), buffer.getvalue()))
    finally:
        capture.release()
    return duration, frames


def extract_audio(video: Path):
    """The soundtrack as 16 kHz mono WAV bytes, or None if the video has no audio."""
    command = [
        imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", str(video),
        "-vn", "-ac", "1", "-ar", str(AUDIO_SAMPLE_RATE), "-f", "wav", "pipe:1",
    ]  # fmt: skip
    completed = subprocess.run(command, capture_output=True)
    if completed.returncode != 0 or len(completed.stdout) <= 44:  # 44 bytes is an empty WAV header
        return None
    return completed.stdout


async def watch_video(frames: list[tuple[float, bytes]], deps: AgentDeps):
    """Vision step: describe what the ad shows."""
    content = ["Frames from the ad, in order:"]
    for seconds, image in frames:
        content += [f"Frame at {seconds}s:", BinaryContent(data=image, media_type="image/jpeg")]
    agent = _step_agent(
        "judge_ad_effectiveness: watch the video", VideoObservation, deps.vision_model, deps.reasoning_effort, 1
    )
    result = await agent.run(content)
    deps.record_usage(result.usage, images_per_request=len(frames))
    return result.output


async def listen_to_audio(video: Path, deps: AgentDeps):
    """Listening step: returns (AudioObservation or None, note explaining why it's None)."""
    audio = await asyncio.to_thread(extract_audio, video)
    if audio is None:
        return None, "The video has no audio track."
    agent = _step_agent(
        "judge_ad_effectiveness: listen to the audio",
        AudioObservation,
        deps.vision_model,
        deps.reasoning_effort,
        0,
        api="chat",  # the Responses API can't take audio; Chat Completions can, if the model supports it
    )
    try:
        result = await agent.run(["The ad's audio track:", BinaryContent(data=audio, media_type="audio/wav")])
    except Exception as error:  # the model may not accept audio at all; the judge is told so
        reason = str(error).splitlines()[0][:300]
        return None, f"The soundtrack could not be analysed ({type(error).__name__}: {reason})."
    deps.record_usage(result.usage)
    return result.output, None


def _video_cache_key(video: Path, deps: AgentDeps):
    """Changes whenever the video, the model or the watch/listen instructions change."""
    digest = hashlib.sha256(video.read_bytes())
    for heading in ("judge_ad_effectiveness: watch the video", "judge_ad_effectiveness: listen to the audio"):
        digest.update(load_prompt_section(heading).encode())
    digest.update(f"{deps.vision_model}|{deps.reasoning_effort}|{MAX_VIDEO_FRAMES}|{FRAME_MAX_SIDE}".encode())
    return digest.hexdigest()[:20]


async def _analyze_video_uncached(video: Path, deps: AgentDeps):
    duration, frames = await asyncio.to_thread(extract_frames, video)
    (observation, (audio, audio_note)) = await asyncio.gather(watch_video(frames, deps), listen_to_audio(video, deps))
    return VideoAnalysis(
        video_path=display_path(video),
        duration_seconds=round(duration, 2),
        frame_times_seconds=[seconds for seconds, _ in frames],
        observation=observation,
        audio_analyzed=audio is not None,
        audio=audio,
        audio_note=audio_note,
        featured_products=match_featured_products(observation.garments_shown, deps.catalog),
    )


# One analysis per video per run, even when several profiles are judged at the same time.
_video_analyses: dict[str, asyncio.Task] = {}


async def analyze_video(video: Path, deps: AgentDeps):
    """Analyse the video once and reuse it for every customer: in memory within a run, on disk across runs."""
    key = _video_cache_key(video, deps)
    cache_file = VIDEO_CACHE_DIR / f"video-{key}.json"
    if deps.use_cache and cache_file.exists():
        try:
            return VideoAnalysis.model_validate_json(cache_file.read_text(encoding="utf-8"))
        except ValueError:
            pass  # stale or damaged cache file: analyse again

    if key not in _video_analyses:
        _video_analyses[key] = asyncio.ensure_future(_analyze_video_uncached(video, deps))
    try:
        analysis = await _video_analyses[key]
    except Exception:
        _video_analyses.pop(key, None)  # let a later attempt try again
        raise

    VIDEO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(analysis.model_dump_json(indent=2), encoding="utf-8")
    return analysis


def _score_matches_response(judgement: AdJudgement):
    expected = (
        "likely to shop" if judgement.effectiveness_score >= 7
        else "might shop" if judgement.effectiveness_score >= 4
        else "unlikely to shop"
    )  # fmt: skip
    return judgement.likely_response == expected, expected


@cache
def _judge_agent(model_name: str, reasoning_effort: str):
    # Text only, so a retry is cheap: it's allowed to fix an answer that contradicts itself.
    agent = _step_agent(
        "judge_ad_effectiveness: judge for the customer", AdJudgement, model_name, reasoning_effort, 2
    )

    @agent.output_validator
    def consistent(judgement: AdJudgement):
        matches, expected = _score_matches_response(judgement)
        if not matches:
            raise ModelRetry(
                f"A score of {judgement.effectiveness_score} means likely_response should be '{expected}'. "
                "Change the score or the response so they agree."
            )
        if not judgement.profile_fit:
            raise ModelRetry("profile_fit is empty: list the profile points that matter most and how the ad serves each.")
        return judgement

    return agent


async def judge_for_customer(analysis: VideoAnalysis, profile: CustomerProfile, deps: AgentDeps):
    """Text-only step: judge the analysed ad for one customer."""
    products = {entry.product_id: entry for entry in deps.catalog}
    featured = [
        f"- {products[pid].product_name} ({pid}): made for {', '.join(products[pid].target_audience)}"
        for pid in analysis.featured_products
    ] or ["- none matched the catalog closely"]
    audio_part = (
        analysis.audio.model_dump_json(indent=2)
        if analysis.audio
        else f"Not analysed. {analysis.audio_note} Do not guess what the soundtrack says."
    )
    request = "\n\n".join(
        [
            f"Customer profile:\n{profile.model_dump_json(indent=2)}",
            f"What the ad shows ({analysis.duration_seconds}s long):\n{analysis.observation.model_dump_json(indent=2)}",
            f"What the ad sounds like:\n{audio_part}",
            "Campus Customs catalog products the ad appears to feature:\n" + "\n".join(featured),
        ]
    )
    result = await _judge_agent(deps.vision_model, deps.reasoning_effort).run(request)
    deps.record_usage(result.usage)
    return result.output


async def judge_ad(video: Path, profile_path: Path, deps: AgentDeps):
    """How effective would this ad video be at getting this customer to shop at Campus Customs?"""
    deps.reset_usage()
    profile = await asyncio.to_thread(load_profile, profile_path)
    analysis = await analyze_video(video, deps)
    judgement = await judge_for_customer(analysis, profile, deps)
    return AdEffectiveness(
        video_path=display_path(video),
        profile_path=display_path(profile_path),
        profile_name=profile.name,
        **judgement.model_dump(),
        video_analysis=analysis,
    )
