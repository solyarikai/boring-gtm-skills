import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_getsales():
    spec = importlib.util.spec_from_file_location("getsales_cli", ROOT / "getsales" / "getsales.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_reply_classifier_fixture_buckets():
    getsales = load_getsales()
    rows = json.loads((ROOT / "examples" / "getsales" / "reply_export.sample.json").read_text())
    intents = [getsales.classify_reply_intent(row["text"])["intent"] for row in rows]
    assert intents == [
        "meeting_signal",
        "redirect",
        "timing_later",
        "not_interested",
        "auto_reply",
    ]
