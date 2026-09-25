# Agent Harness — How We Keep the Sales Agent Under Control

The sales agent reads a plain-English request, researches companies on the open web, and returns either a company profile or a list of customer targets with drafted emails. It runs on its own, with no human approving each step.

That autonomy is the risk. This document is the short version of how the agent is boxed in: what it can do, when it must stop, and what it is never allowed to get wrong. No knowledge of the agent's code or command line is needed to read it.

## 1. Tools — a deliberately small set

The agent can only affect the world through four tools. Everything else is closed to it.

| Tool | What it does | Why it is safe |
| --- | --- | --- |
| **Search the web** | Returns search results for a query | Read-only. Capped per run. Big marketplaces (Amazon, eBay, Walmart, AliExpress, Alibaba, Temu) are blocked so results are real brands, not listings |
| **List a page's links** | Loads one page and returns its text *plus* the links on it | One page load answers two questions, so the agent plans its route cheaply instead of guessing URLs |
| **Read a page** | Returns one page's text, the shop platform it runs on, and any email addresses published on it | Read-only |
| **Return the answer** | Hands back the finished profile or target list | Structured and checked before it counts as done |

What the agent **cannot** do, by construction: send email, fill in a form, log in, buy anything, write to any file it chooses, or run code. It reads public web pages and writes its results to three known output files. Nothing it produces reaches a customer without a person deciding to send it.

Two facts that matter most for judging a prospect — **which shop platform a site runs on** and **which email addresses it publishes** — are extracted by plain code from the page itself, not inferred by the model. The agent cannot hallucinate an email address into existence, and it cannot talk itself into believing a site qualifies when the markup says otherwise.

## 2. Stopping rules — every run is on a meter

The agent never decides for itself when it has done enough. Each run is issued a fixed allowance and stops when any single limit is hit. Research runs get a bigger allowance than single-company briefs.

| Limit | Company brief | Finding customers | Stops |
| --- | --- | --- | --- |
| Page loads | 8 | 22 | Endless crawling |
| Pages per site | 8 | 4 | Sinking the whole budget into one company |
| Text passed to the model | 40k chars | 90k chars | Token costs creeping up quietly |
| Web searches | 3 | 8 | Search-and-hope loops |
| Model calls per run | 14 | 40 | An agent that keeps "thinking" |
| Tool calls per run | 12 | 60 | Tool-call spirals |
| Tokens per run | 400k | 400k | Runaway spend |
| Wall clock | 5 min | 12 min | A stalled call hanging forever |

Supporting caps: each page returns at most 6,000 characters, images and styling never download, a page that will not load within 20 seconds is abandoned, and a failing tool is retried twice and then given up on.

When a budget runs out, the agent is told so in plain language and instructed to answer from what it already has. Running short produces a shorter, honest answer — not a stall, and not invented filler.

**A run that hangs or is interrupted still reports.** This was a real failure we hit in testing: a stalled model call ran for eighteen minutes and left no record at all. Now the wall clock stops it, and timeouts and manual interruptions are both written to the log with whatever work was completed.

## 3. Guardrails — what it must not get wrong

**It stays where it belongs.** A company brief is locked to that company's own website; the agent cannot wander onto other domains. When prospecting it may visit many sites, but only a few pages each.

**Claims must be traceable.** Every proposed customer has to cite pages on that company's *own* site as evidence. A target backed by nothing, or backed only by third-party pages, is rejected automatically and the agent has to try again.

**Bad targets are refused, not argued about.** The agent judges each candidate, but its judgment is then enforced by code. Anything it flags as a competitor or a household-name brand is thrown out. So is the seller's own company, a duplicate of another target, and a token-effort email. The agent cannot mark a target as questionable and keep it anyway.

**Drafts are drafts.** Outreach emails are written to a file marked as unsent, and the agent has no ability to send mail. A person reads and sends them. Each draft also lists the facts from the company's site it leans on, so a reviewer can check its claims quickly.

**Honest gaps.** When a site publishes no email, the agent says so and still writes the draft rather than inventing an address. What the research could not establish is recorded as an open question.

## 4. The audit trail

Every run appends a full record to `output/audit_log.json`: date and time, the request, the mode, each loop iteration with the agent's stated reasoning, every tool call with its arguments and a summary of what came back, tokens used, budget consumed, pages read, how the run ended, and the final result.

This is the accountability layer. Anyone can open that file afterwards and reconstruct exactly what the agent did, what it spent, what it read, and why it reached its conclusions — including for runs that failed, timed out, or were cut short.
