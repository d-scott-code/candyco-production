#!/usr/bin/env python3
"""
Render the lottery's outbound emails from the draw output.

Two jobs:
  winners   one "you won" email per still-pending winner, with a confirm link
            and a hard deadline (drawn_at + confirm_window_hours).
  reminder  one broadcast email listing events whose entry closes within
            config.reminder_days_before_close.

Emails are written to the git-ignored outbox/ (they contain names + emails).
A send step (Power Automate watching the folder, or a Graph sendMail loop) picks
them up — see SCHEDULING.md. Nothing here talks to the network.

    python3 notify.py winners  [--as-of 2026-10-19T09:00]
    python3 notify.py reminder [--as-of 2026-10-16T09:00]
"""

import argparse
from datetime import timedelta
from urllib.parse import quote

import common


def _events_by_id():
    return {e["id"]: e for e in common.load("events.json")["events"]}


def deadline_for(winner, draw, window_hours):
    """Stored per-winner deadline wins; otherwise drawn_at + window."""
    if winner.get("confirm_deadline"):
        return common.parse_dt(winner["confirm_deadline"])
    return common.parse_dt(draw["drawn_at"]) + timedelta(hours=window_hours)


def build_winner_email(winner, draw, event, config, deadline_dt):
    confirm_link = (f'{config["confirm_url"]}?event={quote(draw["event_id"])}'
                    f'&who={quote(winner["member_id"])}')
    html = common.render("winner.html", {
        "name": winner["name"],
        "event_title": draw["title"],
        "event_date": common.fmt_date(draw["date"]),
        "event_time": common.fmt_time(event.get("tipoff", "")),
        "seats": winner["seats"],
        "seat_location": config["seat_location"],
        "confirm_deadline": common.fmt_datetime(deadline_dt),
        "confirm_link": confirm_link,
        "board_url": config["board_url"],
    })
    return {
        "to": winner["email"],
        "subject": f'\U0001f39f You won tickets — {draw["title"]}',
        "filename": f'winner_{draw["event_id"]}_{winner["member_id"]}.html',
        "html": html,
    }


def cmd_winners(args):
    config = common.load_config()
    details = common.load("draw_details.json")
    events = _events_by_id()
    window = config.get("confirm_window_hours", 48)

    emails = []
    for draw in details["draws"]:
        event = events.get(draw["event_id"], {})
        for w in draw["winners"]:
            if w.get("status") not in (None, "pending"):
                continue  # already confirmed / declined / timed out
            emails.append(build_winner_email(w, draw, event, config,
                                             deadline_for(w, draw, window)))

    label = args.label or f"winners-{common.now_or(args.as_of):%Y%m%dT%H%M%S}"
    if not emails:
        print("No pending winners to notify.")
        return
    out, manifest = common.write_outbox(label, emails)
    print(f"Wrote {len(manifest)} winner email(s) to {out}")
    for m in manifest:
        print(f"  -> {m['to']:<32} {m['subject']}")


def cmd_reminder(args):
    config = common.load_config()
    events = common.load("events.json")["events"]
    as_of = common.now_or(args.as_of)
    horizon = config.get("reminder_days_before_close", 3)

    closing = []
    for e in events:
        if e.get("status") != "open":
            continue
        days = (common.parse_dt(e["entry_close"]) - as_of).days
        if 0 <= days <= horizon:
            closing.append((days, e))
    closing.sort()

    if not closing:
        print("No events closing within the reminder window.")
        return

    items = "".join(
        f'<li><b>{e["title"]}</b> — {common.fmt_date(e["date"])} '
        f'(entries close {common.fmt_date(e["entry_close"])})</li>'
        for _, e in closing)
    html = common.render("reminder.html", {
        "event_list": items,
        "next_close_date": common.fmt_date(closing[0][1]["entry_close"]),
        "board_url": config["board_url"],
    })
    email = {
        "to": config.get("broadcast_to", "all-eligible@candyco.com"),
        "subject": "⏳ CandyCo tickets — entries closing soon",
        "filename": "reminder.html",
        "html": html,
    }
    label = args.label or f"reminder-{as_of:%Y%m%dT%H%M%S}"
    out, _ = common.write_outbox(label, [email])
    print(f"Wrote reminder ({len(closing)} event(s)) to {out} -> {email['to']}")


def main():
    ap = argparse.ArgumentParser(description="Render lottery emails to the outbox.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("winners", "reminder"):
        p = sub.add_parser(name)
        p.add_argument("--as-of", help="ISO datetime override (testing)")
        p.add_argument("--label", help="outbox subfolder name override")
    args = ap.parse_args()
    (cmd_winners if args.cmd == "winners" else cmd_reminder)(args)


if __name__ == "__main__":
    main()
