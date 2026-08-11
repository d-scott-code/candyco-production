#!/usr/bin/env python3
"""
CandyCo Delta Center Ticket Lottery — draw engine (Phase 0 pilot).

Runs the weighted lottery for one or more events and writes two files:

  data/results.json        PUBLIC, privacy-safe (first name + last initial only).
                           This is what the employee board reads.
  data/draw_details.json   PRIVATE, full names + emails, used to send the
                           notification emails. Never publish this file.

Weighting for each entrant on an event:

    weight = (1 base entry + earned points), capped at WEIGHT_CAP
    then a COOLDOWN is applied if they won recently (relative to THIS event's
    date), so tickets spread out:
        - premium event  -> recent winners are excluded (weight 0)
        - standard event -> recent winners' weight is multiplied by 0.25

Winners are drawn with a weighted random ordering (Efraimidis-Spirakis), then
seats are handed out in that order while keeping each person's requested party
(1-4 seats) together. Anyone not seated becomes the ordered waitlist used for
the no-show cascade.

Usage:
    python3 draw.py --all                 # draw every event with status "open"
    python3 draw.py --event <event_id>    # draw one specific event
    python3 draw.py --all --seed 42       # reproducible draw (for testing)
    python3 draw.py --all --commit        # also update members.json (last_won,
                                          #   reset points) and mark events drawn
"""

import argparse
import json
import os
import random
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

WEIGHT_CAP = 10          # a strong performer maxes at 10x the base odds
COOLDOWN_STANDARD = 0.25  # recent winners keep 1/4 odds on standard events


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def iso_to_date(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def display_name(full_name):
    """'Jordan Avery' -> 'Jordan A.'  (privacy-safe for the public board)."""
    parts = full_name.split()
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[-1][0]}."


def entrant_weight(member, event, cooldown_days):
    """Weight for one member on one event, after cap and cooldown."""
    weight = min(1 + member.get("points", 0), WEIGHT_CAP)

    last_won = member.get("last_won")
    if last_won:
        days_since = (iso_to_date(event["date"]) - iso_to_date(last_won)).days
        if 0 <= days_since < cooldown_days:
            if event.get("tier") == "premium":
                return 0.0                    # sit this premium one out
            weight *= COOLDOWN_STANDARD        # reduced odds on standard events
    return float(weight)


def weighted_order(entrants, rng):
    """Weighted random ordering. Higher weight -> more likely near the front.
    Zero-weight entrants are dropped (they sit this event out)."""
    keyed = []
    for e in entrants:
        w = e["weight"]
        if w <= 0:
            continue
        # Efraimidis-Spirakis weighted sampling key
        key = rng.random() ** (1.0 / w)
        keyed.append((key, e))
    keyed.sort(key=lambda t: t[0], reverse=True)
    return [e for _, e in keyed]


def draw_event(event, entries, members_by_id, cooldown_days, rng):
    # Build the entrant pool for this event
    entrants = []
    for row in entries:
        if row["event_id"] != event["id"]:
            continue
        m = members_by_id.get(row["member_id"])
        if not m:
            continue
        # max_party lets an event cap group size to spread seats across more
        # households (e.g. premium games -> 2), while uncapped events fill seats.
        cap = min(4, event.get("max_party", 4))
        entrants.append({
            "member": m,
            "seats_requested": max(1, min(cap, row.get("seats_requested", 1))),
            "weight": entrant_weight(m, event, cooldown_days),
        })

    ordering = weighted_order(entrants, rng)

    seats_total = event.get("seats", 4)
    remaining = seats_total
    winners, waitlist = [], []

    for e in ordering:
        m = e["member"]
        want = e["seats_requested"]
        if want <= remaining:
            winners.append({
                "member_id": m["id"],
                "name": m["name"],
                "display_name": display_name(m["name"]),
                "email": m["email"],
                "dept": m.get("dept", ""),
                "site": m.get("site", ""),
                "seats": want,
                "status": "pending",  # -> confirmed / declined / timed_out via reconcile.py
            })
            remaining -= want
        else:
            # Party doesn't fit the seats left -> goes to the waitlist in order.
            waitlist.append({
                "member_id": m["id"],
                "name": m["name"],
                "display_name": display_name(m["name"]),
                "email": m["email"],
                "seats_requested": want,
            })
        if remaining == 0:
            break

    # Anyone after seats ran out is also waitlisted, in draw order.
    seen = {w["member_id"] for w in winners} | {w["member_id"] for w in waitlist}
    for e in ordering:
        if e["member"]["id"] not in seen:
            waitlist.append({
                "member_id": e["member"]["id"],
                "name": e["member"]["name"],
                "display_name": display_name(e["member"]["name"]),
                "email": e["member"]["email"],
                "seats_requested": e["seats_requested"],
            })

    return {
        "event_id": event["id"],
        "title": event["title"],
        "date": event["date"],
        "league": event.get("league", ""),
        "tier": event.get("tier", ""),
        "seats_total": seats_total,
        "seats_filled": seats_total - remaining,
        "seats_open": remaining,
        "max_party": min(4, event.get("max_party", 4)),
        "entrant_count": len(entrants),
        "winners": winners,
        "waitlist": waitlist,
    }


