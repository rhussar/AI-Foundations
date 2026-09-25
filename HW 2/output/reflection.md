# Reflection — Ranking the Targets and Emails

## The reflection (as given)

> Looking for e-commerce CEOs doing 100,000 to 1 million a year in sales; we want outreach emails to be respectful, clear, and to leave the fact that we're young entrepreneurs. The best company would be one doing 2,000 to 50,000 in sales, starting to grow, looking to level up their platform. The worst would be someone under 10k yearly.

### How I read it

- **Buyer:** the CEO or founder, not a support alias — someone who can decide.
- **Size band:** $100k–$1M a year. The "2,000 to 50,000" best case reads as *monthly* revenue (≈$24k–$600k a year), which sits inside that band; the "under 10k yearly" floor is the hard reject.
- **Stage:** starting to grow and looking to level up their platform — past proving the product, not yet tooled up.
- **Tone:** respectful and clear, and open about being young entrepreneurs rather than hiding it.

*One thing to confirm: whether "2,000 to 50,000" is monthly, and whether "leave the fact that we're young entrepreneurs" means leave it **in**. I read both that way below.*

## Ranking the targets

Judged against the band above, the headline result is that **all three current targets are too big**. The agent screened out household names and confirmed each runs on Shopify, but it never applied a revenue test — nothing in its screen asks how big a company is. The ranking is therefore "least wrong" to "most wrong".

| Rank | Company | Read on size | Verdict |
| --- | --- | --- | --- |
| 1 | **COCOLAB / Cocofloss** | Specialist oral-care brand, narrow product system, but runs partnerships, press, and dental-professional channels | Closest to the brief, still above the band |
| 2 | **OSEA Malibu** | Family-owned but long-established, broad catalog, subscription program, retail presence, staffed customer-care and "skincare studio" desks | Too big — a staffed support org means they already solved this |
| 3 | **Pela** | Claims 2M+ customers, multi-currency international storefront, several accessory lines | Furthest off — well past $1M and likely has in-house tooling |

Why Cocofloss ranks first: it is the one with a real "level up the platform" story — a quiz, subscriptions, and a product system that is getting more complicated — which matches the stage you described. Why Pela ranks last: scale is exactly what disqualifies it; a brand that size buys software through a process, not a cold email.

**The honest conclusion:** under your stated screen, this run produced zero qualified targets. The agent optimized for catalog complexity — the thing that makes the product useful — and ignored company size, the thing that makes the deal reachable.

## Ranking the emails

All three are respectful and clear, and none invent facts. None of them, however, do the two things you asked for: they are addressed to a company "team" rather than a CEO, and not one mentions that we are young entrepreneurs.

| Rank | Email | Strength | Weakness |
| --- | --- | --- | --- |
| 1 | **Pela** | Sharpest hook — device compatibility across iPhone, Pixel, and Galaxy is a concrete, checkable problem | Generic `hello@` inbox; no named recipient |
| 2 | **OSEA Malibu** | Specific detail (concern-based categories, quiz, subscriptions) and sent to a product-side inbox | "That breadth can make it difficult…" is a soft, recycled framing |
| 3 | **COCOLAB** | Correctly names their actual product lines | Sent to `partnerships@`, which is the collabs door, not the CEO's; reuses OSEA's claim sentence almost verbatim, so it reads templated |

Common issues across all three: the same three-paragraph skeleton and the same closing ask, which is a tell if two land in the same inbox; the sign-off is an anonymous "BuyScout.ai team" with no human behind it; and the value claim leans on "customer stories reporting…" in each one.

## What to change before the next run

1. **Add a size gate to the screen.** The agent has no revenue test. Cheap proxies it can actually read from a site: stocked in Sephora/Target/major retail, a press page full of national coverage, a careers page with open roles, a wholesale program, or a staffed multi-desk contact page all mean *too big*. A single founder story, a modest catalog, no retail distribution, and one shared inbox mean the right size.
2. **Aim at the founder.** Rank a named founder or CEO address above `hello@` or `partnerships@`, and say in the draft who the intended reader is.
3. **Say who we are.** Add a short, plain line that we are young entrepreneurs building this — stated as a fact, without apology and without a pitch about it.
4. **Break the template.** Require each draft to open on a different kind of detail so three emails never share a skeleton or a claim sentence.
5. **Drop the floor explicitly.** Anything reading under ~$10k a year — a handful of products, a dormant blog, no reviews — should be rejected by name in `rejected_candidates`, so the screen is visible in the output.

Items 1–4 are prompt changes; item 5 is worth enforcing in code, the same way competitor and household-name flags already are.
