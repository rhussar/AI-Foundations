# AI Prompts Log — Homework 2

This file tracks the prompts used with Claude for each problem in Homework 2.

---

## Problem 1: Vibe Coder Prompts

**Prompt 1:**
>

**Follow-up prompt (if needed):**
>

---

## Problem 2: Seller Brief

**Prompt 1:**
> Problem 2: Seller Brief. We will be building a sales agent for the company BuyScout.ai. Create assets-seller_brief.md that records:
>
> * the company name and its website URL
> * the reason I chose this company, which is that it's a company that I'm advising right now
> * specific information: who some of their existing customers are, what they're offering, and where they may be going in the future

---

## Problem 4: Build Agent Plus Profile Run

**Prompt 1:**
> Problem 4: Build agent plus profile run. Now I want you to build a Pydantic AI agent in sales_agent.py that loads prompts/sales_agent.md into its prompt. Use the Playwright web crawler package to help give the sales agent the tools needed to scrape the company website.
>
> From the input query text, the agent should figure out what the human actually wants. I'm going to want it to build a profile of the given company and give it harness pieces to keep costs low
>
> Every time we run the agent, it should write its agent loop iterations, date and time, thoughts, tool calls, names, plus argument, plus result summary when the run stops, to output/audit_log.json.

---

## Problem 5: Expand Prompt + Find Customers

**Prompt 1:**
> Problem 5: Expand prompt + find customers.
>
> Add instructions to the prompts - sales agent.md file on how we can find companies and draft outreach emails when the human asks for customers.
>
> 1. The agent should, in one loop, read the company profile and search the web for potential customers.
> 2. Make sure that it's actually a good target, not a random business, a competitor, or a famous name.
> 3. Look through each candidate's website for useful business contacts and an email.
> 4. Draft an outreach email, but do not send.
>
> Save the results in output targets JSON, so the company info and emails are in the output in emails.json.
>
> Make sure you have the agent update the audit tracker in output audit_log.
>
> I then want to run the agent to find 3 customer with python sales_agent.py "Find 3 good customer targets for this company and draft outreach emails." --profile assets/company_profile.json

---

## Problem 6: Agent Harness Summary

**Prompt 1:**
> Problem 6: Agent Harness Summary create harness.md as a project root. This will be a short summary of how we keep the agent under control. Cover tools, stopping rules, and guardrails. Keep it readable such that we don't need to understand the sales agent UI.

---

## Problem 7: Rank Targets and Emails

**Prompt 1:**
> Problem 7: Rank targets and emails.
>
> Include this reflection in output reflection.md:
>
> Looking for e-commerce CEOs doing 100,000 to 1 million a year in sales; we want outreach emails to be respectful, clear, and to leave the fact that we're young entrepreneurs. The best company would be one doing 2,000 to 50,000 in sales, starting to grow, looking to level up their platform. The worst would be someone under 10k yearly.

---

## Problem 8: Sales Dashboard Webpage

**Prompt 1:**
> Problem 8: Sales Dashboard Webpage
>
> Now build a webpage, dashboard.html, that shows the company profile, target customers, and drafted emails in a way that humans can skim. Humans should be able to open the page and see who the seller is, who the targets are, contact info, and the drafted email.
>
> Make it feel like a classic SaaS dashboard. But I want everywhere the cursor goes to have this hover behind it.
>
> Put the profile targets and emails into the HTML itself. Do not make the page read JSON files when it opens.

---

**Follow-up prompt:**
> Make it a light screen. Clean it up entirely. None of the left tabs work. There's a lot of bloat everywhere. It feels very vibe coded

---

**Follow-up prompt 2:**
> Okay, I don't like how we have to scroll down on the dashboard. Make it all on one visibility, and then use the left tabs to switch tabs or something like that. Make one of the left things be overview of our company, and then the other one can be customers. When we click on customers, on the top there's a new bar that lets me select which customer I want. And then, under "How This Was Made," just leave that as is.

---

## Problem 9: Submit Zip

**Prompt 1:**
> Problem 9 submit Zip
>
> Put everything in a folder named hw2, zip it as hw2.zip.
>
> Do not include the .env file. (Screenshot provided showing the expected folder layout.)

---
