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

The structured answer is saved to `output/identify_product.json`, as a list with one entry per photo. Several `--image` paths can be given, and they are checked at the same time.

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

**4 of 4 correct**, with at most 7 images per photo, and just 1 for the two photos with no Yale branding. Photo 3 is the hard one: the shortlist held two navy "YALE BULLDOGS" long-sleeves, and the side-by-side step picked the right one. `output/identify_product.json` holds all four answers (Problem 4), and `output/agent_evaluation.md` evaluates them.

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

---

## Problem 5: Judging an ad video for a customer

The agent's second ability answers: *how effective would this ad video be at getting this customer to shop at Campus Customs?*

```bash
python agent.py --video "data/videos/ad_humble.mp4" --profile "profiles/profile_student.json"
```

The structured answer goes to `output/ad_effectiveness.json`, as a list with one entry per profile. Several `--profile` files can be given; the video is analysed once and judged for each.

**One prompt file.** Every instruction the agent uses lives in `prompts/prompts.md`:
- The top part is the agent's system prompt. It now describes both abilities and when to use each.
- Below the line `# Tool step instructions`, each model call inside the tools has its own `##` section, which the tool loads by its heading.

The photo steps from Problem 3 were moved into the same file, so there's no second agent prompt file. (`prompts/catalog_extract.md` belongs to `build_catalog.py`, the separate Problem 2 script, not to the agent.)

### The tools for the video + profile job

The agent calls `judge_ad_effectiveness(video_path, profile_path)`. Inside `tools.py`, that runs these tools:

| Tool | What it does | Model call? |
| --- | --- | --- |
| `load_profile` | Reads the profile JSON and checks it against `CustomerProfile` in `models.py`, so a broken profile fails clearly instead of confusing the judge | No |
| `extract_frames` | Takes about one frame per second (the middle of each second, which skips fades), drops frames that barely differ from the last one kept, and stops at 10. The 9-second ad gives 9 frames at 768 px. Its camera never stops moving, so no frame was dropped as a near-duplicate; on a static video that check saves images | No |
| `watch_video` | One vision call sees the frames in order, each labelled with its time. It describes the scenes, the people, the setting, each distinct garment design (read like a product photo), on-screen text, Campus Customs branding, the call to action, the tone and the apparent message. It describes but doesn't judge | Yes, 1 call with 9 images |
| `extract_audio` + `listen_to_audio` | The soundtrack is pulled out with ffmpeg (16 kHz mono WAV). The Responses API the agent uses can't take audio, so this call goes through the Chat Completions API. If the model accepts audio, it describes the lyrics or speech, the music and the mood. If it doesn't, the analysis says so and why, and the judge is told not to guess what the soundtrack says. **In the real runs the provider behind Portkey refused audio** ("content blocks are expected to be either text or image_url type"), so every verdict so far is based on the visuals alone, and says so | Yes, 1 call (refused here) |
| `match_featured_products` | Matches each Yale garment seen in the ad to its closest catalog product, using the same text scorer as Problem 3's shortlist, and only when the match is strong. The judge then knows who those products are made for (for example "students, alumni, fans") | No |
| `analyze_video` | Runs the four steps above once per video and caches the result: shared in memory when several profiles are judged at once, and saved to `output/cache/` for later runs. The cache key includes the video's fingerprint, the model and the watch/listen instructions, so changing any of them triggers a fresh analysis. `--no-cache` forces one | No |
| `judge_for_customer` | One **text-only** call gets the profile, the video analysis and the featured products' audiences, and returns the judgement. No images are re-sent: the video is judged from the analysis | Yes, 1 call, no images |

**Why this split:**
- Watching the video is the expensive part, and what the ad shows doesn't depend on who's watching. So it's done once, and only the cheap text judgement runs per customer. For Problem 7's several profiles, each extra customer costs one text call instead of nine more images.
- Keeping the description and the judgement separate also keeps the description neutral: the vision step can't bend what it sees to fit a customer.

### Guardrails

- **Score and response must agree.** 7–10 means "likely to shop", 4–6 "might shop", 1–3 "unlikely to shop". A judgement that contradicts itself (for example 8/10 but "might shop") is sent back to be fixed. The judge step is text only, so a retry costs no images.
- **No invented soundtrack.** If the audio wasn't analysed, the judge is told plainly and asked not to guess, and `audio_analyzed: false` with `audio_note` records why. Confidence is also capped at `medium` in code. The first real run came back "high" without the audio, and a parody of a rap song can't be judged with high confidence from its visuals alone.
- **The format is measured, not guessed.** The video's resolution and orientation are read from the file and given to the judge. The first real run called this landscape 1920×1080 ad "vertical".
- **Real problems count.** The judging instructions make no Campus Customs branding and no call to action count as weaknesses even when the ad looks great, because a customer who can't tell who's selling can't buy.
- **Paths are checked before any model call.** A typo in `--video` or `--profile` stops the run with a clear message and costs nothing. Inside the agent, a wrong path makes the agent retry with the exact path.
- **The right ability for the job.** The run checks that the agent answered with an `AdEffectiveness` for a video request, and a `ProductIdentification` for a photo request.

### The ad-effectiveness model (`models.py`)

The tool returns an `AdEffectiveness`:

