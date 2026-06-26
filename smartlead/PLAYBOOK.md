# SmartLead Playbook

## Why this exists

Use this playbook to work with SmartLead as an outreach operating center, not as a loose API surface. SmartLead can change live campaign state, sequences, lead status, mailbox assignment, and inbox categories. The workflow must make dangerous lines explicit.

The core rule is simple: read first, preview second, write only after human approval.

## When to use SmartLead

Use the SmartLead skill when you need to:

- inspect campaigns;
- export or inspect campaign leads;
- prepare or upload lead batches;
- inspect or update sequences;
- inspect sender accounts;
- read campaign analytics;
- inspect replies;
- prepare notes, categories, or inbox actions.

If the task is about actual email outreach state, this is the right entry point.

## Operating order

The normal sequence is:

1. Clarify the campaign, lead, account, sequence, or inbox scope.
2. Read current state.
3. Identify whether the requested operation can overwrite or trigger production behavior.
4. Use dry-run for every write-sensitive operation.
5. Show the payload and warnings.
6. Require explicit approval before live writes.
7. Verify the result after a live write.
8. Report counts, skipped records, errors, and output artifacts.

Do not make campaign changes based only on memory or old local notes. Check current API docs when behavior is ambiguous.

## Daily check

A useful daily pass is:

- list active campaigns;
- check lead volume and movement;
- inspect replies;
- inspect sender account state;
- inspect campaign analytics;
- identify blocked or stalled areas.

The goal is to answer:

- Are emails sending?
- Are replies coming in?
- Are bounces, unsubscribes, or account issues rising?
- Is anything broken enough to stop or pause?

## Pre-launch campaign check

Before starting or expanding a campaign, check:

- clear campaign name and status;
- correct audience;
- lead count and required fields;
- duplicate risk;
- sequence exists and matches the campaign logic;
- sender accounts are attached;
- schedule is configured;
- recent analytics do not show obvious risk.

If any of those are unclear, do not launch. Fix the input or configuration first.

## Leads

Lead work has three modes:

- inspect current campaign leads;
- export for audit;
- prepare or upload a new batch.

Before uploading, check:

- required fields;
- duplicate keys;
- local or CRM blocklist;
- campaign destination;
- batch size;
- whether upload should ignore global blocklist or cross-campaign duplicates.

After upload, report:

- attempted leads;
- added leads;
- skipped leads;
- skipped reasons;
- batch count;
- whether lead IDs were returned.

Live uploads must require `--confirm-live`.

## Sequences

Treat sequence updates as sensitive. A sequence update can change live campaign behavior.

Before setting sequences:

- read current sequence;
- validate the new JSON;
- compare step count;
- compare subjects, bodies, variants, and delays;
- check whether `delay_in_days` is relative to the previous email;
- check whether email body formatting uses `<br>` instead of raw newlines;
- dry-run first.

If the change is effectively a full sequence rewrite, say that explicitly.

## Sender accounts

Account issues often explain campaign problems.

Check:

- accounts attached to the campaign;
- warmup status if available;
- daily limits;
- whether the account pool matches campaign volume;
- whether specific accounts are overloaded or inactive.

If campaign activity is quiet while leads and sequences look correct, inspect accounts before rewriting copy.

## Replies and inbox

Treat replies as a separate operational layer.

Check:

- new replies;
- positive signals;
- negative or unsubscribe signals;
- auto-replies;
- repeated issues linked to one campaign or message;
- whether a lead needs category update, note, or manual response.

Do not mix reply handling with launch preparation unless the task explicitly asks for both.

## Analytics and campaign health

Analytics should answer whether the campaign is alive and whether risk is rising.

Useful metrics:

- sent count;
- open/reply/click counts when available;
- positive replies;
- bounces;
- unsubscribes;
- sequence-level performance;
- date-range changes.

If metrics look wrong, inspect mechanics first: campaign status, leads, sequence, accounts, and inbox.

## Common scenarios

### Campaign audit

Read campaign status, lead count, sequence, accounts, inbox replies, and analytics. Report the likely bottleneck and whether a write is needed.

### New lead batch

Validate the lead file, dedupe/blocklist locally, split into batches, dry-run the payload, then ask for live approval.

### Sequence update

Read current sequence, validate new JSON, generate a diff, dry-run the update, and only then ask for approval.

### Reply review

Read replies, classify response types, identify next actions, and avoid changing categories or sending replies unless approved.

## Frequent mistakes

- Looking only at campaign status and ignoring actual movement.
- Uploading leads without validating fields or duplicates.
- Updating a sequence without understanding replacement behavior.
- Ignoring account health.
- Treating no replies as only a copy problem before checking sending mechanics.
- Mixing positive replies, negative replies, and auto-replies in one bucket.

## What to report

After any SmartLead work, report:

- campaigns inspected;
- leads found, exported, prepared, uploaded, or skipped;
- sequence/account/analytics state if relevant;
- errors and skipped reasons;
- output files created;
- whether any live write happened.

If no live write happened, say that explicitly.
