---
name: smartlead
description: "SmartLead CLI-first skill. Operating layer for campaigns, leads, sequences, accounts, analytics, webhooks, and inbox operations."
---

# SmartLead - CLI-First Operating Layer

This skill is the default operating layer for direct SmartLead API work.

Start with the operational guide:
- `PLAYBOOK.md` - the human workflow for thinking through SmartLead operations
- `SKILL.md` - safety rules and the CLI entry points

Use this skill when you need to:
- read campaigns, leads, email accounts, replies, and analytics;
- export data;
- prepare payloads for update/write operations;
- perform operational work through the CLI or helper scripts in this folder.

Do not jump straight to generic API tooling when the task is a direct SmartLead operation. Use this skill first.

## Source of Truth

Before ambiguous or write-sensitive operations, check current SmartLead documentation:
- Docs index: `https://api.smartlead.ai/llms.txt`
- API reference: `https://api.smartlead.ai/api-reference`
- Help center fallback: `https://helpcenter.smartlead.ai/en/articles/125-full-api-documentation`

Local notes in this skill are operational memory, not the source of truth.

Pay special attention to docs before working with:
- campaign status;
- schedule;
- sequences / variants;
- email account settings;
- lead upload limits / validation flags.

## Core Rules

1. Run direct SmartLead operations through:
   `python3 smartlead/smartlead.py <command> [args]`
2. `SMARTLEAD_API_KEY` must come from the environment. Do not hardcode keys in code, markdown, or shell history.
3. Before any write/update/delete, show the payload and wait for human approval.
4. If an endpoint can overwrite existing state, call that out explicitly.
5. On 429 errors, do not hammer the API. Use backoff and sensible batches.
6. Put any new helper scripts in `smartlead/scripts/`.

## Speed Notes

- GET pagination usually uses `limit=100`.
- `POST /campaigns/{id}/leads` supports batches up to `400` leads in this CLI.
- For larger upload jobs, batch the payload instead of sending one lead at a time.
- Prefer export/bulk endpoints over many small requests when possible.
- For inbox and analytics, start with a narrow filter, then expand.

## Safety

- Do not activate a campaign without explicit human confirmation.
- Treat `POST /sequences` as a full replace unless current docs confirm safer partial behavior.
- Treat `delay_in_days` as relative to the previous email.
- Use `<br>` for email bodies rather than raw newline characters.

## Skill Folder

- Playbook: `smartlead/PLAYBOOK.md`
- CLI: `smartlead/smartlead.py`
- Helper scripts: `smartlead/scripts/` if you add your own

## Basic Commands

```bash
# Documentation
python3 smartlead/smartlead.py docs

# Campaigns
python3 smartlead/smartlead.py campaigns
python3 smartlead/smartlead.py campaign-get 3064335

# Leads
python3 smartlead/smartlead.py leads 3064335
python3 smartlead/smartlead.py leads-export 3064335
python3 smartlead/smartlead.py leads-add 3064335 leads.json --dry-run
python3 smartlead/smartlead.py leads-add 3064335 leads.json --confirm-live

# Sequences
python3 smartlead/smartlead.py sequences 3064335
python3 smartlead/smartlead.py sequences-set 3064335 sequences.json --dry-run

# Accounts
python3 smartlead/smartlead.py accounts
python3 smartlead/smartlead.py account-update 101 '{"max_email_per_day": 35}' --dry-run

# Inbox / analytics
python3 smartlead/smartlead.py inbox-replies --campaign-id 3064335
python3 smartlead/smartlead.py analytics 3064335
```
