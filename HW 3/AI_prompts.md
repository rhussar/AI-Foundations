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

## Problem 4: Test Identify on 4 Images

**Prompt 1:**
> Problem 4: Test identify on 4 images. Run the agent on four photos in data/test images. Each file name tells you the ground truth, whether it's true or not. Save the agent's output for all four images to output/identify_product.json. Each entry should match the identify.pydantic AI model you put in models.py. Then evaluate the performance. Was it good? Was it bad? Save the write-up in output/agent_evaluation.md.

**Follow-up prompt (if needed):**
>

**What was lacking after the first prompt:**

---

## Problem 5: Add Ad-Effectiveness Ability

**Prompt 1:**
> Problem 5: Add the abilities to the agent. Can take a video and a customer profile JSON file, then judge how effective the video would be at convincing that customer to shop at campus customs.
>
> * Put the new tool code in tools.py.
> * Update the same prompts in prompts.md so the agent knows how to use this new ability.
> * Do not start a second prompt file.
> * Put the structure result type for this ability in models.py as a pydantic model.
> * Wire the terminal the same way you will use in problem 7: python agent.py --video "data/videos/ad_humble.mp4" --profile "profiles/profile_student.json"
>
> Save the agent structure output for this run to output/ad_effectiveness.json. One profile is enough here.
>
> In output/harness.md, write the tools you gave the agent for the video plus profile job. Which fields are you using in your ad effectiveness model in models.py, and why did you choose those fields?

**Follow-up prompt (if needed):**
>

**What was lacking after the first prompt:**

---

## Problem 6: Student and Parent Profiles

**Prompt 1:**
> Problem 6: Student and parent profiles.
>
> Create profiles/profile_student.json and profiles/profile_parent.json. These describe a typical Yale student and parent of a Yale student, or any student or parent you like, including yourself. Include useful fields that would matter for whether an ad resonates. Define the profile shape in models.py as a Pydantic model, then save the filled-in student and parent instance as those JSON files.
>
> In output harness.md, explain why you chose those two profiles.
> Run the agent on the Campus Customs ad video for both profiles:
> python agent.py --video "data/videos/ad_humble.mp4" --profile "profiles/profile_student.json"
> python agent.py --video "data/videos/ad_humble.mp4" --profile "profiles/profile_parent.json"
>
> Save the structural result for both runs to output/add effectiveness.json.
>
> Write what you think in output/agent_valuation.md. Add a new section for ad runs. The output appears to be good.

**Follow-up prompt (if needed):**
>

**What was lacking after the first prompt:**

---
