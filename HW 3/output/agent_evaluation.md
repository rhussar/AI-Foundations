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

---

# Ad runs — judging the Campus Customs ad for a student and a parent

**Verdict: the agent's analysis is good; its score isn't yet.** It read the ad accurately, found the ad's real weaknesses, and reasoned about each customer in very different, profile-specific terms. It gave both customers the same 5/10, though, even though its own point-by-point analysis says the ad fits the parent clearly worse. The written judgement is useful to a marketer today. The number shouldn't be used to compare customers until the score is tied more closely to the analysis.

## How it was run

```bash
python agent.py --video "data/videos/ad_humble.mp4" --profile "profiles/profile_student.json"
python agent.py --video "data/videos/ad_humble.mp4" --profile "profiles/profile_parent.json"
```

Model `gpt-5.6-luna` via Portkey. Both results are in `output/ad_effectiveness.json`, which has 2 entries because separate runs merge.

| | Student (Maya, 19) | Parent (Tom, 53) |
| --- | --- | --- |
| Score / response | **5/10, might shop** | **5/10, might shop** |
| Confidence | medium (capped: soundtrack not heard) | medium (capped: soundtrack not heard) |
| Profile fit | 1 strong · 4 partial · 3 none · 0 negative | 1 strong · 2 partial · 4 none · **1 negative** |
| Main reasons | Muted streetwear look and group belonging fit her; no brand, price, student deal or way to buy; basic designs she half-owns already | Classic navy basics fit his style; the young, music-video cast makes it feel "for someone else"; no quality, gifting, occasion or trust details |
| Time and tokens | 16.9 s, 7,543 in / 1,789 out (includes watching the video) | 8.8 s, 2,993 in / 835 out (video analysis reused from the cache) |

## What's good

1. **An accurate read of the ad.** I checked the frames myself. The analysis is right that it's a 9-second, landscape, music-video-style clip of a lead in an arched "YALE" navy hoodie under a highway overpass, with a crowd in Yale gear, and **no Campus Customs name, no on-screen text and no call to action anywhere**. That last point is the ad's biggest real problem, and both judgements lead with it.
2. **Genuinely profile-specific reasoning.** Almost nothing is shared between the two judgements beyond the missing branding:
   - For Maya: price sensitivity, phone-first buying, "how is this different from the bookstore?", and landscape video being weaker on TikTok and Reels.
   - For Tom: quality, sizing and returns, gifting and occasions (Family Weekend, Commencement), the sound-off Facebook habit, and the ad feeling aimed at students (marked **negative**).
   Each point cites the profile field it comes from, which makes the judgements easy to check.
3. **Actionable fixes.** For example: "add Campus Customs branding, student pricing or a limited event drop, and a phone-friendly call to action" for Maya; "recast the message for proud Yale parents and gifting occasions" for Tom. A marketer could brief an editor from either list.
4. **Honest about what it can't hear.** The provider refused the audio in both runs, and both judgements say so in their misses and keep confidence at medium. None of them invents lyrics.
5. **The Problem 5 run's mistakes didn't come back.** Its "high" confidence without audio is now capped. Its "vertical video" claim is gone: the judge was given the real format and used it correctly ("the landscape format is a weaker fit for her … Reels habits").
6. **Efficient.** The parent run reused the student run's video analysis: no frames were re-sent, and it used less than half the tokens and time.

## What's not good yet

1. **The score doesn't separate the customers.** The parent's fit is clearly worse by the agent's own table (a negative point and 4 "none" against the student's 0 negatives and 3 "none"), yet both scores are 5. The model seems to anchor on the ad's general quality rather than on the fit it just listed. Right now, the written judgement is more trustworthy than the number.
2. **The soundtrack isn't judged at all.** A parody of a song ("ad_humble") gets much of its meaning from the music and lyrics, and the provider behind Portkey accepts only text and images. The visual judgement is sound, but it covers half the ad. Both verdicts rightly flag this.
3. **An uncertain detail was treated as fact.** The video analysis says a group "stands around a person dressed in black lying on the dirt" (1.5 s). Looking at the frame, it could be a person or a pile of black coats. The student judgement then calls it a possibly off-putting image. It's minor, but it shows the judge trusts every line of the description equally.
4. **Neither the profiles nor the judgements were checked against real people.** I wrote both personas. A real student or parent watching the ad is the only real test of whether "5/10, might shop" is right.

## What I'd do next

1. **Tie the score to the analysis:** have the judge score after listing the fit, and check in code that more `negative`/`none` points can't produce the same or a higher score than a better fit. Or compute a fit score from the table and have the model explain any gap.
2. **Get the soundtrack in**, through a provider route that accepts audio or a transcription step, and re-judge.
3. **Ask the vision step to mark uncertain details** ("possibly a person lying down") so the judge can weigh them.
4. **Test on more ads**, including a deliberately good one (branded, with a call to action) and a clearly wrong-audience one. The scores should spread out; if everything lands on 5, the scale isn't working.
