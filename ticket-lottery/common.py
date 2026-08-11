"""Shared helpers for the Phase 1 automation (notify / reconcile / weekly)."""

import json
import os
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
EMAILS = os.path.join(HERE, "emails")
OUTBOX = os.path.join(HERE, "outbox")

DAY = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTH = ["January", "February", "March", "April", "May", "June",
         "July", "August", "September", "October", "November", "December"]


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def save(name, obj):
    with open(os.path.join(DATA, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


def load_config():
    with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def parse_dt(s):
    """Accept 'YYYY-MM-DD' or a full ISO timestamp."""
    if len(s) == 10:
        return datetime.strptime(s, "%Y-%m-%d")
    return datetime.fromisoformat(s)


def now_or(as_of):
    return parse_dt(as_of) if as_of else datetime.now()


def fmt_date(iso):
    d = parse_dt(iso)
    return f"{DAY[d.weekday()]}, {MONTH[d.month - 1]} {d.day}"


def fmt_datetime(dt):
    h = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{DAY[dt.weekday()]}, {MONTH[dt.month - 1]} {dt.day} at {h}:{dt.minute:02d} {ampm}"


def fmt_time(hhmm):
    try:
        h, m = map(int, hhmm.split(":"))
    except (ValueError, AttributeError):
        return hhmm
    hh = h % 12 or 12
    return f"{hh}:{m:02d} {'AM' if h < 12 else 'PM'}"


def render(template_name, mapping):
    """Fill {{placeholders}} in an emails/ template."""
    with open(os.path.join(EMAILS, template_name), encoding="utf-8") as f:
        html = f.read()
    for k, v in mapping.items():
        html = html.replace("{{" + k + "}}", str(v))
    return html


def write_outbox(label, emails):
    """emails: list of {to, subject, filename, html}. Writes them under
    outbox/<label>/ with an index.json manifest a send step can consume.
    The outbox holds names + emails, so it is git-ignored."""
    out = os.path.join(OUTBOX, label)
    os.makedirs(out, exist_ok=True)
    manifest = []
    for e in emails:
        with open(os.path.join(out, e["filename"]), "w", encoding="utf-8") as f:
            f.write(e["html"])
        manifest.append({"to": e["to"], "subject": e["subject"], "file": e["filename"]})
    with open(os.path.join(out, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"generated": datetime.now().isoformat(timespec="seconds"),
                   "count": len(manifest), "emails": manifest}, f, indent=2)
    return out, manifest
