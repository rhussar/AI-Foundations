"""Problem 2: build the Campus Customs product catalog.

Turns every product photo in data/products into a CatalogEntry (see models.py) using a vision model
through Portkey, and saves them all to output/catalogue.json.

Speed: the photos are described concurrently (up to --concurrency requests in flight at once) instead
of one at a time, each photo is shrunk before upload, and products already in catalogue.json are skipped
unless their photo changed. See output/harness.md.

Run with:  python build_catalogue.py
Try a few first:  python build_catalogue.py --limit 5
"""

import argparse
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path

from pydantic import ValidationError
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

from models import CatalogEntry, ProductAttributes
from tools import (
    ALLOWED_MODELS,
    DATA_DIR,
    MODEL,
    OUTPUT_DIR,
    ROOT,
    build_agent_model,
    is_image_refused,
    load_prompt_section,
    shrink_image,
)


PROMPT_SECTION = "build_catalogue: describe a product photo"  # in prompts/prompt.md
DEFAULT_PRODUCTS_DIR = DATA_DIR / "products"
DEFAULT_OUT_PATH = OUTPUT_DIR / "catalogue.json"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

DEFAULT_CONCURRENCY = 16
MAX_IMAGE_SIDE = 768  # large enough to read left-chest text, small enough to keep uploads and image tokens down
MAX_OUTPUT_TOKENS = 4000
REQUEST_TIMEOUT_SECONDS = 120.0
ID_FIELDS = ("product_id", "image_file", "image_sha256")


