"""Campus Customs agent: the Pydantic AI entry point.

The agent reads a request, picks the ability that answers it, and returns that ability's structured
result. Its system prompt is prompts/prompts.md; the ability logic lives in tools.py.

Ability 1 (Problem 3): is a Campus Customs product in this photo, and which one?

Run with:  python agent.py --image "data/test_images/image_01_true.jpeg"
Several photos at once (Problem 4):  python agent.py --image data/test_images/*.jpeg
Results are saved as a JSON list with one ProductIdentification per photo.
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from pydantic_ai import Agent, ModelRetry, RunContext, ToolOutput
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

import tools
from models import ProductIdentification
from portkey_client import ALLOWED_MODELS, MODEL, OUTPUT_DIR, PROMPTS_DIR, build_agent_model, is_image_refused


SYSTEM_PROMPT_PATH = PROMPTS_DIR / "prompts.md"
DEFAULT_OUT_PATH = OUTPUT_DIR / "identify_product.json"


async def identify_product(ctx: RunContext[tools.AgentDeps], image_path: str) -> ProductIdentification:
    """Check a photo for Campus Customs products and say which one appears, if any.

    Args:
        image_path: Path to the photo, exactly as given in the request.
    """
    try:
        photo = tools.resolve_image_path(image_path)
    except FileNotFoundError as error:
        raise ModelRetry(f"{error} Use the exact path from the request.")
    return await tools.identify_product(photo, ctx.deps)


def build_agent(model_name: str = MODEL):
    # Each ability is an output tool: the agent chooses one, and that tool's result is the final answer,
    # so the tool's structured output is returned exactly as the tool built it.
    return Agent(
        build_agent_model(model_name),
        instructions=SYSTEM_PROMPT_PATH.read_text(encoding="utf-8"),
        deps_type=tools.AgentDeps,
        output_type=[ToolOutput(identify_product, name="identify_product")],
        model_settings=OpenAIResponsesModelSettings(max_tokens=2000, timeout=300.0),
        retries=2,
    )


def save_results(results: list[ProductIdentification], out_path: Path):
    """Save one ProductIdentification per photo, as a JSON list."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [result.model_dump() for result in results]
    out_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def describe_verdict(identification: ProductIdentification):
    if identification.product_id:
        return f"FOUND {identification.product_id} ({identification.product_name})"
    if identification.product_found:
        return f"FOUND a Campus Customs product; could be {', '.join(identification.possible_product_ids)}"
    return "NO Campus Customs product"


async def check_photo(agent: Agent, image: str, catalog, args):
    """Run the agent on one photo. Each photo gets its own deps, so its image count and tokens are its own."""
    deps = tools.AgentDeps(catalog=catalog, vision_model=args.vision_model, reasoning_effort=args.reasoning_effort)
    request = f"Check this photo for Campus Customs products and tell me which one, if you can: {image}"
    started = time.perf_counter()
    try:
        result = await agent.run(request, deps=deps)
    except Exception as error:
        if is_image_refused(error):
            return image, None, f"the model provider's content filter refused {image}, so it could not be checked"
        return image, None, f"{type(error).__name__}: {error}"

    identification = result.output
    elapsed = time.perf_counter() - started
    input_tokens = deps.input_tokens + result.usage.input_tokens
    output_tokens = deps.output_tokens + result.usage.output_tokens
    print(
        f"{identification.image_path}: {describe_verdict(identification)} [{identification.confidence} confidence]\n"
        f"  {identification.summary}\n"
        f"  {len(identification.candidates_checked)} products shortlisted, {identification.images_sent} images sent, "
        f"{elapsed:.1f}s, {input_tokens:,} input / {output_tokens:,} output tokens"
    )
    return image, identification, None


async def run(args):
    catalog = tools.load_catalog()
    agent = build_agent(args.model)

    # Photos are independent, so they are checked at the same time.
    outcomes = await asyncio.gather(*(check_photo(agent, image, catalog, args) for image in args.image))

    results = [identification for _, identification, _ in outcomes if identification]
    failures = [(image, error) for image, _, error in outcomes if error]
    if results:
        save_results(results, args.out)
        print(f"\nSaved {len(results)} result(s) to {args.out}")
    for image, error in failures:
        print(f"FAILED {image}: {error}")
    return 1 if failures else 0


def parse_args():
    parser = argparse.ArgumentParser(description="Campus Customs agent")
    parser.add_argument(
        "--image",
        required=True,
        nargs="+",
        action="extend",
        help="photo(s) to check for Campus Customs products; give several to check them together",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_PATH, help="where to save the structured results (a JSON list, one entry per photo)")
    parser.add_argument("--model", choices=ALLOWED_MODELS, default=MODEL, help="model that runs the agent")
    parser.add_argument("--vision-model", choices=ALLOWED_MODELS, default=MODEL, help="model for the photo checks")
    parser.add_argument(
        "--reasoning-effort",
        choices=["default", "none", "minimal", "low", "medium", "high"],
        default="low",
        help="for the photo checks; 'default' leaves it to the model",
    )
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(run(parse_args())))
