"""Sales research agent for BuyScout.ai.

Two jobs, one agent loop, chosen from the human's own words:
  * profile  — crawl one company's site and return a grounded company profile
  * prospect — read the seller profile, search the web for customer targets,
               qualify them, find contacts, and draft outreach emails (never sent)

Every run appends its agent loop (iterations, thoughts, tool calls, results) to
output/audit_log.json.

Usage:
    python sales_agent.py "build me a profile of buyscout.ai for a cold call"
    python sales_agent.py "Find 3 good customer targets for this company and draft outreach emails." \
        --profile assets/company_profile.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

from dotenv import load_dotenv
from openai import AsyncOpenAI
from playwright.async_api import Page, async_playwright
from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext, UsageLimitExceeded, capture_run_messages
from pydantic_ai.capabilities import WebSearch
from pydantic_ai.messages import (
    ModelResponse,
    NativeToolCallPart,
    NativeToolReturnPart,
    RetryPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

ROOT = Path(__file__).resolve().parent
PROMPT_PATH = ROOT / "prompts" / "sales_agent.md"
OUTPUT_DIR = ROOT / "output"
AUDIT_LOG_PATH = OUTPUT_DIR / "audit_log.json"
PROFILE_OUT_PATH = OUTPUT_DIR / "company_profile.json"
TARGETS_PATH = OUTPUT_DIR / "targets.json"
EMAILS_PATH = OUTPUT_DIR / "emails.json"

MODEL_NAME = "gpt-5.6"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

# --- cost harness: every knob below caps what a single run can spend ---
BUDGETS = {
    # one site, shallow read
    "profile": {"max_pages": 8, "per_host": 8, "chars": 40_000, "requests": 14, "tool_calls": 12, "searches": 3, "timeout": 300},
    # many sites, so pages are rationed per host and searches are capped
    "prospect": {"max_pages": 22, "per_host": 4, "chars": 90_000, "requests": 40, "tool_calls": 60, "searches": 8, "timeout": 720},
}
PAGE_CHAR_LIMIT = 6_000  # chars handed back from one page
MAX_LINKS = 40
TOTAL_TOKENS_LIMIT = 400_000
MAX_OUTPUT_TOKENS = 8_000
NAV_TIMEOUT_MS = 20_000
BLOCKED_RESOURCE_TYPES = {"image", "media", "font", "stylesheet"}
RESULT_SUMMARY_CHARS = 400
# Marketplaces crowd out the brand sites we actually want to reach.
SEARCH_BLOCKED_DOMAINS = ["amazon.com", "ebay.com", "walmart.com", "aliexpress.com", "alibaba.com", "temu.com"]
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
PROSPECT_HINTS = ("customer", "target", "prospect", "lead", "outreach", "email", "who should we sell")
# Paths worth their page load, in priority order, so the link cap keeps the good ones.
LINK_PRIORITY = (
    "contact",
    "about",
    "customer",
    "case-stud",
    "stories",
    "pricing",
    "wholesale",
    "press",
    "team",
    "product",
    "feature",
    "solution",
    "industr",
    "integration",
    "platform",
    "career",
    "job",
    "faq",
    "blog",
    "docs",
)
SKIP_SUFFIXES = (".pdf", ".jpg", ".jpeg", ".png", ".svg", ".gif", ".zip", ".mp4", ".webp", ".css", ".js")
SKIP_PATH_HINTS = ("/login", "/signin", "/sign-in", "/signup", "/cart", "/checkout", "/account", "/privacy", "/terms", "/legal", "/policies/")
# Ecommerce platform fingerprints: the seller's product is Shopify-only, so this is a hard qualifier.
PLATFORM_SIGNALS = {
    "Shopify": ["window.Shopify", "cdn.shopify.com", "/cdn/shop/", "shopifycloud", "myshopify.com"],
    "WooCommerce": ["woocommerce", "wp-content/plugins/woo"],
    "BigCommerce": ["bigcommerce.com", "cdn11.bigcommerce"],
    "Squarespace": ["squarespace.com", "static1.squarespace"],
    "Wix": ["wixstatic.com", "parastorage.com"],
    "Magento": ["mage/cookies", "magento"],
    "Salesforce Commerce": ["demandware.static", "/on/demandware"],
}
PLATFORM_JS = """() => {
  const html = document.documentElement.outerHTML.slice(0, 400000).toLowerCase();
  const hits = [];
  if (window.Shopify) hits.push('window.Shopify');
  return {html_sample: html, shopify_global: !!window.Shopify, hits: hits};
}"""

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
EMAIL_JUNK = ("example.com", "example.org", "sentry.io", "wixpress.com", "domain.com", "yourstore", "email.com", "sentry-next", ".png", ".jpg", ".webp")


class CompanyProfile(BaseModel):
    """Profile of the company the human asked about, grounded in its own website."""

    company_name: str
    website: str
    one_line_pitch: str = Field(description="What they do, in one plain sentence.")
    what_they_offer: list[str] = Field(description="Products, features, channels.")
    target_customers: list[str] = Field(description="Customer types and segments they sell to.")
    named_customers: list[str] = Field(default_factory=list, description="Only customers the site names.")
    pricing_notes: str | None = Field(default=None, description="Pricing model and tiers, if published.")
    proof_points: list[str] = Field(default_factory=list, description="Claimed metrics, reviews, traction — labelled as claims.")
    likely_direction: list[str] = Field(default_factory=list, description="Inferred future direction, labelled as inference.")
    sales_angles: list[str] = Field(default_factory=list, description="Concrete hooks for a BuyScout.ai sales conversation.")
    open_questions: list[str] = Field(default_factory=list, description="What the website could not answer.")
    sources: list[str] = Field(default_factory=list, description="URLs actually read.")


class ProfileRun(BaseModel):
    """Answer for a profiling request: the agent's reading of it, plus the profile."""

    interpreted_request: str = Field(description="What the human actually wants, and why.")
    target_is_buyscout: bool = Field(description="True when the profiled company is BuyScout.ai itself.")
    company_profile: CompanyProfile
    summary_for_human: str = Field(description="Two to four sentences answering the request directly.")