def file_sha256(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_products(products_dir: Path):
    if not products_dir.is_dir():
        raise FileNotFoundError(f"{products_dir} not found. Unzip data.zip in the HW 3 folder first.")
    products = sorted(p for p in products_dir.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if not products:
        raise FileNotFoundError(f"No product photos found in {products_dir}")
    return products


def load_cached_entries(out_path: Path):
    """Entries from a previous run, keyed by product_id. Rows that no longer fit the model are dropped."""
    if not out_path.exists():
        return {}
    try:
        rows = json.loads(out_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

    cached = {}
    for row in rows:
        try:
            entry = CatalogEntry.model_validate(row)
        except ValidationError:
            continue
        cached[entry.product_id] = entry
    return cached


def build_agent(model_name: str, reasoning_effort: str):
    settings = OpenAIResponsesModelSettings(max_tokens=MAX_OUTPUT_TOKENS, timeout=REQUEST_TIMEOUT_SECONDS)
    if reasoning_effort != "default":
        settings["openai_reasoning_effort"] = reasoning_effort

    return Agent(
        build_agent_model(model_name),
        instructions=load_prompt_section(PROMPT_SECTION),
        output_type=ProductAttributes,
        model_settings=settings,
        retries=2,
    )


async def describe_product(agent: Agent, path: Path, sha256: str, semaphore: asyncio.Semaphore):
    image_bytes = await asyncio.to_thread(shrink_image, path, MAX_IMAGE_SIDE)
    async with semaphore:
        result = await agent.run(
            [f"Product photo file name: {path.name}", BinaryContent(data=image_bytes, media_type="image/jpeg")]
        )

    entry = CatalogEntry(
        product_id=path.stem,
        image_file=path.relative_to(ROOT).as_posix(),
        image_sha256=sha256,
        **result.output.model_dump(),
    )
    return entry, result.usage


def entry_to_row(entry: CatalogEntry):
    """Dump an entry with its ID fields first, so catalogue.json reads naturally."""
    data = entry.model_dump()
    return {key: data[key] for key in ID_FIELDS} | {k: v for k, v in data.items() if k not in ID_FIELDS}


def write_catalog(entries: dict, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [entry_to_row(entries[product_id]) for product_id in sorted(entries)]
    out_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


async def build_catalog(args):
    products = find_products(args.products_dir)
    if args.limit:
        products = products[: args.limit]

    cached = {} if args.no_cache else load_cached_entries(args.out)
    hashes = {path: file_sha256(path) for path in products}
    entries = {}
    todo = []
    for path in products:
        previous = cached.get(path.stem)
        if previous and previous.image_sha256 == hashes[path]:
            entries[path.stem] = previous
        else:
            todo.append(path)

    print(
        f"{len(products)} products: {len(entries)} already catalogued, {len(todo)} to describe "
        f"with {args.model} ({args.concurrency} at a time)"
    )
    if not todo:
        write_catalog(entries, args.out)
        print(f"Nothing new. Catalog unchanged at {args.out}")
        return 0

    agent = build_agent(args.model, args.reasoning_effort)
    semaphore = asyncio.Semaphore(args.concurrency)
    input_tokens = output_tokens = 0
    started = time.perf_counter()

    # Canary: send one photo on its own first. If the key, network or model settings are wrong,
    # this fails once instead of failing (and possibly billing) every photo in parallel.
    # A photo refused by the content filter only says that photo is a problem, so it is recorded
    # as a failure and the next photo becomes the canary.
    failures = {}
    queue = list(todo)
    while queue:
        canary = queue.pop(0)
        done = len(failures) + 1
        try:
            entry, usage = await describe_product(agent, canary, hashes[canary], semaphore)
        except Exception as error:
            if is_image_refused(error):
                failures[canary.stem] = f"{type(error).__name__}: {error}"
                print(f"[{done}/{len(todo)}] {canary.stem}  REFUSED by content filter; trying the next photo")
                continue
            print(f"First request failed, so the other {len(queue)} were not sent.\n{type(error).__name__}: {error}")
            return 1
        entries[entry.product_id] = entry
        input_tokens += usage.input_tokens
        output_tokens += usage.output_tokens
        print(f"[{done}/{len(todo)}] {canary.stem}")
        break

    async def describe_or_fail(path: Path):
        try:
            return path, *(await describe_product(agent, path, hashes[path], semaphore)), None
        except Exception as error:
            return path, None, None, error

    tasks = [describe_or_fail(path) for path in queue]
    for done, finished in enumerate(asyncio.as_completed(tasks), start=len(todo) - len(queue) + 1):
        path, entry, usage, error = await finished
        if error:
            failures[path.stem] = f"{type(error).__name__}: {error}"
            print(f"[{done}/{len(todo)}] {path.stem}  FAILED")
            continue
        entries[entry.product_id] = entry
        input_tokens += usage.input_tokens
        output_tokens += usage.output_tokens
        print(f"[{done}/{len(todo)}] {path.stem}")

    # Save whatever succeeded, so a re-run only retries the failures.
    write_catalog(entries, args.out)
    elapsed = time.perf_counter() - started
    print(
        f"\nSaved {len(entries)} entries to {args.out} in {elapsed:.1f}s "
        f"({len(todo) - len(failures)} described, {input_tokens:,} input / {output_tokens:,} output tokens)"
    )
    if failures:
        print(f"{len(failures)} failed; run again to retry just these:")
        for product_id, message in sorted(failures.items()):
            print(f"  {product_id}: {message}")
        return 1
    return 0


def parse_args():
    parser = argparse.ArgumentParser(description="Build output/catalogue.json from the product photos.")
    parser.add_argument("--products-dir", type=Path, default=DEFAULT_PRODUCTS_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_PATH)
    parser.add_argument("--model", choices=ALLOWED_MODELS, default=MODEL)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="requests in flight at once")
    parser.add_argument(
        "--reasoning-effort",
        choices=["default", "none", "minimal", "low", "medium", "high"],
        default="low",
        help="'default' leaves it unset so the model uses its own default",
    )
    parser.add_argument("--limit", type=int, help="only catalogue the first N photos (for a cheap test run)")
    parser.add_argument("--no-cache", action="store_true", help="re-describe every photo, even unchanged ones")
    args = parser.parse_args()
    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1")
    return args


if __name__ == "__main__":
    sys.exit(asyncio.run(build_catalog(parse_args())))
