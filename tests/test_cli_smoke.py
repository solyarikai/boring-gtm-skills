import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_cmd(*args):
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True)


def test_help_and_docs_without_api_keys():
    commands = [
        (sys.executable, "getsales/getsales.py", "--help"),
        (sys.executable, "smartlead/smartlead.py", "--help"),
        (sys.executable, "getsales/getsales.py", "docs"),
        (sys.executable, "smartlead/smartlead.py", "docs"),
    ]
    for cmd in commands:
        result = run_cmd(*cmd)
        assert result.returncode == 0, result.stderr


def test_smartlead_live_upload_requires_confirm_live():
    result = run_cmd(
        sys.executable,
        "smartlead/smartlead.py",
        "leads-add",
        "123",
        "examples/smartlead/leads.valid.json",
    )
    assert result.returncode == 2
    assert "--confirm-live" in result.stderr


def test_smartlead_dry_run_redacts_api_key_placeholder():
    result = run_cmd(
        sys.executable,
        "smartlead/smartlead.py",
        "leads-add",
        "123",
        "examples/smartlead/leads.valid.json",
        "--dry-run",
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout.splitlines()[0] if False else result.stdout)
    assert payload["dry_run"] is True
    assert "SMARTLEAD_API_KEY" in payload["url"]
    assert "your_key_here" not in result.stdout


def test_smartlead_sequence_validate_fixture():
    result = run_cmd(
        sys.executable,
        "smartlead/smartlead.py",
        "sequence-validate",
        "examples/smartlead/sequences.sample.json",
    )
    assert result.returncode == 0, result.stderr
    assert "errors: 0" in result.stdout


def test_smartlead_prepare_upload_fixture(tmp_path):
    output_dir = tmp_path / "smartlead_upload"
    result = run_cmd(
        sys.executable,
        "smartlead/smartlead.py",
        "prepare-upload",
        "123",
        "examples/smartlead/leads.valid.json",
        "--blocklist-csv",
        "examples/smartlead/blocklist.csv",
        "--output-dir",
        str(output_dir),
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads((output_dir / "summary.json").read_text())
    assert summary["ready_leads"] == 2
    assert summary["rejected_leads"] == 0
    assert (output_dir / "payload_batches" / "batch_001.json").exists()


def test_getsales_reply_triage_fixture(tmp_path):
    output_dir = tmp_path / "reply_triage"
    result = run_cmd(
        sys.executable,
        "getsales/getsales.py",
        "reply-triage",
        "--fixture",
        "examples/getsales/reply_export.sample.json",
        "--automation",
        "flow_001",
        "--output-dir",
        str(output_dir),
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads((output_dir / "summary.json").read_text())
    assert summary["buckets"] == {
        "reply_now": 1,
        "redirect_research": 1,
        "follow_up_later": 1,
        "suppress": 1,
        "auto_reply_ignore": 1,
        "review": 0,
    }


def test_monthly_gtm_report_fixture_mode(tmp_path):
    output_dir = tmp_path / "monthly_report"
    result = run_cmd(
        sys.executable,
        "scripts/monthly_gtm_report.py",
        "--month",
        "2026-06",
        "--from-fixtures",
        "examples/reporting",
        "--output-dir",
        str(output_dir),
    )
    assert result.returncode == 0, result.stderr
    assert (output_dir / "monthly_report.html").exists()
    assert (output_dir / "reply_action_queue.csv").exists()
    assert "No production writes" in (output_dir / "monthly_report.html").read_text()


def test_private_marker_scan_is_clean():
    result = run_cmd(sys.executable, "scripts/scan_for_private_markers.py", "--root", ".")
    assert result.returncode == 0, result.stderr
