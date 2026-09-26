# Agent Evaluation — Product Identification

**Verdict: good on this test set, with clear limits on what four photos can prove.** The agent got all 4 photos right, including the exact product in both positive photos. It avoided the one deliberate trap, and it did it cheaply and quickly. But four photos is far too few to call it reliable, and several hard cases haven't been tested yet (see *What this test doesn't show*).

## How it was tested

```bash
python agent.py --image data/test_images/image_01_true.jpeg data/test_images/image_02_false.jpeg \
                        data/test_images/image_03_true.jpeg data/test_images/image_04_false.jpeg
```

- **Model:** `gpt-5.6-luna` via Portkey (the course default) for every step, reasoning effort `low`.
- **Output:** `output/identify_product.json`, 4 entries, each validated against `ProductIdentification` in `models.py`.
- **Ground truth for "is there a product?":** the file name (`_true` / `_false`).
- **Ground truth for "which product?":** the file names don't say, so I checked each positive photo by eye against the catalog:
  - Photo 1 is `yale-dad-t-shirt`: grey tee, navy "YALE" between two bars, "UNIVERSITY" and "DAD" underneath.
  - Photo 3 is `dry-zone-long-sleeve`: navy long-sleeve, plain solid "YALE" over small "BULLDOGS". It isn't the look-alike `ua-mens-tech-l-s-2-0`, which has outlined arched "YALE", a block Y and an Under Armour logo.
- **Repeats:** the same 4-photo run was done three times, to check whether the answers change.

## Results

| Photo | What's in it | Truth | Agent said | Right product? | Confidence | Images sent | Time | Tokens (in / out) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `image_01_true` | Man in grey "YALE UNIVERSITY DAD" tee by the SOM sign | Product | ✅ Found `yale-dad-t-shirt` | ✅ | high | 7 | 2.5 s | 4,611 / 257 |
| `image_02_false` | Woman in grey "ESSENTIALS" hoodie in a hallway | No product | ✅ None | n/a | high | 1 | 1.6 s | 1,632 / 94 |
| `image_03_true` | Man in navy "YALE BULLDOGS" long-sleeve, arm raised, letters partly hidden | Product | ✅ Found `dry-zone-long-sleeve` | ✅ | high | 7 | 2.4 s | 5,239 / 278 |
| `image_04_false` | Woman in navy Balenciaga tee in front of a Yale gate | No product | ✅ None | n/a | high | 1 | 1.7 s | 1,980 / 100 |

| Measure | Result |
| --- | --- |
| Product present or not (accuracy) | **4 / 4** |
| False positives (said "product" when there wasn't one) | 0 of 2 |
| False negatives (missed a real product) | 0 of 2 |
| Exact product correct, when one was found | **2 / 2** |
| Same answers across 3 runs | 3 / 3 (identical) |
| Images per photo | 7 with a product, 1 without (limit: 10) |
| Whole 4-photo run | about 2.5 s wall time (photos run at the same time), 13,462 input / 729 output tokens |

## Why it's good

1. **It resisted the trap.** Photo 4 was built to fool a lazy agent: a navy tee (Campus Customs sells lots of navy) in front of a Yale gate. The agent read "Balenciaga" on the shirt, marked it not Yale-branded, and correctly ignored the background. The prompt says scenery doesn't count, and the model followed that.
2. **It told apart near-identical products.** Photo 3 is the hardest case. Two catalog products are navy long-sleeves saying "YALE BULLDOGS", and the man's raised arm hides part of the lettering. The shortlist put both look-alikes in front of the model, and the model named the exact differences in its evidence: "lacks the outlined YALE, standalone Y, Under Armour logo". That's the reasoning a person would use.
3. **The evidence can be checked.** Every answer lists what the model saw (text, garment, color) and why it chose. That makes each result quick to verify, and it's how I confirmed both product answers.
4. **It's cheap where it can be.** The two photos with no Yale branding stopped after one image and about 1,800 tokens. The two with a product used 7 images, well under the limit of 10. None of the 99 catalog photos was ever compared one by one.
5. **It's fast.** All four photos took about 2.5 seconds together, because they're checked at the same time.

## What this test doesn't show

1. **Four photos is a tiny sample.** 4/4 is encouraging, not proof. Statistically, 4 correct out of 4 is consistent with a true accuracy as low as about 40% (the 95% lower bound). A few dozen labelled photos would give a meaningful number.
2. **The repeats may not be independent.** All three runs gave word-for-word identical answers with identical token counts. That usually means the answers were cached (Portkey can cache repeated requests) or the model is effectively deterministic at this setting. Either way, the repeats show the pipeline is stable, but they don't show the model would decide the same way on a slightly different photo.
3. **The hardest negative wasn't tested:** a *Yale* shirt that Campus Customs doesn't sell, such as one from the Yale bookstore. Both negatives here had no Yale branding at all, so they were settled in step 1 without testing the final comparison step's ability to say "Yale, but not ours".
4. **Small or hidden designs weren't tested.** Both positives had big front prints. Many catalog items have only a small left-chest crest (all the college crewnecks). If step 1 misses a small crest, the agent stops early and misses the product. That failure mode is untested.
5. **A shortlist slip went unnoticed.** In photo 1 the model read the design as "center chest", while the catalog calls it "full front". The right product still came first in the shortlist, but the Dad crewneck and Dad hoodie, its closest look-alikes, dropped out of the top 5. So the final step never had to prove it can tell the tee from the crewneck. On another photo, the same slip could push the right product out entirely.
6. **Confidence was always "high".** It was right every time, so there was nothing wrong to compare it against. Whether "high" really means high is unknown until the agent gets something wrong.
7. **Three products can never be found.** `benjamin-franklin-t-shirt`, `berkeley-1-4-zip` and `timothy-dwight-college-crewneck` are missing from the catalog, because the provider's content filter refuses their photos. Someone wearing one of them would be reported as "no product", or matched to the wrong college.
8. **Only single-person photos were tested.** The model supports several garments per photo, but no test photo had more than one person.

## What I'd do next

1. **Build a bigger test set** of 20–40 labelled photos, including:
   - left-chest crests
   - partly hidden or angled prints
   - group photos
   - Yale shirts Campus Customs doesn't sell
   - the tee/crewneck/hoodie versions of the same design
2. **Make the shortlist tolerant of placement.** Treat "full front" and "center chest" as close matches, and always include same-design siblings (identical printed text, different garment) when one of them makes the list.
3. **Get the 3 refused products into the catalog**, by retrying on another allowed model or writing their entries by hand and marking them as such.
4. **Check confidence against right and wrong answers** once the larger test set produces some misses.

## Bottom line

For the job it's meant to do, flagging people wearing Campus Customs products for outreach, the agent works on every example it was given. It explains its answers, uses at most 7 images per photo (1 when there's no Yale branding), and finishes four photos in a few seconds. The next step is a harder, larger test set, not a redesign.
