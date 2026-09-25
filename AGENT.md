# Lecture 3 Agent Setup

## Python environment

Use the Lecture 3 virtual environment before running Python commands:

```bash
source "Lecture 3/.venv/bin/activate"
python -m pip install -r "Lecture 3/requirements.txt"
```

## Portkey with OpenAI

Keep the Portkey credential in the workspace `.env` file as `PORTKEY_API_KEY`. Do not commit or print its value. The OpenAI client should route requests through Portkey and use the GPT-5.6 model:

```python
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.environ["PORTKEY_API_KEY"],
    base_url="https://api.portkey.ai/v1",
    default_headers={
        "x-portkey-api-key": os.environ["PORTKEY_API_KEY"],
        "x-portkey-provider": "openai",
    },
)

response = client.responses.create(
    model="gpt-5.6",
    input="Your prompt here",
)
```

Use `PORTKEY_API_KEY`, not a hard-coded key or `OPENAI_API_KEY`, for Lecture 3 requests. Keep model and routing changes localized to the Lecture 3 code.