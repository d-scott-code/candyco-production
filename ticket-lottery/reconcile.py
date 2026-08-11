#!/usr/bin/env python3
"""
Process ticket confirmations and cascade unclaimed seats — the automated
follow-through after a draw.

For each winner:
  confirmed        -> keeps the seats.
  declined         -> seats are freed.
  no response and past the 48h deadline -> timed out, seats are freed.
  no response, still within the window   -> stays pending (checked again next run).

Freed seats cascade down the ordered waitlist (keeping each party together, up to
the event's max_party). Newly promoted winners get their own 48h deadline and a
"you won" email. Any seats left after the waitlist is exhausted are marked open,
and a last-minute broadcast is generated so they don't go to waste.

Reads  data/draw_details.json + data/confirmations.json.
Writes data/draw_details.json (private, updated) + data/results.json (public board)
       and promotion / last-minute emails into the git-ignored outbox/.
With --commit it also records cooldown (last_won / points reset) for CONFIRMED
winners in members.json and marks their events "drawn" in events.json.

    python3 reconcile.py --as-of 2026-10-21T09:00
    python3 reconcile.py --as-of 2026-10-21T09:00 --commit
"""

import argparse
from datetime import datetime, timedelta

import common
from notify import build_winner_email


def latest_confirmations():
    conf = {}
    for r in common.load("confirmations.json")["confirmations"]:
        key = (r["member_id"], r["event_id"])
        if key not in conf or r["timestamp"] > conf[key]["timestamp"]:
            conf[key] = r
    return conf


def public_view(details, stamp):
    pub = {"generated": stamp, "draws": []}
    for d in details["draws"]:
        pub["draws"].append({
            "event_id": d["event_id"], "title": d["title"], "date": d["date"],
            "league": d["league"], "tier": d["tier"],
            "seats_total": d["seats_total"], "seats_filled": d["seats_filled"],
            "seats_open": d["seats_open"], "entrant_count": d["entrant_count"],
            "winners": [{"display_name": w["display_name"], "dept": w["dept"],
                         "site": w["site"], "seats": w["seats"],
                         "status": w.get("status", "pending")} for w in d["winners"]],
        })
    return pub


def reconcile(details, conf, members_by_id, events_by_id, config, as_of):
    window = config.get("confirm_window_hours", 48)
    promo_emails = []
    lastminute = []

    for draw in details["draws"]:
        event = events_by_id.get(draw["event_id"], {})
        deadline_orig = common.parse_dt(draw["drawn_at"]) + timedelta(hours=window)
        kept, released, freed = [], list(draw.get("released", [])), 0

        for w in draw["winners"]:
            if not w.get("confirm_deadline"):
                w["confirm_deadline"] = deadline_orig.isoformat(timespec="seconds")
            if w.get("status") == "confirmed":
                kept.append(w)
                continue
            r = conf.get((w["member_id"], draw["event_id"]))
            if r and r["response"] == "confirm":
                w["status"] = "confirmed"
                kept.append(w)
            elif r and r["response"] == "decline":
                w["status"] = "declined"
                released.append(w)
                freed += w["seats"]
            elif as_of >= common.parse_dt(w["confirm_deadline"]):
                w["status"] = "timed_out"
                released.append(w)
                freed += w["seats"]
            else:
                kept.append(w)  # still pending, deadline not reached

        # Cascade freed seats down the waitlist, keeping parties together.
        cap = draw.get("max_party", 4)
        still_wait = []
        for p in draw["waitlist"]:
            want = min(p["seats_requested"], cap)
            if freed > 0 and want <= freed:
                m = members_by_id.get(p["member_id"], {})
                new_deadline = (as_of + timedelta(hours=window)).isoformat(timespec="seconds")
                nw = {
                    "member_id": p["member_id"], "name": p["name"],
                    "display_name": p["display_name"], "email": p["email"],
                    "dept": m.get("dept", ""), "site": m.get("site", ""),
                    "seats": want, "status": "pending", "promoted": True,
                    "confirm_deadline": new_deadline,
                }
                kept.append(nw)
                freed -= want
                promo_emails.append(build_winner_email(
                    nw, draw, event, config, common.parse_dt(new_deadline)))
            else:
                still_wait.append(p)

        draw["winners"] = kept
        draw["waitlist"] = still_wait
        draw["released"] = released
        draw["seats_filled"] = sum(w["seats"] for w in kept)
        draw["seats_open"] = draw["seats_total"] - draw["seats_filled"]
        if draw["seats_open"] > 0 and not still_wait and draw["entrant_count"] > 0:
            lastminute.append(draw)

    return promo_emails, lastminute


def main():
    ap = argparse.ArgumentParser(description="Reconcile confirmations & cascade seats.")
    ap.add_argument("--as-of", help="ISO datetime override (testing)")
    ap.add_argument("--label", help="outbox subfolder name override")
    ap.add_argument("--commit", action="store_true",
                    help="record cooldown for confirmed winners + mark events drawn")
    args = ap.parse_args()

    config = common.load_config()
    details = common.load("draw_details.json")
    conf = latest_confirmations()
    members_doc = common.load("members.json")
    members_by_id = {m["id"]: m for m in members_doc["members"]}
    events_doc = common.load("events.json")
    events_by_id = {e["id"]: e for e in events_doc["events"]}
    as_of = common.now_or(args.as_of)

    promo_emails, lastminute = reconcile(
        details, conf, members_by_id, events_by_id, config, as_of)

    stamp = datetime.now().isoformat(timespec="seconds")
    details["generated"] = stamp
    common.save("draw_details.json", details)
    common.save("results.json", public_view(details, stamp))

    # Build outbox: promotion emails + one last-minute broadcast
    emails = list(promo_emails)
    if lastminute:
        items = "".join(
            f'<li><b>{d["title"]}</b> — {common.fmt_date(d["date"])} '
            f'({d["seats_open"]} seat{"s" if d["seats_open"] != 1 else ""} open)</li>'
            for d in lastminute)
        emails.append({
            "to": config.get("broadcast_to", "all-eligible@candyco.com"),
            "subject": "⚡ Last-minute CandyCo tickets available",
            "filename": "lastminute.html",
            "html": common.render("lastminute.html",
                                  {"event_list": items, "board_url": config["board_url"]}),
        })

    if emails:
        label = args.label or f"reconcile-{as_of:%Y%m%dT%H%M%S}"
        out, _ = common.write_outbox(label, emails)
        print(f"Wrote {len(emails)} follow-up email(s) to {out}")

    # Console summary
    for d in details["draws"]:
        conf_n = sum(1 for w in d["winners"] if w.get("status") == "confirmed")
        pend_n = sum(1 for w in d["winners"] if w.get("status") == "pending")
        rel_n = len(d.get("released", []))
        print(f"  {d['date']}  {d['title']}: {conf_n} confirmed, {pend_n} pending, "
              f"{rel_n} released, {d['seats_open']} open")

    if args.commit:
        for d in details["draws"]:
            ev = events_by_id.get(d["event_id"])
            if ev:
                ev["status"] = "drawn"
            for w in d["winners"]:
                if w.get("status") == "confirmed":
                    m = members_by_id.get(w["member_id"])
                    if m:
                        m["last_won"] = d["date"]
                        m["points"] = 0
        common.save("members.json", members_doc)
        common.save("events.json", events_doc)
        print("Committed: cooldown for confirmed winners + events marked drawn.")
    else:
        print("Dry run. Re-run with --commit to persist cooldown / event status.")


if __name__ == "__main__":
    main()
