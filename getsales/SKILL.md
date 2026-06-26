---
name: getsales
description: "GetSales CLI-first skill. Operating layer for contacts, lists, flows, sender profiles, inbox, reply classification, and stats through the public API."
---

# GetSales - CLI-First Operating Layer

This skill is the default operating layer for direct GetSales API work.

Start with the operational guide:
- `PLAYBOOK.md` - the human workflow for thinking through GetSales operations
- `SKILL.md` - safety rules and the CLI entry points

Use this skill when you need to:
- inspect contact, flow, sender profile, inbox, and reply statistics;
- read replies and classify lead responses;
- export or prepare lead data;
- work with lists, sender profiles, and automations;
- prepare write payloads through a CLI workflow.

## Source of Truth

Before ambiguous or write-sensitive operations, check current GetSales documentation:
- OpenAPI index: `https://api.getsales.io/api/openapi`
- Quick start: `https://api.getsales.io/`
- Import guide: `https://help.getsales.io/en/articles/10217814-uploading-and-importing-leads-into-getsales`

Local notes and old scripts are operational memory, not the source of truth.

## Core Rules

1. Run direct GetSales operations through:
   `python3 getsales/getsales.py <command> [args]`
2. `GETSALES_API_KEY` must come from the environment.
3. Before any write/update/delete, show the payload and wait for human approval.
4. Use `--dry-run` first for write commands.
5. If an API filter is known to be unstable, do not rely on it without verification.

## Known Gotchas

- `/leads/api/leads/search` with `flow_uuid` can fail server-side. For flow-level work, prefer message or lead-envelope aggregation when possible.
- The message/inbox firehose is noisy. For broad reads, narrow by `lead_uuid`, `conversation_uuid`, `sender_profile_uuid`, or `type` first.
- Validate import payloads or CSV files before sending anything to the API.

## Skill Folder

- Playbook: `getsales/PLAYBOOK.md`
- CLI: `getsales/getsales.py`
- Helper scripts: `getsales/scripts/` if you add your own

## Basic Commands

```bash
# Documentation
python3 getsales/getsales.py docs

# Lists / flows / sender profiles
python3 getsales/getsales.py lists
python3 getsales/getsales.py flows
python3 getsales/getsales.py sender-profiles

# Contacts
python3 getsales/getsales.py contacts-search --filter-json '{"company_name":"Acme"}'
python3 getsales/getsales.py contact-get <lead_uuid>
python3 getsales/getsales.py contacts-export --filter-json '{"list_uuid":"..."}' -o leads.csv

# Inbox / stats
python3 getsales/getsales.py inbox --type inbox --limit 50
python3 getsales/getsales.py stats-messages --type inbox --max-pages 10
python3 getsales/getsales.py stats-contacts --filter-json '{"list_uuid":"..."}'
python3 getsales/getsales.py replies --limit 50
python3 getsales/getsales.py reply-intel --limit 50
python3 getsales/getsales.py replies-export -o replies.csv --max-pages 10
python3 getsales/getsales.py stats-replies --max-pages 10
python3 getsales/getsales.py stats-flows --max-pages 10
python3 getsales/getsales.py stats-senders --max-pages 10

# Write with preview first
python3 getsales/getsales.py contact-upsert <list_uuid> lead.json --dry-run
python3 getsales/getsales.py flow-add-new <flow_uuid> <list_uuid> lead.json --dry-run
python3 getsales/getsales.py flow-start <flow_uuid> --dry-run
```

`reply-intel` and `stats-replies` use heuristic intent classification (`not_interested`, `wrong_person`, `redirect`, `timing_later`, `meeting_signal`, `existing_customer`, `acknowledgement`, `auto_reply`, and others). Always review important edge cases manually.
