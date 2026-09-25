import argparse
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parent
PROMPT_PATH = ROOT / "prompts" / "card_extract.md"
DEFAULT_DOCS_DIR = ROOT / "hw1_spoke_and_wrench" / "pdfs"
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


def clean_extracted_json(raw_text: str):
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.S)
        if match:
            cleaned = match.group(1).strip()
    return cleaned


def normalize_row(row: dict):
    if not isinstance(row, dict):
        raise ValueError(f"Expected a JSON object, got: {type(row).__name__}")

    row.setdefault("fields_not_found", [])

    required_fields = [
        "Date",
        "Merchant",
        "Amount_USD",
        "Classification",
        "Expense category",
    ]

    missing = []
    for field in required_fields:
        if row.get(field) is None:
            missing.append(field)
    if missing:
        for field in missing:
            if field not in row["fields_not_found"]:
                row["fields_not_found"].append(field)

    if row.get("Classification") == "personal":
        row["Expense category"] = None

    return row


def extract_pdf_text(file_path: Path) -> str:
    try:
        reader = PdfReader(str(file_path))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n\n".join(pages).strip()
        if not text:
            raise ValueError(f"No readable text found in {file_path.name}")
        return text
    except Exception as exc:
        raise RuntimeError(f"Failed to extract text from {file_path.name}: {exc}") from exc


def extract_card_rows(client: OpenAI, file_path: Path, prompt_text: str):
    extracted_text = extract_pdf_text(file_path)

    response = client.responses.create(
        model="gpt-5.6",
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            f"{prompt_text}\n\n"
                            f"Extract the transactions from this credit card statement PDF and use only the text below.\n"
                            f"Filename: {file_path.name}\n\n"
                            f"Credit card statement text:\n{extracted_text}"
                        ),
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
        raise RuntimeError(f"No output returned for {file_path.name}")

    clean_json = clean_extracted_json(raw_output)
    parsed = json.loads(clean_json)
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        raise ValueError(f"Expected JSON array for {file_path.name}, got {type(parsed).__name__}")

    return [normalize_row(row) for row in parsed]


def parse_args():
    parser = argparse.ArgumentParser(description="Extract credit card transactions from a PDF statement.")
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR, help="Directory containing the credit card statement PDF")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory to write the output JSON file")
    return parser.parse_args()


def main():
    args = parse_args()
    docs_dir = args.docs_dir.resolve()
    out_dir = args.out_dir.resolve()

    prompt_text = read_prompt_template()
    client = build_client()

    card_file = next(docs_dir.glob("credit_card_jan2026.pdf"), None)
    if card_file is None:
        card_file = next(docs_dir.glob("credit_card_Jan_2026.pdf"), None)
    if card_file is None:
        raise FileNotFoundError(f"credit_card_jan2026.pdf or credit_card_Jan_2026.pdf not found in {docs_dir}")

    rows = extract_card_rows(client, card_file, prompt_text)

    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / "credit_card_transactions.json"
    output_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"Saved {len(rows)} credit card transactions to {output_path}")


if __name__ == "__main__":
    main()
