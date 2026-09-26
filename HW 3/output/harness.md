# Agent Harness — Campus Customs

How the Campus Customs agent is built and kept fast, cheap and under control. Each problem adds its section.

---

## Problem 2: Building the product catalog

`build_catalog.py` looks at every product photo in `data/products/` (102 of them) and writes one structured entry per product to `output/catalog.json`. It uses a vision model (`gpt-5.6-luna` by default) through Portkey.

### How the build is sped up

The slow part is waiting for the model: each photo is one request, and most of that time is spent waiting on the network and the model, not using our computer. Doing 102 of those one after another means 102 waits back to back.

**1. Concurrent requests (the main speed-up).** The script sends the requests at the same time with Python's `asyncio`, keeping up to 16 in flight (`--concurrency`). When one finishes, the next photo starts. The total time is roughly *(102 ÷ 16) × one request* instead of *102 × one request*.

In an offline test with a stand-in model that takes 0.5 seconds per photo, one-at-a-time took 10.2 s for 20 photos, which works out to about 52 s for all 102. The concurrent loop did all 102 in **4.3 s, about 12× faster**.

In the real run through Portkey, the concurrent loop described **94 photos in 23.6 seconds**, using 146,505 input and 14,373 output tokens. A 5-photo test before it took 8.6 s.

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
- **A refused photo is not a broken run.** The Azure content filter behind Portkey wrongly refuses 3 ordinary college-crest photos (`benjamin-franklin-t-shirt`, `berkeley-1-4-zip`, `timothy-dwight-college-crewneck`), and refuses them every time. At first, a refused photo that happened to be the canary stopped the whole build. Now a refusal is recorded as that photo's failure and the next photo becomes the canary. The catalog has **99 of 102 products**, and those 3 are listed as failures on every run rather than skipped silently.
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

---

## Problem 3: Product identification

`agent.py` is the Campus Customs agent. It's a Pydantic AI agent whose system prompt is `prompts/prompts.md`. Its first ability answers: *is someone in this photo wearing a Campus Customs product, and which one?*

```bash
python agent.py --image "data/test_images/image_01_true.jpeg"
```

The structured answer is saved to `output/identify_product.json`.

### How the agent identifies a product

The agent reads the request and calls its `identify_product` tool with the photo path. The tool's logic lives in `tools.py` and runs in three steps:

| Step | What happens | Images sent |
| --- | --- | --- |
| **1. Look at the photo** | One vision call lists each printed garment people are wearing: garment type, color, the exact printed words, logos, where the design sits, and whether the garment itself is Yale-branded | 1 |
| **2. Shortlist in code** | Plain Python scores all 99 catalog entries against what was seen, using the text fields from Problem 2's catalog. No model call and no images. The top 5 go forward | 0 |
| **3. Compare side by side** | One vision call sees the photo next to those 5 catalog photos and picks the product, says which few it could be, or says none of them | 1 + 5 |

**If step 1 finds no Yale branding, the agent stops there** and answers "no Campus Customs product" after sending just 1 image. The Yale branding has to be on the clothing: a Yale building in the background doesn't count. That matters for test photo 4, where a woman in a navy Balenciaga tee stands in front of a Yale gate.

### What makes it efficient

- **No image-by-image catalog search.** Comparing the photo with each of 99 catalog photos would take 99 image comparisons. Instead, the catalog built in Problem 2 is searched as text, in code, for free. Only the 5 most likely products are ever looked at as images.
- **Smart scoring.** The shortlist gives most weight to printed words and logos, and weights each word by how rare it is in the catalog. "DAD", "BULLDOGS" or "DAVENPORT" count far more than "YALE", which is on nearly everything. Garment type, color and design placement break ties. Offline tests with sample photo readings against the real catalog put the right product in the top 5 each time, next to the look-alikes that step 3 has to tell apart:
  - Yale Dad tee → `yale-dad-t-shirt`, `yale-dad-hoodie`, `yale-dad-crewneck`, …
  - Navy "YALE BULLDOGS" long-sleeve → `dry-zone-long-sleeve`, `yale-maplehouse-diana-mockneck`, `ua-mens-tech-l-s-2-0`, …
  - Balenciaga tee → no candidates, so the agent stops after 1 image
- **Hard image limit.** A normal run sends **7 images**, and never more than 10:
  - Every upload is counted, and `images_sent` is saved in the output.
  - A retry re-sends every image in the request, so retries count too.
  - Step 1 may retry once, and step 3 never retries, so the worst case is 8. A check in the code blocks any send that would go over 10.
