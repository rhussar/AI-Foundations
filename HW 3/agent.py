"""Campus Customs agent: the Pydantic AI entry point.

The agent reads a request, picks the ability that answers it, and returns that ability's structured
result. Its system prompt is the top part of prompts/prompts.md; the ability logic lives in tools.py.

Ability 1 (Problems 3-4): is a Campus Customs product in this photo, and which one?
    python agent.py --image "data/test_images/image_01_true.jpeg"
    python agent.py --image data/test_images/*.jpeg            (several photos at once)
    -> output/identify_product.json, a list with one ProductIdentification per photo

Ability 2 (Problem 5): how well would this ad video get this customer to shop at Campus Customs?
    python agent.py --video "data/videos/ad_humble.mp4" --profile "profiles/profile_student.json"
    (give several --profile files to judge the same video for each customer)
    -> output/ad_effectiveness.json, a list with one AdEffectiveness per profile
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
from models import AdEffectiveness, ProductIdentification
from portkey_client import ALLOWED_MODELS, MODEL, OUTPUT_DIR, build_agent_model, is_image_refused


IDENTIFY_OUT_PATH = OUTPUT_DIR / "identify_product.json"
AD_OUT_PATH = OUTPUT_DIR / "ad_effectiveness.json"


# --- The agent's abilities (logic in tools.py) ---------------------------------------------------


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


async def judge_ad_effectiveness(ctx: RunContext[tools.AgentDeps], video_path: str, profile_path: str) -> AdEffectiveness:
    """Judge how effective an ad video would be at getting one customer to shop at Campus Customs.

    Args:
        video_path: Path to the ad video, exactly as given in the request.
        profile_path: Path to the customer profile JSON file, exactly as given in the request.
    """
    try:
        video = tools.resolve_path(video_path, tools.VIDEO_SUFFIXES, "video")
        profile = tools.resolve_path(profile_path, {".json"}, "customer profile (.json)")
    except FileNotFoundError as error:
        raise ModelRetry(f"{error} Use the exact paths from the request.")
    return await tools.judge_ad(video, profile, ctx.deps)


def build_agent(model_name: str = MODEL):
    # Each ability is an output tool: the agent chooses one, and that tool's result is the final answer,
    # so the tool's structured output is returned exactly as the tool built it.
    return Agent(
        build_agent_model(model_name),
        instructions=tools.load_system_prompt(),
        deps_type=tools.AgentDeps,
        output_type=[
            ToolOutput(identify_product, name="identify_product"),
            ToolOutput(judge_ad_effectiveness, name="judge_ad_effectiveness"),
        ],
        model_settings=OpenAIResponsesModelSettings(max_tokens=2000, timeout=300.0),
        retries=2,
    )


# --- Running requests ----------------------------------------------------------------------------


def save_results(results: list, out_path: Path):
    """Save one structured result per photo or profile, as a JSON list."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [result.model_dump() for result in results]
    out_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def describe_identification(identification: ProductIdentification):
    if identification.product_id:
        verdict = f"FOUND {identification.product_id} ({identification.product_name})"
    elif identification.product_found:
        verdict = f"FOUND a Campus Customs product; could be {', '.join(identification.possible_product_ids)}"
    else:
        verdict = "NO Campus Customs product"
    return (
        f"{identification.image_path}: {verdict} [{identification.confidence} confidence]\n"
        f"  {identification.summary}\n"
        f"  {len(identification.candidates_checked)} products shortlisted, {identification.images_sent} images sent"
    )


def describe_ad_result(result: AdEffectiveness):
    analysis = result.video_analysis
    audio = "audio analysed" if analysis.audio_analyzed else "audio NOT analysed"
    return (
        f"{result.video_path} for {result.profile_name} ({result.profile_path}): "
        f"{result.effectiveness_score}/10, {result.likely_response} [{result.confidence} confidence]\n"
        f"  {result.summary}\n"
        f"  {len(analysis.frame_times_seconds)} frames, {audio}"
    )


