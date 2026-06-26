#!/usr/bin/env python3
"""Universal GetSales API CLI."""

import argparse
import csv
import json
import os
import re
import ssl
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import certifi

# Setup: export GETSALES_API_KEY=your_key_here
# Get your API key from GetSales Settings > API

BASE_URL = "https://amazing.getsales.io"
API_KEY_ENV = "GETSALES_API_KEY"
REQUEST_TIMEOUT = 60
DEFAULT_REQUEST_GAP = 0.35
MAX_RETRIES = 4
PAGINATION_LIMIT = 100


def _build_ssl_context():
    candidates = []
    try:
        candidates.append(certifi.where())
    except Exception:
        pass
    candidates.extend(
        [
            "/etc/ssl/cert.pem",
            "/private/etc/ssl/cert.pem",
            "/opt/homebrew/etc/openssl@3/cert.pem",
        ]
    )
    for cafile in candidates:
        if cafile and os.path.exists(cafile):
            return ssl.create_default_context(cafile=cafile)
    return ssl.create_default_context()


SSL_CONTEXT = _build_ssl_context()

DOCS_INDEX_URL = "https://api.getsales.io/api/openapi"
DOCS_QUICKSTART_URL = "https://api.getsales.io/"
DOCS_IMPORT_URL = "https://help.getsales.io/en/articles/10217814-uploading-and-importing-leads-into-getsales"

FLOW_UUID_FILTER_WARNING = (
    "WARNING: GetSales /leads/api/leads/search with flow_uuid may 500 server-side. "
    "Prefer flow/message aggregation when possible."
)

POSITIVE_REPLY_PATTERNS = [
    r"\binterested\b",
    r"\bsounds good\b",
    r"\blet'?s\b",
    r"\bbook\b",
    r"\bmeeting\b",
    r"\bdemo\b",
    r"\bcall\b",
    r"\byes\b",
    r"\bда\b",
    r"интерес",
    r"созвон",
    r"встрет",
]
NEGATIVE_REPLY_PATTERNS = [
    r"\bnot interested\b",
    r"\bno thanks\b",
    r"\bnot now\b",
    r"\bunsubscribe\b",
    r"\bstop\b",
    r"\bno longer\b",
    r"\bне интересно\b",
    r"\bне актуал",
    r"\bнет\b",
    r"\bотпис",
]
REDIRECT_REPLY_PATTERNS = [
    r"\bcontact\b",
    r"\breach out\b",
    r"\bspeak with\b",
    r"\btalk to\b",
    r"\bdecision maker\b",
    r"\bdecision-maker\b",
    r"\bceo\b",
    r"\bfounder\b",
    r"\bresponsible\b",
    r"\bобратитесь\b",
    r"\bсвяжитесь\b",
    r"\bнапишите\b",
    r"\bне я\b",
    r"\bне занимаюсь\b",
    r"\bдругому\b",
]
AUTO_REPLY_PATTERNS = [
    r"\bout of office\b",
    r"\bauto.?reply\b",
    r"\bautomatic reply\b",
    r"\baway from\b",
    r"\bvacation\b",
    r"\booo\b",
    r"\bавтоответ\b",
    r"\bв отпуске\b",
]

REPLY_INTENT_RULES = [
    (
        "auto_reply",
        [
            r"\bout of office\b",
            r"\bauto.?reply\b",
            r"\bautomatic reply\b",
            r"\baway from\b",
            r"\bvacation\b",
            r"\booo\b",
            r"\bавтоответ\b",
            r"\bв отпуске\b",
        ],
    ),
    (
        "existing_customer",
        [
            r"\bwe are your client\b",
            r"\balready your client\b",
            r"\balready a client\b",
            r"\balready working with you\b",
            r"\bуже ваш клиент\b",
            r"\bуже работаем\b",
            r"\bмы ваш клиент\b",
        ],
    ),
    (
        "not_interested",
        [
            r"\bnot interested\b",
            r"\bno thanks\b",
            r"\bnot for us\b",
            r"\bunsubscribe\b",
            r"\bstop\b",
            r"\bне интересно\b",
            r"\bне актуал",
            r"\bне нужно\b",
            r"\bнет,?\b",
            r"\bотпис",
        ],
    ),
    (
        "wrong_person",
        [
            r"\bnot the right person\b",
            r"\bwrong person\b",
            r"\bi am not the right person\b",
            r"\bi'?m not the decision maker\b",
            r"\bnot decision maker\b",
            r"\bnot a decision maker\b",
            r"\bnot responsible\b",
            r"\bне я\b",
            r"\bне занимаюсь\b",
            r"\bне решаю\b",
            r"\bне решение за мной\b",
            r"\bне ответствен",
        ],
    ),
    (
        "redirect",
        [
            r"\bcontact\b",
            r"\breach out\b",
            r"\bspeak with\b",
            r"\btalk to\b",
            r"\bplease contact\b",
            r"\byou can contact\b",
            r"\bwrite to\b",
            r"\bceo\b",
            r"\bfounder\b",
            r"\bhead office\b",
            r"\bsi[eè]ge\b",
            r"\bобратитесь\b",
            r"\bсвяжитесь\b",
            r"\bнапишите\b",
            r"\bпишите\b",
            r"\bдругому\b",
            r"\bдиректору\b",
        ],
    ),
    (
        "timing_later",
        [
            r"\bnot now\b",
            r"\bmaybe later\b",
            r"\bnext week\b",
            r"\bnext month\b",
            r"\bthis week\b",
            r"\bfollow up\b",
            r"\breach out later\b",
            r"\bget back to you\b",
            r"\bcome back later\b",
            r"\bпозже\b",
            r"\bпозднее\b",
            r"\bна следующей неделе\b",
            r"\bследующ[а-я]+ недел",
            r"\bверн[её]мся\b",
            r"\bвозьмем.*время\b",
            r"\bнужно время\b",
            r"\bдайте.*время\b",
            r"\bне сейчас\b",
        ],
    ),
    (
        "meeting_signal",
        [
            r"\blet'?s\b",
            r"\bbook\b",
            r"\bmeeting\b",
            r"\bdemo\b",
            r"\bcall\b",
            r"\bschedule\b",
            r"\bcalendar\b",
            r"\bconnect next\b",
            r"\bсозвон\b",
            r"\bвстрет",
            r"\bдемо\b",
            r"\bкалл\b",
        ],
    ),
    (
        "positive_interest",
        [
            r"\binterested\b",
            r"\bsounds good\b",
            r"\bsure\b",
            r"\byes\b",
            r"\bда\b",
            r"\bинтерес",
            r"\bokay\b",
            r"\bok\b",
        ],
    ),
    (
        "acknowledgement",
        [
            r"\bthanks\b",
            r"\bthank you\b",
            r"\bgot it\b",
            r"\bunderstood\b",
            r"\bпонял\b",
            r"\bспасибо\b",
            r"\bок\b",
            r"\bokay\b",
        ],
    ),
]