- **Right-sized images.** The customer photo is sent at up to 1024 px, because its printing is small, angled and partly hidden. The flat catalog photos only need 512 px.
- **Two vision calls, one cheap routing call.** The agent's own call only routes the request, and it sends no images. Everything uses `gpt-5.6-luna` by default. `--vision-model gpt-5.6-terra` switches the photo checks to a smarter model if harder photos need it.

### Results on the four test photos

Run for real through Portkey with `gpt-5.6-luna`:

| Photo | Truth | Agent's answer | Confidence | Images sent |
| --- | --- | --- | --- | --- |
| `image_01_true.jpeg` (man in grey "YALE UNIVERSITY DAD" tee) | product | ✅ `yale-dad-t-shirt` | high | 7 |
| `image_02_false.jpeg` (woman in "ESSENTIALS" hoodie) | no product | ✅ none; stopped after step 1 | high | 1 |
| `image_03_true.jpeg` (man in navy "YALE BULLDOGS" long-sleeve, arm raised) | product | ✅ `dry-zone-long-sleeve` | high | 7 |
| `image_04_false.jpeg` (navy Balenciaga tee in front of a Yale gate) | no product | ✅ none; stopped after step 1 | high | 1 |

**4 of 4 correct**, with at most 7 images per photo, and just 1 for the two photos with no Yale branding. Photo 3 is the hard one: the shortlist held two navy "YALE BULLDOGS" long-sleeves, and the side-by-side step picked the right one. `output/identify_product.json` holds the full answer for `image_01_true.jpeg`.

One thing to watch: for photo 1 the model read the design as "center chest", while the catalog calls it "full front". The right product still came first in the shortlist, but the Dad crewneck and hoodie look-alikes dropped out of the top 5. Placement is a small part of the score for this reason, and the printed words carry most of it.

### Guardrails

- **The model can only pick products it was shown.** If step 3 names a product outside its shortlist, or says "found" without naming a shortlisted product, the code corrects the answer and marks it low confidence, instead of asking again and re-sending 6 images.
- **Honest uncertainty.** When the product clearly appears but the agent can't tell which of two or three look-alikes it is (for example the tee, crewneck and hoodie versions of "YALE DAD"), it says so in `possible_product_ids` instead of guessing.
- **The tool's answer is the final answer.** `identify_product` is the agent's output tool, so its structured result is returned exactly as built. The agent can't reword it or make up a product.
- **Bad paths are caught.** If the agent passes a path that doesn't exist, the tool rejects it and the agent retries with the exact path from the request.
- **Content-filter refusals are reported clearly**, as a refused photo rather than a crash.

### The identification model (`models.py`)

The tool returns a `ProductIdentification`:

| Field | Example | Why it's there |
| --- | --- | --- |
| `image_path` | `data/test_images/image_01_true.jpeg` | Which photo the answer is about |
| `product_found` | `true` | The main yes/no: is this person worth outreach? |
| `product_id` | `yale-dad-t-shirt` | Which exact product, as a catalog key. It links to everything else we know about the product, such as its audience, and is `null` when the agent can't tell |
| `product_name` | `Yale Dad T-Shirt` | Readable name for people and outreach messages |
| `possible_product_ids` | `["yale-dad-t-shirt", "yale-dad-crewneck"]` | Covers "which one, *if you can tell*": when the product clearly appears but look-alikes can't be told apart, the agent names the few it could be instead of guessing |
| `confidence` | `high` / `medium` / `low` | Lets outreach focus on sure matches first. Three plain levels, because a model's made-up percentages aren't meaningful |
| `evidence` | `["navy YALE over DAD across the chest", "short sleeves"]` | The visible details behind the decision, so a person can check it in seconds |
| `summary` | "The man is wearing the Yale Dad tee…" | Plain-language explanation |
| `observed_garments` | garment, color, text, logos, Yale branding | What the agent actually saw. When an answer is wrong, this shows whether the photo was misread (step 1) or the product mis-picked (step 3) |
| `candidates_checked` | the 5 shortlisted product IDs | Shows the agent only compared a shortlist, and whether the right product made it into the shortlist |
| `images_sent` | `7` | Proves each run stayed within the 10-image limit |

The two vision steps have their own smaller models:
- `PhotoObservation` is a list of `ObservedGarment`, using the same garment, color, text, graphics and placement fields as the catalog, so the two can be compared directly.
- `MatchVerdict` holds the step-3 decision.