async def run_request(agent: Agent, request: str, label: str, expected_type: type, deps: tools.AgentDeps, describe):
    """Run the agent on one request. Each request gets its own deps, so its images and tokens are its own."""
    started = time.perf_counter()
    try:
        result = await agent.run(request, deps=deps)
    except Exception as error:
        if is_image_refused(error):
            return label, None, "the model provider's content filter refused an image, so it could not be checked"
        return label, None, f"{type(error).__name__}: {error}"
    if not isinstance(result.output, expected_type):
        return label, None, f"the agent used the wrong ability and returned {type(result.output).__name__}"

    elapsed = time.perf_counter() - started
    input_tokens = deps.input_tokens + result.usage.input_tokens
    output_tokens = deps.output_tokens + result.usage.output_tokens
    print(f"{describe(result.output)}, {elapsed:.1f}s, {input_tokens:,} input / {output_tokens:,} output tokens")
    return label, result.output, None


def missing_files(args):
    """Paths from the command line that don't exist, found before any model call is spent on them."""
    checks = [(image, tools.IMAGE_SUFFIXES, "image") for image in args.image or []]
    if args.video:
        checks.append((args.video, tools.VIDEO_SUFFIXES, "video"))
    checks += [(profile, {".json"}, "customer profile (.json)") for profile in args.profile or []]
    problems = []
    for path_text, suffixes, kind in checks:
        try:
            tools.resolve_path(path_text, suffixes, kind)
        except FileNotFoundError as error:
            problems.append(str(error))
    return problems


async def run(args):
    if problems := missing_files(args):
        print("\n".join(problems))
        return 2
    catalog = tools.load_catalog()
    agent = build_agent(args.model)

    def new_deps():
        return tools.AgentDeps(
            catalog=catalog,
            vision_model=args.vision_model,
            reasoning_effort=args.reasoning_effort,
            use_cache=not args.no_cache,
        )

    if args.image:
        out_path = args.out or IDENTIFY_OUT_PATH
        jobs = [
            run_request(
                agent,
                f"Check this photo for Campus Customs products and tell me which one, if you can: {image}",
                image,
                ProductIdentification,
                new_deps(),
                describe_identification,
            )
            for image in args.image
        ]
    else:
        out_path = args.out or AD_OUT_PATH
        jobs = [
            run_request(
                agent,
                "How effective would this ad video be at convincing this customer to shop at Campus Customs? "
                f"Video: {args.video}  Customer profile: {profile}",
                profile,
                AdEffectiveness,
                new_deps(),
                describe_ad_result,
            )
            for profile in args.profile
        ]

    # Photos (or profiles) are independent, so they are handled at the same time. For several profiles
    # the video itself is analysed only once and shared.
    outcomes = await asyncio.gather(*jobs)

    results = [result for _, result, _ in outcomes if result]
    failures = [(label, error) for label, _, error in outcomes if error]
    if results:
        save_results(results, out_path)
        print(f"\nSaved {len(results)} result(s) to {out_path}")
    for label, error in failures:
        print(f"FAILED {label}: {error}")
    return 1 if failures else 0


def parse_args():
    parser = argparse.ArgumentParser(description="Campus Customs agent")
    parser.add_argument(
        "--image", nargs="+", action="extend", help="photo(s) to check for Campus Customs products"
    )
    parser.add_argument("--video", help="ad video to judge (use with --profile)")
    parser.add_argument(
        "--profile", nargs="+", action="extend", help="customer profile JSON file(s) to judge the video for"
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="where to save the results (default: output/identify_product.json or output/ad_effectiveness.json)",
    )
    parser.add_argument("--model", choices=ALLOWED_MODELS, default=MODEL, help="model that runs the agent")
    parser.add_argument(
        "--vision-model", choices=ALLOWED_MODELS, default=MODEL, help="model for the steps inside the tools"
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=["default", "none", "minimal", "low", "medium", "high"],
        default="low",
        help="for the steps inside the tools; 'default' leaves it to the model",
    )
    parser.add_argument("--no-cache", action="store_true", help="analyse the video again even if it was analysed before")
    args = parser.parse_args()

    if args.image and (args.video or args.profile):
        parser.error("use either --image, or --video with --profile, not both")
    if not args.image and not (args.video and args.profile):
        parser.error("give --image PATH, or --video PATH together with --profile PATH")
    return args


if __name__ == "__main__":
    sys.exit(asyncio.run(run(parse_args())))