def get_api_key():
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        print(f"ERROR: {API_KEY_ENV} is not set", file=sys.stderr)
        sys.exit(1)
    return api_key


def maybe_json(value, label):
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON for {label}: {exc}", file=sys.stderr)
        sys.exit(1)


def load_json_file(path, label):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON in {label}: {exc}", file=sys.stderr)
        sys.exit(1)


def _headers():
    return {
        "Authorization": f"Bearer {get_api_key()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/136.0.0.0 Safari/537.36"
        ),
    }


def _request(path, method="GET", params=None, body=None, retries=MAX_RETRIES):
    url = f"{BASE_URL}{path}"
    if params:
        url = f"{url}?{urlencode(params, doseq=True)}"
    data = json.dumps(body).encode("utf-8") if body is not None else None

    for attempt in range(retries):
        req = Request(url, data=data, method=method, headers=_headers())
        try:
            with urlopen(req, timeout=REQUEST_TIMEOUT, context=SSL_CONTEXT) as resp:
                raw = resp.read().decode("utf-8")
                time.sleep(DEFAULT_REQUEST_GAP)
                if resp.status in (204,) or not raw.strip():
                    return {}
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return {"raw": raw}
        except HTTPError as e:
            body_text = e.read().decode() if e.fp else str(e)
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                wait = min(20, 2 ** attempt)
                print(
                    f"Retryable GetSales error {e.code} on attempt {attempt + 1}/{retries}; waiting {wait}s...",
                    file=sys.stderr,
                )
                time.sleep(wait)
                continue
            print(f"API Error {e.code}: {body_text}", file=sys.stderr)
            sys.exit(1)
        except URLError as e:
            print(f"Network error: {e.reason}", file=sys.stderr)
            sys.exit(1)


def api_get(path, params=None):
    return _request(path, method="GET", params=params)


def api_post(path, body=None, params=None):
    return _request(path, method="POST", params=params, body=body)


def api_put(path, body=None, params=None):
    return _request(path, method="PUT", params=params, body=body)


def api_delete(path, params=None):
    return _request(path, method="DELETE", params=params)


def out(data):
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def preview_request(method, path, body=None, params=None):
    url = f"{BASE_URL}{path}"
    if params:
        url = f"{url}?{urlencode(params, doseq=True)}"
    preview = {
        "dry_run": True,
        "method": method,
        "url": url,
        "headers": {
            "Authorization": f"Bearer ${API_KEY_ENV}",
            "Content-Type": "application/json",
        },
        "body": body or {},
    }
    out(preview)


def maybe_dry_run(args, method, path, body=None, params=None):
    if getattr(args, "dry_run", False):
        preview_request(method, path, body=body, params=params)
        return True
    return False


def add_dry_run_flag(parser):
    parser.add_argument("--dry-run", action="store_true", help="Preview request without sending it")


def extract_lead(item):
    if isinstance(item, dict) and isinstance(item.get("lead"), dict):
        return item["lead"]
    return item if isinstance(item, dict) else {}


def extract_automation(item):
    automation = item.get("automation") if isinstance(item, dict) else None
    if isinstance(automation, dict):
        return automation
    if isinstance(automation, str):
        return {"uuid": "", "name": automation}
    return {}


def iter_paginated_search(filter_obj, max_pages=1_000):
    offset = 0
    total = None
    seen = 0
    pages = 0
    while pages < max_pages:
        payload = {
            "filter": filter_obj or {},
            "limit": PAGINATION_LIMIT,
            "offset": offset,
            "order_field": "created_at",
            "order_type": "desc",
        }
        data = api_post("/leads/api/leads/search", payload)
        batch = data.get("data", []) if isinstance(data, dict) else []
        total = data.get("total", total) if isinstance(data, dict) else total
        if not batch:
            break
        yield batch, total
        seen += len(batch)
        pages += 1
        if len(batch) < PAGINATION_LIMIT:
            break
        offset += PAGINATION_LIMIT


def iter_paginated_messages(params, max_pages=1_000):
    offset = int(params.get("offset", 0))
    pages = 0
    while pages < max_pages:
        page_params = dict(params)
        page_params["limit"] = PAGINATION_LIMIT
        page_params["offset"] = offset
        data = api_get("/flows/api/linkedin-messages", page_params)
        batch = data.get("data", []) if isinstance(data, dict) else []
        total = data.get("total", 0) if isinstance(data, dict) else len(batch)
        has_more = data.get("has_more", False) if isinstance(data, dict) else False
        if not batch:
            break
        yield batch, total
        pages += 1
        if not has_more and len(batch) < PAGINATION_LIMIT:
            break
        offset += PAGINATION_LIMIT


