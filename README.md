# boring-gtm-skills

CLI-first operating layers for GetSales and SmartLead. Boring automation is trustworthy automation.

## What this is

This repository contains CLI-first skills for GetSales and SmartLead. They are not autonomous agents that improvise across production systems. They are constrained workflows: the agent operates through a small CLI layer that knows the safe reads, the dangerous writes, and the approval gates. Writes default to preview or dry-run behavior, and live SmartLead uploads require an explicit `--confirm-live` flag.

The public repository is English-first: skill docs, playbooks, recipes, examples, tests, and CI are written for operators who need a clear production boundary.

## Skills

| Skill | What it does | Safe by default |
|---|---|---|
| GetSales | Lists, contacts, flows, inbox, reply classification | All writes are dry-run by default |
| SmartLead | Campaigns, leads, sequences, analytics | Live uploads require `--confirm-live` |

## Structure

Each skill has three layers:

- `SKILL.md` - when to use it, what's safe, what needs approval
- `PLAYBOOK.md` - how an operator should think through the workflow
- `*.py` - the actual CLI layer

The point is to make the operating surface explicit. The agent should not re-derive the workflow from API docs every time.

## Quickstart - GetSales

```bash
git clone https://github.com/solyarikai/boring-gtm-skills
cd boring-gtm-skills
export GETSALES_API_KEY=your_key_here
python3 getsales/getsales.py lists
python3 getsales/getsales.py reply-intel --limit 50
python3 getsales/getsales.py reply-triage --automation flow_uuid --output-dir tmp/reply_triage
```

## Quickstart - SmartLead

```bash
export SMARTLEAD_API_KEY=your_key_here
python3 smartlead/smartlead.py campaigns
python3 smartlead/smartlead.py sequence-validate examples/smartlead/sequences.sample.json
python3 smartlead/smartlead.py prepare-upload 123 examples/smartlead/leads.valid.json --output-dir tmp/upload_preview
python3 smartlead/smartlead.py leads-add 123 leads.json --dry-run
# add --confirm-live only when you're sure
```

## Safety model

The safety contract is intentionally simple:

- reads can run directly;
- local artifact commands can write files under `--output-dir`;
- write-adjacent commands prepare payloads, summaries, and rejected rows before upload;
- production writes require an explicit live flag;
- blocked unsafe writes return exit code `2`.

See [docs/safety-model.md](docs/safety-model.md), [docs/exit-codes.md](docs/exit-codes.md), and [docs/recipes.md](docs/recipes.md).

## Real-life workflow

Build a monthly GTM health report without production writes:

```bash
python3 scripts/monthly_gtm_report.py \
  --month 2026-06 \
  --from-fixtures examples/reporting \
  --output-dir tmp/monthly_report
```

The report writes `monthly_report.html`, `reply_action_queue.csv`, `smartlead_metrics.json`, and `getsales_reply_summary.json`.

## Adapting to your stack

The public version expects API keys in environment variables. Replace that with your own `.env` setup if you prefer, for example with `python-dotenv`. Replace the optional blocklist check in `smartlead.py` with your own deduplication source: a local CSV, your CRM, or a database.

## Why boring

Real automation is not "agent, go do sales ops".

Real automation is a constrained workflow: read, classify, prepare, preview, then stop before production until a human confirms the write.

Boring automation is trustworthy automation.
