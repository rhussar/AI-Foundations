# Homework 3 Workspace

Campus Customs sells Yale merch. HW 3 builds an agent that answers two growth questions:
1. Is someone in a photo wearing a Campus Customs product (so they might be worth outreach)?
2. Would a Campus Customs ad video land with a given customer profile, such as a Yale student or a parent?

All model calls go through Portkey with `PORTKEY_API_KEY`, using one of `gpt-5.6-luna` (the default, and what the course budget assumes), `gpt-5.6-terra`, `gpt-5.6-sol` or `gpt-6-astra`. The work is submitted as `hw3.zip`; the last problem lists which files to include.

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
