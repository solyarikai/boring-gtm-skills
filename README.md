# boring-gtm-skills

CLI-first operating layers for GetSales and SmartLead. Boring automation is trustworthy automation.

## What this is

This repository contains CLI-first skills for GetSales and SmartLead. They are not autonomous agents that improvise across production systems. They are constrained workflows: the agent operates through a small CLI layer that knows the safe reads, the dangerous writes, and the approval gates. Writes default to preview or dry-run behavior, and live SmartLead uploads require an explicit `--confirm-live` flag.

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
```

## Quickstart - SmartLead

```bash
export SMARTLEAD_API_KEY=your_key_here
python3 smartlead/smartlead.py campaigns
python3 smartlead/smartlead.py leads-add 123 leads.json --dry-run
# add --confirm-live only when you're sure
```

## Adapting to your stack

The public version expects API keys in environment variables. Replace that with your own `.env` setup if you prefer, for example with `python-dotenv`. The SmartLead upload path includes a placeholder for your own deduplication or blocklist logic; connect it to a local CSV, your CRM, or a database.

## Why boring

Real automation is not "agent, go do sales ops".

Real automation is a constrained workflow: read, classify, prepare, preview, then stop before production until a human confirms the write.

Boring automation is trustworthy automation.
