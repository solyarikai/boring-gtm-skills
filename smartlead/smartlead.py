#!/usr/bin/env python3
"""Universal SmartLead API CLI tool.

Covers: campaigns, leads, sequences, email-accounts, analytics, webhooks,
master-inbox, and docs shortcuts.
"""

import argparse
import csv
import hashlib
import json
import os
import random
import ssl
import sys
import time
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from pathlib import Path

try:
    import certifi
except Exception:
    certifi = None

# Setup: export SMARTLEAD_API_KEY=your_key_here
# Get your API key from SmartLead Settings > API

BASE_URL = "https://server.smartlead.ai/api/v1"
DOCS_INDEX_URL = "https://api.smartlead.ai/llms.txt"
DOCS_REFERENCE_URL = "https://api.smartlead.ai/api-reference"
DOCS_HELP_URL = "https://helpcenter.smartlead.ai/en/articles/125-full-api-documentation"

API_KEY_ENV = "SMARTLEAD_API_KEY"
REQUEST_TIMEOUT = 60
DEFAULT_REQUEST_GAP = 1.05
MAX_RETRIES = 5
LEADS_ADD_BATCH_SIZE = 400
PAGINATION_LIMIT = 100

EXIT_VALIDATION = 1
EXIT_BLOCKED_WRITE = 2
EXIT_WARNINGS = 3
EXIT_INPUT = 4


def build_ssl_context():
    """Prefer certifi CA bundle when available to avoid local trust-store drift."""
    if certifi is None:
        return None
    try:
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None


SSL_CONTEXT = build_ssl_context()


def get_api_key():
    """Load SmartLead API key from environment."""
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        print(
            f"ERROR: {API_KEY_ENV} is not set. Export it before using smartlead.py",
            file=sys.stderr,
        )
        sys.exit(1)
    return api_key


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def api_get(endpoint, params=None):
    """GET request to SmartLead API."""
    params = params or {}
    params["api_key"] = get_api_key()
    url = f"{BASE_URL}{endpoint}?{urlencode(params)}"
    return _request(url, method="GET")


def api_post(endpoint, body=None, params=None):
    """POST request to SmartLead API."""
    params = params or {}
    params["api_key"] = get_api_key()
    url = f"{BASE_URL}{endpoint}?{urlencode(params)}"
    return _request(url, method="POST", body=body)


def api_patch(endpoint, body=None, params=None):
    """PATCH request to SmartLead API."""
    params = params or {}
    params["api_key"] = get_api_key()
    url = f"{BASE_URL}{endpoint}?{urlencode(params)}"
    return _request(url, method="PATCH", body=body)


def api_delete(endpoint, params=None):
    """DELETE request to SmartLead API."""
    params = params or {}
    params["api_key"] = get_api_key()
    url = f"{BASE_URL}{endpoint}?{urlencode(params)}"
    return _request(url, method="DELETE")


def _rate_pause(headers, is_retry=False):
    """Pause between requests based on rate-limit headers when present."""
    if is_retry:
        return
    remaining = headers.get("X-RateLimit-Remaining") or headers.get("x-ratelimit-remaining")
    reset = headers.get("X-RateLimit-Reset") or headers.get("x-ratelimit-reset")
    now = time.time()
    if remaining == "0" and reset:
        try:
            sleep_for = max(float(reset) - now, DEFAULT_REQUEST_GAP)
            time.sleep(sleep_for)
            return
        except ValueError:
            pass
    time.sleep(DEFAULT_REQUEST_GAP)


def _request(url, method="GET", body=None, retries=MAX_RETRIES):
    """Execute HTTP request with retry and rate-aware backoff."""
    data_bytes = json.dumps(body).encode("utf-8") if body else None
    for attempt in range(retries):
        req = Request(url, data=data_bytes, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "Mozilla/5.0 SmartLead-CLI/1.0")
        try:
            open_kwargs = {"timeout": REQUEST_TIMEOUT}
            if SSL_CONTEXT is not None:
                open_kwargs["context"] = SSL_CONTEXT
            with urlopen(req, **open_kwargs) as resp:
                raw = resp.read().decode("utf-8")
                _rate_pause(resp.headers, is_retry=attempt > 0)
                if not raw.strip():
                    return {}
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return {"raw": raw}
        except HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                retry_after = e.headers.get("Retry-After") if e.headers else None
                if retry_after:
                    try:
                        wait = float(retry_after)
                    except ValueError:
                        wait = 0
                else:
                    wait = min(30, (2**attempt) + random.uniform(0.25, 1.25))
                print(
                    f"  Rate limited on attempt {attempt + 1}/{retries}, waiting {wait:.2f}s...",
                    file=sys.stderr,
                )
                time.sleep(wait)
                continue
            body_text = e.read().decode() if e.fp else str(e)
            print(f"API Error {e.code}: {body_text}", file=sys.stderr)
            sys.exit(1)
        except URLError as e:
            print(f"Network error: {e.reason}", file=sys.stderr)
            sys.exit(1)


def out(data):
    """Print JSON to stdout."""
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def preview_request(method, endpoint, body=None, params=None):
    """Print a request preview without sending it."""
    params = dict(params or {})
    params["api_key"] = f"${API_KEY_ENV}"
    url = f"{BASE_URL}{endpoint}?{urlencode(params)}"
    preview = {
        "dry_run": True,
        "method": method,
        "url": url,
        "body": body or {},
    }
    out(preview)


def maybe_dry_run(args, method, endpoint, body=None, params=None):
    """Preview a request and skip the network call when dry-run is enabled."""
    if getattr(args, "dry_run", False):
        preview_request(method, endpoint, body=body, params=params)
        return True
    return False


def load_json_file(path, label="JSON"):
    """Load a JSON file with operator-friendly errors."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: {label} file not found: {path}", file=sys.stderr)
        sys.exit(EXIT_INPUT)
    except json.JSONDecodeError as e:
        print(f"ERROR: {label} file is malformed JSON: {path}: {e}", file=sys.stderr)
        sys.exit(EXIT_INPUT)


def write_json_file(path, data):
    """Write pretty JSON and create parent directories."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n")


