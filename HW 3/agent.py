"""Campus Customs agent: the Pydantic AI entry point.

The agent reads a request, picks the ability that answers it, and returns that ability's structured
result. Its system prompt is the top part of prompts/prompt.md; the ability logic lives in tools.py.

Ability 1 (Problems 3-4): is a Campus Customs product in this photo, and which one?
    python agent.py --image "data/test_images/image_01_true.jpeg"
    python agent.py --image data/test_images/*.jpeg            (several photos at once)
    -> output/identify_product.json, a list with one ProductIdentification per photo

Ability 2 (Problem 5): how well would this ad video get this customer to shop at Campus Customs?
    python agent.py --video "data/videos/ad_humble.mp4" --profile "profiles/profile_student.json"
    (give several --profile files to judge the same video for each customer)
    -> output/ad_effectiveness.json, a list with one AdEffectiveness per video and profile

Every run also appends one record per agent loop iteration to output/audit_trail.json.

Results are merged into those files: a new result replaces the old one for the same photo (or the same
video and profile) and keeps the rest, so separate runs for the student and the parent end up side by side.
"""

import argparse
import asyncio
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic_ai import Agent, ModelRetry, RunContext, ToolOutput, UsageLimitExceeded
from pydantic_ai.messages import RetryPromptPart, TextPart, ThinkingPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.openai import OpenAIResponsesModelSettings
from pydantic_ai.usage import UsageLimits

import tools
from tools import ALLOWED_MODELS, MODEL, OUTPUT_DIR, build_agent_model, is_image_refused
from models import AdEffectiveness, AuditEntry, ProductIdentification


IDENTIFY_OUT_PATH = OUTPUT_DIR / "identify_product.json"
AD_OUT_PATH = OUTPUT_DIR / "ad_effectiveness.json"
AUDIT_PATH = OUTPUT_DIR / "audit_trail.json"

# The agent's loop: each iteration is one model call that may call a tool. A normal run takes 1
# (it calls an ability, whose result is the answer); a mistaken path adds one per retry.
MAX_AGENT_ITERATIONS = 4
SUMMARY_LENGTH = 300


# --- The agent's abilities (logic in tools.py) ---------------------------------------------------


async def identify_product(ctx: RunContext[tools.AgentDeps], reason: str, image_path: str) -> ProductIdentification:
    """Check a photo for Campus Customs products and say which one appears, if any.

    Args:
        reason: One sentence on why this ability answers the request (recorded in the audit trail).
        image_path: Path to the photo, exactly as given in the request.
    """
    try:
        photo = tools.resolve_image_path(image_path)
    except FileNotFoundError as error:
        raise ModelRetry(f"{error} Use the exact path from the request.")
    return await tools.identify_product(photo, ctx.deps)


