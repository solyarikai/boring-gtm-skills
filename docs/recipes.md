# Recipes

## SmartLead upload preflight

```bash
python3 smartlead/smartlead.py prepare-upload 123 examples/smartlead/leads.valid.json \
  --blocklist-csv examples/smartlead/blocklist.csv \
  --dedupe-key email \
  --output-dir tmp/upload_preview
```

Review `summary.json`, `ready.json`, `rejected.csv`, and `payload_batches/` before any live upload.

## SmartLead sequence validation

```bash
python3 smartlead/smartlead.py sequence-validate examples/smartlead/sequences.sample.json
```

Use this before `sequences-set`. It catches malformed JSON shape, suspicious delays, and raw newlines in bodies.

## SmartLead sequence diff

```bash
python3 smartlead/smartlead.py sequence-diff 123 examples/smartlead/sequences.sample.json --json
```

This reads the current campaign sequence and compares it with a local candidate file. It does not write.

## SmartLead campaign preflight

```bash
python3 smartlead/smartlead.py campaign-preflight 123 --json
```

This combines campaign, sequence, accounts, and analytics reads into one launch-readiness snapshot.

## GetSales reply triage

```bash
python3 getsales/getsales.py reply-triage \
  --fixture examples/getsales/reply_export.sample.json \
  --output-dir tmp/reply_triage
```

This creates action queues from inbound LinkedIn replies.

## GetSales flow health

```bash
python3 getsales/getsales.py flow-health <flow_uuid> --max-pages 20 --json
```

This uses message aggregation because direct `flow_uuid` lead search can fail server-side.

## Monthly GTM report from fixtures

```bash
python3 scripts/monthly_gtm_report.py \
  --month 2026-06 \
  --from-fixtures examples/reporting \
  --output-dir tmp/monthly_report
```

This generates a public-safe HTML report without API keys.
