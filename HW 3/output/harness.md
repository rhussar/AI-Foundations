# Agent Harness — Campus Customs

How the Campus Customs agent is built and kept fast, cheap and under control. Each problem adds its section.

---

## Problem 2: Building the product catalog

`build_catalog.py` looks at every product photo in `data/products/` (102 of them) and writes one structured entry per product to `output/catalog.json`. It uses a vision model (`gpt-5.6-luna` by default) through Portkey.

### How the build is sped up

The slow part is waiting for the model: each photo is one request, and most of that time is spent waiting on the network and the model, not using our computer. Doing 102 of those one after another means 102 waits back to back.

**1. Concurrent requests (the main speed-up).** The script sends the requests at the same time with Python's `asyncio`, keeping up to 16 in flight (`--concurrency`). When one finishes, the next photo starts. The total time is roughly *(102 ÷ 16) × one request* instead of *102 × one request*.

In an offline test with a stand-in model that takes 0.5 seconds per photo, one-at-a-time took 10.2 s for 20 photos, which works out to about 52 s for all 102. The concurrent loop did all 102 in **4.3 s, about 12× faster**. Real requests take longer than 0.5 s, so the time saved in a real run is larger still.

**Why this loop and not the alternatives:**

| Option | Why not |
| --- | --- |
| A plain `for` loop, one photo at a time | The slowest: every wait happens back to back |
| Several photos in one request | Fewer calls, but the model can mix up details between photos, and one bad answer spoils the whole group |
| OpenAI's Batch API | Cheaper, but results can take up to 24 hours, the opposite of quick |
| **Concurrent single-photo requests** | **Fastest in practice: one clean photo per request, all running at once** |

**2. Smaller uploads.** Each photo is shrunk so its longest side is at most 768 px before it is sent. That is still enough to read small left-chest text like "Yale SCHOOL OF MEDICINE", and it keeps both the upload size and the model's image tokens down.

**3. Skip work already done.** `catalog.json` stores a fingerprint (SHA-256 hash) of each photo. A re-run skips every product whose photo has not changed, so re-running after adding five photos makes five requests, not 102. `--no-cache` forces a full rebuild.

**4. A cheap, quick model.** Cataloguing clean product shots is an easy vision task, so the default is `gpt-5.6-luna`, the course's budget model, with reasoning effort `low`.

### Guardrails

- **Canary request.** The first photo is sent on its own. If the key, the network or a model setting is wrong, the run stops after one failed request instead of sending (and possibly paying for) 102 at once.
- **Concurrency cap.** No more than 16 requests are in flight, so the run doesn't set off Portkey's or OpenAI's rate limits.
- **Retries with backoff.** A request that hits a rate limit or a server error is retried automatically (up to 3 times) with increasing waits. An answer that doesn't fit the catalog model is sent back to the model to fix, up to 2 times.
- **Timeouts.** Each request is abandoned after 120 seconds, so one stuck call cannot hang the build.
- **Failures don't lose work.** Every photo that succeeded is saved even if others failed. The script lists the failures, and a re-run retries only those.
- **`--limit N`** catalogues just the first N photos, for a cheap test before spending on the full run.

### The catalog model (`models.py`)

Each entry is a `CatalogEntry`. The model fills in the product attributes from the photo; the script adds the three ID fields from the file itself, so the model is never asked to invent an ID or a path.

| Field | Example | Why it's there |
| --- | --- | --- |
| `product_id` | `yale-dad-t-shirt` | Stable key from the file name, so every other output can point to a product |
| `image_file` | `data/products/yale-dad-t-shirt.jpg` | Traces each entry back to its photo, so anyone can check it |
| `image_sha256` | `3f9a…` | Photo fingerprint that lets re-runs skip unchanged products |
| `product_name` | `Yale Dad T-Shirt` | Human-readable name for outreach messages and reports |
| `garment_type` | `t-shirt` | The first thing you notice on a person. A fixed list (tee, crewneck, hoodie, quarter-zip…) keeps the values consistent, so they can be compared reliably |
| `base_color` | `heather grey` | Visible even in a small or blurry photo, and quickly rules products in or out |
| `print_colors` | `["navy"]` | Tells apart designs that share a garment and wording |
| `visible_text` | `["YALE", "UNIVERSITY", "DAD"]` | The strongest clue for spotting a product on someone. Most Campus Customs designs are words, and many products differ only in one word (Dad / Mom / Grandpa) |
| `graphics` | `["block Y"]`, `["Davenport College shield"]` | Separates crest and logo designs whose wording is similar or tiny |
| `design_placement` | `full front` / `left chest` | Separates otherwise similar items, e.g. a big full-front "YALE" versus a small left-chest crest |
| `garment_brand` | `Champion`, `Brooks Brothers`, or null | Some products are defined by their brand. It stays null unless the brand is readable, so it's never guessed |
| `affiliation` | `family`, `residential college`, `athletics`… | Groups the catalogue the way customers see themselves |
| `affiliation_detail` | `Dad`, `Davenport College`, `Hockey` | The specific community, which says who the wearer probably is |
| `target_audience` | `["parent"]`, `["student", "alumni"]` | Links products to customer profiles for the ad question (would this land with a Yale student or a parent?) and for choosing whom to contact |
| `matching_description` | "Grey tee with large navy YALE over small UNIVERSITY and DAD — not the crewneck or hoodie version." | A one-line summary for matching a product in a photo, including what separates it from its closest look-alikes |

The fields are chosen for the two growth questions the agent has to answer:
- **Is someone in a photo wearing one of our products?** That needs what you can actually see on a person: garment, colors, text, graphics and placement.
- **Would an ad land with a given customer?** That needs who the product is for: affiliation and audience.

Fields that can't be seen in a photo, such as price, sizes and fabric, are left out because the model would have to guess them.