| Field | Example | Why it's there |
| --- | --- | --- |
| `video_path`, `profile_path`, `profile_name` | `data/videos/ad_humble.mp4`, `profiles/profile_student.json`, `Maya Chen, Yale sophomore` | Which ad and which customer the verdict is about. In Problem 7's list of results for several customers, each entry says whose it is |
| `effectiveness_score` | `6` (1–10) | One number to compare the same ad across customers, or different ads for one customer. The prompt defines what each band means, so the numbers are consistent |
| `likely_response` | `likely to shop` / `might shop` / `unlikely to shop` | The plain-language outcome a marketer acts on. Forced to agree with the score |
| `confidence` | `medium` | How much to trust the verdict. For example, it should drop when the soundtrack couldn't be heard |
| `profile_fit` | `[{profile_point: "streetwear style", ad_evidence: "oversized navy hoodie in a music-video look", fit: "strong"}, …]` | The core of the judgement: the 4–8 profile points that matter most, what in the ad speaks to each, and how well (`strong` / `partial` / `none` / `negative`). It makes the score explainable and checkable point by point, and forces the judge to reason from this customer's profile rather than about ads in general |
| `what_works` | `["the style matches her streetwear taste"]` | What to keep |
| `what_misses` | `["never says Campus Customs", "no call to action"]` | What to fix |
| `suggested_changes` | `["end on the Campus Customs logo and a student discount code"]` | Turns the critique into concrete edits. That's the point of judging an ad |
| `summary` | two or three sentences | The short version for someone skimming |
| `video_analysis` | frames, scenes, garments, branding, call to action, audio, featured products | What the agent actually saw and heard. Anyone can check whether a bad verdict came from misreading the video or from judging it badly, and whether the soundtrack was part of the judgement |

`CustomerProfile` (in `models.py` too) sets out what a profile file contains; see Problem 6.

---

## Problem 6: Student and parent profiles

### Why these two profiles

Campus Customs' two biggest groups of buyers are the people *at* Yale and the people who love someone at Yale. The catalog says so: its `target_audience` values are dominated by students and alumni on one side and parents and family members on the other, with a whole family line ("Yale Dad", "Yale Mom", "Yale Grandpa" and so on). So one profile from each group tests whether an ad reaches the shop's real customers.

They were also written as **deliberate opposites**, to test whether the agent judges from the profile or just rates the ad in general:

| | Student: Maya Chen, 19, Yale sophomore | Parent: Tom Brennan, 53, father of a Yale sophomore |
| --- | --- | --- |
| Relationship to Yale | Lives it daily, in Pierson College | Proud from 8 hours away; first in the family at Yale is his daughter |
| Style | Oversized streetwear, muted colors, hates touristy logos | Classic quarter-zips and crewnecks; no streetwear |
| Money | Campus-job budget, **high** price sensitivity | Pays for quality, **low** price sensitivity |
| Where ads reach them | TikTok and Instagram, sound on, skips anything corporate in 2 s | Facebook with the sound off, the Yale parents group, email |
| Buys for | Herself and matching gear with friends | Himself, as gifts for family, and care packages for his daughter |
| When | The Game, college spirit days | Family Weekend, holidays, move-in, Commencement |
| Objections | Already owns a Yale sweatshirt; doesn't know Campus Customs | "Aimed at students, not me"; wants to see product, price and where to buy; doesn't get the music references |

The ad is a music-video-style clip of young people in Yale hoodies under a highway bridge, with no shop name and no call to action. A good judge should score it clearly higher for Maya than for Tom, for reasons it can name from each profile.

**A typical student and parent rather than myself.** A realistic, specific persona gives the judge concrete things to test the ad against: a budget, a platform, an objection. Either profile could be swapped for a real person by filling in the same fields.

### The profile model (`CustomerProfile` in `models.py`)

`make_profiles.py` builds both profiles as `CustomerProfile` instances and writes them to `profiles/profile_student.json` and `profiles/profile_parent.json`, so the files always match the model.

| Field | Why it matters for whether an ad resonates |
| --- | --- |
| `profile_id`, `name`, `description` | Who this is, in a sentence the judge can picture |
| `age_range`, `relationship_to_yale` | The first filter: does the ad's cast and world look like theirs? |
| `interests`, `values` | What the ad must connect with, or at least not offend: belonging, authenticity, tradition, not embarrassing your kid |
| `style` | Whether the clothes in the ad are clothes they'd wear |
| `budget`, `price_sensitivity` | Whether a missing price or discount is a dealbreaker (student) or barely matters (parent) |
| `shopping_habits` | Whether they could act on the ad the way they actually buy (phone, campus, trusted site) |
| `media_habits` | Where they'd see it and how. A soundtrack-driven ad is weaker for someone who watches with the sound off |
| `already_owns` | Whether the ad gives a reason to buy *another* Yale item |
| `buys_for`, `purchase_occasions` | Added in this problem. Parents buy for others and around campus events, so an ad can win them with a gift or an occasion, and miss them without one |
| `buying_triggers` | What actually pushes them to buy |
| `likely_objections` | What the ad has to overcome. The judge scores each one it leaves unanswered |

Every field is required, and unknown fields are rejected (`extra="forbid"`). A half-filled profile or a misspelt field name would otherwise quietly weaken the judgement. `agent.py` now validates `--profile` files before spending any model calls.

### Running both profiles

Each profile runs as its own command, as the problem specifies. Each run **merges** its result into `output/ad_effectiveness.json` instead of overwriting it: a result replaces the earlier one for the same video and profile, and keeps the rest. So after the student run and then the parent run, the file holds both. The same merging applies to `output/identify_product.json`, keyed by photo.

The second run costs one text call: the video analysis from the first run is cached, so the parent run doesn't look at a single frame again.