class Contact(BaseModel):
    """A business contact found on the target's own website."""

    name: str | None = Field(default=None, description="Person's name, if published.")
    role: str | None = Field(default=None, description="Job title or team, e.g. 'founder', 'wholesale'.")
    email: str | None = Field(default=None, description="Email exactly as published on the site.")
    source_url: str = Field(description="Page the contact was found on.")


class OutreachEmail(BaseModel):
    """A drafted outreach email. Never sent by this agent."""

    to: str | None = Field(description="Best email found on their site, or null if none published.")
    subject: str = Field(description="Under 60 characters, specific to this company.")
    body: str = Field(description="120 words max, plain text, one clear ask.")
    personalization_notes: list[str] = Field(description="Facts from their site the email refers to.")


class CustomerTarget(BaseModel):
    """A qualified prospect for the seller, with evidence and a drafted email."""

    company_name: str
    website: str
    what_they_sell: str
    why_good_fit: str = Field(description="Why this company specifically needs what the seller offers.")
    fit_signals: list[str] = Field(description="Evidence from their site, e.g. 'Shopify storefront', '400+ SKUs'.")
    size_estimate: str = Field(description="Rough size read, e.g. 'small DTC brand, single warehouse'.")
    is_competitor: bool = Field(description="True if they sell a competing product to the seller's.")
    is_household_name: bool = Field(description="True if a famous enterprise brand the seller cannot realistically reach.")
    disqualifiers_checked: list[str] = Field(description="Checks performed, e.g. 'not a competitor', 'not an agency'.")
    contacts: list[Contact] = Field(default_factory=list)
    best_email: str | None = Field(default=None, description="The email the draft should go to, if any was published.")
    evidence_urls: list[str] = Field(description="Pages on their site you actually read.")
    outreach_email: OutreachEmail


class ProspectingRun(BaseModel):
    """Answer for a find-customers request: qualified targets plus drafted emails."""

    interpreted_request: str = Field(description="What the human actually wants, and why.")
    seller_summary: str = Field(description="One sentence: who you are prospecting for, from the seller profile.")
    ideal_customer_profile: list[str] = Field(description="The screen you applied when judging candidates.")
    targets: list[CustomerTarget]
    rejected_candidates: list[str] = Field(default_factory=list, description="Candidate + one-line reason it failed the screen.")
    summary_for_human: str = Field(description="Two to four sentences answering the request directly.")
    notes: list[str] = Field(default_factory=list, description="Caveats, e.g. no published email, budget ran out.")