def iter_paginated_collection(path, max_pages=1_000, params=None):
    offset = int((params or {}).get("offset", 0))
    pages = 0
    while pages < max_pages:
        page_params = dict(params or {})
        page_params["limit"] = int(page_params.get("limit", PAGINATION_LIMIT))
        page_params["offset"] = offset
        data = api_get(path, page_params)
        batch = data.get("data", []) if isinstance(data, dict) else []
        if not batch:
            break
        yield batch, data
        pages += 1
        if len(batch) < page_params["limit"]:
            break
        offset += page_params["limit"]


def classify_reply(text):
    detail = classify_reply_intent(text)
    intent = detail["intent"]
    if intent in {"meeting_signal", "positive_interest", "existing_customer"}:
        return "positive"
    if intent in {"not_interested"}:
        return "negative"
    if intent in {"redirect", "wrong_person"}:
        return "redirect"
    if intent == "auto_reply":
        return "auto_reply"
    return "neutral"


def classify_reply_intent(text):
    content = (text or "").strip().lower()
    if not content:
        return {"intent": "empty", "matched_pattern": "", "simple_class": "neutral"}
    for intent, patterns in REPLY_INTENT_RULES:
        for pattern in patterns:
            if re.search(pattern, content):
                simple_class = classify_reply_simple(intent)
                return {
                    "intent": intent,
                    "matched_pattern": pattern,
                    "simple_class": simple_class,
                }
    return {"intent": "neutral", "matched_pattern": "", "simple_class": "neutral"}


def classify_reply_simple(intent):
    if intent in {"meeting_signal", "positive_interest", "existing_customer"}:
        return "positive"
    if intent == "not_interested":
        return "negative"
    if intent in {"redirect", "wrong_person"}:
        return "redirect"
    if intent == "auto_reply":
        return "auto_reply"
    return "neutral"


def cmd_docs(args):
    print("GetSales docs:")
    print(f"- openapi: {DOCS_INDEX_URL}")
    print(f"- quick start: {DOCS_QUICKSTART_URL}")
    print(f"- import help: {DOCS_IMPORT_URL}")
    print(f"- note: {FLOW_UUID_FILTER_WARNING}")


def cmd_lists(args):
    params = {"limit": args.limit, "offset": args.offset}
    data = api_get("/leads/api/lists", params)
    items = data.get("data", []) if isinstance(data, dict) else data
    if args.search:
        q = args.search.lower()
        items = [x for x in items if q in str(x.get("name", "")).lower()]
    if args.json:
        out(items)
        return
    print(f"\n{'UUID':<36} {'Name'}")
    print("-" * 100)
    for item in items:
        print(f"{item.get('uuid', ''):<36} {item.get('name', '')}")
    print(f"\nReturned: {len(items)}")


def cmd_list_get(args):
    out(api_get(f"/leads/api/lists/{args.list_uuid}"))


def cmd_flows(args):
    params = {"limit": args.limit, "offset": args.offset}
    if args.search:
        params["filter"] = args.search
    data = api_get("/flows/api/flows", params)
    items = data.get("data", []) if isinstance(data, dict) else data
    if args.search:
        q = args.search.lower()
        items = [x for x in items if q in str(x.get("name", "")).lower()]
    if args.status:
        items = [x for x in items if str(x.get("status", "")).lower() == args.status.lower()]
    if args.json:
        out(items)
        return
    print(f"\n{'UUID':<36} {'Status':<12} {'Name'}")
    print("-" * 120)
    for item in items:
        print(f"{item.get('uuid', ''):<36} {str(item.get('status', '')):<12} {item.get('name', '')}")
    print(f"\nReturned: {len(items)}")


def cmd_flow_start(args):
    if maybe_dry_run(args, "PUT", f"/flows/api/flows/{args.flow_uuid}/start"):
        return
    out(api_put(f"/flows/api/flows/{args.flow_uuid}/start"))


def cmd_flow_stop(args):
    if maybe_dry_run(args, "PUT", f"/flows/api/flows/{args.flow_uuid}/stop"):
        return
    out(api_put(f"/flows/api/flows/{args.flow_uuid}/stop"))


def cmd_sender_profiles(args):
    params = {"limit": args.limit, "offset": args.offset}
    data = api_get("/flows/api/sender-profiles", params)
    items = data.get("data", []) if isinstance(data, dict) else data
    if args.search:
        q = args.search.lower()
        items = [
            x for x in items
            if q in str(x.get("name", "")).lower() or q in str(x.get("email", "")).lower()
        ]
    if args.json:
        out(items)
        return
    print(f"\n{'UUID':<36} {'Name':<28} {'Email'}")
    print("-" * 120)
    for item in items:
        print(f"{item.get('uuid', ''):<36} {str(item.get('name', '')):<28} {item.get('email', '')}")
    print(f"\nReturned: {len(items)}")


