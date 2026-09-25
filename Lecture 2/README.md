# Lease portfolio dashboard

This project extracts structured lease data from the PDFs in `Pdfs/` through Portkey's OpenAI-compatible API and writes `lease_data.json`. The Dash app then shows monthly and annual income, leased area, a map, and a lease ledger.

## Setup

From the `Lecture 2` folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python extract_leases.py
python app.py
```

Open `http://127.0.0.1:8050` after starting the app.

The extractor reads `PORTKEY_API_KEY` from the workspace `.env` file. It uses `OPENAI_MODEL` when set, otherwise `gpt-5.6-luna`. Keep `.env` private and do not commit `lease_data.json` if it contains sensitive lease information.
