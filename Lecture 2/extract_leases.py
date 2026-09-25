from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pypdf import PdfReader

BASE_DIR = Path(__file__).resolve().parent
PDF_DIR = BASE_DIR / "Pdfs"
OUTPUT_PATH = BASE_DIR / "lease_data.json"
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
CITY_COORDINATES = {
    "Branford": (41.2795, -72.8151),
    "Hamden": (41.3959, -72.8968),
    "Milford": (41.2307, -73.0640),
    "New Haven": (41.3083, -72.9279),
}


def read_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


def extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("The model response did not contain a JSON object")
    return json.loads(match.group(0))


def extract_lease(client: OpenAI, path: Path) -> dict:
    text = read_pdf(path)
    prompt = f"""Extract the commercial lease fields from the document below.
Return only a JSON object with exactly these keys:
landlord, tenant, address, city, state, zip_code, space_type, square_feet,
annual_base_rent, rent_per_sqft, lease_structure, commencement_date,
expiration_date, security_deposit, permitted_use.
Use ISO dates (YYYY-MM-DD) when a date is present. Use numbers for money,
square footage, and rent per square foot. Use null when a field is missing.
Do not infer coordinates or values that are not in the document.

DOCUMENT:
{text}"""
    response = client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "You extract structured data from lease documents."},
            {"role": "user", "content": prompt},
        ],
    )
    result = extract_json(response.choices[0].message.content or "")
    result["source_file"] = path.name
    result["monthly_rent"] = round(float(result["annual_base_rent"]) / 12, 2)
    coordinates = CITY_COORDINATES.get(result.get("city"))
    result["latitude"], result["longitude"] = coordinates or (None, None)
    return result


def main() -> None:
    load_dotenv(BASE_DIR.parent / ".env")
    portkey_api_key = os.getenv("PORTKEY_API_KEY")
    if not portkey_api_key:
        raise RuntimeError("PORTKEY_API_KEY is missing from the workspace .env file")

    client = OpenAI(
        api_key=portkey_api_key,
        base_url="https://api.portkey.ai/v1",
        default_headers={"x-portkey-api-key": portkey_api_key},
    )
    records = []
    for path in sorted(PDF_DIR.glob("*.pdf")):
        print(f"Extracting {path.name}...")
        records.append(extract_lease(client, path))

    payload = {
        "generated_at": date.today().isoformat(),
        "model": MODEL,
        "properties": records,
    }
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(records)} properties to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