@dataclass
class Crawler:
    """Playwright page plus the per-run scrape budget, cache, and seller context."""

    page: Page
    mode: str = "profile"
    max_pages: int = 8
    max_pages_per_host: int = 8
    page_char_limit: int = PAGE_CHAR_LIMIT
    total_char_budget: int = 40_000
    allowed_host: str | None = None  # profile mode locks to one site; prospect mode roams
    seller_profile: dict | None = None
    pages_loaded: int = 0
    cache_hits: int = 0
    chars_returned: int = 0
    host_counts: dict[str, int] = field(default_factory=dict)
    text_cache: dict[str, str] = field(default_factory=dict)
    link_cache: dict[str, list[str]] = field(default_factory=dict)
    email_cache: dict[str, list[str]] = field(default_factory=dict)
    platform_cache: dict[str, str] = field(default_factory=dict)
    fetched_urls: list[str] = field(default_factory=list)
    # One shared page, so parallel tool calls must navigate one at a time.
    nav_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def seller_host(self) -> str | None:
        site = (self.seller_profile or {}).get("website")
        return host_of(normalize_url(site)) if site else None

    def budget_note(self) -> str:
        return (
            f"[budget] page loads {self.pages_loaded}/{self.max_pages} · "
            f"text {self.chars_returned // 1000}k/{self.total_char_budget // 1000}k chars"
        )

    def spend_check(self, host: str) -> None:
        if self.pages_loaded >= self.max_pages:
            raise ModelRetry(
                f"Page budget spent ({self.max_pages} loads). Stop researching and write your answer "
                f"from the pages you already read: {', '.join(self.fetched_urls)}"
            )
        if self.chars_returned >= self.total_char_budget:
            raise ModelRetry("Text budget spent. Stop researching and write your answer from what you already read.")
        used = self.host_counts.get(host, 0)
        if used >= self.max_pages_per_host:
            raise ModelRetry(
                f"Already read {used} pages on {host}, which is this run's per-site cap. "
                "Move on to another company or write your answer."
            )


def normalize_url(raw: str) -> str:
    candidate = raw.strip()
    if not candidate:
        raise ModelRetry("Empty url. Pass a full page url, e.g. https://example.com/pricing")
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parts = urlparse(candidate)
    if parts.scheme not in ("http", "https"):
        raise ModelRetry(f"Only http(s) urls can be fetched, got {parts.scheme!r}")
    path = parts.path.rstrip("/") or "/"
    return urlunparse((parts.scheme, parts.netloc.lower(), path, "", parts.query, ""))


