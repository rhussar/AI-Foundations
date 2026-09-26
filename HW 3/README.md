# Homework 3 Workspace

This folder contains:
- `AI_prompts.md` for recording prompts used during Homework 3
- `portkey_client.py`, the shared Portkey/OpenAI client every HW 3 script imports
- `prompts/` for prompt files
- `output/` for generated outputs
- `data.zip`, the provided data (unzip it here to get `data/`)

## Data

`data.zip` unzips to `data/` (ignored by git, since the zip is already committed):
- `data/products/` — 102 Yale store product photos, named by product slug
- `data/test_images/` — 4 photos labelled `_true` / `_false` in the filename
- `data/videos/ad_humble.mp4` — a 9 second 1080p ad

## Setup

```bash
cd "HW 3"
unzip -o data.zip
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python portkey_client.py   # checks the key and the connection to Portkey
```

The scripts read `PORTKEY_API_KEY` from `HW 3/.env` or the workspace `.env`, or from the environment.
