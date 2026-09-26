"""Shared Portkey/OpenAI setup for Homework 3.

Every HW 3 script gets its Portkey client, model names and image helpers from here, so routing stays in one place.
Run this file directly to check the connection:  python portkey_client.py
"""

import io
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import APIConnectionError, AsyncOpenAI, AuthenticationError, OpenAI
from PIL import Image
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
PROMPTS_DIR = ROOT / "prompts"

PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
# Allowed for HW 3. The course budget assumes luna; use a smarter one only for hard vision/agent steps.
ALLOWED_MODELS = ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol", "gpt-6-astra")
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

# Keep pydantic-ai's first-run banner out of script output.
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")


def load_environment():
    for candidate in [ROOT / ".env", ROOT.parent / ".env"]:
        if candidate.exists():
            load_dotenv(candidate)

    api_key = os.getenv("PORTKEY_API_KEY")
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY is not set. Add it to the workspace .env file.")

    return api_key


def build_client():
    api_key = load_environment()
    return OpenAI(
        api_key=api_key,
        base_url=PORTKEY_BASE_URL,
        default_headers={
            "x-portkey-api-key": api_key,
            "x-portkey-provider": "openai",
        },
    )


def build_agent_model(model_name: str = MODEL, max_retries: int = 3, api: str = "responses"):
    """Pydantic AI model routed through Portkey, for scripts that run an Agent.

    One AsyncOpenAI client is shared by every request, so concurrent calls reuse its connection pool.
    max_retries lets the client back off and retry on rate limits (429) and server errors.
    api="chat" uses the Chat Completions API instead of Responses; only Chat Completions accepts audio.
    """
    if model_name not in ALLOWED_MODELS:
        raise ValueError(f"{model_name} is not allowed for HW 3. Pick one of: {', '.join(ALLOWED_MODELS)}")

    api_key = load_environment()
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=PORTKEY_BASE_URL,
        default_headers={"x-portkey-api-key": api_key, "x-portkey-provider": "openai"},
        max_retries=max_retries,
    )
    provider = OpenAIProvider(openai_client=client)
    if api == "chat":
        return OpenAIChatModel(model_name, provider=provider)
    return OpenAIResponsesModel(model_name, provider=provider)


def shrink_image(path: Path, max_side: int):
    """Return the image as JPEG bytes, scaled down so its longest side is at most max_side pixels."""
    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((max_side, max_side))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def is_image_refused(error: Exception):
    """True when the provider's content filter refused this particular image.

    That is a problem with one photo, not with the key, network or settings, so callers can skip the
    photo and carry on instead of stopping the whole run.
    """
    return (
        isinstance(error, ModelHTTPError)
        and error.status_code == 400
        and "content_policy" in str(error.body).lower()
    )


def check_connection():
    try:
        client = build_client()
    except RuntimeError as error:
        print(f"FAIL (no key): {error}")
        return 1

    try:
        response = client.responses.create(model=MODEL, input="Reply with the single word: ready")
    except APIConnectionError:
        print(f"FAIL (network): could not reach {PORTKEY_BASE_URL}. Is api.portkey.ai allowed on this network?")
        return 1
    except AuthenticationError:
        print("FAIL (auth): Portkey rejected PORTKEY_API_KEY. Check the key value.")
        return 1

    print(f"OK: {MODEL} via Portkey replied: {response.output_text.strip()!r}")
    return 0


if __name__ == "__main__":
    sys.exit(check_connection())
