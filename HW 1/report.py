import argparse
import json
from pathlib import Path


DEFAULT_JSON_DIR = Path(__file__).resolve().parent / "output"


def parse_args():
    parser = argparse.ArgumentParser(description="Build a one-page HTML summary of the January bookkeeping outputs.")
    parser.add_argument("--json-dir", type=Path, default=DEFAULT_JSON_DIR, help="Directory containing the JSON output files")
    parser.add_argument("--out", type=Path, required=True, help="Path to write the HTML report")
    return parser.parse_args()


def load_json(path: Path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def money(value):
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def html_escape(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def build_excluded_rows(json_dir: Path):
    bank_rows = load_json(json_dir / "bank_transactions.json")
    card_rows = load_json(json_dir / "credit_card_transactions.json")
    reconciliation_rows = load_json(json_dir / "reconciliation_log.json")

    personal_rows = []
    for row in bank_rows + card_rows:
        classification = str(row.get("Classification", "")).lower()
        if classification == "personal":
            personal_rows.append({
                "type": "personal",
                "date": row.get("Date"),
                "description": row.get("Description") or row.get("Merchant"),
                "amount": row.get("Amount_USD"),
                "source": row.get("source_file") or row.get("Merchant"),
            })

    business_rows = []
    for row in reconciliation_rows:
        if str(row.get("included_income_statement", "")).lower() == "no":
            business_rows.append({
                "type": "business excluded",
                "date": "n/a",
                "description": row.get("resolution"),
                "amount": row.get("amounts_used_income_statement"),
                "source": ", ".join(row.get("sources", [])),
            })

    return personal_rows, business_rows


def build_income_statement_html(data):
    revenue = data.get("revenue_USD", 0)
    expenses = data.get("expense_lines", [])
    total_expenses = data.get("Total_expenses_USD", 0)
    net_income = data.get("net_income_USD", 0)

    rows_html = "".join(
        """
        <tr>
          <td>{label}</td>
          <td>{category}</td>
          <td>{amount}</td>
          <td>{sources}</td>
        </tr>
        """.format(
            label=html_escape(item.get("label", "")),
            category=html_escape(item.get("category", "")),
            amount=money(item.get("amount_USD", 0)),
            sources=html_escape(", ".join(item.get("sources", []))),
        )
        for item in expenses
    )

    return f"""
    <section>
      <h2>January Income Statement</h2>
      <table>
        <tr><th>Category</th><th>Amount</th></tr>
        <tr><td>Revenue</td><td>{money(revenue)}</td></tr>
        <tr><td colspan="2"><strong>Expenses</strong></td></tr>
        {rows_html}
        <tr class="total"><td>Total Expenses</td><td>{money(total_expenses)}</td></tr>
        <tr class="total"><td>Net Income</td><td>{money(net_income)}</td></tr>
      </table>
    </section>
    """


def build_excluded_html(personal_rows, business_rows):
    personal_html = "".join(
        """
        <tr>
          <td>{date}</td>
          <td>{description}</td>
          <td>{amount}</td>
          <td>{source}</td>
        </tr>
        """.format(
            date=html_escape(row.get("date", "")),
            description=html_escape(row.get("description", "")),
            amount=money(row.get("amount", 0)),
            source=html_escape(str(row.get("source", ""))),
        )
        for row in personal_rows
    )

    business_html = "".join(
        """
        <tr>
          <td>{date}</td>
          <td>{description}</td>
          <td>{amount}</td>
          <td>{source}</td>
        </tr>
        """.format(
            date=html_escape(row.get("date", "")),
            description=html_escape(row.get("description", "")),
            amount=money(row.get("amount", 0)),
            source=html_escape(str(row.get("source", ""))),
        )
        for row in business_rows
    )

    return f"""
    <section>
      <h2>Excluded From Income Statement</h2>
      <h3>Personal Rows Excluded</h3>
      <table>
        <tr><th>Date</th><th>Description</th><th>Amount</th><th>Source</th></tr>
        {personal_html or '<tr><td colspan="4">No personal rows excluded.</td></tr>'}
      </table>
      <h3>Business Rows Excluded</h3>
      <table>
        <tr><th>Date</th><th>Description</th><th>Amount</th><th>Source</th></tr>
        {business_html or '<tr><td colspan="4">No business rows excluded.</td></tr>'}
      </table>
    </section>
    """


def build_judgment_call_html(judgment_calls):
    rows_html = "".join(
        """
        <tr>
          <td>{transaction_id}</td>
          <td>{included}</td>
          <td>{amount}</td>
          <td>{confidence}</td>
          <td>{evidence}</td>
        </tr>
        """.format(
            transaction_id=html_escape(item.get("transaction_id", "")),
            included=html_escape(item.get("included_income_statement", "")),
            amount=money(item.get("amount_used_in_income_statement", 0)),
            confidence=html_escape(item.get("confidence", "")),
            evidence=html_escape("; ".join(item.get("evidence", []))),
        )
        for item in judgment_calls
    )

    return f"""
    <section>
      <h2>Judgment Calls</h2>
      <table>
        <tr><th>Transaction ID</th><th>Included in Income Statement</th><th>Amount Used</th><th>Confidence</th><th>Evidence</th></tr>
        {rows_html}
      </table>
    </section>
    """


def build_html(json_dir: Path):
    statement = load_json(json_dir / "income_statement_Jan_2026.json")
    judgment_calls = load_json(json_dir / "judgment_calls.json")
    personal_rows, business_rows = build_excluded_rows(json_dir)

    html = f"""
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <title>January 2026 Income Statement Summary</title>
      <style>
        body {{ font-family: Arial, sans-serif; margin: 32px; color: #1f2937; background: #f8fafc; }}
        h1, h2, h3 {{ color: #111827; }}
        table {{ border-collapse: collapse; width: 100%; margin-bottom: 24px; background: white; }}
        th, td {{ border: 1px solid #d1d5db; padding: 8px 10px; text-align: left; vertical-align: top; }}
        th {{ background: #e5e7eb; }}
        .total {{ font-weight: bold; background: #f3f4f6; }}
        .small {{ font-size: 0.9em; color: #4b5563; }}
      </style>
    </head>
    <body>
      <h1>January 2026 Summary</h1>
      <p class="small">Prepared from the extracted January bookkeeping outputs.</p>
      {build_income_statement_html(statement)}
      {build_excluded_html(personal_rows, business_rows)}
      {build_judgment_call_html(judgment_calls)}
    </body>
    </html>
    """
    return html


def main():
    args = parse_args()
    json_dir = args.json_dir.resolve()
    out_path = args.out.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    html = build_html(json_dir)
    out_path.write_text(html, encoding="utf-8")
    print(f"Saved HTML report to {out_path}")


if __name__ == "__main__":
    main()