async def judge_ad_effectiveness(
    ctx: RunContext[tools.AgentDeps], reason: str, video_path: str, profile_path: str
) -> AdEffectiveness:
    """Judge how effective an ad video would be at getting one customer to shop at Campus Customs.

    Args:
        reason: One sentence on why this ability answers the request (recorded in the audit trail).
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
        # Reasoning summaries are what the audit trail records as the agent's thoughts.
        model_settings=OpenAIResponsesModelSettings(max_tokens=2000, timeout=300.0, openai_reasoning_summary="auto"),
        retries=2,
    )


# --- Running requests ----------------------------------------------------------------------------


def result_key(row: dict):
    """What a result is about: one photo, or one video judged for one profile."""
    if "image_path" in row:
        return (row["image_path"],)
    return (row["video_path"], row["profile_path"])


def save_results(results: list, out_path: Path, result_type: type):
    """Merge the results into the JSON list at out_path and return how many entries it now holds.

    A result replaces an earlier one about the same photo (or the same video and profile) and leaves
    the others alone, so running the student and then the parent profile keeps both.
    """
    existing = []
    if out_path.exists():
        try:
            rows = json.loads(out_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            rows = []
        for row in rows if isinstance(rows, list) else []:
            try:
                existing.append(result_type.model_validate(row).model_dump())
            except ValueError:
                print(f"Dropping an old entry in {out_path.name} that no longer matches {result_type.__name__}.")

    merged = {result_key(row): row for row in existing}
    for result in results:
        row = result.model_dump()
        merged[result_key(row)] = row

    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [merged[key] for key in sorted(merged)]
    out_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(rows)


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


# --- Audit trail ---------------------------------------------------------------------------------

_audit_lock = asyncio.Lock()  # several runs can append at the same time


async def append_audit(entry: AuditEntry, path: Path | None = None):
    """Append one entry to the audit trail right away, so it survives a crash later in the run."""
    path = path or AUDIT_PATH
    async with _audit_lock:
        try:
            rows = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        except json.JSONDecodeError:
            path.rename(path.with_suffix(f".damaged-{int(time.time())}.json"))  # keep it; start a fresh trail
            rows = []
        rows.append(entry.model_dump())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def short(text: str, limit: int = SUMMARY_LENGTH):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def summarize_output(output):
    if isinstance(output, ProductIdentification):
        return short(describe_identification(output))
    if isinstance(output, AdEffectiveness):
        return short(describe_ad_result(output))
    return short(repr(output))


class RunAuditor:
    """Turns the agent's loop into AuditEntry records, one per iteration.

    An iteration is: the model responds (thoughts + a tool call), then the tool runs. Its result shows up
    either as the next request to the model (a tool return or a retry) or as the run's final output.
    """

    def __init__(self, request: str, model_name: str):
        self.run_id = uuid.uuid4().hex[:12]
        self.request = short(request)
        self.model_name = model_name
        self.iteration = 0
        self.pending = []  # (thoughts, tool call) from the latest model response, waiting for results

    def _entries(self, results: dict, stop_reason):
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        thoughts, calls = self.pending
        base = dict(run_id=self.run_id, request=self.request, iteration=self.iteration, time=now, model=self.model_name)
        if not calls:
            return [AuditEntry(**base, thoughts=thoughts, tool_name=None, arguments=None,
                               result_summary=results.get(None, "no tool called"), stop_reason=stop_reason)]
        return [
            AuditEntry(**base, thoughts=thoughts, tool_name=call.tool_name, arguments=call.args_as_dict(),
                       result_summary=results.get(call.tool_call_id, "no result"), stop_reason=stop_reason)
            for call in calls
        ]

    def model_responded(self, response):
        self.iteration += 1
        thoughts = [p.content for p in response.parts if isinstance(p, ThinkingPart) and p.content]
        thoughts += [p.content for p in response.parts if isinstance(p, TextPart) and p.content.strip()]
        calls = [p for p in response.parts if isinstance(p, ToolCallPart)]
        if not thoughts:
            # Portkey doesn't always return reasoning summaries, so each ability also takes a stated reason.
            thoughts = [f"(stated reason) {call.args_as_dict()['reason']}" for call in calls if call.args_as_dict().get("reason")]
        self.pending = ([short(t, 1000) for t in thoughts], calls)

    async def tools_answered(self, request):
        """The next request carries the results of the pending tool calls: the loop goes on."""
        if not self.pending:
            return
        results = {}
        for part in request.parts:
            if isinstance(part, ToolReturnPart):
                results[part.tool_call_id] = short(part.content)
            elif isinstance(part, RetryPromptPart):
                results[part.tool_call_id] = short(f"rejected, model asked to retry: {part.model_response()}")
        for entry in self._entries(results, None):
            await append_audit(entry)
        self.pending = []

    async def finished(self, output=None, error: str | None = None):
        if not self.pending:  # the run failed before the model answered at all
            self.iteration += 1
            self.pending = ([], [])
        _, calls = self.pending
        summary = summarize_output(output) if output is not None else short(error or "")
        results = {call.tool_call_id: summary for call in calls} | {None: summary}
        stop = "final answer" if error is None else error if error == "iteration limit" else f"error: {short(error, 200)}"
        for entry in self._entries(results, stop):
            await append_audit(entry)
        self.pending = []


async def run_request(agent: Agent, request: str, label: str, expected_type: type, deps: tools.AgentDeps, describe):
    """Run the agent on one request, auditing every loop iteration. Each request has its own deps."""
    auditor = RunAuditor(request, agent.model.model_name)
    started = time.perf_counter()
    try:
        async with agent.iter(request, deps=deps, usage_limits=UsageLimits(request_limit=MAX_AGENT_ITERATIONS)) as agent_run:
            async for node in agent_run:
                if Agent.is_call_tools_node(node):
                    auditor.model_responded(node.model_response)
                elif Agent.is_model_request_node(node):
                    await auditor.tools_answered(node.request)
            result = agent_run.result
    except UsageLimitExceeded:
        await auditor.finished(error="iteration limit")
        return label, None, f"stopped after {MAX_AGENT_ITERATIONS} loop iterations without an answer"
    except Exception as error:
        refused = is_image_refused(error)
        message = (
            "the model provider's content filter refused an image, so it could not be checked"
            if refused
            else f"{type(error).__name__}: {error}"
        )
        await auditor.finished(error=message)
        return label, None, message

    await auditor.finished(output=result.output)
    if not isinstance(result.output, expected_type):
        return label, None, f"the agent used the wrong ability and returned {type(result.output).__name__}"

    elapsed = time.perf_counter() - started
    input_tokens = deps.input_tokens + result.usage.input_tokens
    output_tokens = deps.output_tokens + result.usage.output_tokens
    print(f"{describe(result.output)}, {elapsed:.1f}s, {input_tokens:,} input / {output_tokens:,} output tokens")
    return label, result.output, None


def check_inputs(args):
    """Problems with the command-line files, found before any model call is spent on them:
    paths that don't exist, and profiles that don't match CustomerProfile."""
    checks = [(image, tools.IMAGE_SUFFIXES, "image") for image in args.image or []]
    if args.video:
        checks.append((args.video, tools.VIDEO_SUFFIXES, "video"))
    checks += [(profile, {".json"}, "customer profile (.json)") for profile in args.profile or []]
    problems = []
    for path_text, suffixes, kind in checks:
        try:
            path = tools.resolve_path(path_text, suffixes, kind)
            if suffixes == {".json"}:
                tools.load_profile(path)
        except (FileNotFoundError, ValueError) as error:
            problems.append(str(error))
    return problems


async def run(args):
    if problems := check_inputs(args):
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
        out_path, result_type = args.out or IDENTIFY_OUT_PATH, ProductIdentification
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
        out_path, result_type = args.out or AD_OUT_PATH, AdEffectiveness
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
        total = save_results(results, out_path, result_type)
        print(f"\nSaved {len(results)} result(s) to {out_path} ({total} in the file)")
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