def cmd_contacts_search(args):
    filter_obj = maybe_json(args.filter_json, "filter-json") if args.filter_json else {}
    if args.flow_uuid:
        print(FLOW_UUID_FILTER_WARNING, file=sys.stderr)
        filter_obj["flow_uuid"] = args.flow_uuid
    for key in ("email", "linkedin_id", "company_name", "list_uuid", "name"):
        value = getattr(args, key, None)
        if value:
            filter_obj[key] = value
    payload = {
        "filter": filter_obj,
        "limit": args.limit,
        "offset": args.offset,
        "order_field": args.order_field,
        "order_type": args.order_type,
    }
    data = api_post("/leads/api/leads/search", payload)
    if args.json:
        out(data)
        return
    items = data.get("data", []) if isinstance(data, dict) else []
    total = data.get("total", len(items)) if isinstance(data, dict) else len(items)
    print(f"\nSearch returned {len(items)} / total {total}\n")
    for item in items:
        lead = extract_lead(item)
        flows = item.get("flows", []) if isinstance(item, dict) else []
        print(
            f"- {lead.get('uuid', '')} | {lead.get('first_name', '')} {lead.get('last_name', '')} | "
            f"{lead.get('company_name', '')} | {lead.get('linkedin', '') or lead.get('linkedin_id', '')} | "
            f"flows={len(flows)}"
        )


def cmd_contact_get(args):
    out(api_get(f"/leads/api/leads/{args.lead_uuid}"))


