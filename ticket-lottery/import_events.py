#!/usr/bin/env python3
"""
Turn scraped Delta Center events into the lottery's events.json.

Input:  data/raw_events.json  (title / date / time / category / source_url),
        produced by scraping https://www.deltacenter.com/events.
Output: data/events.json      (adds league, tier, seats, max_party, entry_close,
                               a stable id, and status).

By default this MERGES: events already in events.json keep their status and any
manual tier / max_party overrides, so a refresh never un-draws or re-opens an
event. Use --replace to rebuild from scratch (e.g. the first real import, which
drops the sample events).

    python3 import_events.py            # merge refresh
    python3 import_events.py --replace  # fresh rebuild

Heuristics (safe defaults — adjust any event by hand afterwards):
  league   from category (Utah Jazz -> NBA, Utah Mammoth -> NHL).
  tier     concerts + other events -> premium; marquee NHL/NBA opponents ->
           premium; preseason and everyone else -> standard.
  max_party 2 for premium (spreads marquee seats across two households), else 4.
  entry_close = event date - config.entry_close_days.

NOTE: deltacenter.com/events lists Utah Mammoth, concerts, and other events but
NOT Utah Jazz games (published separately). Add Jazz to raw_events.json from
utahjazz.com when you want them in the pool.
"""

import argparse
import re
from datetime import timedelta

import common

# Marquee opponents that default to premium (high demand).
MARQUEE = {
    "oilers", "maple leafs", "penguins", "avalanche", "bruins", "rangers",
    "lightning", "golden knights", "red wings", "canadiens",          # NHL
    "lakers", "celtics", "warriors", "nuggets", "suns", "mavericks",
    "knicks", "heat", "bucks", "76ers", "thunder", "clippers",        # NBA
}


def slug(s):
    s = re.sub(r"\|\s*sold out", "", s, flags=re.I)
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s


def clean_title(t):
    return re.sub(r"\s*\|\s*sold out\s*$", "", t, flags=re.I).strip()


def to_24h(t):
    m = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", (t or "").strip().lower())
    if not m:
        return ""
    h = int(m.group(1)) % 12
    if m.group(3) == "pm":
        h += 12
    return f"{h:02d}:{m.group(2) or '00'}"


def league_of(raw):
    c = (raw.get("category") or "").strip().upper()
    if c in ("NBA", "NHL", "CONCERT", "OTHER"):
        return "Concert" if c == "CONCERT" else ("Other" if c == "OTHER" else c)
    title = raw["title"].lower()
    if "jazz" in title:
        return "NBA"
    if "mammoth" in title or "hockey" in title:
        return "NHL"
    return "Other"


def is_premium(raw, league):
    title = raw["title"].lower()
    if league in ("Concert", "Other"):
        return True
    if "preseason" in title:
        return False
    return any(team in title for team in MARQUEE)


def build_event(raw, config):
    league = league_of(raw)
    premium = is_premium(raw, league)
    date = raw["date"]
    close = (common.parse_dt(date) - timedelta(days=config.get("entry_close_days", 7))
             ).strftime("%Y-%m-%d")
    ev = {
        "id": f"{date}-{slug(raw['title'])}"[:80],
        "date": date,
        "tipoff": to_24h(raw.get("time", "")),
        "league": league,
        "title": clean_title(raw["title"]),
        "tier": "premium" if premium else "standard",
        "seats": config.get("seats_per_event", 4),
        "entry_close": close,
        # premium events go through the leadership draft first; standard events
        # go straight to the general entry pool.
        "status": "leadership" if premium else "open",
    }
    if premium:
        ev["max_party"] = 2
    if raw.get("source_url"):
        ev["source_url"] = raw["source_url"]
    if raw.get("image_url"):
        ev["image_url"] = raw["image_url"]
    return ev


def main():
    ap = argparse.ArgumentParser(description="Import Delta Center events -> events.json")
    ap.add_argument("--replace", action="store_true",
                    help="rebuild from scratch instead of merging")
    args = ap.parse_args()

    config = common.load_config()
    raw = common.load("raw_events.json")["events"]
    built = [build_event(r, config) for r in raw]

    if args.replace:
        merged = {e["id"]: e for e in built}
        kept = 0
    else:
        existing = common.load("events.json")
        merged = {e["id"]: e for e in existing.get("events", [])}
        kept = len(merged)
        for e in built:
            if e["id"] in merged:
                old = merged[e["id"]]
                # refresh facts, preserve status + manual tier/party overrides
                e["status"] = old.get("status", "open")
                if "tier" in old:
                    e["tier"] = old["tier"]
                if "max_party" in old:
                    e["max_party"] = old["max_party"]
                elif old.get("tier") == "standard":
                    e.pop("max_party", None)
            merged[e["id"]] = e

    events = sorted(merged.values(), key=lambda e: e["date"])
    doc = {
        "_comment": "Ticket inventory. Imported from deltacenter.com/events via import_events.py; edit tier/max_party/status by hand as needed. tier: premium | standard. max_party (optional) caps group size. status: open | drawn | closed.",
        "season": config.get("season", ""),
        "seat_location": config.get("seat_location", ""),
        "events": events,
    }
    common.save("events.json", doc)

    n_prem = sum(1 for e in events if e["tier"] == "premium")
    print(f"Imported {len(built)} event(s); events.json now has {len(events)} "
          f"({n_prem} premium, {len(events) - n_prem} standard)"
          + ("" if args.replace else f"; {kept} pre-existing preserved") + ".")
    for e in events:
        print(f"  {e['date']}  {e['league']:<8} {e['tier']:<8} {e['title']}")


if __name__ == "__main__":
    main()
