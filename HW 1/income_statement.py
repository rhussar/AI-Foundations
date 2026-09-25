import argparse
import json
from pathlib import Path


DEFAULT_JSON_DIR = Path(__file__).resolve().parent / "output"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def parse_args():
    parser = argparse.ArgumentParser(description="Build a January income statement from the reconciliation log.")
    parser.add_argument("--json-dir", type=Path, default=DEFAULT_JSON_DIR, help="Directory containing reconciliation_log.json")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory to write the income statement JSON")
    return parser.parse_args()


def load_reconciliation_log(json_dir: Path):
    log_path = json_dir / "reconciliation_log.json"
    if not log_path.exists():
        raise FileNotFoundError(f"reconciliation_log.json not found in {json_dir}")
    return json.loads(log_path.read_text(encoding="utf-8"))


def build_income_statement(rows):
    revenues = []
    expenses = []

    for row in rows:
        if str(row.get("included_income_statement", "")).lower() != "yes":
            continue

        amount = float(row.get("amounts_used_income_statement", 0) or 0)
        if amount <= 0:
            continue

        sources = row.get("sources", [])
        label = row.get("ID", "Unknown")

        if "revenue" in str(row.get("resolution", "")).lower() or "deposit" in str(row.get("resolution", "")).lower():
            revenues.append({
                "label": label,
                "amount_USD": round(amount, 2),
                "sources": sources,
            })
        else:
            expenses.append({
                "label": label,
                "amount_USD": round(amount, 2),
                "category": "reconciled expense",
                "sources": sources,
            })

    revenue_total = round(sum(item["amount_USD"] for item in revenues), 2)
    expense_total = round(sum(item["amount_USD"] for item in expenses), 2)
    net_income = round(revenue_total - expense_total, 2)

    statement = {
        "revenue_USD": revenue_total,
        "expense_lines": expenses,
        "Total_expenses_USD": expense_total,
        "net_income_USD": net_income,
    }
    return statement


def main():
    args = parse_args()
    json_dir = args.json_dir.resolve()
    out_dir = args.out_dir.resolve()

    rows = load_reconciliation_log(json_dir)
    statement = build_income_statement(rows)

    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / "income_statement_Jan_2026.json"
    output_path.write_text(json.dumps(statement, indent=2), encoding="utf-8")
    print(f"Saved income statement to {output_path}")


if __name__ == "__main__":
    main()
