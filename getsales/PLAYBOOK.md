# GetSales Playbook

## Why this exists

Use this playbook to work with GetSales as an operating system for LinkedIn leads, flows, sender profiles, and messages. The goal is not to expose every API endpoint. The goal is to give an agent or operator a repeatable way to inspect state, prepare changes, and stop before risky writes.

GetSales can look like a simple CRM wrapper, but operational control gets messy quickly when lists, flows, sender profiles, messages, and replies are inspected separately. This playbook keeps the workflow boring and predictable.

## When to use GetSales

Use the GetSales skill when you need to:

- inspect lists and their contents;
- check whether flows are active and moving;
- upload or prepare leads;
- export contacts for audit or routing;
- find a specific contact or conversation;
- inspect messages, replies, and sender profile activity;
- build reply queues from LinkedIn inbox activity.

If the task is about lead movement through lists, flows, sender profiles, or LinkedIn inbox state, this is the right entry point.

## Operating order

The normal sequence is:

1. Clarify the exact read or change.
2. Read current state.
3. Check whether the change can create duplicate or incorrect outreach.
4. Preview the payload or export.
5. Ask for approval before any live write.
6. Report counts, skipped records, warnings, and output files.

Do not treat a list, flow, or inbox export as self-explanatory. Always explain what it means operationally.

## Daily check

A useful daily pass is:

- list active flows;
- inspect sender profiles;
- inspect recent inbox messages;
- classify new replies;
- check whether a flow has gone quiet unexpectedly;
- export action queues if human follow-up is needed.

The goal is to answer:

- Is anything moving?
- Are replies arriving?
- Is there a bottleneck?
- Which replies need action now?

## Lists

Treat lists as the base layer of order.

Before adding or using a list, check:

- whether it matches the task;
- whether segments are mixed together;
- whether required fields are present;
- whether the list overlaps with an existing launch;
- whether the list is safe to attach to a flow.

Before uploading a new batch, understand exactly which list it goes into and why.

## Flows

Treat flows as live mechanics, not static configuration.

Check:

- which flows are active;
- where new leads will be attached;
- whether contacts are stuck;
- whether messages are going out;
- whether replies map back to the expected flow;
- whether sender distribution looks sane.

If a flow exists but message or reply movement is quiet, inspect sender profiles and messages before blaming the audience.

## Leads and contacts

There are three main modes:

- find and inspect;
- export for audit or routing;
- prepare or add to a list or flow.

Before adding leads, check:

- identity quality;
- list destination;
- duplicate risk;
- required fields;
- whether the lead is already attached to a flow;
- whether the action is a local prep step or a live platform write.

After adding leads, report:

- how many were attempted;
- how many were created or updated;
- how many were skipped;
- why records were skipped;
- which output artifacts were created.

## Sender profiles

Sender profiles often look like background infrastructure until something breaks.

Check:

- whether expected senders exist;
- whether one sender is carrying too much load;
- whether sender state looks inactive or inconsistent;
- whether reply or message distribution is skewed.

If a flow is quiet while leads exist, sender profile health is one of the first things to inspect.

## Messages and inbox

Inbox and message reads are not just logs. They are the closest view of how the system is interacting with real people.

Check:

- new inbound messages;
- action-worthy replies;
- auto-reply noise;
- redirect and wrong-person replies;
- repeated issues in one flow;
- timing-later replies that need a follow-up queue.

Do not leave replies as raw inbox rows. Turn them into action buckets.

## Reply action queues

Use reply classification as a triage layer, not as final truth.

Suggested buckets:

- `reply_now`: meeting signals, explicit interest, or requests for details;
- `redirect_research`: wrong-person and redirect replies;
- `follow_up_later`: timing-later replies;
- `suppress`: clear not-interested or unsubscribe signals;
- `auto_reply_ignore`: out-of-office and automated replies;
- `review`: ambiguous or high-value edge cases.

Important replies should still be checked by a human.

## Statistics and health

Statistics should answer whether the system is alive, not just produce a dashboard.

Useful checks:

- total contacts in scope;
- message volume;
- inbound reply volume;
- reply intent distribution;
- sender profile distribution;
- flow distribution;
- stalled or quiet flows.

If numbers do not match expectations, first verify mechanics. Only then judge targeting or copy.

## Common scenarios

### Flow audit

Use when a flow may be stuck.

Check:

- flow exists and status is expected;
- contacts are attached;
- messages exist;
- replies exist;
- sender profiles are involved;
- reply buckets show real movement.

### Reply triage

Use when the inbox is noisy.

Run reply classification, export action queues, and report:

- how many replies were scanned;
- how many require a response;
- how many are redirects;
- how many should be followed up later;
- how many should be suppressed;
- which file contains the action queue.

### Upload preparation

Use when leads are about to move into GetSales.

Check:

- required fields;
- list destination;
- duplicates;
- flow destination;
- dry-run payload preview;
- approval before live write.

## Frequent mistakes

- Looking only at flow status and ignoring message movement.
- Treating raw inbox rows as handled replies.
- Uploading leads without checking list purpose.
- Ignoring sender profile distribution.
- Treating auto-replies as real engagement.
- Letting timing-later replies disappear instead of creating a follow-up queue.

## What to report

After any GetSales work, report:

- commands or read scope used;
- number of lists, flows, contacts, messages, or replies inspected;
- output files created;
- skipped or ambiguous records;
- warnings and their likely cause;
- whether any live write happened.

If no live write happened, say that explicitly.