def main():
    ap = argparse.ArgumentParser(description="Run the CandyCo ticket lottery draw.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true", help="draw every open event")
    g.add_argument("--event", help="draw a single event by id")
    ap.add_argument("--seed", type=int, help="reproducible draw (testing)")
    ap.add_argument("--commit", action="store_true",
                    help="update members.json + mark events drawn")
    args = ap.parse_args()

    events_doc = load("events.json")
    members_doc = load("members.json")
    entries_doc = load("entries.json")
    cooldown_days = members_doc.get("cooldown_days", 45)
    members_by_id = {m["id"]: m for m in members_doc["members"]}

    if args.event:
        targets = [e for e in events_doc["events"] if e["id"] == args.event]
        if not targets:
            raise SystemExit(f"No event with id {args.event!r}")
    else:
        targets = [e for e in events_doc["events"] if e.get("status") == "open"]

    if not targets:
        print("Nothing to draw (no open events).")
        return

    rng = random.Random(args.seed)  # seed=None -> nondeterministic

    draws = [draw_event(ev, entries_doc["entries"], members_by_id, cooldown_days, rng)
             for ev in targets]

    stamp = datetime.now().isoformat(timespec="seconds")
    for d in draws:
        d["drawn_at"] = stamp  # confirm window (reconcile.py) counts from here

    # PUBLIC results file (no emails, no full names) for the board
    public = {"generated": stamp, "draws": []}
    for d in draws:
        public["draws"].append({
            "event_id": d["event_id"], "title": d["title"], "date": d["date"],
            "league": d["league"], "tier": d["tier"],
            "seats_total": d["seats_total"], "seats_filled": d["seats_filled"],
            "seats_open": d["seats_open"], "entrant_count": d["entrant_count"],
            "winners": [{"display_name": w["display_name"], "dept": w["dept"],
                         "site": w["site"], "seats": w["seats"]} for w in d["winners"]],
        })
    with open(os.path.join(DATA, "results.json"), "w", encoding="utf-8") as f:
        json.dump(public, f, indent=2)

    # PRIVATE details file (full names + emails) for the emails / cascade
    with open(os.path.join(DATA, "draw_details.json"), "w", encoding="utf-8") as f:
        json.dump({"generated": stamp, "draws": draws}, f, indent=2)

    # Console summary
    print(f"Drew {len(draws)} event(s):\n")
    for d in draws:
        print(f"  {d['date']}  {d['title']}  [{d['tier']}]")
        print(f"    {d['entrant_count']} entrants -> "
              f"{d['seats_filled']}/{d['seats_total']} seats filled")
        for w in d["winners"]:
            print(f"      WIN   {w['display_name']:<12} {w['dept']:<13} {w['seats']} seat(s)")
        for w in d["waitlist"][:3]:
            print(f"      wait  {w['display_name']:<12} (next up)")
        print()

    if args.commit:
        # Record wins, reset that person's earned points, mark event drawn.
        for d, ev in zip(draws, targets):
            for w in d["winners"]:
                m = members_by_id[w["member_id"]]
                m["last_won"] = ev["date"]
                m["points"] = 0
            ev["status"] = "drawn"
        with open(os.path.join(DATA, "members.json"), "w", encoding="utf-8") as f:
            json.dump(members_doc, f, indent=2)
        with open(os.path.join(DATA, "events.json"), "w", encoding="utf-8") as f:
            json.dump(events_doc, f, indent=2)
        print("Committed: members.json (last_won / points reset) + events.json (status=drawn).")
    else:
        print("Dry run. Re-run with --commit to persist wins and mark events drawn.")


if __name__ == "__main__":
    main()
