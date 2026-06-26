#!/usr/bin/env python3
"""Build a read-only monthly GTM health report from GetSales and SmartLead data."""

import argparse
import csv
import html
import json
import shutil
import subprocess
import sys
from calendar import monthrange
from datetime import date
from pathlib import Path


EXIT_INPUT = 4


def load_json(path, label):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: {label} not found: {path}", file=sys.stderr)
        sys.exit(EXIT_INPUT)
    except json.JSONDecodeError as e:
        print(f"ERROR: {label} malformed JSON: {path}: {e}", file=sys.stderr)
        sys.exit(EXIT_INPUT)


def ensure_output_dir(path):
    output_dir = Path(path)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n")


def run_json(command, cwd):
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        print(result.stderr.strip() or result.stdout.strip(), file=sys.stderr)
        sys.exit(result.returncode)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"ERROR: command did not return JSON: {' '.join(command)}: {e}", file=sys.stderr)
        sys.exit(EXIT_INPUT)


def parse_month(month):
    try:
        year, month_num = [int(part) for part in month.split("-", 1)]
        last_day = monthrange(year, month_num)[1]
        return date(year, month_num, 1).isoformat(), date(year, month_num, last_day).isoformat()
    except Exception:
        print("ERROR: --month must use YYYY-MM format", file=sys.stderr)
        sys.exit(EXIT_INPUT)