def host_of(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def same_site(host: str, allowed: str) -> bool:
    return host == allowed or host.endswith(f".{allowed}")


def clean_text(raw: str, limit: int) -> str:
    """Drop repeated nav/footer lines and blank runs, then truncate."""
    seen: set[str] = set()
    lines: list[str] = []
    for line in raw.splitlines():
        line = " ".join(line.split())
        if not line:
            continue
        key = line.lower()
        if len(line) < 60 and key in seen:
            continue
        seen.add(key)
        lines.append(line)
    text = "\n".join(lines)
    if len(text) > limit:
        text = text[:limit] + f"\n[truncated at {limit} chars]"
    return text


def extract_emails(text: str, hrefs: list[str]) -> list[str]:
    """Pull published addresses off the page: mailto links are the reliable ones."""
    found: list[str] = []
    for href in hrefs:
        if href and href.lower().startswith("mailto:"):
            address = href[7:].split("?")[0].strip()
            if EMAIL_RE.fullmatch(address):
                found.append(address)
    found.extend(EMAIL_RE.findall(text))
    clean: list[str] = []
    for address in found:
        lowered = address.lower()
        if any(junk in lowered for junk in EMAIL_JUNK):
            continue
        if lowered not in clean:
            clean.append(lowered)
    return clean[:8]


def detect_platform(html: str, shopify_global: bool) -> str:
    """Name the ecommerce platform from markup fingerprints, so fit is checked not guessed."""
    found: list[str] = []
    for platform, needles in PLATFORM_SIGNALS.items():
        matched = [n for n in needles if n.lower() in html]
        if platform == "Shopify" and shopify_global and "window.Shopify" not in matched:
            matched.insert(0, "window.Shopify")
        if matched:
            found.append(f"{platform} ({', '.join(matched[:2])})")
    return "; ".join(found) if found else "none detected"


def rank_links(links: list[str]) -> list[str]:
    def score(url: str) -> int:
        path = urlparse(url).path.lower()
        for index, keyword in enumerate(LINK_PRIORITY):
            if keyword in path:
                return index
        return len(LINK_PRIORITY)

    return sorted(links, key=score)


async def block_heavy_requests(route) -> None:
    if route.request.resource_type in BLOCKED_RESOURCE_TYPES:
        await route.abort()
    else:
        await route.continue_()


async def load(crawler: Crawler, url: str) -> tuple[str, list[str], list[str], str]:
    """Navigate once, cache the text, internal links, emails, and platform of a page."""
    url = normalize_url(url)
    host = host_of(url)

    if crawler.mode == "profile":
        if crawler.allowed_host is None:
            crawler.allowed_host = host
        elif not same_site(host, crawler.allowed_host):
            raise ModelRetry(
                f"Off-target domain {host!r}. This profiling run is locked to {crawler.allowed_host!r}."
            )

    if url in crawler.text_cache:
        crawler.cache_hits += 1
        return (
            crawler.text_cache[url],
            crawler.link_cache.get(url, []),
            crawler.email_cache.get(url, []),
            crawler.platform_cache.get(url, "none detected"),
        )

    async with crawler.nav_lock:
        if url in crawler.text_cache:  # filled by a parallel call while we waited
            crawler.cache_hits += 1
            return crawler.text_cache[url], crawler.link_cache.get(url, []), crawler.email_cache.get(url, [])

        crawler.spend_check(host)

        try:
            response = await crawler.page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        except Exception as exc:  # playwright raises many nav error types
            reason = str(exc).splitlines()[0][:120] if str(exc) else type(exc).__name__
            raise ModelRetry(f"Could not load {url}: {reason}. Try another url.") from exc

        crawler.pages_loaded += 1
        crawler.host_counts[host] = crawler.host_counts.get(host, 0) + 1
        crawler.fetched_urls.append(url)

        if response is not None and response.status >= 400:
            raise ModelRetry(f"{url} returned HTTP {response.status}. Try another url.")

        try:
            await crawler.page.wait_for_load_state("networkidle", timeout=4_000)
        except Exception:
            pass

        raw_text = await crawler.page.inner_text("body")
        hrefs = await crawler.page.eval_on_selector_all(
            "a[href]", "els => els.map(e => e.getAttribute('href'))"
        )
        fingerprint = await crawler.page.evaluate(PLATFORM_JS)

    platform = detect_platform(fingerprint["html_sample"], fingerprint["shopify_global"])
    text = clean_text(raw_text, crawler.page_char_limit)
    emails = extract_emails(text, hrefs)
    internal: list[str] = []
    for href in hrefs:
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        try:
            link = normalize_url(urljoin(url, href))
        except ModelRetry:
            continue
        path = urlparse(link).path.lower()
        if not same_site(host_of(link), host):
            continue
        if path.endswith(SKIP_SUFFIXES) or any(hint in path for hint in SKIP_PATH_HINTS):
            continue
        if link not in internal and link != url:
            internal.append(link)

    links = rank_links(internal)[:MAX_LINKS]
    crawler.text_cache[url] = text
    crawler.link_cache[url] = links
    crawler.email_cache[url] = emails
    crawler.platform_cache[url] = platform
    return text, links, emails, platform


def load_prompt() -> str:
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(f"Prompt not found: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_model() -> OpenAIResponsesModel:
    for candidate in (ROOT / ".env", ROOT.parent / ".env"):
        if candidate.exists():
            load_dotenv(candidate)
    api_key = os.getenv("PORTKEY_API_KEY")
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY is not set. Add it to the workspace .env file.")
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=PORTKEY_BASE_URL,
        default_headers={"x-portkey-api-key": api_key, "x-portkey-provider": "openai"},
    )
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


agent = Agent(
    instructions=load_prompt(),
    deps_type=Crawler,
    output_type=[ProfileRun, ProspectingRun],
    model_settings=OpenAIResponsesModelSettings(
        max_tokens=MAX_OUTPUT_TOKENS,
        timeout=180.0,
        # Reasoning summaries are what the audit log records as the agent's thoughts.
        openai_reasoning_summary="auto",
    ),
    retries=2,
)


@agent.instructions
def seller_context(ctx: RunContext[Crawler]) -> str:
    """Put the seller profile in front of the model instead of spending a tool call on it."""
    profile = ctx.deps.seller_profile
    if not profile:
        return ""
    keep = (
        "company_name",
        "website",
        "one_line_pitch",
        "what_they_offer",
        "target_customers",
        "named_customers",
        "pricing_notes",
        "proof_points",
        "sales_angles",
    )
    digest = {}
    for key in keep:
        value = profile.get(key)
        if isinstance(value, list):
            value = value[:8]
        if value:
            digest[key] = value
    return (
        "## Seller profile (the company you prospect for)\n"
        "This is the company whose product you are selling. Judge every candidate against it.\n\n"
        f"{json.dumps(digest, indent=2)}"
    )


@agent.tool
async def list_links(ctx: RunContext[Crawler], url: str) -> str:
    """Read a page and list its internal links. Use this first on a site to plan which pages to fetch."""
    text, links, emails, platform = await load(ctx.deps, url)
    ctx.deps.chars_returned += len(text)
    listed = "\n".join(links) if links else "(no internal links found)"
    found = ", ".join(emails) if emails else "(none on this page)"
    return (
        f"URL: {url}\n\nPAGE TEXT:\n{text}\n\nPLATFORM SIGNALS: {platform}\n\nEMAILS FOUND: {found}\n\n"
        f"INTERNAL LINKS (ranked):\n{listed}\n\n{ctx.deps.budget_note()}"
    )


@agent.tool
async def fetch_page(ctx: RunContext[Crawler], url: str) -> str:
    """Read one page: its text, the ecommerce platform it runs on, and any emails published on it."""
    text, _, emails, platform = await load(ctx.deps, url)
    ctx.deps.chars_returned += len(text)
    found = ", ".join(emails) if emails else "(none on this page)"
    return (
        f"URL: {url}\n\nPAGE TEXT:\n{text}\n\nPLATFORM SIGNALS: {platform}\n\n"
        f"EMAILS FOUND: {found}\n\n{ctx.deps.budget_note()}"
    )


@agent.output_validator
def enforce_qualification(ctx: RunContext[Crawler], output: ProfileRun | ProspectingRun) -> ProfileRun | ProspectingRun:
    """The model does the judging; this makes its own screen binding."""
    if isinstance(output, ProfileRun):
        return output

    if not output.targets:
        raise ModelRetry("No targets returned. Search again and qualify at least one real company.")

    seller_host = ctx.deps.seller_host
    seen: set[str] = set()
    for target in output.targets:
        label = target.company_name
        host = host_of(normalize_url(target.website))
        if target.is_competitor:
            raise ModelRetry(f"{label} is flagged as a competitor. Drop it and qualify a replacement.")
        if target.is_household_name:
            raise ModelRetry(f"{label} is flagged as a household name. Drop it and qualify a reachable company.")
        if seller_host and same_site(host, seller_host):
            raise ModelRetry(f"{label} is the seller's own site. Drop it and qualify a real prospect.")
        if host in seen:
            raise ModelRetry(f"{label} is a duplicate of another target. Replace it with a different company.")
        seen.add(host)
        if not target.evidence_urls:
            raise ModelRetry(f"{label} has no evidence_urls. Read pages on their site before proposing them.")
        if not any(same_site(host_of(normalize_url(url)), host) for url in target.evidence_urls):
            raise ModelRetry(f"{label}'s evidence_urls are not on {host}. Read their own site, not third-party pages.")
        if len(target.outreach_email.body.split()) < 25:
            raise ModelRetry(f"The email for {label} is too thin. Write a real 60-120 word draft.")
    return output


def summarize(content: object) -> str:
    text = content if isinstance(content, str) else json.dumps(content, default=str)
    text = " ".join(text.split())
    if len(text) > RESULT_SUMMARY_CHARS:
        return f"{text[:RESULT_SUMMARY_CHARS]}... [{len(text)} chars total]"
    return text


def tool_args(part: ToolCallPart | NativeToolCallPart) -> object:
    try:
        return part.args_as_dict()
    except Exception:
        return part.args


def build_iterations(messages: list) -> list[dict]:
    """Rebuild the agent loop: one iteration per model response, with its thoughts and tool calls."""
    results: dict[str, dict] = {}
    for message in messages:
        parts = getattr(message, "parts", [])
        for part in parts:
            if isinstance(part, (ToolReturnPart, NativeToolReturnPart)):
                results[part.tool_call_id] = {"outcome": "return", "result_summary": summarize(part.content)}
            elif isinstance(part, RetryPromptPart):
                results[part.tool_call_id] = {"outcome": "retry", "result_summary": summarize(part.content)}

    iterations: list[dict] = []
    for message in messages:
        if not isinstance(message, ModelResponse):
            continue
        thoughts: list[dict] = []
        calls: list[dict] = []
        for part in message.parts:
            if isinstance(part, ThinkingPart) and part.content:
                thoughts.append({"kind": "thinking", "text": part.content})
            elif isinstance(part, TextPart) and part.content.strip():
                thoughts.append({"kind": "text", "text": part.content.strip()})
            elif isinstance(part, (ToolCallPart, NativeToolCallPart)):
                call = {
                    "tool_name": part.tool_name,
                    "tool_kind": "native" if isinstance(part, NativeToolCallPart) else "local",
                    "arguments": tool_args(part),
                    "tool_call_id": part.tool_call_id,
                }
                call.update(results.get(part.tool_call_id, {"outcome": "no_result_recorded", "result_summary": None}))
                calls.append(call)
        iterations.append(
            {
                "iteration": len(iterations) + 1,
                "timestamp_utc": message.timestamp.isoformat() if message.timestamp else None,
                "thoughts": thoughts,
                "tool_calls": calls,
                "usage": {
                    "input_tokens": message.usage.input_tokens,
                    "output_tokens": message.usage.output_tokens,
                },
                "finish_reason": message.finish_reason,
            }
        )
    return iterations


def write_json(path: Path, payload: object) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def write_audit_log(entry: dict) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    runs: list = []
    if AUDIT_LOG_PATH.exists():
        try:
            existing = json.loads(AUDIT_LOG_PATH.read_text(encoding="utf-8"))
            if isinstance(existing, list):
                runs = existing
        except json.JSONDecodeError:
            runs = []
    runs.append(entry)
    return write_json(AUDIT_LOG_PATH, runs)


def write_results(output: ProfileRun | ProspectingRun, run_id: str, query: str, seller: dict | None) -> list[str]:
    """Persist the run's deliverables: profile, or targets plus drafted emails."""
    stamp = datetime.now().isoformat(timespec="seconds")
    if isinstance(output, ProfileRun):
        write_json(
            PROFILE_OUT_PATH,
            {"run_id": run_id, "generated_at": stamp, "query": query, **output.company_profile.model_dump()},
        )
        return [str(PROFILE_OUT_PATH)]

    seller_stub = {
        "name": (seller or {}).get("company_name"),
        "website": (seller or {}).get("website"),
    }
    targets = []
    emails = []
    for target in output.targets:
        record = target.model_dump()
        draft = record.pop("outreach_email")
        targets.append({"run_id": run_id, "generated_at": stamp, **record})
        emails.append(
            {
                "run_id": run_id,
                "generated_at": stamp,
                "status": "draft_not_sent",
                "company_name": target.company_name,
                "website": target.website,
                "to": draft["to"],
                "subject": draft["subject"],
                "body": draft["body"],
                "personalization_notes": draft["personalization_notes"],
                "contacts": record["contacts"],
            }
        )
    write_json(
        TARGETS_PATH,
        {
            "run_id": run_id,
            "generated_at": stamp,
            "query": query,
            "seller": seller_stub,
            "ideal_customer_profile": output.ideal_customer_profile,
            "rejected_candidates": output.rejected_candidates,
            "targets": targets,
        },
    )
    write_json(
        EMAILS_PATH,
        {
            "run_id": run_id,
            "generated_at": stamp,
            "status": "drafts_only_nothing_sent",
            "seller": seller_stub,
            "emails": emails,
        },
    )
    return [str(TARGETS_PATH), str(EMAILS_PATH)]


def load_seller_profile(raw_path: str) -> tuple[dict, str]:
    path = Path(raw_path)
    for candidate in (path, Path.cwd() / path, ROOT / path):
        if candidate.exists():
            data = json.loads(candidate.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError(f"{candidate} must hold a JSON object")
            return data, str(candidate.resolve())
    raise FileNotFoundError(f"Seller profile not found: {raw_path}")


def pick_mode(query: str, has_profile: bool) -> str:
    lowered = query.lower()
    if has_profile or any(hint in lowered for hint in PROSPECT_HINTS):
        return "prospect"
    return "profile"


async def run_agent(
    query: str,
    profile_path: str | None,
    max_pages: int | None,
    site: str | None,
    run_timeout: int | None = None,
) -> dict:
    started = datetime.now()
    started_monotonic = time.monotonic()
    stop_reason = "completed"
    error: str | None = None
    output: ProfileRun | ProspectingRun | None = None
    usage = None
    files_written: list[str] = []

    seller_profile: dict | None = None
    resolved_profile_path: str | None = None
    if profile_path:
        seller_profile, resolved_profile_path = load_seller_profile(profile_path)

    mode = pick_mode(query, bool(profile_path))
    budget = BUDGETS[mode]
    timeout_seconds = run_timeout or budget["timeout"]
    run_id = started.strftime("%Y%m%dT%H%M%S")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(user_agent=USER_AGENT)
        page = await context.new_page()
        await page.route("**/*", block_heavy_requests)
        crawler = Crawler(
            page=page,
            mode=mode,
            max_pages=max_pages or budget["max_pages"],
            max_pages_per_host=budget["per_host"],
            total_char_budget=budget["chars"],
            seller_profile=seller_profile,
        )
        if site:
            crawler.allowed_host = host_of(normalize_url(site))

        with capture_run_messages() as messages:
            try:
                result = await asyncio.wait_for(
                    agent.run(
                        query,
                        model=build_model(),
                        deps=crawler,
                        capabilities=[
                            WebSearch(
                                local="duckduckgo",
                                max_uses=budget["searches"],
                                search_context_size="low",
                                blocked_domains=SEARCH_BLOCKED_DOMAINS,
                            )
                        ],
                        usage_limits=UsageLimits(
                            request_limit=budget["requests"],
                            tool_calls_limit=budget["tool_calls"],
                            total_tokens_limit=TOTAL_TOKENS_LIMIT,
                        ),
                    ),
                    timeout=timeout_seconds,
                )
                output = result.output
                usage = result.usage
            except UsageLimitExceeded as exc:
                stop_reason = "usage_limit_exceeded"
                error = str(exc)
            except (TimeoutError, asyncio.TimeoutError):
                stop_reason = "timeout"
                error = f"run exceeded its {timeout_seconds}s wall clock and was stopped"
            except (asyncio.CancelledError, KeyboardInterrupt):
                stop_reason = "cancelled"
                error = "run was interrupted before it finished"
            except Exception as exc:
                stop_reason = f"error:{type(exc).__name__}"
                error = str(exc)
            finally:
                await context.close()
                await browser.close()

    if output is not None:
        files_written = write_results(output, run_id, query, seller_profile)

    finished = datetime.now()
    searches = sum(
        1
        for message in messages
        for part in getattr(message, "parts", [])
        if isinstance(part, NativeToolCallPart)
    )
    entry = {
        "run_id": run_id,
        "query": query,
        "mode": mode,
        "model": MODEL_NAME,
        "date": started.strftime("%Y-%m-%d"),
        "time": started.strftime("%H:%M:%S"),
        "started_at_local": started.isoformat(timespec="seconds"),
        "started_at_utc": started.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "finished_at_local": finished.isoformat(timespec="seconds"),
        "duration_seconds": round(time.monotonic() - started_monotonic, 2),
        "stop_reason": stop_reason,
        "error": error,
        "seller_profile_path": resolved_profile_path,
        "seller": (seller_profile or {}).get("company_name"),
        "iterations": build_iterations(list(messages)),
        "usage": {
            "requests": usage.requests if usage else None,
            "tool_calls": usage.tool_calls if usage else None,
            "input_tokens": usage.input_tokens if usage else None,
            "output_tokens": usage.output_tokens if usage else None,
            "cache_read_tokens": usage.cache_read_tokens if usage else None,
        },
        "cost_controls": {
            "limits": {
                "mode": mode,
                "max_pages": crawler.max_pages,
                "max_pages_per_host": crawler.max_pages_per_host,
                "page_char_limit": crawler.page_char_limit,
                "total_char_budget": crawler.total_char_budget,
                "request_limit": budget["requests"],
                "tool_calls_limit": budget["tool_calls"],
                "max_searches": budget["searches"],
                "timeout_seconds": timeout_seconds,
                "total_tokens_limit": TOTAL_TOKENS_LIMIT,
                "max_output_tokens": MAX_OUTPUT_TOKENS,
                "blocked_resource_types": sorted(BLOCKED_RESOURCE_TYPES),
                "search_blocked_domains": SEARCH_BLOCKED_DOMAINS,
            },
            "spent": {
                "pages_loaded": crawler.pages_loaded,
                "pages_per_host": crawler.host_counts,
                "chars_returned": crawler.chars_returned,
                "cache_hits": crawler.cache_hits,
                "web_searches": searches,
                "locked_host": crawler.allowed_host,
            },
        },
        "pages_read": crawler.fetched_urls,
        "files_written": files_written,
        "output": output.model_dump() if output else None,
    }
    entry["iteration_count"] = len(entry["iterations"])
    write_audit_log(entry)
    return entry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Profile a company, or find customer targets and draft outreach.")
    parser.add_argument("query", help="Free-text request, e.g. 'Find 3 good customer targets for this company'")
    parser.add_argument("--profile", default=None, help="Path to the seller's company profile JSON")
    parser.add_argument("--max-pages", type=int, default=None, help="Override the page load budget")
    parser.add_argument("--site", default=None, help="Lock a profiling crawl to this domain")
    parser.add_argument("--timeout", type=int, default=None, help="Wall-clock seconds before the run is stopped")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    entry = asyncio.run(run_agent(args.query, args.profile, args.max_pages, args.site, args.timeout))

    spent = entry["cost_controls"]["spent"]
    usage = entry["usage"]
    print(f"\nmode: {entry['mode']} · stop reason: {entry['stop_reason']}")
    if entry["error"]:
        print(f"error: {entry['error']}")
    print(
        f"iterations: {entry['iteration_count']} · pages: {spent['pages_loaded']}/{entry['cost_controls']['limits']['max_pages']} · "
        f"searches: {spent['web_searches']} · tokens in/out: {usage['input_tokens']}/{usage['output_tokens']} · "
        f"{entry['duration_seconds']}s"
    )

    output = entry["output"]
    if output and "targets" in output:
        print(f"\nrequest read as: {output['interpreted_request']}")
        print(f"\n{output['summary_for_human']}")
        for target in output["targets"]:
            email = target["outreach_email"]
            print(f"\n--- {target['company_name']} — {target['website']}")
            print(f"    sells: {target['what_they_sell']}")
            print(f"    fit:   {target['why_good_fit']}")
            print(f"    email: {target['best_email'] or '(none published)'}")
            print(f"    subj:  {email['subject']}")
        if output["rejected_candidates"]:
            print("\nrejected:")
            for reason in output["rejected_candidates"]:
                print(f"  - {reason}")
    elif output:
        profile = output["company_profile"]
        print(f"\nrequest read as: {output['interpreted_request']}")
        print(f"\n{profile['company_name']} — {profile['one_line_pitch']}")
        print(f"\n{output['summary_for_human']}")

    for path in entry["files_written"]:
        print(f"\nwrote: {path}")
    print(f"audit log: {AUDIT_LOG_PATH}")


if __name__ == "__main__":
    main()
