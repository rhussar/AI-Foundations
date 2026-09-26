"""Shared Portkey/OpenAI setup for Homework 3.

Every HW 3 script imports build_client() and MODEL from here so routing stays in one place.
Run this file directly to check the connection:  python portkey_client.py
"""

import base64
import mimetypes
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import APIConnectionError, AuthenticationError, OpenAI


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
PROMPTS_DIR = ROOT / "prompts"

PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
# Allowed for HW 3. The course budget assumes luna; use a smarter one only for hard vision/agent steps.
ALLOWED_MODELS = ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol", "gpt-6-astra")
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")


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


def image_to_data_url(path: Path):
    """Encode a local image so it can be sent as an input_image to the Responses API."""
    mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


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