def cmd_contacts_export(args):
    filter_obj = maybe_json(args.filter_json, "filter-json") if args.filter_json else {}
    if args.flow_uuid:
        print(FLOW_UUID_FILTER_WARNING, file=sys.stderr)
        filter_obj["flow_uuid"] = args.flow_uuid

    rows = []
    total = 0
    for batch, total in iter_paginated_search(filter_obj, max_pages=args.max_pages):
        rows.extend(batch)

    if args.output.endswith(".json"):
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)
    else:
        flat = []
        for item in rows:
            lead = extract_lead(item)
            flat.append({
                "uuid": lead.get("uuid", ""),
                "first_name": lead.get("first_name", ""),
                "last_name": lead.get("last_name", ""),
                "company_name": lead.get("company_name", ""),
                "linkedin": lead.get("linkedin", ""),
                "ln_id": lead.get("ln_id", ""),
                "email": lead.get("work_email") or lead.get("email") or "",
                "position": lead.get("position", ""),
                "raw_address": lead.get("raw_address", ""),
                "status": lead.get("status", ""),
                "linkedin_status": lead.get("linkedin_status", ""),
                "email_status": lead.get("email_status", ""),
                "list_uuid": lead.get("list_uuid", ""),
                "flow_count": len(item.get("flows", [])) if isinstance(item, dict) else 0,
                "custom_fields": json.dumps(item.get("custom_fields", {}), ensure_ascii=False),
            })
        fieldnames = list(flat[0].keys()) if flat else [
            "uuid", "first_name", "last_name", "company_name", "linkedin", "ln_id",
            "email", "position", "raw_address", "status", "linkedin_status",
            "email_status", "list_uuid", "flow_count", "custom_fields",
        ]
        with open(args.output, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(flat)
    print(f"Exported {len(rows)} contacts to {args.output} (reported total={total})")


def cmd_contact_upsert(args):
    lead = load_json_file(args.lead_json, "lead-json")
    custom_fields = maybe_json(args.custom_fields_json, "custom-fields-json") if args.custom_fields_json else {}
    body = {
        "lead": lead,
        "list_uuid": args.list_uuid,
        "update_if_exists": not args.no_update,
        "move_to_list": args.move_to_list,
    }
    if custom_fields:
        body["custom_fields"] = custom_fields
    if maybe_dry_run(args, "POST", "/leads/api/leads/upsert", body=body):
        return
    out(api_post("/leads/api/leads/upsert", body))


def cmd_contact_update(args):
    body = maybe_json(args.update_json, "update-json")
    if maybe_dry_run(args, "PUT", f"/leads/api/leads/{args.lead_uuid}", body=body):
        return
    out(api_put(f"/leads/api/leads/{args.lead_uuid}", body))


def cmd_contact_delete(args):
    if maybe_dry_run(args, "DELETE", f"/leads/api/leads/{args.lead_uuid}"):
        return
    out(api_delete(f"/leads/api/leads/{args.lead_uuid}"))


def cmd_flow_add_existing(args):
    if maybe_dry_run(args, "POST", f"/flows/api/flows/{args.flow_uuid}/leads/{args.lead_uuid}"):
        return
    out(api_post(f"/flows/api/flows/{args.flow_uuid}/leads/{args.lead_uuid}"))


def cmd_flow_add_new(args):
    lead = load_json_file(args.lead_json, "lead-json")
    custom_fields = maybe_json(args.custom_fields_json, "custom-fields-json") if args.custom_fields_json else {}
    body = {
        "lead": lead,
        "list_uuid": args.list_uuid,
        "update_lead_if_exists": not args.no_update,
        "move_to_list": args.move_to_list,
        "skip_if_lead_exists": args.skip_if_exists,
    }
    if args.flow_segment_id:
        body["flow_segment_id"] = args.flow_segment_id
    if custom_fields:
        body["custom_fields"] = custom_fields
    if maybe_dry_run(args, "POST", f"/flows/api/flows/{args.flow_uuid}/add-new-lead", body=body):
        return
    out(api_post(f"/flows/api/flows/{args.flow_uuid}/add-new-lead", body))


def cmd_flow_cancel(args):
    flow_uuids = [x.strip() for x in args.flow_uuids.split(",") if x.strip()]
    body = {"flow_uuids": flow_uuids}
    if maybe_dry_run(args, "PUT", f"/flows/api/flows/leads/{args.lead_uuid}/cancel", body=body):
        return
    out(api_put(f"/flows/api/flows/leads/{args.lead_uuid}/cancel", body))


def cmd_flow_cancel_all(args):
    if maybe_dry_run(args, "PUT", f"/flows/api/flows/leads/{args.lead_uuid}/cancel-all"):
        return
    out(api_put(f"/flows/api/flows/leads/{args.lead_uuid}/cancel-all"))


def cmd_inbox(args):
    params = {
        "limit": args.limit,
        "offset": args.offset,
        "order_field": args.order_field,
        "order_type": args.order_type,
    }
    if args.type != "all":
        params["filter[type]"] = args.type
    if args.lead_uuid:
        params["filter[lead_uuid]"] = args.lead_uuid
    if args.conversation_uuid:
        params["filter[linkedin_conversation_uuid]"] = args.conversation_uuid
    if args.sender_profile_uuid:
        params["filter[sender_profile_uuid]"] = args.sender_profile_uuid
    if args.uuid:
        params["filter[uuid]"] = args.uuid
    data = api_get("/flows/api/linkedin-messages", params)
    if args.json:
        out(data)
        return
    items = data.get("data", []) if isinstance(data, dict) else []
    total = data.get("total", len(items)) if isinstance(data, dict) else len(items)
    print(f"\nMessages returned {len(items)} / total {total}\n")
    for item in items:
        automation = extract_automation(item)
        sender = item.get("sender_profile_uuid") or (item.get("sender_profile") or {}).get("uuid", "")
        text = str(item.get("text", "")).replace("\n", " ")[:120]
        print(
            f"- {item.get('uuid', '')} | lead={item.get('lead_uuid', '')} | type={item.get('type', '')} | "
            f"sender={sender} | flow={automation.get('uuid', '')} {automation.get('name', '')} | {text}"
        )


def cmd_inbox_export(args):
    params = {
        "order_field": args.order_field,
        "order_type": args.order_type,
    }
    if args.type != "all":
        params["filter[type]"] = args.type
    if args.lead_uuid:
        params["filter[lead_uuid]"] = args.lead_uuid
    if args.conversation_uuid:
        params["filter[linkedin_conversation_uuid]"] = args.conversation_uuid
    if args.sender_profile_uuid:
        params["filter[sender_profile_uuid]"] = args.sender_profile_uuid

    rows = []
    total = 0
    for batch, total in iter_paginated_messages(params, max_pages=args.max_pages):
        rows.extend(batch)

    if args.output.endswith(".json"):
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)
    else:
        flat = []
        for item in rows:
            automation = extract_automation(item)
            sender = item.get("sender_profile_uuid") or (item.get("sender_profile") or {}).get("uuid", "")
            flat.append({
                "uuid": item.get("uuid", ""),
                "lead_uuid": item.get("lead_uuid", ""),
                "conversation_uuid": item.get("linkedin_conversation_uuid", ""),
                "type": item.get("type", ""),
                "sender_profile_uuid": sender,
                "automation_uuid": automation.get("uuid", ""),
                "automation_name": automation.get("name", ""),
                "sent_at": item.get("sent_at", ""),
                "created_at": item.get("created_at", ""),
                "text": item.get("text", ""),
            })
        fieldnames = list(flat[0].keys()) if flat else [
            "uuid", "lead_uuid", "conversation_uuid", "type", "sender_profile_uuid",
            "automation_uuid", "automation_name", "sent_at", "created_at", "text"
        ]
        with open(args.output, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(flat)
    print(f"Exported {len(rows)} messages to {args.output} (reported total={total})")


def build_message_filters(args, force_inbox=False):
    params = {
        "order_field": args.order_field,
        "order_type": args.order_type,
    }
    message_type = "inbox" if force_inbox else args.type
    if message_type != "all":
        params["filter[type]"] = message_type
    if getattr(args, "lead_uuid", None):
        params["filter[lead_uuid]"] = args.lead_uuid
    if getattr(args, "conversation_uuid", None):
        params["filter[linkedin_conversation_uuid]"] = args.conversation_uuid
    if getattr(args, "sender_profile_uuid", None):
        params["filter[sender_profile_uuid]"] = args.sender_profile_uuid
    if getattr(args, "uuid", None):
        params["filter[uuid]"] = args.uuid
    if getattr(args, "search", None):
        params["filter[q]"] = args.search
    if getattr(args, "status", None):
        params["filter[status]"] = args.status
    if getattr(args, "automation", None):
        params["filter[automation]"] = args.automation
    return params


def cmd_replies(args):
    params = build_message_filters(args, force_inbox=True)
    params["limit"] = args.limit
    params["offset"] = args.offset
    data = api_get("/flows/api/linkedin-messages", params)
    if args.json:
        out(data)
        return
    items = data.get("data", []) if isinstance(data, dict) else []
    total = data.get("total", len(items)) if isinstance(data, dict) else len(items)
    print(f"\nReplies returned {len(items)} / total {total}\n")
    for item in items:
        automation = extract_automation(item)
        intel = classify_reply_intent(item.get("text", ""))
        text = str(item.get("text", "")).replace("\n", " ")[:140]
        print(
            f"- {item.get('uuid', '')} | class={intel['simple_class']} | intent={intel['intent']} | lead={item.get('lead_uuid', '')} | "
            f"sender={item.get('sender_profile_uuid', '')} | flow={automation.get('name', '') or automation.get('uuid', '')} | {text}"
        )


def cmd_reply_intel(args):
    params = build_message_filters(args, force_inbox=True)
    params["limit"] = args.limit
    params["offset"] = args.offset
    data = api_get("/flows/api/linkedin-messages", params)
    items = data.get("data", []) if isinstance(data, dict) else []
    total = data.get("total", len(items)) if isinstance(data, dict) else len(items)
    if args.json:
        payload = []
        for item in items:
            intel = classify_reply_intent(item.get("text", ""))
            row = dict(item)
            row["reply_intent"] = intel["intent"]
            row["reply_class"] = intel["simple_class"]
            row["matched_pattern"] = intel["matched_pattern"]
            payload.append(row)
        out({"data": payload, "total": total, "limit": args.limit, "offset": args.offset})
        return
    print(f"\nReply intel returned {len(items)} / total {total}\n")
    for item in items:
        automation = extract_automation(item)
        intel = classify_reply_intent(item.get("text", ""))
        text = str(item.get("text", "")).replace("\n", " ")[:180]
        print(
            f"- {item.get('uuid', '')} | intent={intel['intent']} | class={intel['simple_class']} | "
            f"lead={item.get('lead_uuid', '')} | flow={automation.get('name', '') or automation.get('uuid', '')} | {text}"
        )


def cmd_replies_export(args):
    params = build_message_filters(args, force_inbox=True)
    rows = []
    total = 0
    for batch, data in iter_paginated_messages(params, max_pages=args.max_pages):
        rows.extend(batch)
        total = data
    reported_total = total if isinstance(total, int) else len(rows)
    if args.output.endswith(".json"):
        payload = []
        for item in rows:
            copy = dict(item)
            intel = classify_reply_intent(item.get("text", ""))
            copy["reply_class"] = intel["simple_class"]
            copy["reply_intent"] = intel["intent"]
            copy["matched_pattern"] = intel["matched_pattern"]
            payload.append(copy)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
    else:
        flat = []
        for item in rows:
            automation = extract_automation(item)
            intel = classify_reply_intent(item.get("text", ""))
            flat.append({
                "uuid": item.get("uuid", ""),
                "lead_uuid": item.get("lead_uuid", ""),
                "conversation_uuid": item.get("linkedin_conversation_uuid", ""),
                "sender_profile_uuid": item.get("sender_profile_uuid", ""),
                "automation_uuid": automation.get("uuid", ""),
                "automation_name": automation.get("name", ""),
                "reply_class": intel["simple_class"],
                "reply_intent": intel["intent"],
                "matched_pattern": intel["matched_pattern"],
                "status": item.get("status", ""),
                "sent_at": item.get("sent_at", ""),
                "created_at": item.get("created_at", ""),
                "text": item.get("text", ""),
            })
        fieldnames = list(flat[0].keys()) if flat else [
            "uuid", "lead_uuid", "conversation_uuid", "sender_profile_uuid",
            "automation_uuid", "automation_name", "reply_class", "reply_intent", "matched_pattern", "status",
            "sent_at", "created_at", "text",
        ]
        with open(args.output, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(flat)
    print(f"Exported {len(rows)} replies to {args.output} (reported total={reported_total})")


def cmd_stats_contacts(args):
    filter_obj = maybe_json(args.filter_json, "filter-json") if args.filter_json else {}
    if args.flow_uuid:
        print(FLOW_UUID_FILTER_WARNING, file=sys.stderr)
        filter_obj["flow_uuid"] = args.flow_uuid

    status_counts = Counter()
    linkedin_status_counts = Counter()
    email_status_counts = Counter()
    list_counts = Counter()
    flow_counts = Counter()
    total_rows = 0

    for batch, total in iter_paginated_search(filter_obj, max_pages=args.max_pages):
        for item in batch:
            lead = extract_lead(item)
            total_rows += 1
            status_counts[str(lead.get("status", "") or "EMPTY")] += 1
            linkedin_status_counts[str(lead.get("linkedin_status", "") or "EMPTY")] += 1
            email_status_counts[str(lead.get("email_status", "") or "EMPTY")] += 1
            list_counts[str(lead.get("list_uuid", "") or "EMPTY")] += 1
            for flow in item.get("flows", []) if isinstance(item, dict) else []:
                flow_counts[str(flow.get("flow_uuid", "") or flow.get("uuid", "") or "EMPTY")] += 1

    out({
        "total_rows": total_rows,
        "status_counts": dict(status_counts.most_common()),
        "linkedin_status_counts": dict(linkedin_status_counts.most_common()),
        "email_status_counts": dict(email_status_counts.most_common()),
        "top_list_uuids": dict(list_counts.most_common(20)),
        "top_flow_uuids": dict(flow_counts.most_common(20)),
    })


def cmd_stats_messages(args):
    params = build_message_filters(args)

    type_counts = Counter()
    sender_counts = Counter()
    flow_counts = Counter()
    lead_counts = Counter()
    total_rows = 0

    for batch, total in iter_paginated_messages(params, max_pages=args.max_pages):
        for item in batch:
            total_rows += 1
            type_counts[str(item.get("type", "") or "EMPTY")] += 1
            sender = item.get("sender_profile_uuid") or (item.get("sender_profile") or {}).get("uuid", "")
            sender_counts[str(sender or "EMPTY")] += 1
            automation = extract_automation(item)
            flow_key = automation.get("uuid") or automation.get("name") or "EMPTY"
            flow_counts[str(flow_key)] += 1
            lead_counts[str(item.get("lead_uuid", "") or "EMPTY")] += 1

    out({
        "total_rows": total_rows,
        "message_type_counts": dict(type_counts.most_common()),
        "top_sender_profiles": dict(sender_counts.most_common(20)),
        "top_flows": dict(flow_counts.most_common(20)),
        "top_leads": dict(lead_counts.most_common(20)),
    })


def cmd_stats_replies(args):
    params = build_message_filters(args, force_inbox=True)
    class_counts = Counter()
    intent_counts = Counter()
    sender_counts = Counter()
    flow_counts = Counter()
    lead_counts = Counter()
    status_counts = Counter()
    total_rows = 0

    for batch, total in iter_paginated_messages(params, max_pages=args.max_pages):
        for item in batch:
            total_rows += 1
            intel = classify_reply_intent(item.get("text", ""))
            class_counts[intel["simple_class"]] += 1
            intent_counts[intel["intent"]] += 1
            sender = item.get("sender_profile_uuid") or (item.get("sender_profile") or {}).get("uuid", "")
            sender_counts[str(sender or "EMPTY")] += 1
            automation = extract_automation(item)
            flow_key = automation.get("uuid") or automation.get("name") or "EMPTY"
            flow_counts[str(flow_key)] += 1
            lead_counts[str(item.get("lead_uuid", "") or "EMPTY")] += 1
            status_counts[str(item.get("status", "") or "EMPTY")] += 1

    out({
        "total_rows": total_rows,
        "reply_class_counts": dict(class_counts.most_common()),
        "reply_intent_counts": dict(intent_counts.most_common()),
        "message_status_counts": dict(status_counts.most_common()),
        "top_sender_profiles": dict(sender_counts.most_common(20)),
        "top_flows": dict(flow_counts.most_common(20)),
        "top_leads": dict(lead_counts.most_common(20)),
        "classification_note": "Heuristic intent classification. Validate important edge cases manually.",
    })


def cmd_stats_flows(args):
    params = {"limit": PAGINATION_LIMIT, "offset": 0}
    status_counts = Counter()
    timezone_counts = Counter()
    visibility_counts = Counter()
    owner_counts = Counter()
    total_rows = 0

    for batch, _ in iter_paginated_collection("/flows/api/flows", max_pages=args.max_pages, params=params):
        for item in batch:
            total_rows += 1
            status_counts[str(item.get("status", "") or "EMPTY")] += 1
            timezone = (((item.get("schedule") or {}).get("timezone")) or "EMPTY")
            timezone_counts[str(timezone)] += 1
            visibility_counts["public" if item.get("is_public") else "private"] += 1
            owner_counts[str(item.get("user_id", "") or "EMPTY")] += 1

    out({
        "total_rows": total_rows,
        "status_counts": dict(status_counts.most_common()),
        "visibility_counts": dict(visibility_counts.most_common()),
        "top_timezones": dict(timezone_counts.most_common(20)),
        "top_owner_user_ids": dict(owner_counts.most_common(20)),
    })


def cmd_stats_senders(args):
    params = {"limit": PAGINATION_LIMIT, "offset": 0}
    status_counts = Counter()
    label_counts = Counter()
    timezone_counts = Counter()
    smart_limits_counts = Counter()
    total_rows = 0

    for batch, _ in iter_paginated_collection("/flows/api/sender-profiles", max_pages=args.max_pages, params=params):
        for item in batch:
            total_rows += 1
            status_counts[str(item.get("status", "") or "EMPTY")] += 1
            label_counts[str(item.get("label", "") or "EMPTY")] += 1
            timezone = (((item.get("linkedin_schedule") or {}).get("timezone")) or "EMPTY")
            timezone_counts[str(timezone)] += 1
            smart_limits_counts[str(bool(item.get("smart_limits_enabled"))).lower()] += 1

    out({
        "total_rows": total_rows,
        "status_counts": dict(status_counts.most_common()),
        "smart_limits_enabled_counts": dict(smart_limits_counts.most_common()),
        "top_labels": dict(label_counts.most_common(20)),
        "top_timezones": dict(timezone_counts.most_common(20)),
    })


def build_parser():
    parser = argparse.ArgumentParser(prog="getsales", description="Universal GetSales API CLI")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("docs", help="Show GetSales documentation entry points")
    p.set_defaults(func=cmd_docs)

    p = sub.add_parser("lists", help="List GetSales lists")
    p.add_argument("--search")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_lists)

    p = sub.add_parser("list-get", help="Get one list by UUID")
    p.add_argument("list_uuid")
    p.set_defaults(func=cmd_list_get)

    p = sub.add_parser("flows", help="List GetSales flows")
    p.add_argument("--search")
    p.add_argument("--status")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_flows)

    p = sub.add_parser("flow-start", help="Start a flow")
    p.add_argument("flow_uuid")
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_flow_start)

    p = sub.add_parser("flow-stop", help="Stop a flow")
    p.add_argument("flow_uuid")
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_flow_stop)

    p = sub.add_parser("sender-profiles", help="List sender profiles")
    p.add_argument("--search")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_sender_profiles)

    p = sub.add_parser("contacts-search", help="Search contacts")
    p.add_argument("--filter-json")
    p.add_argument("--email")
    p.add_argument("--linkedin-id")
    p.add_argument("--company-name")
    p.add_argument("--list-uuid")
    p.add_argument("--name")
    p.add_argument("--flow-uuid")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--order-field", default="created_at")
    p.add_argument("--order-type", default="desc", choices=["asc", "desc"])
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_contacts_search)

    p = sub.add_parser("contact-get", help="Get full contact envelope by UUID")
    p.add_argument("lead_uuid")
    p.set_defaults(func=cmd_contact_get)

    p = sub.add_parser("contacts-export", help="Export contacts search results")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--filter-json")
    p.add_argument("--flow-uuid")
    p.add_argument("--max-pages", type=int, default=50)
    p.set_defaults(func=cmd_contacts_export)

    p = sub.add_parser("contact-upsert", help="Create or update a contact in a list")
    p.add_argument("list_uuid")
    p.add_argument("lead_json")
    p.add_argument("--custom-fields-json")
    p.add_argument("--move-to-list", action="store_true")
    p.add_argument("--no-update", action="store_true")
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_contact_upsert)

    p = sub.add_parser("contact-update", help="Update contact by UUID")
    p.add_argument("lead_uuid")
    p.add_argument("update_json")
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_contact_update)

    p = sub.add_parser("contact-delete", help="Delete contact by UUID")
    p.add_argument("lead_uuid")
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_contact_delete)

    p = sub.add_parser("flow-add-existing", help="Add existing contact to flow")
    p.add_argument("flow_uuid")
    p.add_argument("lead_uuid")
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_flow_add_existing)

    p = sub.add_parser("flow-add-new", help="Create/update contact and attach it to a flow")
    p.add_argument("flow_uuid")
    p.add_argument("list_uuid")
    p.add_argument("lead_json")
    p.add_argument("--custom-fields-json")
    p.add_argument("--move-to-list", action="store_true")
    p.add_argument("--no-update", action="store_true")
    p.add_argument("--skip-if-exists", action="store_true")
    p.add_argument("--flow-segment-id", type=int)
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_flow_add_new)

    p = sub.add_parser("flow-cancel", help="Cancel a lead from specific flows")
    p.add_argument("lead_uuid")
    p.add_argument("flow_uuids", help="Comma-separated flow UUIDs")
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_flow_cancel)

    p = sub.add_parser("flow-cancel-all", help="Cancel a lead from all flows")
    p.add_argument("lead_uuid")
    add_dry_run_flag(p)
    p.set_defaults(func=cmd_flow_cancel_all)

    p = sub.add_parser("inbox", help="List LinkedIn messages")
    p.add_argument("--type", default="all", choices=["all", "inbox", "outbox"])
    p.add_argument("--lead-uuid")
    p.add_argument("--conversation-uuid")
    p.add_argument("--sender-profile-uuid")
    p.add_argument("--uuid")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--order-field", default="created_at")
    p.add_argument("--order-type", default="desc", choices=["asc", "desc"])
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_inbox)

    p = sub.add_parser("inbox-export", help="Export LinkedIn messages")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--type", default="all", choices=["all", "inbox", "outbox"])
    p.add_argument("--lead-uuid")
    p.add_argument("--conversation-uuid")
    p.add_argument("--sender-profile-uuid")
    p.add_argument("--max-pages", type=int, default=50)
    p.add_argument("--order-field", default="created_at")
    p.add_argument("--order-type", default="desc", choices=["asc", "desc"])
    p.set_defaults(func=cmd_inbox_export)

    p = sub.add_parser("replies", help="List inbound replies with simple classification")
    p.add_argument("--lead-uuid")
    p.add_argument("--conversation-uuid")
    p.add_argument("--sender-profile-uuid")
    p.add_argument("--uuid")
    p.add_argument("--search")
    p.add_argument("--status")
    p.add_argument("--automation")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--order-field", default="created_at")
    p.add_argument("--order-type", default="desc", choices=["asc", "desc"])
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_replies)

    p = sub.add_parser("reply-intel", help="List inbound replies with richer intent classification")
    p.add_argument("--lead-uuid")
    p.add_argument("--conversation-uuid")
    p.add_argument("--sender-profile-uuid")
    p.add_argument("--uuid")
    p.add_argument("--search")
    p.add_argument("--status")
    p.add_argument("--automation")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--order-field", default="created_at")
    p.add_argument("--order-type", default="desc", choices=["asc", "desc"])
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_reply_intel)

    p = sub.add_parser("replies-export", help="Export inbound replies with simple classification")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--lead-uuid")
    p.add_argument("--conversation-uuid")
    p.add_argument("--sender-profile-uuid")
    p.add_argument("--search")
    p.add_argument("--status")
    p.add_argument("--automation")
    p.add_argument("--max-pages", type=int, default=50)
    p.add_argument("--order-field", default="created_at")
    p.add_argument("--order-type", default="desc", choices=["asc", "desc"])
    p.set_defaults(func=cmd_replies_export)

    p = sub.add_parser("stats-contacts", help="Aggregate contact statuses over paginated search")
    p.add_argument("--filter-json")
    p.add_argument("--flow-uuid")
    p.add_argument("--max-pages", type=int, default=50)
    p.set_defaults(func=cmd_stats_contacts)

    p = sub.add_parser("stats-messages", help="Aggregate message stats over paginated inbox/outbox")
    p.add_argument("--type", default="all", choices=["all", "inbox", "outbox"])
    p.add_argument("--lead-uuid")
    p.add_argument("--conversation-uuid")
    p.add_argument("--sender-profile-uuid")
    p.add_argument("--max-pages", type=int, default=50)
    p.add_argument("--order-field", default="created_at")
    p.add_argument("--order-type", default="desc", choices=["asc", "desc"])
    p.set_defaults(func=cmd_stats_messages)

    p = sub.add_parser("stats-replies", help="Aggregate inbound replies with simple classification")
    p.add_argument("--lead-uuid")
    p.add_argument("--conversation-uuid")
    p.add_argument("--sender-profile-uuid")
    p.add_argument("--search")
    p.add_argument("--status")
    p.add_argument("--automation")
    p.add_argument("--max-pages", type=int, default=50)
    p.add_argument("--order-field", default="created_at")
    p.add_argument("--order-type", default="desc", choices=["asc", "desc"])
    p.set_defaults(func=cmd_stats_replies)

    p = sub.add_parser("stats-flows", help="Aggregate flow inventory and status distribution")
    p.add_argument("--max-pages", type=int, default=50)
    p.set_defaults(func=cmd_stats_flows)

    p = sub.add_parser("stats-senders", help="Aggregate sender profile inventory and status distribution")
    p.add_argument("--max-pages", type=int, default=50)
    p.set_defaults(func=cmd_stats_senders)

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
