"""Campus Customs agent: the Pydantic AI entry point.

The agent reads a request, picks the ability that answers it, and returns that ability's structured
result. Its system prompt is prompts/prompts.md; the ability logic lives in tools.py.

Ability 1 (Problem 3): is a Campus Customs product in this photo, and which one?

Run with:  python agent.py --image "data/test_images/image_01_true.jpeg"
"""

import argparse
import asyncio
import json
import sys
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


def save_result(result: ProductIdentification, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result.model_dump(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


async def run(args):
    deps = tools.AgentDeps(
        catalog=tools.load_catalog(),
        vision_model=args.vision_model,
        reasoning_effort=args.reasoning_effort,
    )
    agent = build_agent(args.model)
    request = f"Check this photo for Campus Customs products and tell me which one, if you can: {args.image}"

    try:
        result = await agent.run(request, deps=deps)
    except Exception as error:
        if is_image_refused(error):
            print(f"The model provider's content filter refused {args.image}, so it could not be checked.")
        else:
            print(f"The agent failed: {type(error).__name__}: {error}")
        return 1

    identification = result.output
    save_result(identification, args.out)

    if identification.product_id:
        verdict = f"FOUND {identification.product_id} ({identification.product_name})"
    elif identification.product_found:
        verdict = f"FOUND a Campus Customs product; could be {', '.join(identification.possible_product_ids)}"
    else:
        verdict = "NO Campus Customs product"
    print(f"{identification.image_path}: {verdict} [{identification.confidence} confidence]")
    print(identification.summary)
    print(f"Checked {len(identification.candidates_checked)} shortlisted products, {identification.images_sent} images sent.")
    print(f"Saved to {args.out}")
    return 0


def parse_args():
    parser = argparse.ArgumentParser(description="Campus Customs agent")
    parser.add_argument("--image", required=True, help="photo to check for Campus Customs products")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_PATH, help="where to save the structured result")
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