def ensure_output_dir(path):
    """Create an output directory or exit with a deterministic input error."""
    output_dir = Path(path)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"ERROR: cannot create output dir {path}: {e}", file=sys.stderr)
        sys.exit(EXIT_INPUT)
    return output_dir


def _as_list(data, preferred_keys=()):
    """Return the most likely list payload from mixed API/file response shapes."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in preferred_keys:
            value = data.get(key)
            if isinstance(value, list):
                return value
        for key in ("data", "results", "items", "records"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def extract_sequences(payload):
    """Normalize sequence payloads from files and SmartLead API responses."""
    return _as_list(payload, preferred_keys=("sequences", "sequence", "steps"))


def _body_text(step):
    """Get an email body from common SmartLead/API shapes."""
    return (
        step.get("email_body")
        or step.get("body")
        or step.get("message")
        or step.get("html")
        or ""
    )


def _subject_text(step):
    """Get an email subject from common SmartLead/API shapes."""
    return step.get("subject") or step.get("email_subject") or ""


def _delay_days(step):
    """Get relative delay in days from common sequence shapes."""
    delay_details = step.get("seq_delay_details") or step.get("delay_details") or {}
    value = (
        delay_details.get("delay_in_days")
        if isinstance(delay_details, dict)
        else None
    )
    if value is None:
        value = step.get("delay_in_days", step.get("delay"))
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def sequence_summary(step, index):
    """Compact, stable sequence step fingerprint for human review and diffs."""
    body = _body_text(step)
    variants = step.get("variants") or step.get("variant_details") or []
    return {
        "index": index,
        "seq_number": step.get("seq_number") or step.get("step") or index,
        "subject": _subject_text(step),
        "body_preview": " ".join(body.split())[:120],
        "body_hash": hashlib.sha256(body.encode("utf-8")).hexdigest()[:16],
        "delay_in_days": _delay_days(step),
        "variants": len(variants) if isinstance(variants, list) else 0,
    }


def validate_sequence_payload(payload):
    """Validate SmartLead sequences without calling the API."""
    errors = []
    warnings = []
    sequences = extract_sequences(payload)

    if not sequences:
        errors.append("No sequence steps found. Expected a list or {'sequences': [...]}.")
        return sequences, errors, warnings

    for index, step in enumerate(sequences, 1):
        if not isinstance(step, dict):
            errors.append(f"Step {index}: expected object, got {type(step).__name__}.")
            continue

        body = _body_text(step)
        subject = _subject_text(step)
        delay = _delay_days(step)

        if not subject:
            warnings.append(f"Step {index}: missing subject.")
        if not body:
            warnings.append(f"Step {index}: missing body.")
        if "\n" in body:
            warnings.append(
                f"Step {index}: body contains raw newline characters; confirm SmartLead renders them as intended."
            )
        if delay is None:
            warnings.append(f"Step {index}: delay_in_days is missing or non-numeric.")
        elif delay < 0 or delay > 30:
            warnings.append(
                f"Step {index}: suspicious delay_in_days={delay}; SmartLead delays are relative to the previous email."
            )

    return sequences, errors, warnings


def diff_sequence_summaries(current, proposed):
    """Compare normalized sequence summaries."""
    current_rows = [sequence_summary(step, i) for i, step in enumerate(current, 1)]
    proposed_rows = [sequence_summary(step, i) for i, step in enumerate(proposed, 1)]
    diffs = []
    if len(current_rows) != len(proposed_rows):
        diffs.append(
            {
                "field": "step_count",
                "current": len(current_rows),
                "proposed": len(proposed_rows),
            }
        )

    for index in range(max(len(current_rows), len(proposed_rows))):
        cur = current_rows[index] if index < len(current_rows) else None
        new = proposed_rows[index] if index < len(proposed_rows) else None
        if cur is None or new is None:
            diffs.append({"step": index + 1, "field": "step_exists", "current": cur, "proposed": new})
            continue
        for field in ("subject", "body_hash", "delay_in_days", "variants"):
            if cur.get(field) != new.get(field):
                diffs.append(
                    {
                        "step": index + 1,
                        "field": field,
                        "current": cur.get(field),
                        "proposed": new.get(field),
                    }
                )
    return {"current": current_rows, "proposed": proposed_rows, "diffs": diffs}


def _lead_value(lead, key):
    """Normalize a lead dedupe key."""
    if key == "email":
        return str(lead.get("email") or lead.get("Email") or "").strip().lower()
    if key == "linkedin":
        return str(
            lead.get("linkedin")
            or lead.get("linkedin_url")
            or lead.get("LinkedIn")
            or ""
        ).strip().rstrip("/").lower()
    if key == "domain":
        raw = lead.get("domain") or lead.get("website") or lead.get("company_url") or ""
        raw = str(raw).strip().lower()
        if raw.startswith(("http://", "https://")):
            raw = urlparse(raw).netloc
        return raw.removeprefix("www.")
    return ""


def load_blocklist_values(path):
    """Load blocklisted emails/domains/linkedin values from a CSV."""
    if not path:
        return set()
    values = set()
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                for row in reader:
                    for key in ("email", "linkedin", "linkedin_url", "domain"):
                        value = (row.get(key) or "").strip().lower().rstrip("/")
                        if value:
                            values.add(value.removeprefix("www."))
            else:
                f.seek(0)
                for row in csv.reader(f):
                    if row and row[0].strip():
                        values.add(row[0].strip().lower().rstrip("/").removeprefix("www."))
    except FileNotFoundError:
        print(f"ERROR: blocklist CSV not found: {path}", file=sys.stderr)
        sys.exit(EXIT_INPUT)
    return values


def cmd_docs(args):
    """Print SmartLead documentation entry points."""
    print("SmartLead docs:")
    print(f"- index: {DOCS_INDEX_URL}")
    print(f"- reference: {DOCS_REFERENCE_URL}")
    print(f"- help center: {DOCS_HELP_URL}")


# ---------------------------------------------------------------------------
# CAMPAIGNS
# ---------------------------------------------------------------------------


def cmd_campaigns_list(args):
    """List all campaigns."""
    data = api_get("/campaigns/", {"include_tags": "true"})
    campaigns = data if isinstance(data, list) else data.get("campaigns", data)

    if args.search:
        q = args.search.lower()
        campaigns = [c for c in campaigns if q in c.get("name", "").lower()]

    if args.status:
        campaigns = [
            c for c in campaigns if c.get("status", "").upper() == args.status.upper()
        ]

    if args.json:
        out(campaigns)
    else:
        print(f"\n{'ID':<10} {'Status':<10} {'Name'}")
        print("-" * 70)
        for c in campaigns:
            print(f"{c['id']:<10} {c.get('status', '?'):<10} {c.get('name', '')}")
        print(f"\nTotal: {len(campaigns)}")


def cmd_campaigns_get(args):
    """Get campaign by ID."""
    data = api_get(f"/campaigns/{args.campaign_id}")
    out(data)


def cmd_campaigns_create(args):
    """Create a new campaign (DRAFTED status)."""
    body = {"name": args.name}
    if args.client_id:
        body["client_id"] = args.client_id
    if maybe_dry_run(args, "POST", "/campaigns/create", body=body):
        return
    data = api_post("/campaigns/create", body)
    out(data)
    print(f"\nCampaign created: ID={data.get('id')}", file=sys.stderr)


def cmd_campaigns_status(args):
    """Update campaign status. NEVER sends START — safety rule."""
    status = args.status.upper()
    if status in ("START", "ACTIVE"):
        print(
            "ERROR: Activating campaigns via API is forbidden. Use SmartLead UI.",
            file=sys.stderr,
        )
        sys.exit(1)
    if maybe_dry_run(
        args, "POST", f"/campaigns/{args.campaign_id}/status", body={"status": status}
    ):
        return
    data = api_post(f"/campaigns/{args.campaign_id}/status", {"status": status})
    out(data)


def cmd_campaigns_settings(args):
    """Update campaign settings."""
    body = json.loads(args.settings_json)
    if maybe_dry_run(
        args, "POST", f"/campaigns/{args.campaign_id}/settings", body=body
    ):
        return
    data = api_post(f"/campaigns/{args.campaign_id}/settings", body)
    out(data)


def cmd_campaigns_schedule(args):
    """Set campaign schedule."""
    body = json.loads(args.schedule_json)
    if maybe_dry_run(
        args, "POST", f"/campaigns/{args.campaign_id}/schedule", body=body
    ):
        return
    data = api_post(f"/campaigns/{args.campaign_id}/schedule", body)
    out(data)


def cmd_campaign_preflight(args):
    """Read-only campaign launch/preflight summary."""
    campaign = api_get(f"/campaigns/{args.campaign_id}")
    sequences_payload = api_get(f"/campaigns/{args.campaign_id}/sequences")
    accounts_payload = api_get(f"/campaigns/{args.campaign_id}/email-accounts")
    analytics = api_get(f"/campaigns/{args.campaign_id}/statistics")

    sequences = extract_sequences(sequences_payload)
    accounts = _as_list(accounts_payload, preferred_keys=("email_accounts", "accounts"))
    warnings = []
    blockers = []

    status = str(campaign.get("status") or campaign.get("campaign_status") or "").upper()
    if status in {"ACTIVE", "STARTED", "RUNNING"}:
        warnings.append(
            "Campaign appears active; avoid sequence or lead changes during send windows."
        )
    if not sequences:
        blockers.append("No sequence steps found.")
    if not accounts:
        blockers.append("No email accounts found for this campaign.")

    if sequences:
        _, _, sequence_warnings = validate_sequence_payload(sequences)
        warnings.extend(sequence_warnings)

    report = {
        "campaign_id": args.campaign_id,
        "campaign": campaign,
        "summary": {
            "status": status or "unknown",
            "sequence_steps": len(sequences),
            "email_accounts": len(accounts),
            "analytics_keys": sorted(analytics.keys()) if isinstance(analytics, dict) else [],
        },
        "sequences": [
            sequence_summary(step, i)
            for i, step in enumerate(sequences, 1)
            if isinstance(step, dict)
        ],
        "accounts": accounts,
        "analytics": analytics,
        "warnings": warnings,
        "blockers": blockers,
    }

    if args.json:
        out(report)
    else:
        print(f"Campaign preflight: {args.campaign_id}")
        print(f"- status: {report['summary']['status']}")
        print(f"- sequence steps: {report['summary']['sequence_steps']}")
        print(f"- email accounts: {report['summary']['email_accounts']}")
        print(f"- blockers: {len(blockers)}")
        print(f"- warnings: {len(warnings)}")
        for blocker in blockers:
            print(f"BLOCKER: {blocker}")
        for warning in warnings:
            print(f"WARN: {warning}")

    if blockers:
        sys.exit(EXIT_VALIDATION)
    if warnings:
        sys.exit(EXIT_WARNINGS)


# ---------------------------------------------------------------------------
# LEADS
# ---------------------------------------------------------------------------


def _fetch_all_leads(campaign_id, status=None, email_status=None, category_id=None):
    """Paginate through all leads."""
    all_leads = []
    offset = 0
    limit = PAGINATION_LIMIT

    while True:
        params = {"offset": offset, "limit": limit}
        if status:
            params["status"] = status
        if email_status:
            params["emailStatus"] = email_status
        if category_id:
            params["category_id"] = category_id

        data = api_get(f"/campaigns/{campaign_id}/leads", params)

        if isinstance(data, dict):
            leads = data.get("data", [])
            total = int(data.get("total_leads", data.get("total", 0)))
        elif isinstance(data, list):
            leads = data
            total = len(data)
        else:
            break

        if not leads:
            break

        all_leads.extend(leads)
        print(f"  Fetched {len(all_leads)}/{total}", file=sys.stderr)

        if len(all_leads) >= total or len(leads) < limit:
            break
        offset += limit

    return all_leads


def cmd_leads_list(args):
    """List leads in a campaign (JSON)."""
    leads = _fetch_all_leads(
        args.campaign_id,
        status=args.status,
        email_status=args.email_status,
        category_id=args.category_id,
    )
    if args.require_job_title:
        leads = [l for l in leads if _get_job_title(l)]
    out(leads)
    print(f"\nTotal: {len(leads)}", file=sys.stderr)


def cmd_leads_export(args):
    """Export leads to CSV with ALL fields."""
    leads = _fetch_all_leads(
        args.campaign_id,
        status=args.status,
        email_status=args.email_status,
        category_id=args.category_id,
    )

    if args.require_job_title:
        before = len(leads)
        leads = [l for l in leads if _get_job_title(l)]
        print(f"  Filtered: {len(leads)}/{before} with job title", file=sys.stderr)

    if not leads:
        print("No leads found.", file=sys.stderr)
        sys.exit(0)

    # Collect all custom field keys across all leads
    cf_keys = set()
    for item in leads:
        lead = item.get("lead", item)
        cf = lead.get("custom_fields") or {}
        if isinstance(cf, dict):
            cf_keys.update(cf.keys())
    cf_keys = sorted(cf_keys)

    # Build output path
    if args.output:
        output_path = args.output
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        output_path = f"leads_campaign_{args.campaign_id}_{ts}.csv"

    # Standard fields
    std_fields = [
        "campaign_lead_map_id",
        "status",
        "lead_category_id",
        "created_at",
        "lead_id",
        "email",
        "first_name",
        "last_name",
        "company_name",
        "job_title",
        "phone_number",
        "location",
        "linkedin_profile",
        "website",
        "company_url",
        "is_unsubscribed",
    ]
    all_fields = std_fields + [f"cf_{k}" for k in cf_keys]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_fields)
        writer.writeheader()

        for item in leads:
            lead = item.get("lead", item)
            cf = lead.get("custom_fields") or {}
            if not isinstance(cf, dict):
                cf = {}

            row = {
                "campaign_lead_map_id": item.get("campaign_lead_map_id", ""),
                "status": item.get("status", lead.get("status", "")),
                "lead_category_id": item.get("lead_category_id", ""),
                "created_at": item.get("created_at", ""),
                "lead_id": lead.get("id", ""),
                "email": lead.get("email", ""),
                "first_name": lead.get("first_name", ""),
                "last_name": lead.get("last_name", ""),
                "company_name": lead.get("company_name", ""),
                "job_title": _get_job_title(item) or "",
                "phone_number": lead.get("phone_number", ""),
                "location": lead.get("location", ""),
                "linkedin_profile": lead.get("linkedin_profile", ""),
                "website": lead.get("website", ""),
                "company_url": lead.get("company_url", ""),
                "is_unsubscribed": lead.get("is_unsubscribed", False),
            }
            for k in cf_keys:
                row[f"cf_{k}"] = cf.get(k, "")

            writer.writerow(row)

    print(f"\nExported {len(leads)} leads → {output_path}", file=sys.stderr)



def cmd_leads_add(args):
    """Add leads to campaign from JSON file (max 400 per batch)."""
    if not args.dry_run and not args.confirm_live:
        print("ERROR: live leads-add requires --confirm-live", file=sys.stderr)
        sys.exit(EXIT_BLOCKED_WRITE)

    all_leads = load_json_file(args.file, label="leads")
    if not isinstance(all_leads, list):
        print("ERROR: leads file must contain a JSON array", file=sys.stderr)
        sys.exit(EXIT_INPUT)

    # Optional: add your own deduplication/blocklist check here
    # e.g. check against a local CSV, your CRM, or a database

    total_added = 0
    total_skipped = 0
    total_batches = 0

    for i in range(0, len(all_leads), LEADS_ADD_BATCH_SIZE):
        batch = all_leads[i : i + LEADS_ADD_BATCH_SIZE]
        body = {"lead_list": batch}
        if args.skip_blocklist:
            body["settings"] = {"ignore_global_block_list": True}
        if args.allow_duplicates:
            body.setdefault("settings", {})[
                "ignore_duplicate_leads_in_other_campaign"
            ] = True
        if args.return_lead_ids:
            body.setdefault("settings", {})["return_lead_ids"] = True

        if maybe_dry_run(args, "POST", f"/campaigns/{args.campaign_id}/leads", body=body):
            print(
                f"  Dry run batch {i // LEADS_ADD_BATCH_SIZE + 1}: {len(batch)} leads",
                file=sys.stderr,
            )
            total_batches += 1
            continue

        result = api_post(f"/campaigns/{args.campaign_id}/leads", body)
        added = result.get("added_count", result.get("upload_count", 0))
        skipped = result.get("skipped_count", 0)
        total_added += added
        total_skipped += skipped
        total_batches += 1
        print(
            f"  Batch {i // LEADS_ADD_BATCH_SIZE + 1}: +{added}, skipped {skipped}",
            file=sys.stderr,
        )

    print(
        f"\nTotal batches: {total_batches}, added: {total_added}, skipped: {total_skipped}",
        file=sys.stderr,
    )


def cmd_prepare_upload(args):
    """Prepare SmartLead upload files without sending leads to SmartLead."""
    leads = load_json_file(args.file, label="leads")
    if not isinstance(leads, list):
        print("ERROR: leads file must contain a JSON array", file=sys.stderr)
        sys.exit(EXIT_INPUT)

    output_dir = ensure_output_dir(args.output_dir)
    batches_dir = output_dir / "payload_batches"
    batches_dir.mkdir(parents=True, exist_ok=True)

    blocklist = load_blocklist_values(args.blocklist_csv)
    seen = set()
    ready = []
    rejected = []

    for index, lead in enumerate(leads, 1):
        if not isinstance(lead, dict):
            rejected.append({"row": index, "reason": "not_an_object", "value": "", "lead": lead})
            continue

        email = _lead_value(lead, "email")
        dedupe_value = _lead_value(lead, args.dedupe_key)
        blocklist_values = {
            _lead_value(lead, "email"),
            _lead_value(lead, "linkedin"),
            _lead_value(lead, "domain"),
        }
        blocklist_values.discard("")

        if not email:
            rejected.append({"row": index, "reason": "missing_email", "value": "", "lead": lead})
            continue
        if args.blocklist_csv and blocklist_values.intersection(blocklist):
            rejected.append(
                {
                    "row": index,
                    "reason": "blocklisted",
                    "value": ",".join(sorted(blocklist_values.intersection(blocklist))),
                    "lead": lead,
                }
            )
            continue
        if not dedupe_value:
            rejected.append(
                {
                    "row": index,
                    "reason": f"missing_{args.dedupe_key}",
                    "value": "",
                    "lead": lead,
                }
            )
            continue
        if dedupe_value in seen:
            rejected.append(
                {
                    "row": index,
                    "reason": f"duplicate_{args.dedupe_key}",
                    "value": dedupe_value,
                    "lead": lead,
                }
            )
            continue
        seen.add(dedupe_value)
        ready.append(lead)

    write_json_file(output_dir / "ready.json", ready)

    rejected_path = output_dir / "rejected.csv"
    with rejected_path.open("w", newline="", encoding="utf-8") as f:
        fieldnames = ["row", "reason", "value", "email", "linkedin", "domain", "lead_json"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for item in rejected:
            lead = item["lead"] if isinstance(item["lead"], dict) else {}
            writer.writerow(
                {
                    "row": item["row"],
                    "reason": item["reason"],
                    "value": item["value"],
                    "email": _lead_value(lead, "email"),
                    "linkedin": _lead_value(lead, "linkedin"),
                    "domain": _lead_value(lead, "domain"),
                    "lead_json": json.dumps(item["lead"], ensure_ascii=False, default=str),
                }
            )

    batch_paths = []
    for batch_index, start in enumerate(range(0, len(ready), LEADS_ADD_BATCH_SIZE), 1):
        batch = ready[start : start + LEADS_ADD_BATCH_SIZE]
        batch_path = batches_dir / f"batch_{batch_index:03d}.json"
        write_json_file(
            batch_path,
            {
                "campaign_id": args.campaign_id,
                "method": "POST",
                "endpoint": f"/campaigns/{args.campaign_id}/leads",
                "body": {"lead_list": batch},
            },
        )
        batch_paths.append(str(batch_path))

    summary = {
        "campaign_id": args.campaign_id,
        "input_leads": len(leads),
        "ready_leads": len(ready),
        "rejected_leads": len(rejected),
        "dedupe_key": args.dedupe_key,
        "blocklist_csv": args.blocklist_csv,
        "batch_size": LEADS_ADD_BATCH_SIZE,
        "payload_batches": batch_paths,
        "outputs": {
            "ready": str(output_dir / "ready.json"),
            "rejected": str(rejected_path),
            "summary": str(output_dir / "summary.json"),
        },
    }
    write_json_file(output_dir / "summary.json", summary)

    if args.json:
        out(summary)
    else:
        print(f"Prepared SmartLead upload for campaign {args.campaign_id}")
        print(f"- ready: {len(ready)}")
        print(f"- rejected: {len(rejected)}")
        print(f"- batches: {len(batch_paths)}")
        print(f"- output_dir: {output_dir}")

    if rejected:
        sys.exit(EXIT_WARNINGS)


def cmd_leads_search(args):
    """Search lead by email."""
    data = api_get("/leads/", {"email": args.email})
    out(data)


def cmd_leads_update(args):
    """Update lead in campaign."""
    body = json.loads(args.update_json)
    if maybe_dry_run(
        args, "POST", f"/campaigns/{args.campaign_id}/leads/{args.lead_id}", body=body
    ):
        return
    data = api_post(f"/campaigns/{args.campaign_id}/leads/{args.lead_id}", body)
    out(data)


def cmd_leads_pause(args):
    """Pause lead in campaign."""
    if maybe_dry_run(args, "POST", f"/campaigns/{args.campaign_id}/leads/{args.lead_id}/pause"):
        return
    data = api_post(f"/campaigns/{args.campaign_id}/leads/{args.lead_id}/pause")
    out(data)


def cmd_leads_resume(args):
    """Resume lead in campaign."""
    if maybe_dry_run(args, "POST", f"/campaigns/{args.campaign_id}/leads/{args.lead_id}/resume"):
        return
    data = api_post(f"/campaigns/{args.campaign_id}/leads/{args.lead_id}/resume")
    out(data)


def cmd_leads_delete(args):
    """Delete a lead from a campaign."""
    if maybe_dry_run(args, "DELETE", f"/campaigns/{args.campaign_id}/leads/{args.lead_id}"):
        return
    data = api_delete(f"/campaigns/{args.campaign_id}/leads/{args.lead_id}")
    out(data)


def cmd_leads_bulk_delete(args):
    """Delete all leads in a campaign that match IDs from a file (one lead_id per line)."""
    with open(args.file) as f:
        lead_ids = [int(line.strip()) for line in f if line.strip()]
    total = len(lead_ids)
    print(
        f"Deleting {total} leads from campaign {args.campaign_id}...", file=sys.stderr
    )
    for i, lead_id in enumerate(lead_ids, 1):
        if maybe_dry_run(args, "DELETE", f"/campaigns/{args.campaign_id}/leads/{lead_id}"):
            if i % 50 == 0 or i == total:
                print(f"  {i}/{total} dry-run previewed", file=sys.stderr)
            continue
        result = api_delete(f"/campaigns/{args.campaign_id}/leads/{lead_id}")
        ok = result.get("message") or result.get("status") or result
        if i % 50 == 0 or i == total:
            print(f"  {i}/{total} done", file=sys.stderr)


def cmd_leads_unsubscribe(args):
    """Unsubscribe lead globally."""
    if maybe_dry_run(args, "POST", f"/leads/{args.lead_id}/unsubscribe"):
        return
    data = api_post(f"/leads/{args.lead_id}/unsubscribe")
    out(data)


def cmd_leads_categories(args):
    """List all lead categories."""
    data = api_get("/leads/fetch-categories")
    out(data)


def cmd_leads_set_category(args):
    """Set lead category in campaign."""
    body = {"category_id": int(args.category_id)}
    if maybe_dry_run(
        args,
        "POST",
        f"/campaigns/{args.campaign_id}/leads/{args.lead_id}/category",
        body=body,
    ):
        return
    data = api_post(
        f"/campaigns/{args.campaign_id}/leads/{args.lead_id}/category",
        body,
    )
    out(data)


def cmd_leads_history(args):
    """Get message history for lead in campaign."""
    data = api_get(
        f"/campaigns/{args.campaign_id}/leads/{args.lead_id}/message-history"
    )
    out(data)


# ---------------------------------------------------------------------------
# SEQUENCES
# ---------------------------------------------------------------------------


def cmd_sequences_get(args):
    """Get sequences for a campaign."""
    data = api_get(f"/campaigns/{args.campaign_id}/sequences")
    out(data)


def cmd_sequences_set(args):
    """Create/update sequences from JSON file."""
    sequences = load_json_file(args.file, label="sequences")
    body = {"sequences": sequences}
    if maybe_dry_run(args, "POST", f"/campaigns/{args.campaign_id}/sequences", body=body):
        return
    data = api_post(
        f"/campaigns/{args.campaign_id}/sequences", body
    )
    out(data)


def cmd_sequence_validate(args):
    """Validate a local SmartLead sequence JSON file."""
    payload = load_json_file(args.file, label="sequences")
    sequences, errors, warnings = validate_sequence_payload(payload)
    report = {
        "file": args.file,
        "steps": [sequence_summary(step, i) for i, step in enumerate(sequences, 1) if isinstance(step, dict)],
        "errors": errors,
        "warnings": warnings,
    }

    if args.json:
        out(report)
    else:
        print(f"Sequence validation: {args.file}")
        print(f"- steps: {len(sequences)}")
        print(f"- errors: {len(errors)}")
        print(f"- warnings: {len(warnings)}")
        for error in errors:
            print(f"ERROR: {error}")
        for warning in warnings:
            print(f"WARN: {warning}")

    if errors:
        sys.exit(EXIT_VALIDATION)
    if warnings:
        sys.exit(EXIT_WARNINGS)


def cmd_sequence_diff(args):
    """Compare live campaign sequences with a local sequence JSON file."""
    proposed_payload = load_json_file(args.file, label="proposed sequences")
    proposed, errors, warnings = validate_sequence_payload(proposed_payload)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(EXIT_VALIDATION)

    current_payload = api_get(f"/campaigns/{args.campaign_id}/sequences")
    current = extract_sequences(current_payload)
    diff = diff_sequence_summaries(current, proposed)
    diff["campaign_id"] = args.campaign_id
    diff["warnings"] = warnings

    if args.json:
        out(diff)
    else:
        print(f"Sequence diff for campaign {args.campaign_id}")
        print(f"- current steps: {len(diff['current'])}")
        print(f"- proposed steps: {len(diff['proposed'])}")
        print(f"- differences: {len(diff['diffs'])}")
        for item in diff["diffs"]:
            prefix = f"step {item.get('step')}: " if item.get("step") else ""
            print(f"{prefix}{item['field']}: {item['current']} -> {item['proposed']}")
        for warning in warnings:
            print(f"WARN: {warning}")

    if warnings:
        sys.exit(EXIT_WARNINGS)


# ---------------------------------------------------------------------------
# EMAIL ACCOUNTS
# ---------------------------------------------------------------------------


def cmd_accounts_list(args):
    """List all email accounts."""
    params = {}
    if args.limit:
        params["limit"] = args.limit
    if args.offset:
        params["offset"] = args.offset
    if args.warmup_status:
        params["emailWarmupStatus"] = args.warmup_status
    data = api_get("/email-accounts/", params)
    accounts = data if isinstance(data, list) else data.get("data", [])

    if args.json:
        out(accounts)
    else:
        print(
            f"\n{'ID':<8} {'Email':<35} {'Type':<8} {'SMTP':<6} {'Warmup':<10} {'Campaigns'}"
        )
        print("-" * 90)
        for a in accounts:
            warmup = a.get("warmup_details") or {}
            print(
                f"{a.get('id', ''):<8} "
                f"{a.get('from_email', ''):<35} "
                f"{a.get('type', ''):<8} "
                f"{'OK' if a.get('is_smtp_success') else 'FAIL':<6} "
                f"{warmup.get('status', 'N/A'):<10} "
                f"{a.get('campaign_count', 0)}"
            )
        print(f"\nTotal: {len(accounts)}")


def cmd_accounts_campaign(args):
    """Get email accounts for a campaign."""
    data = api_get(f"/campaigns/{args.campaign_id}/email-accounts")
    out(data)


def cmd_accounts_add(args):
    """Add email accounts to a campaign."""
    ids = [int(x.strip()) for x in args.account_ids.split(",")]
    body = {"email_account_ids": ids}
    if maybe_dry_run(
        args, "POST", f"/campaigns/{args.campaign_id}/email-accounts", body=body
    ):
        return
    data = api_post(
        f"/campaigns/{args.campaign_id}/email-accounts", body
    )
    out(data)


def cmd_account_update(args):
    """Update email account settings."""
    body = json.loads(args.update_json)
    if maybe_dry_run(args, "POST", f"/email-accounts/{args.account_id}", body=body):
        return
    data = api_post(f"/email-accounts/{args.account_id}", body)
    out(data)


# ---------------------------------------------------------------------------
# ANALYTICS
# ---------------------------------------------------------------------------


def cmd_analytics_campaign(args):
    """Get campaign statistics."""
    data = api_get(f"/campaigns/{args.campaign_id}/statistics")
    out(data)


def cmd_analytics_sequences(args):
    """Get per-step sequence analytics."""
    data = api_get(f"/campaigns/{args.campaign_id}/sequence-analytics")
    out(data)


def cmd_analytics_by_date(args):
    """Get analytics by date range."""
    params = {}
    if args.start_date:
        params["start_date"] = args.start_date
    if args.end_date:
        params["end_date"] = args.end_date
    data = api_get(f"/campaigns/{args.campaign_id}/analytics-by-date", params)
    out(data)


# ---------------------------------------------------------------------------
# WEBHOOKS
# ---------------------------------------------------------------------------


def cmd_webhooks_list(args):
    """List all webhooks."""
    data = api_get("/webhooks")
    out(data)


def cmd_webhooks_create(args):
    """Create a webhook."""
    body = json.loads(args.webhook_json)
    if maybe_dry_run(args, "POST", "/webhook/create", body=body):
        return
    data = api_post("/webhook/create", body)
    out(data)


def cmd_webhooks_update(args):
    """Update a webhook."""
    body = json.loads(args.update_json)
    if maybe_dry_run(args, "PATCH", f"/webhooks/{args.webhook_id}", body=body):
        return
    data = api_patch(f"/webhooks/{args.webhook_id}", body)
    out(data)


def cmd_webhooks_delete(args):
    """Delete a webhook."""
    if maybe_dry_run(args, "DELETE", f"/webhooks/{args.webhook_id}"):
        return
    data = api_delete(f"/webhooks/{args.webhook_id}")
    out(data)


# ---------------------------------------------------------------------------
# MASTER INBOX
# ---------------------------------------------------------------------------


def cmd_inbox_replies(args):
    """Fetch replied leads from master inbox."""
    body = {}
    if args.campaign_id:
        body["campaign_id"] = int(args.campaign_id)
    if args.offset:
        body["offset"] = int(args.offset)
    if args.limit:
        body["limit"] = int(args.limit)
    data = api_post("/master-inbox/inbox-replies", body)
    out(data)


def cmd_inbox_reply(args):
    """Reply to a lead in campaign."""
    body = {"lead_id": int(args.lead_id), "message": args.message}
    if maybe_dry_run(
        args, "POST", f"/campaigns/{args.campaign_id}/reply-email-thread", body=body
    ):
        return
    data = api_post(
        f"/campaigns/{args.campaign_id}/reply-email-thread",
        body,
    )
    out(data)


def cmd_inbox_note(args):
    """Create a note for a lead."""
    body = {"lead_id": int(args.lead_id), "note": args.note}
    if maybe_dry_run(args, "POST", "/master-inbox/create-note", body=body):
        return
    data = api_post("/master-inbox/create-note", body)
    out(data)


def cmd_inbox_category(args):
    """Update lead category in master inbox."""
    body = {"lead_id": int(args.lead_id), "category_id": int(args.category_id)}
    if maybe_dry_run(args, "PATCH", "/master-inbox/update-category", body=body):
        return
    data = api_patch("/master-inbox/update-category", body)
    out(data)


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------


def _get_job_title(item):
    """Extract job title from lead structure."""
    lead = item.get("lead", item)
    cf = lead.get("custom_fields") or {}
    if isinstance(cf, dict):
        for key in (
            "job_title",
            "title",
            "position",
            "designation",
            "Job Title",
            "Title",
        ):
            val = cf.get(key)
            if val and str(val).strip():
                return str(val).strip()
    for key in ("job_title", "title", "position"):
        val = lead.get(key)
        if val and str(val).strip():
            return str(val).strip()
    return None


# ---------------------------------------------------------------------------
# CLI PARSER
# ---------------------------------------------------------------------------


def build_parser():
    parser = argparse.ArgumentParser(
        prog="smartlead", description="Universal SmartLead API CLI"
    )
    sub = parser.add_subparsers(dest="command")

    def add_dry_run_flag(cmd):
        cmd.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview request payload without sending it",
        )

    p = sub.add_parser("docs", help="Show SmartLead documentation entry points")
    p.set_defaults(func=cmd_docs)

    # --- campaigns ---
    p = sub.add_parser("campaigns", help="List campaigns")
    p.add_argument("--search", help="Filter by name (case-insensitive)")
    p.add_argument("--status", help="Filter by status")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.set_defaults(func=cmd_campaigns_list)

    p = sub.add_parser("campaign-get", help="Get campaign by ID")
    p.add_argument("campaign_id", type=int)
    p.set_defaults(func=cmd_campaigns_get)

    p = sub.add_parser("campaign-create", help="Create campaign")
    p.add_argument("name")
    p.add_argument("--client-id", type=int)
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_campaigns_create)

    p = sub.add_parser(
        "campaign-status", help="Update campaign status (PAUSED/STOPPED only)"
    )
    p.add_argument("campaign_id", type=int)
    p.add_argument("status", choices=["PAUSED", "STOPPED"])
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_campaigns_status)

    p = sub.add_parser("campaign-settings", help="Update campaign settings")
    p.add_argument("campaign_id", type=int)
    p.add_argument("settings_json", help="JSON string with settings")
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_campaigns_settings)

    p = sub.add_parser("campaign-schedule", help="Set campaign schedule")
    p.add_argument("campaign_id", type=int)
    p.add_argument("schedule_json", help="JSON string with schedule")
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_campaigns_schedule)

    p = sub.add_parser("campaign-preflight", help="Read-only launch/preflight summary")
    p.add_argument("campaign_id", type=int)
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.set_defaults(func=cmd_campaign_preflight)

    # --- leads ---
    p = sub.add_parser("leads", help="List leads (JSON)")
    p.add_argument("campaign_id", type=int)
    p.add_argument("--status", help="STARTED/INPROGRESS/COMPLETED/PAUSED/STOPPED")
    p.add_argument(
        "--email-status",
        help="is_replied/is_opened/is_clicked/is_bounced/is_unsubscribed",
    )
    p.add_argument("--category-id", type=int)
    p.add_argument("--require-job-title", action="store_true")
    p.set_defaults(func=cmd_leads_list)

    p = sub.add_parser("leads-export", help="Export leads to CSV")
    p.add_argument("campaign_id", type=int)
    p.add_argument("--status")
    p.add_argument("--email-status")
    p.add_argument("--category-id", type=int)
    p.add_argument("--require-job-title", action="store_true")
    p.add_argument("--output", "-o", help="Output CSV path")
    p.set_defaults(func=cmd_leads_export)

    p = sub.add_parser("leads-add", help="Add leads from JSON file")
    p.add_argument("campaign_id", type=int)
    p.add_argument("file", help="JSON file with lead_list array")
    p.add_argument("--skip-blocklist", action="store_true")
    p.add_argument("--allow-duplicates", action="store_true")
    p.add_argument("--return-lead-ids", action="store_true")
    p.add_argument("--confirm-live", action="store_true", help="required for live uploads")
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_leads_add)

    p = sub.add_parser("prepare-upload", help="Prepare SmartLead lead upload files locally")
    p.add_argument("campaign_id", type=int)
    p.add_argument("file", help="JSON file with leads array")
    p.add_argument("--output-dir", required=True, help="Directory for ready/rejected/batches")
    p.add_argument("--blocklist-csv", help="Optional CSV with email/linkedin/domain columns")
    p.add_argument(
        "--dedupe-key",
        choices=["email", "linkedin", "domain"],
        default="email",
        help="Lead key used for local deduplication",
    )
    p.add_argument("--json", action="store_true", help="Output summary as JSON")
    p.set_defaults(func=cmd_prepare_upload)

    p = sub.add_parser("leads-search", help="Search lead by email")
    p.add_argument("email")
    p.set_defaults(func=cmd_leads_search)

    p = sub.add_parser("leads-update", help="Update lead in campaign")
    p.add_argument("campaign_id", type=int)
    p.add_argument("lead_id", type=int)
    p.add_argument("update_json", help="JSON string with updates")
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_leads_update)

    p = sub.add_parser("leads-pause", help="Pause lead")
    p.add_argument("campaign_id", type=int)
    p.add_argument("lead_id", type=int)
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_leads_pause)

    p = sub.add_parser("leads-resume", help="Resume lead")
    p.add_argument("campaign_id", type=int)
    p.add_argument("lead_id", type=int)
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_leads_resume)

    p = sub.add_parser("leads-delete", help="Delete a lead from a campaign")
    p.add_argument("campaign_id", type=int)
    p.add_argument("lead_id", type=int)
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_leads_delete)

    p = sub.add_parser(
        "leads-bulk-delete", help="Delete leads listed in a file (one lead_id per line)"
    )
    p.add_argument("campaign_id", type=int)
    p.add_argument("file", help="File with lead IDs, one per line")
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_leads_bulk_delete)

    p = sub.add_parser("leads-unsubscribe", help="Unsubscribe lead globally")
    p.add_argument("lead_id", type=int)
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_leads_unsubscribe)

    p = sub.add_parser("leads-categories", help="List all lead categories")
    p.set_defaults(func=cmd_leads_categories)

    p = sub.add_parser("leads-set-category", help="Set lead category")
    p.add_argument("campaign_id", type=int)
    p.add_argument("lead_id", type=int)
    p.add_argument("category_id")
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_leads_set_category)

    p = sub.add_parser("leads-history", help="Get message history")
    p.add_argument("campaign_id", type=int)
    p.add_argument("lead_id", type=int)
    p.set_defaults(func=cmd_leads_history)

    # --- sequences ---
    p = sub.add_parser("sequences", help="Get campaign sequences")
    p.add_argument("campaign_id", type=int)
    p.set_defaults(func=cmd_sequences_get)

    p = sub.add_parser("sequences-set", help="Create/update sequences from JSON file")
    p.add_argument("campaign_id", type=int)
    p.add_argument("file", help="JSON file with sequences array")
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_sequences_set)

    p = sub.add_parser("sequence-validate", help="Validate a local SmartLead sequence JSON")
    p.add_argument("file", help="JSON file with sequences array")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.set_defaults(func=cmd_sequence_validate)

    p = sub.add_parser("sequence-diff", help="Read-only diff of live vs local sequences")
    p.add_argument("campaign_id", type=int)
    p.add_argument("file", help="JSON file with proposed sequences")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.set_defaults(func=cmd_sequence_diff)

    # --- email accounts ---
    p = sub.add_parser("accounts", help="List all email accounts")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--warmup-status", help="ACTIVE/INACTIVE")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.set_defaults(func=cmd_accounts_list)

    p = sub.add_parser("accounts-campaign", help="Get accounts for a campaign")
    p.add_argument("campaign_id", type=int)
    p.set_defaults(func=cmd_accounts_campaign)

    p = sub.add_parser("accounts-add", help="Add accounts to campaign")
    p.add_argument("campaign_id", type=int)
    p.add_argument("account_ids", help="Comma-separated account IDs")
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_accounts_add)

    p = sub.add_parser("account-update", help="Update email account settings")
    p.add_argument("account_id", type=int)
    p.add_argument("update_json", help="JSON string with account settings")
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_account_update)

    # --- analytics ---
    p = sub.add_parser("analytics", help="Campaign statistics")
    p.add_argument("campaign_id", type=int)
    p.set_defaults(func=cmd_analytics_campaign)

    p = sub.add_parser("analytics-sequences", help="Per-step sequence analytics")
    p.add_argument("campaign_id", type=int)
    p.set_defaults(func=cmd_analytics_sequences)

    p = sub.add_parser("analytics-dates", help="Analytics by date range")
    p.add_argument("campaign_id", type=int)
    p.add_argument("--start-date", help="ISO 8601 date")
    p.add_argument("--end-date", help="ISO 8601 date")
    p.set_defaults(func=cmd_analytics_by_date)

    # --- webhooks ---
    p = sub.add_parser("webhooks", help="List webhooks")
    p.set_defaults(func=cmd_webhooks_list)

    p = sub.add_parser("webhook-create", help="Create webhook")
    p.add_argument("webhook_json", help="JSON string with webhook config")
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_webhooks_create)

    p = sub.add_parser("webhook-update", help="Update webhook")
    p.add_argument("webhook_id", type=int)
    p.add_argument("update_json", help="JSON string with updates")
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_webhooks_update)

    p = sub.add_parser("webhook-delete", help="Delete webhook")
    p.add_argument("webhook_id", type=int)
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_webhooks_delete)

    # --- master inbox ---
    p = sub.add_parser("inbox-replies", help="Fetch replied leads")
    p.add_argument("--campaign-id", type=int)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_inbox_replies)

    p = sub.add_parser("inbox-reply", help="Reply to a lead")
    p.add_argument("campaign_id", type=int)
    p.add_argument("lead_id", type=int)
    p.add_argument("message")
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_inbox_reply)

    p = sub.add_parser("inbox-note", help="Create a note")
    p.add_argument("lead_id", type=int)
    p.add_argument("note")
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_inbox_note)

    p = sub.add_parser("inbox-category", help="Update lead category in inbox")
    p.add_argument("lead_id", type=int)
    p.add_argument("category_id", type=int)
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_inbox_category)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