def read_reply_queue(path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def render_html(month, getsales_summary, smartlead_metrics, reply_rows):
    buckets = getsales_summary.get("buckets") or getsales_summary.get("classification_counts") or {}
    smartlead_summary = smartlead_metrics.get("summary", smartlead_metrics)
    reply_rows_html = "\n".join(
        "<tr>"
        f"<td>{html.escape(row.get('bucket', ''))}</td>"
        f"<td>{html.escape(row.get('reply_intent', ''))}</td>"
        f"<td>{html.escape(row.get('lead_uuid', ''))}</td>"
        f"<td>{html.escape((row.get('text') or '')[:160])}</td>"
        "</tr>"
        for row in reply_rows[:25]
    )
    bucket_cards = "\n".join(
        f"<div class='metric'><span>{html.escape(str(name))}</span><strong>{count}</strong></div>"
        for name, count in buckets.items()
    )
    metric_cards = "\n".join(
        f"<div class='metric'><span>{html.escape(str(name))}</span><strong>{html.escape(str(value))}</strong></div>"
        for name, value in smartlead_summary.items()
        if isinstance(value, (int, float, str))
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Monthly GTM Health Report - {html.escape(month)}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #15171a;
      --muted: #68707c;
      --line: #d8dde5;
      --panel: #f7f9fb;
      --accent: #176b87;
      --warn: #b45309;
      --good: #157347;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: #ffffff;
    }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 40px 28px; }}
    header {{ border-bottom: 1px solid var(--line); padding-bottom: 24px; margin-bottom: 28px; }}
    h1 {{ font-size: 34px; line-height: 1.1; margin: 0 0 8px; letter-spacing: 0; }}
    h2 {{ font-size: 18px; margin: 32px 0 14px; letter-spacing: 0; }}
    p {{ color: var(--muted); margin: 0; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; }}
    .metric {{ border: 1px solid var(--line); border-radius: 8px; padding: 14px; background: var(--panel); }}
    .metric span {{ display: block; color: var(--muted); font-size: 12px; text-transform: uppercase; }}
    .metric strong {{ display: block; margin-top: 8px; font-size: 24px; }}
    table {{ width: 100%; border-collapse: collapse; border: 1px solid var(--line); }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ background: var(--panel); font-size: 12px; text-transform: uppercase; color: var(--muted); }}
    .note {{ margin-top: 22px; color: var(--muted); font-size: 13px; }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Monthly GTM Health Report</h1>
      <p>{html.escape(month)} · read-only SmartLead metrics + GetSales reply queues</p>
    </header>
    <section>
      <h2>GetSales Reply Actions</h2>
      <div class="grid">{bucket_cards}</div>
    </section>
    <section>
      <h2>SmartLead Metrics</h2>
      <div class="grid">{metric_cards}</div>
    </section>
    <section>
      <h2>Reply Action Queue Preview</h2>
      <table>
        <thead><tr><th>Bucket</th><th>Intent</th><th>Lead</th><th>Text</th></tr></thead>
        <tbody>{reply_rows_html}</tbody>
      </table>
    </section>
    <p class="note">No production writes were performed. Live uploads remain outside this report workflow.</p>
  </main>
</body>
</html>
"""


def build_from_fixtures(args, output_dir):
    fixture_dir = Path(args.from_fixtures)
    getsales_summary = load_json(fixture_dir / "getsales_reply_summary.json", "GetSales fixture")
    smartlead_metrics = load_json(fixture_dir / "smartlead_metrics.json", "SmartLead fixture")
    queue_src = fixture_dir / "reply_action_queue.csv"
    if not queue_src.exists():
        print(f"ERROR: reply queue fixture not found: {queue_src}", file=sys.stderr)
        sys.exit(EXIT_INPUT)
    queue_dst = output_dir / "reply_action_queue.csv"
    shutil.copyfile(queue_src, queue_dst)
    return getsales_summary, smartlead_metrics, read_reply_queue(queue_dst)


def build_from_cli(args, output_dir, repo_root):
    if not args.getsales_automation or not args.smartlead_campaign_id:
        print(
            "ERROR: live read mode requires --getsales-automation and --smartlead-campaign-id",
            file=sys.stderr,
        )
        sys.exit(EXIT_INPUT)

    start_date, end_date = parse_month(args.month)
    triage_dir = output_dir / "getsales_reply_triage"
    subprocess.run(
        [
            sys.executable,
            str(repo_root / "getsales" / "getsales.py"),
            "reply-triage",
            "--automation",
            args.getsales_automation,
            "--output-dir",
            str(triage_dir),
            "--json",
        ],
        cwd=repo_root,
        check=True,
    )
    getsales_summary = load_json(triage_dir / "summary.json", "GetSales summary")
    smartlead_metrics = run_json(
        [
            sys.executable,
            str(repo_root / "smartlead" / "smartlead.py"),
            "analytics-dates",
            str(args.smartlead_campaign_id),
            "--start-date",
            start_date,
            "--end-date",
            end_date,
        ],
        cwd=repo_root,
    )
    queue_dst = output_dir / "reply_action_queue.csv"
    shutil.copyfile(triage_dir / "reply_now.csv", queue_dst)
    return getsales_summary, smartlead_metrics, read_reply_queue(queue_dst)


def main():
    parser = argparse.ArgumentParser(description="Build a read-only monthly GTM report")
    parser.add_argument("--getsales-automation")
    parser.add_argument("--smartlead-campaign-id")
    parser.add_argument("--month", required=True, help="YYYY-MM")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--from-fixtures", help="Use public-safe fixtures instead of API calls")
    args = parser.parse_args()

    output_dir = ensure_output_dir(args.output_dir)
    repo_root = Path(__file__).resolve().parents[1]

    if args.from_fixtures:
        getsales_summary, smartlead_metrics, reply_rows = build_from_fixtures(args, output_dir)
    else:
        getsales_summary, smartlead_metrics, reply_rows = build_from_cli(args, output_dir, repo_root)

    write_json(output_dir / "getsales_reply_summary.json", getsales_summary)
    write_json(output_dir / "smartlead_metrics.json", smartlead_metrics)
    report_html = render_html(args.month, getsales_summary, smartlead_metrics, reply_rows)
    (output_dir / "monthly_report.html").write_text(report_html, encoding="utf-8")

    print(f"Monthly report generated: {output_dir / 'monthly_report.html'}")
    print(f"- reply queue: {output_dir / 'reply_action_queue.csv'}")
    print(f"- SmartLead metrics: {output_dir / 'smartlead_metrics.json'}")
    print(f"- GetSales summary: {output_dir / 'getsales_reply_summary.json'}")


if __name__ == "__main__":
    main()
