# AI Prompts Log — Homework 3

This file tracks the prompts used with Claude for each problem in Homework 3. There is one section per problem, each with the problem number and title, at least one prompt I typed, and a follow-up prompt if one was needed (with one sentence on what was lacking after the first).

---

## Problem 1: Vibe Coder Prompts

**Prompt 1:**
> Problem 1: Vibe coder prompts.

**Follow-up prompt (if needed):**
> Set up like previous homework problems.

**What was lacking after the first prompt:**
The first prompt only named the problem, so it didn't say how the prompt log should be laid out.

---

## Problem 2: Build the Product Catalog

**Prompt 1:**
> Problem 2: Build the product catalog.
>
> * Write build_catalog.py that turns every product photo in data/products into a structured catalog entry.
> * Save the full catalog to output/catalog.json, and then put the catalog entry type in models.py as a Pydantic AI model.
> * There are many images, so figure out a way to speed up your code so it does not grind through all of them one image at a time.
> * Choose the most quick loop.
>
> Start output/harness.md in it. Write how you speed up the catalog build, which fields are in your catalog model in models.py, and why you chose those fields.

**Follow-up prompt (if needed):**
>

**What was lacking after the first prompt:**

---

## Problem 3: Product Identify Agent

**Prompt 1:**
> Problem 3: Product Identify Agent. Build a campus customs agent as four files:
>
> * prompts/prompts.md: This is the system prompt. Load into the agent we will add to this later.
> * agents.py: This will be the Pydantic AI agent entry point.
> * tools.py
> * models.py
>
> Its first ability: take an image and decide whether a campus customs product appears in it and which one, if you can tell. Implement that tool logic in tools.py and wire it from agents.py.
>
> Find a way to do this without checking every catalog image one at a time and without sending more than 10. Add the structured return type for this ability to models.py.
>
> The agent must take a image path from the terminal. python agent.py --image "data/test_images/example.jpg"
>
> Agent.py is your campus customs agent entry point. `--image` is the photo to check for campus customs product, and then replace the path to the real file under data when you test. Save the agent's structured output for this run to output/identify_product.json. One test image is enough.
>
> In output/harness.md, write how your agent does product identification and what you did to make it efficient. Which fields are in your identity model in models.py, and why you chose those fields?

**Follow-up prompt (if needed):**
>

**What was lacking after the first prompt:**

---
