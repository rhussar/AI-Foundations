import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


ROOT = Path(__file__).resolve().parent
PROMPT_PATH = ROOT / "prompts" / "reconcile.md"
DEFAULT_DOCS_DIR = ROOT / "hw1_spoke_and_wrench"
DEFAULT_JSON_DIR = ROOT / "output"
DEFAULT_OUTPUT_DIR = ROOT / "output"


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
        base_url="https://api.portkey.ai/v1",
        default_headers={
            "x-portkey-api-key": api_key,
            "x-portkey-provider": "openai",
        },
    )


def read_prompt_template():
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(f"Prompt template not found: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8")


def load_json_file(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Required JSON file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def build_reconciliation_context(json_dir: Path, docs_dir: Path):
    files = {
        "receipts": json_dir / "receipts.json",
        "bank": json_dir / "bank_transactions.json",
        "card": json_dir / "credit_card_transactions.json",
        "manifest": docs_dir / "manifest.json",
        "owner_memo": docs_dir / "emails" / "email_owner_voice_memo.txt",
        "wedding": docs_dir / "emails" / "email_wedding_ebikes.txt",
        "yclub": docs_dir / "emails" / "email_yale_cycling_club.txt",
        "fleet": docs_dir / "emails" / "email_fleet_wellness.txt",
    }

    context = {}
    for name, path in files.items():
        if path.exists():
            if path.suffix.lower() == ".json":
                context[name] = json.dumps(load_json_file(path), indent=2)
            else:
                context[name] = path.read_text(encoding="utf-8")

    return context


def extract_reconciliation_log(client: OpenAI, prompt_text: str, context: dict):
    payload = "\n\n".join(f"## {key}\n{value}" for key, value in context.items())

    response = client.responses.create(
        model="gpt-5.6",
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"{prompt_text}\n\nUse the following documents and earlier JSON outputs:\n\n{payload}",
                    }
                ],
            }
        ],
    )

    raw_output = getattr(response, "output_text", "") or ""
    if not raw_output:
        raw_output = "".join(
            block.get("text", "")
            for item in getattr(response, "output", [])
            for block in item.get("content", [])
            if isinstance(block, dict)
        )

    if not raw_output:
        raise RuntimeError("No output returned for the reconciliation prompt")

    cleaned = raw_output.strip()
    if cleaned.startswith("```"):
        import re
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.S)
        if match:
            cleaned = match.group(1).strip()

    parsed = json.loads(cleaned)
    if not isinstance(parsed, list):
        raise ValueError(f"Expected a JSON array, got {type(parsed).__name__}")
    return parsed


def parse_args():
    parser = argparse.ArgumentParser(description="Create a reconciliation log from prior extracted outputs and supporting documents.")
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR, help="Directory containing the business document pack")
    parser.add_argument("--json-dir", type=Path, default=DEFAULT_JSON_DIR, help="Directory containing prior JSON outputs")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory to write the reconciliation output")
    return parser.parse_args()


def main():
    args = parse_args()
    docs_dir = args.docs_dir.resolve()
    json_dir = args.json_dir.resolve()
    out_dir = args.out_dir.resolve()

    prompt_text = read_prompt_template()
    client = build_client()
    context = build_reconciliation_context(json_dir, docs_dir)
    rows = extract_reconciliation_log(client, prompt_text, context)

    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / "reconciliation_log.json"
    output_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"Saved {len(rows)} reconciliation rows to {output_path}")


if __name__ == "__main__":
    main()
