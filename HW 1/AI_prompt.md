# AI Prompt Log for Homework 1

This file records the prompts used while working on Homework 1. Add each new user prompt under the relevant problem section as work continues.

## Session Startup Prompt

- Date: 2026-09-11
- Prompt:
  > We will begin work on homework 1. Open the folder and create AI_prompt.md, and I want you to record all prompts that I give you.
  >
  > And then we will begin problems 2 through 9. Each section must include the problem number and title, and the prompts I use for that.

---

## Problem 2

- Problem title: Read receipts
- Prompts used:
  - "Problem 2: Read receipts. Create a script called read_receipts.py. This will call an LLM using the prompt in prompts/receipts_extract.md to extract one row per purchase receipt PDF in the document pack, then save that as a JSON array on those two rows to output/receipts.json."
  - "Each row in JSON:"
    - Vendor
    - Date
    - Description
    - Amount_USD
    - Category
    - source_file
    - "Put any missing fields in fields_not_found."

## Problem 3

- Problem title: Read bank statement
- Prompts used:
  - "Problem 3. Read bank statement. All right, I'll create a script in read_bank.py that calls the LLM using the prompt in prompts/bank_extract.md. It will extract it from the bank statement January 2026 PDF, and it'll save a JSON array of those rows to output/bank_transactions.json."
  - "The output must include:"
    - Date
    - Description
    - Amount_USD
    - Classification (if it's a business or personal)
    - Direction (credit or debit)
    - Accounting label
    - Expense type
  - "It should run with this command format: python read_bank.py --docs-dir PATH --out-dir output"

## Problem 4

- Problem title: Read credit card statement
- Prompts used:
  - "Problem 4: Read credit card statement. Create a script read_card.py that calls an LLM from the prompt in AI_prompt.md, then takes it from credit_card_Jan_2026, and saves a JSON array to output credit_card_transactions.json."
  - "It must include:"
    - Date
    - Merchant
    - Amount_USD
    - Classification (if it's business or personal)
    - Expense category (null for personal rows)
  - "Run with: python read_card.py --docs-dir PATH --out-dir output"

## Problem 5

- Problem title: Reconciliation log
- Prompts used:
  - "Problem 5: Reconciliation log Create a script reconcile.py that calls an LLM from the prompts in reconcile.md to sort out amounts that appear in more than one document or need a single income statement decision. Each row in the log is a reconciled amount."
  - "Pass in the outputs from the previous problems, plus text from relevant documents, and then save all this in a JSON array to output/reconciliation_log.json."
  - "Must include:"
    - an ID
    - sources
    - amounts seen
    - included_income_statement (This is a yes or no)
    - amounts_used_income_statement (0 if excluded)
    - resolution (your thoughts)
  - "run with python reconcile.py --docs-dir PATH --json-dir output --out-dir output"

## Problem 6

- Problem title: Judgment calls
- Prompts used:
  - "Problem 6: Judgment calls. Create a script to identify the three rows from the reconciliation log where the judgment was hardest to make and save them in output/judgment_calls.json."
  - "For each judgment call, include:"
    - the transaction ID
    - the included_income_statement
    - the amount used in income statement
    - evidence (a bullet list with document names and confidence of high, medium, or low) - at least one must be low
  - "Follow-up prompt: make confidence its own row. No longer is it in the evidence for each item. The evidence should only list document names, and the confidence should be a separate field with values of high, medium, or low."

## Problem 7

- Problem title: January income statement
- Prompts used:
  - "Problem 7: January income statement Create a script income_statement.py that takes the reconciliation log, rolls every row with "Included in Income Statement" set to "Yes" into revenue and expense lines, and then saves the output to income_statement_Jan_2026.json in output."
  - "Do not hardcode values. Math can be done in Python."
  - "JSON must include:"
    - period
    - revenue_USD
    - expense_lines, each with their own label, amount_USD, category, and sources
    - Total_expenses_USD
    - net_income_USD
  - "run with: python income_statement.py --json-dir output --out-dir output"

- I need you to add period (2026-01). Add this to problem 7 notes in the prompt.md.
- No, I meant to also make sure that the JSON includes the period.

- Ronan Note: This prompt took three prompts because the first one, I forgot to add. When I asked it to fix it, it did not do a good job. I had to clarify a third time. 

## Problem 8

- Problem title: Income statement web page
- Prompts used:
  - "Problem 8: income statement web page. Create a script report.py that reads the JSON files from output and builds a one-page HTML summary. Save the page to the output folder as income_statement.html. Use the same numbers as the JSON."
  - "Include the January income statement, personal and business rows you excluded from your income statement, and the three judgment calls from problem 6."
  - "The script should run with python report.py --json-dir output --out output/income_statement.html"

## Problem 9

- Problem title: Process Flow Diagram
- Prompts used:
  - "Problem 9: Process Flow Diagram. Create a one-page HTML file in the output titled pipeline.html with a block diagram of everything we've done. Look back at all problems 2 through 8: one block per script, plus blocks for key inputs, document pack PDFs, etc., and outputs (whether it's a JSON or HTML file). Show arrows for inputs to output, mark where the LLM is called."
  - "It must make clear:"
    - each script name
    - what it reads and writes
    - which steps call it LLM
    - the path from the document pack to income_statement.html

---

## Notes

- Keep each section in the format: "Problem X - [Title]".
- Each prompt given by the user should be added under the matching problem number as the work proceeds.
- This log is meant to capture all prompts used during the homework process.
